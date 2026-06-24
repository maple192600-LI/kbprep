"""Canonical IR evidence used by the pre-clean conversion gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical_coverage import COVERAGE_REPORT_INVALID_CODE
from .diagnose import analyze_text_quality


def build_canonical_ir_gate_evidence(run_dir: Path) -> dict[str, Any]:
    """Summarize complete Canonical IR evidence for conversion-gate checks."""
    run_p = Path(run_dir)
    manifest = _read_json_object(run_p / "canonical_ir" / "manifest.json")
    artifacts = _dict_value(manifest.get("artifacts") if manifest else None)
    coverage = _dict_value(manifest.get("coverage") if manifest else None)
    report = _dict_value(coverage.get("report"))
    typed_section = _dict_value(report.get("typed_nodes"))
    spans_section = _dict_value(report.get("source_spans"))
    issues = _coverage_report_artifact_issues(artifacts, typed_section, spans_section)
    typed_nodes_ref = artifacts.get("typed_nodes")
    source_spans_ref = artifacts.get("source_spans")
    typed_nodes_path = _resolve_run_artifact(run_p, typed_nodes_ref)
    source_spans_path = _resolve_run_artifact(run_p, source_spans_ref)
    typed_nodes = _read_json_object(typed_nodes_path) if typed_nodes_path is not None else None
    source_spans = _read_json_object(source_spans_path) if source_spans_path is not None else None
    complete = not issues and _has_complete_ir_evidence(coverage, typed_section, spans_section, typed_nodes, source_spans)
    text = _joined_typed_node_text(typed_nodes) if complete else ""
    return {
        "complete": complete,
        "quality_source": "canonical_ir" if complete else "unavailable",
        "typed_nodes": _typed_nodes_summary(typed_section, typed_nodes, typed_nodes_ref),
        "source_spans": _source_spans_summary(spans_section, source_spans, source_spans_ref),
        "issues": issues,
        "text_quality": analyze_text_quality(text) if complete else {},
    }


def _has_complete_ir_evidence(
    coverage: dict[str, Any],
    typed_section: dict[str, Any],
    spans_section: dict[str, Any],
    typed_nodes: dict[str, Any] | None,
    source_spans: dict[str, Any] | None,
) -> bool:
    return (
        coverage.get("typed_nodes_available") is True
        and coverage.get("source_spans_available") is True
        and typed_section.get("available") is True
        and typed_section.get("status") == "validated"
        and spans_section.get("available") is True
        and spans_section.get("status") == "validated"
        and spans_section.get("typed_node_coverage_ratio") == 1.0
        and spans_section.get("span_count") == spans_section.get("typed_node_count")
        and typed_nodes is not None
        and source_spans is not None
    )


def _typed_nodes_summary(
    section: dict[str, Any],
    payload: dict[str, Any] | None,
    manifest_ref: object,
) -> dict[str, Any]:
    return {
        "artifact": manifest_ref,
        "report_artifact": section.get("artifact"),
        "available": section.get("available") is True,
        "status": str(section.get("status") or "unavailable"),
        "node_count": _int_value(section.get("node_count")),
        "node_types": _dict_value(section.get("node_types")),
        "payload_readable": payload is not None,
    }


def _source_spans_summary(
    section: dict[str, Any],
    payload: dict[str, Any] | None,
    manifest_ref: object,
) -> dict[str, Any]:
    return {
        "artifact": manifest_ref,
        "report_artifact": section.get("artifact"),
        "available": section.get("available") is True,
        "status": str(section.get("status") or "unavailable"),
        "span_count": _int_value(section.get("span_count")),
        "typed_node_count": _int_value(section.get("typed_node_count")),
        "typed_node_coverage_ratio": section.get("typed_node_coverage_ratio"),
        "source_kinds": _dict_value(section.get("source_kinds")),
        "precisions": _dict_value(section.get("precisions")),
        "payload_readable": payload is not None,
    }


def _joined_typed_node_text(payload: dict[str, Any] | None) -> str:
    nodes = payload.get("nodes") if isinstance(payload, dict) else None
    if not isinstance(nodes, list):
        return ""
    texts = [
        str(node.get("text"))
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("text"), str)
    ]
    return "\n\n".join(texts)


def _coverage_report_artifact_issues(
    artifacts: dict[str, Any],
    typed_section: dict[str, Any],
    spans_section: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        *_canonical_artifact_issues("typed_nodes", artifacts.get("typed_nodes"), "canonical_ir/typed_nodes.json"),
        *_canonical_artifact_issues("source_spans", artifacts.get("source_spans"), "canonical_ir/source_spans.json"),
        *_artifact_match_issues("typed_nodes", artifacts.get("typed_nodes"), typed_section.get("artifact")),
        *_artifact_match_issues("source_spans", artifacts.get("source_spans"), spans_section.get("artifact")),
    ]


def _canonical_artifact_issues(name: str, manifest_ref: object, expected: str) -> list[dict[str, Any]]:
    if manifest_ref is None:
        return []
    if manifest_ref == expected:
        return []
    return [{
        "code": "E_CANONICAL_IR_MANIFEST_INVALID",
        "message": f"artifacts.{name} must reference {expected}",
        "evidence": {
            f"artifacts.{name}": manifest_ref,
            "expected": expected,
        },
    }]


def _artifact_match_issues(name: str, manifest_ref: object, report_ref: object) -> list[dict[str, Any]]:
    if report_ref == manifest_ref:
        return []
    return [{
        "code": COVERAGE_REPORT_INVALID_CODE,
        "message": f"coverage.report.{name}.artifact must match artifacts.{name}",
        "evidence": {
            f"artifacts.{name}": manifest_ref,
            f"coverage.report.{name}.artifact": report_ref,
        },
    }]


def _resolve_run_artifact(run_dir: Path, raw: object) -> Path | None:
    if not isinstance(raw, str) or not raw:
        return None
    rel_path = Path(raw)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return None
    resolved = (run_dir / rel_path).resolve()
    try:
        resolved.relative_to(run_dir.resolve())
    except ValueError:
        return None
    return resolved


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
