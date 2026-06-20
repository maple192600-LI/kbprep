"""Title and heading helpers for Obsidian knowledge-base output."""

from __future__ import annotations

import re

from .context import ObsidianContext, context_for_template
from .links import _safe_filename

AUTHOR_PREFIX_RE = re.compile(r"^(#{1,6}\s*)?(?:@?[\w\u4e00-\u9fff]{1,18})[：:]\s*(.+)$")


def complete_body_filename(
    source_title: str,
    template_name: str = "obsidian_generic",
    ctx: ObsidianContext | None = None,
    duplicate_suffix: str = "完整正文",
) -> str:
    active_ctx = ctx or context_for_template(template_name)
    stem = _safe_filename(source_title)
    if stem in {"00-索引", "_audit", "images", *active_ctx.categories}:
        stem = f"{stem}-{_safe_filename(duplicate_suffix)}"
    return f"{stem}.md"


def sanitize_heading_text(
    text: str,
    template_name: str = "obsidian_generic",
    ctx: ObsidianContext | None = None,
) -> str:
    active_ctx = ctx or context_for_template(template_name)
    if not text.strip().startswith("#"):
        return text
    match = re.match(r"^(#{1,6}\s*)(.+)$", text.strip())
    if not match:
        return text
    prefix, title = match.groups()
    title = _strip_author_prefix(title)
    title = _strip_brand_prefix(title, active_ctx)
    if not title:
        return text
    return f"{prefix}{title}"


def _strip_author_prefix(title: str) -> str:
    match = AUTHOR_PREFIX_RE.match(title.strip())
    if not match:
        return title.strip()
    return match.group(2).strip()


def _strip_brand_prefix(title: str, ctx: ObsidianContext) -> str:
    clean = title.strip()
    for old, new in ctx.brand_heading_replacements:
        clean = clean.replace(old, new)
    return clean.strip(" ：:")


def _heading_title(text: str, ctx: ObsidianContext) -> str:
    title = re.sub(r"^#{1,6}\s*", "", text.strip()).strip()
    title = _strip_author_prefix(title)
    title = _strip_brand_prefix(title, ctx)
    return title or "未命名知识"
