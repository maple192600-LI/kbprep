"""
render_outputs - output rendering from blocks.
Renders: cleaned.md, discarded.md, evidence/, blocks.jsonl (updated).
"""
import json
import logging
from pathlib import Path

from .atomic_io import atomic_write_json, atomic_write_text
from .ir_markdown_regeneration import regenerate_blocks_from_ir

logger = logging.getLogger(__name__)

OBSIDIAN_PROFILES = {"obsidian_kb", "curated_obsidian_kb"}


def render(
    blocks: list[dict],
    run_dir: str,
    source_hash: str,
    run_id: str,
    profile: str = "standard",
    source_title: str | None = None,
    render_obsidian: bool = True,
    clean_view: dict | None = None,
) -> None:
    """
    Render output files from classified blocks.
    - cleaned.md: blocks with status=keep
    - discarded.md: blocks with status=discard
    - evidence/: blocks with status=evidence
    """
    run_p = Path(run_dir)
    render_blocks = _blocks_from_clean_view(blocks, clean_view)
    if profile == "standard":
        ir_blocks = regenerate_blocks_from_ir(run_dir=run_p, blocks=render_blocks, clean_view=clean_view)
        if ir_blocks is not None:
            render_blocks = ir_blocks

    keep_blocks = [b for b in render_blocks if b.get("status") == "keep"]
    discard_blocks = [b for b in render_blocks if b.get("status") == "discard"]
    evidence_blocks = [b for b in render_blocks if b.get("status") == "evidence"]
    review_blocks = [b for b in render_blocks if b.get("status") == "review"]

    _render_cleaned_md(keep_blocks, run_p)
    _render_discarded_md(discard_blocks, run_p)
    _render_evidence_md(evidence_blocks, run_p)
    _render_review_md(review_blocks, run_p)
    _render_parts(keep_blocks, run_p)
    _render_obsidian_if_requested(render_blocks, run_dir, source_title, source_hash, run_id, profile, render_obsidian, run_p)

    logger.info("Rendered: cleaned=%d blocks, discarded=%d, evidence=%d, review=%d",
                len(keep_blocks), len(discard_blocks), len(evidence_blocks), len(review_blocks))


def _blocks_from_clean_view(blocks: list[dict], clean_view: dict | None) -> list[dict]:
    if not clean_view or clean_view.get("schema") != "kbprep.clean_view.v1":
        return blocks
    entries = clean_view.get("entries")
    if not isinstance(entries, list):
        return blocks
    by_id = {str(block.get("block_id") or ""): block for block in blocks}
    rendered = []
    for entry in entries:
        block = _block_for_clean_view_entry(entry, by_id)
        if block is None:
            return blocks
        rendered.append(block)
    return rendered if _clean_view_covers_blocks(rendered, blocks) else blocks


def _block_for_clean_view_entry(entry: object, by_id: dict[str, dict]) -> dict | None:
    if not isinstance(entry, dict):
        return None
    block = by_id.get(str(entry.get("block_id") or ""))
    if block is None:
        return None
    rendered = dict(block)
    rendered["status"] = str(entry.get("status") or block.get("status") or "")
    return rendered


def _clean_view_covers_blocks(rendered: list[dict], blocks: list[dict]) -> bool:
    rendered_ids = [str(block.get("block_id") or "") for block in rendered]
    block_ids = [str(block.get("block_id") or "") for block in blocks]
    return len(rendered_ids) == len(block_ids) and set(rendered_ids) == set(block_ids)


def _render_cleaned_md(keep_blocks: list[dict], run_p: Path) -> None:
    cleaned_lines = [_readable_text(block) for block in keep_blocks if _readable_text(block)]
    atomic_write_text(run_p / "cleaned.md", "\n\n".join(cleaned_lines))


def _render_discarded_md(discard_blocks: list[dict], run_p: Path) -> None:
    atomic_write_text(run_p / "discarded.md", _render_blocks_with_metadata(discard_blocks))


def _render_evidence_md(evidence_blocks: list[dict], run_p: Path) -> None:
    evidence_dir = run_p / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    if evidence_blocks:
        atomic_write_text(evidence_dir / "marketing_pages.md", _render_blocks_with_metadata(evidence_blocks))


def _render_review_md(review_blocks: list[dict], run_p: Path) -> None:
    review_md = _render_blocks_with_metadata(review_blocks) if review_blocks else ""
    atomic_write_text(run_p / "review_needed.md", review_md)


def _render_blocks_with_metadata(blocks: list[dict]) -> str:
    lines = []
    for block in blocks:
        text = block.get("text", "").strip()
        lines.append(_block_meta_comment(block, include_reason=True))
        if text:
            lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _render_obsidian_if_requested(
    blocks: list[dict],
    run_dir: str,
    source_title: str | None,
    source_hash: str,
    run_id: str,
    profile: str,
    render_obsidian: bool,
    run_p: Path,
) -> None:
    if not render_obsidian or profile not in OBSIDIAN_PROFILES:
        return
    from .obsidian_kb import render_obsidian_vault, template_for_profile
    render_obsidian_vault(
        blocks=blocks,
        run_dir=run_dir,
        source_title=source_title or run_p.name,
        source_hash=source_hash,
        run_id=run_id,
        profile=profile,
        template_name=template_for_profile(profile),
    )


def _render_parts(keep_blocks: list[dict], run_p: Path) -> None:
    """Render long cleaned documents into chapter-aware parts."""
    parts_dir = run_p / "parts"
    parts_dir.mkdir(exist_ok=True)
    for old in parts_dir.glob("part_*.md"):
        old.unlink(missing_ok=True)

    total_chars = sum(len(b.get("text", "")) for b in keep_blocks)
    if total_chars < 12_000:
        return

    parts: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0
    max_chars = 18_000
    min_chars = 6_000

    for block in keep_blocks:
        text = _readable_text(block)
        if not text:
            continue
        is_heading = block.get("type") == "section_heading"
        if is_heading and current and current_chars >= min_chars:
            parts.append(current)
            current = []
            current_chars = 0
        if current and current_chars + len(text) > max_chars and current_chars >= min_chars:
            parts.append(current)
            current = []
            current_chars = 0
        current.append(block)
        current_chars += len(text)

    if current:
        parts.append(current)

    manifest: list[dict] = []
    for idx, part_blocks in enumerate(parts, start=1):
        manifest.append(_write_part_file(parts_dir, idx, part_blocks))

    atomic_write_json(
        parts_dir / "parts_manifest.json",
        manifest,
        indent=2,
        trailing_newline=False,
    )


def _write_part_file(parts_dir: Path, idx: int, part_blocks: list[dict]) -> dict:
    part_id = f"part_{idx:03d}"
    part_text = "\n\n".join(_readable_text(block) for block in part_blocks if _readable_text(block))
    heading_path = _part_heading_path(part_blocks)
    block_ids = [block.get("block_id") for block in part_blocks]
    content = "\n".join([
        "---",
        f'part_id: "{part_id}"',
        f"heading_path: {json.dumps(heading_path, ensure_ascii=False)}",
        f"block_ids: {json.dumps(block_ids, ensure_ascii=False)}",
        f"char_count: {len(part_text)}",
        "---",
        "",
        part_text,
        "",
    ])
    atomic_write_text(parts_dir / f"{part_id}.md", content)
    return {"part_id": part_id, "heading_path": heading_path, "block_ids": block_ids, "char_count": len(part_text)}


def _part_heading_path(part_blocks: list[dict]) -> list:
    raw_heading_path: object = next((block.get("heading_path", []) for block in part_blocks if block.get("heading_path")), [])
    return raw_heading_path if isinstance(raw_heading_path, list) else []


def _readable_text(block: dict) -> str:
    """Return text intended for human-readable Markdown outputs."""
    text = (block.get("curated_text") or block.get("text") or "").strip()
    if _is_internal_page_marker(text):
        return ""
    return text


def _block_meta_comment(block: dict, *, include_reason: bool = False) -> str:
    """Render compact trace metadata without changing the recovered source text."""
    pieces = [
        f"[{_comment_safe(str(block.get('block_id') or '?'))}]",
        f"type={_comment_safe(str(block.get('type') or 'unknown'))}",
    ]

    page_start = block.get("page_start")
    page_end = block.get("page_end")
    if page_start is not None or page_end is not None:
        if page_start == page_end:
            pieces.append(f"page={page_start}")
        else:
            pieces.append(f"page={page_start}-{page_end}")

    heading_path = block.get("heading_path")
    if heading_path:
        pieces.append(f"heading={_comment_safe(json.dumps(heading_path, ensure_ascii=False))}")

    risk_tags = block.get("risk_tags")
    if risk_tags:
        pieces.append(f"risk_tags={_comment_safe(json.dumps(risk_tags, ensure_ascii=False))}")

    confidence = block.get("confidence")
    if confidence is not None:
        try:
            pieces.append(f"confidence={float(confidence):.2f}")
        except (TypeError, ValueError):
            pieces.append(f"confidence={_comment_safe(str(confidence))}")

    if include_reason and block.get("reason"):
        pieces.append(f"reason={_comment_safe(str(block.get('reason')))}")

    return f"<!-- {' '.join(pieces)} -->"


def _comment_safe(value: str) -> str:
    return value.replace("--", "- -").replace("\r", " ").replace("\n", " ").strip()


def _is_internal_page_marker(text: str) -> bool:
    return text.strip().lower().startswith("<!-- page:") and text.strip().endswith("-->")
