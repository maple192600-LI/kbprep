"""Quality gate runner."""

import logging
import re
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_json
from ..rule_loader import load_cleaning_rules
from .cleanup_safety import (
    allows_cta_keyword_context,
    counts_for_discard_ratio,
    counts_for_text_coverage,
    is_image_block,
    matches_cleanup_pollution,
    qr_image_matches,
)
from .conversion_integrity import (
    conversion_structure_integrity as check_conversion_structure_integrity,
)
from .conversion_integrity import (
    converted_text_quality as read_converted_text_quality,
)
from .conversion_integrity import (
    source_conversion_integrity as check_source_conversion_integrity,
)
from .conversion_integrity import (
    source_text_layer_status,
)
from .gates import (
    build_quality_gates,
    quality_tasks_from_actions,
    write_quality_gate_artifacts,
)
from .io import read_json_file
from .markdown_signals import detect_language_from_blocks
from .retention import detail_retention_stats, image_retention_stats, output_retention_stats
from .thresholds import (
    CLEANING_THRESHOLDS,
    CONVERSION_THRESHOLDS,
    COVERAGE_THRESHOLDS,
    SPLITTING_THRESHOLDS,
)

logger = logging.getLogger(__name__)


def run_quality_check(
    blocks: list[dict],
    run_dir: str,
    source_type: str,
    diagnosis: dict,
    profile: str = "standard",
    document_type: str = "",
    rule_templates: list[str] | tuple[str, ...] | None = None,
    review_applied_at: float | int | None = None,
    quality_iteration: int | str | None = 1,
    max_quality_iterations: int | str | None = 3,
    previous_quality_iteration: int | str | None = None,
) -> dict:
    """Run all quality checks and produce quality_report.json."""
    strict_errors: list[str] = []
    quality_issues: list[dict[str, Any]] = []
    warnings: list[str] = []
    run_p = Path(run_dir)
    cleaning_rules = load_cleaning_rules(profile=profile, document_type=document_type, templates=tuple(rule_templates or ()))
    conversion_gate_report = read_json_file(run_p / "conversion_quality_report.json")
    conversion_report, source_text_layer = _check_conversion_quality(diagnosis, run_p, strict_errors, quality_issues, warnings)
    source_integrity = _check_source_integrity(run_p, conversion_report, strict_errors, quality_issues)
    structure_integrity = _check_structure_integrity(blocks, run_p, strict_errors, quality_issues)
    block_stats = _block_status_stats(blocks)
    cleaning_stats = _check_cleaning_safety(blocks, run_p, cleaning_rules, block_stats, strict_errors, quality_issues, warnings)
    chunk_chars = _check_splitting_quality(run_p, strict_errors, quality_issues, warnings)
    coverage_data = _check_text_coverage(blocks, source_type, strict_errors, quality_issues, warnings)
    retention_data = _check_retention(block_stats["image_blocks"], blocks, run_p, strict_errors, quality_issues)
    quality_loop = _finalize_quality_loop(
        strict_errors,
        quality_issues,
        quality_iteration,
        max_quality_iterations,
        previous_quality_iteration,
    )
    context = _quality_context(
        diagnosis, source_type, profile, document_type, rule_templates, review_applied_at, cleaning_rules.sources
    )
    report = _build_quality_report(
        context, blocks, block_stats, cleaning_stats, coverage_data, retention_data,
        source_text_layer, source_integrity, structure_integrity, conversion_gate_report, quality_loop,
        chunk_chars, quality_issues, strict_errors, warnings,
    )
    _attach_quality_gate_outputs(report, quality_loop, run_p, strict_errors, warnings)
    return report


def _quality_context(
    diagnosis: dict,
    source_type: str,
    profile: str,
    document_type: str,
    rule_templates: list[str] | tuple[str, ...] | None,
    review_applied_at: float | int | None,
    cleaning_rule_sources: tuple[str, ...],
) -> dict:
    return {
        "diagnosis": diagnosis,
        "source_type": source_type,
        "profile": profile,
        "document_type": document_type,
        "rule_templates": rule_templates or [],
        "review_applied_at": review_applied_at,
        "cleaning_rule_sources": cleaning_rule_sources,
    }


def _check_conversion_quality(
    diagnosis: dict,
    run_p: Path,
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
    warnings: list[str],
) -> tuple[dict, dict]:
    conversion_report = read_json_file(run_p / "conversion_report.json")
    source_text_layer = source_text_layer_status(diagnosis, conversion_report)
    _check_source_text_layer_quality(source_text_layer, diagnosis.get("text_quality", {}), strict_errors, quality_issues, warnings)
    _check_converted_text_quality(conversion_report, strict_errors, quality_issues)
    return conversion_report, source_text_layer


def _check_source_text_layer_quality(
    source_text_layer: dict,
    text_quality: dict,
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    ratios = (
        ("garbled_ratio", "E_TEXT_LAYER_GARBLED", "garbled ratio", "garbled"),
        ("unreadable_text_ratio", "E_TEXT_LAYER_UNREADABLE", "unreadable ratio", "unreadable"),
        ("mojibake_ratio", "E_TEXT_LAYER_MOJIBAKE", "mojibake ratio", "mojibake"),
    )
    if source_text_layer["superseded_by_conversion"]:
        worst_ratio = max(float(text_quality.get(key, 0)) for key, _, _, _ in ratios)
        if worst_ratio > CONVERSION_THRESHOLDS["garbage_ratio_warn"]:
            warnings.append(
                "W_SOURCE_TEXT_LAYER_SUPERSEDED: source PDF text layer is unreadable, "
                "so final quality is judged from the converted/OCR output."
            )
        return
    for key, code, label, warning_label in ratios:
        _check_text_quality_ratio(float(text_quality.get(key, 0)), code, label, warning_label, strict_errors, quality_issues, warnings)


def _check_text_quality_ratio(
    value: float,
    code: str,
    label: str,
    warning_label: str,
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    if value > CONVERSION_THRESHOLDS["garbage_ratio_strict"]:
        _append_quality_issue(
            strict_errors,
            quality_issues,
            code,
            "conversion_integrity",
            f"{label} {value:.2%} exceeds strict threshold",
        )
    elif value > CONVERSION_THRESHOLDS["garbage_ratio_warn"]:
        warnings.append(f"W_PDF_TEXT_LAYER_UNTRUSTED: {warning_label} ratio {value:.2%}")


def _check_converted_text_quality(conversion_report: dict, strict_errors: list[str], quality_issues: list[dict[str, Any]]) -> None:
    converted_quality = read_converted_text_quality(conversion_report)
    checks = (
        ("garbled_ratio", "E_CONVERTED_TEXT_GARBLED", "converted text garbled ratio"),
        ("unreadable_text_ratio", "E_CONVERTED_TEXT_UNREADABLE", "converted text unreadable ratio"),
        ("mojibake_ratio", "E_CONVERTED_TEXT_MOJIBAKE", "converted text mojibake ratio"),
    )
    for key, code, label in checks:
        value = float(converted_quality.get(key, 0)) if converted_quality else 0.0
        if value > CONVERSION_THRESHOLDS["garbage_ratio_strict"]:
            _append_quality_issue(
                strict_errors,
                quality_issues,
                code,
                "conversion_integrity",
                f"{label} {value:.2%} exceeds strict threshold",
            )


def _check_source_integrity(run_p: Path, conversion_report: dict, strict_errors: list[str], quality_issues: list[dict[str, Any]]) -> dict:
    integrity = check_source_conversion_integrity(run_p, conversion_report)
    atomic_write_json(run_p / "source_conversion_integrity.json", integrity, indent=2, trailing_newline=False)
    checks = (
        ("missing_heading_count", "source headings missing from converted Markdown"),
        ("missing_table_count", "source tables missing from converted Markdown"),
        ("missing_code_block_count", "source code blocks missing from converted Markdown"),
        ("missing_image_ref_count", "source image references missing from converted Markdown"),
    )
    for key, message in checks:
        if integrity.get(key, 0) > CONVERSION_THRESHOLDS["structure_loss_strict"]:
            _append_quality_issue(
                strict_errors,
                quality_issues,
                "E_SOURCE_CONVERSION_LOSS",
                "conversion_integrity",
                f"{integrity[key]} {message}",
            )
    return integrity


def _check_structure_integrity(blocks: list[dict], run_p: Path, strict_errors: list[str], quality_issues: list[dict[str, Any]]) -> dict:
    integrity = check_conversion_structure_integrity(blocks, run_p)
    checks = (
        ("missing_heading_count", "converted headings missing from block trace"),
        ("missing_table_count", "converted tables missing from block trace"),
        ("missing_code_block_count", "converted code blocks missing from block trace"),
        ("missing_image_ref_count", "converted image references missing from block trace"),
    )
    for key, message in checks:
        if integrity[key] > CONVERSION_THRESHOLDS["structure_loss_strict"]:
            _append_quality_issue(
                strict_errors,
                quality_issues,
                "E_CONVERSION_STRUCTURE_LOSS",
                "conversion_integrity",
                f"{integrity[key]} {message}",
            )
    return integrity


def _block_status_stats(blocks: list[dict]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for block in blocks:
        status = str(block.get("status", "unclassified"))
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "total_blocks": len(blocks),
        "status_counts": status_counts,
        "operation_step_blocks": [block for block in blocks if block.get("type") == "operation_step"],
        "prompt_blocks": [block for block in blocks if block.get("type") == "prompt"],
        "code_blocks": [block for block in blocks if block.get("type") == "code"],
        "table_blocks": [block for block in blocks if block.get("type") == "table"],
        "image_blocks": [block for block in blocks if is_image_block(block)],
    }


def _check_cleaning_safety(
    blocks: list[dict],
    run_p: Path,
    cleaning_rules: Any,
    block_stats: dict[str, Any],
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    protected_discarded = _check_block_loss(
        [block for block in blocks if block.get("protected")], "protected blocks", "E_PROTECTED_BLOCK_LOSS",
        CLEANING_THRESHOLDS["protected_block_loss_strict"], strict_errors, quality_issues,
    )
    op_step_discarded = _check_block_loss(
        block_stats["operation_step_blocks"], "operation_step blocks", "E_OPERATION_STEP_LOSS",
        CLEANING_THRESHOLDS["operation_step_loss_strict"], strict_errors, quality_issues,
    )
    code_discarded = _check_block_loss(
        block_stats["code_blocks"], "code blocks", "E_CODE_BLOCK_LOSS",
        CLEANING_THRESHOLDS["code_block_loss_strict"], strict_errors, quality_issues,
    )
    table_discarded = _check_block_loss(
        block_stats["table_blocks"], "table blocks", "E_TABLE_BLOCK_LOSS",
        CLEANING_THRESHOLDS["table_loss_strict"], strict_errors, quality_issues,
    )
    _check_cleaned_residue(blocks, run_p, cleaning_rules, strict_errors, quality_issues)
    discard_ratio = _check_discard_ratio(blocks, strict_errors, quality_issues, warnings)
    return {
        **discard_ratio,
        "protected_discarded": protected_discarded,
        "op_step_discarded": op_step_discarded,
        "code_discarded": code_discarded,
        "table_discarded": table_discarded,
    }


def _check_block_loss(
    blocks: list[dict],
    block_label: str,
    code: str,
    threshold: float,
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
) -> list[dict]:
    discarded = [block for block in blocks if block.get("status") == "discard"]
    if len(discarded) > threshold:
        _append_quality_issue(
            strict_errors, quality_issues, code, "cleanup_safety", f"{len(discarded)} {block_label} were discarded",
            evidence={"block_ids": _block_ids(discarded)},
        )
    return discarded


def _check_cleaned_residue(
    blocks: list[dict],
    run_p: Path,
    cleaning_rules: Any,
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
) -> None:
    cleaned_path = run_p / "cleaned.md"
    if not cleaned_path.exists():
        return
    cleaned_text = cleaned_path.read_text(encoding="utf-8")
    cta_violations = [
        block for block in blocks
        if block.get("status") == "keep"
        and matches_cleanup_pollution(block.get("text", ""), cleaning_rules)
        and not allows_cta_keyword_context(block, cleaning_rules)
    ]
    if len(cta_violations) > CLEANING_THRESHOLDS["cta_in_cleaned_strict"]:
        _append_quality_issue(
            strict_errors, quality_issues, "E_CTA_RESIDUE", "cleanup_safety",
            f"{len(cta_violations)} CTA patterns found in non-protected cleaned blocks",
            evidence={"block_ids": _block_ids(cta_violations)},
        )
    qr_matches = qr_image_matches(cleaned_text, cleaning_rules)
    if len(qr_matches) > CLEANING_THRESHOLDS["qr_image_in_cleaned_strict"]:
        _append_quality_issue(
            strict_errors,
            quality_issues,
            "E_QR_RESIDUE",
            "cleanup_safety",
            f"{len(qr_matches)} QR images found in cleaned.md",
            evidence={"matches": qr_matches[:10]},
        )


def _check_discard_ratio(
    blocks: list[dict],
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    evaluated_blocks = [block for block in blocks if counts_for_discard_ratio(block)]
    discarded_blocks = [block for block in evaluated_blocks if block.get("status") == "discard"]
    discard_ratio = len(discarded_blocks) / len(evaluated_blocks) if evaluated_blocks else 0.0
    if discard_ratio > CLEANING_THRESHOLDS["discard_ratio_strict"]:
        _append_quality_issue(
            strict_errors, quality_issues, "E_DISCARD_RATIO_EXCEEDED", "cleanup_safety",
            f"discard ratio {discard_ratio:.2%} exceeds strict threshold", evidence={"discard_ratio": round(discard_ratio, 4)},
        )
    elif discard_ratio > CLEANING_THRESHOLDS["discard_ratio_warn"]:
        warnings.append(f"W_LOW_COVERAGE: discard ratio {discard_ratio:.2%}")
    return {"discard_ratio": discard_ratio, "discard_ratio_evaluated_blocks": len(evaluated_blocks)}


def _check_splitting_quality(
    run_p: Path,
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
    warnings: list[str],
) -> list[int]:
    chunks_dir = run_p / "chunks"
    chunk_chars = _chunk_text_lengths(chunks_dir)
    if chunk_chars:
        too_short = sum(1 for chars in chunk_chars if chars < SPLITTING_THRESHOLDS["chunk_chars_min_warn"])
        too_long = sum(1 for chars in chunk_chars if chars > SPLITTING_THRESHOLDS["chunk_chars_max_warn"])
        if too_short > 0:
            warnings.append(f"W_LOW_COVERAGE: {too_short} chunks below {SPLITTING_THRESHOLDS['chunk_chars_min_warn']} chars")
        if too_long > 0:
            warnings.append(f"W_LOW_COVERAGE: {too_long} chunks above {SPLITTING_THRESHOLDS['chunk_chars_max_warn']} chars")
    broken_code = _count_chunks_with_unclosed_code_fences(chunks_dir)
    if broken_code > SPLITTING_THRESHOLDS["broken_code_block_strict"]:
        _append_quality_issue(
            strict_errors,
            quality_issues,
            "E_BROKEN_CODE_BLOCK",
            "splitting_integrity",
            f"{broken_code} chunks have broken code blocks",
        )
    return chunk_chars


def _chunk_text_lengths(chunks_dir: Path) -> list[int]:
    if not chunks_dir.exists():
        return []
    chunk_chars = []
    for chunk_file in sorted(chunks_dir.glob("*.md")):
        text = chunk_file.read_text(encoding="utf-8")
        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                text = text[end + 3:].strip()
        chunk_chars.append(len(text))
    return chunk_chars


def _check_text_coverage(
    blocks: list[dict],
    source_type: str,
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    coverage_blocks = [block for block in blocks if counts_for_text_coverage(block)]
    excluded_blocks = [block for block in blocks if not counts_for_text_coverage(block)]
    keep_chars = sum(len(block.get("text", "")) for block in coverage_blocks if block.get("status") == "keep")
    total_chars = sum(len(block.get("text", "")) for block in coverage_blocks)
    coverage = keep_chars / total_chars if total_chars > 0 else 1.0
    coverage_warn = COVERAGE_THRESHOLDS["warn"].get(source_type, 0.80)
    coverage_strict = COVERAGE_THRESHOLDS["strict"].get(source_type, 0.70)
    if coverage < coverage_strict:
        _append_quality_issue(
            strict_errors, quality_issues, "E_TEXT_COVERAGE_LOW", "cleanup_safety",
            f"coverage {coverage:.2%} below strict threshold {coverage_strict:.0%}",
            evidence={"coverage": round(coverage, 4), "threshold": coverage_strict},
        )
    elif coverage < coverage_warn:
        warnings.append(f"W_LOW_COVERAGE: coverage {coverage:.2%} below warn threshold {coverage_warn:.0%}")
    return {
        "coverage": coverage,
        "coverage_blocks": coverage_blocks,
        "excluded_blocks": excluded_blocks,
        "excluded_chars": sum(len(block.get("text", "")) for block in excluded_blocks),
    }


def _check_retention(
    image_blocks: list[dict],
    blocks: list[dict],
    run_p: Path,
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    image_stats = _check_image_retention(image_blocks, run_p, strict_errors, quality_issues)
    detail_stats = _check_detail_retention(blocks, strict_errors, quality_issues)
    output_stats = _check_output_retention(blocks, run_p, strict_errors, quality_issues)
    return {"image_stats": image_stats, "detail_stats": detail_stats, "output_stats": output_stats}


def _check_image_retention(image_blocks: list[dict], run_p: Path, strict_errors: list[str], quality_issues: list[dict[str, Any]]) -> dict:
    image_stats = image_retention_stats(image_blocks, run_p)
    if image_stats["missing_file_count"] >= CONVERSION_THRESHOLDS["missing_image_file_strict"]:
        _append_quality_issue(
            strict_errors, quality_issues, "E_IMAGE_FILE_MISSING", "conversion_integrity",
            f"{image_stats['missing_file_count']} referenced image files are missing",
            evidence={"missing_file_count": image_stats["missing_file_count"]},
        )
    if image_stats.get("invalid_svg_count", 0) > 0:
        _append_quality_issue(
            strict_errors, quality_issues, "E_SVG_INVALID", "conversion_integrity",
            f"{image_stats['invalid_svg_count']} SVG diagram files have invalid root dimensions",
            evidence={"invalid_svg_count": image_stats["invalid_svg_count"]},
        )
    return image_stats


def _check_detail_retention(blocks: list[dict], strict_errors: list[str], quality_issues: list[dict[str, Any]]) -> dict:
    detail_stats = detail_retention_stats(blocks)
    if detail_stats["discarded_detail_block_ids"]:
        _append_quality_issue(
            strict_errors, quality_issues, "E_DETAIL_BLOCK_DISCARDED", "cleanup_safety",
            f"{len(detail_stats['discarded_detail_block_ids'])} detail-bearing blocks were discarded",
            evidence={"block_ids": detail_stats["discarded_detail_block_ids"]},
        )
    return detail_stats


def _check_output_retention(blocks: list[dict], run_p: Path, strict_errors: list[str], quality_issues: list[dict[str, Any]]) -> dict:
    output_stats = output_retention_stats(blocks, run_p)
    if output_stats["missing_total"] > 0:
        _append_quality_issue(
            strict_errors, quality_issues, "E_OUTPUT_RETENTION_MISSING", "export_readiness",
            f"{output_stats['missing_total']} kept detail signals missing from final knowledge output",
            evidence={"missing_total": output_stats["missing_total"]},
        )
    return output_stats


def _finalize_quality_loop(
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
    quality_iteration: int | str | None,
    max_quality_iterations: int | str | None,
    previous_quality_iteration: int | str | None,
) -> dict:
    quality_loop = _quality_loop_state(strict_errors, quality_iteration, max_quality_iterations, previous_quality_iteration)
    if quality_loop["status"] == "iteration_limit_reached":
        _append_quality_issue(
            strict_errors, quality_issues, "E_QUALITY_ITERATION_LIMIT", "export_readiness",
            f"quality loop reached iteration {quality_loop['current_iteration']} "
            f"of {quality_loop['max_iterations']} while strict errors remain",
        )
        quality_loop["strict_error_count"] = len(strict_errors)
    return quality_loop


def _build_quality_report(
    context: dict[str, Any],
    blocks: list[dict],
    block_stats: dict[str, Any],
    cleaning_stats: dict[str, Any],
    coverage_data: dict[str, Any],
    retention_data: dict[str, Any],
    source_text_layer: dict,
    source_integrity: dict,
    structure_integrity: dict,
    conversion_gate_report: dict,
    quality_loop: dict,
    chunk_chars: list[int],
    quality_issues: list[dict[str, Any]],
    strict_errors: list[str],
    warnings: list[str],
) -> dict:
    report = _quality_report_core(context, blocks)
    report.update(_quality_report_counts(block_stats, cleaning_stats, coverage_data))
    report.update(_quality_report_retention(block_stats, cleaning_stats, retention_data))
    report.update(_quality_report_artifacts(
        retention_data,
        source_text_layer,
        source_integrity,
        structure_integrity,
        conversion_gate_report,
        quality_loop,
    ))
    report.update(_quality_report_runtime(chunk_chars, quality_issues, strict_errors, warnings))
    if context["review_applied_at"] is not None:
        report["review_applied_at"] = context["review_applied_at"]
    return report


def _quality_report_core(context: dict[str, Any], blocks: list[dict]) -> dict:
    return {
        "source_sha256": context["diagnosis"].get("file_id", ""),
        "source_type": context["source_type"],
        "profile": context["profile"],
        "document_type": context["document_type"],
        "rule_templates": list(context["rule_templates"]),
        "language_detected": detect_language_from_blocks(blocks),
        "cleaning_rule_sources": list(context["cleaning_rule_sources"]),
    }


def _quality_report_counts(block_stats: dict[str, Any], cleaning_stats: dict[str, Any], coverage_data: dict[str, Any]) -> dict:
    status_counts = block_stats["status_counts"]
    total_blocks = block_stats["total_blocks"]
    return {
        "total_blocks": total_blocks,
        "keep_blocks": status_counts.get("keep", 0),
        "discard_blocks": status_counts.get("discard", 0),
        "evidence_blocks": status_counts.get("evidence", 0),
        "review_blocks": status_counts.get("review", 0),
        "discard_ratio": round(cleaning_stats["discard_ratio"], 4),
        "discard_ratio_scope": "body_candidate_blocks_excluding_known_pollution",
        "discard_ratio_evaluated_blocks": cleaning_stats["discard_ratio_evaluated_blocks"],
        "discard_ratio_excluded_blocks": total_blocks - cleaning_stats["discard_ratio_evaluated_blocks"],
        "coverage_ratio": round(coverage_data["coverage"], 4),
        "coverage_scope": "text_blocks_excluding_image_only_evidence",
        "coverage_evaluated_blocks": len(coverage_data["coverage_blocks"]),
        "coverage_excluded_blocks": len(coverage_data["excluded_blocks"]),
        "coverage_excluded_chars": coverage_data["excluded_chars"],
    }


def _quality_report_retention(block_stats: dict[str, Any], cleaning_stats: dict[str, Any], retention_data: dict[str, Any]) -> dict:
    image_stats = retention_data["image_stats"]
    prompt_discarded = [block for block in block_stats["prompt_blocks"] if block.get("status") == "discard"]
    return {"retention": {
        "operation_step_total": len(block_stats["operation_step_blocks"]),
        "operation_step_discarded": len(cleaning_stats["op_step_discarded"]),
        "prompt_total": len(block_stats["prompt_blocks"]),
        "prompt_discarded": len(prompt_discarded),
        "code_total": len(block_stats["code_blocks"]),
        "code_discarded": len(cleaning_stats["code_discarded"]),
        "table_total": len(block_stats["table_blocks"]),
        "table_discarded": len(cleaning_stats["table_discarded"]),
        "image_total": image_stats["total_blocks"],
        "image_keep": image_stats["keep_blocks"],
        "image_evidence": image_stats["evidence_blocks"],
        "image_review": image_stats["review_blocks"],
        "image_discarded": image_stats["discard_blocks"],
        "image_referenced_files": image_stats["referenced_file_count"],
        "image_missing_files": image_stats["missing_file_count"],
        "image_invalid_svg_files": image_stats.get("invalid_svg_count", 0),
    }}


def _quality_report_artifacts(
    retention_data: dict[str, Any],
    source_text_layer: dict,
    source_integrity: dict,
    structure_integrity: dict,
    conversion_gate_report: dict,
    quality_loop: dict,
) -> dict:
    return {
        "conversion_quality_gate": conversion_gate_report,
        "detail_retention": retention_data["detail_stats"],
        "source_text_layer": source_text_layer,
        "source_conversion_integrity": source_integrity,
        "conversion_structure_integrity": structure_integrity,
        "output_retention": retention_data["output_stats"],
        "image_retention": retention_data["image_stats"],
        "quality_loop": quality_loop,
    }


def _quality_report_runtime(
    chunk_chars: list[int],
    quality_issues: list[dict[str, Any]],
    strict_errors: list[str],
    warnings: list[str],
) -> dict:
    return {
        "chunk_count": len(chunk_chars),
        "chunk_chars_avg": round(sum(chunk_chars) / len(chunk_chars)) if chunk_chars else 0,
        "quality_issues": quality_issues,
        "strict_errors": strict_errors,
        "warnings": warnings,
        "thresholds": {
            "conversion": CONVERSION_THRESHOLDS,
            "cleaning": CLEANING_THRESHOLDS,
            "splitting": SPLITTING_THRESHOLDS,
            "coverage": COVERAGE_THRESHOLDS,
        },
    }


def _attach_quality_gate_outputs(report: dict, quality_loop: dict, run_p: Path, strict_errors: list[str], warnings: list[str]) -> None:
    gates, next_actions = build_quality_gates(strict_errors, warnings, report)
    if quality_loop["status"] == "iteration_limit_reached":
        next_actions = [{
            "gate": "export_readiness",
            "action": "stop_iteration",
            "target": "quality_loop",
            "reason": "Quality still fails after the configured maximum review/cleanup iterations.",
            "strict_error_count": len(strict_errors),
        }, *next_actions]
    report["quality_gates"] = gates
    report["next_actions"] = next_actions
    report["quality_tasks"] = quality_tasks_from_actions(report, next_actions, run_p)
    report["quality_gate_artifacts"] = write_quality_gate_artifacts(report, gates, run_p)


def _quality_loop_state(
    strict_errors: list[str],
    quality_iteration: int | str | None,
    max_quality_iterations: int | str | None,
    previous_quality_iteration: int | str | None,
) -> dict:
    current = _positive_int(quality_iteration, 1)
    max_iterations = _positive_int(max_quality_iterations, 3)
    previous = _non_negative_int(previous_quality_iteration, current - 1 if current > 1 else 0)
    has_strict_errors = bool(strict_errors)
    limit_reached = has_strict_errors and current >= max_iterations
    if not has_strict_errors:
        status = "passed"
    elif limit_reached:
        status = "iteration_limit_reached"
    else:
        status = "needs_iteration"
    return {
        "current_iteration": current,
        "previous_iteration": previous,
        "max_iterations": max_iterations,
        "remaining_iterations": max(0, max_iterations - current),
        "can_continue": has_strict_errors and not limit_reached,
        "status": status,
        "strict_error_count": len(strict_errors),
    }

def _positive_int(value: int | str | None, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)

def _non_negative_int(value: int | str | None, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(0, parsed)

def _count_chunks_with_unclosed_code_fences(chunks_dir: Path) -> int:
    if not chunks_dir.exists():
        return 0
    broken_code = 0
    for chunk_file in sorted(chunks_dir.glob("*.md")):
        text = chunk_file.read_text(encoding="utf-8")
        if _has_unclosed_markdown_code_fence(text):
            broken_code += 1
    return broken_code

def _has_unclosed_markdown_code_fence(text: str) -> bool:
    opener_char = ""
    opener_len = 0
    fence_pattern = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = fence_pattern.match(line)
        if not match:
            continue
        fence = match.group(1)
        char = fence[0]
        length = len(fence)
        if not opener_char:
            opener_char = char
            opener_len = length
            continue
        if char == opener_char and length >= opener_len:
            opener_char = ""
            opener_len = 0
    return bool(opener_char)

def _append_quality_issue(
    strict_errors: list[str],
    quality_issues: list[dict],
    code: str,
    gate: str,
    message: str,
    evidence: dict | None = None,
) -> None:
    strict_errors.append(f"{code}: {message}")
    issue: dict[str, Any] = {
        "code": code,
        "gate": gate,
        "message": message,
    }
    if evidence:
        issue["evidence"] = evidence
    quality_issues.append(issue)

def _block_ids(blocks: list[dict]) -> list[str]:
    return [str(block.get("block_id") or "") for block in blocks if block.get("block_id")]
