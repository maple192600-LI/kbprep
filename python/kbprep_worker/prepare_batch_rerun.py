"""Selective rerun support for directory batch manifests."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from . import prepare_batch as batch
from .atomic_io import atomic_write_json
from .envelope import fail, ok
from .fs_safety import is_safe_input_path, is_safe_output_root

BATCH_RERUN_MANIFEST_SCHEMA = "kbprep.batch_rerun_manifest.v1"


def run_batch_rerun(data: dict[str, Any]) -> None:
    manifest_path = _required_batch_manifest_path(data)
    manifest = _read_batch_manifest(manifest_path)
    defaults = _dict_value(_dict_value(manifest.get("rerun")).get("command_defaults"))
    config = _batch_rerun_config(data, manifest, defaults)
    input_p, output_p = Path(config.input_dir), Path(config.output_root)
    requested_scope = str(data.get("rerun_scope") or "recommended")
    selected_items = _selected_rerun_items(manifest, requested_scope)
    selected = [str(item.get("relative_path")) for item in selected_items]
    if not selected:
        fail("E_BATCH_RERUN_EMPTY", "Batch manifest has no rerunnable items for the requested scope.")

    started_at = time.time()
    batch._ensure_batch_memory(config.min_free_gb)
    results, failures = _execute_batch_rerun_items(config, input_p, output_p, selected_items)
    manifest_out = _write_batch_rerun_manifest(
        output_p=output_p,
        source_manifest=manifest_path,
        scope=_effective_rerun_scope(manifest, requested_scope),
        selected=selected,
        results=results,
        failures=failures,
        skipped_unsupported=_string_list(_dict_value(manifest.get("rerun")).get("skipped_unsupported")),
        started_at=started_at,
        command_defaults=batch._batch_command_defaults(config),
    )
    _emit_batch_rerun_result(
        status=_batch_rerun_status(results, failures),
        selected=selected,
        results=results,
        failures=failures,
        manifest_out=manifest_out,
        manifest_path=manifest_path,
    )


def _required_batch_manifest_path(data: dict[str, Any]) -> Path:
    raw = data.get("batch_manifest_path") or data.get("batch_manifest")
    raw_text = raw.strip() if isinstance(raw, str) else ""
    if not raw_text:
        fail("E_INVALID_INPUT", "batch rerun requires batch_manifest_path.")
    path = Path(raw_text).expanduser()
    if not path.is_file():
        fail("E_INVALID_INPUT", f"batch_manifest_path is not a file: {path}")
    return path


def _read_batch_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail("E_INVALID_INPUT", f"Cannot read batch manifest: {exc}")
    if not isinstance(payload, dict) or payload.get("schema") != "kbprep.batch_manifest.v1":
        fail("E_INVALID_INPUT", "batch rerun requires a kbprep.batch_manifest.v1 manifest.")
    return payload


def _batch_rerun_config(
    data: dict[str, Any],
    manifest: dict[str, Any],
    defaults: dict[str, Any],
) -> batch.BatchConfig:
    input_dir = str(manifest.get("input_dir") or "")
    output_root = str(manifest.get("output_root") or "")
    if not input_dir or not output_root:
        fail("E_INVALID_INPUT", "Batch manifest is missing input_dir or output_root.")
    _ensure_safe_manifest_paths(input_dir, output_root)
    return batch.BatchConfig(
        input_dir=input_dir,
        output_root=output_root,
        profile=str(data.get("profile") or defaults.get("profile") or "standard"),
        language=str(data.get("language") or defaults.get("language") or "zh"),
        mode=str(data.get("mode") or defaults.get("mode") or "rules_only"),
        force=_force_value(data, defaults),
        artifact_policy=str(data.get("artifact_policy") or defaults.get("artifact_policy") or "keep_latest"),
        max_quality_iterations=data.get(
            "max_quality_iterations",
            defaults.get("max_quality_iterations", batch.DEFAULT_MAX_QUALITY_ITERATIONS),
        ),
        min_free_gb=float(data.get("min_free_memory_gb", batch.DEFAULT_MIN_FREE_GB)),
        convert_jobs=int(data.get("convert_jobs", defaults.get("convert_jobs", 1))),
    )


def _ensure_safe_manifest_paths(input_dir: str, output_root: str) -> None:
    input_p = Path(input_dir)
    output_p = Path(output_root)
    if not input_p.exists() or not input_p.is_dir():
        fail("E_INVALID_INPUT", f"Batch manifest input_dir is not a directory: {input_dir}")
    if not is_safe_input_path(input_p):
        fail("E_INVALID_INPUT", f"Unsafe batch manifest input_dir: {input_dir}")
    _ensure_inside_cli_boundary(input_p, "input_dir", "E_INVALID_INPUT")
    if not is_safe_output_root(output_p):
        fail("E_INVALID_OUTPUT_ROOT", f"Unsafe batch manifest output_root: {output_root}")
    _ensure_inside_cli_boundary(output_p, "output_root", "E_INVALID_OUTPUT_ROOT")


def _ensure_inside_cli_boundary(path: Path, label: str, code: str) -> None:
    boundary = os.environ.get("KBPREP_CLI_BOUNDARY_DIR", "").strip()
    if not boundary:
        return
    try:
        boundary_p = Path(boundary).resolve()
        target = path.resolve()
    except (OSError, RuntimeError):
        fail(code, f"Batch manifest {label} cannot be resolved: {path}")
    if target == boundary_p or boundary_p in target.parents:
        return
    fail(code, f"Batch manifest {label} escapes CLI boundary: {path}")


def _force_value(data: dict[str, Any], defaults: dict[str, Any]) -> bool:
    value = data.get("force")
    if value is None:
        value = defaults.get("force", True)
    return bool(value)


def _selected_rerun_items(manifest: dict[str, Any], requested_scope: str) -> list[dict[str, Any]]:
    rerun = _dict_value(manifest.get("rerun"))
    items_by_path = _items_by_path(manifest)
    scope = _effective_rerun_scope(manifest, requested_scope)
    if scope == "failed_only":
        return _manifest_items_for_paths(items_by_path, _string_list(rerun.get("failed_only")))
    if scope == "pending_only":
        return _manifest_items_for_paths(items_by_path, _string_list(rerun.get("pending")))
    if scope == "failed_and_pending":
        return _manifest_items_for_paths(items_by_path, _string_list(rerun.get("affected")))
    return []


def _items_by_path(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = manifest.get("items")
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("relative_path")): item
        for item in items
        if isinstance(item, dict) and item.get("relative_path")
    }


def _manifest_items_for_paths(items_by_path: dict[str, dict[str, Any]], paths: list[str]) -> list[dict[str, Any]]:
    return [items_by_path.get(path, {"relative_path": path}) for path in paths]


def _effective_rerun_scope(manifest: dict[str, Any], requested_scope: str) -> str:
    normalized = requested_scope.replace("-", "_")
    if normalized == "recommended":
        rerun = _dict_value(manifest.get("rerun"))
        normalized = str(rerun.get("recommended_scope") or "none")
    if normalized == "failed_and_pending":
        return "failed_and_pending"
    if normalized in {"failed_only", "pending_only", "none"}:
        return normalized
    fail("E_INVALID_INPUT", f"Unsupported batch rerun scope: {requested_scope}")
    return "none"


def _execute_batch_rerun_items(
    config: batch.BatchConfig,
    input_p: Path,
    output_p: Path,
    selected: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for item in selected:
        relative_path = str(item.get("relative_path") or "")
        file_path = _safe_rerun_file(input_p, relative_path)
        if file_path is None:
            failures.append(_missing_rerun_file(relative_path))
            continue
        source_changed = _changed_rerun_file(file_path, item)
        if source_changed:
            failures.append(source_changed)
            continue
        output_root = batch._output_root_for_file(output_p, file_path)
        result = batch._process_configured_file(config, file_path, output_root)
        _append_rerun_result(file_path, relative_path, output_root, result, results, failures)
    return results, failures


def _safe_rerun_file(input_p: Path, relative_path: str) -> Path | None:
    candidate = (input_p / relative_path).resolve()
    root = input_p.resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def _missing_rerun_file(relative_path: str) -> dict[str, Any]:
    return {
        "relative_path": relative_path,
        "error": {"code": "E_INPUT_NOT_FOUND", "message": "Batch rerun source file is missing."},
    }


def _changed_rerun_file(file_path: Path, item: dict[str, Any]) -> dict[str, Any] | None:
    expected = item.get("source_sha256")
    if not isinstance(expected, str) or not expected:
        return None
    actual = _file_sha256(file_path)
    if actual == expected:
        return None
    return {
        "relative_path": str(item.get("relative_path") or file_path.name),
        "error": {
            "code": "E_SOURCE_CHANGED",
            "message": "Batch rerun source file changed since the source manifest was written.",
            "expected_source_sha256": expected,
            "actual_source_sha256": actual,
        },
    }


def _file_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_rerun_result(
    file_path: Path,
    relative_path: str,
    output_root: Path,
    result: dict[str, Any],
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> None:
    if result.get("ok") and not _dict_value(result.get("data")).get("strict_errors"):
        entry = batch._result_entry(file_path, relative_path, output_root, result)
        entry.update(batch._batch_final_fields_from_result(_dict_value(result.get("data"))))
        results.append(entry)
        return
    failures.append(batch._failure_entry(file_path, relative_path, output_root, result))


def _write_batch_rerun_manifest(
    *,
    output_p: Path,
    source_manifest: Path,
    scope: str,
    selected: list[str],
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    skipped_unsupported: list[str],
    started_at: float,
    command_defaults: dict[str, Any],
) -> Path:
    payload = {
        "schema": BATCH_RERUN_MANIFEST_SCHEMA,
        "status": _batch_rerun_status(results, failures),
        "source_batch_manifest": str(source_manifest),
        "scope": scope,
        "selected": selected,
        "skipped_unsupported": skipped_unsupported,
        "summary": {"selected": len(selected), "succeeded": len(results), "failed": len(failures)},
        "results": results,
        "failures": failures,
        "command_defaults": command_defaults,
        "started_at": started_at,
        "finished_at": time.time(),
    }
    path = output_p / "batch_rerun_manifest.json"
    atomic_write_json(path, payload, indent=2, trailing_newline=False)
    return path


def _emit_batch_rerun_result(
    *,
    status: str,
    selected: list[str],
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    manifest_out: Path,
    manifest_path: Path,
) -> None:
    if status == "failed":
        fail(
            "E_BATCH_RERUN_FAILED",
            "Batch rerun failed for every selected item.",
            details={"batch_rerun_manifest_json": str(manifest_out), "source_batch_manifest": str(manifest_path)},
        )
    ok(
        data={
            "status": status,
            "selected": len(selected),
            "succeeded": len(results),
            "failed": len(failures),
            "batch_rerun_manifest_json": str(manifest_out),
            "source_batch_manifest": str(manifest_path),
        },
        status=status,
    )


def _batch_rerun_status(results: list[dict[str, Any]], failures: list[dict[str, Any]]) -> str:
    if failures and not results:
        return "failed"
    if failures:
        return "completed_with_warnings"
    return "completed"


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []
