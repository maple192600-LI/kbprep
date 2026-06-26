"""External local-tool conversion helpers for the prepare pipeline."""

from __future__ import annotations

from pathlib import Path

from ..atomic_io import atomic_write_text
from ..converter_registry import ConversionRouteKind
from ..converters.external_tools import extract_youtube_transcript
from ..pdf_route_policy import selected_pdf_strategy
from ..youtube_source import youtube_url_from_source
from .pipeline_helpers import (
    _maybe_fallback_pdf_markdown_to_mineru,
    _mineru_mode_for_strategy,
    _run_mineru_conversion,
)
from .pipeline_state import PipelineError, PipelineState


def convert_external_route(
    state: PipelineState,
    converted_path: Path,
    run_dir: Path,
    route_kind: ConversionRouteKind,
) -> dict:
    if route_kind == ConversionRouteKind.IMAGE_TO_PDF_OCR:
        return _convert_image_via_external_pdf(state, converted_path, run_dir)
    if route_kind == ConversionRouteKind.LEGACY_OFFICE_TO_PDF:
        return _convert_legacy_office_via_pdf(state, converted_path, run_dir)
    if route_kind == ConversionRouteKind.MEDIA_TRANSCRIPT:
        return _convert_media_to_transcript(state, converted_path, run_dir)
    if route_kind == ConversionRouteKind.YOUTUBE_TRANSCRIPT:
        return _convert_youtube_to_transcript(state, converted_path, run_dir)
    raise PipelineError("E_UNSUPPORTED_TYPE", f"External route is not supported: {route_kind.value}")


def external_route_message(route_kind: ConversionRouteKind) -> str:
    messages = {
        ConversionRouteKind.IMAGE_TO_PDF_OCR: "Image wrapped as PDF and converted with MinerU OCR",
        ConversionRouteKind.LEGACY_OFFICE_TO_PDF: "Legacy Office converted to PDF and routed",
        ConversionRouteKind.MEDIA_TRANSCRIPT: "Media transcribed to text",
        ConversionRouteKind.YOUTUBE_TRANSCRIPT: "YouTube subtitles or media transcript converted to text",
    }
    return messages.get(route_kind, "External conversion complete")


def _convert_youtube_to_transcript(state: PipelineState, converted_path: Path, run_dir: Path) -> dict:
    source_url = youtube_url_from_source(state.input_p, state.data)
    external = extract_youtube_transcript(
        source_url,
        run_dir,
        allow_media_fallback=state.data.get("allow_youtube_media_fallback") is True,
    )
    _raise_external_conversion_failure(external.report)
    transcript_path = _external_artifact_path(external.artifact_path)
    text = transcript_path.read_text(encoding="utf-8")
    atomic_write_text(converted_path, text.rstrip() + "\n")
    return {
        "source_md_path": str(converted_path),
        "converter": "youtube_transcript",
        "transcript_path": str(transcript_path),
        "external_conversion": external.report,
        "warnings": [],
    }


def _convert_image_via_external_pdf(state: PipelineState, converted_path: Path, run_dir: Path) -> dict:
    from ..converters.external_tools import wrap_image_as_pdf

    external = wrap_image_as_pdf(state.input_p, run_dir)
    _raise_external_conversion_failure(external.report)
    pdf_path = _external_artifact_path(external.artifact_path)
    result = _run_mineru_conversion(pdf_path, converted_path, run_dir, state.language, "ocr")
    result["converter"] = "image_to_pdf_ocr"
    result["external_conversion"] = external.report
    result["external_artifact_path"] = str(pdf_path)
    return result


def _convert_legacy_office_via_pdf(state: PipelineState, converted_path: Path, run_dir: Path) -> dict:
    from ..converters.external_tools import convert_legacy_office_to_pdf

    external = convert_legacy_office_to_pdf(state.input_p, run_dir)
    _raise_external_conversion_failure(external.report)
    pdf_path = _external_artifact_path(external.artifact_path)
    pdf_artifacts, pdf_diagnosis = _convert_generated_pdf(pdf_path, converted_path, run_dir, state.language)
    pdf_artifacts["external_conversion"] = external.report
    pdf_artifacts["external_artifact_path"] = str(pdf_path)
    pdf_artifacts["generated_pdf_diagnosis"] = pdf_diagnosis
    pdf_artifacts["converter"] = f"legacy_office_{pdf_artifacts.get('converter', 'pdf_route')}"
    state.diagnosis["generated_pdf_diagnosis"] = pdf_diagnosis
    return pdf_artifacts


def _convert_media_to_transcript(state: PipelineState, converted_path: Path, run_dir: Path) -> dict:
    from ..converters.external_tools import transcribe_media

    external = transcribe_media(state.input_p, run_dir)
    _raise_external_conversion_failure(external.report)
    transcript_path = _external_artifact_path(external.artifact_path)
    text = transcript_path.read_text(encoding="utf-8")
    atomic_write_text(converted_path, text.rstrip() + "\n")
    return {
        "source_md_path": str(converted_path),
        "converter": "media_transcript",
        "transcript_path": str(transcript_path),
        "external_conversion": external.report,
        "warnings": [],
    }


def _convert_generated_pdf(pdf_path: Path, converted_path: Path, run_dir: Path, language: str) -> tuple[dict, dict]:
    from ..diagnose.pdf_analysis import analyze_pdf

    pdf_diagnosis = analyze_pdf(str(pdf_path))
    strategy = selected_pdf_strategy(pdf_diagnosis)
    if strategy in {"pymupdf4llm", "pdf_text_layer"}:
        artifacts = _convert_generated_pdf_text_route(pdf_path, converted_path, run_dir, language, strategy)
    else:
        mode = _mineru_mode_for_strategy(strategy)
        artifacts = _run_mineru_conversion(pdf_path, converted_path, run_dir, language, mode)
        artifacts["mineru_mode"] = mode
    return artifacts, pdf_diagnosis


def _convert_generated_pdf_text_route(
    pdf_path: Path,
    converted_path: Path,
    run_dir: Path,
    language: str,
    strategy: str,
) -> dict:
    if strategy == "pymupdf4llm":
        from ..pymupdf4llm_adapter import convert_pymupdf4llm_pdf

        artifacts = convert_pymupdf4llm_pdf(pdf_path, converted_path, run_dir)
    else:
        from .. import pdf_text

        artifacts = pdf_text.convert_text_layer_pdf(pdf_path, converted_path, run_dir)
    fallback = _maybe_fallback_pdf_markdown_to_mineru(
        input_p=pdf_path,
        converted_path=converted_path,
        run_dir=run_dir,
        language=language,
        source_route=strategy,
        source_artifacts=artifacts,
    )
    return fallback if fallback else artifacts


def _raise_external_conversion_failure(report: dict) -> None:
    route_decision = report.get("route_decision")
    if isinstance(route_decision, dict) and route_decision.get("status") == "success":
        return
    raw_failure = report.get("failure_reason")
    failure: dict = raw_failure if isinstance(raw_failure, dict) else {}
    code = str(failure.get("code") or "E_CONVERT_FAILED")
    message = str(failure.get("message") or "External conversion failed.")
    raise PipelineError(code, message, {"external_conversion": report})


def _external_artifact_path(path: Path | None) -> Path:
    if path is None:
        raise PipelineError("E_CONVERT_OUTPUT_MISSING", "External conversion did not produce an artifact.")
    return Path(path)
