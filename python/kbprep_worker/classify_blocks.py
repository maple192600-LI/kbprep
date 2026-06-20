"""Block classification for the kbprep cleaning pipeline.

The classifier is deliberately conservative: protected knowledge content wins
before pollution patterns run. This prevents tutorial steps, case reviews, and
platform-rule examples from being deleted just because they mention CTA words.
"""

from __future__ import annotations

import logging
import re

from .diagnose.text_quality import garbled_signal_count
from .quality.thresholds import CLASSIFICATION_CONFIDENCE
from .rule_loader import LoadedCleaningRules, load_cleaning_rules

logger = logging.getLogger(__name__)


def classify_blocks(
    blocks: list[dict],
    profile: str = "standard",
    document_type: str = "",
    rule_templates: list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    """Assign type, status, protection, and confidence to each block."""
    rules = load_cleaning_rules(
        profile=profile,
        document_type=document_type,
        templates=tuple(rule_templates or ()),
    )
    for block in blocks:
        _classify_one_block(block, rules)
    return blocks


def _classify_one_block(block: dict, rules: LoadedCleaningRules) -> None:
    text = block.get("text", "").strip()
    if not text:
        _mark_empty_block(block)
        return

    block_type = block.get("type")
    if _mark_marketing_wrapper(block, text, rules):
        return
    if _mark_structural_block(block, block_type):
        return
    if _mark_image_placeholder(block, block_type):
        return
    if _mark_known_protected_block(block, block_type):
        return
    if _mark_protected_text(block, text, rules):
        return
    if _mark_contextual_cta(block, text, rules):
        return
    if _mark_discard_or_evidence(block, text, rules):
        return
    if _is_garbled(text):
        _mark_garbled_block(block)
        return
    block["status"] = "keep"
    block["confidence"] = CLASSIFICATION_CONFIDENCE["default_keep"]


def _mark_empty_block(block: dict) -> None:
    block["status"] = "discard"
    block["type"] = "empty"
    block["reason"] = "empty block"


def _mark_marketing_wrapper(block: dict, text: str, rules: LoadedCleaningRules) -> bool:
    marketing_wrapper_type = _marketing_wrapper_type(block, text, rules)
    if not marketing_wrapper_type:
        return False
    block["status"] = "discard"
    block["type"] = marketing_wrapper_type
    block["reason"] = "knowledge-base wrapper/marketing material"
    block["confidence"] = CLASSIFICATION_CONFIDENCE["marketing_wrapper_discard"]
    return True


def _mark_structural_block(block: dict, block_type: object) -> bool:
    if block_type not in {"code", "table", "section_heading", "quote"}:
        return False
    block["status"] = "keep"
    block["confidence"] = CLASSIFICATION_CONFIDENCE["structural_keep"]
    if block_type in {"code", "table"}:
        block["protected"] = True
    return True


def _mark_image_placeholder(block: dict, block_type: object) -> bool:
    if block_type not in {"image_evidence", "image_operation", "diagram"}:
        return False
    block["status"] = "unclassified"
    block["confidence"] = CLASSIFICATION_CONFIDENCE["image_unclassified"]
    return True


def _mark_known_protected_block(block: dict, block_type: object) -> bool:
    if block_type not in {"operation_step", "case_step", "tool_instruction", "prompt"}:
        return False
    block["status"] = "keep"
    block["protected"] = True
    block["confidence"] = CLASSIFICATION_CONFIDENCE["protected_keep"]
    return True


def _mark_protected_text(block: dict, text: str, rules: LoadedCleaningRules) -> bool:
    protected_type = _protected_type(text, rules)
    if not protected_type:
        return False
    block["status"] = "keep"
    block["type"] = protected_type
    block["protected"] = True
    block["confidence"] = CLASSIFICATION_CONFIDENCE["protected_keep"]
    return True


def _mark_contextual_cta(block: dict, text: str, rules: LoadedCleaningRules) -> bool:
    if not _is_contextual_cta_knowledge(text, block, rules):
        return False
    block["status"] = "keep"
    block["type"] = "case_step"
    block["protected"] = True
    block["reason"] = "CTA phrase appears inside a case, rule, or handling step"
    block["confidence"] = CLASSIFICATION_CONFIDENCE["contextual_cta_keep"]
    return True


def _mark_discard_or_evidence(block: dict, text: str, rules: LoadedCleaningRules) -> bool:
    discard_type = _discard_type(text, rules)
    if discard_type:
        block["status"] = "discard"
        block["type"] = discard_type
        block["reason"] = f"matches discard pattern: {discard_type}"
        block["confidence"] = CLASSIFICATION_CONFIDENCE["discard_pattern"]
        return True
    evidence_type = _evidence_type(text, rules)
    if not evidence_type:
        return False
    block["status"] = "evidence"
    block["type"] = evidence_type
    block["reason"] = f"matches evidence pattern: {evidence_type}"
    block["confidence"] = CLASSIFICATION_CONFIDENCE["evidence_pattern"]
    return True


def _mark_garbled_block(block: dict) -> None:
    block["status"] = "discard"
    block["type"] = "garbled_text"
    block["reason"] = "garbled text detected"
    block["confidence"] = CLASSIFICATION_CONFIDENCE["garbled_discard"]


def _protected_type(text: str, rules: LoadedCleaningRules) -> str | None:
    if text.startswith("```"):
        return "code"
    if text.startswith("|") or "<table" in text.lower():
        return "table"
    for signal in rules.protected_patterns:
        if re.search(signal.pattern, text, re.IGNORECASE | re.MULTILINE):
            return signal.label
    return None


def _discard_type(text: str, rules: LoadedCleaningRules) -> str | None:
    if _matches_any_pattern(text, rules.transcript_filler_patterns):
        return "transcript_filler"
    if _has_cta_signal(text, rules):
        return "marketing_cta"
    if _matches_any_pattern(text, rules.refund_patterns):
        return "refund_policy"
    if _matches_any_pattern(text, rules.footer_patterns):
        return "footer"
    return None


def _evidence_type(text: str, rules: LoadedCleaningRules) -> str | None:
    for signal in rules.evidence_patterns:
        if re.search(signal.pattern, text, re.IGNORECASE):
            return signal.label
    return None


def _marketing_wrapper_type(block: dict, text: str, rules: LoadedCleaningRules) -> str | None:
    """Remove source packaging that markets the community/book rather than teaching."""
    heading_path = block.get("heading_path", []) or []
    heading_text = " ".join(str(item) for item in heading_path)
    searchable = f"{heading_text}\n{text}"

    # Keep configured document/package titles themselves; remove surrounding sales/back-matter sections.
    if _is_marketing_wrapper_passthrough_title(text, rules):
        return None

    if _matches_any_pattern(text, rules.refund_patterns):
        return None

    if _is_standalone_direct_cta(text, rules):
        return "marketing_cta"

    if _has_method_knowledge_signal(text, heading_text, rules):
        return None

    if any(term in searchable for term in rules.marketing_wrapper_heading_terms):
        if any(term in searchable for term in rules.marketing_wrapper_back_matter_terms):
            return "back_matter"
        return "marketing_wrapper"

    if _matches_any_pattern(text, rules.marketing_wrapper_line_patterns):
        return "marketing_wrapper"

    return None


def _is_marketing_wrapper_passthrough_title(text: str, rules: LoadedCleaningRules) -> bool:
    title = text.strip().lstrip("# ").strip()
    return title in rules.marketing_wrapper_passthrough_titles


def _is_standalone_direct_cta(text: str, rules: LoadedCleaningRules) -> bool:
    """Direct short CTA lines are pollution even inside an otherwise useful chapter."""
    compact = re.sub(r"\s+", "", text)
    if len(compact) > 80:
        return False
    compact_lower = compact.lower()
    if not any(term.replace(" ", "").lower() in compact_lower for term in rules.cta_keywords):
        return False
    return not any(term in compact for term in rules.knowledge_terms)


def _has_method_knowledge_signal(text: str, heading_text: str, rules: LoadedCleaningRules) -> bool:
    """True when marketing-related words are part of reusable method/case content."""
    searchable = f"{heading_text}\n{text}"
    if _protected_type(text, rules) == "operation_step":
        return True
    if any(term in searchable for term in rules.business_method_context_terms + rules.knowledge_terms):
        return True
    return bool(re.search(
        r"(\u5982\u4f55|\u600e\u4e48|\u65b9\u6cd5|\u6b65\u9aa4|\u7b56\u7565|\u6848\u4f8b|\u590d\u76d8|\u5b9e\u64cd|\u5e95\u5c42\u903b\u8f91).{0,80}"
        r"(\u5f15\u6d41|\u79c1\u57df|\u8d26\u53f7|\u8fd0\u8425|\u5de5\u5177|\u6d41\u91cf|\u8f6c\u5316|\u5ba2\u7fa4|\u8fed\u4ee3)",
        searchable,
    ))


def _is_garbled(text: str) -> bool:
    """Check unreadable Unicode artifacts without penalizing normal scripts."""
    if len(text) < 20:
        return False
    garbled_chars = garbled_signal_count(text)
    if garbled_chars == 0:
        return False
    return text.count("\ufffd") >= 3 or garbled_chars / len(text) > 0.15


def _is_contextual_cta_knowledge(text: str, block: dict | None = None, rules: LoadedCleaningRules | None = None) -> bool:
    """Keep CTA-like phrases when they are the object of a lesson or case."""
    rules = rules or load_cleaning_rules()
    if not _has_cta_signal(text, rules):
        return False

    knowledge_terms = rules.knowledge_terms + rules.tutorial_indicators
    if any(term in text for term in knowledge_terms):
        return True

    block = block or {}
    heading_text = " ".join(str(item) for item in (block.get("heading_path", []) or []))
    if any(term in heading_text for term in rules.business_method_context_terms + rules.knowledge_terms):
        return True

    return bool(re.search(
        r"(\u5982\u679c|\u5f53|\u51fa\u73b0).{0,40}"
        r"(\u626b\u7801|\u5165\u7fa4|\u52a0\u7fa4|\u793e\u7fa4|\u4f53\u9a8c\u5361).{0,60}"
        r"(\u4fdd\u7559|\u6807\u8bb0|\u8bb0\u5f55|\u5224\u65ad|\u5224\u5b9a|\u5220\u9664)",
        text,
    ))


def _has_cta_signal(text: str, rules: LoadedCleaningRules) -> bool:
    text_lower = text.lower()
    return any(term in text or term.lower() in text_lower for term in rules.cta_keywords)


def _matches_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
