"""Regenerate Markdown blocks from Canonical IR plus accepted clean-view changes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TYPED_NODES_SCHEMA = "kbprep.canonical_ir_typed_nodes.v1"
CLEAN_VIEW_SCHEMA = "kbprep.clean_view.v1"


def regenerate_blocks_from_ir(
    *,
    run_dir: Path,
    blocks: list[dict],
    clean_view: dict | None,
) -> list[dict] | None:
    """Return render blocks whose default text comes from Canonical IR."""
    entries = _clean_view_entries(clean_view)
    if entries is None or len(entries) != len(blocks):
        return None
    nodes = _read_typed_nodes(run_dir / "canonical_ir" / "typed_nodes.json")
    if nodes is None:
        return None
    by_block_id = {_block_id(block): block for block in blocks if _block_id(block)}
    by_node_id = {_node_id(node): node for node in nodes if _node_id(node)}
    regenerated: list[dict] = []
    for entry in entries:
        block = by_block_id.get(_entry_block_id(entry))
        if block is None:
            return None
        rendered = _regenerated_block(entry, block, by_node_id)
        if rendered is None:
            return None
        regenerated.append(rendered)
    return regenerated


def _clean_view_entries(clean_view: dict | None) -> list[dict[str, Any]] | None:
    if not isinstance(clean_view, dict) or clean_view.get("schema") != CLEAN_VIEW_SCHEMA:
        return None
    entries = clean_view.get("entries")
    if not isinstance(entries, list):
        return None
    return [entry for entry in entries if isinstance(entry, dict)]


def _read_typed_nodes(path: Path) -> list[dict[str, Any]] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != TYPED_NODES_SCHEMA:
        return None
    nodes = payload.get("nodes")
    return [node for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else None


def _regenerated_block(
    entry: dict[str, Any],
    block: dict,
    by_node_id: dict[str, dict[str, Any]],
) -> dict | None:
    rendered = dict(block)
    rendered["status"] = str(entry.get("status") or block.get("status") or "")
    text = _accepted_change_text(entry, block)
    if text is None:
        node_id = str(entry.get("node_id") or "")
        node = by_node_id.get(node_id)
        text = _markdown_for_node(node) if node is not None else _unmapped_block_text(entry, block)
    if text is None:
        return None
    rendered["text"] = text
    rendered["curated_text"] = text
    return rendered


def _accepted_change_text(entry: dict[str, Any], block: dict) -> str | None:
    patch_ids = entry.get("patch_ids")
    if isinstance(patch_ids, list) and patch_ids:
        return _block_text(block)
    if entry.get("entry_kind") == "derived_block":
        return _block_text(block)
    return None


def _unmapped_block_text(entry: dict[str, Any], block: dict) -> str | None:
    if entry.get("entry_kind") == "unmapped_block":
        return _block_text(block)
    return None


def _markdown_for_node(node: dict[str, Any]) -> str | None:
    text = str(node.get("text") or "").strip()
    node_type = str(node.get("type") or "")
    raw_metadata = node.get("metadata")
    metadata: dict[str, Any] = {}
    if isinstance(raw_metadata, dict):
        metadata = {str(key): value for key, value in raw_metadata.items()}
    if not text:
        return None
    if node_type == "heading":
        level = _heading_level(metadata)
        return f"{'#' * level} {text}"
    if node_type == "code":
        language = str(metadata.get("language") or "").strip()
        return f"```{language}\n{text}\n```"
    if node_type == "list":
        return "\n".join(_list_line(line) for line in text.splitlines() if line.strip())
    if node_type == "quote":
        return "\n".join(f"> {line.strip()}" for line in text.splitlines() if line.strip())
    if node_type == "formula":
        return f"$$\n{text}\n$$"
    return text


def _heading_level(metadata: dict[str, Any]) -> int:
    level = metadata.get("heading_level")
    if isinstance(level, int) and not isinstance(level, bool) and 1 <= level <= 6:
        return level
    return 1


def _list_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith(("- ", "* ", "+ ")):
        return stripped
    return f"- {stripped}"


def _block_text(block: dict) -> str:
    return str(block.get("curated_text") or block.get("text") or "").strip()


def _entry_block_id(entry: dict[str, Any]) -> str:
    return str(entry.get("block_id") or "").strip()


def _block_id(block: dict) -> str:
    return str(block.get("block_id") or "").strip()


def _node_id(node: dict[str, Any]) -> str:
    return str(node.get("node_id") or "").strip()
