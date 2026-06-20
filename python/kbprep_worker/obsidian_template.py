"""Load optional Obsidian curation templates."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .private_rules import project_private_rules_root, project_root, template_candidates


@dataclass(frozen=True)
class ObsidianTemplate:
    source: str
    categories: tuple[str, ...]
    default_category: str
    method_category: str
    cognition_category: str
    case_category: str
    social_profile_labels: tuple[str, ...]
    social_profile_platforms: tuple[str, ...]
    provenance_terms: tuple[str, ...]
    author_bio_terms: tuple[str, ...]
    bio_role_terms: tuple[str, ...]
    author_credential_terms: tuple[str, ...]
    knowledge_terms: tuple[str, ...]
    case_terms: tuple[str, ...]
    method_terms: tuple[str, ...]
    cognition_terms: tuple[str, ...]
    packaging_heading_terms: tuple[str, ...]
    packaging_heading_regexes: tuple[str, ...]
    brand_heading_replacements: tuple[tuple[str, str], ...]
    layout_table_terms: tuple[str, ...]
    brand_program_packaging_terms: tuple[str, ...]
    translator_back_matter_terms: tuple[str, ...]


def templates_root() -> Path:
    return Path(__file__).resolve().parents[2] / "rules" / "templates"


@lru_cache(maxsize=16)
def load_obsidian_template(name: str = "obsidian_generic") -> ObsidianTemplate:
    path = _resolve_template_path(name)
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema") != "kbprep.obsidian_template.v1":
        raise ValueError(f"{path}: schema must be kbprep.obsidian_template.v1")

    categories = tuple(_string_list(data, "categories", path))
    default_category = _required_string(data, "default_category", path)
    if default_category not in categories:
        raise ValueError(f"{path}: default_category must be one of categories")

    return ObsidianTemplate(
        source=_source_name(path),
        categories=categories,
        default_category=default_category,
        method_category=_category_role(data, "method_category", default_category, categories, path),
        cognition_category=_category_role(data, "cognition_category", default_category, categories, path),
        case_category=_category_role(data, "case_category", default_category, categories, path),
        social_profile_labels=tuple(_string_list(data, "social_profile_labels", path)),
        social_profile_platforms=tuple(_string_list(data, "social_profile_platforms", path)),
        provenance_terms=tuple(_string_list(data, "provenance_terms", path)),
        author_bio_terms=tuple(_string_list(data, "author_bio_terms", path)),
        bio_role_terms=tuple(_string_list(data, "bio_role_terms", path)),
        author_credential_terms=tuple(_string_list(data, "author_credential_terms", path)),
        knowledge_terms=tuple(_string_list(data, "knowledge_terms", path)),
        case_terms=tuple(_string_list(data, "case_terms", path)),
        method_terms=tuple(_string_list(data, "method_terms", path)),
        cognition_terms=tuple(_string_list(data, "cognition_terms", path)),
        packaging_heading_terms=tuple(_string_list(data, "packaging_heading_terms", path)),
        packaging_heading_regexes=tuple(_string_list(data, "packaging_heading_regexes", path)),
        brand_heading_replacements=tuple(_replacement_pairs(data, "brand_heading_replacements", path)),
        layout_table_terms=tuple(_string_list(data, "layout_table_terms", path)),
        brand_program_packaging_terms=tuple(_string_list(data, "brand_program_packaging_terms", path)),
        translator_back_matter_terms=tuple(_string_list(data, "translator_back_matter_terms", path)),
    )


def _resolve_template_path(name: str) -> Path:
    for path in template_candidates(name, templates_root()):
        if path.exists():
            return path
    local_path = project_private_rules_root() / "templates" / f"{name}.json"
    if name == "obsidian_course_kb":
        raise FileNotFoundError(
            "curated_obsidian_kb needs a private local template at "
            f".kbprep/rules/templates/{name}.json ({local_path}). "
            "Use profile 'obsidian_kb' for the generic public template, "
            "or place obsidian_course_kb.json under .kbprep/rules/templates/."
        )
    raise FileNotFoundError(f"Obsidian template not found: {name}")


def _source_name(path: Path) -> str:
    repo_root = templates_root().parents[1]
    cwd = Path.cwd().resolve()
    resolved = path.resolve()
    for root in (project_root().resolve(), cwd, repo_root):
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    return resolved.as_posix()


def _required_string(data: dict, key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: {key} must be a non-empty string")
    return value


def _category_role(data: dict, key: str, default_category: str, categories: tuple[str, ...], path: Path) -> str:
    value = data.get(key, default_category)
    if not isinstance(value, str) or value not in categories:
        raise ValueError(f"{path}: {key} must be one of categories")
    return value


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


def _replacement_pairs(data: dict, key: str, path: Path) -> list[tuple[str, str]]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{path}: {key} must be a list")
    result: list[tuple[str, str]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, list) or len(item) != 2 or not all(isinstance(part, str) for part in item):
            raise ValueError(f"{path}: {key}[{idx}] must be a two-string list")
        result.append((item[0], item[1]))
    return result
