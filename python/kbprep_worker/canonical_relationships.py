"""Canonical IR relationship artifact builder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json

CANONICAL_IR_RELATIONSHIPS_SCHEMA = "kbprep.canonical_ir_relationships.v1"


def write_relationships_artifact(*, run_dir: Path, document_id: str, typed_nodes_path: Path) -> tuple[Path, bool]:
    """Write ``canonical_ir/relationships.json`` from typed-node structure."""
    artifact_path = run_dir / "canonical_ir" / "relationships.json"
    nodes = _nodes(typed_nodes_path)
    relationships = _relationships(nodes)
    atomic_write_json(
        artifact_path,
        {
            "schema": CANONICAL_IR_RELATIONSHIPS_SCHEMA,
            "document_id": document_id,
            "typed_nodes_artifact": _relative_run_path(run_dir, typed_nodes_path),
            "relationship_count": len(relationships),
            "relationships": relationships,
        },
        indent=2,
        trailing_newline=False,
    )
    return artifact_path, bool(relationships)


def _relationships(nodes: list[dict[str, Any]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for index, node in enumerate(nodes):
        if index + 1 < len(nodes):
            records.append(_record(len(records) + 1, "next_sibling", node["node_id"], nodes[index + 1]["node_id"]))
        if node.get("type") == "heading":
            records.extend(_contains_records(len(records) + 1, node, nodes[index + 1 :]))
        if node.get("type") == "paragraph" and index + 1 < len(nodes):
            next_node = nodes[index + 1]
            if next_node.get("type") in ("figure", "table"):
                records.append(_record(
                    len(records) + 1, "references", node["node_id"], next_node["node_id"],
                    basis="adjacent_reference",
                ))
    return records


def _contains_records(start_index: int, parent: dict[str, Any], following_nodes: list[dict[str, Any]]) -> list[dict[str, object]]:
    parent_level = _heading_level(parent)
    records: list[dict[str, object]] = []
    for node in following_nodes:
        if node.get("type") == "heading" and _heading_level(node) <= parent_level:
            break
        records.append(_record(start_index + len(records), "contains", parent["node_id"], node["node_id"]))
    return records


def _record(
    index: int,
    relation_type: str,
    source_node_id: object,
    target_node_id: object,
    *,
    basis: str = "typed_node_order",
) -> dict[str, object]:
    return {
        "relationship_id": f"r_{index:06d}",
        "type": relation_type,
        "source_node_id": str(source_node_id),
        "target_node_id": str(target_node_id),
        "evidence": {"basis": basis},
    }


def _heading_level(node: dict[str, Any]) -> int:
    metadata = node.get("metadata")
    raw_level = metadata.get("heading_level") if isinstance(metadata, dict) else None
    return raw_level if isinstance(raw_level, int) and not isinstance(raw_level, bool) else 1


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
