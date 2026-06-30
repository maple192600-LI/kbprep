"""Lightweight EPUB XHTML extraction."""

from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from .atomic_io import atomic_write_bytes, atomic_write_text
from .supported_formats import IMAGE_EXTENSIONS
from .zip_safety import SafeZipReader, ZipSafetyError, open_safe_zip

_BEAUTIFUL_SOUP: Any
_NAVIGABLE_STRING: Any
_TAG: Any
try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:
    _BEAUTIFUL_SOUP = None
    _NAVIGABLE_STRING = str
    _TAG = object
else:
    _BEAUTIFUL_SOUP = BeautifulSoup
    _NAVIGABLE_STRING = NavigableString
    _TAG = Tag

_SKIP_TAGS = {"script", "style", "nav", "footer", "header", "noscript"}
_CONTAINER_TAGS = {"html", "body", "main", "article", "section", "div"}
_BLOCK_TAGS = {"p", "blockquote", "table", "ul", "ol", "pre", "img", *_CONTAINER_TAGS}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def analyze_epub(input_path: str) -> dict:
    markdown, warnings, spine_count, _image_assets = extract_epub_markdown(Path(input_path))
    text = re.sub(r"\s+", " ", markdown).strip()
    return {
        "page_count": spine_count,
        "chapter_count": spine_count,
        "total_text_length": len(text),
        "text_layer_health": "needs_conversion",
        "needs_ocr": False,
        "recommended_pipeline": "epub_xhtml",
        "conversion_strategy": "epub_xhtml",
        "warnings": warnings,
    }


def convert_epub(input_path: Path, output_path: Path, run_dir: Path | None = None) -> tuple[dict, list[str]]:
    markdown, warnings, _spine_count, image_assets = extract_epub_markdown(input_path, run_dir)
    if not markdown.strip():
        raise ValueError(f"{input_path.name} did not contain extractable EPUB XHTML text.")
    atomic_write_text(output_path, markdown.rstrip() + "\n")
    return {
        "source_md_path": str(output_path),
        "content_list_path": None,
        "content_list_v2_path": None,
        "middle_json_path": None,
        "assets_dir": None,
        "converter": "epub_xhtml",
        "epub_image_assets": {
            "copied_count": len(image_assets),
            "copied": image_assets[:50],
        },
        "warnings": warnings,
    }, warnings


def extract_epub_markdown(input_path: Path, run_dir: Path | None = None) -> tuple[str, list[str], int, list[str]]:
    warnings: list[str] = []
    image_assets: list[str] = []
    if not zipfile.is_zipfile(input_path):
        raise ValueError(f"{input_path.name} is not a valid EPUB ZIP container.")

    try:
        with open_safe_zip(input_path) as archive:
            rootfile = _find_rootfile(archive)
            opf_dir = posixpath.dirname(rootfile)
            spine_paths = _spine_xhtml_paths(archive, rootfile)
            if not spine_paths:
                warnings.append("W_EPUB_NO_SPINE: EPUB spine missing; using sorted XHTML/HTML files.")
                spine_paths = _fallback_html_paths(archive)
            chapters = _epub_chapters(archive, opf_dir, spine_paths, run_dir, image_assets, warnings)
    except ZipSafetyError as error:
        raise ValueError(f"{input_path.name} exceeds EPUB ZIP safety limits: {error}") from error

    markdown = "\n\n".join(chapters).strip()
    return markdown + ("\n" if markdown else ""), warnings, len(chapters), image_assets


def _fallback_html_paths(archive: SafeZipReader) -> list[str]:
    return sorted(name for name in archive.namelist() if name.lower().endswith((".xhtml", ".html", ".htm")))


def _epub_chapters(
    archive: SafeZipReader,
    opf_dir: str,
    spine_paths: list[str],
    run_dir: Path | None,
    image_assets: list[str],
    warnings: list[str],
) -> list[str]:
    chapters: list[str] = []
    for href in spine_paths:
        path = _resolve_epub_path(opf_dir, href)
        if not archive.has_entry(path):
            warnings.append(f"W_EPUB_MISSING_ITEM: {path}")
            continue
        html = archive.read_text(path, encoding="utf-8", errors="replace")
        md = html_to_markdown(html, base_path=path, zf=archive, run_dir=run_dir, image_assets=image_assets)
        if md:
            chapters.append(md)
    return chapters


def _find_rootfile(archive: SafeZipReader) -> str:
    try:
        container = archive.read_bytes("META-INF/container.xml")
        root = ET.fromstring(container)
        for elem in root.iter():
            full_path = elem.attrib.get("full-path")
            if full_path:
                return full_path
    except (KeyError, ET.ParseError):
        pass
    candidates = [name for name in archive.namelist() if name.lower().endswith(".opf")]
    if not candidates:
        raise ValueError("EPUB package document (.opf) not found.")
    return candidates[0]


def _spine_xhtml_paths(archive: SafeZipReader, rootfile: str) -> list[str]:
    opf = ET.fromstring(archive.read_bytes(rootfile))
    manifest: dict[str, str] = {}
    spine_ids: list[str] = []
    for elem in opf.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "item":
            _record_manifest_item(elem, manifest)
        elif tag == "itemref":
            idref = elem.attrib.get("idref")
            if idref:
                spine_ids.append(idref)
    return [manifest[idref] for idref in spine_ids if idref in manifest]


def _record_manifest_item(elem: ET.Element, manifest: dict[str, str]) -> None:
    item_id = elem.attrib.get("id")
    href = elem.attrib.get("href")
    media_type = elem.attrib.get("media-type", "")
    if item_id and href and media_type in {"application/xhtml+xml", "text/html"}:
        manifest[item_id] = href


def html_to_markdown(
    html: str,
    base_path: str = "",
    zf: SafeZipReader | None = None,
    run_dir: Path | None = None,
    image_assets: list[str] | None = None,
) -> str:
    if _BEAUTIFUL_SOUP is None:
        _copy_fallback_epub_images(html, base_path, zf, run_dir, image_assets if image_assets is not None else [])
        from .converters.html import html_to_markdown as fallback_html_to_markdown

        return fallback_html_to_markdown(html)
    soup = _BEAUTIFUL_SOUP(html, "html.parser")
    for tag in soup(list(_SKIP_TAGS)):
        tag.decompose()
    footnote_ids, footnote_notes = _collect_footnotes(soup)
    copier = _EpubImageCopier(
        base_path,
        zf,
        run_dir,
        image_assets if image_assets is not None else [],
        footnote_ids,
    )
    body = soup.body or soup
    markdown = _clean_markdown_lines(_block_lines(body, copier))
    if footnote_notes:
        notes_block = "\n".join(f"[^{num}]: {text}" for num, text in footnote_notes)
        markdown = f"{markdown}\n\n{notes_block}" if markdown else notes_block
    return markdown


class _EpubImageCopier:
    def __init__(
        self,
        base_path: str,
        archive: SafeZipReader | None,
        run_dir: Path | None,
        image_assets: list[str],
        footnote_ids: dict[str, int] | None = None,
    ) -> None:
        self.base_path = base_path
        self.archive = archive
        self.run_dir = run_dir
        self.image_assets = image_assets
        self.footnote_ids = footnote_ids or {}

    def markdown_src(self, src: str) -> str:
        if self.archive is None or self.run_dir is None or _is_external(src):
            return src
        source_name = _resolve_image_path(self.base_path, src)
        if not source_name or not self.archive.has_entry(source_name):
            return src
        if Path(source_name).suffix.lower() not in IMAGE_EXTENSIONS:
            return src

        rel_output = Path("epub") / Path(*source_name.split("/"))
        dst = self.run_dir / "images" / rel_output
        dst.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(dst, self.archive.read_bytes(source_name))
        markdown_src = "images/" + rel_output.as_posix()
        if markdown_src not in self.image_assets:
            self.image_assets.append(markdown_src)
        return markdown_src


def _copy_fallback_epub_images(
    html: str,
    base_path: str,
    archive: SafeZipReader | None,
    run_dir: Path | None,
    image_assets: list[str],
) -> None:
    if archive is None or run_dir is None:
        return
    try:
        root = ET.fromstring(html)
    except ET.ParseError:
        return
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1].lower() != "img":
            continue
        _copy_fallback_epub_image(base_path, str(elem.attrib.get("src") or ""), archive, run_dir, image_assets)


def _copy_fallback_epub_image(
    base_path: str,
    src: str,
    archive: SafeZipReader,
    run_dir: Path,
    image_assets: list[str],
) -> None:
    if not src or _is_external(src):
        return
    source_name = _resolve_image_path(base_path, src)
    if not archive.has_entry(source_name) or Path(source_name).suffix.lower() not in IMAGE_EXTENSIONS:
        return
    rel_output = _fallback_image_output_path(src, source_name)
    dst = run_dir / "images" / rel_output
    dst.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(dst, archive.read_bytes(source_name))
    markdown_src = "images/" + rel_output.as_posix()
    if markdown_src not in image_assets:
        image_assets.append(markdown_src)


def _fallback_image_output_path(src: str, source_name: str) -> Path:
    clean_src = unquote(src.strip().split("#", 1)[0].split("?", 1)[0])
    parts = [part for part in posixpath.normpath(clean_src).split("/") if part not in {"", ".", ".."}]
    if not parts:
        parts = [Path(source_name).name]
    return Path(*parts)


def _block_lines(node: Any, copier: _EpubImageCopier) -> list[str]:
    if isinstance(node, _NAVIGABLE_STRING):
        text = _clean(str(node))
        return [text] if text else []
    if not isinstance(node, _TAG):
        return []
    name = _tag_name(node)
    if name in _SKIP_TAGS:
        return []
    if name in _HEADING_TAGS:
        return _heading_lines(node, copier, int(name[1]))
    if name in {"p", "blockquote", "pre"}:
        return _paragraph_lines(node, copier, name)
    if name == "table":
        table = _table_to_markdown(node)
        return [table] if table else []
    if name in {"ul", "ol"}:
        return _list_lines(node, copier, ordered=name == "ol")
    if name == "img":
        image = _inline_text(node, copier)
        return [image] if image else []
    if name in _CONTAINER_TAGS:
        return _children_block_lines(node, copier)
    text = _inline_text(node, copier)
    return [text] if text else _children_block_lines(node, copier)


def _heading_lines(node: Any, copier: _EpubImageCopier, level: int) -> list[str]:
    heading = _heading_text(node, copier)
    lines = [f"{'#' * min(level, 6)} {heading}"] if heading else []
    for child in node.children:
        if isinstance(child, _TAG) and _tag_name(child) in _BLOCK_TAGS:
            lines.extend(_block_lines(child, copier))
    return lines


def _paragraph_lines(node: Any, copier: _EpubImageCopier, name: str) -> list[str]:
    text = _inline_without_block_children(node, copier)
    lines = [_quote_or_plain(name, text)] if text else []
    for child in node.children:
        if isinstance(child, _TAG) and _tag_name(child) in _BLOCK_TAGS:
            lines.extend(_block_lines(child, copier))
    return lines


def _children_block_lines(node: Any, copier: _EpubImageCopier) -> list[str]:
    lines: list[str] = []
    for child in node.children:
        lines.extend(_block_lines(child, copier))
    return lines


def _inline_text(node: Any, copier: _EpubImageCopier) -> str:
    if isinstance(node, _NAVIGABLE_STRING):
        return _clean(str(node))
    if not isinstance(node, _TAG):
        return ""
    name = _tag_name(node)
    if name in _SKIP_TAGS:
        return ""
    if name == "br":
        return "  \n"
    if name in {"strong", "b"}:
        inner = _inline_children(node, copier)
        return f"**{inner}**" if inner else ""
    if name in {"em", "i"}:
        inner = _inline_children(node, copier)
        return f"*{inner}*" if inner else ""
    if name == "code":
        inner = node.get_text("", strip=True)
        return f"`{inner}`" if inner else ""
    if name == "a":
        href = _clean(str(node.get("href") or ""))
        target = href[1:] if href.startswith("#") else ""
        if target and target in copier.footnote_ids:
            return f"[^{copier.footnote_ids[target]}]"
        label = _inline_children(node, copier) or href
        return f"[{label}]({href})" if href else label
    if name == "img":
        alt = _clean(str(node.get("alt") or node.get("title") or ""))
        src = _clean(str(node.get("src") or ""))
        return f"![{alt}]({copier.markdown_src(src)})" if src else alt
    return _inline_children(node, copier)


def _inline_children(node: Any, copier: _EpubImageCopier) -> str:
    return _clean(" ".join(_inline_text(child, copier) for child in node.children))


def _heading_text(node: Any, copier: _EpubImageCopier) -> str:
    return _inline_without_block_children(node, copier) or _inline_children(node, copier)


def _inline_without_block_children(node: Any, copier: _EpubImageCopier) -> str:
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, _TAG) and _tag_name(child) in _BLOCK_TAGS:
            continue
        parts.append(_inline_text(child, copier))
    return _clean(" ".join(parts))


def _list_lines(node: Any, copier: _EpubImageCopier, ordered: bool) -> list[str]:
    lines: list[str] = []
    for idx, item in enumerate(node.find_all("li", recursive=False), start=1):
        text = _inline_text(item, copier)
        if text:
            lines.append((f"{idx}. " if ordered else "- ") + text)
    return lines


def _table_to_markdown(table: Any) -> str:
    row_nodes = [tr for tr in table.find_all("tr") if _closest_ancestor_table(tr) is table]
    if not row_nodes:
        return ""
    grid: dict[tuple[int, int], str] = {}
    occupied: set[tuple[int, int]] = set()
    max_col = 0
    for r, tr in enumerate(row_nodes):
        c = 0
        for cell in tr.find_all(["th", "td"], recursive=False):
            while (r, c) in occupied:
                c += 1
            colspan = _int_attr(cell, "colspan")
            rowspan = _int_attr(cell, "rowspan")
            text = _clean(cell.get_text(" ", strip=True)).replace("|", "\\|")
            for dc in range(colspan):
                grid[(r, c + dc)] = text
                if rowspan > 1:
                    for dr in range(1, rowspan):
                        grid[(r + dr, c + dc)] = text
                        occupied.add((r + dr, c + dc))
            c += colspan
            if c > max_col:
                max_col = c
    rows = [[grid.get((r, col), "") for col in range(max_col)] for r in range(len(row_nodes))]
    return _rows_to_markdown_table(rows)


def _rows_to_markdown_table(rows: list[list[str]]) -> str:
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    lines = [
        "| " + " | ".join(padded[0]) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in padded[1:])
    return "\n".join(lines)


def _quote_or_plain(name: str, text: str) -> str:
    return "> " + text if name == "blockquote" else text


def _resolve_epub_path(opf_dir: str, href: str) -> str:
    clean_href = unquote(href.strip().split("#", 1)[0].split("?", 1)[0])
    return posixpath.normpath(posixpath.join(opf_dir, clean_href))


def _resolve_image_path(base_path: str, src: str) -> str:
    clean_src = unquote(src.strip().split("#", 1)[0].split("?", 1)[0])
    if not clean_src:
        return ""
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_path), clean_src))


def _clean_markdown_lines(lines: list[str]) -> str:
    cleaned: list[str] = []
    for line in lines:
        value = line.strip()
        if value and (not cleaned or cleaned[-1] != value):
            cleaned.append(value)
    return "\n\n".join(cleaned).strip()


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _tag_name(node: Any) -> str:
    return (node.name or "").lower()


def _is_external(src: str) -> bool:
    return bool(re.match(r"^(?:https?:)?//|^data:|^mailto:|^#", src, re.IGNORECASE))


def _int_attr(node: Any, name: str) -> int:
    raw = node.get(name) if hasattr(node, "get") else None
    try:
        value = int(raw) if raw else 1
    except (TypeError, ValueError):
        return 1
    return value if value > 0 else 1


def _epub_type(node: Any) -> str:
    raw = node.get("epub:type") if hasattr(node, "get") else None
    return _clean(str(raw or ""))


def _has_class_token(node: Any, tokens: set[str]) -> bool:
    classes = node.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    return any(str(c).lower() in tokens for c in classes)


def _is_footnote_container(node: Any) -> bool:
    if _tag_name(node) not in {"div", "section", "ul", "ol"}:
        return False
    return _has_class_token(node, {"footnotes", "endnotes", "fn-list", "footnote-list"})


def _is_footnote_definition(node: Any) -> bool:
    if _epub_type(node) in {"footnote", "endnote"}:
        return True
    return _has_class_token(node, {"footnote", "endnote", "fn"})


def _collect_footnotes(soup: Any) -> tuple[dict[str, int], list[tuple[int, str]]]:
    """Identify footnote/endnote definition elements, number them by first
    reference order (unreferenced definitions follow in document order), and
    remove them from the tree so they no longer render as body text.

    Supports two patterns: a container shell (``<div class="footnotes">`` holding
    several ``<p>`` children) and standalone definitions
    (``<aside epub:type="footnote">``). Returns ``(id->number, [(number, text)])``.
    """
    definitions = _collect_footnote_definitions(soup)
    defs_by_id: dict[str, Any] = {}
    for elem in definitions:
        note_id = elem.get("id") or elem.get("name")
        if note_id and str(note_id) not in defs_by_id:
            defs_by_id[str(note_id)] = elem

    referenced: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a"):
        href = _clean(str(anchor.get("href") or ""))
        target = href[1:] if href.startswith("#") else ""
        if target and target in defs_by_id and target not in seen:
            seen.add(target)
            referenced.append(target)

    ordered: list[tuple[str | None, Any]] = [(tid, defs_by_id[tid]) for tid in referenced]
    for elem in definitions:
        note_id = elem.get("id") or elem.get("name")
        key = str(note_id) if note_id else None
        if key in seen:
            continue
        ordered.append((key, elem))

    id_to_num: dict[str, int] = {}
    notes: list[tuple[int, str]] = []
    for idx, (key, elem) in enumerate(ordered, start=1):
        text = _clean(elem.get_text(" ", strip=True))
        if not text:
            continue
        if key:
            id_to_num[key] = idx
        notes.append((idx, text))

    for elem in definitions:
        elem.decompose()
    return id_to_num, notes


def _collect_footnote_definitions(soup: Any) -> list[Any]:
    definitions: list[Any] = []
    for elem in soup.find_all(True):
        if not isinstance(elem, _TAG):
            continue
        if _is_footnote_container(elem):
            for child in elem.children:
                if isinstance(child, _TAG) and _clean(child.get_text(" ", strip=True)):
                    definitions.append(child)
        elif _is_footnote_definition(elem):
            parent = elem.parent
            if parent is not None and _is_footnote_container(parent):
                continue
            definitions.append(elem)
    return definitions


def _closest_ancestor_table(node: Any) -> Any:
    parent = node.parent
    while parent is not None:
        if _tag_name(parent) == "table":
            return parent
        parent = parent.parent
    return None
