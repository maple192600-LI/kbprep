"""Shared XML and Markdown helpers for Office Open XML converters.

These helpers are pure and stateless so DOCX, PPTX, and XLSX converters can
share them without creating cross-format import cycles.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from lxml.etree import _Element


def rows_to_markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    max_cols = max(len(row) for row in rows)
    padded = [row + [""] * (max_cols - len(row)) for row in rows]
    header = padded[0]
    body = padded[1:]
    lines = [
        "| " + " | ".join(escape_table_cell(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(escape_table_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def escape_table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def xml_text(element: _Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        local = local_name(node.tag)
        if local == "t" and node.text:
            parts.append(node.text)
        elif local in {"tab"}:
            parts.append("\t")
        elif local in {"br", "cr"}:
            parts.append("\n")
    text = "".join(parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def iter_by_local_name(element: _Element, local_name_value: str) -> Iterator[_Element]:
    for node in element.iter():
        if local_name(node.tag) == local_name_value:
            yield node


def first_child_by_local_name(element: _Element, local_name_value: str) -> _Element | None:
    for child in list(element):
        if local_name(child.tag) == local_name_value:
            return child
    return None


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def xml_attr_by_local_name(element: _Element, local_name_value: str) -> str | None:
    for key, value in element.attrib.items():
        if local_name(key) == local_name_value:
            return value
    return None
