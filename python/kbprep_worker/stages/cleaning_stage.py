"""Cleaning stage orchestration."""
from __future__ import annotations

import copy
from pathlib import Path

from .. import clean_rules
from ..cleaning_patches import build_cleaning_patches, write_cleaning_patches


def apply_cleaning_rules_stage(
    *,
    blocks: list[dict],
    run_dir: Path,
    policy_snapshot_hash: str,
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
    write_cleaning_patches(run_dir / "cleaning_patches.jsonl", patches)
    return cleaned_blocks
