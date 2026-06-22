"""Canonical IR TypedNode artifact builder."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .atomic_io import atomic_write_json

CANONICAL_IR_TYPED_NODES_SCHEMA = "kbprep.canonical_ir_typed_nodes.v1"
SUPPORTED_NODE_TYPES = frozenset({"heading", "paragraph", "list", "table", "code", "quote"})
TYPED_NODE_KEYS = frozenset({"node_id", "ordinal", "type", "text", "metadata"})

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
_UNORDERED_LIST_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
_TABLE_SEPARATOR_CELL_RE = re.compile(r"^\s*:?-{3,}:?\s*$")


@dataclass(frozen=True)
class TypedNode:
    node_id: str
    ordinal: int
    node_type: str
    text: str
    metadata: Mapping[str, object]


def build_typed_nodes_from_markdown(markdown: str) -> list[TypedNode]:
    """Build deterministic C1 typed nodes from Markdown blocks."""
    lines = markdown.splitlines()
    nodes: list[TypedNode] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        node_type, text, metadata, index = _consume_block(lines, index)
        if text.strip():
            nodes.append(_typed_node(len(nodes) + 1, node_type, text, metadata))
    return nodes


def write_typed_nodes_artifact(*, run_dir: Path, document_id: str, converted_path: Path) -> Path:
    """Write ``canonical_ir/typed_nodes.json`` for the converted Markdown."""
    artifact_path = run_dir / "canonical_ir" / "typed_nodes.json"
    markdown = converted_path.read_text(encoding="utf-8")
    nodes = build_typed_nodes_from_markdown(markdown)
    payload = {
        "schema": CANONICAL_IR_TYPED_NODES_SCHEMA,
        "document_id": document_id,
        "source_artifact": converted_path.resolve().relative_to(run_dir.resolve()).as_posix(),
        "node_count": len(nodes),
        "nodes": [_typed_node_to_dict(node) for node in nodes],
    }
    atomic_write_json(artifact_path, payload, indent=2, trailing_newline=False)
    return artifact_path


def _consume_block(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    line = lines[index]
    if _parse_fence(line) is not None:
        return _consume_code(lines, index)
    heading = _HEADING_RE.match(line)
    if heading:
        return "heading", heading.group(2).strip(), {"heading_level": len(heading.group(1))}, index + 1
    if _list_item_text(line) is not None:
        return _consume_list(lines, index)
    if _starts_table(lines, index):
        return _consume_table(lines, index)
    if line.lstrip().startswith(">"):
        return _consume_quote(lines, index)
    return _consume_paragraph(lines, index)


def _consume_code(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    fence = _parse_fence(lines[index])
    if fence is None:
        return _consume_paragraph(lines, index)
    fence_char, fence_len, language = fence
    block: list[str] = []
    index += 1
    while index < len(lines):
        if _is_closing_fence(lines[index], fence_char, fence_len):
            return "code", "\n".join(block), {"language": language} if language else {}, index + 1
        block.append(lines[index])
        index += 1
    return "code", "\n".join(block), {"language": language} if language else {}, index


def _consume_list(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    items: list[str] = []
    while index < len(lines):
        item = _list_item_text(lines[index])
        if item is None:
            break
        items.append(item.strip())
        index += 1
    return "list", "\n".join(items), {"items": len(items)}, index


def _consume_table(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    rows: list[str] = []
    while index < len(lines) and _has_pipe_cells(lines[index]):
        rows.append(lines[index].strip())
        index += 1
    return "table", "\n".join(rows), {"rows": len(rows)}, index


def _consume_quote(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    quoted: list[str] = []
    while index < len(lines) and lines[index].lstrip().startswith(">"):
        quoted.append(lines[index].lstrip()[1:].strip())
        index += 1
    return "quote", "\n".join(quoted), {"lines": len(quoted)}, index


def _consume_paragraph(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    paragraph: list[str] = []
    while index < len(lines) and lines[index].strip():
        if paragraph and _is_special_block_start(lines, index):
            break
        paragraph.append(lines[index].strip())
        index += 1
    return "paragraph", "\n".join(paragraph), {}, index


def _is_special_block_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    return (
        _parse_fence(line) is not None
        or _HEADING_RE.match(line) is not None
        or _list_item_text(line) is not None
        or _starts_table(lines, index)
        or line.lstrip().startswith(">")
    )


def _starts_table(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and _has_pipe_cells(lines[index])
        and _is_table_separator_row(lines[index + 1])
    )


def _has_pipe_cells(line: str) -> bool:
    return len(_table_cells(line)) >= 2


def _is_table_separator_row(line: str) -> bool:
    cells = _table_cells(line)
    return len(cells) >= 2 and all(_TABLE_SEPARATOR_CELL_RE.match(cell) for cell in cells)


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if "|" not in stripped:
        return []
    parts = stripped.split("|")
    if stripped.startswith("|"):
        parts = parts[1:]
    if stripped.endswith("|") and len(parts) > 2:
        parts = parts[:-1]
    return [cell.strip() for cell in parts]


def _parse_fence(line: str) -> tuple[str, int, str] | None:
    leading_spaces = len(line) - len(line.lstrip(" "))
    if leading_spaces > 3:
        return None
    stripped = line.strip()
    if not stripped or stripped[0] not in {"`", "~"}:
        return None
    fence_char = stripped[0]
    fence_len = len(stripped) - len(stripped.lstrip(fence_char))
    if fence_len < 3:
        return None
    return fence_char, fence_len, stripped[fence_len:].strip()


def _is_closing_fence(line: str, fence_char: str, fence_len: int) -> bool:
    leading_spaces = len(line) - len(line.lstrip(" "))
    if leading_spaces > 3:
        return False
    stripped = line.strip()
    if not stripped.startswith(fence_char * fence_len):
        return False
    closing_len = len(stripped) - len(stripped.lstrip(fence_char))
    return stripped[closing_len:].strip() == ""


def _list_item_text(line: str) -> str | None:
    ordered = _ORDERED_LIST_RE.match(line)
    if ordered:
        return ordered.group(1)
    unordered = _UNORDERED_LIST_RE.match(line)
    if unordered:
        return unordered.group(1)
    return None


def _typed_node(ordinal: int, node_type: str, text: str, metadata: dict[str, object]) -> TypedNode:
    return TypedNode(
        node_id=f"n_{ordinal:06d}",
        ordinal=ordinal,
        node_type=node_type,
        text=text,
        metadata=metadata,
    )


def _typed_node_to_dict(node: TypedNode) -> dict[str, object]:
    return {
        "node_id": node.node_id,
        "ordinal": node.ordinal,
        "type": node.node_type,
        "text": node.text,
        "metadata": dict(node.metadata),
    }
