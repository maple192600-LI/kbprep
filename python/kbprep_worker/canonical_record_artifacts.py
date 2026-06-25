"""Canonical IR record artifact reference validators."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CANONICAL_IR_RELATIONSHIPS_SCHEMA = "kbprep.canonical_ir_relationships.v1"
CANONICAL_IR_ASSETS_SCHEMA = "kbprep.canonical_ir_assets.v1"
CANONICAL_IR_ANNOTATIONS_SCHEMA = "kbprep.canonical_ir_annotations.v1"
RECORD_ARTIFACT_INVALID_CODE = "E_CANONICAL_IR_MANIFEST_INVALID"
RELATIONSHIP_RECORD_KEYS = frozenset({"relationship_id", "type", "source_node_id", "target_node_id", "evidence"})
ASSET_RECORD_KEYS = frozenset({"asset_id", "asset_type", "source_node_id", "reference", "reference_kind"})
ANNOTATION_RECORD_KEYS = frozenset({"annotation_id", "kind", "severity", "target", "message_code", "evidence"})
RELATIONSHIP_TOP_KEYS = frozenset({
    "schema",
    "document_id",
    "typed_nodes_artifact",
    "relationship_count",
    "relationships",
})
ASSET_TOP_KEYS = frozenset({"schema", "document_id", "typed_nodes_artifact", "asset_count", "assets"})
ANNOTATION_TOP_KEYS = frozenset({"schema", "document_id", "annotation_count", "annotations"})
EVIDENCE_KEYS = frozenset({"basis"})

_RECORD_ARTIFACT_CONTRACTS = {
    "relationships": (
        "relationships_available",
        CANONICAL_IR_RELATIONSHIPS_SCHEMA,
        "relationship_count",
        "relationships",
        RELATIONSHIP_RECORD_KEYS,
        RELATIONSHIP_TOP_KEYS,
        EVIDENCE_KEYS,
    ),
    "assets": (
        "assets_available",
        CANONICAL_IR_ASSETS_SCHEMA,
        "asset_count",
        "assets",
        ASSET_RECORD_KEYS,
        ASSET_TOP_KEYS,
        frozenset(),
    ),
    "annotations": (
        "annotations_available",
        CANONICAL_IR_ANNOTATIONS_SCHEMA,
        "annotation_count",
        "annotations",
        ANNOTATION_RECORD_KEYS,
        ANNOTATION_TOP_KEYS,
        EVIDENCE_KEYS,
    ),
}


@dataclass(frozen=True)
class RecordArtifactValidationIssue:
    code: str
    message: str
    evidence: dict[str, Any]


def validate_record_artifact_references(
    *,
    run_dir: Path,
    artifacts: dict[str, Any],
    coverage: dict[str, Any],
    document_id: str,
) -> list[RecordArtifactValidationIssue]:
    issues: list[RecordArtifactValidationIssue] = []
    for artifact_field, contract in _RECORD_ARTIFACT_CONTRACTS.items():
        _validate_record_artifact_reference(
            run_dir=run_dir,
            artifacts=artifacts,
            coverage=coverage,
            document_id=document_id,
            artifact_field=artifact_field,
            contract=contract,
            issues=issues,
        )
    return issues


def valid_record_artifact_payload(
    payload: dict[str, Any] | None,
    schema: str,
    count_field: str,
    list_field: str,
    record_keys: frozenset[str],
    top_keys: frozenset[str],
    evidence_keys: frozenset[str],
) -> bool:
    if payload is None or payload.get("schema") != schema:
        return False
    if frozenset(payload) != top_keys:
        return False
    records = payload.get(list_field)
    if not isinstance(records, list):
        return False
    count = payload.get(count_field)
    if not isinstance(count, int) or isinstance(count, bool) or count != len(records):
        return False
    return all(_valid_record_payload(record, record_keys, evidence_keys) for record in records)


def _validate_record_artifact_reference(
    *,
    run_dir: Path,
    artifacts: dict[str, Any],
    coverage: dict[str, Any],
    document_id: str,
    artifact_field: str,
    contract: tuple[str, str, str, str, frozenset[str], frozenset[str], frozenset[str]],
    issues: list[RecordArtifactValidationIssue],
) -> None:
    coverage_field, schema, count_field, list_field, record_keys, top_keys, evidence_keys = contract
    raw_ref = artifacts.get(artifact_field)
    if raw_ref is None:
        _validate_missing_artifact(coverage, coverage_field, artifact_field, issues)
        return
    resolved = _resolve_artifact_reference(run_dir, raw_ref, artifact_field, issues)
    if resolved is None:
        return
    payload = _read_required_record_artifact(run_dir, resolved, artifact_field, issues)
    if payload is None:
        return
    record_count = _validate_record_artifact_payload(
        payload, document_id, artifact_field, schema, count_field, list_field, record_keys, top_keys, evidence_keys, issues,
    )
    _validate_coverage_available(coverage, coverage_field, artifact_field, record_count, issues)


def _validate_missing_artifact(
    coverage: dict[str, Any],
    coverage_field: str,
    artifact_field: str,
    issues: list[RecordArtifactValidationIssue],
) -> None:
    if coverage.get(coverage_field) is True:
        _add_issue(
            issues,
            f"coverage.{coverage_field} requires artifacts.{artifact_field}",
            {coverage_field: coverage.get(coverage_field)},
        )


def _resolve_artifact_reference(
    run_dir: Path,
    raw_ref: object,
    artifact_field: str,
    issues: list[RecordArtifactValidationIssue],
) -> Path | None:
    if not isinstance(raw_ref, str) or not raw_ref:
        _add_issue(issues, f"manifest field {artifact_field} must be a relative path string", {artifact_field: raw_ref})
        return None
    rel_path = Path(raw_ref)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        _add_issue(issues, f"manifest field {artifact_field} must stay inside the run directory", {artifact_field: raw_ref})
        return None
    resolved = (run_dir / rel_path).resolve()
    if not _is_relative_to(resolved, run_dir.resolve()):
        _add_issue(issues, f"manifest field {artifact_field} escapes the run directory", {artifact_field: raw_ref})
        return None
    expected = (run_dir / "canonical_ir" / f"{artifact_field}.json").resolve()
    if resolved != expected:
        _add_issue(
            issues,
            f"artifacts.{artifact_field} must reference canonical_ir/{artifact_field}.json",
            {artifact_field: raw_ref, "expected": f"canonical_ir/{artifact_field}.json"},
        )
        return None
    return resolved


def _read_required_record_artifact(
    run_dir: Path,
    path: Path,
    artifact_field: str,
    issues: list[RecordArtifactValidationIssue],
) -> dict[str, Any] | None:
    if not path.exists():
        _add_issue(issues, f"artifacts.{artifact_field} points to a missing file", {artifact_field: _relative_run_path(run_dir, path)})
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _add_issue(issues, f"artifacts.{artifact_field} must be valid JSON", {"error": str(exc)})
        return None
    if not isinstance(payload, dict):
        _add_issue(issues, f"artifacts.{artifact_field} must be a JSON object", {artifact_field: payload})
        return None
    return payload


def _validate_record_artifact_payload(
    payload: dict[str, Any],
    document_id: str,
    artifact_field: str,
    schema: str,
    count_field: str,
    list_field: str,
    record_keys: frozenset[str],
    top_keys: frozenset[str],
    evidence_keys: frozenset[str],
    issues: list[RecordArtifactValidationIssue],
) -> int:
    if frozenset(payload) != top_keys:
        _add_issue(
            issues,
            f"{artifact_field} top-level keys must match schema exactly",
            {"keys": sorted(payload), "expected": sorted(top_keys)},
        )
    if payload.get("schema") != schema:
        _add_issue(issues, f"{artifact_field} schema is invalid", {"schema": payload.get("schema")})
    if payload.get("document_id") != document_id:
        _add_issue(
            issues,
            f"{artifact_field}.document_id must match canonical manifest",
            {"document_id": payload.get("document_id"), "expected": document_id},
        )
    records = payload.get(list_field)
    if not isinstance(records, list):
        _add_issue(issues, f"{artifact_field}.{list_field} must be a list", {list_field: records})
        return 0
    count = payload.get(count_field)
    if not isinstance(count, int) or isinstance(count, bool) or count != len(records):
        _add_issue(issues, f"{artifact_field}.{count_field} must equal len({list_field})", {count_field: count, "actual": len(records)})
    for index, record in enumerate(records):
        _validate_record_payload(record, artifact_field, index, record_keys, evidence_keys, issues)
    return len(records)


def _valid_record_payload(record: object, record_keys: frozenset[str], evidence_keys: frozenset[str]) -> bool:
    if not isinstance(record, dict) or frozenset(record) != record_keys:
        return False
    evidence = record.get("evidence")
    if "evidence" in record_keys and not _valid_evidence_payload(evidence, evidence_keys):
        return False
    return True


def _validate_record_payload(
    record: object,
    artifact_field: str,
    index: int,
    record_keys: frozenset[str],
    evidence_keys: frozenset[str],
    issues: list[RecordArtifactValidationIssue],
) -> None:
    if not isinstance(record, dict):
        _add_issue(issues, f"{artifact_field} record must be an object", {"position": index})
        return
    if frozenset(record) != record_keys:
        _add_issue(issues, f"{artifact_field} record keys must match schema exactly", {"position": index, "keys": sorted(record)})
    for key, value in record.items():
        if key == "evidence" and not isinstance(value, dict):
            _add_issue(issues, f"{artifact_field} record evidence must be an object", {"position": index})
        elif key == "evidence":
            _validate_evidence_payload(value, evidence_keys, artifact_field, index, issues)
        elif key != "evidence" and (not isinstance(value, str) or not value):
            _add_issue(issues, f"{artifact_field} record field {key} must be a non-empty string", {"position": index, key: value})


def _valid_evidence_payload(evidence: object, evidence_keys: frozenset[str]) -> bool:
    if not isinstance(evidence, dict) or frozenset(evidence) != evidence_keys:
        return False
    return all(isinstance(value, str) and bool(value) for value in evidence.values())


def _validate_evidence_payload(
    evidence: dict[str, Any],
    evidence_keys: frozenset[str],
    artifact_field: str,
    index: int,
    issues: list[RecordArtifactValidationIssue],
) -> None:
    if frozenset(evidence) != evidence_keys:
        _add_issue(
            issues,
            f"{artifact_field} record evidence keys must match schema exactly",
            {"position": index, "keys": sorted(evidence), "expected": sorted(evidence_keys)},
        )
    for key, value in evidence.items():
        if not isinstance(value, str) or not value:
            _add_issue(issues, f"{artifact_field} record evidence field {key} must be a non-empty string", {"position": index})


def _validate_coverage_available(
    coverage: dict[str, Any],
    coverage_field: str,
    artifact_field: str,
    record_count: int,
    issues: list[RecordArtifactValidationIssue],
) -> None:
    expected_available = record_count > 0
    if coverage.get(coverage_field) != expected_available:
        _add_issue(
            issues,
            f"coverage.{coverage_field} must match {artifact_field} record availability",
            {coverage_field: coverage.get(coverage_field), "record_count": record_count},
        )


def _relative_run_path(run_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _add_issue(issues: list[RecordArtifactValidationIssue], message: str, evidence: dict[str, Any]) -> None:
    issues.append(RecordArtifactValidationIssue(code=RECORD_ARTIFACT_INVALID_CODE, message=message, evidence=evidence))
