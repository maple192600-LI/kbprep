"""Text quality and text-profile diagnosis helpers."""

from __future__ import annotations

import re
import unicodedata

from ..quality.thresholds import DIAGNOSIS_THRESHOLDS
from ..rule_loader import LoadedCleaningRules, load_cleaning_rules, rule_matches
from ..text_profile_rules import load_text_profile_signals
from ..text_quality_rules import load_text_quality_signals

# Chinese character range
CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\U00020000-\U0002a6df]')
# English letters and digits
ALNUM_RE = re.compile(r'[a-zA-Z0-9]')
# Control characters (excluding common whitespace)
CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
IGNORED_CONTROL_WHITESPACE = {"\n", "\r", "\t"}


def analyze_text_quality(
    text: str,
    profile: str = "standard",
    document_type: str = "",
    rule_templates: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Analyze text quality metrics."""
    cleaning_rules = _load_quality_cleaning_rules(profile, document_type, rule_templates)
    if not text:
        return _empty_quality_report(cleaning_rules)

    total = len(text)
    metrics = _quality_signal_counts(text)
    ratios = _quality_ratios(metrics, total)

    return {
        "total_chars": total,
        "chinese_ratio": round(metrics["chinese_chars"] / total, 4),
        "alnum_ratio": round(metrics["alnum_chars"] / total, 4),
        "control_ratio": round(metrics["control_chars"] / total, 4),
        "garbled_ratio": round(metrics["garbled_chars"] / total, 4),
        "garbled_chars": metrics["garbled_chars"],
        "non_common_unicode_ratio": round(ratios["non_common_unicode"], 4),
        "replacement_char_ratio": round(ratios["replacement_char"], 4),
        "mojibake_ratio": round(ratios["mojibake"], 4),
        "mojibake_chars": metrics["mojibake_chars"],
        "unreadable_text_ratio": round(ratios["unreadable_text"], 4),
        "ocr_ai_confusion_count": metrics["ocr_confusions"],
        "has_qr_text": _has_qr_text(text, cleaning_rules),
        "has_cta_text": _has_cta_text(text, cleaning_rules),
        "cleaning_rule_sources": list(cleaning_rules.sources),
    }


def _load_quality_cleaning_rules(
    profile: str,
    document_type: str,
    rule_templates: list[str] | tuple[str, ...] | None,
) -> LoadedCleaningRules:
    return load_cleaning_rules(
        profile=profile,
        document_type=document_type,
        templates=tuple(rule_templates or ()),
    )


def _empty_quality_report(cleaning_rules: LoadedCleaningRules) -> dict:
    return {
        "total_chars": 0,
        "chinese_ratio": 0.0,
        "alnum_ratio": 0.0,
        "control_ratio": 0.0,
        "garbled_ratio": 0.0,
        "garbled_chars": 0,
        "non_common_unicode_ratio": 0.0,
        "replacement_char_ratio": 0.0,
        "mojibake_ratio": 0.0,
        "mojibake_chars": 0,
        "unreadable_text_ratio": 0.0,
        "ocr_ai_confusion_count": 0,
        "has_qr_text": False,
        "has_cta_text": False,
        "cleaning_rule_sources": list(cleaning_rules.sources),
    }


def _quality_signal_counts(text: str) -> dict[str, int]:
    text_quality_signals = load_text_quality_signals()
    abnormal_sequence_chars = _abnormal_sequence_chars(text)
    mojibake_matches = text_quality_signals.mojibake_sequence_re.findall(text)
    mojibake_sequence_chars = sum(len(match) for match in mojibake_matches)
    mojibake_char_count = len(text_quality_signals.mojibake_char_re.findall(text))
    mojibake_token_chars = sum(len(match.group(0)) for match in text_quality_signals.mojibake_token_re.finditer(text))
    return {
        "chinese_chars": len(CJK_RE.findall(text)),
        "alnum_chars": len(ALNUM_RE.findall(text)),
        "control_chars": len(CONTROL_RE.findall(text)),
        "garbled_chars": garbled_signal_count(text, abnormal_sequence_chars),
        "non_common_unicode_chars": _non_common_unicode_count(text),
        "replacement_chars": text.count("\ufffd"),
        "mojibake_chars": max(mojibake_sequence_chars, mojibake_char_count, mojibake_token_chars),
        "ocr_confusions": len(text_quality_signals.ocr_ai_confusion_re.findall(text)),
    }


def garbled_signal_count(text: str, abnormal_sequence_chars: int | None = None) -> int:
    configured_count = abnormal_sequence_chars if abnormal_sequence_chars is not None else _abnormal_sequence_chars(text)
    return max(garbled_character_count(text), configured_count)


def garbled_character_count(text: str) -> int:
    return sum(1 for ch in text if _is_unreadable_unicode_char(ch))


def _abnormal_sequence_chars(text: str) -> int:
    pattern = load_text_quality_signals().abnormal_unicode_sequence_re
    return sum(len(match) for match in pattern.findall(text))


def _non_common_unicode_count(text: str) -> int:
    return sum(1 for ch in text if ord(ch) > 127 and _is_unreadable_unicode_char(ch))


def _is_unreadable_unicode_char(ch: str) -> bool:
    if ch == "\ufffd":
        return True
    if ch in IGNORED_CONTROL_WHITESPACE:
        return False
    category = unicodedata.category(ch)
    if category in {"Cc", "Cf", "Cs", "Co", "Cn"}:
        return True
    return False


def _quality_ratios(metrics: dict[str, int], total: int) -> dict[str, float]:
    non_common_unicode_ratio = metrics["non_common_unicode_chars"] / total
    replacement_char_ratio = metrics["replacement_chars"] / total
    mojibake_ratio = metrics["mojibake_chars"] / total
    signal_ratio = (metrics["chinese_chars"] + metrics["alnum_chars"]) / total
    replacement_unreadable = (
        replacement_char_ratio
        if signal_ratio < DIAGNOSIS_THRESHOLDS["replacement_char_low_signal_ratio"]
        else 0.0
    )
    return {
        "non_common_unicode": non_common_unicode_ratio,
        "replacement_char": replacement_char_ratio,
        "mojibake": mojibake_ratio,
        "unreadable_text": max(
            metrics["garbled_chars"] / total,
            non_common_unicode_ratio,
            mojibake_ratio,
            replacement_unreadable,
        ),
    }


def _has_qr_text(text: str, rules: LoadedCleaningRules) -> bool:
    return _matches_any(text, rules.qr_image_markers + rules.image_qr_indicators)


def _has_cta_text(text: str, rules: LoadedCleaningRules) -> bool:
    text_lower = text.lower()
    if any(keyword in text or keyword.lower() in text_lower for keyword in rules.cta_keywords):
        return True
    return any(rule_matches(rule, text) for rule in rules.promotional_line_rules)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def detect_text_profile(text: str, detected_format: str = "text") -> dict:
    """Classify text shape without summarizing or rewriting it."""
    headings = len(re.findall(r'^#{1,6}\s+', text, re.MULTILINE))
    numbered_steps = len(re.findall(
        r'^\s*(?:\d+[\.\)、)]\s+|第?[一二三四五六七八九十百千\d]+步[骤]?[：:、\.\s]|步骤\s*[一二三四五六七八九十百千\d]+[：:、\.\s])',
        text,
        re.MULTILINE,
    ))
    english_numbered_steps = len(re.findall(r'^\s*step\s*\d+[\uff1a:\.\)\-\s]+', text, re.MULTILINE | re.IGNORECASE))
    numbered_steps += english_numbered_steps
    timestamp_lines = len(re.findall(r'^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?', text, re.MULTILINE))
    speaker_lines = len(re.findall(r'^\s*[^:\n：]{1,24}[：:]\s+\S+', text, re.MULTILINE))
    table_rows = len(re.findall(r'^\|.+\|$', text, re.MULTILINE))
    chars = len(text)

    profile_signals = load_text_profile_signals()

    if headings >= 8 and chars > 12_000:
        profile = "ebook_or_long_report"
    elif detected_format == "subtitle_transcript" or timestamp_lines >= 3 or speaker_lines >= 8:
        profile = "transcript"
    elif _has_profile_term(text, profile_signals.tutorial_terms) or numbered_steps >= 3 or english_numbered_steps > 0:
        profile = "tutorial"
    elif _has_profile_term(text, profile_signals.meeting_terms):
        profile = "meeting_or_interview"
    elif _has_profile_term(text, profile_signals.note_terms):
        profile = "note"
    elif _has_profile_term(text, profile_signals.ebook_terms) and chars > 12_000:
        profile = "ebook_or_long_report"
    elif chars < 4_000:
        profile = "short_text"
    else:
        profile = "long_text"

    return {
        "text_profile": profile,
        "char_count": chars,
        "heading_count": headings,
        "numbered_step_count": numbered_steps,
        "timestamp_line_count": timestamp_lines,
        "speaker_line_count": speaker_lines,
        "table_row_count": table_rows,
    }


def _has_profile_term(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)
