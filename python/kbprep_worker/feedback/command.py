"""Feedback command dispatcher."""

from datetime import datetime, timezone
from uuid import uuid4

from ..envelope import ok
from ..rule_schema import validate_rule_proposal
from .dictionary_suggestions import _promote_dictionary_suggestion, _suggest_dictionary_updates
from .promotion_history import _resolve_promotion_failures, _summarize_promotion_history
from .proposals import _accept_proposal, _confidence, _counterexamples, _examples, _reason, _reject_proposal, _risk_note
from .support import (
    _action,
    _append_jsonl_locked,
    _feedback_text,
    _match_type,
    _optional_string,
    _pattern,
    _proposal_scope_payload,
    _required_path,
    _rules_dir,
    _run_artifacts,
)


def run(data: dict) -> None:
    if _dispatch_special_action(data):
        return
    proposal, proposal_path = _create_feedback_proposal(data)
    ok(data={
        "proposal": proposal,
        "proposal_path": str(proposal_path),
        "next_step": "Review the proposal, then rerun kbprep-feedback with accept_proposal.",
    })


def _dispatch_special_action(data: dict) -> bool:
    if data.get("resolve_promotion_failures") is True:
        _resolve_promotion_failures(data)
        return True
    if data.get("summarize_promotion_history") is True:
        _summarize_promotion_history(data)
        return True
    if data.get("promote_dictionary_suggestion") is True:
        _promote_dictionary_suggestion(data)
        return True
    if data.get("suggest_dictionary_updates") is True:
        _suggest_dictionary_updates(data)
        return True
    if _optional_string(data.get("accept_proposal")):
        _accept_proposal(data)
        return True
    if _optional_string(data.get("reject_proposal")):
        _reject_proposal(data)
        return True
    return False


def _create_feedback_proposal(data: dict) -> tuple[dict, object]:
    run_dir = _required_path(data, "run_dir")
    feedback_text = _feedback_text(data)
    artifacts = _run_artifacts(run_dir)
    rules_dir = _rules_dir(data)
    rules_dir.mkdir(parents=True, exist_ok=True)
    action = _action(data, feedback_text)
    match = _match_type(data)
    pattern = _pattern(data, feedback_text)
    scope_payload = _proposal_scope_payload(data, artifacts, rules_dir, action, match, pattern)

    proposal = {
        "schema": "kbprep.rule_proposal.v1",
        "id": f"proposal-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        "status": "proposed",
        "lifecycle_status": "proposed",
        "lifecycle_history": ["proposed"],
        "action": action,
        **scope_payload,
        "document_type": _optional_string(data.get("document_type")),
        "match": match,
        "pattern": pattern,
        "examples": _examples(data, feedback_text, pattern, match, action, artifacts),
        "counterexamples": _counterexamples(data, pattern, match, action, artifacts),
        "reason": _reason(data, feedback_text),
        "risk_note": _risk_note(data, action, scope_payload["scope"], match),
        "created_from_run": str(run_dir),
        "artifact_context": artifacts["context"],
        "confidence": _confidence(data),
        "owner_confirmation_status": "pending",
        "requires_confirmation": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    validate_rule_proposal(proposal, "feedback")

    proposal_path = rules_dir / "proposed_rules.jsonl"
    _append_jsonl_locked(proposal_path, proposal)
    return proposal, proposal_path
