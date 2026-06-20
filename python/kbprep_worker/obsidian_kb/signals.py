"""Signal predicates for text-first Obsidian curation."""

from __future__ import annotations

import re

from ..quality.thresholds import OBSIDIAN_CONFIDENCE
from .context import ObsidianContext
from .titles import _heading_title, _strip_author_prefix, _strip_brand_prefix

IMAGE_TYPES = {"image_operation", "image_evidence", "diagram", "qr_image", "unknown_image"}
DETAIL_TYPES = {"operation_step", "case_step", "tool_instruction", "prompt", "code", "table"}

AUTHOR_HANDLE_RE = re.compile(r"^@[\w\u4e00-\u9fff][\w\u4e00-\u9fff._-]{0,30}$")
EMPTY_HEADING_RE = re.compile(r"^#{1,6}\s*$")
VISUAL_CHAPTER_SEPARATOR_RE = re.compile(
    r"^[=\-—_]{3,}\s*(?:第[一二三四五六七八九十百\d]+[章节篇部分]?|Chapter\s+\d+)\s*[=\-—_]{3,}$",
    re.IGNORECASE,
)
INTERNAL_PAGE_MARKER_RE = re.compile(r"^<!--\s*page:\s*\d+\s*-->$", re.IGNORECASE)
SLIDE_CHAPTER_LABEL_RE = re.compile(r"^Chapter\s+\d+\s*$", re.IGNORECASE)
SLIDE_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")


def _is_knowledge_diagram(block: dict) -> bool:
    """Keep extracted HTML/SVG diagrams as first-class knowledge assets."""
    images = block.get("images") or []
    if not images:
        return False
    if not any(str(img.get("src") or "").lower().endswith(".svg") for img in images if isinstance(img, dict)):
        return False
    text = str(block.get("text") or "")
    if re.search(r"diagram-\d+\.svg", text, re.IGNORECASE):
        return True
    heading = " ".join(str(part) for part in (block.get("heading_path") or []))
    return any(term in heading for term in ["图", "全景", "流程", "结构", "示意", "金字塔", "工作流"])


def _is_internal_page_marker(text: str) -> bool:
    return bool(INTERNAL_PAGE_MARKER_RE.match(text.strip()))


def _slide_chapter_divider_title(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or len(lines) > 5:
        return None
    if not SLIDE_CHAPTER_LABEL_RE.match(lines[0]):
        return None
    if not SLIDE_PAGE_NUMBER_RE.match(lines[-1]):
        return None
    title_lines = lines[1:-1]
    if any(len(line) > 40 or re.search(r"[。！？!?；;]", line) for line in title_lines):
        return None
    title = " ".join(title_lines).strip()
    if not title or len(title) > 80:
        return None
    return title


def _curated_slide_chapter_body(text: str, title_hint: str | None) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2 or not SLIDE_CHAPTER_LABEL_RE.match(lines[0]):
        return None

    title = (title_hint or "").strip()
    body = "\n".join(_drop_trailing_slide_page_number(lines[1:])).strip()
    if not body:
        return None

    if title:
        body = _strip_slide_title_prefix(body, title)
    elif not title:
        title = lines[1].strip()
        body = "\n".join(_drop_trailing_slide_page_number(lines[2:])).strip()

    if not title or not body:
        return None
    return f"## {title}\n\n{body}"


def _drop_trailing_slide_page_number(lines: list[str]) -> list[str]:
    if len(lines) >= 2 and SLIDE_PAGE_NUMBER_RE.match(lines[-1].strip()):
        return lines[:-1]
    return lines


def _strip_slide_title_prefix(body: str, title: str) -> str:
    prefix_end = _matching_prefix_end(body, title)
    if prefix_end is None:
        return body
    remainder = body[prefix_end:].lstrip()
    repeated_end = _matching_prefix_end(remainder, title)
    if repeated_end is not None:
        second_remainder = remainder[repeated_end:].lstrip()
        if second_remainder and second_remainder[0] not in {"的", "是", "要", "需", "会", "能", "中"}:
            return second_remainder
        return remainder
    if not remainder or remainder[0] in {"的", "是", "要", "需", "会", "能", "中"}:
        return body
    return remainder


def _matching_prefix_end(text: str, title: str) -> int | None:
    target = re.sub(r"\s+", "", title)
    if not target:
        return None
    compact = ""
    for idx, char in enumerate(text):
        if char.isspace():
            continue
        compact += char
        if compact == target:
            return idx + 1
        if not target.startswith(compact):
            return None
    return None


def _is_translator_marketing_back_matter(text: str, ctx: ObsidianContext) -> bool:
    compact = re.sub(r"\s+", "", text)
    if "译后记" not in compact and "本译本仅供" not in compact:
        return False
    hits = sum(1 for term in ctx.translator_back_matter_terms if term.replace(" ", "") in compact)
    return hits >= 3


def _is_packaging_heading(text: str, ctx: ObsidianContext) -> bool:
    title = _heading_title(text, ctx)
    return _is_packaging_heading_title(title, ctx)


def _is_packaging_heading_title(title: str, ctx: ObsidianContext) -> bool:
    if any(term in title for term in ctx.packaging_heading_terms):
        return True
    if any(re.fullmatch(pattern, title, re.IGNORECASE) for pattern in ctx.packaging_heading_regexes):
        return True
    return False


def _is_noise_heading(text: str, ctx: ObsidianContext) -> bool:
    title = _heading_title(text, ctx)
    if len(title) <= 2 and not re.search(r"[A-Za-z0-9]", title):
        return True
    return False


def _is_direct_packaging_context(block: dict, ctx: ObsidianContext) -> bool:
    if block.get("type") == "section_heading":
        return False
    heading_path = block.get("heading_path") or []
    if not heading_path:
        return False
    last_heading = str(heading_path[-1])
    title = _strip_brand_prefix(_strip_author_prefix(last_heading), ctx)
    return _is_packaging_heading_title(title, ctx)


def _is_empty_heading(text: str) -> bool:
    return bool(EMPTY_HEADING_RE.match(text.strip()))


def _is_author_intro(text: str, ctx: ObsidianContext) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) > 240:
        return False
    if any(term in text for term in ctx.author_bio_terms):
        return True
    role_hits = sum(1 for term in ctx.bio_role_terms if term in text)
    if role_hits >= 2 and not _has_strong_knowledge_signal(text, ctx):
        return True
    return False


def _is_author_identity_card(blocks: list[dict], index: int, text: str, ctx: ObsidianContext) -> bool:
    """Drop short byline/profile cards that sit between a title and the body."""
    if not _is_author_card_line(text, ctx):
        return False
    return _is_in_author_card_window(blocks, index, ctx)


def _is_visual_chapter_separator(text: str) -> bool:
    clean = re.sub(r"\s+", " ", text.strip())
    if len(clean) > 80:
        return False
    return bool(VISUAL_CHAPTER_SEPARATOR_RE.fullmatch(clean))


def _is_front_matter_social_profile(blocks: list[dict], index: int, text: str, ctx: ObsidianContext) -> bool:
    """Drop top-of-document presenter/profile link strips, not body case context."""
    if "\n" in text or len(text) > 300:
        return False
    if _has_strong_knowledge_signal(text, ctx):
        return False
    if any(term in text for term in ctx.provenance_terms):
        return False

    for previous in blocks[:index]:
        previous_text = previous.get("text", "").strip()
        if previous.get("status") != "keep" or not previous_text:
            continue
        if previous.get("type") == "section_heading" and previous_text.startswith("## "):
            return False
    if index > 12:
        return False

    markdown_links = len(re.findall(r"\[[^\]]+\]\([^)]+\)", text))
    has_social_platform = any(term in text for term in ctx.social_profile_platforms)
    has_profile_label = any(re.search(rf"(^|\s){re.escape(term)}\s*[：:]", text) for term in ctx.social_profile_labels)
    return has_profile_label and (markdown_links >= 1 or has_social_platform)


def _is_author_card_line(text: str, ctx: ObsidianContext) -> bool:
    if "\n" in text or _is_toc_like(text):
        return False
    clean = _strip_heading_marks(text)
    compact = re.sub(r"\s+", "", clean)
    if not compact or len(compact) > 90:
        return False
    if AUTHOR_HANDLE_RE.fullmatch(compact):
        return True
    if any(term in clean for term in ctx.bio_role_terms):
        return not any(term in clean for term in ctx.knowledge_terms)
    if any(term in clean for term in ctx.author_credential_terms):
        return not re.match(r"^\s*(?:\d+[\.、）)]|第[一二三四五六七八九十]+)", clean)
    return False


def _is_in_author_card_window(blocks: list[dict], index: int, ctx: ObsidianContext) -> bool:
    saw_card = False
    cursor = index - 1
    while cursor >= 0 and index - cursor <= 5:
        previous = blocks[cursor]
        previous_text = previous.get("text", "").strip()
        if not previous_text or previous.get("status") == "discard":
            cursor -= 1
            continue
        if previous.get("type") == "section_heading":
            return True
        if _is_author_card_line(previous_text, ctx):
            saw_card = True
            cursor -= 1
            continue
        break
    return saw_card


def _strip_heading_marks(text: str) -> str:
    return re.sub(r"^#{1,6}\s*", "", text.strip()).strip()


def _is_layout_table_artifact(text: str, ctx: ObsidianContext) -> bool:
    if not text.lstrip().startswith("|"):
        return False
    empty_cells = len(re.findall(r"\|\s*(?=\|)", text))
    rows = [line for line in text.splitlines() if line.strip().startswith("|")]
    if empty_cells >= 4 and any(term in text for term in ctx.layout_table_terms):
        return True
    if len(rows) <= 5 and empty_cells >= 3 and re.search(r"\b\d{1,2}:\d{2}\b", text):
        return True
    return False


def _is_brand_program_packaging(text: str, ctx: ObsidianContext) -> bool:
    return any(term in text for term in ctx.brand_program_packaging_terms)


def _drop_toc_windows(blocks: list[dict]) -> None:
    """Drop table-of-contents text plus the small heading window around it."""
    for index, block in enumerate(blocks):
        if block.get("status") != "keep":
            continue
        if not _is_toc_like(block.get("text", "")):
            continue
        _discard(block, "toc", "drop_table_of_contents_for_text_kb", OBSIDIAN_CONFIDENCE["drop_toc"])

        dropped = 0
        cursor = index - 1
        while cursor >= 0 and dropped < 3:
            previous = blocks[cursor]
            if previous.get("status") == "discard":
                cursor -= 1
                continue
            if previous.get("status") == "keep" and previous.get("type") == "section_heading":
                _discard(previous, "toc_heading", "drop_table_of_contents_heading_for_text_kb", OBSIDIAN_CONFIDENCE["drop_toc_heading"])
                dropped += 1
                cursor -= 1
                continue
            break


def _is_toc_like(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    toc_lines = 0
    for line in lines:
        if len(line) > 120:
            continue
        if re.search(r"[：:].{2,}\s+\d{1,4}$", line):
            toc_lines += 1
        elif re.search(r".{4,}\s{2,}\d{1,4}$", line):
            toc_lines += 1
    return toc_lines >= 2 and toc_lines / len(lines) >= 0.5


def _has_strong_knowledge_signal(text: str, ctx: ObsidianContext) -> bool:
    if re.search(r"^\s*\d+[\.\)\uff09、]", text, re.MULTILINE):
        return True
    if any(term in text for term in ctx.knowledge_terms):
        return True
    if re.search(r"[A-Za-z_]+=\S+", text):
        return True
    return False


def _discard(block: dict, block_type: str, reason: str, confidence: float) -> None:
    block["status"] = "discard"
    block["type"] = block_type
    block["reason"] = reason
    block["confidence"] = confidence
    block["protected"] = False
    _append_tag(block, reason)


def _append_tag(block: dict, tag: str) -> None:
    tags = block.setdefault("risk_tags", [])
    if tag not in tags:
        tags.append(tag)
