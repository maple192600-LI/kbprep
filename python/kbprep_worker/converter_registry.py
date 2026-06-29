"""Declared conversion route selection for KBPrep.

The registry chooses a route from extension, MIME hints, and small content
signatures. Pipeline stages still execute the route and keep quality-gate
evidence centralized.
"""
from __future__ import annotations

import mimetypes
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .pdf_route_policy import selected_pdf_strategy
from .supported_formats import (
    DIRECT_EXTENSIONS,
    EPUB_EXTENSIONS,
    HTML_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MEDIA_EXTENSIONS,
    OFFICE_XML_EXTENSIONS,
    PDF_EXTENSIONS,
    URL_DESCRIPTOR_EXTENSIONS,
)
from .youtube_source import is_youtube_url, source_url_from_descriptor
from .zip_safety import ZipSafetyError, open_safe_zip


class ConversionRouteKind(str, Enum):
    DIRECT_TEXT = "direct_text"
    OFFICE_XML = "office_xml"
    EPUB_XHTML = "epub_xhtml"
    PDF_PYMUPDF4LLM = "pymupdf4llm"
    PDF_TEXT_LAYER = "pdf_text_layer"
    MINERU_OCR = "mineru_ocr"
    IMAGE_TO_PDF_OCR = "image_to_pdf_ocr"
    LEGACY_OFFICE_TO_PDF = "legacy_office_to_pdf"
    MEDIA_TRANSCRIPT = "media_transcript"
    YOUTUBE_TRANSCRIPT = "youtube_transcript"
    MEDIA_TRANSCRIPT_REQUIRED = "media_transcript_required"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ConversionRoute:
    kind: ConversionRouteKind
    converter: str
    conversion_strategy: str
    error_code: str = ""
    message: str = ""
    matched_converter: str = ""
    match_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileIdentity:
    path: Path | None
    extension: str
    mime_type: str
    signatures: tuple[str, ...]


@dataclass(frozen=True)
class ConverterRegistration:
    id: str
    kind: ConversionRouteKind
    priority: int
    extensions: tuple[str, ...]
    mime_types: tuple[str, ...] = ()
    signatures: tuple[str, ...] = ()
    converter: str = ""
    conversion_strategy: str = ""


def registered_converters() -> tuple[ConverterRegistration, ...]:
    return tuple(sorted(_REGISTRATIONS, key=lambda item: item.priority))


def file_identity_for_path(path: Path) -> FileIdentity:
    path = Path(path)
    return FileIdentity(
        path=path,
        extension=path.suffix.lower(),
        mime_type=mimetypes.guess_type(path.name)[0] or "",
        signatures=_sniff_signatures(path),
    )


def select_conversion_route(extension: str, diagnosis: dict, file_identity: FileIdentity | None = None) -> ConversionRoute:
    ext = (extension or "").lower()
    identity = file_identity or FileIdentity(path=None, extension=ext, mime_type=mimetypes.types_map.get(ext, ""), signatures=())
    evidence = _identity_evidence(identity)
    content_ext = _extension_from_signatures(identity.signatures)

    if ext in PDF_EXTENSIONS and identity.path and "pdf_header" not in identity.signatures:
        return _unsupported_route(ext, (*evidence, "extension_content_mismatch"))
    if ext and content_ext and ext not in _extensions_for_signature(content_ext):
        return _unsupported_route(ext, (*evidence, "extension_content_mismatch"))
    if not ext and content_ext:
        ext = content_ext
    if ext in URL_DESCRIPTOR_EXTENSIONS:
        return _youtube_or_unsupported_route(identity, evidence)

    strategy = selected_pdf_strategy(diagnosis) if ext in PDF_EXTENSIONS else str(diagnosis.get("conversion_strategy") or "")
    for registration in registered_converters():
        if not _registration_matches(registration, ext, identity):
            continue
        route_strategy = _strategy_for_registration(registration, strategy)
        if route_strategy is not None:
            return _route_from_registration(registration.id, route_strategy, evidence)
    return _unsupported_route(ext, evidence)


_REGISTRATIONS = (
    ConverterRegistration(
        id="direct_text",
        kind=ConversionRouteKind.DIRECT_TEXT,
        priority=10,
        extensions=tuple(sorted(DIRECT_EXTENSIONS)),
        mime_types=("text/html", "text/plain", "text/markdown", "application/json"),
        signatures=("html_signature",),
        converter="direct_text",
        conversion_strategy="direct_text",
    ),
    ConverterRegistration(
        id="office_xml",
        kind=ConversionRouteKind.OFFICE_XML,
        priority=20,
        extensions=tuple(sorted(OFFICE_XML_EXTENSIONS)),
        signatures=("office_content_types",),
        converter="office_xml",
        conversion_strategy="office_xml",
    ),
    ConverterRegistration(
        id="epub_xhtml",
        kind=ConversionRouteKind.EPUB_XHTML,
        priority=30,
        extensions=tuple(sorted(EPUB_EXTENSIONS)),
        signatures=("epub_mimetype",),
        converter="epub_xhtml",
        conversion_strategy="epub_xhtml",
    ),
    ConverterRegistration(
        id="pymupdf4llm",
        kind=ConversionRouteKind.PDF_PYMUPDF4LLM,
        priority=39,
        extensions=(".pdf",),
        mime_types=("application/pdf",),
        signatures=("pdf_header",),
        converter="pymupdf4llm",
        conversion_strategy="pymupdf4llm",
    ),
    ConverterRegistration(
        id="pdf_text_layer",
        kind=ConversionRouteKind.PDF_TEXT_LAYER,
        priority=40,
        extensions=(".pdf",),
        mime_types=("application/pdf",),
        signatures=("pdf_header",),
        converter="pdf_text_layer",
        conversion_strategy="pdf_text_layer",
    ),
    ConverterRegistration(
        id="mineru",
        kind=ConversionRouteKind.MINERU_OCR,
        priority=50,
        extensions=(".pdf",),
        mime_types=("application/pdf",),
        signatures=("pdf_header",),
        converter="mineru",
        conversion_strategy="mineru_ocr",
    ),
    ConverterRegistration(
        id="image_to_pdf_ocr",
        kind=ConversionRouteKind.IMAGE_TO_PDF_OCR,
        priority=60,
        extensions=tuple(sorted(IMAGE_EXTENSIONS)),
        converter="image_to_pdf_ocr",
        conversion_strategy="image_to_pdf_then_mineru_ocr",
    ),
    # Legacy Office (.doc/.ppt/.xls) is intentionally unsupported (owner declined
    # adaptation). No ConverterRegistration here, so select_conversion_route()
    # returns UNSUPPORTED for these extensions. The legacy bridge code in
    # converters/external_tools.py is kept but unreachable from normal routing.
    ConverterRegistration(
        id="media_transcript",
        kind=ConversionRouteKind.MEDIA_TRANSCRIPT,
        priority=80,
        extensions=tuple(sorted(MEDIA_EXTENSIONS)),
        converter="media_transcript",
        conversion_strategy="media_to_transcript",
    ),
)


def _sniff_signatures(path: Path) -> tuple[str, ...]:
    signatures: list[str] = []
    try:
        head = path.read_bytes()[:4096]
    except OSError:
        return ()
    if head.startswith(b"%PDF-"):
        signatures.append("pdf_header")
    lower = head.lower().lstrip()
    if lower.startswith((b"<!doctype html", b"<html")) or b"<html" in lower[:512]:
        signatures.append("html_signature")
    if zipfile.is_zipfile(path):
        try:
            with open_safe_zip(path) as archive:
                names = set(archive.namelist())
                if "mimetype" in names and archive.read_bytes("mimetype").strip() == b"application/epub+zip":
                    signatures.append("epub_mimetype")
                if "[Content_Types].xml" in names and any(name.startswith(("word/", "ppt/", "xl/")) for name in names):
                    signatures.append("office_content_types")
        except (OSError, zipfile.BadZipFile, KeyError, ZipSafetyError):
            pass
    return tuple(signatures)


def _identity_evidence(identity: FileIdentity) -> tuple[str, ...]:
    evidence: list[str] = []
    if identity.extension:
        evidence.append(f"extension:{identity.extension}")
    if identity.mime_type:
        evidence.append(f"mime:{identity.mime_type}")
    evidence.extend(identity.signatures)
    return tuple(evidence)


def _extension_from_signatures(signatures: tuple[str, ...]) -> str:
    if "pdf_header" in signatures:
        return ".pdf"
    if "office_content_types" in signatures:
        return ".docx"
    if "epub_mimetype" in signatures:
        return ".epub"
    if "html_signature" in signatures:
        return ".html"
    return ""


def _extensions_for_signature(extension: str) -> set[str]:
    if extension == ".docx":
        return set(OFFICE_XML_EXTENSIONS) | {""}
    if extension == ".html":
        return set(HTML_EXTENSIONS) | {""}
    if extension == ".epub":
        return set(EPUB_EXTENSIONS) | {""}
    if extension == ".pdf":
        return {".pdf", ""}
    return {extension}


def _registration_matches(registration: ConverterRegistration, ext: str, identity: FileIdentity) -> bool:
    if ext and ext in registration.extensions:
        return True
    if identity.mime_type and identity.mime_type in registration.mime_types:
        return True
    return bool(set(identity.signatures).intersection(registration.signatures))


def _strategy_for_registration(registration: ConverterRegistration, strategy: str) -> str | None:
    if registration.id == "pymupdf4llm":
        return "pymupdf4llm" if strategy == "pymupdf4llm" else None
    if registration.id == "pdf_text_layer":
        return "pdf_text_layer" if strategy == "pdf_text_layer" else None
    if registration.id == "mineru":
        if strategy in {"mineru_pipeline", "mineru_pipeline_ocr"}:
            return "mineru_ocr"
        allowed = {"", "mineru_txt", "mineru_ocr", "mineru_auto", "mineru_mixed_text_image"}
        return (strategy or registration.conversion_strategy) if strategy in allowed else None
    return registration.conversion_strategy


def _route_from_registration(registration_id: str, strategy: str, evidence: tuple[str, ...]) -> ConversionRoute:
    registration = next(item for item in _REGISTRATIONS if item.id == registration_id)
    return ConversionRoute(
        kind=registration.kind,
        converter=registration.converter,
        conversion_strategy=strategy or registration.conversion_strategy,
        matched_converter=registration.id,
        match_evidence=evidence,
    )


def _youtube_or_unsupported_route(identity: FileIdentity, evidence: tuple[str, ...]) -> ConversionRoute:
    if identity.path and is_youtube_url(source_url_from_descriptor(identity.path)):
        return ConversionRoute(
            kind=ConversionRouteKind.YOUTUBE_TRANSCRIPT,
            converter="youtube_transcript",
            conversion_strategy="youtube_subtitle_then_media_transcript",
            matched_converter="youtube_transcript",
            match_evidence=(*evidence, "youtube_url_descriptor"),
        )
    return _unsupported_route(identity.extension or ".url", (*evidence, "non_youtube_url_descriptor"))


def _unsupported_route(ext: str, evidence: tuple[str, ...]) -> ConversionRoute:
    return ConversionRoute(
        kind=ConversionRouteKind.UNSUPPORTED,
        converter="unsupported",
        conversion_strategy="unsupported_extension",
        error_code="E_UNSUPPORTED_TYPE",
        message=(
            f"{ext or '<none>'} is not supported by KBPrep's verified conversion routes. "
            "Convert it to EPUB, PDF, DOCX, PPTX, XLSX, Markdown, text, code, JSON, HTML, or a subtitle/transcript first."
        ),
        matched_converter="unsupported",
        match_evidence=evidence,
    )
