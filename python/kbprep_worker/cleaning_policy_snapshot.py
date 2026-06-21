"""Compile a partial cleaning policy snapshot for a KBPrep run."""
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
COMPILER_VERSION = "partial.policy-inputs.v1"


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
    return {
        "schema": SNAPSHOT_SCHEMA,
        "compiler_version": COMPILER_VERSION,
        "hash_algorithm": "sha256",
        "policy_inputs": {
            "profile": profile,
            "document_type": document_type or "",
            "rule_templates": list(rule_templates),
            "source_identity": _source_identity_summary(source_identity),
            "rule_routes": _route_snapshots(root, cwd, profile, document_type, rule_templates, source_identity),
        },
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
    accepted_routes = select_accepted_rule_routes(
        root,
        cwd=cwd,
        user_rule_dirs=accepted_rule_dirs_from_env(),
    )
    source_identity_text = json.dumps(_json_safe(source_identity), ensure_ascii=False, sort_keys=True)
    snapshots: list[dict[str, Any]] = []
    for route in (*base_routes, *accepted_routes):
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
        }
    return {
        "sha256": _file_sha256(path) if exists else None,
        "hash_scope": "file",
        "active_rule_count": None,
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
