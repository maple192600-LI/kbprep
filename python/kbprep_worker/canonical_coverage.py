"""Canonical IR coverage report builder and validator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CANONICAL_IR_COVERAGE_REPORT_SCHEMA = "kbprep.canonical_ir_coverage_report.v1"
COVERAGE_REPORT_INVALID_CODE = "E_CANONICAL_IR_COVERAGE_REPORT_INVALID"
_REQUIRED_GAPS = frozenset({
    "route_native_precision",
    "relationships",
    "assets",
    "annotations",
    "ir_markdown_regeneration",
})


@dataclass(frozen=True)
class CoverageReportValidationIssue:
    code: str
    message: str
    evidence: dict[str, Any]


def build_canonical_ir_coverage_report(
    *,
    run_dir: Path,
    typed_nodes_path: Path,
    typed_nodes_available: bool,
    source_spans_path: Path,
    source_spans_available: bool,
    transformation_ledger_path: Path,
    transformation_ledger_available: bool,
) -> dict[str, Any]:
    """Build the C4 coverage report embedded in the Canonical IR manifest."""
    typed_nodes = _read_json_object(typed_nodes_path)
    source_spans = _read_json_object(source_spans_path)
    ledger = _read_json_object(transformation_ledger_path)
    typed_section = _typed_nodes_section(run_dir, typed_nodes_path, typed_nodes, typed_nodes_available)
    span_section = _source_spans_section(
        run_dir, source_spans_path, source_spans, source_spans_available, typed_section,
    )
    ledger_section = _transformation_ledger_section(
        run_dir, transformation_ledger_path, ledger, transformation_ledger_available,
    )
    return {
        "schema": CANONICAL_IR_COVERAGE_REPORT_SCHEMA,
        "typed_nodes": typed_section,
        "source_spans": span_section,
        "transformation_ledger": ledger_section,
        "gaps": _target_gaps(span_section),
    }


def validate_canonical_ir_coverage_report(coverage: dict[str, Any]) -> list[CoverageReportValidationIssue]:
    """Validate coverage report claims against the manifest availability booleans."""
    issues: list[CoverageReportValidationIssue] = []
    report = coverage.get("report")
    if report is None:
        if _claims_any_coverage(coverage):
            _add_issue(issues, "coverage.report is required when Canonical IR artifacts are available", {})
        return issues
    if not isinstance(report, dict):
        _add_issue(issues, "coverage.report must be a JSON object", {"report": report})
        return issues
    if report.get("schema") != CANONICAL_IR_COVERAGE_REPORT_SCHEMA:
        _add_issue(issues, "coverage.report schema is invalid", {"schema": report.get("schema")})
    _validate_typed_nodes_report(coverage, report.get("typed_nodes"), issues)
    _validate_source_spans_report(coverage, report.get("source_spans"), issues)
    _validate_transformation_ledger_report(coverage, report.get("transformation_ledger"), issues)
    _validate_gap_report(report.get("gaps"), issues)
    return issues


def _typed_nodes_section(
    run_dir: Path,
    path: Path,
    payload: dict[str, Any] | None,
    available: bool,
) -> dict[str, Any]:
    nodes = _list_value(payload, "nodes")
    return {
        "artifact": _relative_run_path(run_dir, path),
        "available": available,
        "status": _status(path, payload, available),
        "node_count": _int_value(payload, "node_count", len(nodes)),
        "node_types": _count_by_key(nodes, "type"),
    }


def _source_spans_section(
    run_dir: Path,
    path: Path,
    payload: dict[str, Any] | None,
    available: bool,
    typed_section: dict[str, Any],
) -> dict[str, Any]:
    spans = _list_value(payload, "spans")
    typed_count = int(typed_section.get("node_count") or 0)
    covered_count = _covered_node_count(spans)
    return {
        "artifact": _relative_run_path(run_dir, path),
        "available": available,
        "status": _status(path, payload, available),
        "span_count": _int_value(payload, "span_count", len(spans)),
        "typed_node_count": typed_count,
        "covered_typed_node_count": covered_count,
        "typed_node_coverage_ratio": _coverage_ratio(covered_count, typed_count),
        "source_kinds": _count_by_key(spans, "source_kind"),
        "precisions": _precision_counts(spans),
    }


def _transformation_ledger_section(
    run_dir: Path,
    path: Path,
    payload: dict[str, Any] | None,
    available: bool,
) -> dict[str, Any]:
    entries = _list_value(payload, "entries")
    return {
        "artifact": _relative_run_path(run_dir, path),
        "available": available,
        "status": _status(path, payload, available),
        "entry_count": _int_value(payload, "entry_count", len(entries)),
    }


def _target_gaps(span_section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    precisions = sorted(str(key) for key in _dict_value(span_section.get("precisions")).keys())
    return {
        "route_native_precision": {
            "status": "target_work",
            "current_precisions": precisions,
            "missing": ["pdf_boxes", "docx_runs", "pptx_shapes", "xlsx_cells", "youtube_cue_ids"],
        },
        "relationships": {"status": "target_work", "missing": ["links_between_nodes"]},
        "assets": {"status": "target_work", "missing": ["asset_records"]},
        "annotations": {"status": "target_work", "missing": ["annotation_sets"]},
        "ir_markdown_regeneration": {"status": "target_work", "missing": ["renderer_from_ir_plus_changes"]},
    }


def _validate_typed_nodes_report(
    coverage: dict[str, Any],
    section: object,
    issues: list[CoverageReportValidationIssue],
) -> None:
    typed = _require_section(section, "typed_nodes", issues)
    if typed is None:
        return
    _require_bool_match(typed, coverage, "typed_nodes_available", issues)
    if coverage.get("typed_nodes_available") is True:
        _require_status(typed, "typed_nodes", issues)
        _require_non_negative_int(typed, "node_count", "typed_nodes", issues)
    if not isinstance(typed.get("node_types"), dict):
        _add_issue(issues, "coverage.report.typed_nodes.node_types must be an object", {"node_types": typed.get("node_types")})


def _validate_source_spans_report(
    coverage: dict[str, Any],
    section: object,
    issues: list[CoverageReportValidationIssue],
) -> None:
    spans = _require_section(section, "source_spans", issues)
    if spans is None:
        return
    _require_bool_match(spans, coverage, "source_spans_available", issues)
    if coverage.get("source_spans_available") is True:
        _require_status(spans, "source_spans", issues)
        _require_non_negative_int(spans, "span_count", "source_spans", issues)
        _require_non_negative_int(spans, "typed_node_count", "source_spans", issues)
        _require_non_negative_int(spans, "covered_typed_node_count", "source_spans", issues)
        _require_full_span_coverage(spans, issues)
    for field in ("source_kinds", "precisions"):
        if not isinstance(spans.get(field), dict):
            _add_issue(issues, f"coverage.report.source_spans.{field} must be an object", {field: spans.get(field)})


def _validate_transformation_ledger_report(
    coverage: dict[str, Any],
    section: object,
    issues: list[CoverageReportValidationIssue],
) -> None:
    ledger = _require_section(section, "transformation_ledger", issues)
    if ledger is None:
        return
    _require_bool_match(ledger, coverage, "transformation_ledger_available", issues)
    if coverage.get("transformation_ledger_available") is True:
        _require_status(ledger, "transformation_ledger", issues)
        _require_positive_int(ledger, "entry_count", "transformation_ledger", issues)


def _validate_gap_report(gaps: object, issues: list[CoverageReportValidationIssue]) -> None:
    if not isinstance(gaps, dict):
        _add_issue(issues, "coverage.report.gaps must be an object", {"gaps": gaps})
        return
    missing = sorted(_REQUIRED_GAPS.difference(gaps))
    if missing:
        _add_issue(issues, "coverage.report.gaps is missing target gap keys", {"missing": missing})


def _require_section(
    section: object,
    name: str,
    issues: list[CoverageReportValidationIssue],
) -> dict[str, Any] | None:
    if isinstance(section, dict):
        return section
    _add_issue(issues, f"coverage.report.{name} must be an object", {name: section})
    return None


def _require_bool_match(
    section: dict[str, Any],
    coverage: dict[str, Any],
    field: str,
    issues: list[CoverageReportValidationIssue],
) -> None:
    expected = coverage.get(field, False)
    if section.get("available") != expected:
        _add_issue(issues, f"coverage.report availability must match coverage.{field}", {
            "report_available": section.get("available"),
            field: expected,
        })


def _require_status(
    section: dict[str, Any],
    name: str,
    issues: list[CoverageReportValidationIssue],
) -> None:
    if section.get("status") != "validated":
        _add_issue(issues, f"coverage.report.{name}.status must be validated", {"status": section.get("status")})


def _require_positive_int(
    section: dict[str, Any],
    field: str,
    name: str,
    issues: list[CoverageReportValidationIssue],
) -> None:
    value = section.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        _add_issue(issues, f"coverage.report.{name}.{field} must be a positive integer", {field: value})


def _require_non_negative_int(
    section: dict[str, Any],
    field: str,
    name: str,
    issues: list[CoverageReportValidationIssue],
) -> None:
    value = section.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _add_issue(issues, f"coverage.report.{name}.{field} must be a non-negative integer", {field: value})


def _require_full_span_coverage(
    spans: dict[str, Any],
    issues: list[CoverageReportValidationIssue],
) -> None:
    if spans.get("status") != "validated":
        _add_issue(issues, "coverage.report.source_spans.status must be validated", {"status": spans.get("status")})
    if spans.get("typed_node_coverage_ratio") != 1.0:
        _add_issue(issues, "coverage.report.source_spans.typed_node_coverage_ratio must be 1.0", {
            "typed_node_coverage_ratio": spans.get("typed_node_coverage_ratio"),
        })
    if spans.get("span_count") != spans.get("typed_node_count"):
        _add_issue(issues, "coverage.report.source_spans.span_count must equal typed_node_count", {
            "span_count": spans.get("span_count"),
            "typed_node_count": spans.get("typed_node_count"),
        })


def _claims_any_coverage(coverage: dict[str, Any]) -> bool:
    return any(coverage.get(field) is True for field in (
        "typed_nodes_available",
        "source_spans_available",
        "transformation_ledger_available",
    ))


def _status(path: Path, payload: dict[str, Any] | None, available: bool) -> str:
    if payload is None:
        return "missing" if available else "not_available"
    return "validated" if available else "invalid"


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _list_value(payload: dict[str, Any] | None, field: str) -> list[Any]:
    if payload is None:
        return []
    value = payload.get(field)
    return value if isinstance(value, list) else []


def _int_value(payload: dict[str, Any] | None, field: str, fallback: int) -> int:
    if payload is None:
        return 0
    value = payload.get(field)
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _count_by_key(items: list[Any], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get(key), str):
            label = str(item[key])
            counts[label] = counts.get(label, 0) + 1
    return counts


def _precision_counts(spans: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for span in spans:
        evidence = span.get("evidence") if isinstance(span, dict) else None
        precision = evidence.get("precision") if isinstance(evidence, dict) else None
        if isinstance(precision, str):
            counts[precision] = counts.get(precision, 0) + 1
    return counts


def _covered_node_count(spans: list[Any]) -> int:
    node_ids = {
        str(span.get("node_id"))
        for span in spans
        if isinstance(span, dict) and isinstance(span.get("node_id"), str) and span.get("node_id")
    }
    return len(node_ids)


def _coverage_ratio(covered_count: int, typed_count: int) -> float:
    if typed_count <= 0:
        return 1.0 if covered_count == 0 else 0.0
    return round(covered_count / typed_count, 4)


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _relative_run_path(run_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def _add_issue(
    issues: list[CoverageReportValidationIssue],
    message: str,
    evidence: dict[str, Any],
) -> None:
    issues.append(CoverageReportValidationIssue(
        code=COVERAGE_REPORT_INVALID_CODE,
        message=message,
        evidence=evidence,
    ))
