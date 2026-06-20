"""Load document type classification signals from JSON dictionaries."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from .rule_loader import builtin_rules_root, rules_root

ALLOWED_SCHEMA = "kbprep.document_type_signals.v1"


@dataclass(frozen=True)
class DocumentTypeHint:
    key: str
    value: str
    document_type: str
    score: int
    reason: str


@dataclass(frozen=True)
class DocumentTypePattern:
    document_type: str
    score: int
    pattern: str
    flags: int
    reason: str


@dataclass(frozen=True)
class DocumentTypeSignals:
    supported_document_types: tuple[str, ...]
    source_type_hints: tuple[DocumentTypeHint, ...]
    format_hints: tuple[DocumentTypeHint, ...]
    content_patterns: tuple[DocumentTypePattern, ...]
    source: str


@lru_cache(maxsize=16)
def load_document_type_signals() -> DocumentTypeSignals:
    path = rules_root() / "base" / "document_type_signals.json"
    if not path.exists():
        path = builtin_rules_root() / "base" / "document_type_signals.json"
    try:
        source = str(path.relative_to(path.parents[1]))
    except ValueError:
        source = str(path)
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return _validate_document_type_signals(data, source)


def _validate_document_type_signals(data: object, source: str) -> DocumentTypeSignals:
    if not isinstance(data, dict):
        raise ValueError(f"{source}: document type signals must be a JSON object")
    if data.get("schema") != ALLOWED_SCHEMA:
        raise ValueError(f"{source}: schema must be {ALLOWED_SCHEMA}")

    supported = _string_list(data, "supported_document_types", source)
    known_types = set(supported)
    source_type_hints = tuple(
        _hint(item, "source_type", known_types, source, idx)
        for idx, item in enumerate(_object_list(data, "source_type_hints", source))
    )
    format_hints = tuple(
        _hint(item, "detected_format", known_types, source, idx)
        for idx, item in enumerate(_object_list(data, "format_hints", source))
    )
    content_patterns = tuple(
        _content_pattern(item, known_types, source, idx)
        for idx, item in enumerate(_object_list(data, "content_patterns", source))
    )
    return DocumentTypeSignals(
        supported_document_types=tuple(supported),
        source_type_hints=source_type_hints,
        format_hints=format_hints,
        content_patterns=content_patterns,
        source=source,
    )


def _hint(item: dict, key: str, known_types: set[str], source: str, idx: int) -> DocumentTypeHint:
    document_type = _required_string(item, "document_type", source, idx)
    if document_type not in known_types:
        raise ValueError(f"{source}: {key}_hints[{idx}].document_type is not supported")
    return DocumentTypeHint(
        key=key,
        value=_required_string(item, key, source, idx).lower(),
        document_type=document_type,
        score=_required_int(item, "score", source, idx),
        reason=_required_string(item, "reason", source, idx),
    )


def _content_pattern(item: dict, known_types: set[str], source: str, idx: int) -> DocumentTypePattern:
    document_type = _required_string(item, "document_type", source, idx)
    if document_type not in known_types:
        raise ValueError(f"{source}: content_patterns[{idx}].document_type is not supported")
    flags = 0
    raw_flags = item.get("flags", [])
    if not isinstance(raw_flags, list):
        raise ValueError(f"{source}: content_patterns[{idx}].flags must be a list")
    for flag in raw_flags:
        if flag == "ignore_case":
            flags |= re.IGNORECASE
        elif flag == "multiline":
            flags |= re.MULTILINE
        else:
            raise ValueError(f"{source}: content_patterns[{idx}].flags contains unsupported flag {flag!r}")
    pattern = _required_string(item, "pattern", source, idx)
    re.compile(pattern, flags)
    return DocumentTypePattern(
        document_type=document_type,
        score=_required_int(item, "score", source, idx),
        pattern=pattern,
        flags=flags,
        reason=_required_string(item, "reason", source, idx),
    )


def _object_list(data: dict, key: str, source: str) -> list[dict]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{source}: {key} must be a list")
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{source}: {key}[{idx}] must be an object")
    return value


def _string_list(data: dict, key: str, source: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{source}: {key} must be a non-empty list")
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{source}: {key}[{idx}] must be a non-empty string")
    return value


def _required_string(item: dict, key: str, source: str, idx: int) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: item[{idx}].{key} must be a non-empty string")
    return value


def _required_int(item: dict, key: str, source: str, idx: int) -> int:
    value = item.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{source}: item[{idx}].{key} must be an integer")
    return value
