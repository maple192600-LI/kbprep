"""Declared conversion capabilities for KBPrep.

This registry is deliberately conservative: it describes what the current
pipeline routes through, not what every source format can be guaranteed to
preserve perfectly.
"""

from __future__ import annotations

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
    PDF_EXTENSIONS,
    PLAIN_TEXT_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    TABLE_TEXT_EXTENSIONS,
    VIDEO_EXTENSIONS,
)

Capability = dict[str, object]

CORE_RUNTIME_PART2 = "src/test/scenarios/worker-core-runtime-part2.test.ts"
EXTERNAL_FORMATS_EVIDENCE = (
    f"{CORE_RUNTIME_PART2}::diagnoses local external-converter formats and keeps MOBI explicitly unsupported"
)
CAPABILITY_DIAGNOSIS_EVIDENCE = (
    f"{CORE_RUNTIME_PART2}::declares converter capabilities and exposes the chosen capability through diagnosis"
)

_CAPABILITIES: tuple[Capability, ...] = (
    {
        "id": "markdown_text_direct",
        "source_type": "markdown_note",
        "extensions": sorted(MARKDOWN_EXTENSIONS | PLAIN_TEXT_EXTENSIONS | TABLE_TEXT_EXTENSIONS),
        "route": "direct_text",
        "dependencies": [],
        "fallback": None,
        "status": "verified",
        "test_evidence": [
            "src/test/scenarios/worker-core-runtime-part2.test.ts::declares converter capabilities and exposes the chosen capability through diagnosis",  # noqa: E501
            "src/test/scenarios/worker-quality-gates-part1.test.ts::reports source-to-converted integrity loss for text sources",
        ],
        "preserves": ["headings", "paragraphs", "tables", "links", "code-like details"],
        "risk": "cleanup rules can still remove useful text if rules are too broad",
    },
    {
        "id": "html_direct",
        "source_type": "generic_block",
        "extensions": sorted(HTML_EXTENSIONS),
        "route": "direct_text",
        "dependencies": ["beautifulsoup4", "lxml", "python html.parser fallback"],
        "fallback": None,
        "status": "partial",
        "test_evidence": [
            "src/test/scenarios/worker-direct-content-part2.test.ts::converts a noisy HTML golden fixture while preserving method details",
            "src/test/scenarios/worker-direct-content-part2.test.ts::converts local HTML, JSON, and CSV sources into readable Markdown",
        ],
        "required_evidence": [
            "golden HTML fixtures with navigation/footer/cookie noise and body preservation checks",
            "source-to-converted structure comparison for headings, links, images, and lists",
        ],
        "promotion_blocker": "Needs golden fixtures for noisy webpages before this route can be marked verified.",
        "preserves": ["visible text", "headings", "lists", "links", "image references"],
        "risk": "navigation, footer, cookie, and ad wrappers need document-type cleanup rules",
    },
    {
        "id": "json_direct",
        "source_type": "generic_block",
        "extensions": sorted(JSON_EXTENSIONS),
        "route": "direct_text",
        "dependencies": ["python json"],
        "fallback": None,
        "status": "verified",
        "test_evidence": [
            "src/test/scenarios/worker-direct-content-part2.test.ts::converts local HTML, JSON, and CSV sources into readable Markdown",
        ],
        "preserves": ["keys", "values", "nesting where representable in Markdown"],
        "risk": "large machine JSON may be readable but not knowledge-friendly",
    },
    {
        "id": "code_direct",
        "source_type": "generic_block",
        "extensions": sorted(CODE_EXTENSIONS),
        "route": "direct_code",
        "dependencies": [],
        "fallback": None,
        "status": "verified",
        "test_evidence": [
            "src/test/scenarios/worker-direct-content-part2.test.ts::converts GitHub-style source and config files as fenced Markdown without summarizing code",  # noqa: E501
        ],
        "preserves": ["exact code", "parameters", "comments", "URLs"],
        "risk": "code must be protected from prose cleanup",
    },
    {
        "id": "notebook_json",
        "source_type": "generic_block",
        "extensions": sorted(NOTEBOOK_EXTENSIONS),
        "route": "notebook_json",
        "dependencies": ["python json"],
        "fallback": None,
        "status": "partial",
        "test_evidence": [
            "src/test/scenarios/worker-direct-content-part3.test.ts::converts Jupyter notebooks into readable Markdown cells with code and text outputs",  # noqa: E501
        ],
        "required_evidence": [
            "golden notebooks with markdown cells, code cells, text outputs, rich display outputs, and attachments",
            "cell-order and output-retention assertions",
        ],
        "promotion_blocker": "Needs notebook fixtures beyond simple text/code cells before this route can be marked verified.",
        "preserves": ["markdown cells", "code cells", "cell order"],
        "risk": "outputs, attachments, and rich display data need more fixtures",
    },
    {
        "id": "subtitle_transcript_direct",
        "source_type": "subtitle_transcript",
        "extensions": sorted(SUBTITLE_EXTENSIONS),
        "route": "direct_text",
        "dependencies": [],
        "fallback": None,
        "status": "verified",
        "test_evidence": [
            "src/test/scenarios/worker-direct-content-part1.test.ts::normalizes local subtitle files into readable transcript markdown",
        ],
        "preserves": ["utterance order", "timestamps when present", "speaker-like lines"],
        "risk": "subtitle noise still needs transcript-specific cleanup",
    },
    {
        "id": "office_xml",
        "source_type": "pdf_like",
        "extensions": sorted(OFFICE_XML_EXTENSIONS),
        "route": "office_xml",
        "dependencies": ["python zipfile", "Office Open XML package structure"],
        "fallback": None,
        "status": "partial",
        "test_evidence": [
            "src/test/scenarios/worker-local-formats.test.ts::converts modern Office files through the local XML fallback when MinerU is unnecessary",  # noqa: E501
        ],
        "required_evidence": [
            "golden DOCX, PPTX, and XLSX fixtures with headings, tables, slides, sheets, embedded images, and charts",
            "layout-loss and sheet/slide-order assertions",
        ],
        "promotion_blocker": "Needs broader Office XML golden fixtures, especially charts and complex workbooks.",
        "preserves": ["document text", "slide order", "sheet/table text", "embedded images when extractable"],
        "risk": "layout fidelity, charts, and complex workbook semantics are not fully proven",
    },
    {
        "id": "epub_xhtml",
        "source_type": "pdf_like",
        "extensions": sorted(EPUB_EXTENSIONS),
        "route": "epub_xhtml",
        "dependencies": ["python zipfile", "EPUB spine metadata"],
        "fallback": None,
        "status": "partial",
        "test_evidence": [
            "src/test/scenarios/worker-local-formats.test.ts::converts EPUB ebooks through local XHTML extraction instead of MinerU",
        ],
        "required_evidence": [
            "golden EPUB fixtures with footnotes, complex tables, nested XHTML, spine ordering, links, and image assets",
            "chapter-order and footnote/table preservation assertions",
        ],
        "promotion_blocker": "Needs richer EPUB golden fixtures before this route can be marked verified.",
        "preserves": ["spine order", "chapter headings", "links", "images when referenced"],
        "risk": "footnotes, complex tables, and custom XHTML need more fixtures",
    },
    {
        "id": "pdf_diagnosis_selected",
        "source_type": "pdf_like",
        "extensions": sorted(PDF_EXTENSIONS),
        "route": "pdf_diagnosis_selected",
        "dependencies": [
            "PyMuPDF for diagnosis",
            "pymupdf4llm for trusted simple text-layer PDFs",
            "MinerU/OCR runtime when needed",
        ],
        "fallback": "mineru_ocr when text layer is missing, untrusted, image-heavy, or rejected after conversion",
        "status": "verified",
        "test_evidence": [
            "src/test/scenarios/worker-local-formats.test.ts::converts trusted simple PDFs through Tier 1 PyMuPDF4LLM",  # noqa: E501
            "src/test/scenarios/worker-batch-long-docs-part2.test.ts::diagnoses text-layer, image-only, and PPT-like PDFs differently",  # noqa: E501
            "src/test/scenarios/worker-pdf-routing-part2.test.ts::classifies the six Phase B public PDF acceptance shapes",
            "src/test/scenarios/worker-pdf-routing-part2.test.ts::routes trusted multi-column PDFs through MinerU txt mode",
            "src/test/scenarios/worker-pdf-routing-part2.test.ts::keeps gray-zone trusted PDFs on Tier 1 when noise is sparse",
            "src/test/scenarios/worker-pdf-routing-part2.test.ts::falls back to MinerU when a trusted Tier 1 PDF conversion produces unreadable Markdown",  # noqa: E501
            "src/test/scenarios/worker-pdf-routing.test.ts::routes image-only scanned PDFs through MinerU OCR and records the actual route",
        ],
        "preserves": [
            "page order",
            "trusted text-layer structure",
            "layout evidence",
            "OCR text when routed to MinerU",
            "image evidence",
        ],
        "risk": (
            "route quality still depends on local dependency availability and source PDF quality; "
            "failed quality gates block publication"
        ),
    },
    {
        "id": "image_ocr",
        "source_type": "pdf_like",
        "extensions": sorted(IMAGE_EXTENSIONS),
        "route": "image_to_pdf_then_mineru_ocr",
        "dependencies": ["PyMuPDF", "MinerU/OCR runtime"],
        "fallback": "If PyMuPDF or MinerU is missing, install the local KBPrep runtime dependencies before processing images.",
        "status": "experimental",
        "test_evidence": [
            EXTERNAL_FORMATS_EVIDENCE,
        ],
        "required_evidence": [
            "golden PNG/JPG/SVG fixtures with OCR text-retention checks",
            "real MinerU OCR acceptance run proving image text is preserved before verified promotion",
        ],
        "promotion_blocker": "Needs real image OCR golden fixtures before this route can be marked verified.",
        "preserves": ["image text through MinerU OCR", "conversion report evidence"],
        "risk": "OCR quality depends on local MinerU and image quality; current tests mock the external OCR step.",
    },
    {
        "id": "legacy_office_pdf_bridge",
        "source_type": "pdf_like",
        "extensions": sorted(LEGACY_OFFICE_EXTENSIONS),
        "route": "legacy_office_to_pdf_route",
        "dependencies": ["LibreOffice headless", "PDF diagnosis route"],
        "fallback": "Install LibreOffice locally, or convert legacy Office files to PDF/DOCX/PPTX/XLSX first.",
        "status": "experimental",
        "test_evidence": [
            EXTERNAL_FORMATS_EVIDENCE,
        ],
        "required_evidence": [
            "golden DOC/PPT/XLS fixtures with LibreOffice conversion and PDF route evidence",
            "source-to-Markdown integrity checks for text, tables, slides, and embedded images",
        ],
        "promotion_blocker": "Needs real legacy Office golden fixtures before this route can be marked verified.",
        "preserves": ["LibreOffice-generated PDF evidence", "downstream PDF route quality checks"],
        "risk": "LibreOffice conversion can lose layout or embedded objects; KBPrep records the generated PDF route for audit.",
    },
    {
        "id": "media_local_transcript",
        "source_type": "generic_block",
        "extensions": sorted(AUDIO_EXTENSIONS | VIDEO_EXTENSIONS),
        "route": "media_to_transcript",
        "dependencies": ["ffmpeg", "local Whisper CLI"],
        "fallback": "Install ffmpeg and Whisper locally, or provide .srt, .vtt, .ass, .lrc, .txt, or .md transcript.",
        "status": "experimental",
        "test_evidence": [
            CAPABILITY_DIAGNOSIS_EVIDENCE,
        ],
        "required_evidence": [
            "golden MP3/MP4 fixtures with stable transcript snapshots",
            "quality gate checks proving transcript text enters cleanup and final outputs",
        ],
        "promotion_blocker": "Needs real local ASR fixtures and timing evidence before this route can be marked verified.",
        "preserves": ["transcript text", "ASR command evidence", "Whisper model metadata"],
        "risk": (
            "ASR quality and runtime depend on local Whisper model and media quality; "
            "batch processing still excludes media by default."
        ),
    },
    {
        "id": "youtube_url_routes",
        "source_type": "remote_url",
        "extensions": [],
        "route": "unsupported",
        "dependencies": ["target-only: subtitle fetcher", "target-only: media transcript fallback"],
        "fallback": (
            "Download or export a local subtitle, transcript, Markdown, text, PDF, "
            "or media file before running KBPrep."
        ),
        "status": "design_only",
        "test_evidence": [],
        "required_evidence": [
            "owner-approved YouTube URL input contract",
            "subtitle-first golden fixtures",
            "fallback transcript fixtures",
            "dependency failure and no-network tests",
        ],
        "promotion_blocker": (
            "No standalone CLI URL route, subtitle extraction, media download, or verified fixture support is shipped."
        ),
        "preserves": ["target: subtitle order", "target: transcript text", "target: source URL evidence"],
        "risk": "URL processing can create network, copyright, dependency, and quality risks; it stays target-only.",
    },
    {
        "id": "mobi_unsupported",
        "source_type": "pdf_like",
        "extensions": [".mobi"],
        "route": "unsupported",
        "dependencies": [],
        "fallback": "Convert MOBI to EPUB, PDF, Markdown, or text before running KBPrep.",
        "status": "unsupported",
        "test_evidence": [
            EXTERNAL_FORMATS_EVIDENCE,
        ],
        "required_evidence": [
            "none for current scope; MOBI is intentionally outside this implementation",
        ],
        "promotion_blocker": "MOBI is intentionally out of scope because current ebook workflows should use EPUB/PDF/text.",
        "preserves": [],
        "risk": "MOBI inputs are rejected with explicit guidance instead of being silently converted.",
    },
)


def capability_matrix_rows() -> list[Capability]:
    return [dict(capability) for capability in _CAPABILITIES]


def capability_gap_report() -> dict:
    gaps = []
    summary = {"verified": 0, "partial": 0, "unsupported": 0, "experimental": 0, "design_only": 0}
    for capability in _CAPABILITIES:
        status = str(capability.get("status", "unsupported"))
        if status in summary:
            summary[status] += 1
        if status == "verified":
            continue
        gaps.append({
            "id": capability.get("id"),
            "current_status": status,
            "current_route": capability.get("route"),
            "extensions": capability.get("extensions", []),
            "risk": capability.get("risk", ""),
            "promotion_blocker": capability.get("promotion_blocker") or _default_promotion_blocker(capability),
            "required_evidence": capability.get("required_evidence") or _default_required_evidence(capability),
            "test_evidence": capability.get("test_evidence", []),
        })
    return {
        "schema": "kbprep.capability_gap_report.v1",
        "summary": summary,
        "gaps": gaps,
    }


def _default_promotion_blocker(capability: Capability) -> str:
    status = capability.get("status")
    if status == "partial":
        return "Needs broader golden fixtures and preservation checks before being marked verified."
    if status == "design_only":
        return "Target-only until a reliable route, dependency boundary, and end-to-end fixtures exist."
    return "Unsupported until a reliable conversion route and end-to-end fixtures exist."


def _default_required_evidence(capability: Capability) -> list[str]:
    status = capability.get("status")
    if status == "partial":
        return ["golden fixtures", "source-to-Markdown preservation checks"]
    if status == "design_only":
        return ["owner-approved route design", "subtitle-first fixtures", "dependency failure tests"]
    return ["explicit dependency/conversion route", "end-to-end fixture proving safe Markdown output"]


def get_capability_for_extension(extension: str) -> Capability:
    ext = extension.lower()
    for capability in _CAPABILITIES:
        extensions = capability.get("extensions", [])
        if isinstance(extensions, list) and ext in extensions:
            selected = dict(capability)
            selected["reason"] = f"Extension {ext} matched capability {capability['id']}."
            return selected
    return {
        "id": "unsupported_extension",
        "source_type": "generic_block",
        "extensions": [ext] if ext else [],
        "route": "unsupported",
        "dependencies": [],
        "fallback": None,
        "status": "unsupported",
        "test_evidence": [],
        "preserves": [],
        "risk": "No declared conversion route for this extension.",
        "reason": f"Extension {ext or '<none>'} has no declared KBPrep conversion capability.",
    }
