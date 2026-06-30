# Capability Matrix

The code-level source of truth is `python/kbprep_worker/converter_capabilities.py`.
This file is the reader-facing summary of those declarations and must not claim
a route that is absent from the registry.

The protected design may describe target capabilities. This matrix describes the
current implementation status.

Status values:

- `verified`: implemented and covered by named tests or fixtures
- `partial`: implemented with some named tests or fixtures, but known to miss important structure or lacks broad coverage
- `experimental`: route exists, but quality depends heavily on external tools or source quality
- `design_only`: target route is documented, but no current local CLI support is shipped
- `unsupported`: should be reported clearly instead of pretending success

| Capability ID | Source type | Current route | Status | Must preserve | Current evidence | Current risk |
| --- | --- | --- | --- | --- | --- | --- |
| markdown_text_direct | Markdown/text/table text | direct_text | verified | headings, paragraphs, tables, links, code-like details | `src/test/scenarios/worker-core-runtime-part2.test.ts::declares converter capabilities and exposes the chosen capability through diagnosis`; `src/test/scenarios/worker-quality-gates-part1.test.ts::reports source-to-converted integrity loss for text sources` | cleanup rules can still remove useful text if rules are too broad |
| html_direct | HTML | direct_text | partial | visible text, headings, lists, links, image references | `src/test/scenarios/worker-direct-content-part2.test.ts::converts a noisy HTML golden fixture while preserving method details`; `src/test/scenarios/worker-direct-content-part2.test.ts::converts local HTML, JSON, and CSV sources into readable Markdown` | navigation, footer, cookie, and ad wrappers need document-type cleanup rules |
| json_direct | JSON | direct_text | verified | keys, values, nesting where representable in Markdown | `src/test/scenarios/worker-direct-content-part2.test.ts::converts local HTML, JSON, and CSV sources into readable Markdown` | large machine JSON may be readable but not knowledge-friendly |
| code_direct | Code/config files | direct_code | verified | exact code, parameters, comments, link strings | `src/test/scenarios/worker-direct-content-part2.test.ts::converts GitHub-style source and config files as fenced Markdown without summarizing code` | code must be protected from prose cleanup |
| notebook_json | Jupyter notebooks | notebook_json | partial | markdown cells, code cells, cell order | `src/test/scenarios/worker-direct-content-part3.test.ts::converts Jupyter notebooks into readable Markdown cells with code and text outputs` | outputs, attachments, and rich display data need more fixtures |
| subtitle_transcript_direct | Subtitle/transcript files | direct_text | verified | utterance order, timestamps when present, speaker-like lines | `src/test/scenarios/worker-direct-content-part1.test.ts::normalizes local subtitle files into readable transcript markdown` | subtitle noise still needs transcript-specific cleanup |
| office_xml | Modern Office XML | office_xml | partial | DOCX: paragraph/run structure, heading levels, tables (incl. gridSpan/vMerge merged cells), embedded images, external hyperlinks, ordered/unordered lists, bold/italic/strike emphasis, docx_run_range source spans (priority target); PPTX: slide text/title/notes/readable outline (lightweight); XLSX: sheet names, simple tables, key text (lightweight) | `src/test/scenarios/worker-local-formats.test.ts::converts modern Office files through the local XML fallback when MinerU is unnecessary`; `python/tests/test_office_xml_converter.py` (DOCX hyperlink/list/merged-cell/char-style deepening; PPTX shape spans, notes slide, multi-slide order; XLSX cell-range spans, multi-sheet titles, empty-sheet skip, inline-string values) | Markdown has no native merged-cell/multi-paragraph-cell syntax (merged cells repeat values; multi-paragraph cells collapse to one line); DOCX headers/footers, footnotes, TOC intentionally out of scope; PPTX/XLSX lightweight per `docs/development/format-strategy-decision.md` (no charts/complex workbook work). |
| epub_xhtml | EPUB | epub_xhtml | partial | spine order, chapter headings, links, images when referenced, footnotes (EPUB2 anchor + EPUB3 epub:type noteref/footnote), complex tables (colspan/rowspan expansion) | `src/test/scenarios/worker-local-formats.test.ts::converts EPUB ebooks through local XHTML extraction instead of MinerU`; `python/tests/test_epub_converter.py::test_anchor_footnotes_render_as_markdown_footnotes`; `python/tests/test_epub_converter.py::test_complex_table_expands_colspan_and_rowspan`; `python/tests/test_epub_converter.py::test_epub_type_noteref_and_footnote_render_as_markdown_footnotes` | footnotes, complex tables, and epub:type semantics are covered at unit level; broader real EPUB fixtures still needed before verified promotion; per format-strategy-decision.md, EPUB defaults to direct XHTML parsing and is NOT routed through PDF; PDF is only a manual fallback when XHTML parsing quality is judged poor by the user. |
| pdf_diagnosis_selected | PDF | pdf_diagnosis_selected | verified | page order, trusted text-layer structure, layout evidence, OCR text when routed to MinerU, image evidence | `src/test/scenarios/worker-local-formats.test.ts::converts trusted simple PDFs through Tier 1 PyMuPDF4LLM`; `src/test/scenarios/worker-batch-long-docs-part2.test.ts::diagnoses text-layer, image-only, and PPT-like PDFs differently`; `src/test/scenarios/worker-pdf-routing-part2.test.ts::classifies the six Phase B public PDF acceptance shapes`; `src/test/scenarios/worker-pdf-routing-part2.test.ts::routes trusted multi-column PDFs through MinerU txt mode`; `src/test/scenarios/worker-pdf-routing-part2.test.ts::keeps gray-zone trusted PDFs on Tier 1 when noise is sparse`; `src/test/scenarios/worker-pdf-routing-part2.test.ts::falls back to MinerU when a trusted Tier 1 PDF conversion produces unreadable Markdown`; `src/test/scenarios/worker-pdf-routing.test.ts::routes image-only scanned PDFs through MinerU OCR and records the actual route`; `python/tests/test_pdf_route_diagnostics.py`; `python/tests/test_external_conversion.py`; `scripts/check-vault-pdf-phase-b.mjs` | route quality still depends on local dependency availability and source PDF quality; failed quality gates block publication |
| image_ocr | Image files | image_to_pdf_then_mineru_ocr | experimental | image text through MinerU OCR, conversion report evidence | `src/test/scenarios/worker-core-runtime-part2.test.ts::diagnoses local external-converter formats and keeps MOBI explicitly unsupported` | OCR quality depends on local MinerU and image quality; current tests mock the external OCR step |
| legacy_office_pdf_bridge | Legacy Office | unsupported | unsupported | n/a (intentionally out of scope; owner declined adaptation) | `src/test/scenarios/worker-core-runtime-part2.test.ts::diagnoses local external-converter formats and keeps MOBI explicitly unsupported` | Legacy Office inputs are rejected with explicit guidance; convert to PDF or modern Office (.docx/.pptx/.xlsx) first |
| media_local_transcript | Audio/video binaries | media_to_transcript | partial | transcript text, ASR command evidence, Whisper or Qwen3-ASR model metadata | `src/test/scenarios/worker-core-runtime-part2.test.ts::declares converter capabilities and exposes the chosen capability through diagnosis`; `src/test/scenarios/worker-core-runtime-part2.test.ts::proves optional media and YouTube routes with mocked golden fixtures`; `python/tests/test_external_tools.py::routes Chinese to Qwen3-ASR and English to Whisper`; `python/tests/test_external_tools.py::Qwen3-ASR provider mock inference + dependency gate`; `python/tests/test_media_asr_fixture.py::test_real_qwen3_asr_zh_transcript_fixture_is_version_controlled` | Dual-track ASR (Chinese Qwen3-ASR-1.7B / English Whisper large-v3) runs GPU in the single kbprep venv (torch stays 2.8.0+cu126); real zh audio fixture (90s) via qwen3-asr on cuda:0/bfloat16 + en sample via Whisper large-v3 (dual-track manual acceptance); transcript text enters cleanup and final outputs; quality gates pass with 0 strict errors; reproducible version-controlled zh fixture now ships (python/tests/golden/formats/media/transcript_zh_90s.txt, 689-character zh transcript via Qwen3-ASR-1.7B on RTX 4060 Ti); status stays partial until deterministic or cross-sample ASR evidence supports verified promotion |
| youtube_url_routes | YouTube URLs, `.url` descriptors, and explicit playlist input | youtube_subtitle_then_media_transcript | partial | subtitle order, transcript text, source URL evidence, subtitle inventory/language evidence, Python-library media download fallback, per-video playlist status | `src/test/scenarios/worker-core-runtime-part2.test.ts::proves optional media and YouTube routes with mocked golden fixtures`; `src/adapters/standalone/cli.test.ts::maps accepted YouTube URL shapes to stable local descriptors`; `src/adapters/standalone/cli.test.ts::maps explicit YouTube playlist input to the Python prepare_batch worker command`; `python/tests/test_media_youtube_routes.py::TestMediaYoutubeRoute::test_youtube_source_accepts_documented_url_shapes`; `python/tests/test_media_youtube_routes.py::TestMediaYoutubeRoute::test_youtube_source_reads_source_url_and_descriptor_shapes`; `python/tests/test_media_youtube_routes.py::TestMediaYoutubeRoute::test_youtube_subtitle_report_records_inventory_language_and_artifacts`; `python/tests/test_media_youtube_routes.py::TestMediaYoutubeRoute::test_youtube_no_subtitle_fallback_uses_python_download_library`; `python/tests/test_media_youtube_routes.py::TestMediaYoutubeRoute::test_youtube_playlist_expands_to_bounded_local_descriptors`; `python/tests/test_batch_status_manifest.py::BatchStatusManifestTests::test_playlist_batch_expands_to_youtube_child_jobs_with_parent_status`; `python/tests/test_batch_status_manifest.py::BatchStatusManifestTests::test_playlist_batch_rerun_preserves_playlist_source_collection_evidence`; `python/tests/test_youtube_subtitle_fixture.py::test_real_youtube_subtitle_fixture_is_version_controlled` | URL and playlist processing depend on accepted URL shapes, network timeout handling, subtitle availability, the `yt-dlp` Python package, local transcription dependencies, transcript quality, and final quality gates; current evidence includes recorded-equivalent subtitle inventory/report-contract coverage plus mocked Python-library media fallback fixtures, mocked playlist expansion, playlist rerun evidence checks, and URL-shape contract tests, so this is not verified real YouTube support. |
| mobi_unsupported | MOBI ebooks | unsupported | unsupported | n/a | `src/test/scenarios/worker-core-runtime-part2.test.ts::diagnoses local external-converter formats and keeps MOBI explicitly unsupported` | MOBI inputs are rejected with explicit guidance; convert MOBI to EPUB, PDF, Markdown, or text first |

## Target Architecture Fit

The target architecture routes every supported source into Canonical IR, checks
conversion quality before cleanup, and publishes a complete source-side
deliverable only after hard gates pass. Current capability status below must be
read as implementation evidence, not design ambition.

## Next Required Work

Every `diagnose` result and every `diagnosis_report.json` now records the
selected `capability`, including route, status, dependencies, fallback,
preserved structures, test evidence, risk, and reason.

Every successful conversion also writes `conversion_report.json.route_decision`.
That record compares the declared capability route with the actual converter
used for this run, including the selected PDF tier, diagnosed strategy, actual
route, `fallback_applied`, `fallback_from`, and `fallback_to`. For example, a
PDF can be declared as `pdf_diagnosis_selected`, selected as Tier 1
`pymupdf4llm`, then record an actual route of `mineru_ocr` if the converted
Markdown was rejected as unreadable.

`python/kbprep_worker/converter_capabilities.py` also exposes
`capability_gap_report()`. That machine-readable report lists every non-verified
route with its current status, current route, required evidence, and promotion
blocker. Package checks validate that every non-verified capability appears in
this gap report, so new file routes cannot silently imply full support before
fixtures prove them.

1. Add real image OCR, media ASR, and real-network YouTube subtitle/fallback/playlist fixtures before promoting partial or experimental routes to verified. Legacy Office is intentionally unsupported (owner declined adaptation).
2. Keep MOBI explicitly unsupported unless the project owner later reopens that scope.
