"""Patch quality gate for cleanup-stage block changes."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text
from .cleaning_patches import CLEANING_PATCH_SCHEMA, FORBIDDEN_ARTIFACT_KEYS, PATCH_FIELDS, sanitize_rule_source

PROTECTED_BLOCK_TYPES = frozenset({"code", "table", "image", "formula"})
PROMO_SPLIT_TAG = "promo_line_removed"
PATCH_GATE_SCHEMA = "kbprep.cleaning_patch_gate.v1"
REJECTED_PATCH_SCHEMA = "kbprep.rejected_cleaning_patch.v1"
PATCH_GATE_SUMMARY_KEYS = frozenset({
    "schema",
    "accepted_patch_count",
    "rejected_patch_count",
    "rejected_reason_counts",
})
REJECTED_PATCH_KEYS = frozenset({
    "schema",
    "patch_id",
    "block_id",
    "parent_block_id",
    "change_type",
    "rule_id",
    "rule_source",
    "reason_code",
    "policy_snapshot_hash",
    "before",
    "after",
    "text_changed",
    "location",
})
REJECTED_PATCH_LOCATION_KEYS = frozenset({"line_start", "line_end", "page_start", "page_end"})


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
        "schema": REJECTED_PATCH_SCHEMA,
        "patch_id": str(patch.get("patch_id") or ""),
        "block_id": _block_id(patch),
        "parent_block_id": str(patch.get("parent_block_id") or ""),
        "change_type": str(patch.get("change_type") or ""),
        "rule_id": str(patch.get("rule_id") or ""),
        "rule_source": sanitize_rule_source(patch.get("rule_source")),
        "reason_code": reason_code,
        "policy_snapshot_hash": str(patch.get("policy_snapshot_hash") or ""),
        "before": _safe_patch_fields(patch.get("before", {})),
        "after": _safe_patch_fields(patch.get("after", {})),
        "text_changed": bool(patch.get("text_changed")),
        "location": _safe_location(patch.get("location", {})),
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


def write_rejected_patches(path: Path, rejected_patches: list[dict[str, Any]]) -> None:
    """Write rejected patch evidence as content-safe JSONL."""
    lines = [json.dumps(patch, ensure_ascii=False, sort_keys=True) for patch in rejected_patches]
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def count_rejected_patches_artifact(path: Path) -> int | None:
    """Return the number of valid rejected patch records, or None if invalid."""
    if not path.exists():
        return None
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        records = [json.loads(line) for line in lines]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not all(_valid_rejected_patch_record(record) for record in records):
        return None
    return len(records)


def validate_rejected_patches_artifact(path: Path) -> bool:
    """Return true only for current-schema, content-safe rejected patch JSONL."""
    return count_rejected_patches_artifact(path) is not None


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


def _valid_rejected_patch_record(record: Any) -> bool:
    if not isinstance(record, dict) or set(record) != REJECTED_PATCH_KEYS:
        return False
    if record.get("schema") != REJECTED_PATCH_SCHEMA:
        return False
    if _contains_forbidden_artifact_key(record):
        return False
    if record.get("rule_source") != sanitize_rule_source(record.get("rule_source")):
        return False
    return (
        _valid_safe_fields(record.get("before"))
        and _valid_safe_fields(record.get("after"))
        and _valid_location(record.get("location"))
    )


def _valid_safe_fields(fields: Any) -> bool:
    if not isinstance(fields, dict):
        return False
    source = fields.get("cleaning_rule_source")
    if source is not None and source != sanitize_rule_source(source):
        return False
    return set(fields).issubset(PATCH_FIELDS)


def _contains_forbidden_artifact_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key) in FORBIDDEN_ARTIFACT_KEYS or _contains_forbidden_artifact_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_artifact_key(item) for item in value)
    return False


def _valid_location(location: Any) -> bool:
    if not isinstance(location, dict) or set(location) != REJECTED_PATCH_LOCATION_KEYS:
        return False
    return all(_valid_location_value(value) for value in location.values())


def _valid_location_value(value: Any) -> bool:
    return value is None or type(value) is int


def _safe_patch_fields(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {field: _safe_patch_field(field, value.get(field)) for field in PATCH_FIELDS if field in value}


def _safe_patch_field(field: str, value: Any) -> Any:
    if field == "cleaning_rule_source":
        return sanitize_rule_source(value)
    return _json_safe(value)


def _safe_location(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "line_start": value.get("line_start"),
        "line_end": value.get("line_end"),
        "page_start": value.get("page_start"),
        "page_end": value.get("page_end"),
    }


def _block_id(value: dict) -> str:
    return str(value.get("block_id") or "").strip()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)
