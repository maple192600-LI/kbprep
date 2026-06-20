"""Runtime-facing diagnose command entry points."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..converter_capabilities import get_capability_for_extension
from ..envelope import fail, ok
from ..supported_formats import (
    FORMAT_BY_EXTENSION,
    SOURCE_TYPE_BY_FORMAT,
)
from .format_detect import analyze_audio_video, analyze_ebook, analyze_markdown, analyze_office
from .pdf_analysis import analyze_pdf

EXTENSION_MAP = FORMAT_BY_EXTENSION
SOURCE_TYPE_MAP = SOURCE_TYPE_BY_FORMAT


class DiagnoseError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def diagnose_file(data: dict) -> tuple[dict, list[str]]:
    """Analyze one input file and return worker data plus warnings."""
    input_path = data["input_path"]
    override_source_type = data.get("source_type", "auto")

    input_p = Path(input_path)
    if not input_p.exists():
        raise DiagnoseError("E_INPUT_NOT_FOUND", f"Input file does not exist: {input_path}")

    warnings = []
    file_hash, file_size = _input_file_metadata(input_p)
    ext = input_p.suffix.lower()
    detected_format = EXTENSION_MAP.get(ext, "unknown")
    capability = get_capability_for_extension(ext)

    if detected_format == "unknown":
        raise DiagnoseError("E_UNSUPPORTED_TYPE", f"Unsupported file extension: {ext}")

    source_type = _diagnosed_source_type(detected_format, override_source_type)
    analysis = _analyze_detected_format(input_path, detected_format, ext)
    warnings.extend(analysis.pop("warnings", []))
    result = _diagnosis_result(input_p, file_hash, file_size, detected_format, source_type, capability, analysis, warnings)
    return result, warnings


def _input_file_metadata(input_p: Path) -> tuple[str, int]:
    file_bytes = input_p.read_bytes()
    return hashlib.sha256(file_bytes).hexdigest(), len(file_bytes)


def _diagnosed_source_type(detected_format: str, override_source_type: object) -> object:
    if override_source_type and override_source_type != "auto":
        return override_source_type
    return SOURCE_TYPE_MAP.get(detected_format, "generic_block")


def _analyze_detected_format(input_path: str, detected_format: str, ext: str) -> dict:
    if detected_format == "pdf":
        return analyze_pdf(input_path)
    if detected_format == "ebook":
        return analyze_ebook(input_path, ext)
    if detected_format in ("markdown", "text", "subtitle_transcript", "html", "json", "code", "notebook"):
        return analyze_markdown(input_path, detected_format)
    if detected_format in ("audio", "video"):
        return analyze_audio_video(input_path, detected_format)
    if detected_format in ("docx", "doc", "xlsx", "xls", "pptx", "ppt"):
        return analyze_office(input_path, detected_format)
    if detected_format == "image":
        return _image_analysis()
    return {
        "page_count": 0,
        "text_layer_health": "unknown",
        "needs_ocr": False,
        "recommended_pipeline": "direct",
    }


def _image_analysis() -> dict:
    return {
        "page_count": 1,
        "text_layer_health": "needs_conversion",
        "needs_ocr": True,
        "recommended_pipeline": "image_to_pdf_ocr",
        "conversion_strategy": "image_to_pdf_then_mineru_ocr",
    }


def _diagnosis_result(
    input_p: Path,
    file_hash: str,
    file_size: int,
    detected_format: str,
    source_type: object,
    capability: dict,
    analysis: dict,
    warnings: list[str],
) -> dict:
    result = {
        "ok": True,
        "file_id": file_hash,
        "file_name": input_p.name,
        "file_size": file_size,
        "detected_format": detected_format,
        "source_type": source_type,
        "capability": capability,
        "needs_ocr": analysis.get("needs_ocr", False),
        "recommended_pipeline": analysis.get("recommended_pipeline", "direct"),
        "warnings": warnings,
        **analysis,
    }
    if not result.get("conversion_strategy"):
        result["conversion_strategy"] = result.get("recommended_pipeline", "direct")
    return result


def run(data: dict) -> None:
    """Entry point for diagnose command."""
    try:
        result, warnings = diagnose_file(data)
    except DiagnoseError as exc:
        fail(exc.code, exc.message, details=exc.details)
    ok(data=result, warnings=warnings)
