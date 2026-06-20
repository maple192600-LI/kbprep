"""Cleanup safety helpers for quality gates."""

import re

from ..rule_loader import LoadedCleaningRules, rule_matches
from .markdown_signals import _extract_image_sources

DISCARDED_BODY_LOSS_EXEMPT_TYPES = {
    "page_marker",
    "slide_chapter_divider",
    "translator_marketing_back_matter",
    "transcript_filler",
    "marketing_cta",
    "marketing_wrapper",
    "author_identity",
    "author_intro",
    "image_artifact",
    "layout_table_artifact",
    "layout_separator",
    "author_profile_links",
    "toc",
    "toc_heading",
    "empty_heading",
    "back_matter",
    "refund_policy",
    "footer",
    "qr_image",
    "empty",
}

def _matches_cleanup_pollution(text: str, rules: LoadedCleaningRules) -> bool:
    text_lower = text.lower()
    if any(keyword in text or keyword.lower() in text_lower for keyword in rules.cta_keywords):
        return True
    return any(rule_matches(rule, text) for rule in rules.promotional_line_rules)

def _qr_image_matches(text: str, rules: LoadedCleaningRules) -> list[str]:
    markers = [re.escape(marker) for marker in rules.qr_image_markers]
    if not markers:
        return []
    marker_re = "|".join(markers)
    return re.findall(rf'!\[.*\]\(.*(?:{marker_re}).*\)', text, re.IGNORECASE)

def _allows_cta_keyword_context(block: dict, rules: LoadedCleaningRules) -> bool:
    """CTA words can be legitimate when a protected tutorial block discusses rules or bad examples."""
    if block.get("protected"):
        return True
    if block.get("type") in {"operation_step", "case_step", "tool_instruction", "prompt", "code", "table"}:
        return True
    text = block.get("text", "")
    return any(term in text for term in rules.knowledge_terms)

def _counts_for_text_coverage(block: dict) -> bool:
    """Coverage gates measure body text retention, not image-link bookkeeping."""
    block_type = block.get("type")
    text = block.get("text", "").strip()
    if block.get("status") == "discard" and block_type in DISCARDED_BODY_LOSS_EXEMPT_TYPES:
        return False
    if block_type in {"image_evidence", "image_operation", "diagram"}:
        return not _is_markdown_image_only(text)
    return True

def _counts_for_discard_ratio(block: dict) -> bool:
    """Discard ratio gates body loss, not successful removal of known pollution."""
    block_type = block.get("type")
    if block.get("status") == "discard" and block_type in DISCARDED_BODY_LOSS_EXEMPT_TYPES:
        return False
    return _counts_for_text_coverage(block)

def _is_image_block(block: dict) -> bool:
    return block.get("type") in {"image_evidence", "image_operation", "diagram", "qr_image", "unknown_image"}

def _is_markdown_image_only(text: str) -> bool:
    return bool(_extract_image_sources(text)) and not re.sub(r'!\[[^\]]*\]\([^)]+\)', "", text or "").strip()


allows_cta_keyword_context = _allows_cta_keyword_context
counts_for_discard_ratio = _counts_for_discard_ratio
counts_for_text_coverage = _counts_for_text_coverage
is_image_block = _is_image_block
matches_cleanup_pollution = _matches_cleanup_pollution
qr_image_matches = _qr_image_matches
