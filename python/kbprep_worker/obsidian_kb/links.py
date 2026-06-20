"""Filename and link helpers for Obsidian knowledge-base output."""

from __future__ import annotations

import re


def _safe_filename(title: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", title).strip(" .-_")
    clean = re.sub(r"\s+", " ", clean)
    if len(clean) > 60:
        clean = clean[:60].rstrip()
    return clean or "未命名知识"
