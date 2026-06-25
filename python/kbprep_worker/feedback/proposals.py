"""Feedback rule proposal creation, acceptance, rejection, and narrowing."""

import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..envelope import fail, ok
from ..rule_schema import validate_rule_proposal
from .rerun_verification import _rerun_after_accept
from .support import (
    _append_jsonl_locked,
    _clean_snippet_line,
    _dedupe_strings,
    _looks_like_body_counterexample,
    _matches_pattern,
    _matching_snippets,
    _optional_string,
    _read_jsonl,
    _replace_jsonl_record_locked,
    _rules_dir,
    _string_list,
)

MANUAL_COUNTEREXAMPLE_REQUIRED = "Manual counterexample required before accepting this proposal."


def _accept_proposal(data: dict) -> None:
    rules_dir = _rules_dir(data)
    proposed_path = rules_dir / "proposed_rules.jsonl"
    accepted_path = rules_dir / "accepted_rules.jsonl"
    rejected_path = rules_dir / "rejected_rules.jsonl"
    wanted = _optional_string(data.get("accept_proposal"))
    if not wanted:
        fail("E_INPUT_NOT_FOUND", "accept_proposal is required")
        return
    if not proposed_path.exists():
        fail("E_INPUT_NOT_FOUND", f"proposed_rules.jsonl does not exist: {proposed_path}")

    selected = _selected_proposal(proposed_path, wanted)
    validate_rule_proposal(selected, str(proposed_path))
    _guard_not_rejected(selected, rejected_path, wanted)

    accepted_existing = _read_jsonl(accepted_path) if accepted_path.exists() else []
    if any(item.get("id") == selected.get("id") for item in accepted_existing):
        ok(data={
            "accepted": selected,
            "accepted_path": str(accepted_path),
            "already_accepted": True,
        })
        return

    if not _has_rule_acceptance_confirmation(data):
        return

    validation = _validated_acceptance_or_fail(selected, proposed_path)
    accepted = _accepted_proposal_payload(selected, validation, rerun_requested=data.get("rerun_after_accept") is True)
    validate_rule_proposal(accepted, "accepted feedback")
    rules_dir.mkdir(parents=True, exist_ok=True)
    _append_jsonl_locked(accepted_path, accepted)

    rerun_verification = _rerun_after_accept(accepted, rules_dir, data)
    accepted = _accepted_payload_after_rerun(accepted, rerun_verification, rerun_requested=data.get("rerun_after_accept") is True)
    validate_rule_proposal(accepted, "accepted feedback")
    _replace_jsonl_record_locked(accepted_path, str(accepted["id"]), accepted)

    ok(data={
        "accepted": accepted,
        "accepted_path": str(accepted_path),
        "rerun_verification": rerun_verification,
        "next_step": "Rerun the affected source and inspect quality_report.json, discarded.md, and review_needed.md.",
    })
    return


def _selected_proposal(proposed_path: Path, wanted: str) -> dict:
    proposals = _read_jsonl(proposed_path)
    selected = proposals[-1] if wanted == "latest" and proposals else next(
        (proposal for proposal in proposals if proposal.get("id") == wanted),
        None,
    )
    if isinstance(selected, dict):
        return selected
    fail("E_INPUT_NOT_FOUND", f"proposal not found: {wanted}")
    return {}


def _guard_not_rejected(selected: dict, rejected_path: Path, wanted: str) -> None:
    rejected_existing = _read_jsonl(rejected_path) if rejected_path.exists() else []
    if any(item.get("id") == selected.get("id") for item in rejected_existing):
        fail("E_INVALID_INPUT", f"proposal has been rejected and cannot be accepted: {wanted}")


def _validated_acceptance_or_fail(selected: dict, proposed_path: Path) -> dict:
    validation = _validate_proposal_acceptance(selected)
    if validation["ok"]:
        return validation
    suggested = _suggest_narrowed_proposal(selected, validation)
    if suggested:
        _append_jsonl_locked(proposed_path, suggested)
        validation = {**validation, "suggested_proposal": suggested}
    fail(
        "E_RULE_VALIDATION_FAILED",
        "Feedback rule proposal failed acceptance validation.",
        details=validation,
        recoverable=True,
        suggested_action="Review the suggested narrower proposal, then accept or reject it explicitly.",
    )
    return validation


def _accepted_proposal_payload(selected: dict, validation: dict, *, rerun_requested: bool) -> dict:
    lifecycle_history = ["accepted"]
    lifecycle_status = "accepted"
    if rerun_requested:
        lifecycle_history.append("rerun_pending")
        lifecycle_status = "rerun_pending"
    return {
        **selected,
        "status": "accepted",
        "lifecycle_status": lifecycle_status,
        "lifecycle_history": lifecycle_history,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "accepted_rule_id": f"user-feedback-{selected['id']}",
        "acceptance_validation": validation,
        "owner_confirmation_status": "confirmed",
        "requires_confirmation": True,
    }


def _accepted_payload_after_rerun(accepted: dict, rerun_verification: dict, *, rerun_requested: bool) -> dict:
    if not rerun_requested:
        return accepted
    lifecycle_status = _lifecycle_status_from_rerun(rerun_verification)
    history = _proposal_string_list(accepted.get("lifecycle_history"))
    if history and history[-1] == lifecycle_status:
        lifecycle_history = history
    else:
        lifecycle_history = [*history, lifecycle_status]
    return {
        **accepted,
        "lifecycle_status": lifecycle_status,
        "lifecycle_history": lifecycle_history,
    }


def _lifecycle_status_from_rerun(rerun_verification: dict) -> str:
    status = _optional_string(rerun_verification.get("status")) or ""
    if rerun_verification.get("ok") is True or status == "passed":
        return "rerun_passed"
    if status in {"unavailable", "not_requested", "skipped"}:
        return "rerun_pending"
    return "rerun_failed"


def _has_rule_acceptance_confirmation(data: dict) -> bool:
    if data.get("confirm_rule_acceptance") is True:
        return True
    fail(
        "E_CONFIRMATION_REQUIRED",
        "confirm_rule_acceptance must be true before a feedback proposal can become an accepted rule.",
        recoverable=True,
        suggested_action="Review proposed_rules.jsonl evidence, counterexamples, and risk_note; then rerun with confirm_rule_acceptance=true.",  # noqa: E501
    )
    return False


def _reject_proposal(data: dict) -> None:
    rules_dir = _rules_dir(data)
    proposed_path = rules_dir / "proposed_rules.jsonl"
    rejected_path = rules_dir / "rejected_rules.jsonl"
    accepted_path = rules_dir / "accepted_rules.jsonl"
    wanted = _optional_string(data.get("reject_proposal"))
    if not wanted:
        fail("E_INPUT_NOT_FOUND", "reject_proposal is required")
        return
    if not proposed_path.exists():
        fail("E_INPUT_NOT_FOUND", f"proposed_rules.jsonl does not exist: {proposed_path}")
        return

    selected = _selected_proposal(proposed_path, wanted)
    validate_rule_proposal(selected, str(proposed_path))

    accepted_existing = _read_jsonl(accepted_path) if accepted_path.exists() else []
    if any(item.get("id") == selected.get("id") for item in accepted_existing):
        fail("E_INVALID_INPUT", f"proposal has already been accepted and cannot be rejected: {wanted}")

    rejected_existing = _read_jsonl(rejected_path) if rejected_path.exists() else []
    if any(item.get("id") == selected.get("id") for item in rejected_existing):
        ok(data={
            "rejected": selected,
            "rejected_path": str(rejected_path),
            "already_rejected": True,
        })
        return

    rejected = {
        **selected,
        "status": "rejected",
        "lifecycle_status": "rejected",
        "lifecycle_history": ["rejected"],
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "reject_reason": _optional_string(data.get("reject_reason")) or "Rejected by user or reviewing agent.",
        "owner_confirmation_status": "rejected",
        "requires_confirmation": True,
    }
    validate_rule_proposal(rejected, "rejected feedback")
    rules_dir.mkdir(parents=True, exist_ok=True)
    _append_jsonl_locked(rejected_path, rejected)

    ok(data={
        "rejected": rejected,
        "rejected_path": str(rejected_path),
        "next_step": "Do not promote this proposal. Keep it as feedback memory so future agents do not suggest it again.",
    })
    return

def _examples(
    data: dict,
    feedback_text: str,
    pattern: str,
    match: str,
    action: str,
    artifacts: dict,
) -> list[str]:
    examples = _string_list(data.get("examples"))
    if examples:
        return examples
    if action == "discard":
        sources: tuple[str, ...] = ("discarded", "review_needed")
    elif action == "protect":
        sources = ("discarded", "cleaned", "review_needed")
    else:
        sources = ("review_needed", "discarded", "cleaned")
    result: list[str] = []
    for source in sources:
        result.extend(_matching_snippets(artifacts["texts"].get(source, ""), pattern, match))
    result.append(pattern)
    return _dedupe_strings(result)[:8]

def _counterexamples(data: dict, pattern: str, match: str, action: str, artifacts: dict) -> list[str]:
    explicit = _string_list(data.get("counterexamples"))
    if explicit:
        return explicit
    fallback_sources = ("cleaned", "review_needed", "discarded")
    if action != "discard":
        return _counterexample_fallbacks(artifacts, pattern, match, fallback_sources)
    result = _discard_body_counterexamples(artifacts, pattern, match)
    if result:
        return _dedupe_strings(result)[:5]
    return _counterexample_fallbacks(artifacts, pattern, match, fallback_sources)


def _discard_body_counterexamples(artifacts: dict, pattern: str, match: str) -> list[str]:
    result: list[str] = []
    texts = artifacts.get("texts")
    texts = texts if isinstance(texts, dict) else {}
    for source in ("cleaned", "review_needed"):
        for line in _matching_snippets(str(texts.get(source, "")), pattern, match, limit=12):
            if _looks_like_body_counterexample(line, pattern):
                result.append(line)
    result.extend(_quality_issue_counterexamples(artifacts, pattern, match))
    return result


def _quality_issue_counterexamples(artifacts: dict, pattern: str, match: str) -> list[str]:
    quality = artifacts.get("quality")
    quality = quality if isinstance(quality, dict) else {}
    issues = quality.get("quality_issues")
    if not isinstance(issues, list):
        return []
    result = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        for value in issue.values():
            result.extend(_quality_value_counterexamples(value, pattern, match))
    return result[:5]


def _quality_value_counterexamples(value: object, pattern: str, match: str) -> list[str]:
    if isinstance(value, str):
        return [
            line for line in _matching_snippets(value, pattern, match, limit=5)
            if _looks_like_body_counterexample(line, pattern)
        ]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_quality_value_counterexamples(item, pattern, match))
        return result
    if isinstance(value, dict):
        nested_result: list[str] = []
        for item in value.values():
            nested_result.extend(_quality_value_counterexamples(item, pattern, match))
        return nested_result
    return []


def _counterexample_fallbacks(artifacts: dict, pattern: str, match: str, sources: tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for source in sources:
        result.extend(_non_matching_snippets(artifacts["texts"].get(source, ""), pattern, match))
        if len(result) >= 5:
            break
    return _dedupe_strings(result)[:5] or [MANUAL_COUNTEREXAMPLE_REQUIRED]


def _non_matching_snippets(text: str, pattern: str, match: str, limit: int = 5) -> list[str]:
    snippets: list[str] = []
    for line in text.splitlines():
        cleaned = _clean_snippet_line(line)
        if not cleaned or _matches_pattern(cleaned, pattern, match):
            continue
        snippets.append(cleaned[:240])
        if len(snippets) >= limit:
            break
    return snippets

def _validate_proposal_acceptance(proposal: dict) -> dict:
    pattern = str(proposal.get("pattern", ""))
    match = str(proposal.get("match", "literal"))
    examples = _proposal_string_list(proposal.get("examples"))
    counterexamples = _proposal_string_list(proposal.get("counterexamples"))
    example_misses = [
        value for value in examples
        if not _matches_pattern(value, pattern, match)
    ]
    counterexample_matches = [
        value for value in counterexamples
        if _matches_pattern(value, pattern, match)
    ]
    missing_counterexamples = [
        value for value in counterexamples
        if value == MANUAL_COUNTEREXAMPLE_REQUIRED
    ]
    return {
        "ok": not example_misses and not counterexample_matches and not missing_counterexamples,
        "example_count": len(examples),
        "counterexample_count": len(counterexamples),
        "example_misses": example_misses[:10],
        "counterexample_matches": counterexample_matches[:10],
        "missing_counterexamples": missing_counterexamples[:10],
    }

def _proposal_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result

def _suggest_narrowed_proposal(proposal: dict, validation: dict) -> dict | None:
    if proposal.get("action") != "discard":
        return None
    if not validation.get("counterexample_matches"):
        return None

    match = str(proposal.get("match", "literal"))
    if match != "literal":
        return None

    current_pattern = str(proposal.get("pattern", "")).strip()
    examples = _proposal_string_list(proposal.get("examples"))
    counterexamples = _proposal_string_list(proposal.get("counterexamples"))
    candidates = _literal_narrowing_candidates(examples, current_pattern)
    regex_narrowed = _regex_narrowed_from_examples(proposal, candidates, counterexamples, current_pattern)
    if regex_narrowed:
        return regex_narrowed

    narrowed_pattern = _first_safe_literal_candidate(candidates, counterexamples)
    if not narrowed_pattern:
        return None

    narrowed = _literal_narrowed_payload(proposal, narrowed_pattern, candidates, counterexamples, current_pattern)
    narrowed.update(_narrowed_scope_from_artifacts(proposal))
    validate_rule_proposal(narrowed, "narrowed feedback proposal")
    if not _validate_proposal_acceptance(narrowed)["ok"]:
        return None
    return narrowed


def _literal_narrowing_candidates(examples: list[str], current_pattern: str) -> list[str]:
    candidates = [
        example for example in examples
        if example.strip()
        and example.strip() != current_pattern
        and current_pattern.lower() in example.lower()
    ]
    candidates.sort(key=lambda value: (len(value), value))
    return candidates


def _first_safe_literal_candidate(candidates: list[str], counterexamples: list[str]) -> str | None:
    return next(
        (
            candidate for candidate in candidates
            if not any(candidate.lower() in counterexample.lower() for counterexample in counterexamples)
        ),
        None,
    )


def _literal_narrowed_payload(
    proposal: dict,
    narrowed_pattern: str,
    candidates: list[str],
    counterexamples: list[str],
    current_pattern: str,
) -> dict:
    return {
        **proposal,
        "id": _new_proposal_id(),
        "status": "proposed",
        "lifecycle_status": "proposed",
        "lifecycle_history": ["proposed"],
        "pattern": narrowed_pattern[:120],
        "match": "literal",
        "examples": _dedupe_strings([narrowed_pattern, *candidates])[:8],
        "counterexamples": _dedupe_strings(counterexamples)[:5],
        "parent_proposal_id": proposal.get("id"),
        "narrowed_from_pattern": current_pattern,
        "narrowing_reason": "Original proposal matched counterexamples; narrowed to a concrete run-artifact example.",
        "requires_confirmation": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _new_proposal_id() -> str:
    return f"proposal-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


def _regex_narrowed_from_examples(
    proposal: dict,
    candidates: list[str],
    counterexamples: list[str],
    current_pattern: str,
) -> dict | None:
    if _literal_narrowing_can_validate(candidates, counterexamples):
        return None
    prefix = _shared_positive_prefix(candidates, current_pattern)
    if not prefix:
        return None
    pattern = rf"^\s*(?:[-*+]\s+)?{re.escape(prefix)}(?:\s|$|[，。！？:：,.;；])"
    examples = [example for example in candidates if _matches_pattern(example, pattern, "regex")]
    if not examples:
        return None
    narrowed = {
        **proposal,
        "id": f"proposal-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        "status": "proposed",
        "lifecycle_status": "proposed",
        "lifecycle_history": ["proposed"],
        "pattern": pattern,
        "match": "regex",
        "examples": _dedupe_strings(examples)[:8],
        "counterexamples": _dedupe_strings(counterexamples)[:5],
        "parent_proposal_id": proposal.get("id"),
        "narrowed_from_pattern": current_pattern,
        "narrowing_reason": "Original literal proposal matched counterexamples; narrowed to a line-start regex from positive run-artifact examples.",  # noqa: E501
        "requires_confirmation": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    narrowed.update(_narrowed_scope_from_artifacts(proposal))
    validate_rule_proposal(narrowed, "narrowed feedback proposal")
    if not _validate_proposal_acceptance(narrowed)["ok"]:
        return None
    return narrowed

def _literal_narrowing_can_validate(candidates: list[str], counterexamples: list[str]) -> bool:
    for candidate in candidates:
        if any(candidate.lower() in counterexample.lower() for counterexample in counterexamples):
            continue
        examples = _dedupe_strings([candidate, *candidates])[:8]
        if all(candidate.lower() in example.lower() for example in examples):
            return True
    return False

def _shared_positive_prefix(candidates: list[str], current_pattern: str) -> str | None:
    values = _dedupe_strings([_normalize_regex_example(candidate) for candidate in candidates])
    if not values:
        return None
    prefix = values[0]
    for value in values[1:]:
        prefix = _common_prefix(prefix, value)
    prefix = prefix.rstrip(" ，。！？:：,.;；、")
    if not prefix.casefold().startswith(current_pattern.casefold()):
        return None
    if len(prefix) <= len(current_pattern.strip()) + 1:
        return None
    return prefix

def _normalize_regex_example(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()

def _common_prefix(left: str, right: str) -> str:
    index = 0
    max_index = min(len(left), len(right))
    while index < max_index and left[index].casefold() == right[index].casefold():
        index += 1
    return left[:index]

def _narrowed_scope_from_artifacts(proposal: dict) -> dict:
    if proposal.get("scope") in {"document_type", "source_pattern"}:
        return {}
    artifact_context = proposal.get("artifact_context")
    if not isinstance(artifact_context, dict):
        return {}
    document_type = _optional_string(artifact_context.get("document_type"))
    if document_type and document_type != "unknown":
        return {
            "scope": "document_type",
            "document_type": document_type,
            "narrowed_scope_reason": "Run artifact context identified a document type, so the follow-up proposal is limited to that document type.",  # noqa: E501
        }
    source_name = _optional_string(artifact_context.get("source_name"))
    if source_name:
        return {
            "scope": "source_pattern",
            "source_pattern": source_name,
            "narrowed_scope_reason": "Run artifact context identified a source file, so the follow-up proposal is limited to that source pattern.",  # noqa: E501
        }
    return {}

def _reason(data: dict, feedback_text: str) -> str:
    explicit = _optional_string(data.get("reason"))
    if explicit:
        return explicit
    return feedback_text[:500]

def _confidence(data: dict) -> str | float:
    value = data.get("confidence")
    if isinstance(value, (int, float)):
        return float(value)
    text = _optional_string(value)
    return text or "needs_review"


def _risk_note(data: dict, action: str, scope: str, match: str) -> str:
    explicit = _optional_string(data.get("risk_note"))
    if explicit:
        return explicit
    if action == "discard":
        return f"Discard rule uses {match} matching at {scope} scope; review counterexamples before accepting."
    if action == "protect":
        return f"Protect rule uses {match} matching at {scope} scope; review that it does not preserve cleanup noise."
    return f"Review rule uses {match} matching at {scope} scope; confirm before adding long-term behavior."
