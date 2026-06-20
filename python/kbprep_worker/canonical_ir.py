"""Minimal Canonical IR manifest writer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json

CANONICAL_IR_MANIFEST_SCHEMA = "kbprep.canonical_ir_manifest.v1"
DOCUMENT_MANIFEST_SCHEMA = "kbprep.document_manifest.v1"


@dataclass(frozen=True)
class CanonicalIrValidationIssue:
    code: str
    message: str
    evidence: dict[str, Any]


def write_canonical_ir_manifests(
    *,
    run_dir: Path,
    input_path: Path,
    source_type: str,
    file_hash: str,
    file_size: int,
    run_id: str,
) -> dict[str, Path]:
    """Write the first partial Canonical IR manifest next to conversion artifacts."""
    conversion_report_path = run_dir / "conversion_report.json"
    converted_path = run_dir / "converted.md"
    diagnosis_report_path = run_dir / "diagnosis_report.json"
    conversion_report = _read_json(conversion_report_path)
    canonical_dir = run_dir / "canonical_ir"
    canonical_dir.mkdir(parents=True, exist_ok=True)

    canonical_manifest_path = canonical_dir / "manifest.json"
    document_manifest_path = run_dir / "document_manifest.json"
    route_decision = _dict_or_empty(conversion_report.get("route_decision"))
    canonical_manifest = {
        "schema": CANONICAL_IR_MANIFEST_SCHEMA,
        "document_id": _document_id(file_hash, input_path),
        "source_snapshot": _source_snapshot(input_path, file_hash, file_size, source_type),
        "conversion": _conversion_snapshot(conversion_report, route_decision),
        "artifacts": _artifact_snapshot(converted_path, conversion_report_path, diagnosis_report_path),
        "coverage": _coverage_snapshot(run_dir),
        "status": "partial",
    }
    _write_json(canonical_manifest_path, canonical_manifest)

    document_manifest = {
        "schema": DOCUMENT_MANIFEST_SCHEMA,
        "canonical_ir_manifest": _relative_run_path(run_dir, canonical_manifest_path),
        "conversion_report": _relative_run_path(run_dir, conversion_report_path),
        "converted_md": _relative_run_path(run_dir, converted_path),
        "created_from_run": run_id,
    }
    _write_json(document_manifest_path, document_manifest)
    return {
        "canonical_ir_manifest": canonical_manifest_path,
        "document_manifest": document_manifest_path,
    }


def validate_canonical_ir_manifests(
    run_dir: Path,
    *,
    converted_path: Path | None = None,
) -> list[CanonicalIrValidationIssue]:
    """Validate the partial Canonical IR manifest contract for conversion gate use."""
    run_p = Path(run_dir)
    canonical_path = run_p / "canonical_ir" / "manifest.json"
    document_path = run_p / "document_manifest.json"
    issues: list[CanonicalIrValidationIssue] = []
    canonical_manifest = _read_required_manifest(
        canonical_path,
        missing_code="E_CANONICAL_IR_MANIFEST_MISSING",
        invalid_code="E_CANONICAL_IR_MANIFEST_INVALID",
        label="canonical_ir/manifest.json",
        issues=issues,
    )
    document_manifest = _read_required_manifest(
        document_path,
        missing_code="E_DOCUMENT_MANIFEST_MISSING",
        invalid_code="E_DOCUMENT_MANIFEST_INVALID",
        label="document_manifest.json",
        issues=issues,
    )
    if canonical_manifest is not None:
        _validate_canonical_manifest(run_p, canonical_manifest, converted_path, issues)
    if document_manifest is not None:
        _validate_document_manifest(run_p, document_manifest, canonical_path, converted_path, issues)
    return issues


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload, indent=2, trailing_newline=False)


def _read_required_manifest(
    path: Path,
    *,
    missing_code: str,
    invalid_code: str,
    label: str,
    issues: list[CanonicalIrValidationIssue],
) -> dict[str, Any] | None:
    if not path.exists():
        _add_issue(issues, missing_code, f"{label} is missing", {label: str(path)})
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _add_issue(issues, invalid_code, f"{label} is not readable JSON", {label: str(path), "error": str(exc)})
        return None
    if not isinstance(data, dict):
        _add_issue(issues, invalid_code, f"{label} must be a JSON object", {label: str(path)})
        return None
    return data


def _dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _document_id(file_hash: str, input_path: Path) -> str:
    if file_hash:
        return f"doc_{file_hash[:16]}"
    fallback = hashlib.sha256(str(input_path).encode("utf-8")).hexdigest()
    return f"doc_{fallback[:16]}"


def _source_snapshot(input_path: Path, file_hash: str, file_size: int, source_type: str) -> dict[str, Any]:
    return {
        "input_path": str(input_path),
        "input_name": input_path.name,
        "input_sha256": file_hash,
        "input_size": file_size,
        "source_type": source_type,
    }


def _conversion_snapshot(
    conversion_report: dict[str, Any],
    route_decision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "converter": conversion_report.get("converter"),
        "actual_route": route_decision.get("actual_route"),
        "route_decision": route_decision,
        "route_decision_hash": _stable_hash(route_decision),
    }


def _artifact_snapshot(
    converted_path: Path,
    conversion_report_path: Path,
    diagnosis_report_path: Path,
) -> dict[str, str]:
    run_dir = conversion_report_path.parent
    return {
        "converted_md": _relative_run_path(run_dir, converted_path),
        "conversion_report": _relative_run_path(run_dir, conversion_report_path),
        "diagnosis_report": _relative_run_path(run_dir, diagnosis_report_path),
    }


def _coverage_snapshot(run_dir: Path) -> dict[str, bool]:
    return {
        "typed_nodes_available": False,
        "source_spans_available": False,
        "assets_available": (run_dir / "images").exists(),
    }


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _validate_canonical_manifest(
    run_dir: Path,
    manifest: dict[str, Any],
    converted_path: Path | None,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    _require_schema(manifest, CANONICAL_IR_MANIFEST_SCHEMA, "E_CANONICAL_IR_MANIFEST_INVALID", issues)
    _require_nonempty_string(manifest, "document_id", "E_CANONICAL_IR_MANIFEST_INVALID", issues)
    _validate_source_snapshot(manifest.get("source_snapshot"), issues)
    _validate_conversion_snapshot(manifest.get("conversion"), issues)
    _validate_artifact_snapshot(run_dir, manifest.get("artifacts"), converted_path, issues)
    _validate_coverage_snapshot(manifest.get("coverage"), issues)
    if manifest.get("status") != "partial":
        _add_issue(
            issues,
            "E_CANONICAL_IR_MANIFEST_INVALID",
            "canonical_ir/manifest.json status must be partial for this slice",
            {"status": manifest.get("status")},
        )


def _validate_document_manifest(
    run_dir: Path,
    manifest: dict[str, Any],
    canonical_path: Path,
    converted_path: Path | None,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    _require_schema(manifest, DOCUMENT_MANIFEST_SCHEMA, "E_DOCUMENT_MANIFEST_INVALID", issues)
    _validate_run_reference(
        run_dir, manifest.get("canonical_ir_manifest"), canonical_path, "canonical_ir_manifest",
        "E_DOCUMENT_MANIFEST_INVALID", issues,
    )
    _validate_run_reference(
        run_dir, manifest.get("conversion_report"), run_dir / "conversion_report.json", "conversion_report",
        "E_DOCUMENT_MANIFEST_INVALID", issues,
    )
    if converted_path is not None:
        _validate_run_reference(
            run_dir, manifest.get("converted_md"), converted_path, "converted_md",
            "E_DOCUMENT_MANIFEST_INVALID", issues,
        )
    _require_nonempty_string(manifest, "created_from_run", "E_DOCUMENT_MANIFEST_INVALID", issues)


def _validate_source_snapshot(value: object, issues: list[CanonicalIrValidationIssue]) -> None:
    snapshot = _require_mapping(value, "source_snapshot", "E_CANONICAL_IR_MANIFEST_INVALID", issues)
    if snapshot is None:
        return
    for field in ("input_path", "input_name", "input_sha256", "source_type"):
        _require_nonempty_string(snapshot, field, "E_CANONICAL_IR_MANIFEST_INVALID", issues, "source_snapshot")
    input_size = snapshot.get("input_size")
    if not isinstance(input_size, int) or input_size < 0:
        _add_issue(
            issues,
            "E_CANONICAL_IR_MANIFEST_INVALID",
            "canonical_ir/manifest.json source_snapshot.input_size must be a non-negative integer",
            {"input_size": input_size},
        )


def _validate_conversion_snapshot(value: object, issues: list[CanonicalIrValidationIssue]) -> None:
    conversion = _require_mapping(value, "conversion", "E_CANONICAL_IR_MANIFEST_INVALID", issues)
    if conversion is None:
        return
    for field in ("converter", "actual_route", "route_decision_hash"):
        _require_nonempty_string(conversion, field, "E_CANONICAL_IR_MANIFEST_INVALID", issues, "conversion")


def _validate_artifact_snapshot(
    run_dir: Path,
    value: object,
    converted_path: Path | None,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    artifacts = _require_mapping(value, "artifacts", "E_CANONICAL_IR_MANIFEST_INVALID", issues)
    if artifacts is None:
        return
    expected = {
        "conversion_report": run_dir / "conversion_report.json",
        "diagnosis_report": run_dir / "diagnosis_report.json",
    }
    if converted_path is not None:
        expected["converted_md"] = converted_path
    for field, path in expected.items():
        _validate_run_reference(run_dir, artifacts.get(field), path, field, "E_CANONICAL_IR_MANIFEST_INVALID", issues)


def _validate_coverage_snapshot(value: object, issues: list[CanonicalIrValidationIssue]) -> None:
    coverage = _require_mapping(value, "coverage", "E_CANONICAL_IR_MANIFEST_INVALID", issues)
    if coverage is None:
        return
    for field in ("typed_nodes_available", "source_spans_available", "assets_available"):
        if not isinstance(coverage.get(field), bool):
            _add_issue(
                issues,
                "E_CANONICAL_IR_MANIFEST_INVALID",
                f"canonical_ir/manifest.json coverage.{field} must be boolean",
                {field: coverage.get(field)},
            )


def _require_schema(
    manifest: dict[str, Any],
    expected: str,
    code: str,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    if manifest.get("schema") != expected:
        _add_issue(issues, code, f"manifest schema must be {expected}", {"schema": manifest.get("schema")})


def _require_mapping(
    value: object,
    field: str,
    code: str,
    issues: list[CanonicalIrValidationIssue],
) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    _add_issue(issues, code, f"canonical_ir/manifest.json missing {field}", {field: value})
    return None


def _require_nonempty_string(
    manifest: dict[str, Any],
    field: str,
    code: str,
    issues: list[CanonicalIrValidationIssue],
    prefix: str | None = None,
) -> None:
    value = manifest.get(field)
    if isinstance(value, str) and value:
        return
    display = f"{prefix}.{field}" if prefix else field
    _add_issue(issues, code, f"manifest field {display} must be a non-empty string", {display: value})


def _validate_run_reference(
    run_dir: Path,
    raw_value: object,
    expected_path: Path,
    field: str,
    code: str,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    resolved = _resolve_run_reference(run_dir, raw_value, field, code, issues)
    if resolved is None:
        return
    expected = expected_path.resolve()
    if resolved != expected:
        _add_issue(
            issues,
            code,
            f"manifest field {field} must reference {_relative_run_path(run_dir, expected_path)}",
            {field: raw_value, "expected": _relative_run_path(run_dir, expected_path)},
        )
    if not resolved.exists():
        _add_issue(issues, code, f"manifest field {field} points to a missing file", {field: raw_value})


def _resolve_run_reference(
    run_dir: Path,
    raw_value: object,
    field: str,
    code: str,
    issues: list[CanonicalIrValidationIssue],
) -> Path | None:
    if not isinstance(raw_value, str) or not raw_value:
        _add_issue(issues, code, f"manifest field {field} must be a relative path string", {field: raw_value})
        return None
    rel_path = Path(raw_value)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        _add_issue(issues, code, f"manifest field {field} must stay inside the run directory", {field: raw_value})
        return None
    resolved = (run_dir / rel_path).resolve()
    if not _is_relative_to(resolved, run_dir.resolve()):
        _add_issue(issues, code, f"manifest field {field} escapes the run directory", {field: raw_value})
        return None
    return resolved


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


def _add_issue(
    issues: list[CanonicalIrValidationIssue],
    code: str,
    message: str,
    evidence: dict[str, Any],
) -> None:
    issues.append(CanonicalIrValidationIssue(code=code, message=message, evidence=evidence))
