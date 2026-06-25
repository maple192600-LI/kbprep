"""Dictionary promotion history summaries and resolution checks."""

from datetime import datetime, timezone
from pathlib import Path

from ..envelope import fail, ok
from .rerun_verification import _dedupe_paths_local, _rerun_representative_source
from .support import (
    _append_jsonl_locked,
    _optional_string,
    _promotion_history_rules_dir,
    _read_jsonl,
    _string_list,
    _target_rules_dir,
)


def _promotion_history_risk(*, target_rules_dir: Path, document_type: str) -> dict:
    history_path = target_rules_dir / "promotion_history.jsonl"
    if not history_path.exists():
        return {
            "status": "clear",
            "history_path": str(history_path),
            "reason": "No promotion history found for this rules directory.",
        }
    entries = [
        item for item in _read_jsonl(history_path)
        if item.get("schema") in {"kbprep.dictionary_promotion_history.v1", "kbprep.dictionary_promotion_resolution.v1"}
        and item.get("document_type") == document_type
    ]
    if not entries:
        return {
            "status": "clear",
            "history_path": str(history_path),
            "reason": f"No promotion history found for document_type: {document_type}.",
        }
    summary = _promotion_history_document_summary(document_type, entries)
    counts = _promotion_history_counts(entries)
    if counts["unresolved_failed"] > 0:
        return {
            "status": "blocked",
            "lifecycle_status": "promotion_blocked",
            "history_path": str(history_path),
            "summary": summary,
            "failed_samples": _failed_sample_references(entries),
            "reason": "Failed promotion history exists for this document type.",
        }
    if counts["unverified"] > 0:
        return {
            "status": "warn",
            "history_path": str(history_path),
            "summary": summary,
            "reason": "Unverified promotion history exists for this document type.",
        }
    return {
        "status": "clear",
        "history_path": str(history_path),
        "summary": summary,
    }

def _append_promotion_history(
    *,
    document_type: str,
    target_rules_dir: Path,
    target_path: Path,
    backup_path: Path | None,
    promoted_rules: list[dict],
    skipped_duplicates: int,
    suggestions_path: Path,
    regression_verification: dict,
) -> dict:
    history_path = target_rules_dir / "promotion_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "schema": "kbprep.dictionary_promotion_history.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "document_type": document_type,
        "target_path": str(target_path),
        "backup_path": str(backup_path) if backup_path else None,
        "source_suggestions_path": str(suggestions_path),
        "promoted_count": len(promoted_rules),
        "skipped_duplicates": skipped_duplicates,
        "promoted_rule_ids": [
            str(rule.get("id"))
            for rule in promoted_rules
            if rule.get("id")
        ],
        "regression_verification": regression_verification,
    }
    _append_jsonl_locked(history_path, entry)
    return {"path": history_path, "entry": entry}

def _summarize_promotion_history(data: dict) -> None:
    target_rules_dir = _target_rules_dir(data)
    history_rules_dir = _promotion_history_rules_dir(target_rules_dir)
    history_path = Path(
        _optional_string(data.get("promotion_history_file")) or str(history_rules_dir / "promotion_history.jsonl")
    ).expanduser().resolve()
    document_type_filter = _optional_string(data.get("document_type"))
    if not history_path.exists():
        ok(data={
            "summary": {
                "schema": "kbprep.dictionary_promotion_history_summary.v1",
                "history_path": str(history_path),
                "total_promotions": 0,
                "document_types": [],
                "recommendation": "No promotion history found. Promote only after review and rerun representative sources when possible.",
            },
        })
        return

    entries = [
        item for item in _read_jsonl(history_path)
        if item.get("schema") in {"kbprep.dictionary_promotion_history.v1", "kbprep.dictionary_promotion_resolution.v1"}
    ]
    if document_type_filter:
        entries = [
            item for item in entries
            if item.get("document_type") == document_type_filter
        ]

    grouped: dict[str, list[dict]] = {}
    for entry in entries:
        document_type = _optional_string(entry.get("document_type")) or "unknown"
        grouped.setdefault(document_type, []).append(entry)

    document_types = [
        _promotion_history_document_summary(document_type, items)
        for document_type, items in sorted(grouped.items())
    ]
    ok(data={
        "summary": {
            "schema": "kbprep.dictionary_promotion_history_summary.v1",
            "history_path": str(history_path),
            "document_type_filter": document_type_filter,
            "total_promotions": len(entries),
            "document_types": document_types,
            "recommendation": _overall_history_recommendation(document_types),
        },
    })

def _promotion_history_document_summary(document_type: str, entries: list[dict]) -> dict:
    sorted_entries = sorted(entries, key=lambda item: str(item.get("created_at") or ""))
    latest = sorted_entries[-1] if sorted_entries else {}
    latest_status = _latest_promotion_status(latest)
    last_failure_reason = _last_failure_reason(sorted_entries)
    return {
        "document_type": document_type,
        "latest_status": latest_status,
        "latest_created_at": latest.get("created_at"),
        "last_failure_reason": last_failure_reason,
        "recommended_action": _document_history_recommendation(
            latest_status=latest_status,
            last_failure_reason=last_failure_reason,
        ),
    }


def _resolve_promotion_failures(data: dict) -> None:
    if not _has_failure_resolution_confirmation(data):
        return

    document_type = _required_resolution_document_type(data)
    if not document_type:
        return
    target_rules_dir = _target_rules_dir(data)
    history_rules_dir = _promotion_history_rules_dir(target_rules_dir)
    history_path = history_rules_dir / "promotion_history.jsonl"
    if not history_path.exists():
        fail("E_INPUT_NOT_FOUND", f"promotion_history.jsonl does not exist: {history_path}")

    existing = _document_promotion_history_entries(history_path, document_type)
    summary = _promotion_history_document_summary(document_type, existing)
    unresolved_failed = _promotion_history_counts(existing)["unresolved_failed"]
    if unresolved_failed == 0:
        ok(data=_no_resolution_needed_response(document_type, history_path, summary))
        return

    run_dirs = _resolution_run_dirs(data)
    if not run_dirs:
        fail(
            "E_INPUT_NOT_FOUND",
            "representative_run_dirs is required to resolve failed promotion history.",
            recoverable=True,
            suggested_action="Pass at least one representative_run_dir from the failed or fixed document-type samples.",
        )

    verification = _resolution_regression_verification(run_dirs, target_rules_dir)
    if verification["status"] != "passed":
        fail(
            "E_PROMOTION_RESOLUTION_FAILED",
            "Representative reruns still fail; failed promotion history remains unresolved.",
            details={"regression_verification": verification, "summary": summary},
            recoverable=True,
            suggested_action="Inspect failed sample quality_report.json and cleaned.md before marking this promotion history resolved.",
        )

    entry = _promotion_resolution_entry(document_type, history_path, unresolved_failed, verification)
    _append_jsonl_locked(history_path, entry)
    updated_entries = [*existing, entry]
    ok(data={
        "resolution": entry,
        "summary": _promotion_history_document_summary(document_type, updated_entries),
    })


def _has_failure_resolution_confirmation(data: dict) -> bool:
    if data.get("confirm_failure_resolved") is True:
        return True
    fail(
        "E_CONFIRMATION_REQUIRED",
        "confirm_failure_resolved must be true before failed promotion history can be marked resolved.",
        recoverable=True,
        suggested_action="Rerun representative samples, inspect quality_report.json and cleaned.md, then retry with confirm_failure_resolved=true.",  # noqa: E501
    )
    return False


def _required_resolution_document_type(data: dict) -> str | None:
    document_type = _optional_string(data.get("document_type"))
    if document_type and document_type != "unknown":
        return document_type
    fail("E_INVALID_INPUT", "document_type is required and cannot be unknown")
    return None


def _document_promotion_history_entries(history_path: Path, document_type: str) -> list[dict]:
    return [
        item for item in _read_jsonl(history_path)
        if item.get("schema") in {"kbprep.dictionary_promotion_history.v1", "kbprep.dictionary_promotion_resolution.v1"}
        and item.get("document_type") == document_type
    ]


def _no_resolution_needed_response(document_type: str, history_path: Path, summary: dict) -> dict:
    return {
        "resolution": {
            "schema": "kbprep.dictionary_promotion_resolution.v1",
            "document_type": document_type,
            "status": "not_needed",
            "resolved_failed_promotions": 0,
            "history_path": str(history_path),
            "summary": summary,
        },
    }


def _resolution_run_dirs(data: dict) -> list[Path]:
    return [
        Path(value).expanduser().resolve()
        for value in _string_list(data.get("representative_run_dirs"))
    ]


def _resolution_regression_verification(run_dirs: list[Path], target_rules_dir: Path) -> dict:
    samples = [
        _rerun_representative_source(
            run_dir=run_dir,
            target_rules_dir=target_rules_dir,
            promoted_rules=[],
        )
        for run_dir in _dedupe_paths_local(run_dirs)
    ]
    passed = [sample for sample in samples if sample.get("ok")]
    return {
        "status": "passed" if len(passed) == len(samples) else "failed",
        "ok": len(passed) == len(samples),
        "sample_count": len(samples),
        "passed_count": len(passed),
        "failed_count": len(samples) - len(passed),
        "samples": samples,
    }


def _promotion_resolution_entry(
    document_type: str,
    history_path: Path,
    unresolved_failed: int,
    verification: dict,
) -> dict:
    return {
        "schema": "kbprep.dictionary_promotion_resolution.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "document_type": document_type,
        "resolved_failed_promotions": unresolved_failed,
        "history_path": str(history_path),
        "regression_verification": verification,
    }

def _promotion_failure_reasons(verification: dict) -> list[str]:
    reasons = []
    if _optional_string(verification.get("reason")):
        reasons.append(str(verification.get("reason")))
    samples = verification.get("samples")
    if isinstance(samples, list):
        for sample in samples:
            if not isinstance(sample, dict) or sample.get("ok"):
                continue
            if _optional_string(sample.get("reason")):
                reasons.append(str(sample.get("reason")))
            elif _optional_string(sample.get("error")):
                reasons.append(str(sample.get("error")))
            worker_error = sample.get("worker_error")
            if isinstance(worker_error, dict) and _optional_string(worker_error.get("code")):
                reasons.append(str(worker_error.get("code")))
            effects = sample.get("rule_effects")
            if isinstance(effects, list):
                for effect in effects:
                    if isinstance(effect, dict) and effect.get("ok") is False and _optional_string(effect.get("effect")):
                        reasons.append(str(effect.get("effect")))
    return reasons


def _failed_sample_references(entries: list[dict]) -> list[dict]:
    result: list[dict] = []
    for entry in entries:
        verification = entry.get("regression_verification")
        verification = verification if isinstance(verification, dict) else {}
        if verification.get("status") != "failed":
            continue
        samples = verification.get("samples")
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if isinstance(sample, dict) and sample.get("ok") is False:
                result.append(_failed_sample_reference(sample))
    return result[:10]


def _failed_sample_reference(sample: dict) -> dict:
    worker_error = sample.get("worker_error")
    worker_error = worker_error if isinstance(worker_error, dict) else {}
    return {
        "run_dir": _optional_string(sample.get("run_dir")) or "",
        "source_path": _optional_string(sample.get("source_path")) or "",
        "reason": _optional_string(sample.get("reason")) or _optional_string(sample.get("error")) or "",
        "worker_error_code": _optional_string(worker_error.get("code")) or "",
    }

def _promotion_history_counts(entries: list[dict]) -> dict:
    failed = 0
    resolved_failed = 0
    unverified = 0
    for entry in entries:
        schema = entry.get("schema")
        verification = entry.get("regression_verification")
        verification = verification if isinstance(verification, dict) else {}
        status = _optional_string(verification.get("status")) or "unknown"
        if schema == "kbprep.dictionary_promotion_resolution.v1":
            if status == "passed":
                resolved_failed += _positive_int_or_zero(entry.get("resolved_failed_promotions")) or 1
            else:
                unverified += 1
            continue
        if status == "failed":
            failed += 1
        elif status != "passed":
            unverified += 1
    return {
        "unresolved_failed": max(0, failed - resolved_failed),
        "unverified": unverified,
    }


def _latest_promotion_status(entry: dict) -> str:
    if not entry:
        return "unknown"
    verification = entry.get("regression_verification")
    verification = verification if isinstance(verification, dict) else {}
    if entry.get("schema") == "kbprep.dictionary_promotion_resolution.v1":
        return "resolved" if verification.get("status") == "passed" else "resolution_failed"
    return _optional_string(verification.get("status")) or "unknown"


def _last_failure_reason(entries: list[dict]) -> str:
    latest = entries[-1] if entries else {}
    if _latest_promotion_status(latest) == "resolved":
        return ""
    for entry in reversed(entries):
        verification = entry.get("regression_verification")
        verification = verification if isinstance(verification, dict) else {}
        reasons = _promotion_failure_reasons(verification)
        if reasons:
            return reasons[0]
    return ""


def _document_history_recommendation(*, latest_status: str, last_failure_reason: str) -> str:
    if latest_status in {"failed", "resolution_failed"} or last_failure_reason:
        return "Stop promoting more rules for this document type until failed regression samples are reviewed."
    if latest_status in {"not_requested", "unavailable", "unknown"}:
        return "Run regression verification before accepting more dictionary changes for this document type."
    return "Promotion history is currently passing; continue requiring review and representative reruns."

def _overall_history_recommendation(document_types: list[dict]) -> str:
    if any(item.get("last_failure_reason") or item.get("latest_status") in {"failed", "resolution_failed"} for item in document_types):
        return "At least one document type has failed promotions; review failures before adding more rules."
    if any(item.get("latest_status") in {"not_requested", "unavailable", "unknown"} for item in document_types):
        return "Some promotions are unverified; run representative regression before relying on those dictionaries."
    if document_types:
        return "Promotion history is passing so far; keep using confirmation and regression checks."
    return "No promotion history found."

def _positive_int_or_zero(value: object) -> int:
    try:
        parsed = int(value) if isinstance(value, (str, int, float)) and not isinstance(value, bool) else 0
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)
