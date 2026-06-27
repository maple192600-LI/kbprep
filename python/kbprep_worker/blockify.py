"""
blockify - block-level structuring.
Parses normalized.md into structured blocks with metadata.

Input: normalized.md + page map + image map + heading map
Output: blocks.jsonl (list of block dicts)
"""
import json
import logging
import re
from pathlib import Path

from .structure_patterns import is_step_line

logger = logging.getLogger(__name__)

# ── Raw block types emitted before cleanup/classification ─────────
BLOCK_TYPES = (
    "code",
    "image_evidence",
    "operation_step",
    "paragraph",
    "quote",
    "section_heading",
    "table",
)

# ── Heading patterns ──────────────────────────────────────────────
H_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# ── Image reference pattern ───────────────────────────────────────
IMG_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

# ── Code block pattern ────────────────────────────────────────────
CODE_BLOCK_RE = re.compile(r'^```[\s\S]*?^```', re.MULTILINE)

# ── Table pattern (Markdown) ──────────────────────────────────────
TABLE_RE = re.compile(r'^\|.+\|$\n^\|[\s\-:|]+\|$\n(?:^\|.+\|$\n?)+', re.MULTILINE)

# ── Quote/callout pattern ─────────────────────────────────────────
CALLOUT_RE = re.compile(r'^>\s*\[!(\w+)\]', re.MULTILINE)


def blockify(text: str, source_hash: str, mineru_artifacts: dict | None = None, run_dir: str = "") -> list[dict]:
    """
    Parse normalized markdown into structured blocks.
    Each block has: block_id, source_sha256, page_start, page_end,
    line_start, line_end, heading_path, type, text, images, status,
    risk_tags, protected, confidence.
    """
    lines = text.split("\n")
    builder = _BlockBuilder(source_hash=source_hash, page_map=_build_page_map(text, mineru_artifacts))
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            builder.flush_current(i - 1)
            builder.set_block_start(i + 1)
            i += 1
            continue

        h_match = H_RE.match(line)
        if h_match:
            _consume_heading(builder, line, i, h_match)
            i += 1
            continue

        if stripped.startswith("```"):
            i = _consume_code_block(lines, i, builder)
            continue

        if stripped.startswith("|") and "|" in stripped[1:]:
            next_index = _consume_table(lines, i, builder)
            if next_index is not None:
                i = next_index
                continue

        if _is_standalone_image_line(stripped):
            i = _consume_image_line(builder, line, i)
            continue

        if stripped.startswith(">"):
            i = _consume_callout(lines, i, builder)
            continue

        builder.append_line(line)
        i += 1

    builder.flush_current(len(lines) - 1)
    return builder.blocks


class _BlockBuilder:
    def __init__(self, source_hash: str, page_map: list[dict]) -> None:
        self.source_hash = source_hash
        self.page_map = page_map
        self.blocks: list[dict] = []
        self.block_idx = 0
        self.current_block_lines: list[str] = []
        self.current_block_start = 0
        self.current_heading_path: list[str] = []
        self.heading_stack: list[tuple[int, str]] = []

    def append_line(self, line: str) -> None:
        self.current_block_lines.append(line)

    def set_block_start(self, line_index: int) -> None:
        self.current_block_start = line_index

    def update_heading(self, level: int, title: str) -> None:
        while self.heading_stack and self.heading_stack[-1][0] >= level:
            self.heading_stack.pop()
        self.heading_stack.append((level, title))
        self.current_heading_path = [heading[1] for heading in self.heading_stack]

    def flush_current(self, end_line: int) -> None:
        if not self.current_block_lines:
            return
        self.add_block("\n".join(self.current_block_lines), self.current_block_start, end_line)
        self.current_block_lines = []

    def add_block(
        self,
        text: str,
        line_start: int,
        line_end: int,
        override_type: str | None = None,
        protected: bool = False,
    ) -> None:
        block = _make_block(
            self.block_idx,
            text,
            line_start,
            line_end,
            list(self.current_heading_path),
            self.source_hash,
            self.page_map,
            override_type=override_type,
            protected=protected,
        )
        if block:
            self.blocks.append(block)
            self.block_idx += 1


def _consume_heading(builder: _BlockBuilder, line: str, line_index: int, h_match: re.Match[str]) -> None:
    builder.flush_current(line_index - 1)
    builder.update_heading(len(h_match.group(1)), h_match.group(2).strip())
    builder.add_block(line, line_index, line_index, override_type="section_heading")
    builder.set_block_start(line_index + 1)


def _consume_code_block(lines: list[str], index: int, builder: _BlockBuilder) -> int:
    code_lines = [lines[index]]
    j = index + 1
    while j < len(lines):
        code_lines.append(lines[j])
        if lines[j].strip().startswith("```") and j > index:
            break
        j += 1
    builder.flush_current(index - 1)
    builder.add_block("\n".join(code_lines), index, j, override_type="code", protected=True)
    next_index = j + 1
    builder.set_block_start(next_index)
    return next_index


def _consume_table(lines: list[str], index: int, builder: _BlockBuilder) -> int | None:
    table_lines = [lines[index]]
    j = index + 1
    while j < len(lines) and lines[j].strip().startswith("|"):
        table_lines.append(lines[j])
        j += 1
    if len(table_lines) < 2:
        return None
    builder.flush_current(index - 1)
    builder.add_block("\n".join(table_lines), index, j - 1, override_type="table", protected=True)
    builder.set_block_start(j)
    return j


def _consume_image_line(builder: _BlockBuilder, line: str, line_index: int) -> int:
    builder.flush_current(line_index - 1)
    builder.add_block(line, line_index, line_index, override_type="image_evidence")
    next_index = line_index + 1
    builder.set_block_start(next_index)
    return next_index


def _consume_callout(lines: list[str], index: int, builder: _BlockBuilder) -> int:
    callout_lines = [lines[index]]
    j = index + 1
    while j < len(lines) and (lines[j].strip().startswith(">") or lines[j].strip() == ""):
        if lines[j].strip() == "" and j + 1 < len(lines) and not lines[j + 1].strip().startswith(">"):
            break
        callout_lines.append(lines[j])
        j += 1
    builder.flush_current(index - 1)
    builder.add_block("\n".join(callout_lines), index, j - 1, override_type="quote")
    builder.set_block_start(j)
    return j


def _is_standalone_image_line(stripped: str) -> bool:
    return IMG_RE.search(stripped) is not None and len(stripped) < 200


def _make_block(
    idx: int,
    text: str,
    line_start: int,
    line_end: int,
    heading_path: list[str],
    source_hash: str,
    page_map: list[dict],
    override_type: str | None = None,
    protected: bool = False,
) -> dict | None:
    """Create a block dict from text content."""
    text = text.strip()
    if not text:
        return None

    # Determine block type
    if override_type:
        block_type = override_type
    else:
        block_type = _infer_block_type(text)

    # Find page range
    page_start, page_end = _find_page_range(line_start, line_end, page_map)

    # Extract images
    images = []
    for m in IMG_RE.finditer(text):
        images.append({"alt": m.group(1), "src": m.group(2)})

    block_id = f"b_{idx:06d}"

    return {
        "block_id": block_id,
        "source_sha256": source_hash[:16],
        "page_start": page_start,
        "page_end": page_end,
        "line_start": line_start,
        "line_end": line_end,
        "heading_path": heading_path,
        "type": block_type,
        "text": text,
        "images": images,
        "status": "unclassified",
        "risk_tags": [],
        "protected": protected,
        "confidence": 0.0,
    }


def _infer_block_type(text: str) -> str:
    """Infer block type from content."""
    stripped = text.strip()

    # Code block
    if stripped.startswith("```"):
        return "code"

    # Table
    if stripped.startswith("|"):
        return "table"

    # Heading
    if H_RE.match(stripped):
        return "section_heading"

    # Image
    if IMG_RE.match(stripped) and len(stripped) < 200:
        return "image_evidence"

    # Callout/quote
    if stripped.startswith(">"):
        return "quote"

    # Numbered steps
    if is_step_line(stripped):
        return "operation_step"

    # Default
    return "paragraph"


def _build_page_map(text: str, mineru_artifacts: dict | None = None) -> list[dict]:
    """Build page boundary map from MinerU content_list."""
    if not mineru_artifacts:
        return []

    content_list_path = mineru_artifacts.get("content_list_path")
    if not content_list_path:
        return []

    try:
        content_list = json.loads(Path(content_list_path).read_text(encoding="utf-8"))
        line_offsets = _line_start_offsets(text)
        pages = []
        for item in content_list:
            page_idx = item.get("page_idx", item.get("page", 0))
            item_text = item.get("text", "")
            if item_text:
                pos = text.find(item_text[:40])
                if pos >= 0:
                    pages.append({"page": page_idx, "line": _offset_to_line(pos, line_offsets)})
        pages.sort(key=lambda x: x["line"])
        return pages
    except Exception:
        return []


def extract_pdf_native_source_spans(content_list_path: Path | str, converted_text: str) -> list[dict]:
    """Extract ``pdf_bbox`` native source spans from a MinerU content_list.

    Maps each content block's text to its converted-Markdown line and emits a
    ``pdf_bbox`` native span aligned with typed_node numbering (1-based). See
    ``_parse_pdf_bbox_item`` and ``attach_pdf_native_source_spans`` for the
    no-fabrication guardrails: orphan blocks are skipped, a non-numeric bbox skips
    the whole block, and the text search advances a cursor so repeated blocks
    (headers, buttons, table cells) each map to their own occurrence.
    """
    try:
        content_list = json.loads(Path(content_list_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(content_list, list):
        return []
    line_offsets = _line_start_offsets(converted_text)
    spans: list[dict] = []
    search_from = 0
    for item in content_list:
        parsed = _parse_pdf_bbox_item(item)
        if parsed is None:
            continue
        bbox, page_idx, text = parsed
        needle = text[:40]
        pos = converted_text.find(needle, search_from)
        if pos < 0:
            continue
        search_from = pos + len(needle)
        spans.append(_pdf_bbox_span(page_idx, bbox, _offset_to_line(pos, line_offsets)))
    return spans


def _parse_pdf_bbox_item(item: object) -> tuple[list, int, str] | None:
    """Validate a MinerU content block and return ``(bbox, page_idx, text)``.

    Returns ``None`` when the block lacks a 4-element numeric bbox, an integer
    ``page_idx``, or non-empty text — these blocks are skipped so the extractor
    never fabricates coordinates from malformed OCR output.
    """
    if not isinstance(item, dict):
        return None
    bbox = item.get("bbox")
    page_idx = item.get("page_idx", item.get("page"))
    text = item.get("text", "")
    if (
        not isinstance(bbox, list)
        or len(bbox) != 4
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox)
        or isinstance(page_idx, bool)
        or not isinstance(page_idx, int)
        or not isinstance(text, str)
        or not text
    ):
        return None
    return bbox, page_idx, text


def _pdf_bbox_span(page_idx: int, bbox: list, line: int) -> dict:
    """Build a ``pdf_bbox`` native span from a 0-based ``page_idx`` and 0-based line.

    Both are stored 1-based: lines align with typed_node numbering
    (``canonical_nodes._parse_markdown_blocks`` uses ``start_index + 1``) and the
    source_spans validator requires ``page > 0`` while MinerU ``page_idx`` is 0-based.
    """
    return {
        "converted_line_start": line + 1,
        "converted_line_end": line + 1,
        "precision": "pdf_bbox",
        "location": {"page": page_idx + 1, "bbox": [float(v) for v in bbox]},
    }


def attach_pdf_native_source_spans(artifacts: dict, converted_path: Path) -> None:
    """Attach pdf_bbox native source spans to a MinerU artifacts dict in place.

    Only MinerU OCR routes carry block-level bbox coordinates. When
    ``content_list_path`` is absent (e.g. text-layer routes) nothing is attached,
    keeping the C1R pdf_bbox gap honest. The span writer gates evidence by
    source_kind=pdf, so non-PDF routes that reuse this conversion ignore the
    candidate evidence instead of emitting fabricated coordinates.
    """
    content_list_path = artifacts.get("content_list_path")
    if not content_list_path or not converted_path.exists():
        return
    converted_text = converted_path.read_text(encoding="utf-8")
    if converted_text:
        artifacts["native_source_spans"] = extract_pdf_native_source_spans(content_list_path, converted_text)


def _find_page_range(line_start: int, line_end: int, page_map: list[dict]) -> tuple[int | None, int | None]:
    """Find page range for given line positions."""
    if not page_map:
        return None, None

    page_start = None
    page_end = None
    for pm in page_map:
        if pm["line"] <= line_start:
            page_start = pm["page"]
        if pm["line"] <= line_end:
            page_end = pm["page"]

    return page_start, page_end


def _line_start_offsets(text: str) -> list[int]:
    offsets = [0]
    for match in re.finditer(r"\n", text):
        offsets.append(match.end())
    return offsets


def _offset_to_line(offset: int, line_offsets: list[int]) -> int:
    line = 0
    for idx, start in enumerate(line_offsets):
        if start > offset:
            break
        line = idx
    return line
