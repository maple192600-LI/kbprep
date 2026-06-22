"""Minimal Canonical IR manifest writer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .canonical_nodes import (
    CANONICAL_IR_TYPED_NODES_SCHEMA,
    SUPPORTED_NODE_TYPES,
    TYPED_NODE_KEYS,
    write_typed_nodes_artifact,
)
from .canonical_routes import canonical_conversion_route, canonical_converter, dict_or_empty
from .canonical_spans import (
    validate_source_spans_artifact,
    validate_source_spans_reference,
    write_source_spans_artifact,
)

CANONICAL_IR_MANIFEST_SCHEMA = "kbprep.canonical_ir_manifest.v1"
DOCUMENT_MANIFEST_SCHEMA = "kbprep.document_manifest.v1"
TYPED_NODES_INVALID_CODE = "E_CANONICAL_IR_TYPED_NODES_INVALID"


@dataclass(frozen=True)
class CanonicalIrValidationIssue:
    code: str
    message: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class CanonicalArtifactState:
    document_id: str
    route_decision: dict[str, Any]
    typed_nodes_path: Path
    typed_nodes_available: bool
    source_spans_path: Path
    source_spans_available: bool


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
    conversion_report = _read_json(conversion_report_path)
    canonical_dir = run_dir / "canonical_ir"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    canonical_manifest_path = canonical_dir / "manifest.json"
    document_manifest_path = run_dir / "document_manifest.json"
    artifact_state = _write_canonical_artifacts(
        run_dir=run_dir,
        input_path=input_path,
        source_type=source_type,
        file_hash=file_hash,
        converted_path=converted_path,
        conversion_report=conversion_report,
    )
    canonical_manifest = _canonical_manifest_payload(
        run_dir=run_dir,
        input_path=input_path,
        source_type=source_type,
        file_hash=file_hash,
        file_size=file_size,
        document_id=artifact_state.document_id,
        conversion_report=conversion_report,
        route_decision=artifact_state.route_decision,
        typed_nodes_path=artifact_state.typed_nodes_path,
        typed_nodes_available=artifact_state.typed_nodes_available,
        source_spans_path=artifact_state.source_spans_path,
        source_spans_available=artifact_state.source_spans_available,
    )
    _write_json(canonical_manifest_path, canonical_manifest)

    _write_json(document_manifest_path, _document_manifest_payload(
        run_dir=run_dir,
        canonical_manifest_path=canonical_manifest_path,
        conversion_report_path=conversion_report_path,
        converted_path=converted_path,
        run_id=run_id,
    ))
    return {"canonical_ir_manifest": canonical_manifest_path, "document_manifest": document_manifest_path}


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


def _write_canonical_artifacts(
    *,
    run_dir: Path,
    input_path: Path,
    source_type: str,
    file_hash: str,
    converted_path: Path,
    conversion_report: dict[str, Any],
) -> CanonicalArtifactState:
    route_decision = dict_or_empty(conversion_report.get("route_decision"))
    document_id = _document_id(file_hash, input_path)
    converter = canonical_converter(conversion_report, route_decision)
    conversion_route = canonical_conversion_route(conversion_report, route_decision)
    typed_path, typed_available = _write_validated_typed_nodes(
        run_dir, document_id, input_path, converted_path, source_type, conversion_route,
    )
    spans_path, spans_available = _write_validated_source_spans(
        run_dir, document_id, input_path, converted_path, typed_path, source_type,
        converter, conversion_route,
    )
    return CanonicalArtifactState(
        document_id=document_id,
        route_decision=route_decision,
        typed_nodes_path=typed_path,
        typed_nodes_available=typed_available,
        source_spans_path=spans_path,
        source_spans_available=spans_available,
    )


def _write_validated_typed_nodes(
    run_dir: Path,
    document_id: str,
    input_path: Path,
    converted_path: Path,
    source_type: str,
    conversion_route: str,
) -> tuple[Path, bool]:
    typed_nodes_path = write_typed_nodes_artifact(
        run_dir=run_dir,
        document_id=document_id,
        converted_path=converted_path,
        source_type=source_type,
        conversion_route=conversion_route,
        input_path=input_path,
    )
    typed_nodes_available = _typed_nodes_artifact_is_valid(
        run_dir=run_dir,
        typed_nodes_path=typed_nodes_path,
        document_id=document_id,
        converted_path=converted_path,
    )
    return typed_nodes_path, typed_nodes_available


def _write_validated_source_spans(
    run_dir: Path,
    document_id: str,
    input_path: Path,
    converted_path: Path,
    typed_nodes_path: Path,
    source_type: str,
    converter: str,
    conversion_route: str,
) -> tuple[Path, bool]:
    source_spans_path = write_source_spans_artifact(
        run_dir=run_dir,
        document_id=document_id,
        input_path=input_path,
        converted_path=converted_path,
        typed_nodes_path=typed_nodes_path,
        source_type=source_type,
        converter=converter,
        conversion_route=conversion_route,
    )
    source_spans_available = _source_spans_artifact_is_valid(
        run_dir=run_dir,
        source_spans_path=source_spans_path,
        typed_nodes_path=typed_nodes_path,
        document_id=document_id,
        converted_path=converted_path,
    )
    return source_spans_path, source_spans_available


def _canonical_manifest_payload(
    *,
    run_dir: Path,
    input_path: Path,
    source_type: str,
    file_hash: str,
    file_size: int,
    document_id: str,
    conversion_report: dict[str, Any],
    route_decision: dict[str, Any],
    typed_nodes_path: Path,
    typed_nodes_available: bool,
    source_spans_path: Path,
    source_spans_available: bool,
) -> dict[str, Any]:
    conversion_report_path = run_dir / "conversion_report.json"
    diagnosis_report_path = run_dir / "diagnosis_report.json"
    converted_path = run_dir / "converted.md"
    return {
        "schema": CANONICAL_IR_MANIFEST_SCHEMA,
        "document_id": document_id,
        "source_snapshot": _source_snapshot(input_path, file_hash, file_size, source_type),
        "conversion": _conversion_snapshot(conversion_report, route_decision),
        "artifacts": _artifact_snapshot(
            converted_path,
            conversion_report_path,
            diagnosis_report_path,
            typed_nodes_path,
            source_spans_path,
        ),
        "coverage": _coverage_snapshot(
            run_dir,
            typed_nodes_available=typed_nodes_available,
            source_spans_available=source_spans_available,
        ),
        "status": "partial",
    }


def _document_manifest_payload(
    *,
    run_dir: Path,
    canonical_manifest_path: Path,
    conversion_report_path: Path,
    converted_path: Path,
    run_id: str,
) -> dict[str, str]:
    return {
        "schema": DOCUMENT_MANIFEST_SCHEMA,
        "canonical_ir_manifest": _relative_run_path(run_dir, canonical_manifest_path),
        "conversion_report": _relative_run_path(run_dir, conversion_report_path),
        "converted_md": _relative_run_path(run_dir, converted_path),
        "created_from_run": run_id,
    }


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
        "converter": canonical_converter(conversion_report, route_decision),
        "actual_route": canonical_conversion_route(conversion_report, route_decision),
        "route_decision": route_decision,
        "route_decision_hash": _stable_hash(route_decision),
    }


def _artifact_snapshot(
    converted_path: Path,
    conversion_report_path: Path,
    diagnosis_report_path: Path,
    typed_nodes_path: Path,
    source_spans_path: Path,
) -> dict[str, str]:
    run_dir = conversion_report_path.parent
    return {
        "converted_md": _relative_run_path(run_dir, converted_path),
        "conversion_report": _relative_run_path(run_dir, conversion_report_path),
        "diagnosis_report": _relative_run_path(run_dir, diagnosis_report_path),
        "typed_nodes": _relative_run_path(run_dir, typed_nodes_path),
        "source_spans": _relative_run_path(run_dir, source_spans_path),
    }


def _coverage_snapshot(
    run_dir: Path,
    *,
    typed_nodes_available: bool,
    source_spans_available: bool,
) -> dict[str, bool]:
    return {
        "typed_nodes_available": typed_nodes_available,
        "source_spans_available": source_spans_available,
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
    artifacts = _validate_artifact_snapshot(run_dir, manifest.get("artifacts"), converted_path, issues)
    coverage = _validate_coverage_snapshot(manifest.get("coverage"), issues)
    if artifacts is not None and coverage is not None:
        converted = converted_path or run_dir / "converted.md"
        _validate_typed_nodes_reference(
            run_dir,
            artifacts,
            coverage,
            str(manifest.get("document_id") or ""),
            converted,
            issues,
        )
        for issue in validate_source_spans_reference(
            run_dir=run_dir,
            artifacts=artifacts,
            coverage=coverage,
            document_id=str(manifest.get("document_id") or ""),
            converted_path=converted,
        ):
            _add_issue(issues, issue.code, issue.message, issue.evidence)
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
) -> dict[str, Any] | None:
    artifacts = _require_mapping(value, "artifacts", "E_CANONICAL_IR_MANIFEST_INVALID", issues)
    if artifacts is None:
        return None
    expected = {
        "conversion_report": run_dir / "conversion_report.json",
        "diagnosis_report": run_dir / "diagnosis_report.json",
    }
    if converted_path is not None:
        expected["converted_md"] = converted_path
    for field, path in expected.items():
        _validate_run_reference(run_dir, artifacts.get(field), path, field, "E_CANONICAL_IR_MANIFEST_INVALID", issues)
    return artifacts


def _validate_coverage_snapshot(value: object, issues: list[CanonicalIrValidationIssue]) -> dict[str, Any] | None:
    coverage = _require_mapping(value, "coverage", "E_CANONICAL_IR_MANIFEST_INVALID", issues)
    if coverage is None:
        return None
    for field in ("typed_nodes_available", "source_spans_available", "assets_available"):
        if not isinstance(coverage.get(field), bool):
            _add_issue(
                issues,
                "E_CANONICAL_IR_MANIFEST_INVALID",
                f"canonical_ir/manifest.json coverage.{field} must be boolean",
                {field: coverage.get(field)},
            )
    return coverage


def _typed_nodes_artifact_is_valid(
    *,
    run_dir: Path,
    typed_nodes_path: Path,
    document_id: str,
    converted_path: Path,
) -> bool:
    issues: list[CanonicalIrValidationIssue] = []
    _validate_typed_nodes_artifact(run_dir, typed_nodes_path, document_id, converted_path, issues)
    return not issues


def _source_spans_artifact_is_valid(
    *,
    run_dir: Path,
    source_spans_path: Path,
    typed_nodes_path: Path,
    document_id: str,
    converted_path: Path,
) -> bool:
    issues = validate_source_spans_artifact(
        run_dir=run_dir,
        source_spans_path=source_spans_path,
        typed_nodes_path=typed_nodes_path,
        document_id=document_id,
        converted_path=converted_path,
    )
    return not issues


def _validate_typed_nodes_reference(
    run_dir: Path,
    artifacts: dict[str, Any],
    coverage: dict[str, Any],
    document_id: str,
    converted_path: Path,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    raw_ref = artifacts.get("typed_nodes")
    if raw_ref is None:
        if coverage.get("typed_nodes_available") is True:
            _add_issue(
                issues,
                "E_CANONICAL_IR_MANIFEST_INVALID",
                "coverage.typed_nodes_available requires artifacts.typed_nodes",
                {"typed_nodes_available": coverage.get("typed_nodes_available")},
            )
        return
    resolved = _resolve_run_reference(run_dir, raw_ref, "typed_nodes", "E_CANONICAL_IR_MANIFEST_INVALID", issues)
    if resolved is None:
        return
    expected = run_dir / "canonical_ir" / "typed_nodes.json"
    if resolved != expected.resolve():
        _add_issue(
            issues,
            "E_CANONICAL_IR_MANIFEST_INVALID",
            "artifacts.typed_nodes must reference canonical_ir/typed_nodes.json",
            {"typed_nodes": raw_ref, "expected": "canonical_ir/typed_nodes.json"},
        )
    if coverage.get("typed_nodes_available") is not True:
        _add_issue(
            issues,
            "E_CANONICAL_IR_MANIFEST_INVALID",
            "coverage.typed_nodes_available must be true when artifacts.typed_nodes exists",
            {"typed_nodes_available": coverage.get("typed_nodes_available")},
        )
    _validate_typed_nodes_artifact(run_dir, resolved, document_id, converted_path, issues)


def _validate_typed_nodes_artifact(
    run_dir: Path,
    typed_nodes_path: Path,
    document_id: str,
    converted_path: Path,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    payload = _read_required_manifest(
        typed_nodes_path,
        missing_code=TYPED_NODES_INVALID_CODE,
        invalid_code=TYPED_NODES_INVALID_CODE,
        label="canonical_ir/typed_nodes.json",
        issues=issues,
    )
    if payload is None:
        return
    _validate_typed_nodes_header(run_dir, payload, document_id, converted_path, issues)
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        _add_issue(issues, TYPED_NODES_INVALID_CODE, "typed_nodes.nodes must be a list", {"nodes": nodes})
        return
    _validate_typed_nodes_count(payload.get("node_count"), len(nodes), issues)
    for position, node in enumerate(nodes, start=1):
        _validate_typed_node(node, position, issues)


def _validate_typed_nodes_header(
    run_dir: Path,
    payload: dict[str, Any],
    document_id: str,
    converted_path: Path,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    if payload.get("schema") != CANONICAL_IR_TYPED_NODES_SCHEMA:
        _add_issue(issues, TYPED_NODES_INVALID_CODE, "typed_nodes schema is invalid", {"schema": payload.get("schema")})
    if payload.get("document_id") != document_id:
        _add_issue(
            issues,
            TYPED_NODES_INVALID_CODE,
            "typed_nodes.document_id must match canonical manifest",
            {"document_id": payload.get("document_id"), "expected": document_id},
        )
    _validate_typed_nodes_source_artifact(run_dir, payload.get("source_artifact"), converted_path, issues)


def _validate_typed_nodes_count(
    node_count: object,
    actual_count: int,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    if not isinstance(node_count, int) or isinstance(node_count, bool) or node_count < 0:
        _add_issue(
            issues,
            TYPED_NODES_INVALID_CODE,
            "typed_nodes.node_count must be a non-negative integer",
            {"node_count": node_count},
        )
        return
    if node_count != actual_count:
        _add_issue(
            issues,
            TYPED_NODES_INVALID_CODE,
            "typed_nodes.node_count must equal len(nodes)",
            {"node_count": node_count, "actual_count": actual_count},
        )


def _validate_typed_nodes_source_artifact(
    run_dir: Path,
    raw_value: object,
    converted_path: Path,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    resolved = _resolve_run_reference(run_dir, raw_value, "source_artifact", TYPED_NODES_INVALID_CODE, issues)
    if resolved is None:
        return
    expected_source = run_dir / "converted.md"
    if resolved != expected_source.resolve():
        _add_issue(
            issues,
            TYPED_NODES_INVALID_CODE,
            "typed_nodes.source_artifact must reference converted.md",
            {"source_artifact": raw_value, "expected": _relative_run_path(run_dir, expected_source)},
        )
    if resolved != converted_path.resolve():
        _add_issue(
            issues,
            TYPED_NODES_INVALID_CODE,
            "typed_nodes.source_artifact must match the validated converted artifact",
            {"source_artifact": raw_value, "converted_path": _relative_run_path(run_dir, converted_path)},
        )


def _validate_typed_node(
    node: object,
    position: int,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    if not isinstance(node, dict):
        _add_issue(issues, TYPED_NODES_INVALID_CODE, "typed_nodes node must be an object", {"position": position})
        return
    if set(node) != TYPED_NODE_KEYS:
        _add_issue(
            issues,
            TYPED_NODES_INVALID_CODE,
            "typed_nodes node keys must match C1 schema exactly",
            {"position": position, "keys": sorted(node)},
        )
    _validate_typed_node_identity(node, position, issues)
    if node.get("type") not in SUPPORTED_NODE_TYPES:
        _add_issue(issues, TYPED_NODES_INVALID_CODE, "typed_nodes node type is unsupported", {"type": node.get("type")})
    if not isinstance(node.get("text"), str) or not node.get("text", "").strip():
        _add_issue(issues, TYPED_NODES_INVALID_CODE, "typed_nodes node text must be non-empty", {"position": position})
    if not isinstance(node.get("metadata"), dict):
        _add_issue(issues, TYPED_NODES_INVALID_CODE, "typed_nodes node metadata must be an object", {"position": position})


def _validate_typed_node_identity(
    node: dict[str, Any],
    position: int,
    issues: list[CanonicalIrValidationIssue],
) -> None:
    expected_id = f"n_{position:06d}"
    if node.get("node_id") != expected_id:
        _add_issue(
            issues,
            TYPED_NODES_INVALID_CODE,
            "typed_nodes node_id must be deterministic and contiguous",
            {"position": position, "node_id": node.get("node_id"), "expected": expected_id},
        )
    if node.get("ordinal") != position:
        _add_issue(
            issues,
            TYPED_NODES_INVALID_CODE,
            "typed_nodes ordinal must be contiguous",
            {"position": position, "ordinal": node.get("ordinal")},
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
