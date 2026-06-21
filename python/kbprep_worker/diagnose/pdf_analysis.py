"""PDF subtype and processing-strategy analysis helpers."""

from __future__ import annotations

import contextlib
import io
from typing import Any

from ..detect import detect_language_from_text
from ..quality.thresholds import DIAGNOSIS_THRESHOLDS
from .pdf_route_diagnostics import build_pdf_route_diagnostics
from .text_quality import analyze_text_quality, detect_text_profile


def analyze_pdf(input_path: str) -> dict:
    """Analyze PDF file quality using PyMuPDF (fitz)."""
    warnings = []
    result = _initial_pdf_result()

    try:
        import fitz  # PyMuPDF
    except ImportError:
        warnings.append("PyMuPDF not installed. PDF analysis limited. Install: pip install pymupdf")
        # Try basic analysis with mineru's content extraction
        result["text_layer_health"] = "unavailable"
        return _finalize_pdf_result(result, warnings)

    analysis_errors = _fitz_analysis_errors(fitz)
    doc: Any | None = None
    try:
        doc = fitz.open(input_path)
        page_stats = _collect_pdf_page_stats(doc)
        total_text = page_stats["total_text"]
        result.update({key: value for key, value in page_stats.items() if key != "total_text"})
        image_pages = page_stats["image_pages"]
        text_pages = page_stats["text_pages"]
        image_count = page_stats["image_count"]
        landscape_pages = page_stats["landscape_pages"]

        quality = analyze_text_quality(total_text)
        result["text_quality"] = quality
        detected_language = detect_language_from_text(total_text)
        result["detected_language"] = detected_language
        if total_text.strip():
            result.update(detect_text_profile(total_text, "pdf"))

        _apply_text_layer_assessment(result, quality, image_pages, text_pages, detected_language, warnings)
        _apply_image_ratio_assessment(result, image_pages, text_pages, warnings)
        _append_ocr_confusion_warning(quality, warnings)

        _apply_pdf_layout_profile(result, image_pages, text_pages, image_count, landscape_pages)
        _apply_pdf_processing_strategy(result)

    except analysis_errors as e:
        warnings.append(f"PDF analysis error: {e}")
        result["text_layer_health"] = "error"
    finally:
        if doc is not None:
            _close_pdf_doc(doc, warnings)

    return _finalize_pdf_result(result, warnings)


def _finalize_pdf_result(result: dict, warnings: list[str]) -> dict:
    result["warnings"] = warnings
    result["pdf_route_diagnostics"] = build_pdf_route_diagnostics(result)
    return result


def _fitz_analysis_errors(fitz_module: Any) -> tuple[type[BaseException], ...]:
    errors: list[type[BaseException]] = [OSError, RuntimeError, ValueError]
    for name in ("FileDataError", "EmptyFileError", "FileNotFoundError"):
        error_type = getattr(fitz_module, name, None)
        if isinstance(error_type, type) and issubclass(error_type, BaseException):
            errors.append(error_type)
    return tuple(errors)


def _close_pdf_doc(doc: Any, warnings: list[str]) -> None:
    try:
        doc.close()
    except (OSError, RuntimeError, ValueError) as exc:
        warnings.append(f"PDF analysis close warning: {exc}")


def _initial_pdf_result() -> dict:
    return {
        "page_count": 0,
        "image_pages": 0,
        "text_pages": 0,
        "empty_pages": 0,
        "total_text_length": 0,
        "image_count": 0,
        "text_layer_health": "unknown",
        "is_scanned": False,
        "is_garbled": False,
        "needs_ocr": False,
        "recommended_pipeline": "mineru_pipeline",
    }


def diagnostic_page_indexes(page_count: int) -> tuple[tuple[int, ...], bool]:
    if page_count <= int(DIAGNOSIS_THRESHOLDS["pdf_large_page_count"]):
        return tuple(range(page_count)), False

    head = int(DIAGNOSIS_THRESHOLDS["pdf_large_sample_head_pages"])
    tail = int(DIAGNOSIS_THRESHOLDS["pdf_large_sample_tail_pages"])
    stride = int(DIAGNOSIS_THRESHOLDS["pdf_large_sample_stride"])
    pages = set(range(min(head, page_count)))
    pages.update(range(max(page_count - tail, 0), page_count))
    pages.update(range(0, page_count, stride))
    return tuple(sorted(pages)), True


def _collect_pdf_page_stats(doc: Any) -> dict:
    page_indexes, sampling_applied = diagnostic_page_indexes(len(doc))
    stats = _initial_page_stats()
    for page_num in page_indexes:
        _update_page_stats(doc[page_num], stats)
    return _page_stats_payload(len(doc), page_indexes, sampling_applied, stats)


def _initial_page_stats() -> dict[str, Any]:
    return {
        "image_pages": 0,
        "text_pages": 0,
        "empty_pages": 0,
        "total_text": "",
        "image_count": 0,
        "landscape_pages": 0,
        "max_image_count_on_page": 0,
        "multi_column_pages": 0,
        "table_pages": 0,
        "image_text_interleaved_pages": 0,
    }


def _update_page_stats(page: Any, stats: dict[str, Any]) -> None:
    if page.rect.width > page.rect.height:
        stats["landscape_pages"] += 1
    text = page.get_text("text").strip()
    images = page.get_images(full=True)
    stats["image_count"] += len(images)
    stats["max_image_count_on_page"] = max(stats["max_image_count_on_page"], len(images))

    if _page_has_multi_column_text(page):
        stats["multi_column_pages"] += 1
    if _page_has_tables(page, text):
        stats["table_pages"] += 1
    if text and images:
        stats["image_text_interleaved_pages"] += 1

    _update_text_image_page_counts(stats, text, bool(images))


def _update_text_image_page_counts(stats: dict[str, Any], text: str, has_images: bool) -> None:
    if not text and has_images:
        stats["image_pages"] += 1
    elif text:
        stats["text_pages"] += 1
        stats["total_text"] += text + "\n"
    else:
        stats["empty_pages"] += 1


def _page_stats_payload(
    page_count: int,
    page_indexes: tuple[int, ...],
    sampling_applied: bool,
    stats: dict[str, Any],
) -> dict:
    total_text = stats["total_text"]
    text_pages = stats["text_pages"]
    return {
        "page_count": page_count,
        "sampled_page_count": len(page_indexes),
        "large_pdf_sampling_applied": sampling_applied,
        "large_pdf_sampled_pages": len(page_indexes),
        "large_pdf_sample_strategy": "first_5_last_5_stride_10" if sampling_applied else "full_scan",
        "image_pages": stats["image_pages"],
        "text_pages": text_pages,
        "empty_pages": stats["empty_pages"],
        "total_text": total_text,
        "total_text_length": len(total_text),
        "image_count": stats["image_count"],
        "landscape_pages": stats["landscape_pages"],
        "max_image_count_on_page": stats["max_image_count_on_page"],
        "multi_column_pages": stats["multi_column_pages"],
        "table_pages": stats["table_pages"],
        "image_text_interleaved_pages": stats["image_text_interleaved_pages"],
        "average_text_chars_per_text_page": round(len(total_text) / text_pages, 1) if text_pages else 0,
    }


def _page_has_multi_column_text(page: Any) -> bool:
    try:
        page_dict = page.get_text("dict")
    except (RuntimeError, ValueError, TypeError):
        return False
    if not isinstance(page_dict, dict):
        return False
    blocks = page_dict.get("blocks", [])
    text_boxes = [
        block["bbox"]
        for block in blocks
        if block.get("type") == 0 and _block_text(block).strip()
    ]
    if len(text_boxes) < DIAGNOSIS_THRESHOLDS["pdf_multi_column_min_blocks"]:
        return False
    width = float(page.rect.width)
    has_left = any(float(box[0]) < width * 0.45 for box in text_boxes)
    has_right = any(float(box[0]) > width * 0.45 for box in text_boxes)
    return has_left and has_right


def _block_text(block: dict) -> str:
    lines = block.get("lines")
    if not isinstance(lines, list):
        return ""
    spans: list[str] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        for span in line.get("spans", []):
            if isinstance(span, dict):
                spans.append(str(span.get("text") or ""))
    return "".join(spans)


def _page_has_tables(page: Any, text: str) -> bool:
    finder = getattr(page, "find_tables", None)
    if callable(finder):
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                tables = finder()
            return bool(getattr(tables, "tables", []))
        except (RuntimeError, ValueError, TypeError):
            pass
    return "\t" in text


def _apply_bad_text_layer(result: dict, warnings: list[str], message: str, *, degraded: bool = False) -> None:
    result["text_layer_health"] = "degraded" if degraded else "bad"
    result["pdf_subtype"] = "garbled_text_layer"
    result["needs_ocr"] = True
    result["recommended_pipeline"] = "mineru_pipeline_ocr"
    if not degraded:
        result["is_garbled"] = True
    warnings.append(message)


def _apply_text_layer_assessment(
    result: dict,
    quality: dict,
    image_pages: int,
    text_pages: int,
    language: str,
    warnings: list[str],
) -> None:
    if text_pages == 0 and image_pages > 0:
        result["text_layer_health"] = "no_text_layer"
        result["pdf_subtype"] = "image_only_or_scanned"
        result["is_scanned"] = True
        result["needs_ocr"] = True
        result["recommended_pipeline"] = "mineru_pipeline_ocr"
    elif quality.get("unreadable_text_ratio", quality["garbled_ratio"]) > DIAGNOSIS_THRESHOLDS["pdf_unreadable_text_layer"]:
        _apply_bad_text_layer(
            result,
            warnings,
            "W_PDF_TEXT_LAYER_UNTRUSTED: "
            f"unreadable text ratio {quality.get('unreadable_text_ratio', 0):.2%}",
        )
    elif _mojibake_ratio_exceeds(quality, language, "pdf_mojibake_strict"):
        _apply_bad_text_layer(result, warnings, f"W_PDF_TEXT_LAYER_UNTRUSTED: mojibake ratio {quality['mojibake_ratio']:.2%}")
    elif quality["garbled_ratio"] > DIAGNOSIS_THRESHOLDS["pdf_garbled_strict"]:
        _apply_bad_text_layer(result, warnings, f"W_PDF_TEXT_LAYER_UNTRUSTED: garbled ratio {quality['garbled_ratio']:.2%}")
    elif _mojibake_ratio_exceeds(quality, language, "pdf_mojibake_warn"):
        _apply_bad_text_layer(result, warnings, f"W_PDF_TEXT_LAYER_UNTRUSTED: mojibake ratio {quality['mojibake_ratio']:.2%}", degraded=True)  # noqa: E501
    elif quality["garbled_ratio"] > DIAGNOSIS_THRESHOLDS["pdf_garbled_warn"]:
        _apply_bad_text_layer(result, warnings, f"W_PDF_TEXT_LAYER_UNTRUSTED: garbled ratio {quality['garbled_ratio']:.2%}", degraded=True)
    elif _readable_signal_ratio(quality) < DIAGNOSIS_THRESHOLDS["replacement_char_low_signal_ratio"] and result["page_count"] > 5:
        _apply_bad_text_layer(result, warnings, "W_PDF_TEXT_LAYER_UNTRUSTED: low readable text signal", degraded=True)
    else:
        result["text_layer_health"] = "good"
        result["pdf_subtype"] = "text_layer"


def _mojibake_ratio_exceeds(quality: dict, language: str, threshold_key: str) -> bool:
    return language == "ch" and quality.get("mojibake_ratio", 0) > DIAGNOSIS_THRESHOLDS[threshold_key]


def _readable_signal_ratio(quality: dict) -> float:
    return float(quality.get("chinese_ratio", 0.0)) + float(quality.get("alnum_ratio", 0.0))


def _apply_image_ratio_assessment(result: dict, image_pages: int, text_pages: int, warnings: list[str]) -> None:
    if result["page_count"] <= 0:
        return
    page_denominator = _page_ratio_denominator(result)
    if page_denominator <= 0:
        return
    image_page_ratio = image_pages / page_denominator
    result["image_page_ratio"] = round(image_page_ratio, 4)
    if image_page_ratio > DIAGNOSIS_THRESHOLDS["pdf_image_page_ratio"]:
        result["needs_ocr"] = True
        result["pdf_subtype"] = "image_heavy_mixed" if text_pages else "image_only_or_scanned"
        if result["recommended_pipeline"] == "mineru_pipeline":
            result["recommended_pipeline"] = "mineru_pipeline_ocr"
            warnings.append(f"W_FORCE_OCR_RECOMMENDED: {image_page_ratio:.0%} pages are image-only")


def _append_ocr_confusion_warning(quality: dict, warnings: list[str]) -> None:
    if quality["ocr_ai_confusion_count"] > 0:
        warnings.append(f"W_OCR_AI_CONFUSION: {quality['ocr_ai_confusion_count']} AI/Al confusion patterns found")


def _apply_pdf_layout_profile(
    result: dict,
    image_pages: int,
    text_pages: int,
    image_count: int,
    landscape_pages: int,
) -> None:
    if result["page_count"] > 0 and image_pages > 0 and text_pages > 0 and "pdf_subtype" not in result:
        result["pdf_subtype"] = "mixed_text_image"
    page_denominator = _page_ratio_denominator(result)
    landscape_ratio = landscape_pages / page_denominator if page_denominator else 0
    result["landscape_ratio"] = round(landscape_ratio, 4)

    avg_chars = result["average_text_chars_per_text_page"]
    slide_like_score = 0.0
    if page_denominator >= 3:
        if landscape_ratio >= DIAGNOSIS_THRESHOLDS["pdf_landscape_ratio"]:
            slide_like_score += 0.45
        if avg_chars and avg_chars < 900:
            slide_like_score += DIAGNOSIS_THRESHOLDS["pdf_slide_image_score"]
        if image_count >= page_denominator:
            slide_like_score += DIAGNOSIS_THRESHOLDS["pdf_slide_text_score"]
        if text_pages <= max(1, page_denominator * DIAGNOSIS_THRESHOLDS["pdf_slide_image_score"]):
            slide_like_score += 0.1
    result["slide_like_score"] = round(min(slide_like_score, 1.0), 4)

    if result["slide_like_score"] >= DIAGNOSIS_THRESHOLDS["pdf_slide_like_score"]:
        result["layout_profile"] = "slide_deck_or_ppt_export"
    elif landscape_ratio >= DIAGNOSIS_THRESHOLDS["pdf_landscape_ratio"]:
        result["layout_profile"] = "landscape_report"
    elif image_pages / page_denominator > DIAGNOSIS_THRESHOLDS["pdf_image_page_ratio"] if page_denominator else False:
        result["layout_profile"] = "image_heavy_document"
    else:
        result["layout_profile"] = "document_pages"

    if (
        image_count >= page_denominator
        and text_pages <= max(1, page_denominator * DIAGNOSIS_THRESHOLDS["pdf_slide_text_score"])
        and landscape_ratio > DIAGNOSIS_THRESHOLDS["pdf_image_page_ratio"]
    ):
        result["pdf_subtype"] = "ppt_exported_or_scanned"
    elif (
        result.get("pdf_subtype") == "text_layer"
        and result["layout_profile"] == "slide_deck_or_ppt_export"
    ):
        result["pdf_subtype"] = "ppt_exported_text_layer"
    result["layout_complexity"] = _pdf_layout_complexity(result)


def _page_ratio_denominator(result: dict) -> int:
    if result.get("large_pdf_sampling_applied"):
        sampled = result.get("sampled_page_count")
        if isinstance(sampled, int) and sampled > 0:
            return sampled
    page_count = result.get("page_count")
    return page_count if isinstance(page_count, int) else 0


def _pdf_layout_complexity(result: dict) -> str:
    complex_profiles = {"slide_deck_or_ppt_export", "landscape_report", "image_heavy_document"}
    complex_subtypes = {"mixed_text_image", "ppt_exported_text_layer"}
    if result.get("layout_profile") in complex_profiles:
        return "complex"
    if result.get("pdf_subtype") in complex_subtypes:
        return "complex"
    if _structure_signal_ratio(result) >= DIAGNOSIS_THRESHOLDS["pdf_structure_signal_ratio_complex"]:
        return "complex"
    return "simple"


def _structure_signal_ratio(result: dict) -> float:
    denominator = _page_ratio_denominator(result)
    if denominator <= 0:
        return 0.0
    signals = (
        _positive_count(result.get("multi_column_pages")),
        _positive_count(result.get("table_pages")),
        _positive_count(result.get("image_text_interleaved_pages")),
    )
    return max(signals) / denominator


def _apply_pdf_processing_strategy(result: dict) -> None:
    pdf_subtype = result.get("pdf_subtype", "unknown")
    layout_profile = result.get("layout_profile", "unknown")
    hints: list[str] = []

    if result.get("needs_ocr"):
        result["recommended_pipeline"] = "mineru_pipeline_ocr"
        result["conversion_strategy"] = "mineru_ocr"
        hints.append("Run OCR because the text layer is missing, image-heavy, or untrusted.")
    elif result.get("layout_complexity") == "complex":
        result["recommended_pipeline"] = "mineru_pipeline"
        result["conversion_strategy"] = _complex_pdf_conversion_strategy(result)
        mode = result["conversion_strategy"].removeprefix("mineru_")
        hints.append(f"Use MinerU {mode} mode because the trusted text layer has complex visual layout.")
    else:
        result["recommended_pipeline"] = "pdf_text_layer"
        result["conversion_strategy"] = "pdf_text_layer"
        hints.append("Use the existing text layer; OCR is not recommended by diagnosis.")

    if "split_strategy" not in result:
        result["split_strategy"] = (
            "preserve_slide_or_page_order"
            if layout_profile == "slide_deck_or_ppt_export"
            else "content_structure"
        )

    if pdf_subtype in {"image_only_or_scanned", "ppt_exported_or_scanned"}:
        hints.append("Expect OCR output; keep discarded text recoverable for manual review.")
    if layout_profile == "slide_deck_or_ppt_export":
        hints.append("Slides and report pages often contain sparse but important details; avoid over-aggressive cleanup.")

    result["processing_hints"] = hints


def _complex_pdf_conversion_strategy(result: dict) -> str:
    if (
        _positive_count(result.get("table_pages"))
        or _positive_count(result.get("image_text_interleaved_pages"))
        or result.get("layout_profile") in {"slide_deck_or_ppt_export", "landscape_report", "image_heavy_document"}
    ):
        return "mineru_auto"
    return "mineru_txt"


def _positive_count(value: object) -> bool:
    return isinstance(value, int) and value > 0
