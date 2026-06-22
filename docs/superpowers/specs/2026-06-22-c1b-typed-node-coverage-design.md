# C1b Typed Node Coverage Design

## Purpose

Extend the shipped Canonical IR TypedNode builder beyond the C1 block types without changing publication behavior, conversion routing, cleanup, or SourceSpan claims.

## Scope

This C1b slice adds three block-level node types:

- `metadata`: YAML frontmatter at the start of a converted Markdown document.
- `figure`: standalone Markdown image blocks such as `![Alt](assets/diagram.png "Title")`.
- `formula`: standalone Markdown math blocks using `$$ ... $$` and standalone inline-style math lines such as `$x + y$`.

The existing C1 node types remain unchanged: `heading`, `paragraph`, `list`, `table`, `code`, and `quote`.

## Parsing Rules

The builder stays deterministic and conservative:

- Code fences are still consumed before any other block detection, so formulas or image syntax inside code remain code text.
- YAML frontmatter is recognized only at the beginning of the document. It becomes one `metadata` node with raw frontmatter text preserved.
- Standalone image syntax becomes one `figure` node. The node text preserves the original Markdown image line. Metadata records `alt`, `target`, and optional `title`.
- Display math delimited by `$$` becomes one `formula` node. The node text is the formula body when present, or the raw formula line for one-line formulas.
- A single standalone `$...$` line becomes one `formula` node. Inline math inside prose remains paragraph text for this slice.

## Non-Goals

- Do not add `transcript_cue`; it remains a separate C1b follow-up.
- Do not add SourceSpan or line ranges.
- Do not turn the builder into a full CommonMark parser.
- Do not change conversion routes, cleanup behavior, source-side publication, or capability status to `implemented`.

## Verification

Use project-environment commands only:

- `node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_schema -v`
- `node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_schema python.tests.test_conversion_gate -v`
- `npm run python:test`
- `npm run python:ruff`
- `npm run python:typecheck`
- `npm run dev:check`
- `git diff --check`
