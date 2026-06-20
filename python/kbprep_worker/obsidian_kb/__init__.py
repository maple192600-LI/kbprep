"""Curated Obsidian knowledge-base rendering public API."""

from __future__ import annotations

from .body_notes import render_obsidian_vault
from .context import ObsidianContext, context_for_template, template_for_profile
from .frontmatter import _yaml_safe
from .links import _safe_filename
from .policy import apply_curated_obsidian_policy
from .titles import complete_body_filename, sanitize_heading_text

__all__ = [
    "ObsidianContext",
    "apply_curated_obsidian_policy",
    "complete_body_filename",
    "context_for_template",
    "render_obsidian_vault",
    "sanitize_heading_text",
    "template_for_profile",
    "_safe_filename",
    "_yaml_safe",
]
