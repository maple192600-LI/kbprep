"""Canonical IR SourceSpan artifact builder and validator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .canonical_nodes import build_typed_nodes_from_markdown
from .canonical_transcripts import TranscriptCue, read_transcript_cues
from .supported_formats import (
    CODE_EXTENSIONS,
    EPUB_EXTENSIONS,
    HTML_EXTENSIONS,
    JSON_EXTENSIONS,
    MARKDOWN_EXTENSIONS,
    NOTEBOOK_EXTENSIONS,
    OFFICE_XML_EXTENSIONS,
    PLAIN_TEXT_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    TABLE_TEXT_EXTENSIONS,
)

CANONICAL_IR_SOURCE_SPANS_SCHEMA = "kbprep.canonical_ir_source_spans.v1"
MANIFEST_INVALID_CODE = "E_CANONICAL_IR_MANIFEST_INVALID"
SOURCE_SPANS_INVALID_CODE = "E_CANONICAL_IR_SOURCE_SPANS_INVALID"
SOURCE_SPAN_KEYS = frozenset({"span_id", "node_id", "source_kind", "location", "evidence"})
SOURCE_SPAN_EVIDENCE_KEYS = frozenset({
    "source_type",
    "converter",
    "conversion_route",
    "source_kind",
    "precision",
})
SOURCE_LINE_LOCATION_KEYS = frozenset({"source_line_start", "source_line_end"})
TRANSCRIPT_TIMING_LOCATION_KEYS = frozenset({"cue_id", "start_time", "end_time", "cue_settings"})
TRANSCRIPT_CUE_LOCATION_KEYS = TRANSCRIPT_TIMING_LOCATION_KEYS | {"cue_index", "cue_settings"}
SUPPORTED_PRECISIONS = frozenset({
    "converted_line_range",
    "source_line_range",
    "transcript_cue_timing",
})
SUPPORTED_SOURCE_KINDS = frozenset({
    "converted_markdown",
    "markdown_text",
    "transcript",
    "pdf",
    "docx",
    "pptx",
    "xlsx",
    "html",
    "epub",
    "structured_data",
    "notebook",
    "code",
    "youtube",
    "unknown",
})


@dataclass(frozen=True)
class SourceSpanValidationIssue:
    code: str
    message: str
    evidence: dict[str, Any]


def write_source_spans_artifact(
    *,
    run_dir: Path,
    document_id: str,
    input_path: Path,
    converted_path: Path,
    typed_nodes_path: Path,
    source_type: str,
    converter: str,
    conversion_route: str,
) -> Path:
    """Write ``canonical_ir/source_spans.json`` for the converted Markdown."""
    artifact_path = run_dir / "canonical_ir" / "source_spans.json"
    markdown = converted_path.read_text(encoding="utf-8")
    transcript_cues = read_transcript_cues(input_path) if _is_transcript_context(source_type, conversion_route) else []
    nodes = build_typed_nodes_from_markdown(
        markdown,
        source_type=source_type,
        conversion_route=conversion_route,
        transcript_cue_texts=[cue.text for cue in transcript_cues],
    )
    spans = [
        _span_dict(index, node, input_path, source_type, converter, conversion_route, transcript_cues)
        for index, node in enumerate(nodes, start=1)
    ]
    payload = {
        "schema": CANONICAL_IR_SOURCE_SPANS_SCHEMA,
        "document_id": document_id,
        "source_artifact": converted_path.resolve().relative_to(run_dir.resolve()).as_posix(),
        "typed_nodes_artifact": typed_nodes_path.resolve().relative_to(run_dir.resolve()).as_posix(),
        "span_count": len(spans),
        "spans": spans,
    }
    atomic_write_json(artifact_path, payload, indent=2, trailing_newline=False)
    return artifact_path


def validate_source_spans_artifact(
    *,
    run_dir: Path,
    source_spans_path: Path,
    typed_nodes_path: Path,
    document_id: str,
    converted_path: Path,
) -> list[SourceSpanValidationIssue]:
    """Validate ``canonical_ir/source_spans.json`` against typed-node evidence."""
    issues: list[SourceSpanValidationIssue] = []
    payload = _read_required_json(source_spans_path, "canonical_ir/source_spans.json", issues)
    typed_nodes = _read_required_json(typed_nodes_path, "canonical_ir/typed_nodes.json", issues)
    if payload is None or typed_nodes is None:
        return issues
    _validate_header(run_dir, payload, document_id, converted_path, typed_nodes_path, issues)
    typed_node_ids = _typed_node_ids(typed_nodes, issues)
    spans = payload.get("spans")
    if not isinstance(spans, list):
        _add_issue(issues, "source_spans.spans must be a list", {"spans": spans})
        return issues
    _validate_span_count(payload.get("span_count"), len(spans), len(typed_node_ids), issues)
    for position, span in enumerate(spans, start=1):
        expected_node_id = typed_node_ids[position - 1] if position <= len(typed_node_ids) else ""
        _validate_span(span, position, expected_node_id, issues)
    return issues


def validate_source_spans_reference(
    *,
    run_dir: Path,
    artifacts: dict[str, Any],
    coverage: dict[str, Any],
    document_id: str,
    converted_path: Path,
) -> list[SourceSpanValidationIssue]:
    """Validate manifest reference and payload for ``source_spans.json``."""
    issues: list[SourceSpanValidationIssue] = []
    raw_ref = artifacts.get("source_spans")
    if raw_ref is None:
        if coverage.get("source_spans_available") is True:
            _add_issue(
                issues,
                "coverage.source_spans_available requires artifacts.source_spans",
                {"source_spans_available": coverage.get("source_spans_available")},
                MANIFEST_INVALID_CODE,
            )
        return issues
    resolved = _resolve_run_reference(run_dir, raw_ref, "source_spans", issues, MANIFEST_INVALID_CODE)
    if resolved is None:
        return issues
    expected = run_dir / "canonical_ir" / "source_spans.json"
    if resolved != expected.resolve():
        _add_issue(
            issues,
            "artifacts.source_spans must reference canonical_ir/source_spans.json",
            {"source_spans": raw_ref, "expected": "canonical_ir/source_spans.json"},
            MANIFEST_INVALID_CODE,
        )
    if coverage.get("source_spans_available") is not True:
        _add_issue(
            issues,
            "coverage.source_spans_available must be true when artifacts.source_spans exists",
            {"source_spans_available": coverage.get("source_spans_available")},
            MANIFEST_INVALID_CODE,
        )
    typed_nodes_path = _source_spans_typed_nodes_path(run_dir, artifacts, issues)
    if typed_nodes_path is None:
        return issues
    issues.extend(validate_source_spans_artifact(
        run_dir=run_dir,
        source_spans_path=resolved,
        typed_nodes_path=typed_nodes_path,
        document_id=document_id,
        converted_path=converted_path,
    ))
    return issues


def _span_dict(
    index: int,
    node: Any,
    input_path: Path,
    source_type: str,
    converter: str,
    conversion_route: str,
    transcript_cues: list[TranscriptCue],
) -> dict[str, object]:
    source_kind = _span_source_kind(node.node_type, input_path, source_type, converter, conversion_route)
    location = _span_location(node, source_kind, input_path, converter, conversion_route, transcript_cues)
    return {
        "span_id": f"s_{index:06d}",
        "node_id": node.node_id,
        "source_kind": source_kind,
        "location": location,
        "evidence": _span_evidence(source_type, converter, conversion_route, location, source_kind),
    }


def _span_source_kind(
    node_type: str,
    input_path: Path,
    source_type: str,
    converter: str,
    conversion_route: str,
) -> str:
    if _is_transcript_context(source_type, conversion_route):
        return "transcript" if node_type == "transcript_cue" else "converted_markdown"
    return _source_kind(input_path, source_type, converter, conversion_route)


def _source_kind(input_path: Path, source_type: str, converter: str, conversion_route: str) -> str:
    ext = input_path.suffix.lower()
    if ext in SUBTITLE_EXTENSIONS or _is_transcript_context(source_type, conversion_route):
        return "transcript"
    if ext in NOTEBOOK_EXTENSIONS:
        return "notebook"
    if ext in TABLE_TEXT_EXTENSIONS or ext in JSON_EXTENSIONS:
        return "structured_data"
    if ext in MARKDOWN_EXTENSIONS | PLAIN_TEXT_EXTENSIONS:
        return "markdown_text"
    if ext in HTML_EXTENSIONS:
        return "html"
    if ext in EPUB_EXTENSIONS:
        return "epub"
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in OFFICE_XML_EXTENSIONS:
        return ext.removeprefix(".")
    if source_type == "pdf_like":
        return "pdf"
    if converter == "media_transcript" or conversion_route == "media_to_transcript":
        return "transcript"
    return "unknown"


def _span_location(
    node: Any,
    source_kind: str,
    input_path: Path,
    converter: str,
    conversion_route: str,
    transcript_cues: list[TranscriptCue],
) -> dict[str, object]:
    location: dict[str, object] = {
        "converted_line_start": node.line_start,
        "converted_line_end": node.line_end,
    }
    if source_kind == "markdown_text" and _is_passthrough_text(input_path, converter, conversion_route):
        location["source_line_start"] = node.line_start
        location["source_line_end"] = node.line_end
    if source_kind == "transcript":
        _add_transcript_location(location, node, transcript_cues)
    return location


def _add_transcript_location(location: dict[str, object], node: Any, transcript_cues: list[TranscriptCue]) -> None:
    raw_index = node.metadata.get("cue_index") if isinstance(node.metadata, dict) else None
    if not isinstance(raw_index, int):
        return
    location["cue_index"] = raw_index
    if 1 <= raw_index <= len(transcript_cues):
        cue = transcript_cues[raw_index - 1]
        location["cue_id"] = cue.cue_id
        location["start_time"] = cue.start_time
        location["end_time"] = cue.end_time
        if cue.settings:
            location["cue_settings"] = cue.settings


def _span_evidence(
    source_type: str,
    converter: str,
    conversion_route: str,
    location: dict[str, object],
    source_kind: str,
) -> dict[str, object]:
    precision = "converted_line_range"
    if source_kind == "transcript" and "start_time" in location:
        precision = "transcript_cue_timing"
    elif "source_line_start" in location:
        precision = "source_line_range"
    return {
        "source_type": source_type,
        "converter": converter,
        "conversion_route": conversion_route,
        "source_kind": source_kind,
        "precision": precision,
    }


def _is_passthrough_text(input_path: Path, converter: str, conversion_route: str) -> bool:
    ext = input_path.suffix.lower()
    return converter == "direct_text" and conversion_route == "direct_text" and ext in MARKDOWN_EXTENSIONS | PLAIN_TEXT_EXTENSIONS


def _is_transcript_context(source_type: str, conversion_route: str) -> bool:
    return source_type == "subtitle_transcript" or conversion_route in {"media_to_transcript", "media_transcript"}


def _read_required_json(
    path: Path,
    label: str,
    issues: list[SourceSpanValidationIssue],
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
    issues: list[SourceSpanValidationIssue],
) -> None:
    if payload.get("schema") != CANONICAL_IR_SOURCE_SPANS_SCHEMA:
        _add_issue(issues, "source_spans schema is invalid", {"schema": payload.get("schema")})
    if payload.get("document_id") != document_id:
        _add_issue(issues, "source_spans.document_id must match canonical manifest", {"document_id": payload.get("document_id")})
    _validate_run_reference(run_dir, payload.get("source_artifact"), converted_path, "source_artifact", issues)
    _validate_run_reference(run_dir, payload.get("typed_nodes_artifact"), typed_nodes_path, "typed_nodes_artifact", issues)


def _typed_node_ids(typed_nodes: dict[str, Any], issues: list[SourceSpanValidationIssue]) -> list[str]:
    nodes = typed_nodes.get("nodes")
    if not isinstance(nodes, list):
        _add_issue(issues, "typed_nodes.nodes must be a list for source-span validation", {"nodes": nodes})
        return []
    ids: list[str] = []
    for node in nodes:
        ids.append(str(node.get("node_id") if isinstance(node, dict) else ""))
    return ids


def _validate_span_count(
    span_count: object,
    actual_count: int,
    typed_node_count: int,
    issues: list[SourceSpanValidationIssue],
) -> None:
    if not isinstance(span_count, int) or isinstance(span_count, bool) or span_count < 0:
        _add_issue(issues, "source_spans.span_count must be a non-negative integer", {"span_count": span_count})
    elif span_count != actual_count:
        _add_issue(
            issues,
            "source_spans.span_count must equal len(spans)",
            {"span_count": span_count, "actual_count": actual_count},
        )
    if actual_count != typed_node_count:
        _add_issue(
            issues,
            "source_spans must contain one span per typed node",
            {"span_count": actual_count, "typed_node_count": typed_node_count},
        )


def _validate_span(
    span: object,
    position: int,
    expected_node_id: str,
    issues: list[SourceSpanValidationIssue],
) -> None:
    if not isinstance(span, dict):
        _add_issue(issues, "source span must be an object", {"position": position})
        return
    if set(span) != SOURCE_SPAN_KEYS:
        _add_issue(issues, "source span keys must match schema exactly", {"position": position, "keys": sorted(span)})
    expected_span_id = f"s_{position:06d}"
    if span.get("span_id") != expected_span_id:
        _add_issue(issues, "source span_id must be deterministic and contiguous", {"position": position, "expected": expected_span_id})
    if span.get("node_id") != expected_node_id:
        _add_issue(issues, "source span node_id must match typed-node order", {"position": position, "expected": expected_node_id})
    if span.get("source_kind") not in SUPPORTED_SOURCE_KINDS:
        _add_issue(issues, "source span source_kind is unsupported", {"source_kind": span.get("source_kind")})
    location = span.get("location")
    _validate_location(location, span.get("source_kind"), position, issues)
    _validate_evidence(span.get("evidence"), span.get("source_kind"), location, position, issues)


def _validate_location(
    location: object,
    source_kind: object,
    position: int,
    issues: list[SourceSpanValidationIssue],
) -> None:
    if not isinstance(location, dict) or not location:
        _add_issue(issues, "source span location must be a non-empty object", {"position": position})
        return
    start = location.get("converted_line_start")
    end = location.get("converted_line_end")
    if not _valid_line_range(start, end):
        _add_issue(issues, "source span converted line range is invalid", {"position": position, "location": location})
    if source_kind == "transcript" and not _valid_positive_int(location.get("cue_index")):
        _add_issue(issues, "transcript source span requires cue_index", {"position": position, "location": location})


def _validate_evidence(
    evidence: object,
    source_kind: object,
    location: object,
    position: int,
    issues: list[SourceSpanValidationIssue],
) -> None:
    if not isinstance(evidence, dict) or not evidence:
        _add_issue(issues, "source span evidence must be a non-empty object", {"position": position})
        return
    if set(evidence) != SOURCE_SPAN_EVIDENCE_KEYS:
        _add_issue(issues, "source span evidence keys must match schema exactly", {"position": position})
    for field in ("source_type", "converter", "conversion_route"):
        if not isinstance(evidence.get(field), str):
            _add_issue(issues, f"source span evidence.{field} must be a string", {"position": position})
    if evidence.get("source_kind") != source_kind:
        _add_issue(issues, "source span evidence.source_kind must match source_kind", {"position": position})
    precision = evidence.get("precision")
    if precision not in SUPPORTED_PRECISIONS:
        _add_issue(issues, "source span evidence.precision is unsupported", {"position": position})
        return
    if isinstance(location, dict):
        _validate_precision_location(precision, source_kind, location, position, issues)


def _validate_precision_location(
    precision: object,
    source_kind: object,
    location: dict[str, object],
    position: int,
    issues: list[SourceSpanValidationIssue],
) -> None:
    if precision == "source_line_range":
        _validate_source_line_precision(source_kind, location, position, issues)
    if precision == "transcript_cue_timing":
        _validate_transcript_timing_precision(source_kind, location, position, issues)
    if precision == "converted_line_range":
        _validate_converted_line_precision(location, position, issues)


def _validate_source_line_precision(
    source_kind: object,
    location: dict[str, object],
    position: int,
    issues: list[SourceSpanValidationIssue],
) -> None:
    if not _valid_line_range(location.get("source_line_start"), location.get("source_line_end")):
        _add_issue(issues, "source_line_range precision requires source line range", {"position": position})
    if source_kind == "transcript" or _has_any_location_key(location, TRANSCRIPT_CUE_LOCATION_KEYS):
        _add_issue(issues, "source_line_range precision cannot include transcript cue fields", {"position": position})


def _validate_transcript_timing_precision(
    source_kind: object,
    location: dict[str, object],
    position: int,
    issues: list[SourceSpanValidationIssue],
) -> None:
    if source_kind != "transcript":
        _add_issue(issues, "transcript_cue_timing precision requires transcript source_kind", {"position": position})
    if not _valid_nonempty_string(location.get("start_time")) or not _valid_nonempty_string(location.get("end_time")):
        _add_issue(issues, "transcript_cue_timing precision requires start_time and end_time", {"position": position})
    if _has_any_location_key(location, SOURCE_LINE_LOCATION_KEYS):
        _add_issue(issues, "transcript_cue_timing precision cannot include source line range", {"position": position})


def _validate_converted_line_precision(
    location: dict[str, object],
    position: int,
    issues: list[SourceSpanValidationIssue],
) -> None:
    if _has_any_location_key(location, SOURCE_LINE_LOCATION_KEYS):
        _add_issue(issues, "source line range requires source_line_range precision", {"position": position})
    if _has_any_location_key(location, TRANSCRIPT_TIMING_LOCATION_KEYS):
        _add_issue(issues, "transcript timing requires transcript_cue_timing precision", {"position": position})


def _has_any_location_key(location: dict[str, object], keys: frozenset[str]) -> bool:
    return any(key in location for key in keys)


def _valid_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _valid_line_range(start: object, end: object) -> bool:
    return _valid_positive_int(start) and _valid_positive_int(end) and isinstance(start, int) and isinstance(end, int) and end >= start


def _validate_run_reference(
    run_dir: Path,
    raw_value: object,
    expected_path: Path,
    field: str,
    issues: list[SourceSpanValidationIssue],
) -> None:
    resolved = _resolve_run_reference(run_dir, raw_value, field, issues, SOURCE_SPANS_INVALID_CODE)
    if resolved is None:
        return
    if resolved != expected_path.resolve():
        _add_issue(issues, f"source_spans.{field} must reference expected artifact", {field: raw_value})


def _resolve_run_reference(
    run_dir: Path,
    raw_value: object,
    field: str,
    issues: list[SourceSpanValidationIssue],
    code: str,
) -> Path | None:
    if not isinstance(raw_value, str) or not raw_value:
        _add_issue(issues, f"source_spans.{field} must be a relative path string", {field: raw_value}, code)
        return None
    rel_path = Path(raw_value)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        _add_issue(issues, f"source_spans.{field} must stay inside the run directory", {field: raw_value}, code)
        return None
    resolved = (run_dir / rel_path).resolve()
    if not _is_relative_to(resolved, run_dir.resolve()):
        _add_issue(issues, f"source_spans.{field} escapes the run directory", {field: raw_value}, code)
        return None
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _add_issue(
    issues: list[SourceSpanValidationIssue],
    message: str,
    evidence: dict[str, Any],
    code: str = SOURCE_SPANS_INVALID_CODE,
) -> None:
    issues.append(SourceSpanValidationIssue(code=code, message=message, evidence=evidence))


def _source_spans_typed_nodes_path(
    run_dir: Path,
    artifacts: dict[str, Any],
    issues: list[SourceSpanValidationIssue],
) -> Path | None:
    raw_ref = artifacts.get("typed_nodes")
    if raw_ref is None:
        _add_issue(
            issues,
            "artifacts.source_spans requires artifacts.typed_nodes",
            {"typed_nodes": raw_ref},
            MANIFEST_INVALID_CODE,
        )
        return None
    return _resolve_run_reference(run_dir, raw_ref, "typed_nodes", issues, MANIFEST_INVALID_CODE)
