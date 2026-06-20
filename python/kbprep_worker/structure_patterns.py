"""Shared structural Markdown/text patterns used across worker stages."""

from __future__ import annotations

import re

STEP_LINE_RE = re.compile(
    r"^\s*(?:\d+[\.\)、)]\s+|第?[一二三四五六七八九十百千\d]+步[骤]?[：:、\.\s]|步骤\s*[一二三四五六七八九十百千\d]+[：:、\.\s])",
    re.MULTILINE,
)
EN_STEP_LINE_RE = re.compile(r"^\s*step\s*\d+[\uff1a:\.\)\-\s]+", re.MULTILINE | re.IGNORECASE)


def is_step_line(text: str) -> bool:
    return bool(STEP_LINE_RE.match(text) or EN_STEP_LINE_RE.match(text))


def has_step_signal(text: str) -> bool:
    return bool(STEP_LINE_RE.search(text) or EN_STEP_LINE_RE.search(text))
