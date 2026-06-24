"""prepare - single-file pipeline with tracked stage failures."""
import hashlib
import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from .. import __version__
from ..atomic_io import atomic_write_json, atomic_write_text
from ..cleaning_policy_snapshot import write_cleaning_policy_snapshot
from ..envelope import fail, ok, status_from_findings
from ..fs_safety import is_safe_input_path, is_safe_output_root
from ..prepare_artifacts import (
    apply_artifact_policy as _apply_artifact_policy,
)
from ..prepare_artifacts import (
    latest_output_paths as _latest_output_paths,
)
from ..prepare_artifacts import (
    publish_latest_outputs as _publish_latest_outputs,
)
from ..prepare_artifacts import (
    write_publish_report as _write_publish_report,
)
from ..prepare_diagnosis import (
    source_title_for_render as _source_title_for_render,
)
from ..prepare_diagnosis import (
    write_diagnosis_report as _write_diagnosis_report,
)
from ..prepare_errors import write_error_report_from_context as _write_error_report_from_context
from ..prepare_runtime import (
    check_env as _check_env,
)
from ..prepare_runtime import (
    get_mineru_version as _get_mineru_version,
)
from ..prepare_runtime import (
    mineru_timeout_seconds_from_env as _mineru_timeout_seconds_from_env,
)
from ..prepare_runtime import (
    runtime_cache_key as _runtime_cache_key,
)
from ..prepare_runtime import (
    runtime_snapshot as _runtime_snapshot,
)
from .cache_probe import discard_cache_probe_run
from .pipeline_helpers import (  # noqa: F401
    _actual_route_for_converter,
    _conversion_route_decision,
    _converted_text_quality,
    _copy_local_markdown_image_assets,
    _copy_mineru_image_assets,
    _copy_one_local_markdown_image,
    _domain_from_identity_url,
    _find_existing_run,
    _generate_audit_md,
    _identity_scalar,
    _is_nonlocal_markdown_image,
    _looks_like_image_reference,
    _markdown_image_path_part,
    _merge_identity_values,
    _obsidian_complete_path,
    _pdf_text_layer_output_needs_ocr,
    _primary_quality_issue,
    _quality_gate_name_from_error,
    _run_diagnose_direct,
    _run_mineru_conversion,
    _source_identity_for_rules,
    _update_run_metadata,
    _write_blocks,
    _write_conversion_report,
    _write_run_metadata,
)
from .pipeline_state import PipelineError, PipelineState, _stderr_log
from .review_pack import _generate_review_pack

logger = logging.getLogger(__name__)


def run(data: dict) -> None:
    try:
        state = PipelineState(data)
    except PipelineError as e:
        fail(e.code, e.message, details=e.details)
        return
    if not is_safe_output_root(state.root_p):
        fail("E_OUTPUT_ROOT_REJECTED", f"Output root is unsafe (system/home/protected): {state.root_p}")
        return
    if not is_safe_input_path(state.input_p):
        fail("E_INPUT_PATH_REJECTED", f"Input path is unsafe (device or too large): {state.input_path}")
        return
    if not state.input_p.exists():
        fail("E_INPUT_NOT_FOUND", f"Input file does not exist: {state.input_path}")
        return

    try:
        _stage_env_check(state)
        _stage_initialize_run(state)
        _stage_diagnose(state)
        _stage_convert(state)
        _stage_pre_clean_conversion_gate(state)
        _stage_normalize(state)
        _stage_blockify(state)
        _stage_classify_blocks(state)
        _stage_cleaning_policy_snapshot(state)
        if not state.force and _publish_cached_run_if_available(state):
            return
        _stage_apply_cleaning_rules(state)
        _stage_post_cleaning(state)
        _stage_review_pack(state)
        _stage_render_outputs(state)
        _stage_split(state)
        _stage_quality_check(state)
    except PipelineError as e:
        _handle_pipeline_error(state, e)
        return
    except FileNotFoundError as e:
        _handle_missing_mineru(state, e)
        return
    except TimeoutError as e:
        _handle_timeout(state, e)
        return
    except Exception as e:
        _handle_unexpected_error(state, e)
        return

    _stage_audit(state)
    _stage_publish_or_block(state)


def _stage_env_check(state: PipelineState) -> None:
    _stderr_log("info", "env_check", "Checking environment")
    state.warnings.extend(_check_env(state.profile))


def _stage_initialize_run(state: PipelineState) -> None:
    _stderr_log("info", "original_preserve", "Computing file hash")
    _capture_input_fingerprint(state)
    _capture_runtime_snapshot(state)
    _detect_source_and_identity(state)
    _compute_run_identity(state)
    _assign_run_paths(state)

    _create_run_workspace(state)
    _write_initial_run_metadata(state)
    _preserve_original_input(state)


def _capture_input_fingerprint(state: PipelineState) -> None:
    file_bytes = state.input_p.read_bytes()
    state.file_hash = hashlib.sha256(file_bytes).hexdigest()
    state.file_size = len(file_bytes)


def _capture_runtime_snapshot(state: PipelineState) -> None:
    state.plugin_version = __version__
    state.mineru_version = _get_mineru_version()
    state.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    state.runtime = _runtime_snapshot(state.mineru_version)
    state.runtime_cache_key = _runtime_cache_key(state.runtime)


def _detect_source_and_identity(state: PipelineState) -> None:
    from ..detect import detect_source_type
    state.source_type = state.override_source_type if state.override_source_type != "auto" else detect_source_type(state.input_path)
    state.source_identity = _source_identity_for_rules(state.input_p, state.data)


def _compute_run_identity(state: PipelineState) -> None:
    config_str = json.dumps({
        "source_type": state.source_type,
        "language": state.language,
        "mode": state.mode,
        "splitter": state.override_splitter,
        "profile": state.profile,
        "artifact_policy": state.artifact_policy,
        "source_identity": state.source_identity,
    }, sort_keys=True)
    state.config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]
    run_hash_input = f"{state.file_hash}:{state.config_hash}:{state.plugin_version}:{state.runtime_cache_key}"
    run_hash = hashlib.sha256(run_hash_input.encode()).hexdigest()
    unique_suffix = time.time_ns()
    state.run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{run_hash[:12]}_{unique_suffix:x}"


def _assign_run_paths(state: PipelineState) -> None:
    original_dir = state.root_p / "original"
    runs_dir = state.root_p / "runs"
    run_dir = runs_dir / state.run_id
    latest_file = state.root_p / "latest.json"
    state.original_dir = original_dir
    state.runs_dir = runs_dir
    state.run_dir = run_dir
    state.latest_file = latest_file


def _publish_cached_run_if_available(state: PipelineState) -> bool:
    if not state.cleaning_policy_snapshot_hash:
        return False
    existing = _find_existing_run(
        state.root_p,
        state.file_hash,
        state.config_hash,
        state.plugin_version,
        state.runtime_cache_key,
        policy_snapshot_hash=state.cleaning_policy_snapshot_hash,
        required_artifacts=(
            "cleaning_patches.jsonl",
            "cleaning_patch_gate.json",
            "rejected_patches.jsonl",
            "clean_view.json",
            "document_cleaning_gate.json",
        ),
    )
    if not existing:
        return False
    _stderr_log("info", "original_preserve", f"Skipping: matching run {existing['run_id']}")
    existing_run_dir = Path(existing["run_dir"])
    discard_cache_probe_run(state.run_dir, state.runs_dir, existing_run_dir)
    latest_outputs = _publish_latest_outputs(existing_run_dir, state.root_p, state.input_p, state.profile)
    ok(data={
        "run_id": existing["run_id"],
        "run_dir": existing["run_dir"],
        "latest_outputs": latest_outputs,
        "skipped": True,
        "warnings": ["Already processed with same config. Use force=true to re-process."],
        "strict_errors": [],
    })
    return True


def _create_run_workspace(state: PipelineState) -> None:
    original_dir = state.require_path("original_preserve", "original_dir")
    run_dir = state.require_path("original_preserve", "run_dir")
    original_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "evidence").mkdir(exist_ok=True)
    (run_dir / "chunks").mkdir(exist_ok=True)
    (run_dir / "logs").mkdir(exist_ok=True)


def _write_initial_run_metadata(state: PipelineState) -> None:
    run_dir = state.require_path("original_preserve", "run_dir")
    _write_run_metadata(
        run_dir=run_dir,
        run_id=state.run_id,
        input_path=state.input_p,
        output_root=state.root_p,
        source_type=state.source_type,
        language=state.language,
        mode=state.mode,
        splitter=state.override_splitter,
        profile=state.profile,
        artifact_policy=state.artifact_policy,
        force=state.force,
        file_hash=state.file_hash,
        file_size=state.file_size,
        config_hash=state.config_hash,
        plugin_version=state.plugin_version,
        mineru_version=state.mineru_version,
        runtime_cache_key=state.runtime_cache_key,
        runtime=state.runtime,
    )
    _update_run_metadata(run_dir, {"source_identity": state.source_identity})


def _preserve_original_input(state: PipelineState) -> None:
    original_dir = state.require_path("original_preserve", "original_dir")
    state.original_file = original_dir / f"{state.file_hash[:16]}{state.input_p.suffix}"
    if not state.original_file.exists():
        shutil.copy2(str(state.input_p), str(state.original_file))
        _stderr_log("info", "original_preserve", f"Original saved: {state.original_file.name}")


def _stage_diagnose(state: PipelineState) -> None:
    state.require_stage_fields("diagnose", "run_dir")
    run_dir = state.require_path("diagnose", "run_dir")
    _stderr_log("info", "diagnose", "Diagnosing file quality")
    try:
        diag_envelope = _run_diagnose_direct(state.input_path, state.output_root, state.override_source_type)
        if diag_envelope.get("ok"):
            state.diagnosis = diag_envelope.get("data", {})
            state.warnings.extend(state.diagnosis.get("warnings", []))
        else:
            state.warnings.append(f"Diagnosis failed: {diag_envelope.get('error', {}).get('message', 'unknown')}")
    except Exception as e:
        state.warnings.append(f"Diagnosis error: {e}")
        _stderr_log("warn", "diagnose", str(e))

    _write_diagnosis_report(
        run_dir=run_dir,
        input_path=state.input_p,
        file_hash=state.file_hash,
        source_type=state.source_type,
        diagnosis=state.diagnosis,
        runtime=state.runtime,
        warnings=state.warnings,
    )


def _stage_convert(state: PipelineState) -> None:
    from .pipeline_conversion import run_conversion_stage

    run_conversion_stage(state)


def _stage_pre_clean_conversion_gate(state: PipelineState) -> None:
    state.require_stage_fields("pre_clean_conversion_gate", "run_dir", "converted_path")
    run_dir = state.require_path("pre_clean_conversion_gate", "run_dir")
    _stderr_log("info", "pre_clean_conversion_gate", "Checking converted Markdown before cleanup")
    from ..quality.conversion_gate import run_pre_clean_conversion_gate

    report = run_pre_clean_conversion_gate(run_dir, state.diagnosis)
    strict_errors = report.get("strict_errors", [])
    if not strict_errors:
        return
    first_issue = report.get("quality_issues", [{}])[0]
    code = str(first_issue.get("code") or str(strict_errors[0]).split(":", 1)[0])
    raise PipelineError(
        code,
        "Pre-clean conversion quality gate failed; cleanup, splitting, rendering, and publishing were not started.",
        {
            "legacy_code": "E_QA_FAILED",
            "gate": "pre_clean_conversion",
            "run_id": state.run_id,
            "run_dir": str(run_dir),
            "conversion_quality_report": str(run_dir / "conversion_quality_report.json"),
            "conversion_report": str(run_dir / "conversion_report.json"),
            "converted_md": str(run_dir / "converted.md"),
            "strict_errors": strict_errors,
            "quality_issues": report.get("quality_issues", []),
        },
    )


def _stage_normalize(state: PipelineState) -> None:
    state.require_stage_fields("normalize", "run_dir", "converted_path")
    run_dir = state.require_path("normalize", "run_dir")
    converted_path = state.require_path("normalize", "converted_path")
    _stderr_log("info", "normalize", "Normalizing markdown")
    normalized_path = run_dir / "normalized.md"
    state.normalized_path = normalized_path
    from .. import normalize as norm_mod
    norm_result = norm_mod.normalize(
        converted_text=converted_path.read_text(encoding="utf-8"),
        run_dir=str(run_dir),
        mineru_artifacts=state.mineru_artifacts,
    )
    atomic_write_text(normalized_path, norm_result["normalized_text"])
    state.warnings.extend(norm_result.get("warnings", []))
    _stderr_log("info", "normalize", f"Normalized: {norm_result.get('fix_count', 0)} fixes applied")
    if not normalized_path.exists():
        raise PipelineError("E_NORMALIZE_FAILED", "normalized.md not found after normalization")


def _stage_blockify(state: PipelineState) -> None:
    state.require_stage_fields("blockify", "run_dir", "normalized_path")
    run_dir = state.require_path("blockify", "run_dir")
    normalized_path = state.require_path("blockify", "normalized_path")
    _stderr_log("info", "blockify", "Building blocks")
    blocks_path = run_dir / "blocks.jsonl"
    state.blocks_path = blocks_path
    from .. import blockify as block_mod
    normalized_text = normalized_path.read_text(encoding="utf-8")
    state.blocks = block_mod.blockify(
        text=normalized_text,
        source_hash=state.file_hash,
        mineru_artifacts=state.mineru_artifacts,
        run_dir=str(run_dir),
    )
    from ..document_type import build_document_classification_artifact as _build_document_classification_artifact
    from ..document_type import classify_document_type as _classify_document_type
    state.document_type_detection = _classify_document_type(
        text=normalized_text,
        source_type=state.source_type,
        diagnosis={**state.diagnosis, "detected_format": state.diagnosis.get("detected_format")},
    )
    document_classification = _build_document_classification_artifact(
        text=normalized_text,
        source_type=state.source_type,
        diagnosis={**state.diagnosis, "detected_format": state.diagnosis.get("detected_format")},
        classification=state.document_type_detection,
    )
    document_classification_path = run_dir / "document_classification.json"
    atomic_write_json(
        document_classification_path,
        document_classification,
        indent=2,
        trailing_newline=False,
    )
    state.document_type = state.document_type_detection.get("document_type", "unknown")
    _update_run_metadata(run_dir, {
        "document_type": state.document_type,
        "document_type_detection": state.document_type_detection,
        "document_classification": str(document_classification_path),
    })
    _stderr_log("info", "document_type", f"Document type: {state.document_type} ({state.document_type_detection.get('confidence', 0)})")
    _write_blocks(blocks_path, state.blocks)
    _stderr_log("info", "blockify", f"Created {len(state.blocks)} blocks")


def _stage_classify_blocks(state: PipelineState) -> None:
    state.require_stage_fields("classify_blocks", "blocks_path")
    blocks_path = state.require_path("classify_blocks", "blocks_path")
    _stderr_log("info", "classify_blocks", "Classifying blocks")
    from .. import classify_blocks as cls_mod
    state.blocks = cls_mod.classify_blocks(state.blocks, profile=state.profile, document_type=state.document_type)
    _write_blocks(blocks_path, state.blocks)
    _stderr_log("info", "classify_blocks", "Classification complete")


def _stage_cleaning_policy_snapshot(state: PipelineState) -> None:
    state.require_stage_fields("cleaning_policy_snapshot", "run_dir")
    run_dir = state.require_path("cleaning_policy_snapshot", "run_dir")
    source_quality = str(state.diagnosis.get("text_layer_health") or "")
    result = write_cleaning_policy_snapshot(
        run_dir,
        profile=state.profile,
        document_type=state.document_type,
        source_identity=state.source_identity,
        source_quality=source_quality,
    )
    if result.path is None:
        raise PipelineError("E_INTERNAL", "cleaning policy snapshot path was not written")
    state.cleaning_policy_snapshot_hash = result.snapshot_hash
    state.cleaning_policy_snapshot = result.snapshot
    state.cleaning_policy_snapshot_path = result.path
    _update_run_metadata(run_dir, {
        "cleaning_policy_snapshot_hash": result.snapshot_hash,
        "cleaning_policy_snapshot": {
            "path": str(result.path),
            "snapshot_hash": result.snapshot_hash,
        },
    })
    _stderr_log("info", "cleaning_policy_snapshot", f"Policy snapshot: {result.snapshot_hash[:12]}")


def _stage_apply_cleaning_rules(state: PipelineState) -> None:
    state.require_stage_fields("clean_rules", "blocks_path", "run_dir")
    blocks_path = state.require_path("clean_rules", "blocks_path")
    run_dir = state.require_path("clean_rules", "run_dir")
    _stderr_log("info", "clean_rules", "Applying cleaning rules")
    from .cleaning_stage import apply_cleaning_rules_stage
    state.blocks = apply_cleaning_rules_stage(
        blocks=state.blocks,
        run_dir=run_dir,
        policy_snapshot_hash=state.cleaning_policy_snapshot_hash,
        compiled_policy=state.cleaning_policy_snapshot.get("compiled_policy", {}),
        profile=state.profile,
        document_type=state.document_type,
        source_identity=json.dumps(state.source_identity, ensure_ascii=False, sort_keys=True),
    )
    _write_blocks(blocks_path, state.blocks)
    _stderr_log("info", "clean_rules", "Cleaning rules applied")


def _stage_post_cleaning(state: PipelineState) -> None:
    from .post_cleaning_stage import run_post_cleaning_stages

    run_post_cleaning_stages(state)


def _stage_review_pack(state: PipelineState) -> None:
    state.require_stage_fields("review_pack", "run_dir")
    run_dir = state.require_path("review_pack", "run_dir")
    if state.mode == "rules_plus_review_pack":
        _stderr_log("info", "review_pack", "Generating review pack")
        _generate_review_pack(
            state.blocks,
            run_dir,
            state.source_type,
            source_quality=str(state.diagnosis.get("text_layer_health") or ""),
            document_type=state.document_type,
            profile=state.profile,
            source_identity=json.dumps(state.source_identity, ensure_ascii=False, sort_keys=True),
        )


def _stage_render_outputs(state: PipelineState) -> None:
    state.require_stage_fields("render_outputs", "run_dir", "converted_path")
    run_dir = state.require_path("render_outputs", "run_dir")
    converted_path = state.require_path("render_outputs", "converted_path")
    _stderr_log("info", "render_outputs", "Rendering output files")
    from .. import render_outputs as render_mod
    render_mod.render(
        blocks=state.blocks,
        run_dir=str(run_dir),
        source_hash=state.file_hash,
        run_id=state.run_id,
        profile=state.profile,
        source_title=_source_title_for_render(state.input_p, converted_path),
        render_obsidian=False,
        clean_view=_read_clean_view(run_dir),
    )
    _stderr_log("info", "render_outputs", "Output files rendered")


def _stage_split(state: PipelineState) -> None:
    state.require_stage_fields("split", "run_dir")
    run_dir = state.require_path("split", "run_dir")
    _stderr_log("info", "split", "Splitting into chunks")
    from .. import split as split_mod
    splitter_type = state.override_splitter if state.override_splitter != "auto" else state.source_type
    split_result = split_mod.split_into_chunks(
        blocks=state.blocks,
        run_dir=str(run_dir),
        source_type=splitter_type,
        source_hash=state.file_hash,
        run_id=state.run_id,
        split_strategy=state.diagnosis.get("split_strategy"),
    )
    state.warnings.extend(split_result.get("warnings", []))
    _stderr_log("info", "split", f"Created {split_result.get('chunk_count', 0)} chunks")


def _stage_quality_check(state: PipelineState) -> None:
    state.require_stage_fields("quality_check", "run_dir")
    run_dir = state.require_path("quality_check", "run_dir")
    _stderr_log("info", "quality_check", "Running quality checks")
    from .. import quality as qa_mod
    state.quality_report = qa_mod.run_quality_check(
        blocks=state.blocks,
        run_dir=str(run_dir),
        source_type=state.source_type,
        diagnosis=state.diagnosis,
        profile=state.profile,
        document_type=state.document_type,
        quality_iteration=1,
        max_quality_iterations=state.max_quality_iterations,
    )
    state.strict_errors.extend(state.quality_report.get("strict_errors", []))
    state.warnings.extend(state.quality_report.get("warnings", []))
    state.quality_report.update({
        "source_sha256": state.file_hash,
        "config_hash": state.config_hash,
        "plugin_version": state.plugin_version,
        "mineru_version": state.mineru_version,
        "runtime_cache_key": state.runtime_cache_key,
        "runtime": state.runtime,
        "document_type_detection": state.document_type_detection,
        "cleaning_policy_snapshot_hash": state.cleaning_policy_snapshot_hash,
        "cleaning_policy_snapshot": {
            "path": str(state.cleaning_policy_snapshot_path) if state.cleaning_policy_snapshot_path else "",
            "snapshot_hash": state.cleaning_policy_snapshot_hash,
        },
    })
    atomic_write_json(
        run_dir / "quality_report.json",
        state.quality_report,
        indent=2,
        trailing_newline=False,
    )
    _stderr_log("info", "quality_check", f"Quality: {len(state.strict_errors)} strict errors, {len(state.warnings)} warnings")


def _stage_audit(state: PipelineState) -> None:
    state.require_stage_fields("audit", "run_dir")
    run_dir = state.require_path("audit", "run_dir")
    try:
        audit_md = _generate_audit_md(
            input_name=state.input_p.name,
            file_hash=state.file_hash,
            plugin_version=state.plugin_version,
            mineru_version=state.mineru_version,
            python_version=state.python_version,
            runtime=state.runtime,
            diagnosis=state.diagnosis,
            blocks=state.blocks,
            quality_report=state.quality_report,
            warnings=state.warnings,
            strict_errors=state.strict_errors,
        )
        atomic_write_text(run_dir / "audit.md", audit_md)
    except Exception as e:
        _stderr_log("warn", "audit", f"Failed to generate audit.md: {e}")


def _stage_publish_or_block(state: PipelineState) -> None:
    state.require_stage_fields("publish_or_block", "run_dir", "converted_path", "latest_file")
    run_dir = state.require_path("publish_or_block", "run_dir")
    converted_path = state.require_path("publish_or_block", "converted_path")
    latest_file = state.require_path("publish_or_block", "latest_file")
    state.latest_outputs = _latest_output_paths(state.root_p, state.input_p, state.profile)
    if not state.strict_errors:
        _publish_successful_run(state, run_dir, converted_path, latest_file)
    else:
        _write_publish_report(
            run_dir=run_dir,
            root_p=state.root_p,
            input_p=state.input_p,
            profile=state.profile,
            latest_outputs=state.latest_outputs,
            strict_errors=state.strict_errors,
        )
        _stderr_log("warn", "quality_check", "Strict errors: latest.json NOT updated")

    run_outputs = _run_outputs(state)
    if state.strict_errors:
        _fail_quality_gate(state, run_outputs)
        return

    _emit_success(state, run_dir, run_outputs)


def _publish_successful_run(
    state: PipelineState,
    run_dir: Path,
    converted_path: Path,
    latest_file: Path,
) -> None:
    if state.profile in {"obsidian_kb", "curated_obsidian_kb"}:
        _render_obsidian_after_quality_pass(state, run_dir, converted_path)
    state.latest_outputs = _publish_latest_outputs(run_dir, state.root_p, state.input_p, state.profile)
    publish_report = _write_publish_report(
        run_dir=run_dir,
        root_p=state.root_p,
        input_p=state.input_p,
        profile=state.profile,
        latest_outputs=state.latest_outputs,
        strict_errors=[],
    )
    shutil.copy2(str(publish_report), str(state.root_p / "publish_report.json"))
    state.latest_outputs = _latest_output_paths(state.root_p, state.input_p, state.profile)
    _apply_artifact_policy(state.root_p, run_dir, state.artifact_policy)
    _write_latest_file(state, run_dir, latest_file)


def _render_obsidian_after_quality_pass(state: PipelineState, run_dir: Path, converted_path: Path) -> None:
    _stderr_log("info", "obsidian_export", "Rendering Obsidian output after quality gates passed")
    from .. import obsidian_kb as obsidian_mod
    obsidian_mod.render_obsidian_vault(
        blocks=state.blocks,
        run_dir=str(run_dir),
        source_title=_source_title_for_render(state.input_p, converted_path),
        source_hash=state.file_hash,
        run_id=state.run_id,
        profile=state.profile,
        template_name=obsidian_mod.template_for_profile(state.profile),
    )


def _write_latest_file(state: PipelineState, run_dir: Path, latest_file: Path) -> None:
    payload = {
        "source_sha256": state.file_hash,
        "run_id": state.run_id,
        "source_type": state.source_type,
        "input_path": str(state.input_p),
        "run_dir": str(run_dir),
        "latest_outputs": state.latest_outputs,
        "timestamp": time.time(),
        "plugin_version": state.plugin_version,
        "mineru_version": state.mineru_version,
        "runtime_cache_key": state.runtime_cache_key,
        "runtime": state.runtime,
    }
    atomic_write_json(latest_file, payload, indent=2, trailing_newline=False)


def _fail_quality_gate(state: PipelineState, run_outputs: dict[str, Any]) -> None:
    primary_issue = _primary_quality_issue(state.quality_report)
    fail(
        primary_issue.get("code", "E_QA_FAILED"),
        "Quality gate failed; latest outputs were not published.",
        details={
            "legacy_code": "E_QA_FAILED",
            "primary_quality_issue": primary_issue,
            "run_id": state.run_id,
            "run_dir": str(state.run_dir),
            "outputs": run_outputs,
            "quality_issues": state.quality_report.get("quality_issues", []),
            "strict_errors": state.strict_errors,
            "quality_gates": state.quality_report.get("quality_gates", []),
            "next_actions": state.quality_report.get("next_actions", []),
            "quality_tasks": state.quality_report.get("quality_tasks", {}),
            "latest_outputs": state.latest_outputs,
        },
        warnings=state.warnings,
        recoverable=True,
        suggested_action="Inspect quality_report.json, discarded.md, and review_needed.md in run_dir, then adjust the input or rules and rerun.",  # noqa: E501
    )


def _emit_success(state: PipelineState, run_dir: Path, run_outputs: dict[str, Any]) -> None:
    chunks_dir = run_dir / "chunks"
    status = status_from_findings(state.strict_errors, state.warnings)
    ok(data={
        "run_id": state.run_id,
        "run_dir": str(run_dir),
        "latest_outputs": state.latest_outputs,
        "outputs": run_outputs,
        "chunk_count": len(list(chunks_dir.glob("*.md"))) if chunks_dir.exists() else 0,
        "warnings": state.warnings,
        "strict_errors": state.strict_errors,
        "status": status,
    }, warnings=state.warnings, status=status)


def _run_outputs(state: PipelineState) -> dict[str, Any]:
    state.require_stage_fields("run_outputs", "run_dir")
    run_dir = state.require_path("run_outputs", "run_dir")
    chunks_dir = run_dir / "chunks"
    obsidian_complete = _obsidian_complete_path(run_dir / "obsidian")
    policy_snapshot_path = run_dir / "cleaning_policy_snapshot.json"
    return {
        "converted_md": str(run_dir / "converted.md"),
        "normalized_md": str(run_dir / "normalized.md"),
        "diagnosis_report": str(run_dir / "diagnosis_report.json"),
        "blocks_jsonl": str(run_dir / "blocks.jsonl"),
        "cleaning_patches": str(run_dir / "cleaning_patches.jsonl"),
        "cleaning_patch_gate": str(run_dir / "cleaning_patch_gate.json"),
        "rejected_patches": str(run_dir / "rejected_patches.jsonl"),
        "clean_view": str(run_dir / "clean_view.json"),
        "document_cleaning_gate": str(run_dir / "document_cleaning_gate.json"),
        "cleaned_md": str(run_dir / "cleaned.md"),
        "discarded_md": str(run_dir / "discarded.md"),
        "review_needed_md": str(run_dir / "review_needed.md"),
        "audit_md": str(run_dir / "audit.md"),
        "quality_report": str(run_dir / "quality_report.json"),
        "cleaning_policy_snapshot": str(policy_snapshot_path) if policy_snapshot_path.exists() else None,
        "publish_report": str(run_dir / "publish_report.json") if (run_dir / "publish_report.json").exists() else None,
        "conversion_quality_report": str(run_dir / "conversion_quality_report.json"),
        "document_classification": str(run_dir / "document_classification.json"),
        "chunks_dir": str(chunks_dir),
        "parts_dir": str(run_dir / "parts"),
        "images_dir": str(run_dir / "images"),
        "obsidian_dir": str(run_dir / "obsidian") if (run_dir / "obsidian").exists() else None,
        "obsidian_index": str(run_dir / "obsidian" / "00-索引.md") if (run_dir / "obsidian" / "00-索引.md").exists() else None,
        "obsidian_complete": str(obsidian_complete) if obsidian_complete else None,
        "review_pack": str(run_dir / "review_pack.json") if (run_dir / "review_pack.json").exists() else None,
    }


def _read_clean_view(run_dir: Path) -> dict[str, Any]:
    from .post_cleaning_stage import read_clean_view_artifact

    return read_clean_view_artifact(run_dir)


def _handle_pipeline_error(state: PipelineState, error: PipelineError) -> None:
    _stderr_log("error", "pipeline", error.message, error.code)
    details = dict(error.details)
    details.update(_write_error_report_from_context(state.error_context(), error.code, error.message, state.warnings))
    fail(error.code, error.message, details=details, warnings=state.warnings)


def _handle_missing_mineru(state: PipelineState, error: FileNotFoundError) -> None:
    _stderr_log("error", "pipeline", str(error), "E_MINERU_NOT_FOUND")
    details = _write_error_report_from_context(state.error_context(), "E_MINERU_NOT_FOUND", str(error), state.warnings)
    fail(
        "E_MINERU_NOT_FOUND",
        f"MinerU not found: {error}",
        details=details,
        warnings=state.warnings,
        recoverable=False,
        suggested_action="Rebuild the KBPrep-local .kbprep/venv so MinerU is installed there.",
    )


def _handle_timeout(state: PipelineState, error: TimeoutError) -> None:
    _stderr_log("error", "pipeline", str(error), "E_TIMEOUT")
    details = _write_error_report_from_context(state.error_context(), "E_TIMEOUT", str(error), state.warnings)
    details["mineru_timeout_seconds"] = _mineru_timeout_seconds_from_env()
    fail(
        "E_TIMEOUT",
        str(error),
        details=details,
        warnings=state.warnings,
        recoverable=True,
        suggested_action="Increase config mineru_timeout_seconds, try a smaller sample first, or verify MinerU/GPU readiness with kbprep_preflight.",  # noqa: E501
    )


def _handle_unexpected_error(state: PipelineState, error: Exception) -> None:
    error_code = "E_CONVERT_FAILED" if type(error).__name__ == "MinerUProcessError" else "E_INTERNAL"
    _stderr_log("error", "pipeline", str(error), error_code)
    import traceback
    tb = traceback.format_exc()
    _stderr_log("error", "pipeline", tb)
    details = {"exception_type": type(error).__name__}
    details.update(_write_error_report_from_context(
        state.error_context(), error_code, str(error), state.warnings, traceback_text=tb,
    ))
    extra_details = getattr(error, "details", None)
    if isinstance(extra_details, dict):
        details.update(extra_details)
    fail(error_code, str(error), details=details, warnings=state.warnings)
