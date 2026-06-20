# 03 Deterministic Conversion Routing

## Purpose

Make every source kind choose one auditable default conversion route.

## Flowchart Mapping

This stage supports input inspection, unsupported exits, route selection, the PDF three-tier diagnostic route, and the PDF upgrade loop in the flowchart contract.

## Routing Rules

- Route selection is deterministic.
- Unsupported input stops before conversion.
- Missing dependencies produce clear errors.
- PDF uses the protected three-tier diagnostic route: Tier 1 `pymupdf4llm`, Tier 2 `mineru_txt` or `mineru_auto`, Tier 3 `mineru_ocr`.
- PDF can upgrade once after the first conversion attempt when the conversion quality gate rejects the result.
- Other routes do not silently cascade through multiple engines.
- Optional media and YouTube routes stay target or experimental until evidence promotes them.

## PDF Three-Tier Route

PDF routing is not a multi-engine race. The inspector chooses one initial route from recorded evidence:

| Tier | Route | Use when | Must record |
| --- | --- | --- | --- |
| Tier 1 | `pymupdf4llm` | Text layer is trusted and layout is simple. | text-layer trust, simple-layout evidence, dependency status |
| Tier 2 | `mineru_txt` or `mineru_auto` | Text layer is trusted but layout is complex: multi-column, table-heavy, image/text interleaving, slide-like, or reading-order risk. | layout complexity evidence, selected MinerU mode, dependency status |
| Tier 3 | `mineru_ocr` | Text layer is not trusted: scanned pages, garbled text, CID or ToUnicode risk, high image coverage, or embedded text must be superseded. | OCR trigger evidence, text-layer rejection reason, dependency status |

Required diagnostic signals:

- text-layer trust
- layout complexity
- image coverage
- table or multi-column structure when available
- CID, ToUnicode, replacement-character, private-use, or control-character risk when available
- large-PDF sampling strategy when sampling is used

Required PDF acceptance fixtures before promotion beyond `partial`:

- simple single-column PDF routes to Tier 1
- English simple text PDF routes to Tier 1 without Chinese-ratio false rejection
- multi-column paper routes to Tier 2
- table-heavy PDF routes to Tier 2
- scanned PDF routes to Tier 3
- CID or ToUnicode-damaged PDF routes to Tier 3

## Acceptance

- `diagnosis_report.json` records selected capability and dependency status.
- `conversion_report.json.route_decision` records declared route, selected PDF tier when relevant, actual route, fallback or upgrade, and reason.
- Capability status matches `docs/capability-matrix.md`.

## Risk And Rollback

Risk: implicit route fallback can hide bad conversion evidence.

Rollback: disable the new route or fallback and return the capability to partial, experimental, or unsupported status.
