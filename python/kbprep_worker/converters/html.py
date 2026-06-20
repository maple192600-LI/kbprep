from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from ..atomic_io import atomic_write_text
from ..supported_formats import IMAGE_EXTENSIONS


@dataclass(frozen=True)
class RichHtmlContext:
    assets_dir: Path | None
    source_root: Path | None
    asset_stem: str


def _is_nonlocal_markdown_image(path_text: str) -> bool:
    return bool(re.match(r"^(?:https?:)?//|^data:|^mailto:|^#", path_text, re.IGNORECASE))


def _looks_like_image_reference(path_text: str) -> bool:
    clean = path_text.split("?", 1)[0].split("#", 1)[0]
    return Path(clean).suffix.lower() in IMAGE_EXTENSIONS


def _clean_html_attribute(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(item) for item in value)
    return re.sub(r"\s+", " ", str(value)).strip()


class _HTMLToMarkdownParser(HTMLParser):
    """Small stdlib HTML reader for saved pages and exported web notes."""

    BLOCK_TAGS = {"article", "main", "section", "p", "div", "blockquote", "tr"}
    SKIP_TAGS = {"script", "style", "svg", "noscript", "nav", "header", "footer"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.current: list[str] = []
        self.skip_depth = 0
        self.heading_level: int | None = None
        self.in_li = False
        self.link_stack: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): value for key, value in attrs if value is not None}
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_pending_heading()
            self.heading_level = int(tag[1])
        elif tag == "li":
            self._flush_pending_heading()
            self.in_li = True
        elif tag == "br":
            self._flush()
        elif tag == "a":
            href = (attrs_dict.get("href") or "").strip()
            if href:
                self.link_stack.append((href, len(self.current)))
        elif tag == "img":
            src = (attrs_dict.get("src") or "").strip()
            if src:
                alt = (attrs_dict.get("alt") or attrs_dict.get("title") or "").strip()
                self.current.append(f"![{alt}]({src})")
        elif tag in self.BLOCK_TAGS:
            self._flush_pending_heading()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush(heading_level=self.heading_level)
            self.heading_level = None
        elif tag == "li":
            self._flush(list_item=True)
            self.in_li = False
        elif tag == "a":
            self._close_link()
        elif tag in self.BLOCK_TAGS or tag in {"ul", "ol", "table"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.current.append(text)

    def _close_link(self) -> None:
        if not self.link_stack:
            return
        href, start = self.link_stack.pop()
        if start > len(self.current):
            return
        label = " ".join(self.current[start:]).strip() or href
        del self.current[start:]
        self.current.append(f"[{label}]({href})")

    def _flush_pending_heading(self) -> None:
        self._flush(heading_level=self.heading_level)
        self.heading_level = None

    def _flush(self, heading_level: int | None = None, list_item: bool = False) -> None:
        text = " ".join(self.current).strip()
        self.current = []
        if not text:
            return
        if heading_level:
            self.lines.append(f"{'#' * min(heading_level, 6)} {text}")
        elif list_item:
            self.lines.append(f"- {text}")
        else:
            self.lines.append(text)

    def markdown(self) -> str:
        self._flush(heading_level=self.heading_level, list_item=self.in_li)
        cleaned: list[str] = []
        previous = ""
        for line in self.lines:
            line = line.strip()
            if line and line != previous:
                cleaned.append(line)
                previous = line
        return "\n\n".join(cleaned).strip() + "\n"


class _HTMLPlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts).strip()


def html_to_markdown(
    text: str,
    run_dir: Path | None = None,
    source_stem: str = "html",
    source_root: Path | None = None,
) -> str:
    rich = rich_html_to_markdown(text, run_dir=run_dir, source_stem=source_stem, source_root=source_root)
    if rich.strip():
        return rich
    parser = _HTMLToMarkdownParser()
    parser.feed(text)
    markdown = parser.markdown()
    if markdown.strip() and run_dir and source_root:
        markdown = _rewrite_and_copy_html_markdown_images(markdown, run_dir, source_root)
    return markdown if markdown.strip() else _plain_text_from_html(text) + "\n"


def _plain_text_from_html(text: str) -> str:
    parser = _HTMLPlainTextParser()
    parser.feed(text)
    parser.close()
    return parser.text()


def _rewrite_and_copy_html_markdown_images(markdown: str, run_dir: Path, source_root: Path) -> str:
    assets_dir = run_dir / "images"

    def replace(match: re.Match) -> str:
        alt = match.group(1)
        src = match.group(2).strip()
        rewritten = _copy_html_image_reference(src, assets_dir, source_root)
        return f"![{alt}]({rewritten})" if rewritten else match.group(0)

    return re.sub(r"!\[([^\]]*)\]\(([^)\n]+)\)", replace, markdown)


def rich_html_to_markdown(
    text: str,
    run_dir: Path | None = None,
    source_stem: str = "html",
    source_root: Path | None = None,
) -> str:
    """Convert readable HTML pages while preserving tables, cards, and SVG diagrams.

    Many saved course pages encode important knowledge as visual cards, tables,
    and inline SVG diagrams. The small stdlib fallback intentionally stays simple,
    but this richer path keeps the structure that makes those pages usable in
    Obsidian.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return ""

    soup = BeautifulSoup(text, "lxml")
    _strip_rich_html_noise(soup)
    body = soup.body or soup.find("main") or soup
    ctx = _rich_html_context(soup, run_dir, source_stem, source_root)
    _number_inline_svgs(body)
    lines = _rich_html_block(body, ctx)
    return _clean_rich_html_lines(lines)


def _strip_rich_html_noise(soup: Any) -> None:
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "button"]):
        tag.decompose()


def _rich_html_context(
    soup: Any,
    run_dir: Path | None,
    source_stem: str,
    source_root: Path | None,
) -> RichHtmlContext:
    page_title = _clean_html_attribute(soup.title.get_text(" ", strip=True)) if soup.title else ""
    return RichHtmlContext(
        assets_dir=run_dir / "images" if run_dir else None,
        source_root=source_root,
        asset_stem=page_title or source_stem,
    )


def _number_inline_svgs(body: Any) -> None:
    for index, svg in enumerate(body.find_all("svg"), start=1):
        svg["_kbprep_svg_index"] = str(index)


def _rich_html_inline(node: Any, ctx: RichHtmlContext) -> str:
    if _is_html_text_node(node):
        return _clean_html_attribute(str(node))
    name = _html_node_name(node)
    if not name or name in {"script", "style", "noscript", "svg"}:
        return ""
    if name == "br":
        return "  \n"
    if name in {"strong", "b"}:
        inner = _rich_html_inline_children(node, ctx)
        return f"**{inner}**" if inner else ""
    if name in {"em", "i"}:
        inner = _rich_html_inline_children(node, ctx)
        return f"*{inner}*" if inner else ""
    if name == "code":
        inner = node.get_text("", strip=True)
        return f"`{inner}`" if inner else ""
    if name == "a":
        return _rich_html_link(node, ctx)
    if name == "img":
        return _rich_html_image(node, ctx)
    return _rich_html_inline_children(node, ctx)


def _rich_html_inline_children(node: Any, ctx: RichHtmlContext) -> str:
    return _clean_html_attribute(" ".join(_rich_html_inline(child, ctx) for child in node.children))


def _rich_html_link(node: Any, ctx: RichHtmlContext) -> str:
    href = _clean_html_attribute(node.get("href", ""))
    label = _rich_html_inline_children(node, ctx) or _clean_html_attribute(node.get_text(" ", strip=True)) or href
    return f"[{label}]({href})" if href else label


def _rich_html_image(node: Any, ctx: RichHtmlContext) -> str:
    alt = _clean_html_attribute(node.get("alt") or node.get("title") or "")
    src = _clean_html_attribute(node.get("src", ""))
    if not src:
        return alt
    if src.startswith("assets/logos/"):
        return alt
    rewritten = _rich_html_copy_image(src, ctx)
    return f"![{alt}]({rewritten or src})"


def _rich_html_table_to_md(table: Any) -> str:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if cells:
            rows.append([_escape_table_cell(_clean_html_attribute(cell.get_text(" ", strip=True))) for cell in cells])
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _rich_html_copy_image(src: str, ctx: RichHtmlContext) -> str | None:
    if not ctx.source_root or not ctx.assets_dir:
        return None
    return _copy_html_image_reference(src, ctx.assets_dir, ctx.source_root)


def _rich_html_svg_to_md(svg: Any, ctx: RichHtmlContext) -> str:
    label = _svg_label(svg)
    if not ctx.assets_dir:
        visible_text = _clean_html_attribute(svg.get_text(" ", strip=True))
        return f"> [!info] {label}\n> {visible_text}" if visible_text else f"> [!info] {label}"
    ctx.assets_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", ctx.asset_stem).strip(".-_") or "html"
    index = str(svg.attrs.pop("_kbprep_svg_index", "1")).zfill(2)
    filename = f"{safe_stem}-diagram-{index}.svg"
    atomic_write_text(ctx.assets_dir / filename, _standalone_svg_text(svg))
    return f"![{label}](images/{filename})"


def _svg_label(svg: Any) -> str:
    label = _clean_html_attribute(svg.get("aria-label") or "")
    title = svg.find("title")
    desc = svg.find("desc")
    if not label and title:
        label = _clean_html_attribute(title.get_text(" ", strip=True))
    if not label and desc:
        label = _clean_html_attribute(desc.get_text(" ", strip=True))
    return label or "HTML diagram"


def _rich_html_block(node: Any, ctx: RichHtmlContext, depth: int = 0) -> list[str]:
    if _is_html_text_node(node):
        text_value = _clean_html_attribute(str(node))
        return [text_value] if text_value else []
    name = _html_node_name(node)
    if not name or name in {"script", "style", "noscript", "nav", "header", "footer", "button"}:
        return []
    if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        heading = _rich_html_inline(node, ctx)
        return [f"{'#' * int(name[1])} {heading}"] if heading else []
    if name in {"p", "blockquote"}:
        return _rich_html_paragraph_block(node, ctx, name)
    if name == "svg":
        return [_rich_html_svg_to_md(node, ctx)]
    if name == "table":
        table_md = _rich_html_table_to_md(node)
        return [table_md] if table_md else []
    if name in {"ul", "ol"}:
        return _rich_html_list_block(node, ctx, ordered=name == "ol")
    if name == "li":
        li_text = _rich_html_inline(node, ctx)
        return [f"- {li_text}"] if li_text else []
    if name == "img":
        image = _rich_html_inline(node, ctx)
        return [image] if image else []
    if name in {"div", "main", "body", "html", "[document]"}:
        return _rich_html_container_block(node, ctx, depth)
    if name in {"span", "strong", "b", "em", "i", "a", "code"}:
        value = _rich_html_inline(node, ctx)
        return [value] if value else []
    return _rich_html_child_blocks(node, ctx, depth)


def _rich_html_paragraph_block(node: Any, ctx: RichHtmlContext, name: str) -> list[str]:
    paragraph = _rich_html_inline(node, ctx)
    if not paragraph:
        return []
    if name == "blockquote" or "quote" in _html_node_classes(node):
        return ["> " + paragraph]
    return [paragraph]


def _rich_html_list_block(node: Any, ctx: RichHtmlContext, *, ordered: bool) -> list[str]:
    list_lines: list[str] = []
    for idx, li in enumerate(node.find_all("li", recursive=False), start=1):
        li_text = _rich_html_inline(li, ctx)
        if li_text:
            prefix = f"{idx}. " if ordered else "- "
            list_lines.append(prefix + li_text)
    return ["\n".join(list_lines)] if list_lines else []


def _rich_html_container_block(node: Any, ctx: RichHtmlContext, depth: int) -> list[str]:
    classes = _html_node_classes(node)
    child_lines = _rich_html_card_heading(node, ctx, classes)
    for child in node.children:
        if _should_skip_card_heading(child, classes):
            continue
        child_lines.extend(_rich_html_block(child, ctx, depth + 1))
    return child_lines


def _rich_html_card_heading(node: Any, ctx: RichHtmlContext, classes: set[str]) -> list[str]:
    if not ({"card", "case-card"} & classes):
        return []
    for heading_tag in ["h3", "h4"]:
        found = node.find(heading_tag)
        if found:
            title = _rich_html_inline(found, ctx)
            return [f"#### {title}"] if title else []
    return []


def _should_skip_card_heading(node: Any, classes: set[str]) -> bool:
    name = _html_node_name(node)
    return bool({"card", "case-card"} & classes) and name in {"h3", "h4"}


def _rich_html_child_blocks(node: Any, ctx: RichHtmlContext, depth: int) -> list[str]:
    lines: list[str] = []
    for child in node.children:
        lines.extend(_rich_html_block(child, ctx, depth + 1))
    return lines


def _clean_rich_html_lines(lines: list[str]) -> str:
    cleaned: list[str] = []
    previous = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == previous:
            continue
        cleaned.append(line)
        previous = line
    return "\n\n".join(cleaned).strip() + ("\n" if cleaned else "")


def _is_html_text_node(node: Any) -> bool:
    return getattr(node, "name", None) is None


def _html_node_name(node: Any) -> str:
    return str(getattr(node, "name", "") or "").lower()


def _html_node_classes(node: Any) -> set[str]:
    raw_classes = node.get("class") or []
    if isinstance(raw_classes, str):
        return set(raw_classes.split())
    return {str(item) for item in raw_classes}


def _standalone_svg_text(svg) -> str:
    """Serialize an inline HTML SVG as a valid standalone SVG asset."""
    if "viewBox" not in svg.attrs and "viewbox" in svg.attrs:
        svg["viewBox"] = svg.attrs.pop("viewbox")

    view_box = str(svg.get("viewBox") or "").strip()
    view_box_numbers = _parse_svg_view_box(view_box)
    if view_box_numbers:
        _, _, width, height = view_box_numbers
        root_width = str(svg.get("width") or "").strip()
        root_height = str(svg.get("height") or "").strip()
        if not root_width or root_width.endswith("%"):
            svg["width"] = _format_svg_number(width)
        if not root_height or root_height.endswith("%"):
            svg["height"] = _format_svg_number(height)

    if "preserveAspectRatio" not in svg.attrs:
        svg["preserveAspectRatio"] = "xMidYMid meet"

    svg_text = str(svg)
    root_open = svg_text.split(">", 1)[0]
    if "<svg" in svg_text and "xmlns=" not in root_open:
        svg_text = svg_text.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    return svg_text


def _copy_html_image_reference(src: str, assets_dir: Path, source_root: Path) -> str | None:
    if _is_nonlocal_markdown_image(src):
        return None
    decoded = unquote(src).replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
    if not _looks_like_image_reference(decoded):
        return None
    source_path = (source_root / decoded).resolve()
    try:
        rel = source_path.relative_to(source_root)
    except ValueError:
        return None
    if not source_path.is_file():
        return None
    safe_parts = [part for part in rel.parts if part not in {"", ".", ".."}]
    if not safe_parts:
        return None
    target_path = assets_dir / Path(*safe_parts)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        shutil.copy2(str(source_path), str(target_path))
    return "images/" + Path(*safe_parts).as_posix()


def _parse_svg_view_box(value: str) -> tuple[float, float, float, float] | None:
    parts = re.split(r"[\s,]+", value.strip())
    if len(parts) != 4:
        return None
    try:
        numbers = tuple(float(part) for part in parts)
    except ValueError:
        return None
    if numbers[2] <= 0 or numbers[3] <= 0:
        return None
    return (numbers[0], numbers[1], numbers[2], numbers[3])


def _format_svg_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _escape_table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()
