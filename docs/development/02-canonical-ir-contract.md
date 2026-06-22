# 02 Canonical IR Contract

## Purpose

Define the stable internal document model used after conversion and before cleanup.

## Flowchart Mapping

This stage supports the flowchart nodes for Canonical IR conversion, normalization, and structure indexing.

## Current Shipped Boundary

The current worker ships a partial Canonical IR contract. It writes
`canonical_ir/manifest.json`, `document_manifest.json`, and a validated
`canonical_ir/typed_nodes.json` artifact for converted Markdown blocks.

The shipped typed-node slices cover heading, paragraph, list, table, code,
quote, formula, figure, and metadata nodes in source order.
`typed_nodes_available` is true only when that artifact validates.
`source_spans_available` remains false; transcript cues, SourceSpan coverage,
relationship evidence, assets, annotations, a transformation ledger, and
Markdown regeneration from IR plus accepted changes are still target work.

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
