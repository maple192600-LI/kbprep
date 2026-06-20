from __future__ import annotations

import posixpath
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

from lxml.etree import _Element

from ..atomic_io import atomic_write_bytes, atomic_write_json
from ..supported_formats import IMAGE_EXTENSIONS
from ..zip_safety import SafeZipReader, ZipSafetyError, open_safe_zip


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
    try:
        with open_safe_zip(input_p) as zf:
            if ext == ".docx":
                markdown, image_artifacts = docx_to_markdown(zf, run_dir)
            elif ext == ".pptx":
                markdown, image_artifacts = pptx_to_markdown(zf, run_dir)
            elif ext == ".xlsx":
                markdown = xlsx_to_markdown(zf)
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
    return markdown.strip() + "\n", warnings, artifacts


def docx_to_markdown(zf: SafeZipReader, run_dir: Path) -> tuple[str, list[str]]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(zf.read_bytes("word/document.xml"))
    body = first_child_by_local_name(root, "body")
    if body is None:
        return "", []

    lines: list[str] = []
    for child in list(body):
        local = local_name(child.tag)
        if local == "p":
            text = xml_text(child)
            if text:
                heading = docx_heading_level(child)
                lines.append(("#" * heading + " " + text) if heading else text)
        elif local == "tbl":
            table = word_table_to_markdown(child)
            if table:
                lines.append(table)
    image_lines, image_artifacts = extract_office_images(
        zf=zf,
        part_name="word/document.xml",
        rels_name="word/_rels/document.xml.rels",
        run_dir=run_dir,
        output_prefix="office/docx",
        alt_prefix="DOCX Image",
    )
    if image_lines:
        lines.extend(["## Embedded Images", *image_lines])
    return "\n\n".join(lines), image_artifacts


def pptx_to_markdown(zf: SafeZipReader, run_dir: Path) -> tuple[str, list[str]]:
    import xml.etree.ElementTree as ET

    def slide_index(name: str) -> int:
        match = re.search(r"slide(\d+)\.xml", name)
        return int(match.group(1)) if match else 0

    slide_names = sorted(
        (name for name in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
        key=slide_index,
    )
    sections: list[str] = []
    image_artifacts: list[str] = []
    for idx, name in enumerate(slide_names, start=1):
        root = ET.fromstring(zf.read_bytes(name))
        paragraphs = drawing_paragraphs(root)
        image_lines, slide_artifacts = extract_office_images(
            zf=zf,
            part_name=name,
            rels_name=f"ppt/slides/_rels/slide{idx}.xml.rels",
            run_dir=run_dir,
            output_prefix=f"office/slide_{idx:03d}",
            alt_prefix=f"Slide {idx} Image",
        )
        image_artifacts.extend(slide_artifacts)
        if paragraphs or image_lines:
            title = paragraphs[0] if paragraphs else ""
            body = paragraphs[1:] if paragraphs else []
            section_lines = [f"# Slide {idx}: {title}"] if title else [f"# Slide {idx}"]
            section_lines.extend(body)
            section_lines.extend(image_lines)
            sections.append("\n\n".join(section_lines))

        notes_name = f"ppt/notesSlides/notesSlide{idx}.xml"
        if notes_name in zf.namelist():
            notes_root = ET.fromstring(zf.read_bytes(notes_name))
            notes = drawing_paragraphs(notes_root)
            if notes:
                sections.append("\n\n".join([f"## Slide {idx} Notes", *notes]))
    return "\n\n".join(sections), image_artifacts


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

    rels_root = ET.fromstring(zf.read_bytes(rels_name))
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


def xlsx_to_markdown(zf: SafeZipReader) -> str:
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

    sections: list[str] = []
    for idx, name in enumerate(worksheet_names, start=1):
        root = ET.fromstring(zf.read_bytes(name))
        rows: list[list[str]] = []
        for row_el in iter_by_local_name(root, "row"):
            values: list[str] = []
            for cell in [c for c in list(row_el) if local_name(c.tag) == "c"]:
                values.append(xlsx_cell_value(cell, shared_strings))
            if any(value.strip() for value in values):
                rows.append(values)
        if rows:
            title = sheet_names[idx - 1] if idx - 1 < len(sheet_names) else f"Sheet {idx}"
            sections.append("\n\n".join([f"# {title}", rows_to_markdown_table(rows)]))
    return "\n\n".join(sections)


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


def word_table_to_markdown(tbl_el: _Element) -> str:
    rows: list[list[str]] = []
    for tr in [n for n in tbl_el.iter() if local_name(n.tag) == "tr"]:
        cells = [xml_text(tc) for tc in list(tr) if local_name(tc.tag) == "tc"]
        if any(cell.strip() for cell in cells):
            rows.append(cells)
    return rows_to_markdown_table(rows)


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
