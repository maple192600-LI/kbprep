"""Assemble content-safe Clean View artifacts from Canonical IR and patches."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .cleaning_patches import FORBIDDEN_ARTIFACT_KEYS

CLEAN_VIEW_SCHEMA = "kbprep.clean_view.v1"
CLEAN_VIEW_KEYS = frozenset({"schema", "source_artifact", "patch_artifact", "entry_count", "entries"})
CLEAN_VIEW_ENTRY_KEYS = frozenset({
    "entry_id",
    "ordinal",
    "node_id",
    "block_id",
    "parent_block_id",
    "entry_kind",
    "type",
    "status",
    "patch_ids",
    "rule_ids",
    "location",
})
CLEAN_VIEW_LOCATION_KEYS = frozenset({"line_start", "line_end", "page_start", "page_end"})
ALLOWED_ENTRY_KINDS = frozenset({"canonical_node", "derived_block", "unmapped_block"})
ALLOWED_STATUSES = frozenset({"keep", "discard", "evidence", "review", "unclassified"})
_HEADING_MARKER_RE = re.compile(r"^#{1,6}\s+")
_FENCE_RE = re.compile(r"^```[^\n]*\n|\n```$", re.MULTILINE)
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
_SAFE_TYPE_RE = re.compile(r"^[A-Za-z0-9_:-]{1,80}$")


def assemble_clean_view(
    *,
    run_dir: Path,
    blocks: list[dict],
    accepted_patches: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a text-free Clean View payload in Canonical IR order."""
    nodes = _read_typed_nodes(run_dir / "canonical_ir" / "typed_nodes.json")
    patch_map = _patches_by_block(accepted_patches)
    ordered_blocks = _ordered_blocks(nodes, blocks, accepted_patches)
    entries = [
        _entry_payload(index, block, patch_map.get(_block_id(block), []))
        for index, block in enumerate(ordered_blocks, start=1)
    ]
    return {
        "schema": CLEAN_VIEW_SCHEMA,
        "source_artifact": "canonical_ir/typed_nodes.json",
        "patch_artifact": "cleaning_patches.jsonl",
        "entry_count": len(entries),
        "entries": entries,
    }


def write_clean_view(path: Path, payload: dict[str, Any]) -> None:
    """Write a Clean View JSON artifact atomically."""
    atomic_write_json(path, payload, indent=2, trailing_newline=False)


def validate_clean_view_artifact(path: Path) -> bool:
    """Return true only for the current content-safe Clean View schema."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return _valid_clean_view_payload(payload)


def _read_typed_nodes(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    nodes = payload.get("nodes") if isinstance(payload, dict) else None
    return [node for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else []


def _ordered_blocks(nodes: list[dict[str, Any]], blocks: list[dict], patches: list[dict[str, Any]]) -> list[dict]:
    by_id = {_block_id(block): block for block in blocks if _block_id(block)}
    derived_by_parent = _derived_patch_children(patches)
    matched_ids: set[str] = set()
    ordered: list[dict] = []
    for node in sorted(nodes, key=_node_ordinal):
        block = _match_node_to_block(node, blocks, matched_ids, derived_by_parent)
        if block is not None:
            _append_block_and_children(ordered, block, by_id, derived_by_parent, matched_ids)
    for block in sorted(blocks, key=_block_sort_key):
        if _block_id(block) not in matched_ids and _block_id(block) not in _all_derived_ids(derived_by_parent):
            _append_block_and_children(ordered, block, by_id, derived_by_parent, matched_ids)
    for block in sorted(blocks, key=_block_sort_key):
        if _block_id(block) not in matched_ids:
            _append_unique(ordered, block, matched_ids)
    return ordered


def _match_node_to_block(
    node: dict[str, Any],
    blocks: list[dict],
    matched_ids: set[str],
    derived_by_parent: dict[str, list[str]],
) -> dict | None:
    target = _normalized_text(node.get("text"), node.get("type"))
    derived_ids = _all_derived_ids(derived_by_parent)
    for block in sorted(blocks, key=_block_sort_key):
        block_id = _block_id(block)
        if block_id in matched_ids or block_id in derived_ids:
            continue
        candidate = _normalized_text(block.get("text"), block.get("type"))
        if _text_matches(target, candidate):
            block["clean_view_node_id"] = str(node.get("node_id") or "")
            return block
    return None


def _append_block_and_children(
    ordered: list[dict],
    block: dict,
    by_id: dict[str, dict],
    derived_by_parent: dict[str, list[str]],
    matched_ids: set[str],
) -> None:
    _append_unique(ordered, block, matched_ids)
    for child_id in derived_by_parent.get(_block_id(block), []):
        child = by_id.get(child_id)
        if child is not None:
            _append_unique(ordered, child, matched_ids)


def _entry_payload(ordinal: int, block: dict, patches: list[dict[str, Any]]) -> dict[str, Any]:
    change_types = {str(patch.get("change_type") or "") for patch in patches}
    return {
        "entry_id": f"cv_{ordinal:06d}",
        "ordinal": ordinal,
        "node_id": str(block.get("clean_view_node_id") or ""),
        "block_id": _block_id(block),
        "parent_block_id": _parent_block_id(block, patches),
        "entry_kind": "derived_block" if "derived_block" in change_types else _entry_kind(block),
        "type": str(block.get("type") or ""),
        "status": str(block.get("status") or ""),
        "patch_ids": [str(patch.get("patch_id") or "") for patch in patches if patch.get("patch_id")],
        "rule_ids": _rule_ids(patches),
        "location": _safe_location(block),
    }


def _valid_clean_view_payload(payload: Any) -> bool:
    if not isinstance(payload, dict) or set(payload) != CLEAN_VIEW_KEYS:
        return False
    if payload.get("schema") != CLEAN_VIEW_SCHEMA or _contains_forbidden_artifact_key(payload):
        return False
    if payload.get("source_artifact") != "canonical_ir/typed_nodes.json":
        return False
    if payload.get("patch_artifact") != "cleaning_patches.jsonl":
        return False
    entries = payload.get("entries")
    return (
        isinstance(entries, list)
        and _non_negative_int(payload.get("entry_count"))
        and payload.get("entry_count") == len(entries)
        and all(_valid_entry(entry) for entry in entries)
    )


def _valid_entry(entry: Any) -> bool:
    if not isinstance(entry, dict) or set(entry) != CLEAN_VIEW_ENTRY_KEYS:
        return False
    if not _valid_entry_scalars(entry):
        return False
    return _valid_id_list(entry.get("patch_ids")) and _valid_id_list(entry.get("rule_ids")) and _valid_location(entry.get("location"))


def _valid_entry_scalars(entry: dict[str, Any]) -> bool:
    return (
        isinstance(entry.get("entry_id"), str)
        and entry["entry_id"].startswith("cv_")
        and _safe_id(entry.get("entry_id"))
        and _non_negative_int(entry.get("ordinal"))
        and _optional_safe_id(entry.get("node_id"))
        and _safe_id(entry.get("block_id"))
        and _optional_safe_id(entry.get("parent_block_id"))
        and entry.get("entry_kind") in ALLOWED_ENTRY_KINDS
        and _safe_type(entry.get("type"))
        and entry.get("status") in ALLOWED_STATUSES
    )


def _valid_id_list(value: Any) -> bool:
    return isinstance(value, list) and all(_safe_id(item) for item in value)


def _derived_patch_children(patches: list[dict[str, Any]]) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {}
    for patch in patches:
        if patch.get("change_type") != "derived_block":
            continue
        parent = str(patch.get("parent_block_id") or "")
        child = str(patch.get("block_id") or "")
        if parent and child:
            children.setdefault(parent, []).append(child)
    return children


def _patches_by_block(patches: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for patch in patches:
        block_id = str(patch.get("block_id") or "")
        if block_id:
            grouped.setdefault(block_id, []).append(patch)
    return grouped


def _all_derived_ids(derived_by_parent: dict[str, list[str]]) -> set[str]:
    return {child_id for child_ids in derived_by_parent.values() for child_id in child_ids}


def _append_unique(ordered: list[dict], block: dict, matched_ids: set[str]) -> None:
    block_id = _block_id(block)
    if block_id and block_id not in matched_ids:
        ordered.append(block)
        matched_ids.add(block_id)


def _entry_kind(block: dict) -> str:
    return "canonical_node" if block.get("clean_view_node_id") else "unmapped_block"


def _parent_block_id(block: dict, patches: list[dict[str, Any]]) -> str:
    if patches:
        return str(patches[0].get("parent_block_id") or "")
    return ""


def _rule_ids(patches: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for patch in patches:
        rule_id = _safe_reference_id(str(patch.get("rule_id") or ""))
        if rule_id and rule_id not in ids:
            ids.append(rule_id)
    return ids


def _safe_reference_id(value: str) -> str:
    if _safe_id(value):
        return value
    if not value:
        return ""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"rule_{digest}"


def _safe_location(block: dict) -> dict[str, Any]:
    return {
        "line_start": block.get("line_start"),
        "line_end": block.get("line_end"),
        "page_start": block.get("page_start"),
        "page_end": block.get("page_end"),
    }


def _valid_location(location: Any) -> bool:
    return isinstance(location, dict) and set(location) == CLEAN_VIEW_LOCATION_KEYS and all(
        value is None or type(value) is int for value in location.values()
    )


def _contains_forbidden_artifact_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key) in FORBIDDEN_ARTIFACT_KEYS or _contains_forbidden_artifact_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_artifact_key(item) for item in value)
    return False


def _normalized_text(value: Any, node_type: Any = "") -> str:
    text = str(value or "").strip()
    if str(node_type or "") in {"heading", "section_heading"}:
        text = _HEADING_MARKER_RE.sub("", text)
    if str(node_type or "") == "code":
        text = _FENCE_RE.sub("", text).strip()
    return " ".join(text.split())


def _text_matches(target: str, candidate: str) -> bool:
    if not target or not candidate:
        return False
    return target == candidate or target in candidate or candidate in target


def _node_ordinal(node: dict[str, Any]) -> int:
    ordinal = node.get("ordinal")
    return ordinal if isinstance(ordinal, int) and not isinstance(ordinal, bool) else 0


def _block_sort_key(block: dict) -> tuple[int, str]:
    line_start = block.get("line_start")
    line_value = line_start if isinstance(line_start, int) and not isinstance(line_start, bool) else 0
    return (line_value, _block_id(block))


def _block_id(block: dict) -> str:
    return str(block.get("block_id") or "").strip()


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _safe_id(value: Any) -> bool:
    return isinstance(value, str) and _SAFE_ID_RE.fullmatch(value) is not None and not _looks_private_or_leaky(value)


def _optional_safe_id(value: Any) -> bool:
    return value == "" or _safe_id(value)


def _safe_type(value: Any) -> bool:
    return isinstance(value, str) and _SAFE_TYPE_RE.fullmatch(value) is not None and not _looks_private_or_leaky(value)


def _looks_private_or_leaky(value: str) -> bool:
    lowered = value.lower()
    return (
        ".kbprep" in lowered
        or "users/" in lowered
        or "users\\" in lowered
        or "do_not_leak" in lowered
        or "\\" in value
        or "/" in value
    )
