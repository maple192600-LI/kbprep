"""Title candidate filters used while deriving display names from converted text."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class TitleFilters:
    source: str
    split_patterns: tuple[str, ...]
    reject_patterns: tuple[str, ...]
    reject_exact: tuple[str, ...]
    structural_reject_patterns: tuple[str, ...]
    keyword_score_patterns: tuple[str, ...]


def rules_root() -> Path:
    return Path(__file__).resolve().parents[2] / "rules"


@lru_cache(maxsize=1)
def load_title_filters() -> TitleFilters:
    path = rules_root() / "base" / "title_filters.json"
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema") != "kbprep.title_filters.v1":
        raise ValueError(f"{path}: schema must be kbprep.title_filters.v1")
    return TitleFilters(
        source=str(path.relative_to(rules_root().parent)),
        split_patterns=tuple(_string_list(data, "split_patterns", path)),
        reject_patterns=tuple(_string_list(data, "reject_patterns", path)),
        reject_exact=tuple(_string_list(data, "reject_exact", path)),
        structural_reject_patterns=tuple(_string_list(data, "structural_reject_patterns", path)),
        keyword_score_patterns=tuple(_string_list(data, "keyword_score_patterns", path)),
    )


def _string_list(data: dict, key: str, path: Path) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{path}: {key} must be a list")
    result: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{path}: {key}[{idx}] must be a non-empty string")
        result.append(item)
    return result
