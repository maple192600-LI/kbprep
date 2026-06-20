"""Cleanup lifecycle management for kbprep artifacts.

The source file and source-side final Markdown are user assets. Everything
under output_root is treated as temporary audit/process material unless the
user intentionally keeps it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .envelope import fail, ok
from .fs_safety import safe_rmtree, safe_unlink

TOP_LEVEL_FILES = [
    "converted.md",
    "diagnosis_report.json",
    "blocks.jsonl",
    "cleaned.md",
    "discarded.md",
    "review_needed.md",
    "quality_report.json",
    "publish_report.json",
    "conversion_quality_report.json",
    "conversion_report.json",
    "audit.md",
    "review_pack.json",
    "latest.json",
    "batch_inventory.json",
    "batch_manifest.json",
    "progress.json",
    "failures.json",
    "results.json",
]

TOP_LEVEL_DIRS = [
    "original",
    "runs",
    "parts",
    "images",
    "obsidian",
    "files",
]


def run(data: dict) -> None:
    output_root = Path(data["output_root"])
    action = data.get("action", "finalize")
    dry_run = bool(data.get("dry_run", False))
    confirm_review_needed = bool(data.get("confirm_review_needed", False))
    older_than_days = float(data.get("older_than_days", 7))

    if action not in {"finalize", "expired", "all"}:
        fail(
            "E_INVALID_INPUT",
            f"Unsupported cleanup action: {action}",
            details={"allowed_actions": ["finalize", "expired", "all"]},
        )

    if not output_root.exists() or not output_root.is_dir():
        fail("E_INVALID_INPUT", f"output_root does not exist or is not a directory: {output_root}")

    root = output_root.resolve()

    if action == "finalize":
        if (root / "results.json").exists() and not (root / "latest.json").exists():
            result = _finalize_batch(root, confirm_review_needed=confirm_review_needed, dry_run=dry_run)
        else:
            result = _finalize_single(root, confirm_review_needed=confirm_review_needed, dry_run=dry_run)
    elif action == "expired":
        result = _cleanup_expired(root, older_than_days=older_than_days, dry_run=dry_run)
    else:
        result = _cleanup_all(root, dry_run=dry_run)

    ok(data=result)


def _finalize_single(root: Path, *, confirm_review_needed: bool, dry_run: bool) -> dict:
    latest_path = root / "latest.json"
    if not latest_path.exists():
        fail(
            "KBPREP_NO_SUCCESSFUL_RUN",
            "No latest.json found. Run kbprep_prepare successfully before finalizing cleanup.",
            details={"output_root": str(root)},
        )

    latest = _read_json(latest_path)
    latest_outputs = latest.get("latest_outputs", {})
    try:
        final_artifact = _final_artifact_from_outputs(latest_outputs, file_label=latest.get("input_path"))
    except ValueError as exc:
        fail(
            "KBPREP_FINAL_OUTPUT_MISSING",
            f"{exc}. Cleanup stopped to avoid deleting audit evidence.",
            details={"latest_json": str(latest_path), "output_root": str(root), "latest_outputs": latest_outputs},
        )
    _guard_single_review_needed(root, confirm_review_needed)
    manifest = _single_cleanup_manifest(latest, final_artifact)

    deleted = _delete_standard_artifacts(root, dry_run=dry_run, protected_paths=final_artifact["protected_paths"])
    manifest_path = root / "kbprep_manifest.json"
    if not dry_run:
        atomic_write_json(manifest_path, manifest, indent=2, trailing_newline=False)

    return {
        "action": "finalize",
        "output_root": str(root),
        **final_artifact["return_fields"],
        "manifest": str(manifest_path),
        "deleted": deleted,
        "dry_run": dry_run,
    }


def _finalize_batch(root: Path, *, confirm_review_needed: bool, dry_run: bool) -> dict:
    results_path = root / "results.json"
    results = _read_json(results_path)
    if not isinstance(results, list):
        fail("KBPREP_INVALID_STATE", "results.json is not a batch results array.", details={"results_json": str(results_path)})

    finalized, missing, review_needed, protected_paths = _collect_batch_finalization(results)
    if missing:
        fail(
            "KBPREP_FINAL_OUTPUT_MISSING",
            "Some batch final deliverables are missing. Cleanup stopped.",
            details={"missing": missing[:20], "missing_count": len(missing)},
        )
    if review_needed and not confirm_review_needed:
        fail(
            "KBPREP_REVIEW_NEEDED",
            "Some batch files still have review_needed.md content. Confirm cleanup only after you accept the results.",
            details={"review_needed": review_needed[:20], "review_needed_count": len(review_needed)},
        )

    manifest = _batch_cleanup_manifest(finalized)
    deleted = _delete_standard_artifacts(root, dry_run=dry_run, protected_paths=protected_paths)
    manifest_path = root / "kbprep_batch_manifest.json"
    if not dry_run:
        atomic_write_json(manifest_path, manifest, indent=2, trailing_newline=False)

    return {
        "action": "finalize",
        "output_root": str(root),
        "manifest": str(manifest_path),
        "finalized": finalized,
        "deleted": deleted,
        "dry_run": dry_run,
    }


def _guard_single_review_needed(root: Path, confirm_review_needed: bool) -> None:
    review_needed = root / "review_needed.md"
    if not _has_review_content(review_needed) or confirm_review_needed:
        return
    fail(
        "KBPREP_REVIEW_NEEDED",
        "review_needed.md still has content. Confirm cleanup only after you accept the result.",
        details={"review_needed_md": str(review_needed)},
        suggested_action="Inspect review_needed.md, then rerun cleanup with confirm_review_needed=true if you accept it.",
    )


def _single_cleanup_manifest(latest: dict, final_artifact: dict) -> dict:
    return {
        "schema": "kbprep.cleanup_manifest.v1",
        "status": "finalized",
        "finalized_at": time.time(),
        "source_path": latest.get("input_path"),
        "source_sha256": latest.get("source_sha256"),
        "source_type": latest.get("source_type"),
        **final_artifact["manifest_fields"],
        "run_id": latest.get("run_id"),
        "plugin_version": latest.get("plugin_version"),
        "runtime_cache_key": latest.get("runtime_cache_key"),
    }


def _collect_batch_finalization(results: list) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[Path]]:
    finalized: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    review_needed: list[str] = []
    protected_paths: list[Path] = []
    for entry in results:
        if not isinstance(entry, dict) or not entry.get("ok"):
            continue
        _append_batch_finalization_entry(entry, finalized, missing, review_needed, protected_paths)
    return finalized, missing, review_needed, protected_paths


def _append_batch_finalization_entry(
    entry: dict,
    finalized: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    review_needed: list[str],
    protected_paths: list[Path],
) -> None:
    file_label = entry.get("relative_path") or entry.get("file")
    try:
        final_artifact = _final_artifact_from_batch_entry(entry)
    except ValueError as exc:
        missing.append({"file": file_label, "reason": str(exc)})
        return
    protected_paths.extend(final_artifact["protected_paths"])
    review_path = Path(entry.get("output_root", "")) / "review_needed.md"
    if _has_review_content(review_path):
        review_needed.append(str(review_path))
    finalized.append({"file": file_label, **final_artifact["manifest_fields"], "run_id": entry.get("run_id")})


def _batch_cleanup_manifest(finalized: list[dict[str, Any]]) -> dict:
    return {
        "schema": "kbprep.batch_cleanup_manifest.v1",
        "status": "finalized",
        "finalized_at": time.time(),
        "total_finalized": len(finalized),
        "finalized": finalized,
    }


def _final_artifact_from_batch_entry(entry: dict[str, Any]) -> dict[str, Any]:
    latest_outputs = entry.get("latest_outputs", {})
    if not isinstance(latest_outputs, dict):
        latest_outputs = {}
    merged_outputs = dict(latest_outputs)
    if entry.get("batch_final_md"):
        merged_outputs["final_md"] = entry.get("batch_final_md")
        merged_outputs.setdefault("final_artifact_type", "markdown")
    if entry.get("batch_obsidian_dir"):
        merged_outputs["obsidian_dir"] = entry.get("batch_obsidian_dir")
        merged_outputs.setdefault("final_artifact_type", "obsidian_dir")
    if entry.get("batch_obsidian_index"):
        merged_outputs["obsidian_index"] = entry.get("batch_obsidian_index")
        merged_outputs.setdefault("final_artifact_type", "obsidian_dir")
    try:
        return _final_artifact_from_outputs(merged_outputs, file_label=entry.get("relative_path") or entry.get("file"))
    except SystemExit:
        raise
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _final_artifact_from_outputs(latest_outputs: dict[str, Any], *, file_label: str | None = None) -> dict[str, Any]:
    artifact_type = latest_outputs.get("final_artifact_type")
    if artifact_type not in {"markdown", "obsidian_dir"}:
        if latest_outputs.get("final_md"):
            artifact_type = "markdown"
        elif latest_outputs.get("obsidian_dir") or latest_outputs.get("obsidian_index"):
            artifact_type = "obsidian_dir"

    if artifact_type == "markdown":
        final_md_raw = latest_outputs.get("final_md")
        if not final_md_raw:
            raise ValueError("latest outputs do not record final_md")
        final_md = Path(final_md_raw)
        if not final_md.exists():
            raise ValueError(f"final Markdown is missing: {final_md}")
        manifest_fields = {
            "final_artifact_type": "markdown",
            "final_md": str(final_md),
            "final_assets_dir": latest_outputs.get("final_assets_dir"),
        }
        return {
            "manifest_fields": manifest_fields,
            "return_fields": manifest_fields,
            "protected_paths": [final_md],
        }

    if artifact_type == "obsidian_dir":
        obsidian_dir_raw = latest_outputs.get("obsidian_dir")
        obsidian_index_raw = latest_outputs.get("obsidian_index")
        if not obsidian_dir_raw or not obsidian_index_raw:
            raise ValueError("latest outputs do not record obsidian_dir and obsidian_index")
        obsidian_dir = Path(obsidian_dir_raw)
        obsidian_index = Path(obsidian_index_raw)
        if not obsidian_dir.exists() or not obsidian_dir.is_dir():
            raise ValueError(f"Obsidian final directory is missing: {obsidian_dir}")
        if not obsidian_index.exists() or not obsidian_index.is_file():
            raise ValueError(f"Obsidian index is missing: {obsidian_index}")
        manifest_fields = {
            "final_artifact_type": "obsidian_dir",
            "obsidian_dir": str(obsidian_dir),
            "obsidian_index": str(obsidian_index),
            "obsidian_complete": latest_outputs.get("obsidian_complete"),
        }
        return {
            "manifest_fields": manifest_fields,
            "return_fields": manifest_fields,
            "protected_paths": [obsidian_dir],
        }

    raise ValueError(f"latest outputs do not record a supported final deliverable for {file_label or '<unknown>'}")


def _cleanup_expired(root: Path, *, older_than_days: float, dry_run: bool) -> dict:
    cutoff = time.time() - max(0.0, older_than_days) * 86400
    deleted: list[str] = []
    runs_dir = root / "runs"
    if runs_dir.exists():
        for child in runs_dir.iterdir():
            if child.is_dir() and child.stat().st_mtime < cutoff:
                _delete_path(root, child, deleted, dry_run=dry_run)

    files_dir = root / "files"
    if files_dir.exists():
        for child in files_dir.iterdir():
            runs = child / "runs"
            if runs.exists():
                for run_dir in runs.iterdir():
                    if run_dir.is_dir() and run_dir.stat().st_mtime < cutoff:
                        _delete_path(root, run_dir, deleted, dry_run=dry_run)

    return {
        "action": "expired",
        "output_root": str(root),
        "older_than_days": older_than_days,
        "deleted": deleted,
        "dry_run": dry_run,
    }


def _cleanup_all(root: Path, *, dry_run: bool) -> dict:
    deleted = _delete_standard_artifacts(root, dry_run=dry_run)
    return {
        "action": "all",
        "output_root": str(root),
        "deleted": deleted,
        "dry_run": dry_run,
    }


def _delete_standard_artifacts(root: Path, *, dry_run: bool, protected_paths: list[Path] | None = None) -> list[str]:
    deleted: list[str] = []
    protected = {path.resolve() for path in protected_paths or []}
    for name in TOP_LEVEL_FILES:
        _delete_path(root, root / name, deleted, dry_run=dry_run, protected_paths=protected)
    for name in TOP_LEVEL_DIRS:
        _delete_path(root, root / name, deleted, dry_run=dry_run, protected_paths=protected)
    return deleted


def _delete_path(root: Path, path: Path, deleted: list[str], *, dry_run: bool, protected_paths: set[Path] | None = None) -> None:
    if not path.exists():
        return
    protected_paths = protected_paths or set()
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise RuntimeError(f"Refusing to delete outside output_root: {resolved}")
    if resolved in protected_paths:
        return
    protected_descendants = [protected for protected in protected_paths if resolved in protected.parents]
    if protected_descendants and path.is_dir():
        for child in list(path.iterdir()):
            _delete_path(root, child, deleted, dry_run=dry_run, protected_paths=protected_paths)
        if not any(path.iterdir()) and resolved != root:
            deleted.append(str(resolved))
            if not dry_run:
                path.rmdir()
        return
    deleted.append(str(resolved))
    if dry_run:
        return
    if path.is_dir():
        safe_rmtree(path, root=root)
    else:
        safe_unlink(path, root=root)


def _has_review_content(path: Path) -> bool:
    if not path.exists():
        return False
    return bool(path.read_text(encoding="utf-8").strip())


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail("KBPREP_INVALID_STATE", f"Invalid JSON file: {path}", details={"error": str(exc)})
