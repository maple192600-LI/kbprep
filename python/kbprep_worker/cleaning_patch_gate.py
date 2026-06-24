"""Patch quality gate for cleanup-stage block changes."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cleaning_patches import CLEANING_PATCH_SCHEMA

PROTECTED_BLOCK_TYPES = frozenset({"code", "table", "image", "formula"})
PROMO_SPLIT_TAG = "promo_line_removed"
PATCH_GATE_SCHEMA = "kbprep.cleaning_patch_gate.v1"
PATCH_GATE_SUMMARY_KEYS = frozenset({
    "schema",
    "accepted_patch_count",
    "rejected_patch_count",
    "rejected_reason_counts",
})


@dataclass(frozen=True)
class PatchGateResult:
    gated_blocks: list[dict[str, Any]]
    accepted_patches: list[dict[str, Any]]
    rejected_patches: list[dict[str, Any]]
    summary: dict[str, Any]


def apply_patch_quality_gate(
    before_blocks: list[dict],
    cleaned_blocks: list[dict],
    patches: list[dict],
    compiled_policy: dict,
) -> PatchGateResult:
    """Reject unsafe cleaning patches and restore affected blocks."""
    context = _gate_context(before_blocks, cleaned_blocks, patches, compiled_policy)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    rejected_block_ids: set[str] = set()
    for patch in patches:
        reason = _rejection_reason(patch, context)
        if reason:
            rejected.append(_rejected_patch_record(patch, reason))
            rejected_block_ids.add(_block_id(patch))
        else:
            accepted.append(patch)
    gated_blocks = _restore_rejected_blocks(cleaned_blocks, context["before_by_id"], rejected_block_ids)
    return PatchGateResult(
        gated_blocks=gated_blocks,
        accepted_patches=accepted,
        rejected_patches=rejected,
        summary=_summary(accepted, rejected),
    )


def _gate_context(before_blocks: list[dict], cleaned_blocks: list[dict], patches: list[dict], compiled_policy: dict) -> dict:
    active_rule_ids = {str(rule_id) for rule_id in compiled_policy.get("active_rule_ids", [])}
    return {
        "before_by_id": {_block_id(block): block for block in before_blocks if _block_id(block)},
        "cleaned_by_id": {_block_id(block): block for block in cleaned_blocks if _block_id(block)},
        "active_rule_ids": active_rule_ids,
        "valid_derived_parents": _valid_derived_parents(patches, active_rule_ids),
    }


def _valid_derived_parents(patches: list[dict], active_rule_ids: set[str]) -> set[str]:
    return {
        str(patch.get("parent_block_id") or "")
        for patch in patches
        if patch.get("change_type") == "derived_block"
        and _rule_id_allowed(str(patch.get("rule_id") or ""), active_rule_ids)
        and str(patch.get("parent_block_id") or "")
    }


def _rejection_reason(patch: dict, context: dict) -> str:
    if patch.get("schema") != CLEANING_PATCH_SCHEMA or not patch.get("patch_id"):
        return "missing_evidence"
    block_id = _block_id(patch)
    if not block_id or block_id not in context["cleaned_by_id"]:
        return "missing_target_node"
    if patch.get("change_type") != "derived_block" and block_id not in context["before_by_id"]:
        return "missing_target_node"
    if not _rule_evidence_allowed(patch, context):
        return "rule_not_in_policy_snapshot"
    if _derived_from_protected_parent(patch, context):
        return "protected_structure_change"
    before = context["before_by_id"].get(block_id, {})
    if _protected_structure_changed(before, patch):
        return "protected_structure_change"
    if _whole_section_deleted(before, patch):
        return "whole_section_deletion"
    return ""


def _rule_evidence_allowed(patch: dict, context: dict) -> bool:
    rule_id = str(patch.get("rule_id") or "")
    if rule_id:
        return _rule_id_allowed(rule_id, context["active_rule_ids"])
    change_type = patch.get("change_type")
    after = patch.get("after", {})
    if change_type == "metadata_update":
        return True
    if change_type == "status_update" and after.get("status") == "review":
        return "possible_cta" in after.get("risk_tags", [])
    if change_type == "content_update" and _is_rule_backed_promo_split_parent(patch, context):
        return True
    return False


def _is_rule_backed_promo_split_parent(patch: dict, context: dict) -> bool:
    after = patch.get("after", {})
    return PROMO_SPLIT_TAG in after.get("risk_tags", []) and _block_id(patch) in context["valid_derived_parents"]


def _protected_structure_changed(before: dict, patch: dict) -> bool:
    if not before:
        return False
    if not _protected_block(before, patch.get("before", {})):
        return False
    after = patch.get("after", {})
    return bool(
        patch.get("text_changed")
        or _after_status_not_keep(after)
        or _type_changed(before, patch.get("before", {}), after)
        or _protected_flag_removed(before, patch.get("before", {}), after)
    )


def _derived_from_protected_parent(patch: dict, context: dict) -> bool:
    if patch.get("change_type") != "derived_block":
        return False
    parent = context["before_by_id"].get(str(patch.get("parent_block_id") or ""), {})
    return _protected_block(parent, {})


def _protected_block(before: dict, safe_before: dict) -> bool:
    before_type = str(before.get("type") or safe_before.get("type") or "")
    return bool(before.get("protected") or safe_before.get("protected") or before_type in PROTECTED_BLOCK_TYPES)


def _after_status_not_keep(after: dict) -> bool:
    status = after.get("status")
    return status is not None and status != "keep"


def _type_changed(before: dict, safe_before: dict, after: dict) -> bool:
    before_type = str(before.get("type") or safe_before.get("type") or "")
    return bool(before_type and after.get("type") != before_type)


def _protected_flag_removed(before: dict, safe_before: dict, after: dict) -> bool:
    before_protected = bool(before.get("protected") or safe_before.get("protected"))
    return before_protected and after.get("protected") is not True


def _whole_section_deleted(before: dict, patch: dict) -> bool:
    if str(before.get("type") or "") != "section_heading":
        return False
    after = patch.get("after", {})
    return after.get("status") == "discard"


def _restore_rejected_blocks(
    cleaned_blocks: list[dict],
    before_by_id: dict[str, dict],
    rejected_block_ids: set[str],
) -> list[dict[str, Any]]:
    restored = []
    for block in cleaned_blocks:
        block_id = _block_id(block)
        if block_id in rejected_block_ids:
            if block_id in before_by_id:
                restored.append(copy.deepcopy(before_by_id[block_id]))
            continue
        restored.append(copy.deepcopy(block))
    return restored


def _rejected_patch_record(patch: dict, reason_code: str) -> dict[str, Any]:
    return {
        "patch_id": str(patch.get("patch_id") or ""),
        "block_id": _block_id(patch),
        "parent_block_id": str(patch.get("parent_block_id") or ""),
        "change_type": str(patch.get("change_type") or ""),
        "rule_id": str(patch.get("rule_id") or ""),
        "reason_code": reason_code,
    }


def _summary(accepted: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": PATCH_GATE_SCHEMA,
        "accepted_patch_count": len(accepted),
        "rejected_patch_count": len(rejected),
        "rejected_reason_counts": _reason_counts(rejected),
    }


def validate_cleaning_patch_gate_artifact(path: Path) -> bool:
    """Return true only for the current safe patch-gate summary artifact."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or set(payload) != PATCH_GATE_SUMMARY_KEYS:
        return False
    if payload.get("schema") != PATCH_GATE_SCHEMA:
        return False
    if not _non_negative_int(payload.get("accepted_patch_count")):
        return False
    if not _non_negative_int(payload.get("rejected_patch_count")):
        return False
    reason_counts = payload.get("rejected_reason_counts")
    return isinstance(reason_counts, dict) and all(
        isinstance(reason, str) and _non_negative_int(count)
        for reason, count in reason_counts.items()
    )


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and value >= 0


def _reason_counts(rejected: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for patch in rejected:
        reason = str(patch.get("reason_code") or "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _rule_id_allowed(rule_id: str, active_rule_ids: set[str]) -> bool:
    return bool(rule_id and rule_id in active_rule_ids)


def _block_id(value: dict) -> str:
    return str(value.get("block_id") or "").strip()
