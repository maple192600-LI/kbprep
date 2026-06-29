"""Format-specific non-PDF diagnosis helpers."""

from __future__ import annotations

import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from ..converter_capabilities import get_capability_for_extension
from ..quality.thresholds import DIAGNOSIS_THRESHOLDS
from ..youtube_source import youtube_url_from_source
from .text_quality import analyze_text_quality, detect_text_profile


def analyze_markdown(input_path: str, detected_format: str | None = None) -> dict:
    """Analyze text-like files that can be converted without OCR."""
    warnings = []
    text_result = _read_profile_source_text(input_path, detected_format)
    if text_result.get("error"):
        return text_result["error"]
    text = str(text_result["text"])
    warnings.extend(text_result["warnings"])
    ext = Path(input_path).suffix.lower()
    profile_input = _text_for_profile(text, detected_format or "text")
    quality = analyze_text_quality(profile_input)
    profile_format = detected_format or ("markdown" if ext in {".md", ".markdown"} else "text")
    result = _base_markdown_analysis(profile_input, profile_format, quality)
    if detected_format == "code":
        result["conversion_strategy"] = "direct_code"
    elif detected_format == "notebook":
        result["conversion_strategy"] = "notebook_json"

    warnings.extend(_markdown_quality_warnings(quality, result))
    result["warnings"] = warnings
    return result


def _read_profile_source_text(input_path: str, detected_format: str | None) -> dict:
    if detected_format == "notebook":
        return _read_notebook_profile_text(input_path)
    try:
        return {"text": Path(input_path).read_text(encoding="utf-8"), "warnings": []}
    except UnicodeDecodeError:
        return _read_text_with_fallback_encoding(input_path)


def _read_notebook_profile_text(input_path: str) -> dict:
    try:
        from ..notebook import notebook_to_markdown
        return {"text": notebook_to_markdown(input_path), "warnings": []}
    except Exception as e:
        return {"error": {"text_layer_health": "error", "warnings": [f"Cannot parse notebook: {e}"]}}


def _read_text_with_fallback_encoding(input_path: str) -> dict:
    for encoding in ["utf-8-sig", "gbk", "gb2312", "latin-1"]:
        try:
            text = Path(input_path).read_text(encoding=encoding)
            return {"text": text, "warnings": [f"Encoding: {encoding} (not UTF-8)"]}
        except (UnicodeDecodeError, LookupError):
            continue
    return {"error": {"text_layer_health": "error", "warnings": ["Cannot decode file"]}}


def _base_markdown_analysis(profile_input: str, profile_format: str, quality: dict) -> dict:
    return {
        "page_count": 1,
        "total_text_length": len(profile_input),
        "heading_count": len(re.findall(r'^#{1,6}\s+', profile_input, re.MULTILINE)),
        "code_block_count": len(re.findall(r'^```[\s\S]*?^```', profile_input, re.MULTILINE)),
        "table_row_count": len(re.findall(r'^\|.+\|$', profile_input, re.MULTILINE)),
        "text_quality": quality,
        "text_layer_health": "good",
        "needs_ocr": False,
        "recommended_pipeline": "direct",
        **detect_text_profile(profile_input, profile_format),
    }


def _markdown_quality_warnings(quality: dict, result: dict) -> list[str]:
    warnings = []
    if quality["garbled_ratio"] > DIAGNOSIS_THRESHOLDS["markdown_garbled_warn"]:
        result["text_layer_health"] = "degraded"
        warnings.append(f"High garbled ratio: {quality['garbled_ratio']:.2%}")
    if quality["ocr_ai_confusion_count"] > 0:
        warnings.append(f"W_OCR_AI_CONFUSION: {quality['ocr_ai_confusion_count']} patterns found")
    return warnings


def _text_for_profile(text: str, detected_format: str) -> str:
    if detected_format == "html":
        return _html_text_for_profile(text)
    return text


def _html_text_for_profile(text: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return _html_text_for_profile_with_parser(text)

    soup = BeautifulSoup(text, "lxml")
    skip_tags = ["script", "style", "nav", "footer", "header", "aside", "figure", "figcaption", "noscript", "template"]
    for tag in soup(skip_tags):
        tag.decompose()
    return soup.get_text(" ", strip=True)


class _HTMLTextProfileParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "figure", "figcaption", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.SKIP_TAGS:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text and not self.skip_depth:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


def _html_text_for_profile_with_parser(text: str) -> str:
    parser = _HTMLTextProfileParser()
    parser.feed(text)
    parser.close()
    return parser.text()


def analyze_audio_video(input_path: str, detected_format: str) -> dict:
    return {
        "page_count": 0,
        "total_text_length": 0,
        "text_layer_health": "unavailable",
        "needs_ocr": False,
        "recommended_pipeline": "media_transcript",
        "conversion_strategy": "media_to_transcript",
        "text_profile": detected_format,
        "warnings": [
            "Audio/video will be transcribed with local ffmpeg + Whisper before quality gates run."
        ],
    }


def analyze_remote_url(input_path: str, data: dict | None = None) -> dict:
    source_url = youtube_url_from_source(Path(input_path), data)
    if not source_url:
        return {
            "page_count": 0,
            "text_layer_health": "unsupported",
            "needs_ocr": False,
            "recommended_pipeline": "unsupported",
            "conversion_strategy": "unsupported_extension",
            "warnings": ["Only YouTube .url descriptors are supported by this optional route."],
        }
    capability = get_capability_for_extension(".url")
    return {
        "page_count": 0,
        "total_text_length": 0,
        "text_layer_health": "unavailable",
        "needs_ocr": False,
        "recommended_pipeline": "youtube_transcript",
        "conversion_strategy": "youtube_subtitle_then_media_transcript",
        "text_profile": "remote_url",
        "capability": capability,
        "warnings": ["YouTube subtitles are tried before local media transcription fallback."],
    }


def analyze_office(input_path: str, detected_format: str) -> dict:
    """Choose the Office conversion route without mutating the input file."""
    modern_office = {"docx", "pptx", "xlsx"}
    if detected_format in modern_office:
        if not zipfile.is_zipfile(input_path):
            return {
                "page_count": 0,
                "text_layer_health": "invalid_container",
                "needs_ocr": False,
                "recommended_pipeline": "office_xml",
                "conversion_strategy": "office_xml",
                "warnings": [f"{detected_format} is not a valid Office Open XML package"],
            }
        return {
            "page_count": 0,
            "text_layer_health": "needs_conversion",
            "needs_ocr": False,
            "recommended_pipeline": "office_xml",
            "conversion_strategy": "office_xml",
            "warnings": [],
        }

    return {
        "page_count": 0,
        "text_layer_health": "unsupported",
        "needs_ocr": False,
        "recommended_pipeline": "unsupported",
        "conversion_strategy": "unsupported_extension",
        "warnings": [
            f"Legacy Office .{detected_format} is intentionally not adapted by KBPrep. "
            "Convert it to PDF or modern Office (.docx/.pptx/.xlsx) first."
        ],
    }


def analyze_ebook(input_path: str, ext: str) -> dict:
    if ext == ".epub":
        try:
            from ..epub import analyze_epub
            return analyze_epub(input_path)
        except Exception as e:
            return {
                "page_count": 0,
                "text_layer_health": "invalid_container",
                "needs_ocr": False,
                "recommended_pipeline": "epub_xhtml",
                "conversion_strategy": "epub_xhtml",
                "warnings": [f"EPUB analysis failed: {e}"],
            }
    return {
        "page_count": 0,
        "text_layer_health": "unsupported",
        "needs_ocr": False,
        "recommended_pipeline": "unsupported",
        "conversion_strategy": "unsupported_extension",
        "warnings": ["MOBI is not supported by KBPrep's verified conversion routes. Convert it to EPUB, PDF, Markdown, or text first."],
    }
