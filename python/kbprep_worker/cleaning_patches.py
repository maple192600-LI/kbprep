"""Build auditable CleaningPatch records from cleanup block changes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text

CLEANING_PATCH_SCHEMA = "kbprep.cleaning_patch.v1"
PATCH_FIELDS = ("status", "type", "protected", "risk_tags", "cleaning_rule_id", "cleaning_rule_source")
STATUS_FIELDS = ("status", "type", "protected", "cleaning_rule_id", "cleaning_rule_source")
FORBIDDEN_ARTIFACT_KEYS = {
    "text",
    "reason",
    "pattern",
    "patterns",
    "heading",
    "before_text_sha256",
    "after_text_sha256",
}


def build_cleaning_patches(
    before_blocks: list[dict],
    after_blocks: list[dict],
    policy_snapshot_hash: str,
) -> list[dict[str, Any]]:
    """Build patch records without copying source text into the artifact."""
    before_by_id = {_block_id(block): block for block in before_blocks if _block_id(block)}
    patches = []
    for after in after_blocks:
        block_id = _block_id(after)
        if not block_id:
            continue
        before = before_by_id.get(block_id)
        patch = _patch_for_block(before, after, policy_snapshot_hash)
        if patch is not None:
            patches.append(patch)
    return patches


def write_cleaning_patches(path: Path, patches: list[dict[str, Any]]) -> None:
    """Write patches as JSONL so later gates can stream and reject entries."""
    lines = [json.dumps(patch, ensure_ascii=False, sort_keys=True) for patch in patches]
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def validate_cleaning_patches_artifact(path: Path) -> bool:
    """Return true only for current-schema, content-safe patch JSONL."""
    if not path.exists():
        return False
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return all(_valid_patch_record(json.loads(line)) for line in lines)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False


def _patch_for_block(
    before: dict | None,
    after: dict,
    policy_snapshot_hash: str,
) -> dict[str, Any] | None:
    if before is None:
        return _patch_payload("derived_block", None, after, policy_snapshot_hash)
    change_type = _change_type(before, after)
    if change_type is None:
        return None
    return _patch_payload(change_type, before, after, policy_snapshot_hash)


def _change_type(before: dict, after: dict) -> str | None:
    if _field_subset(before, STATUS_FIELDS) != _field_subset(after, STATUS_FIELDS):
        return "status_update"
    if _text_value(before) != _text_value(after):
        return "content_update"
    if _safe_fields(before) != _safe_fields(after):
        return "metadata_update"
    return None


def _patch_payload(
    change_type: str,
    before: dict | None,
    after: dict,
    policy_snapshot_hash: str,
) -> dict[str, Any]:
    payload = {
        "schema": CLEANING_PATCH_SCHEMA,
        "patch_id": "",
        "change_type": change_type,
        "block_id": _block_id(after),
        "parent_block_id": _parent_block_id(after) if change_type == "derived_block" else "",
        "policy_snapshot_hash": policy_snapshot_hash,
        "rule_id": str(after.get("cleaning_rule_id") or ""),
        "rule_source": _safe_rule_source(after.get("cleaning_rule_source")),
        "before": _safe_fields(before or {}),
        "after": _safe_fields(after),
        "text_changed": _text_value(before or {}) != _text_value(after),
        "location": _location(after),
    }
    payload["patch_id"] = _payload_sha256(payload)[:16]
    return payload


def _safe_fields(block: dict) -> dict[str, Any]:
    return {field: _safe_field(field, block.get(field)) for field in PATCH_FIELDS if field in block}


def _field_subset(block: dict, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: _safe_field(field, block.get(field)) for field in fields if field in block}


def _safe_field(field: str, value: Any) -> Any:
    if field == "cleaning_rule_source":
        return _safe_rule_source(value)
    return _json_safe(value)


def sanitize_rule_source(value: Any) -> str:
    """Return a public/private-safe rule-source label for artifacts."""
    source = str(value or "").replace("\\", "/").strip()
    if not source:
        return ""
    if source in {"private_rules", "external_rules"}:
        return source
    lower_source = source.lower()
    if lower_source.startswith("rules/"):
        return source
    if lower_source.startswith(".kbprep/") or "/.kbprep/" in lower_source:
        return "private_rules"
    if source.startswith(("/", "//", "~")) or ":" in source:
        return "private_rules"
    return "external_rules"


def _safe_rule_source(value: Any) -> str:
    return sanitize_rule_source(value)


def _valid_patch_record(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    if record.get("schema") != CLEANING_PATCH_SCHEMA:
        return False
    if _contains_forbidden_artifact_key(record):
        return False
    if record.get("rule_source") != _safe_rule_source(record.get("rule_source")):
        return False
    for section in ("before", "after"):
        fields = record.get(section, {})
        if not isinstance(fields, dict):
            return False
        source = fields.get("cleaning_rule_source")
        if source is not None and source != _safe_rule_source(source):
            return False
    return True


def _contains_forbidden_artifact_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(key) in FORBIDDEN_ARTIFACT_KEYS or _contains_forbidden_artifact_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden_artifact_key(item) for item in value)
    return False


def _location(block: dict) -> dict[str, Any]:
    return {
        "line_start": block.get("line_start"),
        "line_end": block.get("line_end"),
        "page_start": block.get("page_start"),
        "page_end": block.get("page_end"),
    }


def _parent_block_id(block: dict) -> str:
    block_id = _block_id(block)
    marker = "_promo_"
    if marker in block_id:
        return block_id.split(marker, 1)[0]
    return ""


def _block_id(block: dict) -> str:
    return str(block.get("block_id") or "").strip()


def _text_value(block: dict) -> str:
    return str(block.get("text") or "")


def _payload_sha256(payload: Any) -> str:
    canonical = json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)
