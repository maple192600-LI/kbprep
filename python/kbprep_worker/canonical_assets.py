"""Canonical IR asset artifact builder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json

CANONICAL_IR_ASSETS_SCHEMA = "kbprep.canonical_ir_assets.v1"


def write_assets_artifact(*, run_dir: Path, document_id: str, typed_nodes_path: Path) -> tuple[Path, bool]:
    """Write ``canonical_ir/assets.json`` with content-safe figure references."""
    artifact_path = run_dir / "canonical_ir" / "assets.json"
    assets = _assets(_nodes(typed_nodes_path))
    atomic_write_json(
        artifact_path,
        {
            "schema": CANONICAL_IR_ASSETS_SCHEMA,
            "document_id": document_id,
            "typed_nodes_artifact": _relative_run_path(run_dir, typed_nodes_path),
            "asset_count": len(assets),
            "assets": assets,
        },
        indent=2,
        trailing_newline=False,
    )
    return artifact_path, bool(assets)


def _assets(nodes: list[dict[str, Any]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for node in nodes:
        metadata = node.get("metadata")
        target = metadata.get("target") if isinstance(metadata, dict) else None
        if node.get("type") == "figure" and isinstance(target, str) and target:
            records.append({
                "asset_id": f"a_{len(records) + 1:06d}",
                "asset_type": "image",
                "source_node_id": str(node["node_id"]),
                "reference": target,
                "reference_kind": "markdown_image",
            })
    return records


def _nodes(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_nodes = payload.get("nodes") if isinstance(payload, dict) else None
    if not isinstance(raw_nodes, list):
        return []
    return [node for node in raw_nodes if isinstance(node, dict) and isinstance(node.get("node_id"), str)]


def _relative_run_path(run_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(run_dir.resolve()).as_posix()
