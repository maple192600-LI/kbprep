"""Conversion stage for the single-file prepare pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..canonical_ir import write_canonical_ir_manifests
from ..converter_registry import ConversionRouteKind, file_identity_for_path, select_conversion_route
from ..supported_formats import CODE_EXTENSIONS, NOTEBOOK_EXTENSIONS
from .pipeline_helpers import (
    _converted_text_quality,
    _pdf_text_layer_output_needs_ocr,
    _run_mineru_conversion,
    _validate_convertible_container,
    _write_conversion_report,
)
from .pipeline_state import PipelineError, PipelineState, _stderr_log

_EXTERNAL_CONVERSION_ROUTE_KINDS = {
    ConversionRouteKind.IMAGE_TO_PDF_OCR,
    ConversionRouteKind.LEGACY_OFFICE_TO_PDF,
    ConversionRouteKind.MEDIA_TRANSCRIPT,
}


def run_conversion_stage(state: PipelineState) -> None:
    state.require_stage_fields("convert", "run_dir")
    run_dir = state.require_path("convert", "run_dir")
    _stderr_log("info", "convert", "Converting file")
    converted_path = run_dir / "converted.md"
    state.converted_path = converted_path
    ext, route = _select_conversion_route_for_state(state)
    _run_selected_conversion(state, converted_path, run_dir, ext, route)
    _ensure_converted_output(converted_path)
    _stderr_log("info", "convert", f"Converted file size: {converted_path.stat().st_size} bytes")
    _write_conversion_report_for_route(state, run_dir, converted_path, ext, route)


def _select_conversion_route_for_state(state: PipelineState) -> tuple[str, Any]:
    file_identity = file_identity_for_path(state.input_p)
    ext = file_identity.extension
    route = select_conversion_route(ext, state.diagnosis, file_identity=file_identity)
    state.diagnosis["matched_converter"] = route.matched_converter
    state.diagnosis["match_evidence"] = list(route.match_evidence)
    return ext, route


def _run_selected_conversion(
    state: PipelineState,
    converted_path: Path,
    run_dir: Path,
    ext: str,
    route: Any,
) -> None:
    if route.kind in {ConversionRouteKind.MEDIA_TRANSCRIPT_REQUIRED, ConversionRouteKind.UNSUPPORTED}:
        _raise_unsupported_conversion_route(route, ext)
    if route.kind == ConversionRouteKind.DIRECT_TEXT:
        _convert_direct_text_route(state, converted_path, run_dir, route, ext)
    elif route.kind == ConversionRouteKind.OFFICE_XML:
        _convert_office_xml_route(state, converted_path, run_dir, ext)
    elif route.kind == ConversionRouteKind.EPUB_XHTML:
        _convert_epub_route(state, converted_path, run_dir)
    elif route.kind in _EXTERNAL_CONVERSION_ROUTE_KINDS:
        _convert_external_route_kind(state, converted_path, run_dir, route.kind)
    elif route.kind == ConversionRouteKind.PDF_TEXT_LAYER:
        _convert_pdf_text_layer_route(state, converted_path, run_dir)
    elif route.kind == ConversionRouteKind.MINERU_OCR:
        _convert_mineru_ocr_route(state, converted_path, run_dir)


def _raise_unsupported_conversion_route(route: Any, ext: str) -> None:
    raise PipelineError(
        route.error_code or "E_UNSUPPORTED_TYPE",
        route.message,
        {
            "extension": ext,
            "recommended_pipeline": route.converter,
            "conversion_strategy": route.conversion_strategy,
        },
    )


def _convert_direct_text_route(
    state: PipelineState,
    converted_path: Path,
    run_dir: Path,
    route: Any,
    ext: str,
) -> None:
    from .local_conversion import convert_direct_text

    convert_direct_text(state, converted_path, run_dir, route.match_evidence, ext)
    _stderr_log("info", "convert", "Text-like file normalized directly")


def _convert_office_xml_route(state: PipelineState, converted_path: Path, run_dir: Path, ext: str) -> None:
    from .local_conversion import convert_office_xml

    convert_office_xml(state, converted_path, run_dir, ext)
    _stderr_log("info", "convert", "Office XML converted directly")


def _convert_epub_route(state: PipelineState, converted_path: Path, run_dir: Path) -> None:
    _validate_convertible_container(state.input_p)
    from ..epub import convert_epub
    result, epub_warnings = convert_epub(state.input_p, converted_path, run_dir)
    state.mineru_artifacts = result
    state.warnings.extend(epub_warnings)
    _stderr_log("info", "convert", "EPUB XHTML converted directly")


def _convert_external_route_kind(
    state: PipelineState,
    converted_path: Path,
    run_dir: Path,
    route_kind: ConversionRouteKind,
) -> None:
    from .external_conversion import convert_external_route, external_route_message

    state.mineru_artifacts = convert_external_route(state, converted_path, run_dir, route_kind)
    state.warnings.extend(state.mineru_artifacts.get("warnings", []))
    _stderr_log("info", "convert", external_route_message(route_kind))


def _convert_pdf_text_layer_route(state: PipelineState, converted_path: Path, run_dir: Path) -> None:
    from .. import pdf_text
    result = pdf_text.convert_text_layer_pdf(state.input_p, converted_path, run_dir)
    state.mineru_artifacts = result
    state.warnings.extend(result.get("warnings", []))
    _stderr_log("info", "convert", "PDF text layer converted directly")
    fallback = _maybe_fallback_pdf_text_layer_to_mineru(
        input_p=state.input_p,
        converted_path=converted_path,
        run_dir=run_dir,
        language=state.language,
        text_layer_artifacts=result,
    )
    if fallback:
        state.mineru_artifacts = fallback
        state.warnings.extend(fallback.get("warnings", []))
        _stderr_log("warn", "convert", "PDF text layer was unreadable; fell back to MinerU OCR")


def _convert_mineru_ocr_route(state: PipelineState, converted_path: Path, run_dir: Path) -> None:
    result = _run_mineru_conversion(state.input_p, converted_path, run_dir, state.language, "auto")
    state.mineru_artifacts = result
    state.warnings.extend(result.get("warnings", []))
    _stderr_log("info", "convert", "MinerU conversion complete")


def _ensure_converted_output(converted_path: Path) -> None:
    if not converted_path.exists():
        raise PipelineError("E_CONVERT_OUTPUT_MISSING", "converted.md not found after conversion")


def _write_conversion_report_for_route(
    state: PipelineState,
    run_dir: Path,
    converted_path: Path,
    ext: str,
    route: Any,
) -> None:
    _write_conversion_report(
        run_dir=run_dir,
        input_path=state.input_p,
        output_path=converted_path,
        converter=_conversion_report_converter(route.kind, ext, state.mineru_artifacts),
        route=route,
        source_type=state.source_type,
        mineru_artifacts=state.mineru_artifacts,
        runtime=state.runtime,
        diagnosis=state.diagnosis,
        warnings=state.warnings,
    )
    write_canonical_ir_manifests(
        run_dir=run_dir,
        input_path=state.input_p,
        source_type=state.source_type,
        file_hash=state.file_hash,
        file_size=state.file_size,
        run_id=state.run_id,
    )


def _conversion_report_converter(route: ConversionRouteKind, ext: str, artifacts: dict) -> str:
    if ext in CODE_EXTENSIONS:
        return "direct_code"
    if ext in NOTEBOOK_EXTENSIONS:
        return "notebook_json"
    if artifacts.get("fallback_from") == "pdf_text_layer":
        return "mineru_after_pdf_text_layer_fallback"
    if route == ConversionRouteKind.DIRECT_TEXT:
        return "direct_text"
    if route == ConversionRouteKind.OFFICE_XML:
        return "office_xml"
    if route == ConversionRouteKind.EPUB_XHTML:
        return "epub_xhtml"
    if route == ConversionRouteKind.IMAGE_TO_PDF_OCR:
        return "image_to_pdf_ocr"
    if route == ConversionRouteKind.LEGACY_OFFICE_TO_PDF:
        return str(artifacts.get("converter") or "legacy_office_to_pdf")
    if route == ConversionRouteKind.MEDIA_TRANSCRIPT:
        return "media_transcript"
    if route == ConversionRouteKind.PDF_TEXT_LAYER:
        return "pdf_text_layer"
    if route == ConversionRouteKind.MINERU_OCR:
        return "mineru"
    return "unsupported"


def _maybe_fallback_pdf_text_layer_to_mineru(
    input_p: Path,
    converted_path: Path,
    run_dir: Path,
    language: str,
    text_layer_artifacts: dict,
) -> dict | None:
    text = converted_path.read_text(encoding="utf-8") if converted_path.exists() else ""
    rejected_quality = _converted_text_quality(text)
    text_layer_artifacts["post_convert_text_quality"] = rejected_quality

    if not _pdf_text_layer_output_needs_ocr(rejected_quality):
        return None

    rejected_path = run_dir / "converted.pdf_text_layer.rejected.md"
    if converted_path.exists():
        shutil.copy2(str(converted_path), str(rejected_path))

    fallback = _run_mineru_conversion(
        input_p=input_p,
        converted_path=converted_path,
        run_dir=run_dir,
        language=language,
        mode="ocr",
    )
    fallback["fallback_from"] = "pdf_text_layer"
    fallback["fallback_reason"] = "post_convert_text_unreadable"
    fallback["rejected_text_layer_md"] = str(rejected_path)
    fallback["rejected_text_layer_quality"] = rejected_quality
    ocr_text = converted_path.read_text(encoding="utf-8") if converted_path.exists() else ""
    fallback["post_convert_text_quality"] = _converted_text_quality(ocr_text)
    fallback["warnings"] = [*fallback.get("warnings", []), _fallback_warning(rejected_quality)]
    return fallback


def _fallback_warning(rejected_quality: dict) -> str:
    unreadable = rejected_quality.get("unreadable_text_ratio", 0)
    garbled = rejected_quality.get("garbled_ratio", 0)
    return (
        "W_PDF_TEXT_LAYER_FALLBACK_TO_OCR: text-layer conversion produced unreadable Markdown "
        f"(unreadable={unreadable:.2%}, garbled={garbled:.2%}); reran MinerU in OCR mode."
    )
