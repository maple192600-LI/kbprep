"""
clean_rules - block-level cleaning rules.
Operates on blocks.jsonl, NOT on raw markdown.

Each block's status is updated based on classification.
Blocks with status=discard are removed from cleaned output.
Blocks with status=evidence go to evidence/ directory.
"""
import logging

from .rule_loader import LoadedCleaningRules, load_cleaning_rules, rule_matches
from .rule_schema import CleaningRule
from .structure_patterns import has_step_signal

logger = logging.getLogger(__name__)

WRAPPER_HEADING_RISK_TAGS = frozenset({
    "report_author_byline_heading",
    "report_source_wrapper_heading",
})


def apply_clean_rules(
    blocks: list[dict],
    profile: str = "standard",
    document_type: str = "",
    rule_templates: list[str] | tuple[str, ...] | None = None,
    source_identity: str = "",
) -> list[dict]:
    """
    Apply cleaning rules to classified blocks.
    Refines classification based on context.
    """
    rules = load_cleaning_rules(
        profile=profile,
        document_type=document_type,
        templates=tuple(rule_templates or ()),
        source_identity=source_identity,
    )
    derived_blocks: list[dict] = []
    for block in blocks:
        derived_blocks.extend(_process_clean_block(block, rules))
    if derived_blocks:
        blocks.extend(derived_blocks)
    return blocks


def _process_clean_block(block: dict, rules: LoadedCleaningRules) -> list[dict]:
    text = block.get("text", "").strip()
    status = block.get("status", "unclassified")
    block_type = block.get("type", "unknown")
    if status in ("discard", "evidence"):
        return []

    promo_blocks = _split_promotional_lines(block, rules)
    text = block.get("text", "").strip()
    if promo_blocks and not text:
        _mark_all_promo_block(block)
        return promo_blocks
    if block.get("protected"):
        block["status"] = "keep"
        return promo_blocks
    if _apply_wrapper_heading_rule_if_needed(block, text, block_type, rules):
        return promo_blocks
    if _apply_promotional_match_if_needed(block, text, block_type, rules):
        return promo_blocks
    if _mark_contextual_cta_review(block, text, block_type, rules):
        return promo_blocks
    if block_type == "duplicate":
        block["status"] = "discard"
        block["reason"] = "duplicate content"
    return promo_blocks


def _mark_all_promo_block(block: dict) -> None:
    block["status"] = "discard"
    block["type"] = "marketing_cta"
    block["reason"] = "all lines matched promotional patterns"


def _apply_promotional_match_if_needed(
    block: dict,
    text: str,
    block_type: object,
    rules: LoadedCleaningRules,
) -> bool:
    matched_rule = _matching_promotional_rule(text, rules)
    if block_type == "section_heading" or not matched_rule:
        return False
    _apply_matched_rule(block, matched_rule)
    return True


def _apply_wrapper_heading_rule_if_needed(
    block: dict,
    text: str,
    block_type: object,
    rules: LoadedCleaningRules,
) -> bool:
    if block_type != "section_heading":
        return False
    matched_rule = _matching_promotional_rule(text, rules)
    if matched_rule is None or matched_rule.action == "protect":
        return False
    if matched_rule.risk_tag not in WRAPPER_HEADING_RISK_TAGS:
        return False
    _apply_matched_rule(block, matched_rule)
    return True


def _mark_contextual_cta_review(
    block: dict,
    text: str,
    block_type: object,
    rules: LoadedCleaningRules,
) -> bool:
    if block_type == "section_heading" or not _has_cta_keywords(text, rules):
        return False
    if _is_tutorial_context(text, block, rules):
        return False
    block["status"] = "review"
    block["risk_tags"] = block.get("risk_tags", [])
    if "possible_cta" not in block["risk_tags"]:
        block["risk_tags"].append("possible_cta")
    block["reason"] = block.get("reason", "") + " | contains CTA keywords"
    return True


def _split_promotional_lines(block: dict, rules: LoadedCleaningRules) -> list[dict]:
    """Move standalone promo/update lines out of mixed useful blocks."""
    text = block.get("text", "")
    if "\n" not in text:
        return []

    kept_lines: list[str] = []
    promo_lines: list[tuple[str, CleaningRule]] = []
    for line in text.splitlines():
        stripped = line.strip()
        matched_rule = _matching_promotional_rule(stripped, rules)
        if stripped and matched_rule and matched_rule.action == "discard":
            promo_lines.append((stripped, matched_rule))
        else:
            kept_lines.append(line)

    if not promo_lines:
        return []

    block["text"] = "\n".join(line for line in kept_lines if line.strip()).strip()
    if "promo_line_removed" not in block.setdefault("risk_tags", []):
        block["risk_tags"].append("promo_line_removed")

    derived = []
    for idx, (line, matched_rule) in enumerate(promo_lines, start=1):
        derived.append({
            "block_id": f"{block.get('block_id', 'block')}_promo_{idx:03d}",
            "source_sha256": block.get("source_sha256", ""),
            "page_start": block.get("page_start"),
            "page_end": block.get("page_end"),
            "line_start": block.get("line_start"),
            "line_end": block.get("line_end"),
            "heading_path": block.get("heading_path", []),
            "type": "marketing_cta",
            "text": line,
            "images": [],
            "status": "discard",
            "risk_tags": [matched_rule.risk_tag],
            "protected": False,
            "confidence": 0.95,
            "reason": matched_rule.reason,
            "cleaning_rule_id": matched_rule.rule_id,
            "cleaning_rule_source": matched_rule.source,
        })
    return derived


def _matching_promotional_rule(line: str, rules: LoadedCleaningRules) -> CleaningRule | None:
    for rule in rules.promotional_line_rules:
        if rule.action == "protect" and rule_matches(rule, line):
            return rule
    for rule in rules.promotional_line_rules:
        if rule.action != "protect" and _is_confirmed_feedback_rule(rule) and rule_matches(rule, line):
            return rule
    if _is_contextual_promo_knowledge(line, rules):
        return None
    for rule in rules.promotional_line_rules:
        if rule.action != "protect" and rule_matches(rule, line):
            return rule
    return None


def _is_confirmed_feedback_rule(rule: CleaningRule) -> bool:
    return rule.risk_tag.startswith(("user_feedback_", "learned_feedback_"))


def _apply_matched_rule(block: dict, matched_rule) -> None:
    if matched_rule.action == "protect":
        block["status"] = "keep"
        block["protected"] = True
        block["reason"] = matched_rule.reason
    elif matched_rule.action == "review":
        block["status"] = "review"
        block["reason"] = matched_rule.reason
    else:
        block["status"] = "discard"
        block["type"] = "marketing_cta"
        block["reason"] = matched_rule.reason
    block["risk_tags"] = block.get("risk_tags", [])
    if matched_rule.risk_tag not in block["risk_tags"]:
        block["risk_tags"].append(matched_rule.risk_tag)
    block["cleaning_rule_id"] = matched_rule.rule_id
    block["cleaning_rule_source"] = matched_rule.source


def _is_contextual_promo_knowledge(line: str, rules: LoadedCleaningRules) -> bool:
    return any(term in line for term in rules.knowledge_terms)


def _has_cta_keywords(text: str, rules: LoadedCleaningRules) -> bool:
    """Check if text contains CTA-related keywords."""
    text_lower = text.lower()
    return any(kw in text or kw.lower() in text_lower for kw in rules.cta_keywords)


def _is_tutorial_context(text: str, block: dict, rules: LoadedCleaningRules) -> bool:
    """
    Determine if CTA keywords appear in tutorial/educational context.
    Returns True if the content is likely educational, not a CTA.
    """
    heading_path = block.get("heading_path", [])
    heading_text = " ".join(heading_path).lower()

    # Check heading path for tutorial indicators
    if any(ind.lower() in heading_text for ind in rules.tutorial_indicators):
        return True

    # Check if text contains step numbers (1. 2. 3.)
    if has_step_signal(text):
        return True

    # Check if text contains code blocks or commands
    if "```" in text or "$ " in text:
        return True

    if any(term in text for term in rules.knowledge_terms):
        return True

    # Check text length: CTAs are typically short (<200 chars),
    # educational content is longer
    if len(text) > 200:
        return True

    # Check if text contains analytical/educational language
    text_lower = text.lower()
    if any(ind.lower() in text_lower for ind in rules.tutorial_indicators + rules.knowledge_terms):
        return True

    return False
