"""Rule-backed detail retention signals."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

from .rule_loader import builtin_rules_root, rules_root


@dataclass(frozen=True)
class DetailSignals:
    patterns: Mapping[str, re.Pattern[str]]
    block_type_categories: Mapping[str, str]
    strict_categories: frozenset[str]
    categories: tuple[str, ...]


@lru_cache(maxsize=1)
def load_detail_signals() -> DetailSignals:
    path = _base_rule_path("detail_signals.json")
    payload = _load_json_object(path)
    if payload.get("schema") != "kbprep.detail_signals.v1":
        raise ValueError(f"Invalid detail signal schema in {path}")
    patterns = _compile_patterns(payload, path)
    categories = ("operation_step", *patterns.keys())
    block_type_categories = _string_mapping(payload, "block_type_categories", path)
    strict_categories = frozenset(_string_list(payload, "strict_categories", path))
    _validate_category_references(path, categories, block_type_categories, strict_categories)
    return DetailSignals(
        patterns=MappingProxyType(patterns),
        block_type_categories=MappingProxyType(dict(block_type_categories)),
        strict_categories=strict_categories,
        categories=categories,
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


def _compile_patterns(payload: dict, path: Path) -> dict[str, re.Pattern[str]]:
    patterns = payload.get("patterns")
    if not isinstance(patterns, dict) or not patterns:
        raise ValueError(f"{path}: patterns must be a non-empty object")
    compiled: dict[str, re.Pattern[str]] = {}
    for name, pattern in patterns.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path}: pattern names must be non-empty strings")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError(f"{path}: patterns.{name} must be a non-empty regex string")
        compiled[name] = _compile_regex(pattern, path, f"patterns.{name}")
    return compiled


def _compile_regex(pattern: str, path: Path, key: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    except re.error as exc:
        raise ValueError(f"{path}: {key} contains invalid regex: {exc}") from exc


def _string_mapping(payload: dict, key: str, path: Path) -> dict[str, str]:
    values = payload.get(key)
    if not isinstance(values, dict) or not values:
        raise ValueError(f"{path}: {key} must be a non-empty object")
    mapping = {str(name): str(category) for name, category in values.items() if str(name).strip() and str(category).strip()}
    if len(mapping) != len(values):
        raise ValueError(f"{path}: {key} must map non-empty strings to non-empty strings")
    return mapping


def _string_list(payload: dict, key: str, path: Path) -> tuple[str, ...]:
    values = payload.get(key)
    if not isinstance(values, list):
        raise ValueError(f"{path}: {key} must be a list")
    strings = tuple(value for value in values if isinstance(value, str) and value.strip())
    if len(strings) != len(values) or not strings:
        raise ValueError(f"{path}: {key} must contain non-empty strings")
    return strings


def _validate_category_references(
    path: Path,
    categories: tuple[str, ...],
    block_type_categories: dict[str, str],
    strict_categories: frozenset[str],
) -> None:
    category_set = set(categories)
    unknown = set(block_type_categories.values()) | set(strict_categories)
    unknown -= category_set
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise ValueError(f"{path}: unknown detail categories referenced: {joined}")
