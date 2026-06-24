"""Canonical IR TransformationLedger artifact builder and validator."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json

CANONICAL_IR_TRANSFORMATION_LEDGER_SCHEMA = "kbprep.canonical_ir_transformation_ledger.v1"
TRANSFORMATION_LEDGER_INVALID_CODE = "E_CANONICAL_IR_TRANSFORMATION_LEDGER_INVALID"
_REQUIRED_OPERATIONS = (
    "route_decision_recorded",
    "converted_markdown_written",
    "typed_nodes_artifact_written",
    "typed_nodes_artifact_validated",
    "source_spans_artifact_written",
    "source_spans_artifact_validated",
)
_ENTRY_ID_RE = re.compile(r"^e_\d{6}$")
_ENTRY_KEYS = frozenset({
    "entry_id",
    "ordinal",
    "stage",
    "operation",
    "producer",
    "target_node_ids",
    "target_span_ids",
    "evidence_refs",
    "details",
    "details_hash",
})


@dataclass(frozen=True)
class TransformationLedgerValidationIssue:
    code: str
    message: str
    evidence: dict[str, Any]


def write_transformation_ledger_artifact(
    *,
    run_dir: Path,
    document_id: str,
    run_id: str,
    converted_path: Path,
    typed_nodes_path: Path,
    typed_nodes_available: bool,
    source_spans_path: Path,
    source_spans_available: bool,
    conversion: dict[str, Any],
) -> Path:
    """Write ``canonical_ir/transformation_ledger.json`` for conversion evidence."""
    artifact_path = run_dir / "canonical_ir" / "transformation_ledger.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _ledger_payload(
        run_dir=run_dir,
        document_id=document_id,
        run_id=run_id,
        converted_path=converted_path,
        typed_nodes_path=typed_nodes_path,
        typed_nodes_available=typed_nodes_available,
        source_spans_path=source_spans_path,
        source_spans_available=source_spans_available,
        conversion=conversion,
    )
    atomic_write_json(artifact_path, payload, indent=2, trailing_newline=False)
    return artifact_path


def validate_transformation_ledger_artifact(
    *,
    run_dir: Path,
    ledger_path: Path,
    document_id: str,
    converted_path: Path,
    typed_nodes_path: Path,
    source_spans_path: Path,
) -> list[TransformationLedgerValidationIssue]:
    """Validate ``canonical_ir/transformation_ledger.json``."""
    issues: list[TransformationLedgerValidationIssue] = []
    payload = _read_required_json(ledger_path, "canonical_ir/transformation_ledger.json", issues)
    if payload is None:
        return issues
    _validate_header(run_dir, payload, document_id, converted_path, typed_nodes_path, source_spans_path, issues)
    entries = payload.get("entries")
    if not isinstance(entries, list):
        _add_issue(issues, "transformation_ledger.entries must be a list", {"entries": entries})
        return issues
    _validate_entry_count(payload.get("entry_count"), len(entries), issues)
    _validate_entries(entries, run_dir, issues)
    return issues


def validate_transformation_ledger_reference(
    *,
    run_dir: Path,
    artifacts: dict[str, Any],
    coverage: dict[str, Any],
    document_id: str,
    converted_path: Path,
) -> list[TransformationLedgerValidationIssue]:
    """Validate manifest reference and payload for ``transformation_ledger.json``."""
    issues: list[TransformationLedgerValidationIssue] = []
    raw_ref = artifacts.get("transformation_ledger")
    if raw_ref is None:
        if coverage.get("transformation_ledger_available") is True:
            _add_issue(issues, "coverage.transformation_ledger_available requires artifacts.transformation_ledger", {
                "transformation_ledger_available": coverage.get("transformation_ledger_available"),
            })
        return issues
    if coverage.get("transformation_ledger_available") is not True:
        _add_issue(issues, "coverage.transformation_ledger_available must be true when artifacts.transformation_ledger exists", {
            "transformation_ledger_available": coverage.get("transformation_ledger_available"),
        })
    _validate_ledger_manifest_reference(run_dir, artifacts, raw_ref, document_id, converted_path, issues)
    return issues


def _ledger_payload(
    *,
    run_dir: Path,
    document_id: str,
    run_id: str,
    converted_path: Path,
    typed_nodes_path: Path,
    typed_nodes_available: bool,
    source_spans_path: Path,
    source_spans_available: bool,
    conversion: dict[str, Any],
) -> dict[str, Any]:
    entries = _ledger_entries(
        run_dir=run_dir,
        converted_path=converted_path,
        typed_nodes_path=typed_nodes_path,
        typed_nodes_available=typed_nodes_available,
        source_spans_path=source_spans_path,
        source_spans_available=source_spans_available,
        conversion=conversion,
    )
    return {
        "schema": CANONICAL_IR_TRANSFORMATION_LEDGER_SCHEMA,
        "document_id": document_id,
        "canonical_ir_manifest": "canonical_ir/manifest.json",
        "converted_artifact": _relative_run_path(run_dir, converted_path),
        "typed_nodes_artifact": _relative_run_path(run_dir, typed_nodes_path),
        "source_spans_artifact": _relative_run_path(run_dir, source_spans_path),
        "created_from_run": run_id,
        "entry_count": len(entries),
        "entries": entries,
    }


def _ledger_entries(
    *,
    run_dir: Path,
    converted_path: Path,
    typed_nodes_path: Path,
    typed_nodes_available: bool,
    source_spans_path: Path,
    source_spans_available: bool,
    conversion: dict[str, Any],
) -> list[dict[str, Any]]:
    converted_ref = _relative_run_path(run_dir, converted_path)
    typed_ref = _relative_run_path(run_dir, typed_nodes_path)
    spans_ref = _relative_run_path(run_dir, source_spans_path)
    return [
        _conversion_entry(conversion),
        _artifact_written_entry(2, "converted_markdown_written", converted_ref, run_dir, converted_path),
        _artifact_written_entry(3, "typed_nodes_artifact_written", typed_ref, run_dir, typed_nodes_path),
        _artifact_validated_entry(4, "typed_nodes_artifact_validated", typed_ref, typed_nodes_available),
        _artifact_written_entry(5, "source_spans_artifact_written", spans_ref, run_dir, source_spans_path),
        _artifact_validated_entry(6, "source_spans_artifact_validated", spans_ref, source_spans_available),
    ]


def _conversion_entry(conversion: dict[str, Any]) -> dict[str, Any]:
    return _entry(
        1,
        stage="conversion",
        operation="route_decision_recorded",
        evidence_refs=["conversion_report.json"],
        details=_conversion_details(conversion),
    )


def _artifact_written_entry(
    ordinal: int,
    operation: str,
    ref: str,
    run_dir: Path,
    path: Path,
) -> dict[str, Any]:
    stage = "conversion" if operation == "converted_markdown_written" else "canonical_ir"
    return _entry(
        ordinal,
        stage=stage,
        operation=operation,
        evidence_refs=[ref],
        details=_artifact_summary(run_dir, path),
    )


def _artifact_validated_entry(
    ordinal: int,
    operation: str,
    ref: str,
    available: bool,
) -> dict[str, Any]:
    return _entry(
        ordinal,
        stage="canonical_ir",
        operation=operation,
        evidence_refs=[ref],
        details={"artifact": ref, "available": available},
    )


def _entry(
    ordinal: int,
    *,
    stage: str,
    operation: str,
    evidence_refs: list[str],
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "entry_id": f"e_{ordinal:06d}",
        "ordinal": ordinal,
        "stage": stage,
        "operation": operation,
        "producer": "canonical_ir",
        "target_node_ids": [],
        "target_span_ids": [],
        "evidence_refs": evidence_refs,
        "details": details,
        "details_hash": _stable_hash(details),
    }


def _validate_ledger_manifest_reference(
    run_dir: Path,
    artifacts: dict[str, Any],
    raw_ref: object,
    document_id: str,
    converted_path: Path,
    issues: list[TransformationLedgerValidationIssue],
) -> None:
    ledger_path = _resolve_run_reference(run_dir, raw_ref, "transformation_ledger", issues)
    typed_nodes_path = _resolve_run_reference(run_dir, artifacts.get("typed_nodes"), "typed_nodes", issues)
    source_spans_path = _resolve_run_reference(run_dir, artifacts.get("source_spans"), "source_spans", issues)
    if ledger_path is None or typed_nodes_path is None or source_spans_path is None:
        return
    expected = run_dir / "canonical_ir" / "transformation_ledger.json"
    if ledger_path != expected.resolve():
        _add_issue(issues, "artifacts.transformation_ledger must reference canonical_ir/transformation_ledger.json", {
            "transformation_ledger": raw_ref,
            "expected": "canonical_ir/transformation_ledger.json",
        })
    issues.extend(validate_transformation_ledger_artifact(
        run_dir=run_dir,
        ledger_path=ledger_path,
        document_id=document_id,
        converted_path=converted_path,
        typed_nodes_path=typed_nodes_path,
        source_spans_path=source_spans_path,
    ))


def _conversion_details(conversion: dict[str, Any]) -> dict[str, Any]:
    return {
        "converter": str(conversion.get("converter") or ""),
        "actual_route": str(conversion.get("actual_route") or ""),
        "route_decision_hash": str(conversion.get("route_decision_hash") or ""),
    }


def _artifact_summary(run_dir: Path, path: Path) -> dict[str, Any]:
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    return {"artifact": _relative_run_path(run_dir, path), "exists": exists, "bytes": size}


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _relative_run_path(run_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(run_dir.resolve()).as_posix()


def _read_required_json(
    path: Path,
    label: str,
    issues: list[TransformationLedgerValidationIssue],
) -> dict[str, Any] | None:
    if not path.exists():
        _add_issue(issues, f"{label} is missing", {label: str(path)})
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _add_issue(issues, f"{label} is not readable JSON", {label: str(path), "error": str(exc)})
        return None
    if isinstance(data, dict):
        return data
    _add_issue(issues, f"{label} must be a JSON object", {label: str(path)})
    return None


def _validate_header(
    run_dir: Path,
    payload: dict[str, Any],
    document_id: str,
    converted_path: Path,
    typed_nodes_path: Path,
    source_spans_path: Path,
    issues: list[TransformationLedgerValidationIssue],
) -> None:
    if payload.get("schema") != CANONICAL_IR_TRANSFORMATION_LEDGER_SCHEMA:
        _add_issue(issues, "transformation_ledger schema is invalid", {"schema": payload.get("schema")})
    if payload.get("document_id") != document_id:
        _add_issue(
            issues,
            "transformation_ledger.document_id must match canonical manifest",
            {"document_id": payload.get("document_id")},
        )
    if not _valid_nonempty_string(payload.get("created_from_run")):
        _add_issue(
            issues,
            "transformation_ledger.created_from_run must be a non-empty string",
            {"created_from_run": payload.get("created_from_run")},
        )
    _validate_run_reference(
        run_dir,
        payload.get("canonical_ir_manifest"),
        run_dir / "canonical_ir" / "manifest.json",
        "canonical_ir_manifest",
        issues,
    )
    _validate_run_reference(run_dir, payload.get("converted_artifact"), converted_path, "converted_artifact", issues)
    _validate_run_reference(run_dir, payload.get("typed_nodes_artifact"), typed_nodes_path, "typed_nodes_artifact", issues)
    _validate_run_reference(run_dir, payload.get("source_spans_artifact"), source_spans_path, "source_spans_artifact", issues)


def _validate_entry_count(
    entry_count: object,
    actual_count: int,
    issues: list[TransformationLedgerValidationIssue],
) -> None:
    if not isinstance(entry_count, int) or isinstance(entry_count, bool) or entry_count < 0:
        _add_issue(issues, "transformation_ledger.entry_count must be a non-negative integer", {"entry_count": entry_count})
    elif entry_count != actual_count:
        _add_issue(issues, "transformation_ledger.entry_count must equal len(entries)", {
            "entry_count": entry_count,
            "actual_count": actual_count,
        })


def _validate_entries(
    entries: list[object],
    run_dir: Path,
    issues: list[TransformationLedgerValidationIssue],
) -> None:
    if len(entries) != len(_REQUIRED_OPERATIONS):
        _add_issue(issues, "transformation_ledger.entries must record the required operations", {"entry_count": len(entries)})
    for position, entry in enumerate(entries, start=1):
        _validate_entry(entry, position, run_dir, issues)


def _validate_entry(
    entry: object,
    position: int,
    run_dir: Path,
    issues: list[TransformationLedgerValidationIssue],
) -> None:
    if not isinstance(entry, dict):
        _add_issue(issues, "transformation_ledger entry must be an object", {"position": position})
        return
    _validate_entry_shape(entry, position, issues)
    _validate_entry_strings(entry, position, issues)
    _validate_entry_lists(entry, position, run_dir, issues)
    _validate_entry_details(entry, position, issues)


def _validate_entry_shape(
    entry: dict[str, Any],
    position: int,
    issues: list[TransformationLedgerValidationIssue],
) -> None:
    if set(entry) != _ENTRY_KEYS:
        _add_issue(issues, "transformation_ledger entry keys must match schema exactly", {"position": position, "keys": sorted(entry)})
    if entry.get("entry_id") != f"e_{position:06d}" or not _valid_entry_id(entry.get("entry_id")):
        _add_issue(issues, "transformation_ledger entry_id must be deterministic and contiguous", {"position": position})
    if entry.get("ordinal") != position:
        _add_issue(issues, "transformation_ledger ordinal must match entry position", {"position": position})


def _validate_entry_strings(
    entry: dict[str, Any],
    position: int,
    issues: list[TransformationLedgerValidationIssue],
) -> None:
    for field in ("stage", "operation", "producer"):
        if not _valid_nonempty_string(entry.get(field)):
            _add_issue(issues, f"transformation_ledger.{field} must be a non-empty string", {"position": position})
    if entry.get("producer") != "canonical_ir":
        _add_issue(issues, "transformation_ledger.producer must be canonical_ir", {"position": position})
    expected = _REQUIRED_OPERATIONS[position - 1] if position <= len(_REQUIRED_OPERATIONS) else ""
    if entry.get("operation") != expected:
        _add_issue(issues, "transformation_ledger operation order is invalid", {"position": position, "expected": expected})


def _validate_entry_lists(
    entry: dict[str, Any],
    position: int,
    run_dir: Path,
    issues: list[TransformationLedgerValidationIssue],
) -> None:
    for field in ("target_node_ids", "target_span_ids", "evidence_refs"):
        value = entry.get(field)
        if not _string_list(value):
            _add_issue(issues, f"transformation_ledger.{field} must be a list of strings", {"position": position})
    refs = entry.get("evidence_refs")
    if isinstance(refs, list):
        _validate_evidence_refs(run_dir, refs, position, issues)


def _validate_entry_details(
    entry: dict[str, Any],
    position: int,
    issues: list[TransformationLedgerValidationIssue],
) -> None:
    details = entry.get("details")
    if not isinstance(details, dict):
        _add_issue(issues, "transformation_ledger.details must be an object", {"position": position})
        return
    if entry.get("details_hash") != _stable_hash(details):
        _add_issue(issues, "transformation_ledger.details_hash must match details", {"position": position})


def _validate_evidence_refs(
    run_dir: Path,
    refs: list[object],
    position: int,
    issues: list[TransformationLedgerValidationIssue],
) -> None:
    for ref in refs:
        resolved = _resolve_run_reference(run_dir, ref, "evidence_refs", issues)
        if resolved is None:
            continue
        if not _is_relative_to(resolved, run_dir.resolve()):
            _add_issue(issues, "transformation_ledger.evidence_refs escapes the run directory", {"position": position, "ref": ref})


def _validate_run_reference(
    run_dir: Path,
    raw_value: object,
    expected_path: Path,
    field: str,
    issues: list[TransformationLedgerValidationIssue],
) -> None:
    resolved = _resolve_run_reference(run_dir, raw_value, field, issues)
    if resolved is not None and resolved != expected_path.resolve():
        _add_issue(issues, f"transformation_ledger.{field} must reference expected artifact", {"field": field, "value": raw_value})


def _resolve_run_reference(
    run_dir: Path,
    raw_value: object,
    field: str,
    issues: list[TransformationLedgerValidationIssue],
) -> Path | None:
    if not isinstance(raw_value, str) or not raw_value:
        _add_issue(issues, f"transformation_ledger.{field} must be a relative path string", {field: raw_value})
        return None
    rel_path = Path(raw_value)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        _add_issue(issues, f"transformation_ledger.{field} must stay inside the run directory", {field: raw_value})
        return None
    resolved = (run_dir / rel_path).resolve()
    if not _is_relative_to(resolved, run_dir.resolve()):
        _add_issue(issues, f"transformation_ledger.{field} escapes the run directory", {field: raw_value})
        return None
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _valid_entry_id(value: object) -> bool:
    return isinstance(value, str) and _ENTRY_ID_RE.match(value) is not None


def _valid_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _add_issue(
    issues: list[TransformationLedgerValidationIssue],
    message: str,
    evidence: dict[str, Any],
) -> None:
    issues.append(TransformationLedgerValidationIssue(
        code=TRANSFORMATION_LEDGER_INVALID_CODE,
        message=message,
        evidence=evidence,
    ))
