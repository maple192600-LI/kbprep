"""Batch status manifest writer."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json

BATCH_MANIFEST_SCHEMA = "kbprep.batch_manifest.v1"


def write_batch_manifest(
    *,
    output_root: Path,
    input_dir: Path,
    inventory: dict[str, Any],
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    counters: dict[str, int],
    started_at: float,
    stage: str,
    finished_at: float | None = None,
    command_defaults: dict[str, Any] | None = None,
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    items = _manifest_items(inventory, results, failures)
    rerun = _rerun_scope(items)
    if command_defaults:
        rerun["command_defaults"] = _command_defaults(command_defaults)
    payload = {
        "schema": BATCH_MANIFEST_SCHEMA,
        "status": _parent_status(items),
        "stage": stage,
        "input_dir": str(input_dir),
        "output_root": str(output_root),
        "summary": _summary(inventory, results, counters, items),
        "items": items,
        "rerun": rerun,
        "artifacts": _artifacts(output_root),
        "started_at": started_at,
        "updated_at": finished_at or time.time(),
        "finished_at": finished_at,
    }
    source_collection = inventory.get("source_collection")
    if isinstance(source_collection, dict):
        payload["source_collection"] = source_collection
    path = output_root / "batch_manifest.json"
    atomic_write_json(path, payload, indent=2, trailing_newline=False)
    return path


def _command_defaults(command_defaults: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "profile",
        "mode",
        "language",
        "force",
        "artifact_policy",
        "max_quality_iterations",
        "convert_jobs",
        "allow_youtube_media_fallback",
    }
    return {key: command_defaults[key] for key in allowed if key in command_defaults}


def _manifest_items(
    inventory: dict[str, Any],
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result_by_path = _by_relative_path(results)
    failure_by_path = _by_relative_path(failures)
    items: list[dict[str, Any]] = []
    for entry in inventory.get("files", []):
        relative_path = str(entry.get("relative_path") or entry.get("file") or "")
        if entry.get("action") == "skip":
            items.append(_skipped_item(entry, relative_path))
            continue
        result = result_by_path.get(relative_path)
        failure = failure_by_path.get(relative_path)
        items.append(_processed_or_pending_item(entry, relative_path, result, failure))
    return items


def _by_relative_path(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for entry in entries:
        relative_path = entry.get("relative_path")
        if isinstance(relative_path, str):
            indexed[relative_path] = entry
    return indexed


def _skipped_item(entry: dict[str, Any], relative_path: str) -> dict[str, Any]:
    return {
        "relative_path": relative_path,
        "file": entry.get("file"),
        "status": "skipped_unsupported",
        "detected_format": entry.get("detected_format"),
        "reason": entry.get("reason"),
        "rerunnable": False,
    }


def _processed_or_pending_item(
    entry: dict[str, Any],
    relative_path: str,
    result: dict[str, Any] | None,
    failure: dict[str, Any] | None,
) -> dict[str, Any]:
    if result is None:
        return _pending_item(entry, relative_path)
    if result.get("ok") and not result.get("strict_errors"):
        return _succeeded_item(entry, relative_path, result)
    return _failed_item(entry, relative_path, failure or result)


def _pending_item(entry: dict[str, Any], relative_path: str) -> dict[str, Any]:
    return {
        "relative_path": relative_path,
        "file": entry.get("file"),
        **_source_evidence(entry),
        "status": "pending",
        "reason": "blocked_before_processing",
        "rerunnable": True,
    }


def _succeeded_item(entry: dict[str, Any], relative_path: str, result: dict[str, Any]) -> dict[str, Any]:
    status = "skipped_existing" if result.get("skipped") else "succeeded"
    return {
        "relative_path": relative_path,
        "file": entry.get("file"),
        **_source_evidence(entry),
        "status": status,
        "run_id": result.get("run_id"),
        "output_root": result.get("output_root"),
        "rerunnable": False,
    }


def _failed_item(entry: dict[str, Any], relative_path: str, failure: dict[str, Any]) -> dict[str, Any]:
    error = _dict_value(failure.get("error"))
    return {
        "relative_path": relative_path,
        "file": entry.get("file"),
        **_source_evidence(entry),
        "status": "failed",
        "output_root": failure.get("output_root"),
        "failure_code": error.get("code") or "unknown",
        "failure_stage": _failure_stage(error),
        "rerunnable": True,
    }


def _source_evidence(entry: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    if entry.get("source_url"):
        evidence["source_url"] = entry.get("source_url")
    if entry.get("source_sha256"):
        evidence["source_sha256"] = entry.get("source_sha256")
    if entry.get("size_bytes") is not None:
        evidence["size_bytes"] = entry.get("size_bytes")
    return evidence


def _failure_stage(error: dict[str, Any]) -> str:
    details = _dict_value(error.get("details"))
    primary = _dict_value(details.get("primary_quality_issue"))
    return str(details.get("stage") or primary.get("gate") or error.get("code") or "unknown")


def _dict_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _parent_status(items: list[dict[str, Any]]) -> str:
    failed = [item for item in items if item.get("status") == "failed"]
    pending = [item for item in items if item.get("status") == "pending"]
    succeeded = [item for item in items if item.get("status") in {"succeeded", "skipped_existing"}]
    skipped = [item for item in items if item.get("status") == "skipped_unsupported"]
    if failed and not succeeded:
        return "failed"
    if failed or pending or skipped:
        return "completed_with_warnings"
    return "completed"


def batch_parent_status(
    inventory: dict[str, Any],
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> str:
    """Return the batch parent job status from child results (core design §16/§17).

    Public mirror of the status written into batch_manifest.json so emitters
    (e.g. the batch success envelope) can publish the same status without
    re-reading the manifest file.
    """
    return _parent_status(_manifest_items(inventory, results, failures))


def _summary(
    inventory: dict[str, Any],
    results: list[dict[str, Any]],
    counters: dict[str, int],
    items: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "total": int(inventory.get("processable_total", 0)),
        "discovered_total": int(inventory.get("discovered_total", 0)),
        "processed": len(results),
        "succeeded": counters.get("succeeded", 0),
        "failed": counters.get("failed", 0),
        "skipped_existing": counters.get("skipped", 0),
        "skipped_unsupported": int(inventory.get("skipped_unsupported", 0)),
        "pending": len([item for item in items if item.get("status") == "pending"]),
    }


def _rerun_scope(items: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [str(item["relative_path"]) for item in items if item.get("status") == "failed"]
    pending = [str(item["relative_path"]) for item in items if item.get("status") == "pending"]
    skipped = [str(item["relative_path"]) for item in items if item.get("status") == "skipped_unsupported"]
    return {
        "recommended_scope": _recommended_scope(failed, pending),
        "failed_only": failed,
        "pending": pending,
        "affected": failed + pending,
        "skipped_unsupported": skipped,
    }


def _recommended_scope(failed: list[str], pending: list[str]) -> str:
    if failed and pending:
        return "failed_and_pending"
    if failed:
        return "failed_only"
    if pending:
        return "pending_only"
    return "none"


def _artifacts(output_root: Path) -> dict[str, str]:
    return {
        "batch_inventory_json": str(output_root / "batch_inventory.json"),
        "progress_json": str(output_root / "progress.json"),
        "failures_json": str(output_root / "failures.json"),
        "results_json": str(output_root / "results.json"),
        "files_dir": str(output_root / "files"),
    }
