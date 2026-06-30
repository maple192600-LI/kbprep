"""DOCX-specific structure helpers: char styles, hyperlinks, and merged cells.

These helpers deepen DOCX fidelity (run-level emphasis, hyperlink targets,
gridSpan/vMerge table cells) and are kept out of the shared Office XML module
so the PPTX/XLSX paths stay lightweight per ``format-strategy-decision.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml.etree import _Element

from .office_xml_common import (
    first_child_by_local_name,
    iter_by_local_name,
    local_name,
    rows_to_markdown_table,
    xml_attr_by_local_name,
    xml_text,
)


@dataclass(frozen=True)
class _DocxCell:
    """A DOCX table cell with its merge metadata."""

    text: str
    gridspan: int
    vmerge: str | None  # "restart", "continue", or None


def word_table_to_markdown(tbl_el: _Element, external_rels: dict[str, str] | None = None) -> str:
    rels = external_rels or {}
    raw_rows: list[list[_DocxCell]] = []
    for tr in [n for n in tbl_el.iter() if local_name(n.tag) == "tr"]:
        cells = [
            _DocxCell(
                text=_docx_tablecell_styled_text(tc, rels),
                gridspan=_tc_gridspan(tc),
                vmerge=_tc_vmerge(tc),
            )
            for tc in list(tr)
            if local_name(tc.tag) == "tc"
        ]
        if any(cell.text.strip() for cell in cells):
            raw_rows.append(cells)
    expanded = _expand_docx_merged_cells(raw_rows)
    return rows_to_markdown_table(expanded)


def _docx_paragraph_styled_text(paragraph: _Element, external_rels: dict[str, str]) -> str:
    """Build paragraph text from direct children, applying run styles and hyperlinks.

    Walks direct children (``r`` and ``hyperlink``) in document order so link
    targets and emphasis survive; runs nested inside a hyperlink are rendered
    through the hyperlink renderer instead of being duplicated.
    """
    parts: list[str] = []
    for child in list(paragraph):
        local = local_name(child.tag)
        if local == "r":
            parts.append(_docx_run_styled_text(child))
        elif local == "hyperlink":
            parts.append(_docx_hyperlink_text(child, external_rels))
    if not parts:
        # Non-conforming paragraph: <w:t> sits directly under <w:p> without a
        # <w:r> wrapper. Fall back to recursive text so it is not dropped.
        return xml_text(paragraph)
    text = "".join(parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _docx_run_styled_text(run: _Element) -> str:
    """Return a run's text wrapped in Markdown emphasis for bold/italic/strike."""
    raw = xml_text(run)
    if not raw:
        return ""
    r_pr = first_child_by_local_name(run, "rPr")
    if r_pr is None:
        return raw
    text = raw
    if _rpr_bool(r_pr, "strike"):
        text = f"~~{text}~~"
    if _rpr_bool(r_pr, "b"):
        text = f"**{text}**"
    if _rpr_bool(r_pr, "i"):
        text = f"*{text}*"
    return text


def _rpr_bool(r_pr: _Element, name: str) -> bool:
    """Return True when a run-property toggle is present and not explicitly disabled."""
    node = first_child_by_local_name(r_pr, name)
    if node is None:
        return False
    val = xml_attr_by_local_name(node, "val")
    return (val or "").lower() not in {"false", "0", "off"}


def _docx_hyperlink_text(hyperlink: _Element, external_rels: dict[str, str]) -> str:
    """Render a hyperlink as ``[text](target)``; keep text when the target is missing."""
    link_text = _docx_hyperlink_inner_text(hyperlink)
    if not link_text:
        return ""
    anchor = xml_attr_by_local_name(hyperlink, "anchor")
    if anchor:
        return f"[{link_text}](#{anchor})"
    rel_id = xml_attr_by_local_name(hyperlink, "id")
    target = external_rels.get(rel_id or "")
    if target:
        return f"[{link_text}]({target})"
    return link_text


def _docx_hyperlink_inner_text(hyperlink: _Element) -> str:
    """Collect styled run text inside a hyperlink element."""
    parts = [_docx_run_styled_text(run) for run in iter_by_local_name(hyperlink, "r")]
    return "".join(parts).strip()


def _docx_tablecell_styled_text(tc: _Element, external_rels: dict[str, str]) -> str:
    """Collect styled paragraph text inside a table cell, joined by newlines."""
    parts = [
        _docx_paragraph_styled_text(p, external_rels)
        for p in iter_by_local_name(tc, "p")
    ]
    return "\n".join(part for part in parts if part)


def _tc_gridspan(tc: _Element) -> int:
    tc_pr = first_child_by_local_name(tc, "tcPr")
    if tc_pr is None:
        return 1
    node = first_child_by_local_name(tc_pr, "gridSpan")
    val = xml_attr_by_local_name(node, "val") if node is not None else None
    try:
        return max(1, int(val)) if val else 1
    except (TypeError, ValueError):
        return 1


def _tc_vmerge(tc: _Element) -> str | None:
    tc_pr = first_child_by_local_name(tc, "tcPr")
    if tc_pr is None:
        return None
    node = first_child_by_local_name(tc_pr, "vMerge")
    if node is None:
        return None
    val = (xml_attr_by_local_name(node, "val") or "").lower()
    return "restart" if val == "restart" else "continue"


def _expand_docx_merged_cells(raw_rows: list[list[_DocxCell]]) -> list[list[str]]:
    """Expand gridSpan horizontally and fill vMerge-continue cells from their restart value.

    Markdown has no native cell-spanning syntax, so a merged cell's value is
    repeated across the columns/rows it covers to keep the table rectangular.
    """
    grid: list[list[_DocxCell]] = []
    for row in raw_rows:
        expanded: list[_DocxCell] = []
        for cell in row:
            expanded.extend([cell] * cell.gridspan)
        grid.append(expanded)
    col_count = max((len(row) for row in grid), default=0)
    for row in grid:
        while len(row) < col_count:
            row.append(_DocxCell("", 1, None))
    prev_values: list[str] = [""] * col_count
    out: list[list[str]] = []
    for row in grid:
        out_row: list[str] = []
        for ci, cell in enumerate(row):
            if cell.vmerge == "restart":
                prev_values[ci] = cell.text
                out_row.append(cell.text)
            elif cell.vmerge == "continue":
                out_row.append(prev_values[ci])
            else:
                prev_values[ci] = cell.text
                out_row.append(cell.text)
        out.append(out_row)
    return out
