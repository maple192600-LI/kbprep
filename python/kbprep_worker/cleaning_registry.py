"""Declared cleaning rule route selection for KBPrep.

The registry only selects rule packages. The rule loader still parses,
validates, and merges the actual dictionaries before quality gates run.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .private_rules import project_private_rules_root


class CleaningRuleRouteKind(str, Enum):
    BASE = "base"
    DOCUMENT_TYPE = "document_type"
    PROFILE_TEMPLATE = "profile_template"
    REQUESTED_TEMPLATE = "requested_template"
    ACCEPTED_USER = "accepted_user"


@dataclass(frozen=True)
class CleaningRuleRoute:
    kind: CleaningRuleRouteKind
    path: Path
    source: str
    reason: str
    priority: int
    cache_strategy: str
    runtime_filter: str = ""


def profile_templates(profile: str = "standard") -> tuple[str, ...]:
    if profile == "curated_obsidian_kb":
        return ("self_media_course",)
    return ()


def select_base_cleaning_routes(
    root: Path,
    profile: str = "standard",
    document_type: str = "",
    templates: tuple[str, ...] = (),
) -> tuple[CleaningRuleRoute, ...]:
    routes = [_base_cleaning_route(root)]
    if document_type:
        routes.append(_document_type_cleaning_route(root, document_type))

    seen_templates: set[str] = set()
    for template in profile_templates(profile):
        seen_templates.add(template)
        routes.append(_profile_template_route(root, profile, template))
    for template in templates:
        if template in seen_templates:
            continue
        seen_templates.add(template)
        routes.append(_requested_template_route(root, template))
    return tuple(routes)


def select_accepted_rule_routes(
    root: Path,
    cwd: Path | None = None,
    user_rule_dirs: tuple[Path, ...] = (),
) -> tuple[CleaningRuleRoute, ...]:
    cwd = cwd or Path.cwd()
    paths = [
        *(path / "accepted_rules.jsonl" for path in user_rule_dirs),
        project_private_rules_root(cwd) / "user" / "accepted_rules.jsonl",
    ]
    return tuple(
        _route(
            CleaningRuleRouteKind.ACCEPTED_USER,
            root,
            path,
            "accepted user feedback rules filtered at runtime",
            priority=100 + index,
            cache_strategy="accepted_rules_file_stat",
            runtime_filter="document_type_and_source_pattern",
        )
        for index, path in enumerate(_dedupe_paths(paths))
    )


def _base_cleaning_route(root: Path) -> CleaningRuleRoute:
    return _route(
        CleaningRuleRouteKind.BASE,
        root,
        root / "base" / "obvious_noise.json",
        "default generic cleanup signals",
        priority=10,
        cache_strategy="base_rules",
    )


def _document_type_cleaning_route(root: Path, document_type: str) -> CleaningRuleRoute:
    return _route(
        CleaningRuleRouteKind.DOCUMENT_TYPE,
        root,
        root / "document_types" / f"{document_type}.json",
        f"document type matched: {document_type}",
        priority=20,
        cache_strategy="base_rules",
    )


def _profile_template_route(root: Path, profile: str, template: str) -> CleaningRuleRoute:
    return _route(
        CleaningRuleRouteKind.PROFILE_TEMPLATE,
        root,
        root / "templates" / f"{template}.json",
        f"profile matched: {profile}",
        priority=30,
        cache_strategy="base_rules",
    )


def _requested_template_route(root: Path, template: str) -> CleaningRuleRoute:
    return _route(
        CleaningRuleRouteKind.REQUESTED_TEMPLATE,
        root,
        root / "templates" / f"{template}.json",
        f"explicit template requested: {template}",
        priority=40,
        cache_strategy="base_rules",
    )


def _route(
    kind: CleaningRuleRouteKind,
    root: Path,
    path: Path,
    reason: str,
    priority: int,
    cache_strategy: str,
    runtime_filter: str = "",
) -> CleaningRuleRoute:
    return CleaningRuleRoute(
        kind=kind,
        path=path,
        source=_source_name(root, path),
        reason=reason,
        priority=priority,
        cache_strategy=cache_strategy,
        runtime_filter=runtime_filter,
    )


def _source_name(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root.parent).as_posix()
    except ValueError:
        return path.as_posix()


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    result = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result
