"""Converter-native source span evidence matching for the Canonical IR span writer."""

from __future__ import annotations

from typing import Any

NATIVE_PRECISION_SOURCE_KIND: dict[str, str] = {
    "pdf_bbox": "pdf",
    "docx_run_range": "docx",
    "pptx_shape": "pptx",
    "xlsx_cell_range": "xlsx",
}


def match_native_evidence(
    node: Any,
    native_source_spans: list[dict[str, object]] | None,
) -> dict[str, object] | None:
    """Return the first native evidence whose converted line range overlaps the typed node."""
    if not native_source_spans:
        return None
    for evidence in native_source_spans:
        if not isinstance(evidence, dict):
            continue
        start = evidence.get("converted_line_start")
        end = evidence.get("converted_line_end")
        if not isinstance(start, int) or isinstance(start, bool):
            continue
        if not isinstance(end, int) or isinstance(end, bool):
            continue
        if start > 0 and end > 0 and start <= node.line_end and end >= node.line_start:
            return evidence
    return None


def native_evidence_precision(evidence: dict[str, object] | None, source_kind: str) -> str | None:
    """Return the native precision only when it is compatible with the span source_kind."""
    if not isinstance(evidence, dict):
        return None
    precision = evidence.get("precision")
    if not isinstance(precision, str):
        return None
    return precision if NATIVE_PRECISION_SOURCE_KIND.get(precision) == source_kind else None


def add_native_location(location: dict[str, object], native_evidence: dict[str, object] | None) -> None:
    """Merge converter-native coordinate fields into the span location."""
    if not isinstance(native_evidence, dict):
        return
    native_location = native_evidence.get("location")
    if not isinstance(native_location, dict):
        return
    for key, value in native_location.items():
        location[key] = value
