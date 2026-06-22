# C1b-2 And C2 SourceSpan Design

## Purpose

Finish the next Canonical IR slice by adding transcript cue nodes and a
validated SourceSpan artifact without changing conversion routing, cleanup,
rendering, or publication behavior.

## Scope

This slice adds:

- `transcript_cue` TypedNodes for transcript-like converted Markdown.
- `canonical_ir/source_spans.json` as a sibling artifact to
  `canonical_ir/typed_nodes.json`.
- Manifest wiring for `artifacts.source_spans` and
  `coverage.source_spans_available`.
- Conversion-gate validation for malformed SourceSpan evidence.

The existing TypedNode JSON shape stays unchanged. Source evidence is kept in a
separate artifact so later cleanup patches can point to nodes without putting
fake span fields inside `typed_nodes.json`.

## Artifact Contract

`canonical_ir/source_spans.json` uses schema
`kbprep.canonical_ir_source_spans.v1`:

```json
{
  "schema": "kbprep.canonical_ir_source_spans.v1",
  "document_id": "doc_hashprefix",
  "source_artifact": "converted.md",
  "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
  "span_count": 2,
  "spans": [
    {
      "span_id": "s_000001",
      "node_id": "n_000001",
      "source_kind": "converted_markdown",
      "location": {
        "converted_line_start": 1,
        "converted_line_end": 1
      },
      "evidence": {
        "source_type": "markdown_note",
        "converter": "direct_text",
        "conversion_route": "direct_text",
        "source_kind": "converted_markdown",
        "precision": "converted_line_range"
      }
    }
  ]
}
```

Each SourceSpan maps one TypedNode to one evidence location. The first shipped
coverage guarantees converted-Markdown line ranges for every node. Direct
Markdown/text inputs can additionally report original source line ranges where
the conversion is pass-through. Subtitle transcript cues additionally carry cue
index and timing when the input file provides them.

## Transcript Cue Rules

Transcript cues are only inferred when the caller identifies the source as a
transcript context: `source_type == "subtitle_transcript"` or a media transcript
conversion route. In that context, paragraph nodes become `transcript_cue` only
when they match raw timed cue text, or when no raw cue text is available and the
paragraph has a short `Speaker:` or `Speaker：` prefix. Converter-added
introductions or notes stay as ordinary paragraph nodes so they do not shift cue
timing. The builder records deterministic `cue_index` metadata and a `speaker`
value when a speaker prefix exists.

## SourceSpan Rules

- `source_spans_available` is true only when `source_spans.json` exists and
  validates against the matching typed-node artifact.
- The SourceSpan artifact must use contiguous span ids and must reference typed
  node ids in the same order.
- Every span must include a non-empty `location` object and an `evidence` object
  with exact keys for source type, converter, conversion route, source kind, and
  precision.
- Evidence precision must match location data: source line ranges require source
  line fields, and transcript cue timing requires start and end times.
- Precision-specific location fields are mutually exclusive: source line
  precision cannot carry transcript cue timing, and transcript cue timing cannot
  carry source line ranges.
- SourceSpan paths must stay inside the run directory.
- Invalid SourceSpan evidence blocks cleanup through the conversion quality
  gate.

## Non-Goals

- Do not change protected design semantics.
- Do not add `SourceSpan` fields to `typed_nodes.json`.
- Do not claim full Canonical IR fact-layer usage, TransformationLedger,
  relationship evidence, asset registry, annotations, CleaningPatch, or Clean
  View.
- Do not promote optional media or YouTube route capability status.
- Do not invent PDF bounding boxes, DOCX run ranges, PPTX shapes, XLSX cells, or
  YouTube cue ids when converters do not provide that evidence yet.

## Verification

Use project-environment commands only:

- `node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_source_spans python.tests.test_canonical_ir_manifest python.tests.test_canonical_ir_schema python.tests.test_conversion_gate -v`
- `npm run python:test`
- `npm run python:ruff`
- `npm run python:typecheck`
- `npm run dev:full-check`
- `git diff --check`
