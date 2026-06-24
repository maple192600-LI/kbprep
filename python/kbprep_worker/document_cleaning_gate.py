"""Final content-safe document cleaning gate over Clean View."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .clean_view import validate_clean_view_artifact
from .cleaning_patches import FORBIDDEN_ARTIFACT_KEYS

DOCUMENT_CLEANING_GATE_SCHEMA = "kbprep.document_cleaning_gate.v1"
GATE_KEYS = frozenset({
    "schema",
    "status",
    "strict_errors",
    "warnings",
    "checks",
    "input_artifacts",
    "blocks_publication",
    "clean_view_entry_count",
    "block_count",
    "rejected_patch_count",
    "rejected_patch_reason_counts",
})
CHECK_KEYS = frozenset({"name", "status", "severity", "reason_code", "evidence"})
ALLOWED_STATUSES = frozenset({"pass", "warn", "fail"})
ALLOWED_CHECK_STATUSES = frozenset({"pass", "warn", "fail"})
ALLOWED_SEVERITIES = frozenset({"info", "warning", "error"})
ALLOWED_EVIDENCE_KEYS = frozenset({
    "missing_block_ids",
    "extra_block_ids",
    "duplicate_block_ids",
    "duplicate_source_block_ids",
    "rejected_patch_count",
    "rejected_patch_reason_counts",
    "reason_codes",
})
INPUT_ARTIFACTS = (
    "clean_view.json",
    "cleaned.md",
    "rejected_patches.jsonl",
)
SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def run_document_cleaning_gate(*, run_dir: Path, blocks: list[dict]) -> dict[str, Any]:
    """Return the final cleanup gate report without copying source content."""
    clean_view = _read_valid_clean_view(run_dir / "clean_view.json")
    rejected = _read_rejected_patch_records(run_dir / "rejected_patches.jsonl")
    checks = [
        _check_clean_view_valid(clean_view),
        _check_clean_view_covers_blocks(clean_view, blocks),
        _check_cleaned_markdown_exists(run_dir / "cleaned.md"),
        _check_rejected_patches(rejected),
    ]
    strict_errors = _strict_errors(checks)
    warnings = _warnings(checks)
    status = _gate_status(strict_errors, warnings)
    return {
        "schema": DOCUMENT_CLEANING_GATE_SCHEMA,
        "status": status,
        "strict_errors": strict_errors,
        "warnings": warnings,
        "checks": checks,
        "input_artifacts": list(INPUT_ARTIFACTS),
        "blocks_publication": bool(strict_errors),
        "clean_view_entry_count": _clean_view_entry_count(clean_view),
        "block_count": len(blocks),
        "rejected_patch_count": len(rejected),
        "rejected_patch_reason_counts": _rejected_reason_counts(rejected),
    }


def write_document_cleaning_gate(path: Path, payload: dict[str, Any]) -> None:
    """Write the document cleaning gate artifact atomically."""
    atomic_write_json(path, payload, indent=2, trailing_newline=False)


def validate_document_cleaning_gate_artifact(path: Path) -> bool:
    """Return true only for a content-safe document cleaning gate artifact."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return _valid_gate_payload(payload)


def document_cleaning_gate_allows_publication(path: Path) -> bool:
    """Return true when the gate artifact is valid and non-blocking."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        _valid_gate_payload(payload)
        and payload.get("status") in {"pass", "warn"}
        and payload.get("blocks_publication") is False
    )


def _read_valid_clean_view(path: Path) -> dict[str, Any]:
    if not validate_clean_view_artifact(path):
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_rejected_patch_records(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    records: list[dict[str, Any]] = []
    for line in lines:
        record = _safe_rejected_record(line)
        if record is not None:
            records.append(record)
    return records


def _safe_rejected_record(line: str) -> dict[str, Any] | None:
    if not line.strip():
        return None
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None
    return {
        "patch_id": str(record.get("patch_id") or ""),
        "block_id": str(record.get("block_id") or ""),
        "reason_code": str(record.get("reason_code") or "unknown"),
    }


def _check_clean_view_valid(clean_view: dict[str, Any]) -> dict[str, Any]:
    if clean_view:
        return _check("clean_view_valid", "pass", "info", "clean_view_valid")
    return _check("clean_view_valid", "fail", "error", "clean_view_invalid")


def _check_clean_view_covers_blocks(clean_view: dict[str, Any], blocks: list[dict]) -> dict[str, Any]:
    clean_view_ids = _clean_view_block_ids(clean_view)
    block_ids = _block_ids(blocks)
    clean_view_set = set(clean_view_ids)
    block_set = set(block_ids)
    duplicate_clean_ids = _duplicate_ids(clean_view_ids)
    duplicate_block_ids = _duplicate_ids(block_ids)
    if not duplicate_clean_ids and not duplicate_block_ids and clean_view_set == block_set and len(clean_view_ids) == len(block_ids):
        return _check("clean_view_covers_blocks", "pass", "info", "clean_view_covers_blocks")
    reason_code = "clean_view_incomplete"
    if duplicate_clean_ids or duplicate_block_ids or (clean_view_set == block_set and len(clean_view_ids) != len(block_ids)):
        reason_code = "clean_view_inconsistent"
    return _check(
        "clean_view_covers_blocks",
        "fail",
        "error",
        reason_code,
        {
            "missing_block_ids": sorted(block_set - clean_view_set),
            "extra_block_ids": sorted(clean_view_set - block_set),
            "duplicate_block_ids": duplicate_clean_ids,
            "duplicate_source_block_ids": duplicate_block_ids,
        },
    )


def _check_cleaned_markdown_exists(path: Path) -> dict[str, Any]:
    if path.exists():
        return _check("cleaned_markdown_exists", "pass", "info", "cleaned_markdown_exists")
    return _check("cleaned_markdown_exists", "fail", "error", "cleaned_markdown_missing")


def _check_rejected_patches(rejected: list[dict[str, Any]]) -> dict[str, Any]:
    if not rejected:
        return _check("rejected_patches_reported", "pass", "info", "no_rejected_patches")
    reason_counts = _rejected_reason_counts(rejected)
    return _check(
        "rejected_patches_reported",
        "warn",
        "warning",
        "rejected_patches_preserved",
        {
            "rejected_patch_count": len(rejected),
            "rejected_patch_reason_counts": reason_counts,
            "reason_codes": sorted(reason_counts),
        },
    )


def _check(
    name: str,
    status: str,
    severity: str,
    reason_code: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "severity": severity,
        "reason_code": reason_code,
        "evidence": evidence or {},
    }


def _clean_view_block_ids(clean_view: dict[str, Any]) -> list[str]:
    entries = clean_view.get("entries")
    if not isinstance(entries, list):
        return []
    return [str(entry.get("block_id") or "") for entry in entries if isinstance(entry, dict) and entry.get("block_id")]


def _block_ids(blocks: list[dict]) -> list[str]:
    return [str(block.get("block_id") or "") for block in blocks if block.get("block_id")]


def _duplicate_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _clean_view_entry_count(clean_view: dict[str, Any]) -> int:
    count = clean_view.get("entry_count")
    return count if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else 0


def _rejected_reason_counts(rejected: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in rejected:
        reason = _safe_token(str(record.get("reason_code") or "")) or "unknown"
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _strict_errors(checks: list[dict[str, Any]]) -> list[str]:
    errors = []
    for check in checks:
        if check.get("status") == "fail":
            errors.append(f"E_DOCUMENT_CLEANING_GATE_FAILED: {_failure_message(check)}")
    return errors


def _failure_message(check: dict[str, Any]) -> str:
    if check.get("reason_code") == "clean_view_inconsistent":
        return "Clean View does not map exactly one entry per block id"
    if check.get("reason_code") == "clean_view_incomplete":
        return "Clean View does not cover every block id"
    if check.get("reason_code") == "cleaned_markdown_missing":
        return "cleaned.md is missing"
    return "Clean View artifact is missing or invalid"


def _warnings(checks: list[dict[str, Any]]) -> list[str]:
    for check in checks:
        if check.get("reason_code") == "rejected_patches_preserved":
            count = int(check.get("evidence", {}).get("rejected_patch_count") or 0)
            return [f"W_REJECTED_CLEANING_PATCHES: {count} rejected cleanup patches preserved"]
    return []


def _gate_status(strict_errors: list[str], warnings: list[str]) -> str:
    if strict_errors:
        return "fail"
    if warnings:
        return "warn"
    return "pass"


def _valid_gate_payload(payload: Any) -> bool:
    if not isinstance(payload, dict) or set(payload) != GATE_KEYS:
        return False
    if payload.get("schema") != DOCUMENT_CLEANING_GATE_SCHEMA or _contains_forbidden_artifact_key(payload):
        return False
    checks_value = payload.get("checks")
    if not isinstance(checks_value, list) or not _valid_checks(checks_value):
        return False
    checks = [check for check in checks_value if isinstance(check, dict)]
    expected_strict_errors = _strict_errors(checks)
    expected_warnings = _warnings(checks)
    expected_rejected_count, expected_rejected_reason_counts = _rejected_summary_from_checks(checks)
    blocks_publication = payload.get("blocks_publication")
    return (
        payload.get("status") == _gate_status(expected_strict_errors, expected_warnings)
        and payload.get("strict_errors") == expected_strict_errors
        and payload.get("warnings") == expected_warnings
        and payload.get("input_artifacts") == list(INPUT_ARTIFACTS)
        and isinstance(blocks_publication, bool)
        and blocks_publication == bool(expected_strict_errors)
        and _non_negative_int(payload.get("clean_view_entry_count"))
        and _non_negative_int(payload.get("block_count"))
        and payload.get("rejected_patch_count") == expected_rejected_count
        and payload.get("rejected_patch_reason_counts") == expected_rejected_reason_counts
        and not _contains_leaky_value(payload)
    )


def _valid_checks(value: Any) -> bool:
    return isinstance(value, list) and all(_valid_check(check) for check in value)


def _valid_check(check: Any) -> bool:
    if not isinstance(check, dict) or set(check) != CHECK_KEYS:
        return False
    return (
        bool(_safe_token(str(check.get("name") or "")))
        and check.get("status") in ALLOWED_CHECK_STATUSES
        and check.get("severity") in ALLOWED_SEVERITIES
        and bool(_safe_token(str(check.get("reason_code") or "")))
        and _valid_evidence(check.get("evidence"))
        and _valid_check_semantics(check)
    )


def _valid_check_semantics(check: dict[str, Any]) -> bool:
    evidence = check.get("evidence")
    if check.get("name") == "clean_view_valid":
        return _matches_check(check, "pass", "info", "clean_view_valid", {}) or _matches_check(
            check, "fail", "error", "clean_view_invalid", {},
        )
    if check.get("name") == "clean_view_covers_blocks":
        return _valid_clean_view_coverage_check(check, evidence)
    if check.get("name") == "cleaned_markdown_exists":
        return _matches_check(check, "pass", "info", "cleaned_markdown_exists", {}) or _matches_check(
            check, "fail", "error", "cleaned_markdown_missing", {},
        )
    if check.get("name") == "rejected_patches_reported":
        return _matches_check(check, "pass", "info", "no_rejected_patches", {}) or (
            check.get("status") == "warn"
            and check.get("severity") == "warning"
            and check.get("reason_code") == "rejected_patches_preserved"
            and _valid_rejected_patch_evidence(evidence)
        )
    return False


def _matches_check(check: dict[str, Any], status: str, severity: str, reason_code: str, evidence: dict[str, Any]) -> bool:
    return (
        check.get("status") == status
        and check.get("severity") == severity
        and check.get("reason_code") == reason_code
        and check.get("evidence") == evidence
    )


def _valid_clean_view_coverage_check(check: dict[str, Any], evidence: Any) -> bool:
    if _matches_check(check, "pass", "info", "clean_view_covers_blocks", {}):
        return True
    if check.get("status") != "fail" or check.get("severity") != "error" or not isinstance(evidence, dict):
        return False
    if check.get("reason_code") == "clean_view_incomplete":
        return bool(evidence.get("missing_block_ids") or evidence.get("extra_block_ids")) and not bool(
            evidence.get("duplicate_block_ids") or evidence.get("duplicate_source_block_ids"),
        )
    if check.get("reason_code") == "clean_view_inconsistent":
        return bool(evidence.get("duplicate_block_ids") or evidence.get("duplicate_source_block_ids"))
    return False


def _valid_rejected_patch_evidence(evidence: Any) -> bool:
    if not isinstance(evidence, dict):
        return False
    count = evidence.get("rejected_patch_count")
    reason_counts = evidence.get("rejected_patch_reason_counts")
    reason_codes = evidence.get("reason_codes")
    if not isinstance(reason_counts, dict):
        return False
    return (
        isinstance(count, int)
        and count > 0
        and _valid_reason_counts(reason_counts)
        and isinstance(reason_codes, list)
        and reason_codes == sorted(reason_counts)
        and sum(reason_counts.values()) == count
    )


def _valid_evidence(value: Any) -> bool:
    if not isinstance(value, dict) or not set(value).issubset(ALLOWED_EVIDENCE_KEYS):
        return False
    return all(_valid_evidence_value(key, item) for key, item in value.items())


def _valid_evidence_value(key: str, value: Any) -> bool:
    if key == "rejected_patch_count":
        return _non_negative_int(value)
    if key == "rejected_patch_reason_counts":
        return _valid_reason_counts(value)
    return isinstance(value, list) and all(_safe_token(str(item)) for item in value)


def _valid_reason_counts(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return all(_safe_token(str(key)) and _non_negative_int(count) for key, count in value.items())


def _rejected_summary_from_checks(checks: list[dict[str, Any]]) -> tuple[int, dict[str, int]]:
    for check in checks:
        if check.get("reason_code") == "rejected_patches_preserved":
            evidence = check.get("evidence", {})
            return int(evidence["rejected_patch_count"]), dict(evidence["rejected_patch_reason_counts"])
    return 0, {}


def _safe_token(value: str) -> str:
    return value if SAFE_TOKEN_RE.fullmatch(value) and not _looks_private_or_leaky(value) else ""


def _contains_forbidden_artifact_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key) in FORBIDDEN_ARTIFACT_KEYS or _contains_forbidden_artifact_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_artifact_key(item) for item in value)
    return False


def _contains_leaky_value(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_leaky_value(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_leaky_value(item) for item in value)
    return isinstance(value, str) and _looks_private_or_leaky(value)


def _looks_private_or_leaky(value: str) -> bool:
    lowered = value.lower()
    return (
        ".kbprep" in lowered
        or "users/" in lowered
        or "users\\" in lowered
        or "do_not_leak" in lowered
        or "\\" in value
        or "/" in value
    )


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
