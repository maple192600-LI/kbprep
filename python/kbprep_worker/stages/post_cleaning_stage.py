"""Post-cleaning stages before review, rendering, and quality gates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..clean_view import validate_clean_view_artifact
from .pipeline_helpers import _write_blocks
from .pipeline_state import PipelineState, _stderr_log


def run_post_cleaning_stages(state: PipelineState) -> None:
    """Apply post-cleaning block policies and assemble Clean View."""
    _stage_classify_images(state)
    _stage_apply_obsidian_policy(state)
    _stage_assemble_clean_view(state)


def read_clean_view_artifact(run_dir: Path) -> dict[str, Any]:
    """Read ``clean_view.json`` for rendering, returning an empty payload on failure."""
    path = run_dir / "clean_view.json"
    if not validate_clean_view_artifact(path):
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _stage_classify_images(state: PipelineState) -> None:
    state.require_stage_fields("image_clean", "run_dir", "blocks_path")
    run_dir = state.require_path("image_clean", "run_dir")
    blocks_path = state.require_path("image_clean", "blocks_path")
    _stderr_log("info", "image_clean", "Classifying images")
    try:
        from .. import images as img_mod
        state.blocks = img_mod.classify_images(
            state.blocks, str(run_dir), profile=state.profile, document_type=state.document_type,
        )
        _write_blocks(blocks_path, state.blocks)
        _stderr_log("info", "image_clean", "Image classification complete")
    except Exception as e:
        _stderr_log("warn", "image_clean", str(e))
        state.warnings.append(f"Image classification failed: {e}")


def _stage_apply_obsidian_policy(state: PipelineState) -> None:
    state.require_stage_fields("obsidian_policy", "blocks_path")
    blocks_path = state.require_path("obsidian_policy", "blocks_path")
    if state.profile in {"obsidian_kb", "curated_obsidian_kb"}:
        _stderr_log("info", state.profile, "Applying Obsidian knowledge-base policy")
        from .. import obsidian_kb as obsidian_mod
        state.blocks = obsidian_mod.apply_curated_obsidian_policy(
            state.blocks,
            template_name=obsidian_mod.template_for_profile(state.profile),
        )
        _write_blocks(blocks_path, state.blocks)
        _stderr_log("info", state.profile, "Obsidian policy applied")


def _stage_assemble_clean_view(state: PipelineState) -> None:
    state.require_stage_fields("clean_view", "run_dir", "blocks_path")
    run_dir = state.require_path("clean_view", "run_dir")
    _stderr_log("info", "clean_view", "Assembling Clean View")
    from ..clean_view import assemble_clean_view, write_clean_view

    accepted_patches = _read_jsonl(run_dir / "cleaning_patches.jsonl")
    clean_view = assemble_clean_view(run_dir=run_dir, blocks=state.blocks, accepted_patches=accepted_patches)
    write_clean_view(run_dir / "clean_view.json", clean_view)
    _stderr_log("info", "clean_view", f"Clean View entries: {clean_view.get('entry_count', 0)}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    records = []
    for line in lines:
        record = _jsonl_record(line)
        if record is not None:
            records.append(record)
    return records


def _jsonl_record(line: str) -> dict[str, Any] | None:
    if not line.strip():
        return None
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None
