"""
Load KBPrep cleaning dictionaries from the repository-level rules directory.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .cleaning_registry import (
    CleaningRuleRoute,
    select_accepted_rule_routes,
    select_base_cleaning_routes,
)
from .cleaning_registry import (
    profile_templates as registry_profile_templates,
)
from .private_rules import accepted_rule_dirs_from_env, project_root, template_candidates
from .rule_schema import (
    ClassificationPattern,
    CleaningRule,
    CleaningRuleSet,
    RuleProposal,
    validate_rule_file,
    validate_rule_proposal,
)


@dataclass(frozen=True)
class CleaningRuleGroup:
    promotional_line_rules: tuple[CleaningRule, ...]
    cta_keywords: tuple[str, ...]
    qr_image_markers: tuple[str, ...]


@dataclass(frozen=True)
class ImageRuleGroup:
    image_qr_indicators: tuple[str, ...]
    image_marketing_indicators: tuple[str, ...]
    image_operation_indicators: tuple[str, ...]
    image_proof_indicators: tuple[str, ...]
    image_educational_heading_indicators: tuple[str, ...]


@dataclass(frozen=True)
class ClassificationRuleGroup:
    tutorial_indicators: tuple[str, ...]
    knowledge_terms: tuple[str, ...]
    refund_patterns: tuple[str, ...]
    footer_patterns: tuple[str, ...]
    evidence_patterns: tuple[ClassificationPattern, ...]
    marketing_wrapper_heading_terms: tuple[str, ...]
    marketing_wrapper_passthrough_titles: tuple[str, ...]
    marketing_wrapper_back_matter_terms: tuple[str, ...]
    marketing_wrapper_line_patterns: tuple[str, ...]
    business_method_context_terms: tuple[str, ...]
    transcript_filler_patterns: tuple[str, ...]
    protected_patterns: tuple[ClassificationPattern, ...]


@dataclass(frozen=True)
class FeedbackRuleGroup:
    feedback_protect_intent_terms: tuple[str, ...]
    feedback_discard_intent_terms: tuple[str, ...]


@dataclass(frozen=True)
class LoadedCleaningRules:
    cleaning: CleaningRuleGroup
    image: ImageRuleGroup
    classification: ClassificationRuleGroup
    feedback: FeedbackRuleGroup
    sources: tuple[str, ...]

    @property
    def promotional_line_rules(self) -> tuple[CleaningRule, ...]:
        return self.cleaning.promotional_line_rules

    @property
    def cta_keywords(self) -> tuple[str, ...]:
        return self.cleaning.cta_keywords

    @property
    def qr_image_markers(self) -> tuple[str, ...]:
        return self.cleaning.qr_image_markers

    @property
    def image_qr_indicators(self) -> tuple[str, ...]:
        return self.image.image_qr_indicators

    @property
    def image_marketing_indicators(self) -> tuple[str, ...]:
        return self.image.image_marketing_indicators

    @property
    def image_operation_indicators(self) -> tuple[str, ...]:
        return self.image.image_operation_indicators

    @property
    def image_proof_indicators(self) -> tuple[str, ...]:
        return self.image.image_proof_indicators

    @property
    def image_educational_heading_indicators(self) -> tuple[str, ...]:
        return self.image.image_educational_heading_indicators

    @property
    def tutorial_indicators(self) -> tuple[str, ...]:
        return self.classification.tutorial_indicators

    @property
    def knowledge_terms(self) -> tuple[str, ...]:
        return self.classification.knowledge_terms

    @property
    def refund_patterns(self) -> tuple[str, ...]:
        return self.classification.refund_patterns

    @property
    def footer_patterns(self) -> tuple[str, ...]:
        return self.classification.footer_patterns

    @property
    def evidence_patterns(self) -> tuple[ClassificationPattern, ...]:
        return self.classification.evidence_patterns

    @property
    def marketing_wrapper_heading_terms(self) -> tuple[str, ...]:
        return self.classification.marketing_wrapper_heading_terms

    @property
    def marketing_wrapper_passthrough_titles(self) -> tuple[str, ...]:
        return self.classification.marketing_wrapper_passthrough_titles

    @property
    def marketing_wrapper_back_matter_terms(self) -> tuple[str, ...]:
        return self.classification.marketing_wrapper_back_matter_terms

    @property
    def marketing_wrapper_line_patterns(self) -> tuple[str, ...]:
        return self.classification.marketing_wrapper_line_patterns

    @property
    def business_method_context_terms(self) -> tuple[str, ...]:
        return self.classification.business_method_context_terms

    @property
    def transcript_filler_patterns(self) -> tuple[str, ...]:
        return self.classification.transcript_filler_patterns

    @property
    def protected_patterns(self) -> tuple[ClassificationPattern, ...]:
        return self.classification.protected_patterns

    @property
    def feedback_protect_intent_terms(self) -> tuple[str, ...]:
        return self.feedback.feedback_protect_intent_terms

    @property
    def feedback_discard_intent_terms(self) -> tuple[str, ...]:
        return self.feedback.feedback_discard_intent_terms


def rules_root() -> Path:
    override = os.environ.get("KBPREP_RULES_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return builtin_rules_root()


def builtin_rules_root() -> Path:
    return Path(__file__).resolve().parents[2] / "rules"


def profile_templates(profile: str = "standard") -> tuple[str, ...]:
    return registry_profile_templates(profile)


def load_cleaning_rules(
    profile: str = "standard",
    document_type: str = "",
    templates: tuple[str, ...] = (),
    source_identity: str = "",
) -> LoadedCleaningRules:
    base = _load_base_cleaning_rules(profile, document_type, templates)
    accepted_rules: list[CleaningRule] = []
    accepted_sources: list[str] = []
    for path in _accepted_rule_paths():
        if not path.exists():
            continue
        path_rules = _load_accepted_rule_proposals(path, document_type, source_identity)
        accepted_rules.extend(path_rules)
        if path_rules:
            accepted_sources.append(_source_name(path))
    if not accepted_rules:
        return base
    return _merge_accepted_rules(base, accepted_rules, accepted_sources)


@lru_cache(maxsize=64)
def _load_base_cleaning_rules(
    profile: str = "standard",
    document_type: str = "",
    templates: tuple[str, ...] = (),
) -> LoadedCleaningRules:
    selected = select_base_cleaning_routes(rules_root(), profile=profile, document_type=document_type, templates=templates)
    rule_sets = _load_rule_sets(selected)
    return LoadedCleaningRules(
        cleaning=_cleaning_rule_group(rule_sets),
        image=_image_rule_group(rule_sets),
        classification=_classification_rule_group(rule_sets),
        feedback=_feedback_rule_group(rule_sets),
        sources=tuple(rule_set.source for rule_set in rule_sets),
    )


def _load_rule_sets(selected: tuple[CleaningRuleRoute, ...]) -> list[CleaningRuleSet]:
    rule_sets: list[CleaningRuleSet] = []
    for route in selected:
        path = _resolve_rule_route_path(route)
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            rule_sets.append(validate_rule_file(json.load(fh), _source_name(path)))
    return rule_sets


def _resolve_rule_route_path(route: CleaningRuleRoute) -> Path:
    if route.path.parent.name == "templates" and route.path.suffix == ".json":
        for path in template_candidates(route.path.stem, rules_root() / "templates"):
            if path.exists():
                return path
    return route.path


def _cleaning_rule_group(rule_sets: list[CleaningRuleSet]) -> CleaningRuleGroup:
    return CleaningRuleGroup(
        promotional_line_rules=_promotional_rules(rule_sets),
        cta_keywords=_string_values(rule_sets, lambda rule_set: rule_set.cta_keywords),
        qr_image_markers=_string_values(rule_sets, lambda rule_set: rule_set.qr_image_markers),
    )


def _image_rule_group(rule_sets: list[CleaningRuleSet]) -> ImageRuleGroup:
    return ImageRuleGroup(
        image_qr_indicators=_string_values(rule_sets, lambda rule_set: rule_set.image_qr_indicators),
        image_marketing_indicators=_string_values(rule_sets, lambda rule_set: rule_set.image_marketing_indicators),
        image_operation_indicators=_string_values(rule_sets, lambda rule_set: rule_set.image_operation_indicators),
        image_proof_indicators=_string_values(rule_sets, lambda rule_set: rule_set.image_proof_indicators),
        image_educational_heading_indicators=_string_values(rule_sets, lambda rule_set: rule_set.image_educational_heading_indicators),
    )


def _classification_rule_group(rule_sets: list[CleaningRuleSet]) -> ClassificationRuleGroup:
    return ClassificationRuleGroup(
        tutorial_indicators=_string_values(rule_sets, lambda rule_set: rule_set.tutorial_indicators),
        knowledge_terms=_string_values(rule_sets, lambda rule_set: rule_set.knowledge_terms),
        refund_patterns=_string_values(rule_sets, lambda rule_set: rule_set.refund_patterns),
        footer_patterns=_string_values(rule_sets, lambda rule_set: rule_set.footer_patterns),
        evidence_patterns=_classification_patterns(rule_sets, lambda rule_set: rule_set.evidence_patterns),
        marketing_wrapper_heading_terms=_string_values(rule_sets, lambda rule_set: rule_set.marketing_wrapper_heading_terms),
        marketing_wrapper_passthrough_titles=_string_values(rule_sets, lambda rule_set: rule_set.marketing_wrapper_passthrough_titles),
        marketing_wrapper_back_matter_terms=_string_values(rule_sets, lambda rule_set: rule_set.marketing_wrapper_back_matter_terms),
        marketing_wrapper_line_patterns=_string_values(rule_sets, lambda rule_set: rule_set.marketing_wrapper_line_patterns),
        business_method_context_terms=_string_values(rule_sets, lambda rule_set: rule_set.business_method_context_terms),
        transcript_filler_patterns=_string_values(rule_sets, lambda rule_set: rule_set.transcript_filler_patterns),
        protected_patterns=_classification_patterns(rule_sets, lambda rule_set: rule_set.protected_patterns),
    )


def _feedback_rule_group(rule_sets: list[CleaningRuleSet]) -> FeedbackRuleGroup:
    return FeedbackRuleGroup(
        feedback_protect_intent_terms=_string_values(rule_sets, lambda rule_set: rule_set.feedback_protect_intent_terms),
        feedback_discard_intent_terms=_string_values(rule_sets, lambda rule_set: rule_set.feedback_discard_intent_terms),
    )


def _promotional_rules(rule_sets: list[CleaningRuleSet]) -> tuple[CleaningRule, ...]:
    rules: list[CleaningRule] = []
    for rule_set in rule_sets:
        rules.extend(rule_set.promotional_line_rules)
    return tuple(rules)


def _string_values(rule_sets: list[CleaningRuleSet], getter: Callable[[CleaningRuleSet], tuple[str, ...]]) -> tuple[str, ...]:
    values: list[str] = []
    for rule_set in rule_sets:
        values.extend(getter(rule_set))
    return tuple(_dedupe(values))


def _classification_patterns(
    rule_sets: list[CleaningRuleSet],
    getter: Callable[[CleaningRuleSet], tuple[ClassificationPattern, ...]],
) -> tuple[ClassificationPattern, ...]:
    values: list[ClassificationPattern] = []
    for rule_set in rule_sets:
        values.extend(getter(rule_set))
    return tuple(_dedupe_classification_patterns(values))


def _merge_accepted_rules(base: LoadedCleaningRules, accepted_rules: list[CleaningRule], sources: list[str]) -> LoadedCleaningRules:
    return LoadedCleaningRules(
        cleaning=CleaningRuleGroup(
            promotional_line_rules=(*base.promotional_line_rules, *accepted_rules),
            cta_keywords=base.cta_keywords,
            qr_image_markers=base.qr_image_markers,
        ),
        image=base.image,
        classification=base.classification,
        feedback=base.feedback,
        sources=(*base.sources, *sources),
    )


def _clear_cleaning_rule_caches() -> None:
    _load_base_cleaning_rules.cache_clear()
    _load_accepted_rule_entries.cache_clear()


load_cleaning_rules.cache_info = _load_base_cleaning_rules.cache_info  # type: ignore[attr-defined]
load_cleaning_rules.cache_clear = _clear_cleaning_rule_caches  # type: ignore[attr-defined]


def rule_matches(rule: CleaningRule, text: str) -> bool:
    if rule.match == "literal":
        return rule.pattern.lower() in text.lower()
    return re.search(rule.pattern, text, re.IGNORECASE) is not None


def _accepted_rule_paths() -> list[Path]:
    return [route.path for route in select_accepted_rule_routes(rules_root(), cwd=Path.cwd(), user_rule_dirs=_user_rule_dirs_from_env())]


def load_active_accepted_rules(path: Path, document_type: str, source_identity: str) -> tuple[CleaningRule, ...]:
    if not path.exists():
        return ()
    return tuple(_load_accepted_rule_proposals(path, document_type, source_identity))


def _user_rule_dirs_from_env() -> tuple[Path, ...]:
    return accepted_rule_dirs_from_env()


def _load_accepted_rule_proposals(path: Path, document_type: str, source_identity: str) -> list[CleaningRule]:
    result: list[CleaningRule] = []
    entries = _load_accepted_rule_entries(str(path.resolve()), *_accepted_rule_signature(path))
    for raw, proposal in entries:
        if raw.get("status") != "accepted":
            continue
        proposal_document_type = raw.get("document_type")
        if raw.get("scope") == "document_type" and proposal_document_type and proposal_document_type != document_type:
            continue
        if raw.get("scope") == "source_pattern":
            if not _source_pattern_matches(raw, source_identity):
                continue
        result.append(CleaningRule(
            rule_id=str(raw.get("accepted_rule_id") or proposal.proposal_id),
            action=proposal.action,
            match=proposal.match,
            pattern=proposal.pattern,
            reason=proposal.reason,
            risk_tag=f"user_feedback_{proposal.action}",
            source=_source_name(path),
        ))
    return result


def _accepted_rule_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=32)
def _load_accepted_rule_entries(path_text: str, mtime_ns: int, size: int) -> tuple[tuple[dict, RuleProposal], ...]:
    del mtime_ns, size
    path = Path(path_text)
    result: list[tuple[dict, RuleProposal]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc.msg}") from exc
            proposal = validate_rule_proposal(raw, f"{path}:{line_no}")
            result.append((raw, proposal))
    return tuple(result)


def _source_pattern_matches(raw: dict, source_identity: str) -> bool:
    pattern = str(raw.get("source_pattern") or "").strip()
    if not pattern:
        return False
    candidates = _source_identity_candidates(source_identity)
    if not candidates:
        return False
    pattern_norm = pattern.replace("\\", "/").lower()
    field, _, field_pattern = pattern_norm.partition(":")
    if field_pattern and field in SOURCE_PATTERN_FIELDS:
        return any(
            candidate_key == field and _keyed_source_pattern_matches(field, field_pattern, candidate_value)
            for candidate_key, candidate_value in candidates
        )
    return any(_plain_source_pattern_matches(pattern_norm, candidate_key, candidate_value) for candidate_key, candidate_value in candidates)


def _keyed_source_pattern_matches(field: str, pattern: str, value: str) -> bool:
    if field == "source_domain":
        return value == pattern or value.endswith(f".{pattern}")
    if field == "source_url":
        return _url_prefix_boundary_matches(pattern, value)
    if field in {"input_path", "source_path", "source_name"}:
        return _path_or_name_prefix_matches(pattern, value)
    return _text_prefix_boundary_matches(pattern, value)


def _plain_source_pattern_matches(pattern: str, field: str, value: str) -> bool:
    if field == "source_domain":
        return value == pattern or value.endswith(f".{pattern}")
    if field == "source_url":
        return False
    if field in {"input_path", "source_path", "source_name", "source_identity"}:
        return _path_or_name_prefix_matches(pattern, value)
    if field == "site_name":
        return _text_prefix_boundary_matches(pattern, value)
    return _text_prefix_boundary_matches(pattern, value)


def _url_prefix_boundary_matches(pattern: str, value: str) -> bool:
    if value == pattern:
        return True
    if not value.startswith(pattern):
        return False
    remainder = value[len(pattern):]
    return not remainder or remainder[0] in {"/", "?", "#", "&"}


def _path_or_name_prefix_matches(pattern: str, value: str) -> bool:
    parts = [part for part in re.split(r"[\\/]+", value) if part]
    return any(_text_prefix_boundary_matches(pattern, part) for part in parts)


def _text_prefix_boundary_matches(pattern: str, value: str) -> bool:
    if value == pattern:
        return True
    if not value.startswith(pattern):
        return False
    remainder = value[len(pattern):]
    return bool(remainder) and remainder[0] in {"-", "_", ".", " ", "~", "(", "[", "{"}


def _source_identity_candidates(source_identity: str) -> list[tuple[str, str]]:
    raw = str(source_identity or "").strip()
    if not raw:
        return []
    result: list[tuple[str, str]] = []
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        _collect_source_identity(parsed, result)
    else:
        result.append(("source_identity", raw))
    return _dedupe_identity_candidates(result)


SOURCE_PATTERN_FIELDS = {
    "input_path",
    "source_path",
    "source_name",
    "source_url",
    "source_domain",
    "site_name",
}


def _collect_source_identity(value: dict, result: list[tuple[str, str]]) -> None:
    for key, raw_value in value.items():
        normalized_key = str(key).strip().lower()
        if normalized_key not in SOURCE_PATTERN_FIELDS:
            continue
        if isinstance(raw_value, list):
            for item in raw_value:
                if isinstance(item, (str, int, float)):
                    result.append((normalized_key, str(item)))
            continue
        if isinstance(raw_value, (str, int, float)):
            result.append((normalized_key, str(raw_value)))


def _dedupe_identity_candidates(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen = set()
    result = []
    for key, value in values:
        normalized = value.replace("\\", "/").lower().strip()
        if not normalized:
            continue
        item = (key.lower(), normalized)
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _source_name(path: Path) -> str:
    resolved = path.resolve()
    for root in (project_root().resolve(), Path.cwd().resolve(), rules_root().parent):
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    return str(path)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


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


def _dedupe_classification_patterns(values: list[ClassificationPattern]) -> list[ClassificationPattern]:
    seen = set()
    result = []
    for value in values:
        key = (value.label.lower(), value.pattern.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
