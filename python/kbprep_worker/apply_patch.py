"""
apply_patch - apply guarded review patches to blocks.
Only allows changing: status, risk_tags, reason, confidence.
Cannot change: text, page_range, source_line_range.
Cannot discard protected blocks.
"""
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path

from .atomic_io import atomic_write_json, atomic_write_text
from .envelope import fail, ok
from .fs_safety import safe_rmtree
from .prepare_artifacts import publish_latest_outputs as _shared_publish_latest_outputs
from .quality import _detail_categories, _is_known_pollution_without_detail, _positive_int

logger = logging.getLogger(__name__)

OBSIDIAN_PROFILES = {"obsidian_kb", "curated_obsidian_kb"}

# ── Allowed fields ────────────────────────────────────────────────
ALLOWED_FIELDS = {"status", "risk_tags", "reason", "confidence"}
ALLOWED_STATUSES = {"keep", "discard", "evidence", "review"}
PROTECTED_TYPES = {"operation_step", "case_step", "tool_instruction", "prompt", "code", "table"}
KEEP_TYPES = {"operation_step", "case_step", "tool_instruction", "prompt", "code", "table"}


def run(data: dict) -> None:
    run_p = Path(data["run_dir"])
    blocks_path = run_p / "blocks.jsonl"
    quality_path = run_p / "quality_report.json"
    blocks = _read_blocks_or_fail(blocks_path, str(data["run_dir"]))
    applied, rejected = _apply_patch_ops(blocks, data["patch_json"])
    _write_blocks(blocks_path, blocks)

    previous_quality = _read_previous_quality(quality_path)
    source_hash = blocks[0].get("source_sha256", "") if blocks else ""
    run_id = run_p.name
    profile = _profile_for_patch_run(run_p)
    source_type = previous_quality.get("source_type", "generic_block")
    diagnosis = _read_diagnosis(run_p)
    _rerender_after_patch(blocks, run_p, source_hash, run_id, profile, previous_quality)
    _resplit_after_patch(blocks, run_p, source_type, source_hash, run_id, diagnosis)

    review_applied_at = time.time()
    quality_report = _rerun_quality_after_patch(
        blocks, run_p, source_type, diagnosis, profile, previous_quality, review_applied_at,
    )
    strict_errors = quality_report.get("strict_errors", [])
    latest_outputs = _run_output_paths(run_p)
    published = False
    if not strict_errors:
        output_root = _find_output_root(run_p)
        if output_root:
            latest_outputs = _publish_latest_outputs(run_p, output_root, profile)
            _update_latest_json(output_root, run_p, latest_outputs, previous_quality, source_type, review_applied_at)
            published = True

    updated_obsidian_complete = _obsidian_complete_path(run_p / "obsidian")
    ok(data={
        "applied": applied,
        "rejected": len(rejected),
        "rejected_details": rejected,
        "published": published,
        "updated_outputs": {
            "cleaned_md": str(run_p / "cleaned.md"),
            "discarded_md": str(run_p / "discarded.md"),
            "review_needed_md": str(run_p / "review_needed.md"),
            "audit_md": str(run_p / "audit.md"),
            "obsidian_dir": str(run_p / "obsidian") if (run_p / "obsidian").exists() else None,
            "obsidian_index": str(run_p / "obsidian" / "00-索引.md") if (run_p / "obsidian" / "00-索引.md").exists() else None,
            "obsidian_complete": str(updated_obsidian_complete) if updated_obsidian_complete else None,
            "quality_report": str(run_p / "quality_report.json"),
        },
        "latest_outputs": latest_outputs,
    })


def _read_blocks_or_fail(blocks_path: Path, run_dir: str) -> list[dict]:
    if not blocks_path.exists():
        fail("E_INPUT_NOT_FOUND", f"blocks.jsonl not found in {run_dir}")
    blocks = []
    with blocks_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                blocks.append(json.loads(line))
    return blocks


def _apply_patch_ops(blocks: list[dict], patch_json: list[dict]) -> tuple[int, list[dict]]:
    block_map = {block["block_id"]: block for block in blocks}
    applied = 0
    rejected = []
    for op in patch_json:
        applied_one, rejected_one = _apply_one_patch_op(op, block_map)
        applied += applied_one
        if rejected_one:
            rejected.append(rejected_one)
    return applied, rejected


def _apply_one_patch_op(op: dict, block_map: dict[str, dict]) -> tuple[int, dict | None]:
    parsed = _parse_patch_path(op)
    if not parsed.get("ok"):
        return 0, _rejected_op(op, parsed["reason"])
    block = block_map.get(parsed["block_id"])
    if block is None:
        return 0, _rejected_op(op, f"block {parsed['block_id']} not found")
    field = parsed["field"]
    if field not in ALLOWED_FIELDS:
        return 0, _rejected_op(op, f"field {field} not allowed (only {ALLOWED_FIELDS})")
    op_type = str(op.get("op") or "")
    invalid_reason = _validate_patch_value(field, op.get("value"), op_type)
    if invalid_reason:
        return 0, _rejected_op(op, invalid_reason)
    discard_reason = _discard_rejection_reason(block, field, op.get("value"))
    if discard_reason:
        return 0, _rejected_op(op, discard_reason)
    return _apply_valid_patch_op(op, block, field)


def _parse_patch_path(op: dict) -> dict:
    parts = str(op.get("path", "")).strip("/").split("/")
    if len(parts) != 3 or parts[0] != "blocks":
        return {"ok": False, "reason": "invalid path format"}
    return {"ok": True, "block_id": parts[1], "field": parts[2]}


def _discard_rejection_reason(block: dict, field: str, value: object) -> str:
    if field != "status" or value != "discard":
        return ""
    detail_categories = _detail_categories(block)
    if detail_categories and not _is_known_pollution_without_detail(block, detail_categories):
        return f"cannot discard detail-bearing block: {sorted(detail_categories)}"
    if block.get("type") in PROTECTED_TYPES:
        return f"cannot discard protected block of type {block['type']}"
    if block.get("protected"):
        return "cannot discard protected block"
    if block.get("type") in KEEP_TYPES:
        return f"cannot discard block of type {block['type']}"
    return ""


def _apply_valid_patch_op(op: dict, block: dict, field: str) -> tuple[int, dict | None]:
    op_type = op.get("op")
    value = op.get("value")
    if op_type == "replace":
        block[field] = value
        return 1, None
    if op_type == "add" and field == "risk_tags" and isinstance(block.get("risk_tags"), list):
        block["risk_tags"].append(value)
        return 1, None
    if op_type == "add":
        return 0, _rejected_op(op, f"add not supported for field {field}")
    return 0, _rejected_op(op, f"op {op_type} not supported")


def _rejected_op(op: dict, reason: str) -> dict:
    return {"op": json.dumps(op), "reason": reason}


def _write_blocks(blocks_path: Path, blocks: list[dict]) -> None:
    with blocks_path.open("w", encoding="utf-8") as fh:
        for block in blocks:
            fh.write(json.dumps(block, ensure_ascii=False) + "\n")


def _read_previous_quality(quality_path: Path) -> dict:
    if not quality_path.exists():
        return {}
    try:
        return json.loads(quality_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _profile_for_patch_run(run_p: Path) -> str:
    profile = _profile_from_run_metadata(run_p)
    if profile == "standard" and (run_p / "obsidian").exists():
        return "obsidian_kb"
    return profile


def _rerender_after_patch(
    blocks: list[dict],
    run_p: Path,
    source_hash: str,
    run_id: str,
    profile: str,
    previous_quality: dict,
) -> None:
    from . import render_outputs as render_mod
    render_mod.render(
        blocks=blocks,
        run_dir=str(run_p),
        source_hash=source_hash,
        run_id=run_id,
        profile=profile,
        source_title=_source_title_from_previous_quality(previous_quality, run_p),
    )


def _resplit_after_patch(
    blocks: list[dict],
    run_p: Path,
    source_type: str,
    source_hash: str,
    run_id: str,
    diagnosis: dict,
) -> None:
    from . import split as split_mod
    split_mod.split_into_chunks(
        blocks=blocks,
        run_dir=str(run_p),
        source_type=source_type,
        source_hash=source_hash,
        run_id=run_id,
        split_strategy=diagnosis.get("split_strategy"),
    )


def _rerun_quality_after_patch(
    blocks: list[dict],
    run_p: Path,
    source_type: str,
    diagnosis: dict,
    profile: str,
    previous_quality: dict,
    review_applied_at: float,
) -> dict:
    from . import quality as qa_mod
    previous_iteration, max_quality_iterations = _quality_iteration_fields(previous_quality)
    quality_report = qa_mod.run_quality_check(
        blocks=blocks,
        run_dir=str(run_p),
        source_type=source_type,
        diagnosis=diagnosis,
        profile=profile,
        review_applied_at=review_applied_at,
        quality_iteration=previous_iteration + 1,
        previous_quality_iteration=previous_iteration,
        max_quality_iterations=max_quality_iterations,
    )
    return _write_updated_quality_report(run_p / "quality_report.json", quality_report, previous_quality, source_type)


def _quality_iteration_fields(previous_quality: dict) -> tuple[int, int]:
    raw_loop = previous_quality.get("quality_loop")
    previous_quality_loop = raw_loop if isinstance(raw_loop, dict) else {}
    previous_iteration = _positive_int(previous_quality_loop.get("current_iteration", 1), 1)
    max_quality_iterations = _positive_int(previous_quality_loop.get("max_iterations"), 3)
    return previous_iteration, max_quality_iterations


def _write_updated_quality_report(
    quality_path: Path,
    quality_report: dict,
    previous_quality: dict,
    source_type: str,
) -> dict:
    quality_report["source_type"] = source_type
    for key in ("source_sha256", "config_hash", "plugin_version", "mineru_version", "runtime_cache_key", "runtime"):
        if key in previous_quality:
            quality_report[key] = previous_quality[key]
    atomic_write_json(quality_path, quality_report, indent=2, trailing_newline=False)
    return quality_report


def _validate_patch_value(field: str, value: object, op_type: str) -> str | None:
    if field == "status":
        if value not in ALLOWED_STATUSES:
            return f"invalid status {value!r}; allowed: {sorted(ALLOWED_STATUSES)}"
    elif field == "risk_tags":
        if op_type == "replace":
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                return "risk_tags must be a list of strings"
        elif op_type == "add":
            if not isinstance(value, str):
                return "risk_tags add value must be a string"
    elif field == "reason":
        if not isinstance(value, str):
            return "reason must be a string"
    elif field == "confidence":
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 or value > 1:
            return "confidence must be a number between 0 and 1"
    return None


def _find_output_root(run_p: Path) -> Path | None:
    if run_p.parent.name == "runs":
        return run_p.parent.parent
    return None


def _read_diagnosis(run_p: Path) -> dict:
    report_path = run_p / "diagnosis_report.json"
    if not report_path.exists():
        return {}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        diagnosis = report.get("diagnosis")
        if isinstance(diagnosis, dict):
            return diagnosis
        return report if isinstance(report, dict) else {}
    except Exception:
        return {}


def _profile_from_run_metadata(run_p: Path) -> str:
    metadata_path = run_p / "run_metadata.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            profile = metadata.get("profile")
            if isinstance(profile, str) and profile.strip():
                return profile
            payload = metadata.get("prepare_payload")
            if isinstance(payload, dict):
                payload_profile = payload.get("profile")
                if isinstance(payload_profile, str) and payload_profile.strip():
                    return payload_profile
        except Exception:
            pass
    return "standard"


def _source_title_from_previous_quality(previous_quality: dict, run_p: Path) -> str:
    source_file = previous_quality.get("input_file")
    if isinstance(source_file, str) and source_file.strip():
        return Path(source_file).stem
    diagnosis_path = run_p / "diagnosis_report.json"
    if diagnosis_path.exists():
        try:
            diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
            input_file = diagnosis.get("input_file")
            if isinstance(input_file, str) and input_file.strip():
                return Path(input_file).stem
        except Exception:
            pass
    return run_p.name


def _run_output_paths(run_p: Path) -> dict:
    has_obsidian = (run_p / "obsidian").exists()
    obsidian_complete = _obsidian_complete_path(run_p / "obsidian")
    return {
        "diagnosis_report": str(run_p / "diagnosis_report.json"),
        "blocks_jsonl": str(run_p / "blocks.jsonl"),
        "cleaned_md": str(run_p / "cleaned.md"),
        "final_artifact_type": "obsidian_dir" if has_obsidian else "markdown",
        "final_md": None,
        "final_assets_dir": None,
        "discarded_md": str(run_p / "discarded.md"),
        "review_needed_md": str(run_p / "review_needed.md"),
        "quality_report": str(run_p / "quality_report.json"),
        "parts_dir": str(run_p / "parts"),
        "images_dir": str(run_p / "images"),
        "obsidian_dir": str(run_p / "obsidian") if has_obsidian else None,
        "obsidian_index": str(run_p / "obsidian" / "00-索引.md") if (run_p / "obsidian" / "00-索引.md").exists() else None,
        "obsidian_complete": str(obsidian_complete) if obsidian_complete else None,
    }


def _publish_latest_outputs(run_p: Path, output_root: Path, profile: str = "standard") -> dict:
    output_root.mkdir(parents=True, exist_ok=True)
    input_path = _input_path_from_latest(output_root)
    if input_path:
        return _shared_publish_latest_outputs(run_p, output_root, input_path, profile)
    _copy_latest_top_level_outputs(run_p, output_root)
    source_side_final = profile not in OBSIDIAN_PROFILES
    final_md, final_assets_dir = _fallback_final_targets(output_root, input_path, source_side_final)
    _publish_source_side_final_if_needed(run_p, input_path, source_side_final)
    _sync_latest_output_dir(run_p / "parts", output_root / "parts", output_root, create_when_missing=True)
    _sync_latest_output_dir(run_p / "images", output_root / "images", output_root, create_when_missing=True)
    _sync_latest_output_dir(run_p / "obsidian", output_root / "obsidian", output_root, create_when_missing=False)
    return _latest_outputs_payload(output_root, final_md, final_assets_dir, source_side_final)


def _copy_latest_top_level_outputs(run_p: Path, output_root: Path) -> None:
    for name in _latest_top_level_output_names():
        src = run_p / name
        dst = output_root / name
        if src.exists():
            shutil.copy2(str(src), str(dst))
        elif name == "review_pack.json" and dst.exists():
            dst.unlink()


def _latest_top_level_output_names() -> list[str]:
    return [
        "converted.md",
        "diagnosis_report.json",
        "blocks.jsonl",
        "cleaned.md",
        "discarded.md",
        "review_needed.md",
        "quality_report.json",
        "conversion_report.json",
        "audit.md",
        "review_pack.json",
    ]


def _fallback_final_targets(
    output_root: Path,
    input_path: Path | None,
    source_side_final: bool,
) -> tuple[Path | None, Path | None]:
    if not source_side_final:
        return None, None
    final_md = _source_final_markdown_path(input_path) if input_path else output_root / "cleaned.md"
    final_assets_dir = _source_final_assets_dir(input_path) if input_path else output_root / "images"
    return final_md, final_assets_dir


def _publish_source_side_final_if_needed(run_p: Path, input_path: Path | None, source_side_final: bool) -> None:
    if input_path and source_side_final:
        _publish_direct_final_to_source(run_p, input_path)


def _sync_latest_output_dir(
    src_dir: Path,
    dst_dir: Path,
    output_root: Path,
    *,
    create_when_missing: bool,
) -> None:
    if dst_dir.exists():
        safe_rmtree(dst_dir, root=output_root)
    if src_dir.exists():
        shutil.copytree(src_dir, dst_dir)
    elif create_when_missing:
        dst_dir.mkdir(parents=True, exist_ok=True)


def _latest_outputs_payload(
    output_root: Path,
    final_md: Path | None,
    final_assets_dir: Path | None,
    source_side_final: bool,
) -> dict:
    dst_obsidian = output_root / "obsidian"
    obsidian_index = dst_obsidian / "00-索引.md"
    obsidian_complete = _obsidian_complete_path(dst_obsidian)
    review_pack = output_root / "review_pack.json"
    return {
        "converted_md": str(output_root / "converted.md"),
        "diagnosis_report": str(output_root / "diagnosis_report.json"),
        "blocks_jsonl": str(output_root / "blocks.jsonl"),
        "cleaned_md": str(output_root / "cleaned.md"),
        "final_artifact_type": "markdown" if source_side_final else "obsidian_dir",
        "final_md": str(final_md) if final_md else None,
        "final_assets_dir": str(final_assets_dir) if final_assets_dir else None,
        "discarded_md": str(output_root / "discarded.md"),
        "review_needed_md": str(output_root / "review_needed.md"),
        "quality_report": str(output_root / "quality_report.json"),
        "conversion_report": str(output_root / "conversion_report.json"),
        "audit_md": str(output_root / "audit.md"),
        "parts_dir": str(output_root / "parts"),
        "images_dir": str(output_root / "images"),
        "obsidian_dir": str(dst_obsidian) if dst_obsidian.exists() else None,
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


def _input_path_from_latest(output_root: Path) -> Path | None:
    latest_path = output_root / "latest.json"
    if not latest_path.exists():
        return None
    try:
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    input_path = payload.get("input_path")
    return Path(input_path) if input_path else None


def _publish_direct_final_to_source(run_p: Path, input_path: Path) -> None:
    cleaned_src = run_p / "cleaned.md"
    if not cleaned_src.exists():
        return

    final_md = _source_final_markdown_path(input_path)
    final_md.parent.mkdir(parents=True, exist_ok=True)
    text = cleaned_src.read_text(encoding="utf-8")

    images_src = run_p / "images"
    if images_src.exists() and any(p.is_file() for p in images_src.rglob("*")):
        assets_dir = _source_final_assets_dir(input_path)
        assets_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(images_src, assets_dir, dirs_exist_ok=True)
        try:
            asset_rel = assets_dir.relative_to(final_md.parent).as_posix()
        except ValueError:
            asset_rel = os.path.relpath(assets_dir, final_md.parent).replace("\\", "/")
        text = _rewrite_markdown_image_refs(text, asset_rel)

    atomic_write_text(final_md, text)


def _source_final_markdown_path(input_path: Path) -> Path:
    stem = _safe_source_stem(input_path)
    if input_path.suffix.lower() in {".md", ".markdown"}:
        return input_path.with_name(f"{stem}.cleaned.md")
    return input_path.with_name(f"{stem}.md")


def _source_final_assets_dir(input_path: Path) -> Path:
    return input_path.with_name(f"{_safe_source_stem(input_path)}.assets")


def _safe_source_stem(input_path: Path) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", input_path.stem).strip(" ._")
    if not stem:
        stem = "cleaned"
    return stem


def _rewrite_markdown_image_refs(text: str, asset_rel: str) -> str:
    return re.sub(
        r"(!\[[^\]]*\]\()images[/\\]([^)]+)(\))",
        lambda m: f"{m.group(1)}{asset_rel}/{m.group(2).replace(chr(92), '/')}{m.group(3)}",
        text,
    )


def _read_latest_or_empty(latest_path: Path) -> dict:
    """Read latest.json, returning ``{}`` if missing or unreadable.

    Preserves the previous tolerant parse semantics: any read/parse failure
    falls back to an empty dict so the publish step still writes a fresh file
    rather than crashing the whole patch operation.
    """
    if not latest_path.exists():
        return {}
    try:
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return latest if isinstance(latest, dict) else {}


def _update_latest_json(
    output_root: Path,
    run_p: Path,
    latest_outputs: dict,
    previous_quality: dict,
    source_type: str,
    review_applied_at: float | int,
) -> None:
    """Atomically rewrite ``output_root/latest.json`` after a review apply.

    Note: caller must serialize per output_root — this is a read-merge-write
    and is not safe under concurrent writers to the same file.
    """
    latest_path = output_root / "latest.json"
    latest = _read_latest_or_empty(latest_path)
    latest.update({
        "run_id": run_p.name,
        "run_dir": str(run_p),
        "source_type": source_type,
        "source_sha256": previous_quality.get("source_sha256", latest.get("source_sha256", "")),
        "latest_outputs": latest_outputs,
        "review_applied_at": review_applied_at,
    })
    atomic_write_json(latest_path, latest, indent=2, trailing_newline=False)
