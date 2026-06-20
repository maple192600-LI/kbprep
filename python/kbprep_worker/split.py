"""
split - block-aware splitting.
Splits blocks into Obsidian-manageable chunks with full traceability.

Supports pdf_like, markdown_note, subtitle_transcript, and generic block splitting.
"""
import json
import logging
import re
from pathlib import Path

from .atomic_io import atomic_write_text

logger = logging.getLogger(__name__)

# ── Chunk size limits ─────────────────────────────────────────────
CHUNK_MIN_CHARS = 300
CHUNK_TARGET_CHARS = 1200
CHUNK_MAX_CHARS = 3500

TRANSCRIPT_TIMESTAMP_RE = re.compile(
    r"^\s*(?:\[(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?\]|"
    r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?\s*(?:-->|-))"
)
TRANSCRIPT_SPEAKER_RE = re.compile(
    r"^\s*(?:speaker|host|interviewer|guest|主持人|嘉宾|讲者|旁白)\s*[:：]",
    re.IGNORECASE,
)


def split_into_chunks(
    blocks: list[dict],
    run_dir: str,
    source_type: str,
    source_hash: str,
    run_id: str,
    split_strategy: str | None = None,
) -> dict:
    """
    Split kept blocks into chunks.
    Returns dict with chunk_count, warnings.
    """
    chunks, warnings = _select_chunks(blocks, source_type, split_strategy)

    run_p = Path(run_dir)
    chunks_dir = run_p / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    _clear_stale_chunks(chunks_dir)

    if not chunks:
        _write_chunk_manifest(run_p, [])
        return {"chunk_count": 0, "warnings": warnings + ["No chunks produced"]}

    manifest_entries = _write_chunks(chunks, chunks_dir, source_type, split_strategy, source_hash, run_id)
    _write_chunk_manifest(run_p, manifest_entries)
    return {"chunk_count": len(manifest_entries), "warnings": warnings}


def _select_chunks(blocks: list[dict], source_type: str, split_strategy: str | None) -> tuple[list[dict], list[str]]:
    warnings = []
    if split_strategy == "preserve_slide_or_page_order":
        chunks = _split_by_page_order(blocks)
    elif source_type == "pdf_like":
        chunks = _split_pdf_like(blocks)
    elif source_type == "markdown_note":
        chunks = _split_markdown_note(blocks)
    elif source_type == "subtitle_transcript":
        chunks = _split_transcript(blocks)
    else:
        chunks = _split_generic(blocks)
        warnings.append("W_GENERIC_SPLITTER_USED: specialized splitter not available for this source type")
    return [chunk for chunk in chunks if chunk.get("text", "").strip()], warnings


def _write_chunks(
    chunks: list[dict],
    chunks_dir: Path,
    source_type: str,
    split_strategy: str | None,
    source_hash: str,
    run_id: str,
) -> list[dict]:
    manifest_entries = []
    for i, chunk in enumerate(chunks):
        chunk_id = f"chunk_{i + 1:04d}"
        text = chunk.get("text", "").strip()
        if not text:
            continue

        heading_path = chunk.get("heading_path", [])
        block_ids = chunk.get("block_ids", [])
        page_start = chunk.get("page_start")
        page_end = chunk.get("page_end")
        source_type_str = source_type
        split_strategy_str = split_strategy or "content_structure"

        frontmatter = _chunk_frontmatter(
            chunk_id=chunk_id,
            source_type=source_type_str,
            split_strategy=split_strategy_str,
            source_hash=source_hash,
            run_id=run_id,
            page_start=page_start,
            page_end=page_end,
            heading_path=heading_path,
            block_ids=block_ids,
            char_count=len(text),
        )
        chunk_file = chunks_dir / f"{chunk_id}.md"
        atomic_write_text(chunk_file, frontmatter + text)

        manifest_entries.append({
            "chunk_id": chunk_id,
            "heading_path": heading_path,
            "block_ids": block_ids,
            "page_start": page_start,
            "page_end": page_end,
            "char_count": len(text),
            "split_strategy": split_strategy_str,
        })
    return manifest_entries


def _write_chunk_manifest(run_p: Path, manifest_entries: list[dict]) -> None:
    manifest_path = run_p / "chunk_manifest.jsonl"
    with open(manifest_path, "w", encoding="utf-8") as f:
        for entry in manifest_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _clear_stale_chunks(chunks_dir: Path) -> None:
    """Remove leftover chunk files before writing fresh ones.

    apply_patch re-runs splitting on the same run_dir; without this, the
    chunk_*.md files from the previous iteration linger and inflate glob-based
    chunk counts, which then diverge from the freshly overwritten manifest.
    """
    for stale in chunks_dir.glob("*.md"):
        stale.unlink()


def _chunk_frontmatter(
    chunk_id: str,
    source_type: str,
    split_strategy: str,
    source_hash: str,
    run_id: str,
    page_start: object,
    page_end: object,
    heading_path: object,
    block_ids: object,
    char_count: int,
) -> str:
    page_range = f"{page_start}-{page_end}" if page_start is not None and page_end is not None else "unknown"
    lines = [
        "---",
        f"chunk_id: {_yaml_value(chunk_id)}",
        f"source_type: {_yaml_plain_value(source_type)}",
        f"split_strategy: {_yaml_plain_value(split_strategy)}",
        f"source_sha256: {_yaml_value(source_hash[:16])}",
        f"run_id: {_yaml_value(run_id)}",
        f"page_range: {_yaml_value(page_range)}",
        f"heading_path: {_yaml_value(heading_path)}",
        f"block_ids: {_yaml_value(block_ids)}",
        f"char_count: {char_count}",
        "---",
        "",
    ]
    return "\n".join(lines) + "\n"


def _yaml_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _yaml_plain_value(value: str) -> str:
    if value and all(char.isalnum() or char in {"_", "-"} for char in value):
        return value
    return _yaml_value(value)


def _split_pdf_like(blocks: list[dict]) -> list[dict]:
    """
    Split PDF-like content by H1/H2/H3 headings, then by block type.
    Priority: H1 > H2 > H3 > block type > page range.
    """
    chunks = []
    current_chunk = _new_chunk()

    for block in blocks:
        text = _kept_block_text(block)
        if not text:
            continue

        if block.get("type", "") == "section_heading":
            current_text = current_chunk.get("text", "").strip()
            if current_text and len(current_text) >= CHUNK_MIN_CHARS:
                chunks.append(current_chunk)
                current_chunk = _new_chunk()
                current_chunk["heading_path"] = block.get("heading_path", [])
            elif current_text:
                # Small chunk: merge heading into current
                pass

        # Check if adding this block would exceed max
        candidate_text = current_chunk.get("text", "") + "\n\n" + text if current_chunk.get("text") else text
        if len(candidate_text) > CHUNK_MAX_CHARS and current_chunk.get("text", "").strip():
            # Flush current chunk if it's big enough
            if len(current_chunk.get("text", "")) >= CHUNK_MIN_CHARS:
                chunks.append(current_chunk)
                current_chunk = _new_chunk()
                current_chunk["heading_path"] = block.get("heading_path", [])

        _append_block_to_chunk(current_chunk, block, text)
        _update_chunk_page_range(current_chunk, block)

        # Check if we've reached target size
        if len(current_chunk.get("text", "")) >= CHUNK_TARGET_CHARS:
            chunks.append(current_chunk)
            current_chunk = _new_chunk()

    # Flush remaining
    if current_chunk.get("text", "").strip():
        chunks.append(current_chunk)

    return chunks


def _split_by_page_order(blocks: list[dict]) -> list[dict]:
    """
    Preserve page/slide boundaries for slide decks and sparse landscape reports.
    This is only used when diagnosis explicitly requests slide/page order.
    """
    chunks = []
    current_chunk = _new_chunk()
    current_page = None

    for block in blocks:
        text = _kept_block_text(block)
        if not text:
            continue

        ps = block.get("page_start")
        block_page = ps if ps is not None else current_page
        candidate_text = current_chunk.get("text", "") + "\n\n" + text if current_chunk.get("text") else text

        page_changed = _page_changed(current_chunk, current_page, block_page)
        too_large = len(candidate_text) > CHUNK_MAX_CHARS and current_chunk.get("text", "").strip()

        if page_changed or too_large:
            chunks.append(current_chunk)
            current_chunk = _new_chunk()

        _append_block_to_chunk(current_chunk, block, text)
        if block.get("heading_path") and not current_chunk.get("heading_path"):
            current_chunk["heading_path"] = block["heading_path"]
        current_page = _update_page_order_range(current_chunk, block, current_page)

    if current_chunk.get("text", "").strip():
        chunks.append(current_chunk)

    return chunks


def _kept_block_text(block: dict) -> str:
    if block.get("status") != "keep":
        return ""
    return block.get("text", "").strip()


def _append_block_to_chunk(chunk: dict, block: dict, text: str) -> None:
    if chunk.get("text"):
        chunk["text"] += "\n\n" + text
    else:
        chunk["text"] = text
    chunk["block_ids"].append(block.get("block_id", ""))


def _update_chunk_page_range(chunk: dict, block: dict) -> None:
    page_start = block.get("page_start")
    page_end = block.get("page_end")
    if page_start is not None and (chunk["page_start"] is None or page_start < chunk["page_start"]):
        chunk["page_start"] = page_start
    if page_end is not None and (chunk["page_end"] is None or page_end > chunk["page_end"]):
        chunk["page_end"] = page_end


def _page_changed(chunk: dict, current_page: object, block_page: object) -> bool:
    return bool(
        chunk.get("text", "").strip()
        and current_page is not None
        and block_page is not None
        and block_page != current_page
    )


def _update_page_order_range(chunk: dict, block: dict, current_page: object) -> object:
    page_start = block.get("page_start")
    page_end = block.get("page_end")
    _update_chunk_page_range(chunk, block)
    if page_start is not None:
        return page_start
    if page_end is not None and current_page is None:
        return page_end
    return current_page


def _split_markdown_note(blocks: list[dict]) -> list[dict]:
    """
    Split Markdown notes by H1/H2/H3 headings.
    Preserves YAML frontmatter, Obsidian links, tags, callouts.
    """
    frontmatter_blocks, body_blocks = _split_leading_frontmatter(blocks)
    chunks = _split_markdown_sections(body_blocks)
    if not chunks:
        return [_chunk_from_blocks(frontmatter_blocks)] if frontmatter_blocks else []
    if frontmatter_blocks:
        _prepend_blocks_to_chunk(chunks[0], frontmatter_blocks)
    return chunks


def _split_leading_frontmatter(blocks: list[dict]) -> tuple[list[dict], list[dict]]:
    kept_blocks = [block for block in blocks if _kept_block_text(block)]
    if not kept_blocks or not _is_frontmatter_block(kept_blocks[0]):
        return [], kept_blocks
    return [kept_blocks[0]], kept_blocks[1:]


def _is_frontmatter_block(block: dict) -> bool:
    lines = _kept_block_text(block).splitlines()
    if len(lines) < 2 or lines[0].strip() != "---":
        return False
    return any(line.strip() == "---" for line in lines[1:])


def _split_markdown_sections(blocks: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    current_chunk = _new_chunk()
    for block in blocks:
        text = _kept_block_text(block)
        if not text:
            continue
        if _starts_markdown_section(block, text, current_chunk):
            chunks.append(current_chunk)
            current_chunk = _new_chunk()
        if _would_exceed_max(current_chunk, text):
            chunks.append(current_chunk)
            current_chunk = _new_chunk()
        _append_block_to_chunk(current_chunk, block, text)
        _update_chunk_page_range(current_chunk, block)
        if len(current_chunk.get("text", "")) >= CHUNK_TARGET_CHARS and block.get("type") != "section_heading":
            chunks.append(current_chunk)
            current_chunk = _new_chunk()
    if current_chunk.get("text", "").strip():
        chunks.append(current_chunk)
    return chunks


def _starts_markdown_section(block: dict, text: str, chunk: dict) -> bool:
    return bool(chunk.get("text") and block.get("type") == "section_heading" and _heading_level(text) <= 3)


def _heading_level(text: str) -> int:
    match = re.match(r"^\s*(#{1,6})\s+", text)
    return len(match.group(1)) if match else 99


def _would_exceed_max(chunk: dict, text: str) -> bool:
    if not chunk.get("text", "").strip():
        return False
    candidate = f"{chunk.get('text', '')}\n\n{text}"
    return len(candidate) > CHUNK_MAX_CHARS


def _prepend_blocks_to_chunk(chunk: dict, blocks: list[dict]) -> None:
    prefix_text = "\n\n".join(_kept_block_text(block) for block in blocks)
    if chunk.get("text"):
        chunk["text"] = f"{prefix_text}\n\n{chunk['text']}"
    else:
        chunk["text"] = prefix_text
    chunk["block_ids"] = [block.get("block_id", "") for block in blocks] + chunk.get("block_ids", [])
    for block in blocks:
        _update_chunk_page_range(chunk, block)


def _chunk_from_blocks(blocks: list[dict]) -> dict:
    chunk = _new_chunk()
    for block in blocks:
        _append_block_to_chunk(chunk, block, _kept_block_text(block))
        _update_chunk_page_range(chunk, block)
    return chunk


def _split_generic(blocks: list[dict]) -> list[dict]:
    """
    Generic splitter: aggregate blocks by order, 1000-2000 chars per chunk.
    Preserves code blocks, tables, and prompts as whole units.
    """
    chunks = []
    current_chunk = _new_chunk()

    for block in blocks:
        if block.get("status") != "keep":
            continue

        text = block.get("text", "").strip()
        if not text:
            continue

        block_type = block.get("type", "")

        # Protected blocks stay together
        if block.get("protected") or block_type in ("code", "table", "prompt"):
            # If current chunk + this block exceeds max, flush first
            candidate = current_chunk.get("text", "") + "\n\n" + text if current_chunk.get("text") else text
            if len(candidate) > CHUNK_MAX_CHARS and current_chunk.get("text", "").strip():
                chunks.append(current_chunk)
                current_chunk = _new_chunk()

        # Check size
        candidate = current_chunk.get("text", "") + "\n\n" + text if current_chunk.get("text") else text
        if len(candidate) > CHUNK_TARGET_CHARS and current_chunk.get("text", "").strip():
            chunks.append(current_chunk)
            current_chunk = _new_chunk()

        # Add to chunk
        if current_chunk.get("text"):
            current_chunk["text"] += "\n\n" + text
        else:
            current_chunk["text"] = text
        current_chunk["block_ids"].append(block.get("block_id", ""))

        # Update heading path
        if block.get("heading_path") and not current_chunk.get("heading_path"):
            current_chunk["heading_path"] = block["heading_path"]

    # Flush remaining
    if current_chunk.get("text", "").strip():
        chunks.append(current_chunk)

    return chunks


def _split_transcript(blocks: list[dict]) -> list[dict]:
    """Split transcripts by paragraph order while preserving utterance order."""
    chunks = []
    current_chunk = _new_chunk()
    for block in blocks:
        text = _kept_block_text(block)
        if not text:
            continue
        boundary = _is_transcript_turn_boundary(text)
        if _should_start_transcript_chunk(current_chunk, text, boundary):
            chunks.append(current_chunk)
            current_chunk = _new_chunk()
        _append_block_to_chunk(current_chunk, block, text)
        _update_chunk_page_range(current_chunk, block)
    if current_chunk.get("text", "").strip():
        chunks.append(current_chunk)
    return chunks


def _is_transcript_turn_boundary(text: str) -> bool:
    first_line = text.lstrip().splitlines()[0] if text.strip() else ""
    return bool(TRANSCRIPT_TIMESTAMP_RE.match(first_line) or TRANSCRIPT_SPEAKER_RE.match(first_line))


def _should_start_transcript_chunk(chunk: dict, text: str, boundary: bool) -> bool:
    if not chunk.get("text", "").strip():
        return False
    candidate = f"{chunk.get('text', '')}\n\n{text}"
    return len(candidate) > CHUNK_MAX_CHARS or (boundary and len(chunk.get("text", "")) >= CHUNK_TARGET_CHARS)


def _new_chunk() -> dict:
    """Create a new empty chunk dict."""
    return {
        "text": "",
        "heading_path": [],
        "block_ids": [],
        "page_start": None,
        "page_end": None,
    }
