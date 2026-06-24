"""Cleaning stage orchestration."""
from __future__ import annotations

import copy
from pathlib import Path

from .. import clean_rules
from ..atomic_io import atomic_write_json
from ..cleaning_patch_gate import apply_patch_quality_gate, write_rejected_patches
from ..cleaning_patches import build_cleaning_patches, write_cleaning_patches


def apply_cleaning_rules_stage(
    *,
    blocks: list[dict],
    run_dir: Path,
    policy_snapshot_hash: str,
    compiled_policy: dict,
    profile: str,
    document_type: str,
    source_identity: str,
) -> list[dict]:
    before_blocks = copy.deepcopy(blocks)
    cleaned_blocks = clean_rules.apply_clean_rules(
        blocks,
        profile=profile,
        document_type=document_type,
        source_identity=source_identity,
    )
    patches = build_cleaning_patches(before_blocks, cleaned_blocks, policy_snapshot_hash)
    gate_result = apply_patch_quality_gate(before_blocks, cleaned_blocks, patches, compiled_policy)
    write_cleaning_patches(run_dir / "cleaning_patches.jsonl", gate_result.accepted_patches)
    write_rejected_patches(run_dir / "rejected_patches.jsonl", gate_result.rejected_patches)
    atomic_write_json(run_dir / "cleaning_patch_gate.json", gate_result.summary)
    return gate_result.gated_blocks
