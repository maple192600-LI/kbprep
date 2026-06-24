"""Helper functions for pipeline conversion, reporting, metadata, and audit output."""
from __future__ import annotations

import json
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from ..atomic_io import atomic_write_json
from ..audit import AuditContext
from ..audit import generate_audit_md as _generate_audit_from_context
from ..cleaning_patches import validate_cleaning_patches_artifact
from ..converter_capabilities import get_capability_for_extension
from ..converter_registry import ConversionRoute
from ..converters.direct import read_direct_source as _read_direct_source_impl
from ..converters.html import html_to_markdown as _html_to_markdown
from ..quality.thresholds import DIAGNOSIS_THRESHOLDS
from ..supported_formats import IMAGE_EXTENSIONS
from .pipeline_state import PipelineError

EXISTING_RUN_SCAN_LIMIT = 20
PDF_FALLBACK_CONVERTERS = {
    "mineru_after_pdf_text_layer_fallback",
    "mineru_after_pymupdf4llm_fallback",
}


def _write_blocks(blocks_path: Path, blocks: list[dict[str, Any]]) -> None:
    with open(blocks_path, "w", encoding="utf-8") as f:
        for block in blocks:
            f.write(json.dumps(block, ensure_ascii=False) + "\n")

def _validate_convertible_container(input_p: Path) -> None:
    """Fail fast for modern Office-like containers before invoking heavy converters."""
    zip_container_exts = {".docx", ".pptx", ".xlsx", ".epub", ".odt", ".odp", ".ods"}
    if input_p.suffix.lower() in zip_container_exts and not zipfile.is_zipfile(input_p):
        raise PipelineError(
            "E_CONVERT_INPUT_INVALID",
            f"{input_p.name} is not a valid Office ZIP container. Check whether the file is corrupted or mislabeled.",
            {"extension": input_p.suffix.lower()},
        )


def _read_direct_source(path: Path, run_dir: Path | None = None, force_html: bool = False) -> str:
    if force_html and path.suffix.lower() not in {".html", ".htm"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        return _html_to_markdown(text, run_dir, path.stem or "html", path.parent)
    return _read_direct_source_impl(path, run_dir=run_dir, html_converter=_html_to_markdown)


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


def _run_mineru_conversion(
    input_p: Path,
    converted_path: Path,
    run_dir: Path,
    language: str,
    mode: str,
) -> dict:
    _validate_convertible_container(input_p)
    from .. import mineru_adapter

    result = mineru_adapter.run_mineru(
        input_path=str(input_p),
        output_dir=str(run_dir),
        language=language,
        mode=mode,
        keep_debug_files=False,
    )
    source_md = Path(result["source_md_path"])
    if not source_md.exists():
        raise PipelineError(
            "E_CONVERT_OUTPUT_MISSING",
            f"MinerU did not produce source Markdown: {source_md}",
            {"source_md_path": str(source_md)},
        )
    _copy_mineru_image_assets(source_md, run_dir, result)
    shutil.copy2(str(source_md), str(converted_path))
    return result


def _copy_mineru_image_assets(source_md: Path, run_dir: Path, mineru_result: dict) -> None:
    image_dirs: list[Path] = []
    direct_images = source_md.parent / "images"
    if direct_images.exists():
        image_dirs.append(direct_images)
    assets_dir = mineru_result.get("assets_dir")
    if assets_dir:
        assets_path = Path(str(assets_dir))
        if assets_path.exists():
            image_dirs.extend(path for path in assets_path.rglob("images") if path.is_dir())

    if not image_dirs:
        return
    target_images = run_dir / "images"
    copied: set[Path] = set()
    for source_images in image_dirs:
        for src in source_images.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(source_images)
            dst = target_images / rel
            if dst in copied:
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            copied.add(dst)


def _copy_local_markdown_image_assets(text: str, input_path: Path, run_dir: Path) -> tuple[str, dict]:
    """Copy local Markdown/Obsidian image refs into run_dir/images and rewrite refs."""
    source_root = input_path.parent.resolve()
    target_root = run_dir / "images"
    copied: list[str] = []
    missing: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []

    def rewrite_standard(match: re.Match) -> str:
        alt = match.group(1)
        raw_target = match.group(2)
        rewritten = _copy_one_local_markdown_image(
            raw_target=raw_target,
            source_root=source_root,
            target_root=target_root,
            copied=copied,
            missing=missing,
            skipped=skipped,
        )
        if not rewritten:
            return match.group(0)
        return f"![{alt}]({rewritten})"

    def rewrite_obsidian(match: re.Match) -> str:
        raw_target = match.group(1).split("|", 1)[0].strip()
        if not _looks_like_image_reference(raw_target):
            return match.group(0)
        rewritten = _copy_one_local_markdown_image(
            raw_target=raw_target,
            source_root=source_root,
            target_root=target_root,
            copied=copied,
            missing=missing,
            skipped=skipped,
        )
        if not rewritten:
            return match.group(0)
        return f"![]({rewritten})"

    text = re.sub(r"!\[([^\]]*)\]\(([^)\n]+)\)", rewrite_standard, text)
    text = re.sub(r"!\[\[([^\]\n]+)\]\]", rewrite_obsidian, text)

    return text, _local_markdown_image_report(copied, missing, skipped, warnings)


def _local_markdown_image_report(
    copied: list[str],
    missing: list[str],
    skipped: list[str],
    warnings: list[str],
) -> dict:
    if missing:
        warnings.append(f"W_LOCAL_IMAGE_MISSING: {len(missing)} local Markdown image references were not found")
    if skipped:
        warnings.append(
            "W_LOCAL_IMAGE_SKIPPED: "
            f"{len(skipped)} local Markdown image references were outside the source folder or unsupported"
        )
    return {
        "local_image_assets": {
            "copied_count": len(set(copied)),
            "copied": sorted(set(copied))[:50],
            "missing_count": len(missing),
            "missing": missing[:50],
            "skipped_count": len(skipped),
            "skipped": skipped[:50],
        },
        "warnings": warnings,
    }


def _copy_one_local_markdown_image(
    raw_target: str,
    source_root: Path,
    target_root: Path,
    copied: list[str],
    missing: list[str],
    skipped: list[str],
) -> str | None:
    path_text = _markdown_image_path_part(raw_target)
    if not path_text or _is_nonlocal_markdown_image(path_text):
        return None
    if not _looks_like_image_reference(path_text):
        skipped.append(path_text)
        return None

    decoded = unquote(path_text).replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
    source_path = (source_root / decoded).resolve()
    try:
        rel = source_path.relative_to(source_root)
    except ValueError:
        skipped.append(path_text)
        return None

    if not source_path.is_file():
        missing.append(path_text)
        return None

    safe_parts = [part for part in rel.parts if part not in {"", ".", ".."}]
    if safe_parts and safe_parts[0].lower() == "images":
        safe_parts = safe_parts[1:]
    if not safe_parts:
        skipped.append(path_text)
        return None
    safe_rel = Path(*safe_parts)
    target_path = target_root / safe_rel
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        shutil.copy2(str(source_path), str(target_path))
    rewritten = "images/" + safe_rel.as_posix()
    copied.append(rewritten)
    return rewritten


def _markdown_image_path_part(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1:target.index(">")].strip()
    return re.sub(r"\s+(?:\"[^\"]*\"|'[^']*'|\([^)]+\))\s*$", "", target).strip()


def _is_nonlocal_markdown_image(path_text: str) -> bool:
    return bool(re.match(r"^(?:https?:)?//|^data:|^mailto:|^#", path_text, re.IGNORECASE))


def _looks_like_image_reference(path_text: str) -> bool:
    clean = path_text.split("?", 1)[0].split("#", 1)[0]
    return Path(clean).suffix.lower() in IMAGE_EXTENSIONS


def _converted_text_quality(text: str) -> dict:
    from ..diagnose import analyze_text_quality
    return analyze_text_quality(text)


def _pdf_text_layer_output_needs_ocr(quality: dict) -> bool:
    threshold = DIAGNOSIS_THRESHOLDS["post_convert_pdf_text_layer_unreadable"]
    return (
        quality.get("total_chars", 0) > 0
        and (
            quality.get("unreadable_text_ratio", 0) > threshold
            or quality.get("garbled_ratio", 0) > threshold
            or quality.get("mojibake_ratio", 0) > threshold
            or quality.get("replacement_char_ratio", 0) > threshold
        )
    )


def _pdf_text_layer_fallback_warning(rejected_quality: dict) -> str:
    unreadable = rejected_quality.get("unreadable_text_ratio", 0)
    garbled = rejected_quality.get("garbled_ratio", 0)
    return (
        "W_PDF_TEXT_LAYER_FALLBACK_TO_OCR: text-layer conversion produced unreadable Markdown "
        f"(unreadable={unreadable:.2%}, garbled={garbled:.2%}); reran MinerU in OCR mode."
    )


def _mineru_mode_for_strategy(strategy: object) -> str:
    value = str(strategy or "")
    if value == "mineru_txt":
        return "txt"
    if value == "mineru_ocr":
        return "ocr"
    return "auto"


def _maybe_fallback_pdf_markdown_to_mineru(
    input_p: Path,
    converted_path: Path,
    run_dir: Path,
    language: str,
    source_route: str,
    source_artifacts: dict,
) -> dict | None:
    text = converted_path.read_text(encoding="utf-8") if converted_path.exists() else ""
    rejected_quality = _converted_text_quality(text)
    source_artifacts["post_convert_text_quality"] = rejected_quality

    if not _pdf_text_layer_output_needs_ocr(rejected_quality):
        return None

    rejected_path = run_dir / f"converted.{source_route}.rejected.md"
    if converted_path.exists():
        shutil.copy2(str(converted_path), str(rejected_path))

    fallback = _run_mineru_conversion(
        input_p=input_p,
        converted_path=converted_path,
        run_dir=run_dir,
        language=language,
        mode="ocr",
    )
    fallback["fallback_from"] = source_route
    fallback["fallback_reason"] = "post_convert_text_unreadable"
    fallback["rejected_text_layer_md"] = str(rejected_path)
    fallback["rejected_markdown_path"] = str(rejected_path)
    fallback["rejected_text_layer_quality"] = rejected_quality
    ocr_text = converted_path.read_text(encoding="utf-8") if converted_path.exists() else ""
    fallback["post_convert_text_quality"] = _converted_text_quality(ocr_text)
    fallback["warnings"] = [*fallback.get("warnings", []), _pdf_fallback_warning(source_route, rejected_quality)]
    return fallback


def _pdf_fallback_warning(source_route: str, rejected_quality: dict) -> str:
    if source_route == "pdf_text_layer":
        return _pdf_text_layer_fallback_warning(rejected_quality)
    unreadable = rejected_quality.get("unreadable_text_ratio", 0)
    garbled = rejected_quality.get("garbled_ratio", 0)
    return (
        "W_PDF_MARKDOWN_FALLBACK_TO_OCR: "
        f"{source_route} produced unreadable Markdown "
        f"(unreadable={unreadable:.2%}, garbled={garbled:.2%}); reran MinerU in OCR mode."
    )


def _write_conversion_report(
    run_dir: Path,
    input_path: Path,
    output_path: Path,
    converter: str,
    route: ConversionRoute,
    source_type: str,
    mineru_artifacts: dict,
    runtime: dict,
    diagnosis: dict,
    warnings: list[str],
) -> None:
    route_decision = _conversion_route_decision(
        input_path=input_path,
        converter=converter,
        route=route,
        diagnosis=diagnosis,
        mineru_artifacts=mineru_artifacts,
    )
    report = {
        "input_file": input_path.name,
        "input_extension": input_path.suffix.lower(),
        "converter": converter,
        "route_decision": route_decision,
        "source_type": source_type,
        "diagnosed_format": diagnosis.get("detected_format"),
        "diagnosed_pipeline": diagnosis.get("recommended_pipeline"),
        "diagnosed_strategy": diagnosis.get("conversion_strategy"),
        "diagnosed_split_strategy": diagnosis.get("split_strategy"),
        "text_profile": diagnosis.get("text_profile"),
        "text_layer_health": diagnosis.get("text_layer_health"),
        "pdf_subtype": diagnosis.get("pdf_subtype"),
        "layout_profile": diagnosis.get("layout_profile"),
        "pdf_route_diagnostics": diagnosis.get("pdf_route_diagnostics"),
        "converted_md": str(output_path),
        "converted_bytes": output_path.stat().st_size if output_path.exists() else 0,
        "mineru_artifacts": mineru_artifacts,
        "runtime": runtime,
        "warnings": warnings,
    }
    atomic_write_json(
        run_dir / "conversion_report.json",
        report,
        indent=2,
        trailing_newline=False,
    )


def _conversion_route_decision(
    input_path: Path,
    converter: str,
    route: ConversionRoute,
    diagnosis: dict,
    mineru_artifacts: dict,
) -> dict:
    capability = diagnosis.get("capability") if isinstance(diagnosis.get("capability"), dict) else {}
    if not capability:
        capability = get_capability_for_extension(input_path.suffix.lower())

    actual_route = _actual_route_for_converter(converter, diagnosis, mineru_artifacts)
    fallback_from = mineru_artifacts.get("fallback_from") or None
    fallback_applied = bool(fallback_from) or converter in PDF_FALLBACK_CONVERTERS
    fallback_to = actual_route if fallback_applied else None

    decision = {
        "declared_capability_id": capability.get("id", ""),
        "declared_route": capability.get("route", ""),
        "declared_status": capability.get("status", ""),
        "diagnosed_pipeline": diagnosis.get("recommended_pipeline", ""),
        "diagnosed_strategy": diagnosis.get("conversion_strategy", ""),
        "actual_converter": converter,
        "actual_route": actual_route,
        "matched_converter": route.matched_converter,
        "match_evidence": list(route.match_evidence),
        "selected_route": _selected_route_for_decision(route),
        "fallback_applied": fallback_applied,
        "fallback_from": fallback_from,
        "fallback_to": fallback_to,
    }
    pdf_route = diagnosis.get("pdf_route_diagnostics")
    if isinstance(pdf_route, dict):
        decision["selected_pdf_tier"] = pdf_route.get("recommended_tier")
        decision["pdf_route_reason"] = pdf_route.get("reason", "")
        decision["pdf_route_diagnostics_schema"] = pdf_route.get("schema")
    return decision


def _selected_route_for_decision(route: ConversionRoute) -> str:
    if route.kind.value == "mineru_ocr" and route.conversion_strategy in {
        "mineru_txt",
        "mineru_ocr",
        "mineru_auto",
        "mineru_mixed_text_image",
    }:
        return route.conversion_strategy
    return route.kind.value


def _actual_route_for_converter(converter: str, diagnosis: dict, mineru_artifacts: dict | None = None) -> str:
    if converter in PDF_FALLBACK_CONVERTERS:
        return "mineru_ocr"
    if converter == "mineru":
        strategy = str(diagnosis.get("conversion_strategy") or "")
        pdf_route = diagnosis.get("pdf_route_diagnostics")
        if isinstance(pdf_route, dict) and pdf_route.get("recommended_route") in {
            "mineru_txt",
            "mineru_auto",
            "mineru_ocr",
        }:
            return str(pdf_route["recommended_route"])
        if strategy in {"mineru_txt", "mineru_ocr", "mineru_auto", "mineru_mixed_text_image"}:
            return strategy
        return "mineru"
    if converter == "image_to_pdf_ocr":
        return "image_to_pdf_then_mineru_ocr"
    if converter.startswith("legacy_office_"):
        if isinstance(mineru_artifacts, dict) and mineru_artifacts.get("fallback_from") == "pdf_text_layer":
            return "legacy_office_to_pdf_then_mineru_ocr"
        generated = diagnosis.get("generated_pdf_diagnosis")
        if isinstance(generated, dict):
            return f"legacy_office_to_pdf_then_{generated.get('conversion_strategy', 'pdf_route')}"
        return "legacy_office_to_pdf_route"
    if converter == "media_transcript":
        return "media_to_transcript"
    return converter


def _run_diagnose_direct(input_path: str, output_root: str, source_type: str) -> dict:
    from ..diagnose import DiagnoseError, diagnose_file

    payload = {
        "input_path": input_path,
        "output_root": output_root,
        "source_type": source_type,
    }
    try:
        result, warnings = diagnose_file(payload)
        return {"ok": True, "data": result, "warnings": warnings}
    except DiagnoseError as exc:
        return {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        }


def _primary_quality_issue(quality_report: dict) -> dict:
    issues = quality_report.get("quality_issues")
    if isinstance(issues, list):
        for issue in issues:
            if isinstance(issue, dict) and issue.get("code"):
                return issue
    strict_errors = quality_report.get("strict_errors")
    if isinstance(strict_errors, list) and strict_errors:
        first = str(strict_errors[0])
        code = first.split(":", 1)[0].strip() or "E_QA_FAILED"
        return {"code": code, "gate": _quality_gate_name_from_error(first), "message": first}
    return {"code": "E_QA_FAILED", "gate": "export_readiness", "message": "Quality gate failed"}


def _quality_gate_name_from_error(error: str) -> str:
    from ..quality.gates import ERROR_CODE_TO_GATE
    code = error.split(":", 1)[0].strip()
    if code in ERROR_CODE_TO_GATE:
        return ERROR_CODE_TO_GATE[code]
    if error.startswith(("E_TEXT_LAYER_", "E_CONVERTED_TEXT_", "E_SOURCE_CONVERSION_LOSS", "E_CONVERSION_STRUCTURE_LOSS")):
        return "conversion_integrity"
    return "export_readiness"


def _find_existing_run(
    root_p: Path,
    file_hash: str,
    config_hash: str,
    plugin_version: str,
    runtime_cache_key: str,
    policy_snapshot_hash: str | None = None,
    required_artifacts: tuple[str, ...] = (),
) -> dict | None:
    runs_dir = root_p / "runs"
    if not runs_dir.exists():
        return None
    scanned = 0
    for run_dir in sorted(runs_dir.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        scanned += 1
        if scanned > EXISTING_RUN_SCAN_LIMIT:
            break
        quality_file = run_dir / "quality_report.json"
        if quality_file.exists():
            try:
                report = json.loads(quality_file.read_text(encoding="utf-8"))
                if (report.get("source_sha256") == file_hash and
                    report.get("config_hash") == config_hash and
                    report.get("plugin_version") == plugin_version and
                    report.get("runtime_cache_key") == runtime_cache_key and
                    _policy_snapshot_matches(report, policy_snapshot_hash) and
                    _required_artifacts_exist(run_dir, required_artifacts) and
                    not report.get("strict_errors")):
                    return {"run_id": run_dir.name, "run_dir": str(run_dir)}
            except Exception:
                continue
    return None


def _policy_snapshot_matches(report: dict, policy_snapshot_hash: str | None) -> bool:
    if policy_snapshot_hash is None:
        return True
    return report.get("cleaning_policy_snapshot_hash") == policy_snapshot_hash


def _required_artifacts_exist(run_dir: Path, required_artifacts: tuple[str, ...]) -> bool:
    return all(_required_artifact_exists(run_dir, artifact) for artifact in required_artifacts)


def _required_artifact_exists(run_dir: Path, artifact: str) -> bool:
    path = run_dir / artifact
    if artifact == "cleaning_patches.jsonl":
        return validate_cleaning_patches_artifact(path)
    return path.exists()


def _prepare_metadata_payload(
    *,
    input_path: Path,
    output_root: Path,
    profile: str,
    mode: str,
    language: str,
    source_type: str,
    splitter: str,
    artifact_policy: str,
    force: bool,
) -> dict:
    return {
        "input_path": str(input_path),
        "output_root": str(output_root),
        "profile": profile,
        "mode": mode,
        "language": language,
        "source_type": source_type,
        "splitter": splitter,
        "artifact_policy": artifact_policy,
        "force": force,
    }


def _write_run_metadata(
    *,
    run_dir: Path,
    run_id: str,
    input_path: Path,
    output_root: Path,
    source_type: str,
    language: str,
    mode: str,
    splitter: str,
    profile: str,
    artifact_policy: str,
    force: bool,
    file_hash: str,
    file_size: int,
    config_hash: str,
    plugin_version: str,
    mineru_version: str,
    runtime_cache_key: str,
    runtime: dict,
) -> None:
    metadata = {
        "schema": "kbprep.run_metadata.v1",
        "run_id": run_id,
        "input_path": str(input_path),
        "output_root": str(output_root),
        "prepare_payload": _prepare_metadata_payload(
            input_path=input_path, output_root=output_root, profile=profile,
            mode=mode, language=language, source_type=source_type,
            splitter=splitter, artifact_policy=artifact_policy, force=force,
        ),
        "source_sha256": file_hash,
        "file_size": file_size,
        "config_hash": config_hash,
        "plugin_version": plugin_version,
        "mineru_version": mineru_version,
        "runtime_cache_key": runtime_cache_key,
        "runtime": runtime,
        "created_at": time.time(),
    }
    atomic_write_json(
        run_dir / "run_metadata.json",
        metadata,
        indent=2,
        trailing_newline=False,
    )


def _update_run_metadata(run_dir: Path, updates: dict) -> None:
    metadata_path = run_dir / "run_metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    except Exception:
        metadata = {}
    metadata.update(updates)
    atomic_write_json(
        metadata_path,
        metadata,
        indent=2,
        trailing_newline=False,
    )


def _source_identity_for_rules(input_path: Path, data: dict) -> dict:
    identity: dict = {
        "input_path": str(input_path),
        "source_path": str(input_path),
        "source_name": input_path.name,
    }

    raw_identity = data.get("source_identity")
    if isinstance(raw_identity, dict):
        _merge_identity_values(identity, raw_identity)
    elif isinstance(raw_identity, str) and raw_identity.strip():
        identity["source_identity"] = raw_identity.strip()

    source_metadata = data.get("source_metadata")
    if isinstance(source_metadata, dict):
        identity["source_metadata"] = source_metadata
        _merge_identity_values(identity, source_metadata)

    for key in (
        "source_url",
        "source_domain",
        "site_name",
        "origin",
        "origin_url",
        "source_title",
    ):
        value = _identity_scalar(data.get(key))
        if value:
            identity[key] = value

    if "source_domain" not in identity:
        domain = _domain_from_identity_url(identity.get("source_url") or identity.get("origin_url"))
        if domain:
            identity["source_domain"] = domain

    return identity


def _merge_identity_values(identity: dict, values: dict) -> None:
    for key in (
        "source_url",
        "source_domain",
        "site_name",
        "origin",
        "origin_url",
        "source_title",
    ):
        if key not in identity:
            value = _identity_scalar(values.get(key))
            if value:
                identity[key] = value


def _identity_scalar(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _domain_from_identity_url(value) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    parsed = urlparse(value.strip())
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain




def _generate_audit_md(
    input_name: str,
    file_hash: str,
    plugin_version: str,
    mineru_version: str,
    python_version: str,
    runtime: dict,
    diagnosis: dict,
    blocks: list[dict],
    quality_report: dict,
    warnings: list[str],
    strict_errors: list[str],
) -> str:
    return _generate_audit_from_context(AuditContext(
        input_name=input_name,
        file_hash=file_hash,
        plugin_version=plugin_version,
        mineru_version=mineru_version,
        python_version=python_version,
        runtime=runtime,
        diagnosis=diagnosis,
        blocks=blocks,
        quality_report=quality_report,
        warnings=warnings,
        strict_errors=strict_errors,
    ))
