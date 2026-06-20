"""Latest-output and retention helpers for prepare."""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from .atomic_io import atomic_write_json
from .fs_safety import safe_rmtree
from .prepare_publish import (
    publish_direct_final_to_source,
    source_final_assets_dir,
    source_final_markdown_path,
)

logger = logging.getLogger(__name__)

OBSIDIAN_PROFILES = {"obsidian_kb", "curated_obsidian_kb"}


def latest_output_paths(root_p: Path, input_p: Path | None = None, profile: str = "standard") -> dict:
    """Return stable top-level paths for the latest successful run."""
    source_side_final = profile not in OBSIDIAN_PROFILES
    final_artifact_type = "markdown" if source_side_final else "obsidian_dir"
    final_md = (source_final_markdown_path(input_p) if input_p else root_p / "cleaned.md") if source_side_final else None
    final_assets_dir = (source_final_assets_dir(input_p) if input_p else root_p / "images") if source_side_final else None
    obsidian_dir = root_p / "obsidian"
    obsidian_index = obsidian_dir / "00-索引.md"
    obsidian_complete = _obsidian_complete_path(obsidian_dir)
    review_pack = root_p / "review_pack.json"
    return {
        "converted_md": str(root_p / "converted.md"),
        "diagnosis_report": str(root_p / "diagnosis_report.json"),
        "blocks_jsonl": str(root_p / "blocks.jsonl"),
        "cleaned_md": str(root_p / "cleaned.md"),
        "final_artifact_type": final_artifact_type,
        "final_md": str(final_md) if final_md else None,
        "final_assets_dir": str(final_assets_dir) if final_assets_dir else None,
        "discarded_md": str(root_p / "discarded.md"),
        "review_needed_md": str(root_p / "review_needed.md"),
        "quality_report": str(root_p / "quality_report.json"),
        "publish_report": str(root_p / "publish_report.json") if (root_p / "publish_report.json").exists() else None,
        "quality_gates_dir": str(root_p / "quality_gates") if (root_p / "quality_gates").exists() else None,
        "conversion_quality_report": str(root_p / "conversion_quality_report.json"),
        "conversion_report": str(root_p / "conversion_report.json"),
        "audit_md": str(root_p / "audit.md"),
        "parts_dir": str(root_p / "parts"),
        "images_dir": str(root_p / "images"),
        "obsidian_dir": str(obsidian_dir) if obsidian_dir.exists() else None,
        "obsidian_index": str(obsidian_index) if obsidian_index.exists() else None,
        "obsidian_complete": str(obsidian_complete) if obsidian_complete else None,
        "review_pack": str(review_pack) if review_pack.exists() else None,
    }


def _obsidian_complete_path(obsidian_dir: Path) -> Path | None:
    if not obsidian_dir.exists():
        return None
    legacy = obsidian_dir / "01-完整正文.md"
    if legacy.exists():
        return legacy
    candidates = [path for path in obsidian_dir.glob("*.md") if path.name != "00-索引.md"]
    if len(candidates) == 1:
        return candidates[0]
    return None


def publish_latest_outputs(run_dir: Path, root_p: Path, input_p: Path, profile: str = "standard") -> dict:
    """Copy successful run artifacts to output_root for direct reading."""
    root_p.mkdir(parents=True, exist_ok=True)
    _copy_latest_top_level_files(run_dir, root_p)
    if profile not in OBSIDIAN_PROFILES:
        publish_direct_final_to_source(run_dir, input_p)
    _sync_latest_output_dirs(run_dir, root_p)
    return latest_output_paths(root_p, input_p, profile)


def _copy_latest_top_level_files(run_dir: Path, root_p: Path) -> None:
    for name in _latest_top_level_names():
        src = run_dir / name
        dst = root_p / name
        if src.exists():
            shutil.copy2(str(src), str(dst))
        elif dst.exists() and name == "review_pack.json":
            dst.unlink()


def _latest_top_level_names() -> tuple[str, ...]:
    return (
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
    )


def _sync_latest_output_dirs(run_dir: Path, root_p: Path) -> None:
    _sync_optional_dir(run_dir / "parts", root_p / "parts", root_p, ensure_empty=True)
    _sync_optional_dir(run_dir / "quality_gates", root_p / "quality_gates", root_p)
    _sync_optional_dir(run_dir / "images", root_p / "images", root_p, ensure_empty=True)
    _sync_optional_dir(run_dir / "obsidian", root_p / "obsidian", root_p)


def _sync_optional_dir(src: Path, dst: Path, root_p: Path, *, ensure_empty: bool = False) -> None:
    if dst.exists():
        safe_rmtree(dst, root=root_p)
    if src.exists():
        shutil.copytree(src, dst)
    elif ensure_empty:
        dst.mkdir(parents=True, exist_ok=True)


def apply_artifact_policy(root_p: Path, current_run_dir: Path, artifact_policy: str) -> None:
    if artifact_policy == "keep_all":
        return
    if artifact_policy not in {"keep_latest", "final_only"}:
        artifact_policy = "keep_latest"

    runs_dir = root_p / "runs"
    if not runs_dir.exists():
        return

    keep_count = 1 if artifact_policy == "final_only" else 3
    max_age_seconds = 7 * 86400
    now = time.time()
    run_dirs = sorted(
        [p for p in runs_dir.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    keep = {current_run_dir.resolve()}
    for run_dir in run_dirs[:keep_count]:
        keep.add(run_dir.resolve())

    for run_dir in run_dirs:
        try:
            is_current = run_dir.resolve() == current_run_dir.resolve()
            is_expired = (now - run_dir.stat().st_mtime) > max_age_seconds
            if (run_dir.resolve() not in keep or is_expired) and not is_current:
                safe_rmtree(run_dir, root=runs_dir)
        except Exception as exc:
            logger.warning("Failed to prune old run %s: %s", run_dir, exc)


def write_publish_report(
    *,
    run_dir: Path,
    root_p: Path,
    input_p: Path,
    profile: str,
    latest_outputs: dict,
    strict_errors: list[str],
) -> Path:
    report_path = run_dir / "publish_report.json"
    report = _publish_report_payload(
        run_dir=run_dir,
        root_p=root_p,
        input_p=input_p,
        profile=profile,
        latest_outputs=latest_outputs,
        strict_errors=strict_errors,
    )
    atomic_write_json(report_path, report, indent=2, trailing_newline=False)
    return report_path


def _publish_report_payload(
    *,
    run_dir: Path,
    root_p: Path,
    input_p: Path,
    profile: str,
    latest_outputs: dict,
    strict_errors: list[str],
) -> dict:
    published = not strict_errors
    return {
        "schema": "kbprep.publish_report.v1",
        "status": "published" if published else "blocked",
        "published": published,
        "profile": profile,
        "source_path": str(input_p),
        "output_root": str(root_p),
        "final_artifact": _final_artifact_summary(latest_outputs) if published else None,
        "process_evidence": _process_evidence_summary(run_dir),
        "cleanup_guidance": _cleanup_guidance(root_p, published),
        "blocked_reason": {"strict_errors": strict_errors} if strict_errors else None,
    }


def _final_artifact_summary(latest_outputs: dict) -> dict:
    return {
        "final_artifact_type": latest_outputs.get("final_artifact_type"),
        "final_md": latest_outputs.get("final_md"),
        "final_assets_dir": latest_outputs.get("final_assets_dir"),
        "obsidian_dir": latest_outputs.get("obsidian_dir"),
        "obsidian_index": latest_outputs.get("obsidian_index"),
        "obsidian_complete": latest_outputs.get("obsidian_complete"),
    }


def _process_evidence_summary(run_dir: Path) -> dict:
    return {
        "run_dir": str(run_dir),
        "converted_md": str(run_dir / "converted.md"),
        "cleaned_md": str(run_dir / "cleaned.md"),
        "discarded_md": str(run_dir / "discarded.md"),
        "review_needed_md": str(run_dir / "review_needed.md"),
        "quality_report": str(run_dir / "quality_report.json"),
        "conversion_quality_report": str(run_dir / "conversion_quality_report.json"),
    }


def _cleanup_guidance(root_p: Path, published: bool) -> dict:
    return {
        "can_finalize": published,
        "cleanup_command": f"kbprep-cleanup --output {root_p} --action finalize" if published else None,
        "keep": (
            "Keep the final_artifact paths. Process evidence can be finalized after review."
            if published
            else "Do not finalize this run. Inspect strict errors and keep process evidence for repair."
        ),
    }
