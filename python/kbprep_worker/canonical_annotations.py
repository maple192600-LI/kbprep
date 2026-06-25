"""Canonical IR annotation artifact builder."""

from __future__ import annotations

from pathlib import Path

from .atomic_io import atomic_write_json

CANONICAL_IR_ANNOTATIONS_SCHEMA = "kbprep.canonical_ir_annotations.v1"


def write_annotations_artifact(*, run_dir: Path, document_id: str) -> tuple[Path, bool]:
    """Write ``canonical_ir/annotations.json`` with content-safe coverage warnings."""
    artifact_path = run_dir / "canonical_ir" / "annotations.json"
    annotations = [{
        "annotation_id": "an_000001",
        "kind": "coverage_warning",
        "severity": "info",
        "target": "ir_markdown_regeneration",
        "message_code": "renderer_from_ir_plus_changes_not_shipped",
        "evidence": {"basis": "canonical_ir_coverage_gap"},
    }]
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
