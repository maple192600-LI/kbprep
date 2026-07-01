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
    URL_DESCRIPTOR_EXTENSIONS,
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
MEDIA_YOUTUBE_EVIDENCE = f"{CORE_RUNTIME_PART2}::proves optional media and YouTube routes with mocked golden fixtures"

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
            (
                "broader real-world DOCX samples covering nested lists, complex tables, "
                "and multi-run styled paragraphs before DOCX verified promotion"
            ),
            (
                "PPTX/XLSX lightweight fixtures (slide notes order, simple sheet tables) "
                "— no charts or complex workbook semantics per format strategy"
            ),
        ],
        "promotion_blocker": (
            "DOCX structure fidelity is deepened (external hyperlinks, ordered/unordered lists, "
            "gridSpan/vMerge merged cells, bold/italic/strike emphasis) but stays partial until "
            "broader real-world DOCX samples prove preservation; PPTX and XLSX are intentionally "
            "lightweight per docs/development/format-strategy-decision.md (no charts or complex workbook work)."
        ),
        "preserves": [
            "DOCX: paragraph/run structure, heading levels, tables with gridSpan/vMerge merged cells, "
            "embedded images, external hyperlinks, ordered/unordered lists, bold/italic/strike emphasis, docx_run_range source spans",
            "PPTX: slide order, shape text, titles, speaker notes, readable outline (lightweight)",
            "XLSX: sheet names, simple tables, key text (lightweight)",
        ],
        "risk": (
            "Markdown has no native merged-cell or multi-paragraph-cell syntax, so merged cells repeat "
            "values and multi-paragraph cells collapse to one line; DOCX headers/footers, footnotes, "
            "and TOC are intentionally out of scope; PPTX/XLSX stay lightweight by strategy."
        ),
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
        "route": "unsupported",
        "dependencies": [],
        "fallback": "Convert legacy Office files to PDF or modern Office (.docx/.pptx/.xlsx) before running KBPrep.",
        "status": "unsupported",
        "test_evidence": [
            EXTERNAL_FORMATS_EVIDENCE,
        ],
        "required_evidence": [],
        "promotion_blocker": (
            "Legacy Office is intentionally out of scope (owner declined this adaptation). "
            "Convert to PDF or modern Office first."
        ),
        "preserves": [],
        "risk": "Legacy Office inputs are rejected with explicit guidance instead of being silently converted.",
    },
    {
        "id": "media_local_transcript",
        "source_type": "generic_block",
        "extensions": sorted(AUDIO_EXTENSIONS | VIDEO_EXTENSIONS),
        "route": "media_to_transcript",
        "dependencies": ["ffmpeg", "qwen3-asr (zh route, cuda:0/bfloat16)", "local Whisper CLI (en route)"],
        "fallback": "Install ffmpeg and Whisper locally, or provide .srt, .vtt, .ass, .lrc, .txt, or .md transcript.",
        "status": "verified",
        "test_evidence": [
            CAPABILITY_DIAGNOSIS_EVIDENCE,
            MEDIA_YOUTUBE_EVIDENCE,
        ],
        "real_fixture_evidence": (
            "Real 90s zh audio (YouTube video 3DlXq9nsQOE, public) transcribed via "
            "qwen3-asr Qwen3-ASR-1.7B (cuda:0/bfloat16, RTX 4060 Ti); a reproducible "
            "version-controlled fixture ships at python/tests/golden/formats/media/"
            "transcript_zh_90s.txt and is content-hash locked (see "
            "python/tests/test_media_asr_fixture.py FIXTURE_SHA256) so any silent drift "
            "fails CI until the fixture is regenerated deliberately. English Whisper "
            "large-v3 route also passed manual acceptance (see "
            "docs/development/asr-dual-track-acceptance.md)."
        ),
        "preserves": ["transcript text", "ASR command evidence", "Whisper model metadata"],
        "risk": (
            "ASR quality and runtime depend on local qwen3-asr/Whisper model and media quality; "
            "batch processing still excludes media by default."
        ),
    },
    {
        "id": "youtube_url_routes",
        "source_type": "remote_url",
        "extensions": sorted(URL_DESCRIPTOR_EXTENSIONS),
        "route": "youtube_subtitle_then_media_transcript",
        "dependencies": ["yt-dlp subtitle route", "yt-dlp Python package media fallback", "ffmpeg and local Whisper CLI"],
        "fallback": (
            "Download or export a local subtitle, transcript, Markdown, text, PDF, "
            "or media file before running KBPrep."
        ),
        "status": "partial",
        "test_evidence": [
            MEDIA_YOUTUBE_EVIDENCE,
        ],
        "required_evidence": [
            "documented YouTube URL technical contract",
            "subtitle-first golden fixtures",
            "fallback transcript fixtures",
            "direct CLI URL input tests",
            "playlist expansion and child status tests",
            "playlist rerun source-collection evidence tests",
            "real YouTube subtitle export fixture",
            "real YouTube playlist expansion fixture",
            "real fallback media transcript acceptance evidence",
            "dependency failure and no-network tests",
        ],
        "promotion_blocker": (
            "Direct URL, explicit video id, local .url descriptor routing, playlist expansion, and playlist rerun evidence "
            "are covered with mocked fixtures; "
            "verified promotion needs real subtitle/fallback/playlist fixtures, dependency variance, timeout handling, "
            "and final quality-gate evidence."
        ),
        "preserves": ["subtitle order", "transcript text", "source URL evidence", "per-video playlist status"],
        "risk": (
            "URL and playlist processing depend on accepted URL shapes, network timeout handling, subtitle availability, "
            "external dependencies, transcript quality, and final quality gates; it remains partial."
        ),
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
        return ["documented technical route design", "subtitle-first fixtures", "dependency failure tests"]
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
