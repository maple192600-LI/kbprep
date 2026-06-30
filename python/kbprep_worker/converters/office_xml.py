from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path

from lxml.etree import _Element

from ..atomic_io import atomic_write_bytes, atomic_write_json
from ..supported_formats import IMAGE_EXTENSIONS
from ..zip_safety import SafeZipReader, ZipSafetyError, open_safe_zip
from .office_xml_common import (
    first_child_by_local_name,
    iter_by_local_name,
    local_name,
    rows_to_markdown_table,
    xml_attr_by_local_name,
    xml_text,
)
from .office_xml_docx import (
    _docx_paragraph_styled_text,
    word_table_to_markdown,
)


class OfficeXmlConversionError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def office_xml_to_markdown(input_p: Path, run_dir: Path) -> tuple[str, list[str], dict]:
    """Extract readable Markdown from modern Office Open XML files without heavy converters."""
    ext = input_p.suffix.lower()
    warnings: list[str] = []
    artifacts: dict = {"office_image_assets": {"copied_count": 0, "copied": []}}
    native_source_spans: list[dict] = []
    try:
        with open_safe_zip(input_p) as zf:
            if ext == ".docx":
                markdown, image_artifacts, native_source_spans = docx_to_markdown(zf, run_dir)
            elif ext == ".pptx":
                markdown, image_artifacts, native_source_spans = pptx_to_markdown(zf, run_dir)
            elif ext == ".xlsx":
                markdown, native_source_spans = xlsx_to_markdown(zf)
                image_artifacts = []
            else:
                raise ValueError(f"Unsupported Office XML extension: {ext}")
            artifacts["office_image_assets"] = {
                "copied_count": len(image_artifacts),
                "copied": image_artifacts[:50],
            }
    except KeyError as e:
        raise OfficeXmlConversionError(
            "E_CONVERT_INPUT_INVALID",
            f"{input_p.name} is missing required Office XML part: {e}",
            {"extension": ext},
        )
    except zipfile.BadZipFile:
        raise OfficeXmlConversionError(
            "E_CONVERT_INPUT_INVALID",
            f"{input_p.name} is not a valid Office ZIP container. Check whether the file is corrupted or mislabeled.",
            {"extension": ext},
        )
    except ZipSafetyError as e:
        raise OfficeXmlConversionError(
            "E_CONVERT_INPUT_INVALID",
            f"{input_p.name} exceeds Office ZIP safety limits: {e}",
            {"extension": ext},
        ) from e

    if not markdown.strip():
        raise OfficeXmlConversionError(
            "E_CONVERT_OUTPUT_EMPTY",
            f"{input_p.name} did not contain extractable Office text.",
            {"extension": ext},
        )

    warnings.append("W_OFFICE_XML_CONVERTER_USED: extracted text directly from Office XML; complex layout fidelity may be limited.")
    artifacts["native_source_spans"] = native_source_spans
    return markdown.strip() + "\n", warnings, artifacts


def docx_to_markdown(zf: SafeZipReader, run_dir: Path) -> tuple[str, list[str], list[dict]]:
    import xml.etree.ElementTree as ET

    external_rels = _docx_external_targets(zf, "word/_rels/document.xml.rels")
    numbering_index = _docx_numbering_index(zf)

    root = ET.fromstring(zf.read_bytes("word/document.xml"))
    body = first_child_by_local_name(root, "body")
    if body is None:
        return "", [], []

    builder = _MarkdownLineBuilder()
    native_spans: list[dict] = []
    _render_docx_body(body, builder, native_spans, external_rels, numbering_index)

    image_lines, image_artifacts = extract_office_images(
        zf=zf,
        part_name="word/document.xml",
        rels_name="word/_rels/document.xml.rels",
        run_dir=run_dir,
        output_prefix="office/docx",
        alt_prefix="DOCX Image",
    )
    if image_lines:
        builder.append_block("## Embedded Images")
        for image_line in image_lines:
            builder.append_block(image_line)
    return builder.build(), image_artifacts, native_spans


def _render_docx_body(
    body: _Element,
    builder: _MarkdownLineBuilder,
    native_spans: list[dict],
    external_rels: dict[str, str],
    numbering_index: dict[tuple[str, int], str],
) -> None:
    """Walk the document body, appending rendered paragraphs/tables and native spans."""
    paragraph_index = -1
    list_counter: dict[str, int] = {}
    for child in list(body):
        local = local_name(child.tag)
        if local == "p":
            paragraph_index += 1
            text, run_range = _docx_paragraph_text_and_runs(child, external_rels)
            if not text:
                continue
            heading = docx_heading_level(child)
            list_info = _docx_paragraph_list_info(child, numbering_index)
            if list_info is None:
                list_counter.clear()
            block = _docx_render_paragraph_block(text, heading, list_info, list_counter)
            start_line, end_line = builder.append_block(block)
            if run_range is not None:
                native_spans.append({
                    "converted_line_start": start_line,
                    "converted_line_end": end_line,
                    "precision": "docx_run_range",
                    "location": {
                        "paragraph_index": paragraph_index,
                        "run_start": run_range[0],
                        "run_end": run_range[1],
                    },
                })
        elif local == "tbl":
            list_counter.clear()
            table = word_table_to_markdown(child, external_rels)
            if table:
                builder.append_block(table)


def _docx_paragraph_text_and_runs(
    paragraph: _Element, external_rels: dict[str, str] | None = None
) -> tuple[str, tuple[int, int] | None]:
    """Return (paragraph text, run index range) for a DOCX paragraph.

    Text carries run-level character styles and resolved hyperlinks so the
    rendered Markdown preserves emphasis and link targets, not just raw text.
    The run index range is computed via ``iter_by_local_name`` (recursive), so
    it includes runs nested inside a ``<w:hyperlink>``; consumers reading the
    source DOCX by ``run_start``/``run_end`` must use the same recursive walk.
    """
    text = _docx_paragraph_styled_text(paragraph, external_rels or {})
    runs = list(iter_by_local_name(paragraph, "r"))
    if not runs:
        return text, None
    first_run = -1
    last_run = -1
    for index, run in enumerate(runs):
        if xml_text(run):
            if first_run < 0:
                first_run = index
            last_run = index
    if first_run < 0:
        return text, None
    return text, (first_run, last_run)


def _docx_external_targets(zf: SafeZipReader, rels_name: str) -> dict[str, str]:
    """Map hyperlink relationship ids to external targets from a ``.rels`` part."""
    import xml.etree.ElementTree as ET

    if rels_name not in zf.namelist():
        return {}
    try:
        rels_root = ET.fromstring(zf.read_bytes(rels_name))
    except ET.ParseError:
        return {}
    targets: dict[str, str] = {}
    for rel in list(rels_root):
        rel_id = xml_attr_by_local_name(rel, "Id")
        target = xml_attr_by_local_name(rel, "Target")
        mode = (xml_attr_by_local_name(rel, "TargetMode") or "").lower()
        if rel_id and target and mode == "external":
            targets[rel_id] = target
    return targets


def _docx_numbering_index(zf: SafeZipReader) -> dict[tuple[str, int], str]:
    """Resolve ``(numId, ilvl)`` to a numbering format (``bullet``/``decimal``/...).

    Returns an empty map when ``word/numbering.xml`` is absent so list-less
    documents degrade to plain paragraphs without fabricating markers.
    """
    import xml.etree.ElementTree as ET

    if "word/numbering.xml" not in zf.namelist():
        return {}
    try:
        root = ET.fromstring(zf.read_bytes("word/numbering.xml"))
    except ET.ParseError:
        return {}
    abstract_fmt: dict[str, dict[int, str]] = {}
    for abstract in iter_by_local_name(root, "abstractNum"):
        abs_id = xml_attr_by_local_name(abstract, "abstractNumId")
        if abs_id is None:
            continue
        lvl_fmt: dict[int, str] = {}
        for lvl in iter_by_local_name(abstract, "lvl"):
            ilvl_str = xml_attr_by_local_name(lvl, "ilvl")
            fmt_node = first_child_by_local_name(lvl, "numFmt")
            fmt = xml_attr_by_local_name(fmt_node, "val") if fmt_node is not None else None
            try:
                ilvl = int(ilvl_str) if ilvl_str else 0
            except (TypeError, ValueError):
                ilvl = 0
            if fmt:
                lvl_fmt[ilvl] = fmt
        abstract_fmt[abs_id] = lvl_fmt
    index: dict[tuple[str, int], str] = {}
    for num in iter_by_local_name(root, "num"):
        num_id = xml_attr_by_local_name(num, "numId")
        abs_node = first_child_by_local_name(num, "abstractNumId")
        abs_id = xml_attr_by_local_name(abs_node, "val") if abs_node is not None else None
        if not num_id or abs_id not in abstract_fmt:
            continue
        for ilvl, fmt in abstract_fmt[abs_id].items():
            index[(num_id, ilvl)] = fmt
    return index


def _docx_paragraph_list_info(
    paragraph: _Element, numbering_index: dict[tuple[str, int], str]
) -> tuple[str, int, str] | None:
    """Return ``(numId, ilvl, fmt)`` when a paragraph is a numbered list item."""
    if not numbering_index:
        return None
    p_pr = first_child_by_local_name(paragraph, "pPr")
    if p_pr is None:
        return None
    num_pr = first_child_by_local_name(p_pr, "numPr")
    if num_pr is None:
        return None
    num_id_node = first_child_by_local_name(num_pr, "numId")
    ilvl_node = first_child_by_local_name(num_pr, "ilvl")
    num_id = xml_attr_by_local_name(num_id_node, "val") if num_id_node is not None else None
    ilvl_str = xml_attr_by_local_name(ilvl_node, "val") if ilvl_node is not None else "0"
    if not num_id:
        return None
    try:
        ilvl = int(ilvl_str) if ilvl_str else 0
    except (TypeError, ValueError):
        ilvl = 0
    fmt = numbering_index.get((num_id, ilvl)) or numbering_index.get((num_id, 0))
    if fmt is None:
        return None
    return (num_id, ilvl, fmt)


def _docx_render_paragraph_block(
    text: str,
    heading: int,
    list_info: tuple[str, int, str] | None,
    list_counter: dict[str, int],
) -> str:
    """Render a paragraph as a list item, heading, or plain block."""
    if list_info is not None:
        num_id, ilvl, fmt = list_info
        indent = "  " * ilvl
        if fmt == "decimal":
            count = list_counter.get(num_id, 0) + 1
            list_counter[num_id] = count
            marker = f"{count}. "
        else:
            marker = "- "
        return f"{indent}{marker}{text}"
    if heading:
        return ("#" * heading) + " " + text
    return text


def docx_heading_level(p_el: _Element) -> int:
    for node in p_el.iter():
        if local_name(node.tag) == "pStyle":
            value = xml_attr_by_local_name(node, "val")
            if not value:
                continue
            lowered = value.lower()
            if lowered.startswith("heading"):
                digits = "".join(ch for ch in lowered if ch.isdigit())
                if digits:
                    return max(1, min(6, int(digits)))
            if lowered in {"title", "subtitle"}:
                return 1
    return 0


def pptx_to_markdown(zf: SafeZipReader, run_dir: Path) -> tuple[str, list[str], list[dict]]:
    import xml.etree.ElementTree as ET

    def slide_index(name: str) -> int:
        match = re.search(r"slide(\d+)\.xml", name)
        return int(match.group(1)) if match else 0

    slide_names = sorted(
        (name for name in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
        key=slide_index,
    )
    builder = _MarkdownLineBuilder()
    native_source_spans: list[dict] = []
    image_artifacts: list[str] = []
    for idx, name in enumerate(slide_names, start=1):
        root = ET.fromstring(zf.read_bytes(name))
        shape_texts = _pptx_slide_text(root)
        image_lines, slide_artifacts = extract_office_images(
            zf=zf,
            part_name=name,
            rels_name=f"ppt/slides/_rels/slide{idx}.xml.rels",
            run_dir=run_dir,
            output_prefix=f"office/slide_{idx:03d}",
            alt_prefix=f"Slide {idx} Image",
        )
        image_artifacts.extend(slide_artifacts)
        if shape_texts or image_lines:
            _append_pptx_slide_section(builder, native_source_spans, idx, shape_texts, image_lines)

        notes_name = f"ppt/notesSlides/notesSlide{idx}.xml"
        if notes_name in zf.namelist():
            notes_root = ET.fromstring(zf.read_bytes(notes_name))
            notes = drawing_paragraphs(notes_root)
            if notes:
                _append_pptx_notes_section(builder, idx, notes)
    return builder.build(), image_artifacts, native_source_spans


class _MarkdownLineBuilder:
    """Build Markdown by joining blocks with blank lines while tracking line numbers."""

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._line_count = 0

    def append_block(self, text: str) -> tuple[int, int]:
        """Append a block and return its (start_line, end_line) in the rendered Markdown."""
        if not text:
            return (0, 0)
        block_lines = text.count("\n") + 1
        start_line = self._line_count + 2 if self._parts else 1
        self._parts.append(text)
        self._line_count = start_line + block_lines - 1
        return (start_line, self._line_count)

    def build(self) -> str:
        return "\n\n".join(self._parts)


def _pptx_slide_text(root: _Element) -> list[tuple[str | None, str]]:
    """Flatten slide text into (shape_id, paragraph_text) pairs in document order."""
    shapes = drawing_shapes(root)
    if shapes:
        return [(shape_id, text) for shape_id, texts in shapes for text in texts]
    return [(None, text) for text in drawing_paragraphs(root)]


def drawing_shapes(root: _Element) -> list[tuple[str, list[str]]]:
    """Return (shape_id, paragraph_texts) for each shape that carries text.

    Duplicate paragraph text within a slide is collapsed (mirrors the pre-existing
    drawing_paragraphs behavior) so the same line is not emitted twice; shapes with
    identical text therefore share their first occurrence's shape_id.
    """
    shapes: list[tuple[str, list[str]]] = []
    for sp in iter_by_local_name(root, "sp"):
        shape_id = _shape_identifier(sp)
        paragraphs: list[str] = []
        for paragraph in iter_by_local_name(sp, "p"):
            text = xml_text(paragraph)
            if text and text not in paragraphs:
                paragraphs.append(text)
        if paragraphs:
            shapes.append((shape_id, paragraphs))
    return shapes


def _shape_identifier(sp: _Element) -> str:
    """Return the cNvPr id of a shape, falling back to its name."""
    for nv_sp_pr in iter_by_local_name(sp, "nvSpPr"):
        for cnv_pr in iter_by_local_name(nv_sp_pr, "cNvPr"):
            identifier = xml_attr_by_local_name(cnv_pr, "id")
            if identifier:
                return identifier
            name = xml_attr_by_local_name(cnv_pr, "name")
            if name:
                return name
    return ""


def _append_pptx_slide_section(
    builder: _MarkdownLineBuilder,
    native_source_spans: list[dict],
    slide_idx: int,
    shape_texts: list[tuple[str | None, str]],
    image_lines: list[str],
) -> None:
    title_text = shape_texts[0][1] if shape_texts else ""
    if title_text:
        heading = f"# Slide {slide_idx}: {title_text}"
        title_shape_id = shape_texts[0][0]
        body = shape_texts[1:]
    else:
        heading = f"# Slide {slide_idx}"
        title_shape_id = None
        body = shape_texts
    for shape_id, text in [(title_shape_id, heading), *body]:
        start_line, end_line = builder.append_block(text)
        if shape_id:
            native_source_spans.append({
                "converted_line_start": start_line,
                "converted_line_end": end_line,
                "precision": "pptx_shape",
                "location": {"slide": slide_idx, "shape_id": shape_id},
            })
    for image_line in image_lines:
        builder.append_block(image_line)


def _append_pptx_notes_section(builder: _MarkdownLineBuilder, slide_idx: int, notes: list[str]) -> None:
    for text in [f"## Slide {slide_idx} Notes", *notes]:
        builder.append_block(text)


def extract_office_images(
    zf: SafeZipReader,
    part_name: str,
    rels_name: str,
    run_dir: Path,
    output_prefix: str,
    alt_prefix: str,
) -> tuple[list[str], list[str]]:
    import xml.etree.ElementTree as ET

    if part_name not in zf.namelist() or rels_name not in zf.namelist():
        return [], []

    root = ET.fromstring(zf.read_bytes(part_name))
    relationships = _office_relationship_targets(zf, rels_name)
    lines: list[str] = []
    copied: list[str] = []
    seen_sources: set[str] = set()
    part_dir = posixpath.dirname(part_name)
    target_root = run_dir / "images"

    for node in root.iter():
        if local_name(node.tag) != "blip":
            continue
        rel_id = xml_attr_by_local_name(node, "embed")
        target = relationships.get(rel_id or "")
        if not target:
            continue
        source_name = posixpath.normpath(posixpath.join(part_dir, target))
        if source_name in seen_sources or source_name not in zf.namelist():
            continue
        if Path(source_name).suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        seen_sources.add(source_name)
        markdown_src = _copy_office_image(zf, source_name, target_root, output_prefix)
        lines.append(f"![{alt_prefix} {len(lines) + 1}]({markdown_src})")
        copied.append(markdown_src)

    return lines, copied


def _office_relationship_targets(zf: SafeZipReader, rels_name: str) -> dict[str, str]:
    import xml.etree.ElementTree as ET

    try:
        rels_root = ET.fromstring(zf.read_bytes(rels_name))
    except ET.ParseError:
        return {}
    relationships: dict[str, str] = {}
    for rel in list(rels_root):
        rel_id = xml_attr_by_local_name(rel, "Id")
        target = xml_attr_by_local_name(rel, "Target")
        mode = (xml_attr_by_local_name(rel, "TargetMode") or "").lower()
        if rel_id and target and mode != "external":
            relationships[rel_id] = target
    return relationships


def _copy_office_image(zf: SafeZipReader, source_name: str, target_root: Path, output_prefix: str) -> str:
    rel_output = Path(output_prefix) / Path(source_name).name
    dst = target_root / rel_output
    dst.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(dst, zf.read_bytes(source_name))
    return "images/" + rel_output.as_posix()


def write_pptx_content_list(text: str, run_dir: Path) -> dict:
    content_list: list[dict] = []
    matches = list(re.finditer(r"(?m)^# Slide\s+(\d+)(?::[^\n]*)?$", text))
    for i, match in enumerate(matches):
        slide_no = int(match.group(1))
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        slide_text = text[start:end].strip()
        if slide_text:
            content_list.append({
                "page_idx": slide_no - 1,
                "type": "text",
                "text": slide_text,
            })

    if not content_list:
        return {}

    path = run_dir / "pptx_content_list.json"
    atomic_write_json(path, content_list, indent=2, trailing_newline=False)
    return {
        "source_md_path": str(run_dir / "converted.md"),
        "content_list_path": str(path),
        "content_list_v2_path": None,
        "middle_json_path": None,
        "assets_dir": None,
        "converter": "office_xml_pptx",
    }


def xlsx_to_markdown(zf: SafeZipReader) -> tuple[str, list[dict]]:
    import xml.etree.ElementTree as ET

    shared_strings = xlsx_shared_strings(zf)
    sheet_names = xlsx_sheet_names(zf)

    def sheet_index(name: str) -> int:
        match = re.search(r"sheet(\d+)\.xml", name)
        return int(match.group(1)) if match else 0

    worksheet_names = sorted(
        (name for name in zf.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)),
        key=sheet_index,
    )

    builder = _MarkdownLineBuilder()
    native_source_spans: list[dict] = []
    for idx, name in enumerate(worksheet_names, start=1):
        root = ET.fromstring(zf.read_bytes(name))
        rows, cell_range = _xlsx_rows_and_cell_range(root, shared_strings)
        if rows:
            title = sheet_names[idx - 1] if idx - 1 < len(sheet_names) else f"Sheet {idx}"
            builder.append_block(f"# {title}")
            table_start, table_end = builder.append_block(rows_to_markdown_table(rows))
            if cell_range is not None:
                native_source_spans.append({
                    "converted_line_start": table_start,
                    "converted_line_end": table_end,
                    "precision": "xlsx_cell_range",
                    "location": {"sheet": title, "start": cell_range[0], "end": cell_range[1]},
                })
    return builder.build(), native_source_spans


def _xlsx_rows_and_cell_range(
    root: _Element, shared_strings: list[str]
) -> tuple[list[list[str]], tuple[str, str] | None]:
    """Return worksheet rows and the (start_cell, end_cell) range of non-empty rows."""
    rows: list[list[str]] = []
    first_cell: str | None = None
    last_cell: str | None = None
    for row_el in iter_by_local_name(root, "row"):
        values: list[str] = []
        row_refs: list[str] = []
        for cell in [c for c in list(row_el) if local_name(c.tag) == "c"]:
            values.append(xlsx_cell_value(cell, shared_strings))
            ref = xml_attr_by_local_name(cell, "r")
            if ref:
                row_refs.append(ref)
        if any(value.strip() for value in values):
            rows.append(values)
            if row_refs:
                if first_cell is None:
                    first_cell = row_refs[0]
                last_cell = row_refs[-1]
    if first_cell is None or last_cell is None:
        return rows, None
    return rows, (first_cell, last_cell)


def drawing_paragraphs(root: _Element) -> list[str]:
    paragraphs: list[str] = []
    for p in iter_by_local_name(root, "p"):
        text = xml_text(p)
        if text and text not in paragraphs:
            paragraphs.append(text)
    return paragraphs


def xlsx_shared_strings(zf: SafeZipReader) -> list[str]:
    import xml.etree.ElementTree as ET

    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read_bytes("xl/sharedStrings.xml"))
    return [xml_text(si) for si in iter_by_local_name(root, "si")]


def xlsx_sheet_names(zf: SafeZipReader) -> list[str]:
    import xml.etree.ElementTree as ET

    if "xl/workbook.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read_bytes("xl/workbook.xml"))
    names: list[str] = []
    for sheet in iter_by_local_name(root, "sheet"):
        name = xml_attr_by_local_name(sheet, "name")
        if name:
            names.append(name)
    return names


def xlsx_cell_value(cell: _Element, shared_strings: list[str]) -> str:
    cell_type = xml_attr_by_local_name(cell, "t")
    value_node = first_child_by_local_name(cell, "v")
    if cell_type == "inlineStr":
        return xml_text(cell)
    if value_node is None or value_node.text is None:
        return ""
    raw = value_node.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    return raw
