"""
Schema validation for KBPrep cleaning dictionaries.

Rule files are JSON on purpose: the worker currently has no YAML dependency,
and cleanup rules must be readable without expanding the runtime surface.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ALLOWED_SCHEMA = "kbprep.cleaning_rules.v1"
ALLOWED_RULE_PROPOSAL_SCHEMA = "kbprep.rule_proposal.v1"
ALLOWED_RULE_ACTIONS = {"discard", "review", "protect"}
ALLOWED_MATCH_TYPES = {"regex", "literal"}
ALLOWED_RULE_SCOPES = {"global", "user", "project", "document_type", "source_pattern"}
ALLOWED_OWNER_CONFIRMATION_STATUSES = {"pending", "confirmed", "rejected"}
ALLOWED_RULE_PROPOSAL_STATUSES = {"proposed", "accepted", "rejected"}
ALLOWED_RULE_LIFECYCLE_STATUSES = {
    "proposed",
    "accepted",
    "rejected",
    "rerun_pending",
    "rerun_passed",
    "rerun_failed",
    "promotion_blocked",
}


@dataclass(frozen=True)
class CleaningRule:
    rule_id: str
    action: str
    match: str
    pattern: str
    reason: str
    risk_tag: str
    source: str


@dataclass(frozen=True)
class ClassificationPattern:
    label: str
    pattern: str


@dataclass(frozen=True)
class CleaningRuleSet:
    source: str
    promotional_line_rules: tuple[CleaningRule, ...]
    cta_keywords: tuple[str, ...]
    qr_image_markers: tuple[str, ...]
    image_qr_indicators: tuple[str, ...]
    image_marketing_indicators: tuple[str, ...]
    image_operation_indicators: tuple[str, ...]
    image_proof_indicators: tuple[str, ...]
    image_educational_heading_indicators: tuple[str, ...]
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
    feedback_protect_intent_terms: tuple[str, ...]
    feedback_discard_intent_terms: tuple[str, ...]


@dataclass(frozen=True)
class RuleProposal:
    proposal_id: str
    action: str
    scope: str
    match: str
    pattern: str
    reason: str
    risk_note: str
    created_from_run: str
    requires_confirmation: bool
    owner_confirmation_status: str
    lifecycle_status: str | None = None


def validate_rule_file(data: object, source: str) -> CleaningRuleSet:
    if not isinstance(data, dict):
        raise ValueError(f"{source}: rule file must be a JSON object")
    if data.get("schema") != ALLOWED_SCHEMA:
        raise ValueError(f"{source}: schema must be {ALLOWED_SCHEMA}")

    keyword_sets = data.get("keyword_sets", {})
    if not isinstance(keyword_sets, dict):
        raise ValueError(f"{source}: keyword_sets must be an object")

    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError(f"{source}: rules must be a list")
    return _cleaning_rule_set(source, keyword_sets, _promotional_line_rules(raw_rules, source))


def _promotional_line_rules(raw_rules: list[object], source: str) -> list[CleaningRule]:
    promotional_line_rules: list[CleaningRule] = []
    for idx, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"{source}: rules[{idx}] must be an object")
        if raw_rule.get("type") != "promotional_line":
            continue
        rule_id = _required_string(raw_rule, "id", source, idx)
        action = _required_string(raw_rule, "action", source, idx)
        match = _required_string(raw_rule, "match", source, idx)
        pattern = _required_string(raw_rule, "pattern", source, idx)
        reason = _required_string(raw_rule, "reason", source, idx)
        risk_tag = _required_string(raw_rule, "risk_tag", source, idx)
        if action not in ALLOWED_RULE_ACTIONS:
            raise ValueError(f"{source}: rules[{idx}].action must be one of {sorted(ALLOWED_RULE_ACTIONS)}")
        if match not in ALLOWED_MATCH_TYPES:
            raise ValueError(f"{source}: rules[{idx}].match must be one of {sorted(ALLOWED_MATCH_TYPES)}")
        _validate_regex_pattern(match, pattern, f"{source}: rules[{idx}].pattern")
        promotional_line_rules.append(CleaningRule(
            rule_id=rule_id,
            action=action,
            match=match,
            pattern=pattern,
            reason=reason,
            risk_tag=risk_tag,
            source=source,
        ))
    return promotional_line_rules


def _cleaning_rule_set(source: str, keyword_sets: dict, promotional_line_rules: list[CleaningRule]) -> CleaningRuleSet:
    return CleaningRuleSet(
        source=source,
        promotional_line_rules=tuple(promotional_line_rules),
        cta_keywords=tuple(_string_list(keyword_sets, "cta_keywords", source)),
        qr_image_markers=tuple(_string_list(keyword_sets, "qr_image_markers", source)),
        image_qr_indicators=tuple(_string_list(keyword_sets, "image_qr_indicators", source)),
        image_marketing_indicators=tuple(_string_list(keyword_sets, "image_marketing_indicators", source)),
        image_operation_indicators=tuple(_string_list(keyword_sets, "image_operation_indicators", source)),
        image_proof_indicators=tuple(_string_list(keyword_sets, "image_proof_indicators", source)),
        image_educational_heading_indicators=tuple(_string_list(keyword_sets, "image_educational_heading_indicators", source)),
        tutorial_indicators=tuple(_string_list(keyword_sets, "tutorial_indicators", source)),
        knowledge_terms=tuple(_string_list(keyword_sets, "knowledge_terms", source)),
        refund_patterns=tuple(_string_list(keyword_sets, "refund_patterns", source)),
        footer_patterns=tuple(_string_list(keyword_sets, "footer_patterns", source)),
        evidence_patterns=tuple(_classification_pattern_list(keyword_sets, "evidence_patterns", source)),
        marketing_wrapper_heading_terms=tuple(_string_list(keyword_sets, "marketing_wrapper_heading_terms", source)),
        marketing_wrapper_passthrough_titles=tuple(_string_list(keyword_sets, "marketing_wrapper_passthrough_titles", source)),
        marketing_wrapper_back_matter_terms=tuple(_string_list(keyword_sets, "marketing_wrapper_back_matter_terms", source)),
        marketing_wrapper_line_patterns=tuple(_string_list(keyword_sets, "marketing_wrapper_line_patterns", source)),
        business_method_context_terms=tuple(_string_list(keyword_sets, "business_method_context_terms", source)),
        transcript_filler_patterns=tuple(_string_list(keyword_sets, "transcript_filler_patterns", source)),
        protected_patterns=tuple(_classification_pattern_list(keyword_sets, "protected_patterns", source)),
        feedback_protect_intent_terms=tuple(_string_list(keyword_sets, "feedback_protect_intent_terms", source)),
        feedback_discard_intent_terms=tuple(_string_list(keyword_sets, "feedback_discard_intent_terms", source)),
    )


def validate_rule_proposal(data: object, source: str) -> RuleProposal:
    if not isinstance(data, dict):
        raise ValueError(f"{source}: rule proposal must be a JSON object")
    if data.get("schema") != ALLOWED_RULE_PROPOSAL_SCHEMA:
        raise ValueError(f"{source}: schema must be {ALLOWED_RULE_PROPOSAL_SCHEMA}")

    fields = _proposal_string_fields(data, source)
    requires_confirmation = data.get("requires_confirmation")
    lifecycle_status = _optional_lifecycle_status(data, source)
    _validate_rule_proposal_contract(data, source, fields, requires_confirmation)

    return RuleProposal(
        proposal_id=fields["proposal_id"],
        action=fields["action"],
        scope=fields["scope"],
        match=fields["match"],
        pattern=fields["pattern"],
        reason=fields["reason"],
        risk_note=fields["risk_note"],
        created_from_run=fields["created_from_run"],
        requires_confirmation=True,
        owner_confirmation_status=fields["owner_confirmation_status"],
        lifecycle_status=lifecycle_status,
    )


def _proposal_string_fields(data: dict, source: str) -> dict[str, str]:
    return {
        "proposal_id": _required_top_string(data, "id", source),
        "action": _required_top_string(data, "action", source),
        "scope": _required_top_string(data, "scope", source),
        "match": _required_top_string(data, "match", source),
        "pattern": _required_top_string(data, "pattern", source),
        "reason": _required_top_string(data, "reason", source),
        "risk_note": _required_top_string(data, "risk_note", source),
        "created_from_run": _required_top_string(data, "created_from_run", source),
        "owner_confirmation_status": _required_top_string(data, "owner_confirmation_status", source),
    }


def _validate_rule_proposal_contract(
    data: dict,
    source: str,
    fields: dict[str, str],
    requires_confirmation: object,
) -> None:
    action = fields["action"]
    scope = fields["scope"]
    match = fields["match"]
    pattern = fields["pattern"]
    owner_confirmation_status = fields["owner_confirmation_status"]
    if action not in ALLOWED_RULE_ACTIONS:
        raise ValueError(f"{source}: action must be one of {sorted(ALLOWED_RULE_ACTIONS)}")
    if scope not in ALLOWED_RULE_SCOPES:
        raise ValueError(f"{source}: scope must be one of {sorted(ALLOWED_RULE_SCOPES)}")
    if scope == "source_pattern":
        source_pattern = data.get("source_pattern")
        if not isinstance(source_pattern, str) or not source_pattern.strip():
            raise ValueError(f"{source}: source_pattern is required when scope is source_pattern")
    if scope == "document_type":
        document_type = data.get("document_type")
        if not isinstance(document_type, str) or not document_type.strip():
            raise ValueError(f"{source}: document_type is required when scope is document_type")
    if match not in ALLOWED_MATCH_TYPES:
        raise ValueError(f"{source}: match must be one of {sorted(ALLOWED_MATCH_TYPES)}")
    _validate_regex_pattern(match, pattern, f"{source}: pattern")
    if requires_confirmation is not True:
        raise ValueError(f"{source}: requires_confirmation must be true")
    _validate_owner_confirmation_status(data, owner_confirmation_status, source)
    _validate_required_string_list(data.get("examples"), "examples", source)
    _validate_required_string_list(data.get("counterexamples"), "counterexamples", source)


def _required_string(raw_rule: dict, key: str, source: str, idx: int) -> str:
    value = raw_rule.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: rules[{idx}].{key} must be a non-empty string")
    return value


def _required_top_string(data: dict, key: str, source: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: {key} must be a non-empty string")
    return value


def _validate_required_string_list(value: object, key: str, source: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{source}: {key} must be a list")
    if not value:
        raise ValueError(f"{source}: {key} must contain at least one item")
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{source}: {key}[{idx}] must be a non-empty string")


def _validate_owner_confirmation_status(data: dict, owner_confirmation_status: str, source: str) -> None:
    if owner_confirmation_status not in ALLOWED_OWNER_CONFIRMATION_STATUSES:
        raise ValueError(
            f"{source}: owner_confirmation_status must be one of {sorted(ALLOWED_OWNER_CONFIRMATION_STATUSES)}"
        )
    raw_status = data.get("status")
    status = raw_status if isinstance(raw_status, str) else ""
    if status not in ALLOWED_RULE_PROPOSAL_STATUSES:
        raise ValueError(f"{source}: status must be one of {sorted(ALLOWED_RULE_PROPOSAL_STATUSES)}")
    expected_by_status = {
        "proposed": "pending",
        "accepted": "confirmed",
        "rejected": "rejected",
    }
    expected = expected_by_status.get(status)
    if expected and owner_confirmation_status != expected:
        raise ValueError(f"{source}: owner_confirmation_status must be {expected} when status is {status}")


def _optional_lifecycle_status(data: dict, source: str) -> str | None:
    value = data.get("lifecycle_status")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: lifecycle_status must be a non-empty string when provided")
    if value not in ALLOWED_RULE_LIFECYCLE_STATUSES:
        raise ValueError(f"{source}: lifecycle_status must be one of {sorted(ALLOWED_RULE_LIFECYCLE_STATUSES)}")
    history = data.get("lifecycle_history")
    if history is not None:
        _validate_lifecycle_history(history, source)
    _validate_lifecycle_matches_status(data, value, source)
    return value


def _validate_lifecycle_history(value: object, source: str) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{source}: lifecycle_history must be a non-empty list when provided")
    for idx, item in enumerate(value):
        if item not in ALLOWED_RULE_LIFECYCLE_STATUSES:
            raise ValueError(
                f"{source}: lifecycle_history[{idx}] must be one of {sorted(ALLOWED_RULE_LIFECYCLE_STATUSES)}"
            )


def _validate_lifecycle_matches_status(data: dict, lifecycle_status: str, source: str) -> None:
    raw_status = data.get("status")
    status = raw_status if isinstance(raw_status, str) else ""
    allowed_by_status = {
        "proposed": {"proposed"},
        "accepted": {"accepted", "rerun_pending", "rerun_passed", "rerun_failed"},
        "rejected": {"rejected"},
    }
    allowed = allowed_by_status.get(status)
    if allowed is None:
        return
    if lifecycle_status not in allowed:
        raise ValueError(f"{source}: lifecycle_status {lifecycle_status!r} is invalid when status is {status!r}")
    history = data.get("lifecycle_history")
    if isinstance(history, list) and history[-1] != lifecycle_status:
        raise ValueError(f"{source}: lifecycle_history must end with lifecycle_status")


def _validate_regex_pattern(match: str, pattern: str, source: str) -> None:
    if match != "regex":
        return
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"{source} is not a valid regex: {exc}") from exc


def _string_list(container: dict, key: str, source: str) -> list[str]:
    value = container.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{source}: keyword_sets.{key} must be a list")
    result = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{source}: keyword_sets.{key}[{idx}] must be a non-empty string")
        result.append(item)
    return result


def _classification_pattern_list(container: dict, key: str, source: str) -> list[ClassificationPattern]:
    value = container.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{source}: keyword_sets.{key} must be a list")
    result: list[ClassificationPattern] = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{source}: keyword_sets.{key}[{idx}] must be an object")
        label = item.get("label")
        pattern = item.get("pattern")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{source}: keyword_sets.{key}[{idx}].label must be a non-empty string")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError(f"{source}: keyword_sets.{key}[{idx}].pattern must be a non-empty string")
        result.append(ClassificationPattern(label=label, pattern=pattern))
    return result
