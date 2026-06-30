# 02 Canonical IR Contract

## Purpose

Define the stable internal document model used after conversion and before cleanup.

## Flowchart Mapping

This stage supports the flowchart nodes for Canonical IR conversion, normalization, and structure indexing.

## Current Shipped Boundary

The current worker ships an implemented Canonical IR contract (YouTube/media/image optional routes remain partial, Wave 4). It writes
`canonical_ir/manifest.json`, `document_manifest.json`, a validated
`canonical_ir/typed_nodes.json` artifact, a validated
`canonical_ir/source_spans.json` artifact,
`canonical_ir/transformation_ledger.json`, and C2
`canonical_ir/relationships.json`, `canonical_ir/assets.json`, and
`canonical_ir/annotations.json` artifacts for conversion-phase Canonical IR
evidence.

The shipped typed-node slices cover heading, paragraph, list, table, code,
quote, formula, figure, metadata, and transcript cue nodes in source order.
`typed_nodes_available` is true only when that artifact validates.
`source_spans_available` is true only when every typed node has a matching
validated SourceSpan. The current SourceSpan artifact records converted
Markdown line ranges for every node and transcript cue timing when raw cue
evidence is available. SourceSpan evidence is schema-checked so arbitrary
non-empty evidence objects cannot pass the conversion gate. The SourceSpan
schema now accepts route-native precision records only when the corresponding
location fields are present: PDF page bounding boxes, DOCX paragraph/run
ranges, PPTX slide shape ids, XLSX cell ranges, and future YouTube cue ids.
The Office XML converter now emits that native evidence for PPTX slide shape
ids, DOCX paragraph/run ranges, and XLSX cell ranges, threading it through
`conversion_report.mineru_artifacts.native_source_spans` into the span writer,
which attaches the route-native precision only when the evidence overlaps a
typed node and its precision matches the span source kind. The MinerU OCR route
extracts block-level `bbox` + `page_idx` from its `content_list.json` and threads
those as `pdf_bbox` native evidence through the same channel (lines mapped 1-based
to align with typed nodes; page stored 1-based because the validator requires
page > 0). The PDF text-layer route still emits no native bbox evidence because
`page.get_text("text")` carries no coordinates and line normalization breaks bbox
alignment; it keeps converted-line precision and the coverage report lists
`pdf_bbox` as a missing native kind only on that route. When any route omits
native evidence, the writer keeps converted-line precision and the coverage
report lists the missing native precision kinds instead of fabricating
coordinates.
The manifest also embeds `coverage.report`, which records typed-node counts,
source-span counts, coverage ratio, span precision summaries,
TransformationLedger availability, and remaining target gaps. The conversion
gate rejects available-artifact claims when this coverage report is missing or
incomplete.
When the coverage report proves complete typed-node and source-span coverage,
the pre-clean conversion gate can evaluate text quality from typed-node text
before falling back to converter-provided quality or rendered `converted.md`.
Route-native fine-grained spans still depend on converters emitting that
evidence before they can be considered complete for every route. The
TransformationLedger currently records ordered conversion-phase evidence for
route decisions, converted Markdown, typed nodes, and source spans, and the
pre-clean conversion gate validates it when the manifest claims the artifact.
C2 relationships record content-safe `contains`, `next_sibling`, and
`references` structure links between typed-node ids; `references` links a
paragraph to an adjacent figure or table node. C2 assets record content-safe
image and table references from figure/table nodes, each carrying a
`source_path` and a `referenced_by` node-id list, without copying alt text,
title text, or table cell content. C2 annotations record the content-safe
coverage warning plus dynamic `quality_warning` annotations (for example
`W_EMPTY_HEADING`, `W_SHORT_PARAGRAPH`) targeted at specific typed-node ids.
The coverage report now marks these three gap areas as `partial` only when the
corresponding artifact has records, and each section also reports a
`distribution` of the record type/kind values; empty or missing artifacts
remain `target_work`. Remaining target work: route-native relationship
semantics that require source-structure containers without a typed-node id
(such as PPTX shape `embeds` or notes `annotates`), transcript speaker
segmentation, node-level `coverage_gap` annotations that depend on
source-kind-aware native precision gaps, and full Markdown regeneration
coverage.

This IR-contract deferral is a schema/completeness gap, **not** a current
PPTX deepening plan. Per `docs/development/format-strategy-decision.md`,
PPTX is lightweight only; the PPTX shape `embeds` and notes `annotates`
relationship semantics would be pursued only if the owner reopens PPTX
depth. The `transcript speaker_segment` deferral in the same list is
independent — it follows the media/transcript route, not PPTX strategy.

The standard Markdown render path now has a minimal IR regeneration slice:
when a valid `clean_view.json` and `canonical_ir/typed_nodes.json` are present,
`cleaned.md` defaults to Canonical IR node text in Clean View order, while
entries carrying accepted patch identity render from the accepted in-memory
cleanup block content. `cleaning_patches.jsonl` remains content-safe and does
not copy source text, cleaned text, or private rule bodies. This is not the
complete Canonical IR contract: route-native relationship semantics requiring
source-structure containers, transcript speaker segmentation, node-level
coverage-gap annotations, every output profile, and universal fact-layer usage
remain partial or target work. (Converter-native source-span extraction for
PPTX/DOCX/XLSX landed in C1R; PDF bbox via MinerU OCR `content_list` landed in
Wave 1; the PDF text-layer route still lacks a coordinate source and stays
converted-line only.)

## Contract

Canonical IR must include:

- `CanonicalDocument`
- `SourceSnapshot`
- `TypedNode`
- `SourceSpan`
- `Asset`
- `Relationship`
- `AnnotationSet`
- `TransformationLedger`

The contract must preserve source order, source evidence, asset links, and node identity.

## Acceptance

- Every converted source can identify the route that produced its IR.
- Every cleanup target can point back to a source span when the converter provides one.
- Rendered Markdown can be regenerated from IR plus accepted changes.

## Route-Wide Semantics

The C2 relationship, asset, and annotation artifacts carry route-wide semantics
on top of typed-node identity. The current shipped boundary is:

| Artifact | Shipped semantics | Deferred semantics |
| --- | --- | --- |
| relationships | `contains`, `next_sibling`, `references` (paragraph -> adjacent figure/table) | PPTX shape `embeds`, notes `annotates`, transcript `speaker_segment` (need source-structure containers without typed-node ids) |
| assets | image + table `asset_type`, `reference`, `reference_kind` (`markdown_image`, `inline_table`), `source_path`, `referenced_by` node-id list | `office_embed` `reference_kind` with original media part paths (needs `office_image_assets` threading), multi-route asset provenance |
| annotations | `coverage_warning` (regeneration gap), dynamic `quality_warning` (`W_EMPTY_HEADING`, `W_SHORT_PARAGRAPH`) targeted at typed-node ids | node-level `coverage_gap` (`W_NATIVE_PRECISION_MISSING`) for source-kind-aware native precision gaps |

All relationship, asset, and annotation records remain content-safe: they
reference typed-node ids and structural fields only, never source text, alt
text, title text, table cell content, or private rule bodies.

> Note: the PPTX `embeds`/`annotates` deferrals are IR schema gaps, not a
> current PPTX deepening plan (PPTX is lightweight per
> `format-strategy-decision.md`); they land only if the owner reopens PPTX
> depth. The `transcript speaker_segment` deferral follows the
> media/transcript route and is independent of PPTX strategy.

## Risk And Rollback

Risk: an unstable IR contract can break conversion, cleanup, render, and feedback at the same time.

Rollback: keep the existing conversion artifacts active while new IR artifacts run in parallel until tests prove equivalence.
