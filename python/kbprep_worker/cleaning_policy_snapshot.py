"""Compile a cleaning policy snapshot for a KBPrep run."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .cleaning_registry import (
    CleaningRuleRoute,
    CleaningRuleRouteKind,
    select_accepted_rule_routes,
    select_base_cleaning_routes,
    select_private_document_type_routes,
)
from .private_rules import accepted_rule_dirs_from_env, template_candidates
from .quality.thresholds import (
    CLEANING_THRESHOLDS,
    REVIEW_THRESHOLDS,
    review_pack_low_confidence_threshold,
)
from .rule_loader import load_active_accepted_rules, rules_root
from .rule_schema import CleaningRule

SNAPSHOT_SCHEMA = "kbprep.cleaning_policy_snapshot.v1"
COMPILED_POLICY_SCHEMA = "kbprep.compiled_cleaning_policy.v1"
COMPILER_VERSION = "compiled-policy-contract.v1"


@dataclass(frozen=True)
class CleaningPolicySnapshotResult:
    snapshot: dict[str, Any]
    snapshot_hash: str
    path: Path | None = None


def compile_cleaning_policy_snapshot(
    *,
    profile: str,
    document_type: str,
    source_identity: dict[str, Any],
    source_quality: str = "",
    rule_templates: tuple[str, ...] = (),
    cwd: Path | None = None,
) -> CleaningPolicySnapshotResult:
    """Compile the current policy inputs without copying rule contents."""
    root = rules_root()
    working_dir = cwd or Path.cwd()
    payload = _snapshot_payload(
        root=root,
        cwd=working_dir,
        profile=profile,
        document_type=document_type,
        source_identity=source_identity,
        source_quality=source_quality,
        rule_templates=rule_templates,
    )
    snapshot_hash = _payload_sha256(payload)
    return CleaningPolicySnapshotResult(
        snapshot={**payload, "snapshot_hash": snapshot_hash},
        snapshot_hash=snapshot_hash,
    )


def write_cleaning_policy_snapshot(
    run_dir: Path,
    *,
    profile: str,
    document_type: str,
    source_identity: dict[str, Any],
    source_quality: str = "",
    rule_templates: tuple[str, ...] = (),
    cwd: Path | None = None,
) -> CleaningPolicySnapshotResult:
    """Write ``cleaning_policy_snapshot.json`` and return its hash reference."""
    result = compile_cleaning_policy_snapshot(
        profile=profile,
        document_type=document_type,
        source_identity=source_identity,
        source_quality=source_quality,
        rule_templates=rule_templates,
        cwd=cwd,
    )
    path = run_dir / "cleaning_policy_snapshot.json"
    atomic_write_json(path, result.snapshot, indent=2, trailing_newline=False)
    return CleaningPolicySnapshotResult(
        snapshot=result.snapshot,
        snapshot_hash=result.snapshot_hash,
        path=path,
    )


def _snapshot_payload(
    *,
    root: Path,
    cwd: Path,
    profile: str,
    document_type: str,
    source_identity: dict[str, Any],
    source_quality: str,
    rule_templates: tuple[str, ...],
) -> dict[str, Any]:
    rule_routes = _route_snapshots(root, cwd, profile, document_type, rule_templates, source_identity)
    return {
        "schema": SNAPSHOT_SCHEMA,
        "compiler_version": COMPILER_VERSION,
        "hash_algorithm": "sha256",
        "policy_inputs": {
            "profile": profile,
            "document_type": document_type or "",
            "rule_templates": list(rule_templates),
            "source_identity": _source_identity_summary(source_identity),
            "rule_routes": rule_routes,
        },
        "compiled_policy": _compiled_policy_summary(rule_routes, profile, document_type, rule_templates),
        "thresholds": _threshold_summary(source_quality, document_type),
    }


def _route_snapshots(
    root: Path,
    cwd: Path,
    profile: str,
    document_type: str,
    rule_templates: tuple[str, ...],
    source_identity: dict[str, Any],
) -> list[dict[str, Any]]:
    base_routes = select_base_cleaning_routes(
        root,
        profile=profile,
        document_type=document_type,
        templates=rule_templates,
    )
    private_document_type_routes = select_private_document_type_routes(
        root,
        document_type=document_type,
        cwd=cwd,
    )
    accepted_routes = select_accepted_rule_routes(
        root,
        cwd=cwd,
        user_rule_dirs=accepted_rule_dirs_from_env(),
    )
    source_identity_text = json.dumps(_json_safe(source_identity), ensure_ascii=False, sort_keys=True)
    snapshots: list[dict[str, Any]] = []
    for route in (*base_routes, *private_document_type_routes, *accepted_routes):
        snapshot = _route_snapshot(route, root, cwd, document_type, source_identity_text)
        if snapshot is not None:
            snapshots.append(snapshot)
    return snapshots


def _route_snapshot(
    route: CleaningRuleRoute,
    root: Path,
    cwd: Path,
    document_type: str,
    source_identity: str,
) -> dict[str, Any] | None:
    path = _resolve_route_path(route, root, cwd)
    exists = path.exists()
    fingerprint = _route_fingerprint(route, path, exists, document_type, source_identity)
    if fingerprint is None:
        return None
    return {
        "kind": route.kind.value,
        "source": _source_name(root, path),
        "path": str(path),
        "sha256": fingerprint["sha256"],
        "hash_scope": fingerprint["hash_scope"],
        "exists": exists,
        "reason": route.reason,
        "priority": route.priority,
        "cache_strategy": route.cache_strategy,
        "runtime_filter": route.runtime_filter,
        "active_rule_count": fingerprint["active_rule_count"],
        "active_rule_ids": fingerprint["active_rule_ids"],
        "declared_source": route.source,
        "declared_path": str(route.path),
    }


def _route_fingerprint(
    route: CleaningRuleRoute,
    path: Path,
    exists: bool,
    document_type: str,
    source_identity: str,
) -> dict[str, Any] | None:
    if route.kind is CleaningRuleRouteKind.ACCEPTED_USER:
        active_rules = load_active_accepted_rules(path, document_type, source_identity)
        if not active_rules:
            return None
        return {
            "sha256": _payload_sha256([_rule_fingerprint(rule) for rule in active_rules]),
            "hash_scope": "active_accepted_rules",
            "active_rule_count": len(active_rules),
            "active_rule_ids": [rule.rule_id for rule in active_rules],
        }
    return {
        "sha256": _file_sha256(path) if exists else None,
        "hash_scope": "file",
        "active_rule_count": None,
        "active_rule_ids": [],
    }


def _rule_fingerprint(rule: CleaningRule) -> dict[str, str]:
    return {
        "rule_id": rule.rule_id,
        "action": rule.action,
        "match": rule.match,
        "pattern": rule.pattern,
        "reason": rule.reason,
        "risk_tag": rule.risk_tag,
        "source": rule.source,
    }


def _compiled_policy_summary(
    rule_routes: list[dict[str, Any]],
    profile: str,
    document_type: str,
    rule_templates: tuple[str, ...],
) -> dict[str, Any]:
    file_contracts = [_rule_file_contract(route) for route in rule_routes if route.get("hash_scope") == "file"]
    rule_fingerprints = [
        *_section_fingerprints(file_contracts, "rule_fingerprints"),
        *_accepted_rule_route_fingerprints(rule_routes),
    ]
    dictionary_fingerprints = _section_fingerprints(file_contracts, "dictionary_fingerprints")
    protection_fingerprints = _section_fingerprints(file_contracts, "protection_fingerprints")
    active_rule_ids = _unique_sorted([
        *[rule_id for contract in file_contracts for rule_id in contract["active_rule_ids"]],
        *[rule_id for route in rule_routes for rule_id in route.get("active_rule_ids", [])],
    ])
    active_dictionary_ids = _unique_sorted(
        dictionary_id for contract in file_contracts for dictionary_id in contract["active_dictionary_ids"]
    )
    active_protection_ids = _unique_sorted(
        protection_id for contract in file_contracts for protection_id in contract["active_protection_ids"]
    )
    disabled_rule_ids = _unique_sorted(
        rule_id for contract in file_contracts for rule_id in contract["disabled_rule_ids"]
    )
    conflict_resolutions = _unique_records(
        record for contract in file_contracts for record in contract["conflict_resolutions"]
    )
    return {
        "schema": COMPILED_POLICY_SCHEMA,
        "active_rule_ids": active_rule_ids,
        "active_dictionary_ids": active_dictionary_ids,
        "active_protection_ids": active_protection_ids,
        "disabled_rule_ids": disabled_rule_ids,
        "conflict_resolutions": conflict_resolutions,
        "preferences": _policy_preferences(profile, document_type, rule_templates),
        "rule_set_hash": _section_hash("rules", rule_fingerprints),
        "dictionary_hash": _section_hash("dictionaries", dictionary_fingerprints),
        "protection_hash": _section_hash("protections", protection_fingerprints),
        "active_rule_count": len(active_rule_ids),
        "active_dictionary_count": len(active_dictionary_ids),
        "active_protection_count": len(active_protection_ids),
    }


def _rule_file_contract(route: dict[str, Any]) -> dict[str, Any]:
    if not route.get("exists"):
        return _empty_rule_file_contract()
    data = _read_rule_file(Path(str(route["path"])))
    if not isinstance(data, dict):
        return _empty_rule_file_contract()
    return {
        "active_rule_ids": _rule_ids(data),
        "active_dictionary_ids": _dictionary_ids(data),
        "active_protection_ids": _protection_ids(data),
        "disabled_rule_ids": _disabled_rule_ids(data),
        "conflict_resolutions": _conflict_resolutions(data),
        "rule_fingerprints": _rule_fingerprints(data),
        "dictionary_fingerprints": _dictionary_fingerprints(data),
        "protection_fingerprints": _protection_fingerprints(data),
    }


def _empty_rule_file_contract() -> dict[str, Any]:
    return {
        "active_rule_ids": [],
        "active_dictionary_ids": [],
        "active_protection_ids": [],
        "disabled_rule_ids": [],
        "conflict_resolutions": [],
        "rule_fingerprints": [],
        "dictionary_fingerprints": [],
        "protection_fingerprints": [],
    }


def _read_rule_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _rule_ids(data: dict[str, Any]) -> list[str]:
    result = []
    for raw_rule in _raw_rules(data):
        rule_id = raw_rule.get("id")
        if isinstance(rule_id, str) and rule_id.strip() and not _rule_disabled(raw_rule):
            result.append(rule_id)
    return result


def _rule_fingerprints(data: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _raw_rule_fingerprint(raw_rule)
        for raw_rule in _raw_rules(data)
        if not _rule_disabled(raw_rule) and isinstance(raw_rule.get("id"), str)
    ]


def _raw_rule_fingerprint(raw_rule: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(raw_rule.get("id", "")),
        "type": str(raw_rule.get("type", "")),
        "action": str(raw_rule.get("action", "")),
        "match": str(raw_rule.get("match", "")),
        "pattern_sha256": _payload_sha256(raw_rule.get("pattern", "")),
        "reason_sha256": _payload_sha256(raw_rule.get("reason", "")),
        "risk_tag": str(raw_rule.get("risk_tag", "")),
    }


def _disabled_rule_ids(data: dict[str, Any]) -> list[str]:
    result = []
    for raw_rule in _raw_rules(data):
        rule_id = raw_rule.get("id")
        if isinstance(rule_id, str) and rule_id.strip() and _rule_disabled(raw_rule):
            result.append(rule_id)
    raw_disabled = data.get("disabled_rule_ids", [])
    if isinstance(raw_disabled, list):
        result.extend(item for item in raw_disabled if isinstance(item, str) and item.strip())
    return result


def _raw_rules(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        return []
    return [raw_rule for raw_rule in raw_rules if isinstance(raw_rule, dict)]


def _rule_disabled(raw_rule: dict[str, Any]) -> bool:
    return raw_rule.get("enabled") is False or raw_rule.get("disabled") is True


def _dictionary_ids(data: dict[str, Any]) -> list[str]:
    keyword_sets = data.get("keyword_sets", {})
    if not isinstance(keyword_sets, dict):
        return []
    return [
        key
        for key, value in keyword_sets.items()
        if key != "protected_patterns" and isinstance(key, str) and _has_values(value)
    ]


def _dictionary_fingerprints(data: dict[str, Any]) -> list[dict[str, Any]]:
    keyword_sets = data.get("keyword_sets", {})
    if not isinstance(keyword_sets, dict):
        return []
    return [
        {"id": str(key), "value_hashes": _value_hashes(value)}
        for key, value in sorted(keyword_sets.items())
        if key != "protected_patterns" and isinstance(key, str) and _has_values(value)
    ]


def _protection_ids(data: dict[str, Any]) -> list[str]:
    ids = _protect_rule_ids(data)
    keyword_sets = data.get("keyword_sets", {})
    if isinstance(keyword_sets, dict):
        ids.extend(_protected_pattern_ids(keyword_sets.get("protected_patterns", [])))
    return ids


def _protection_fingerprints(data: dict[str, Any]) -> list[dict[str, Any]]:
    fingerprints = [
        _raw_rule_fingerprint(raw_rule)
        for raw_rule in _raw_rules(data)
        if raw_rule.get("action") == "protect" and isinstance(raw_rule.get("id"), str)
    ]
    keyword_sets = data.get("keyword_sets", {})
    if isinstance(keyword_sets, dict):
        fingerprints.extend(_protected_pattern_fingerprints(keyword_sets.get("protected_patterns", [])))
    return fingerprints


def _protect_rule_ids(data: dict[str, Any]) -> list[str]:
    return [
        str(raw_rule["id"])
        for raw_rule in _raw_rules(data)
        if raw_rule.get("action") == "protect" and isinstance(raw_rule.get("id"), str)
    ]


def _protected_pattern_ids(raw_patterns: Any) -> list[str]:
    if not isinstance(raw_patterns, list):
        return []
    result = []
    for index, item in enumerate(raw_patterns):
        if isinstance(item, dict) and isinstance(item.get("label"), str) and item["label"].strip():
            result.append(f"protected_patterns:{item['label']}")
        elif _has_values(item):
            result.append(f"protected_patterns:index-{index}")
    return result


def _protected_pattern_fingerprints(raw_patterns: Any) -> list[dict[str, str]]:
    if not isinstance(raw_patterns, list):
        return []
    result = []
    for index, item in enumerate(raw_patterns):
        result.append(_protected_pattern_fingerprint(index, item))
    return result


def _protected_pattern_fingerprint(index: int, item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        label = item.get("label")
        pattern = item.get("pattern")
        return {
            "id": f"protected_patterns:{label}" if isinstance(label, str) and label.strip() else f"protected_patterns:index-{index}",
            "pattern_sha256": _payload_sha256(pattern if _is_scalar(pattern) else item),
        }
    return {"id": f"protected_patterns:index-{index}", "pattern_sha256": _payload_sha256(item)}


def _conflict_resolutions(data: dict[str, Any]) -> list[dict[str, str]]:
    raw_conflicts = data.get("conflict_resolutions", [])
    if not isinstance(raw_conflicts, list):
        return []
    return [_safe_conflict_record(item) for item in raw_conflicts if isinstance(item, dict)]


def _safe_conflict_record(item: dict[str, Any]) -> dict[str, str]:
    safe_keys = {"id", "rule_id", "winner_rule_id", "loser_rule_id", "resolution", "priority"}
    return {
        str(key): str(value)
        for key, value in sorted(item.items())
        if str(key) in safe_keys and _is_scalar(value) and value is not None
    }


def _has_values(value: Any) -> bool:
    if isinstance(value, list | tuple):
        return bool(value)
    if isinstance(value, dict):
        return bool(value)
    return isinstance(value, str) and bool(value.strip())


def _policy_preferences(profile: str, document_type: str, rule_templates: tuple[str, ...]) -> dict[str, Any]:
    return {
        "profile": profile,
        "document_type": document_type or "",
        "rule_templates": list(rule_templates),
        "project": {},
        "user": {},
    }


def _section_fingerprints(contracts: list[dict[str, Any]], key: str) -> list[Any]:
    return [fingerprint for contract in contracts for fingerprint in contract[key]]


def _accepted_rule_route_fingerprints(rule_routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "active_rule_ids": route.get("active_rule_ids", []),
            "hash_scope": route.get("hash_scope"),
            "sha256": route.get("sha256"),
            "source": route.get("source"),
        }
        for route in rule_routes
        if route.get("hash_scope") == "active_accepted_rules" and route.get("sha256")
    ]


def _section_hash(name: str, fingerprints: list[Any]) -> str:
    return _payload_sha256({"section": name, "fingerprints": fingerprints})


def _value_hashes(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [_payload_sha256({"key": str(key), "value": _json_safe(item)}) for key, item in sorted(value.items())]
    if isinstance(value, list | tuple):
        return [_payload_sha256(_json_safe(item)) for item in value]
    return [_payload_sha256(_json_safe(value))]


def _unique_sorted(values: Any) -> list[str]:
    return sorted({str(value) for value in values if isinstance(value, str) and value.strip()})


def _unique_records(records: Any) -> list[dict[str, str]]:
    canonical = {_payload_sha256(record): record for record in records}
    return [canonical[key] for key in sorted(canonical)]


def _resolve_route_path(route: CleaningRuleRoute, root: Path, cwd: Path) -> Path:
    if route.path.parent.name != "templates" or route.path.suffix != ".json":
        return route.path
    for path in template_candidates(route.path.stem, root / "templates", cwd=cwd):
        if path.exists():
            return path
    return route.path


def _source_name(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root.parent).as_posix()
    except ValueError:
        return path.as_posix()


def _source_identity_summary(source_identity: dict[str, Any]) -> dict[str, Any]:
    normalized = _json_safe(source_identity)
    keys = sorted(str(key) for key in normalized)
    summary: dict[str, Any] = {
        "sha256": _payload_sha256(normalized),
        "keys": keys,
        "field_count": len(keys),
    }
    for key in ("source_name", "source_domain", "site_name"):
        value = normalized.get(key)
        if _is_scalar(value) and value is not None:
            summary[key] = value
    return summary


def _threshold_summary(source_quality: str, document_type: str) -> dict[str, Any]:
    return {
        "review": dict(REVIEW_THRESHOLDS),
        "cleaning": dict(CLEANING_THRESHOLDS),
        "review_pack_low_confidence_threshold": review_pack_low_confidence_threshold(
            source_quality=source_quality,
            document_type=document_type,
        ),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if _is_scalar(value):
        return value
    return str(value)


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _payload_sha256(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
