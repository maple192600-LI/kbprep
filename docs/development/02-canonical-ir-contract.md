# 02 Canonical IR Contract

## Purpose

Define the stable internal document model used after conversion and before cleanup.

## Flowchart Mapping

This stage supports the flowchart nodes for Canonical IR conversion, normalization, and structure indexing.

## Current Shipped Boundary

The current worker ships a partial Canonical IR contract. It writes
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
When converters do not provide that native evidence, the writer keeps
converted-line precision and the coverage report lists the missing native
precision kinds instead of fabricating coordinates.
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
C2 relationships record content-safe `contains` and `next_sibling` structure
links between typed-node ids. C2 assets record content-safe image references
from figure nodes without copying alt text or title text. C2 annotations record
content-safe coverage warnings. The coverage report now marks these three gap
areas as `partial` only when the corresponding artifact has records; empty or
missing artifacts remain `target_work`. Full route-wide gate use of IR
semantics, complete route-native relationship and asset semantics, richer
quality annotations, and full Markdown regeneration coverage are still target
work.

The standard Markdown render path now has a minimal IR regeneration slice:
when a valid `clean_view.json` and `canonical_ir/typed_nodes.json` are present,
`cleaned.md` defaults to Canonical IR node text in Clean View order, while
entries carrying accepted patch identity render from the accepted in-memory
cleanup block content. `cleaning_patches.jsonl` remains content-safe and does
not copy source text, cleaned text, or private rule bodies. This is not the
complete Canonical IR contract: converter-native extraction, route-wide
relationship and asset semantics, richer annotations, every output profile, and
universal fact-layer usage remain partial or target work.

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

## Risk And Rollback

Risk: an unstable IR contract can break conversion, cleanup, render, and feedback at the same time.

Rollback: keep the existing conversion artifacts active while new IR artifacts run in parallel until tests prove equivalence.
