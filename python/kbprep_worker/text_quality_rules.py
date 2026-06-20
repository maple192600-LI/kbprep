"""Rule-backed text quality signals."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .rule_loader import builtin_rules_root, rules_root


@dataclass(frozen=True)
class TextQualitySignals:
    abnormal_unicode_sequence_re: re.Pattern[str]
    mojibake_sequence_re: re.Pattern[str]
    mojibake_char_re: re.Pattern[str]
    mojibake_token_re: re.Pattern[str]
    ocr_ai_confusion_re: re.Pattern[str]


@lru_cache(maxsize=1)
def load_text_quality_signals() -> TextQualitySignals:
    path = _base_rule_path("text_quality_signals.json")
    payload = _load_json_object(path)
    if payload.get("schema") != "kbprep.text_quality_signals.v1":
        raise ValueError(f"Invalid text quality signal schema in {path}")
    return TextQualitySignals(
        abnormal_unicode_sequence_re=_compile_required_pattern(payload, "abnormal_unicode_sequence_pattern", path),
        mojibake_sequence_re=_compile_required_pattern(payload, "mojibake_sequence_pattern", path),
        mojibake_char_re=_compile_required_pattern(payload, "mojibake_character_pattern", path),
        mojibake_token_re=_compile_literal_tokens(_string_list(payload, "mojibake_tokens", path), path),
        ocr_ai_confusion_re=_compile_pattern_list(payload, "ocr_ai_confusion_patterns", path),
    )


def _load_json_object(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: rule payload must be an object")
    return payload


def _base_rule_path(filename: str) -> Path:
    override_path = rules_root() / "base" / filename
    if override_path.exists():
        return override_path
    return builtin_rules_root() / "base" / filename


def _compile_required_pattern(payload: dict, key: str, path: Path) -> re.Pattern[str]:
    pattern = payload.get(key)
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError(f"{path}: {key} must be a non-empty regex string")
    return _compile_regex(pattern, path, key)


def _compile_pattern_list(payload: dict, key: str, path: Path) -> re.Pattern[str]:
    patterns = _string_list(payload, key, path)
    joined = "|".join(f"(?:{pattern})" for pattern in patterns)
    return _compile_regex(joined or r"(?!)", path, key, re.IGNORECASE)


def _compile_literal_tokens(tokens: tuple[str, ...], path: Path) -> re.Pattern[str]:
    pattern = "|".join(re.escape(token) for token in tokens)
    return _compile_regex(pattern or r"(?!)", path, "mojibake_tokens")


def _compile_regex(pattern: str, path: Path, key: str, flags: int = 0) -> re.Pattern[str]:
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise ValueError(f"{path}: {key} contains invalid regex: {exc}") from exc


def _string_list(payload: dict, key: str, path: Path) -> tuple[str, ...]:
    values = payload.get(key)
    if not isinstance(values, list):
        raise ValueError(f"{path}: {key} must be a list")
    strings = tuple(value for value in values if isinstance(value, str) and value.strip())
    if len(strings) != len(values) or not strings:
        raise ValueError(f"{path}: {key} must contain non-empty strings")
    return strings
