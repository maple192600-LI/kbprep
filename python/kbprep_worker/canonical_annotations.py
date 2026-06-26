"""Canonical IR annotation artifact builder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json

CANONICAL_IR_ANNOTATIONS_SCHEMA = "kbprep.canonical_ir_annotations.v1"
MIN_PARAGRAPH_LENGTH = 20


def write_annotations_artifact(
    *,
    run_dir: Path,
    document_id: str,
    typed_nodes_path: Path | None = None,
) -> tuple[Path, bool]:
    """Write ``canonical_ir/annotations.json`` with content-safe coverage and quality warnings."""
    artifact_path = run_dir / "canonical_ir" / "annotations.json"
    records: list[dict[str, object]] = [_base_coverage_warning()]
    if typed_nodes_path is not None:
        records.extend(_quality_warnings(_nodes(typed_nodes_path)))
    annotations = [
        {**record, "annotation_id": f"an_{index + 1:06d}"}
        for index, record in enumerate(records)
    ]
    atomic_write_json(
        artifact_path,
        {
            "schema": CANONICAL_IR_ANNOTATIONS_SCHEMA,
            "document_id": document_id,
            "annotation_count": len(annotations),
            "annotations": annotations,
        },
        indent=2,
        trailing_newline=False,
    )
    return artifact_path, True


def _base_coverage_warning() -> dict[str, object]:
    return {
        "kind": "coverage_warning",
        "severity": "info",
        "target": "ir_markdown_regeneration",
        "message_code": "renderer_from_ir_plus_changes_not_shipped",
        "evidence": {"basis": "canonical_ir_coverage_gap"},
    }


def _quality_warnings(nodes: list[dict[str, Any]]) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    for index, node in enumerate(nodes):
        node_type = node.get("type")
        node_id = str(node["node_id"])
        if node_type == "heading" and _is_empty_heading(nodes, index):
            warnings.append({
                "kind": "quality_warning",
                "severity": "info",
                "target": node_id,
                "message_code": "W_EMPTY_HEADING",
                "evidence": {"basis": "heading_without_following_content"},
            })
        elif node_type == "paragraph" and _is_short_paragraph(node):
            warnings.append({
                "kind": "quality_warning",
                "severity": "info",
                "target": node_id,
                "message_code": "W_SHORT_PARAGRAPH",
                "evidence": {"basis": "paragraph_below_min_length"},
            })
    return warnings


def _is_empty_heading(nodes: list[dict[str, Any]], index: int) -> bool:
    if index + 1 >= len(nodes):
        return True
    return nodes[index + 1].get("type") == "heading"


def _is_short_paragraph(node: dict[str, Any]) -> bool:
    text = node.get("text")
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    return 0 < len(stripped) < MIN_PARAGRAPH_LENGTH


def _nodes(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_nodes = payload.get("nodes") if isinstance(payload, dict) else None
    if not isinstance(raw_nodes, list):
        return []
    return [node for node in raw_nodes if isinstance(node, dict) and isinstance(node.get("node_id"), str)]
