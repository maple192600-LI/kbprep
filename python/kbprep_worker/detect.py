"""Source type and lightweight language detection."""
from __future__ import annotations

import re
from pathlib import Path

from .supported_formats import (
    AUDIO_EXTENSIONS,
    CODE_EXTENSIONS,
    EPUB_EXTENSIONS,
    HTML_EXTENSIONS,
    IMAGE_EXTENSIONS,
    JSON_EXTENSIONS,
    LEGACY_OFFICE_EXTENSIONS,
    MARKDOWN_EXTENSIONS,
    NOTEBOOK_EXTENSIONS,
    OFFICE_XML_EXTENSIONS,
    PLAIN_TEXT_EXTENSIONS,
    SOURCE_TYPE_BY_EXTENSION,
    SUBTITLE_EXTENSIONS,
    TABLE_TEXT_EXTENSIONS,
    VIDEO_EXTENSIONS,
)

TEXT_EXTENSIONS = (
    MARKDOWN_EXTENSIONS
    | PLAIN_TEXT_EXTENSIONS
    | TABLE_TEXT_EXTENSIONS
    | HTML_EXTENSIONS
    | JSON_EXTENSIONS
    | SUBTITLE_EXTENSIONS
)
EXTENSION_MAP = SOURCE_TYPE_BY_EXTENSION
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002a6df]")
LATIN_RE = re.compile(r"[A-Za-z]")
LANGUAGE_CHINESE = "ch"
LANGUAGE_ENGLISH = "en"

CHINESE_LANGUAGE_HINTS = {
    "ch",
    "zh",
    "zh-cn",
    "zh_cn",
    "cn",
    "chinese",
    "simplified_chinese",
    "zh-hans",
    "zh_hans",
    "zh-tw",
    "zh_tw",
    "zh-hk",
    "zh_hk",
    "traditional_chinese",
    "chinese_cht",
}
ENGLISH_LANGUAGE_HINTS = {"en", "eng", "english"}


def detect_source_type(file_path: str) -> str:
    """Detect processing source_type from file extension."""
    ext = Path(file_path).suffix.lower()
    return SOURCE_TYPE_BY_EXTENSION.get(ext, "generic_block")


def detect_source_family(file_path: str) -> str:
    """Detect the broad input family for diagnostics and routing."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".docx", ".doc", ".odt"}:
        return "word"
    if ext in {".pptx", ".ppt", ".odp"}:
        return "presentation"
    if ext in {".xlsx", ".xls", ".ods"}:
        return "spreadsheet"
    if ext in EPUB_EXTENSIONS or ext == ".mobi":
        return "ebook"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in SUBTITLE_EXTENSIONS:
        return "subtitle_transcript"
    if ext in NOTEBOOK_EXTENSIONS:
        return "notebook"
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in TEXT_EXTENSIONS:
        return "text"
    if ext in OFFICE_XML_EXTENSIONS | LEGACY_OFFICE_EXTENSIONS:
        return "office"
    return "unknown"


def normalize_language_hint(language: str | None, default: str = "en") -> str:
    """Normalize user or caller language hints to KBPrep's supported codes."""
    if not language:
        return default
    normalized = language.strip().lower()
    if normalized in CHINESE_LANGUAGE_HINTS:
        return LANGUAGE_CHINESE
    if normalized in ENGLISH_LANGUAGE_HINTS:
        return LANGUAGE_ENGLISH
    return default


def detect_language_from_text(text: str) -> str:
    """Detect the dominant supported language from a text sample."""
    if not text.strip():
        return LANGUAGE_ENGLISH
    cjk_chars = len(CJK_RE.findall(text))
    latin_chars = len(LATIN_RE.findall(text))
    signal_chars = cjk_chars + latin_chars
    if signal_chars == 0:
        return LANGUAGE_ENGLISH
    if cjk_chars >= 3 and cjk_chars / signal_chars >= 0.2:
        return LANGUAGE_CHINESE
    return LANGUAGE_ENGLISH


def detect_language(file_path: str) -> str:
    """Detect a MinerU-compatible language hint from file content or name."""
    path = Path(file_path)
    if path.exists() and path.suffix.lower() == ".pdf":
        pdf_text = _sample_pdf_text(path)
        if pdf_text.strip():
            return detect_language_from_text(pdf_text)
    if path.exists() and path.suffix.lower() in TEXT_EXTENSIONS:
        text = _sample_text_file(path)
        if text.strip():
            return detect_language_from_text(text)
    return detect_language_from_text(path.stem)


def _sample_text_file(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return handle.read(65536)
    except OSError:
        return ""


def _sample_pdf_text(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ""
    try:
        doc = fitz.open(str(path))
    except Exception:
        return ""
    try:
        parts = [doc[index].get_text("text") for index in range(min(len(doc), 5))]
    finally:
        doc.close()
    return "\n".join(parts)
