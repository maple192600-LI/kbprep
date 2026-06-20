"""Frontmatter formatting helpers for Obsidian knowledge-base output."""

from __future__ import annotations

import json


def _yaml_safe(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)[1:-1]


def _yaml_quoted(value: str) -> str:
    return '"' + _yaml_safe(value) + '"'


def frontmatter_lines(fields: dict[str, str]) -> list[str]:
    lines = ["---"]
    for key, value in fields.items():
        lines.append(key + ": " + _yaml_quoted(value))
    lines.append("---")
    return lines
