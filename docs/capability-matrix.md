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
- `unsupported`: should be reported clearly instead of pretending success

| Capability ID | Source type | Current route | Status | Must preserve | Current evidence | Current risk |
| --- | --- | --- | --- | --- | --- | --- |
| markdown_text_direct | Markdown/text/table text | direct_text | verified | headings, paragraphs, tables, links, code-like details | `src/test/scenarios/worker-core-runtime-part2.test.ts::declares converter capabilities and exposes the chosen capability through diagnosis`; `src/test/scenarios/worker-quality-gates-part1.test.ts::reports source-to-converted integrity loss for text sources` | cleanup rules can still remove useful text if rules are too broad |
| html_direct | HTML | direct_text | partial | visible text, headings, lists, links, image references | `src/test/scenarios/worker-direct-content-part2.test.ts::converts a noisy HTML golden fixture while preserving method details`; `src/test/scenarios/worker-direct-content-part2.test.ts::converts local HTML, JSON, and CSV sources into readable Markdown` | navigation, footer, cookie, and ad wrappers need document-type cleanup rules |
| json_direct | JSON | direct_text | verified | keys, values, nesting where representable in Markdown | `src/test/scenarios/worker-direct-content-part2.test.ts::converts local HTML, JSON, and CSV sources into readable Markdown` | large machine JSON may be readable but not knowledge-friendly |
| code_direct | Code/config files | direct_code | verified | exact code, parameters, comments, link strings | `src/test/scenarios/worker-direct-content-part2.test.ts::converts GitHub-style source and config files as fenced Markdown without summarizing code` | code must be protected from prose cleanup |
| notebook_json | Jupyter notebooks | notebook_json | partial | markdown cells, code cells, cell order | `src/test/scenarios/worker-direct-content-part3.test.ts::converts Jupyter notebooks into readable Markdown cells with code and text outputs` | outputs, attachments, and rich display data need more fixtures |
| subtitle_transcript_direct | Subtitle/transcript files | direct_text | verified | utterance order, timestamps when present, speaker-like lines | `src/test/scenarios/worker-direct-content-part1.test.ts::normalizes local subtitle files into readable transcript markdown` | subtitle noise still needs transcript-specific cleanup |
| office_xml | Modern Office XML | office_xml | partial | document text, slide order, sheet/table text, embedded images when extractable | `src/test/scenarios/worker-local-formats.test.ts::converts modern Office files through the local XML fallback when MinerU is unnecessary` | layout fidelity, charts, and complex workbook semantics are not fully proven |
| epub_xhtml | EPUB | epub_xhtml | partial | spine order, chapter headings, links, images when referenced | `src/test/scenarios/worker-local-formats.test.ts::converts EPUB ebooks through local XHTML extraction instead of MinerU` | footnotes, complex tables, and custom XHTML need more fixtures |
| pdf_diagnosis_selected | PDF | pdf_diagnosis_selected | partial | page order, text layer where trusted, layout evidence, OCR text when routed to MinerU, image evidence | `src/test/scenarios/worker-local-formats.test.ts::converts trusted text-layer PDFs without invoking MinerU`; `src/test/scenarios/worker-pdf-routing.test.ts::falls back to MinerU when a trusted PDF text-layer conversion produces unreadable Markdown`; `src/test/scenarios/worker-pdf-routing.test.ts::routes image-only scanned PDFs through MinerU OCR and records the actual route` | protected target is three-tier PDF routing: Tier 1 `pymupdf4llm`, Tier 2 `mineru_txt` or `mineru_auto`, Tier 3 `mineru_ocr`; current implementation is partial until those tiers and named fixtures are complete |
| image_ocr | Image files | image_to_pdf_then_mineru_ocr | experimental | image text through MinerU OCR, conversion report evidence | `src/test/scenarios/worker-core-runtime-part2.test.ts::diagnoses local external-converter formats and keeps MOBI explicitly unsupported` | OCR quality depends on local MinerU and image quality; current tests mock the external OCR step |
| legacy_office_pdf_bridge | Legacy Office | legacy_office_to_pdf_route | experimental | LibreOffice-generated PDF evidence, downstream PDF route quality checks | `src/test/scenarios/worker-core-runtime-part2.test.ts::diagnoses local external-converter formats and keeps MOBI explicitly unsupported` | LibreOffice conversion can lose layout or embedded objects; KBPrep records the generated PDF route for audit |
| media_local_transcript | Audio/video binaries | media_to_transcript | experimental | transcript text, ASR command evidence, Whisper model metadata | `src/test/scenarios/worker-core-runtime-part2.test.ts::declares converter capabilities and exposes the chosen capability through diagnosis` | ASR quality and runtime depend on local Whisper model and media quality; batch processing still excludes media by default |
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
used for this run, including the diagnosed strategy, actual route,
`fallback_applied`, `fallback_from`, and `fallback_to`. For example, a PDF can
be declared as `pdf_diagnosis_selected`, diagnosed as `pdf_text_layer`, then
record an actual route of `mineru_ocr` if the text layer was rejected after
conversion.

`python/kbprep_worker/converter_capabilities.py` also exposes
`capability_gap_report()`. That machine-readable report lists every non-verified
route with its current status, current route, required evidence, and promotion
blocker. Package checks validate that every `partial` or `unsupported`
capability appears in this gap report, so new file routes cannot silently imply
full support before fixtures prove them.

1. Add golden fixtures for every `partial` route before promoting it to `verified`, including PDF Tier 1 simple single-column and English text fixtures, Tier 2 multi-column and table-heavy fixtures, and Tier 3 scanned plus CID or ToUnicode-damaged fixtures.
2. Add real image OCR, legacy Office, and media ASR fixtures before promoting experimental routes.
3. Keep MOBI explicitly unsupported unless the project owner later reopens that scope.
