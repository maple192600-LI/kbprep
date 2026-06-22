# C1b-2 And C2 SourceSpan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add transcript cue TypedNodes and a validated SourceSpan artifact for the current Canonical IR pipeline.

**Architecture:** Keep TypedNode identity and SourceSpan evidence separate. Extend the Markdown TypedNode builder with line ranges and transcript context, add a focused `canonical_spans.py` module for `source_spans.json`, then wire it into `canonical_ir.py` and the conversion quality gate. Keep status conservative: this lands C1b-2 and the first C2 artifact, while route-native PDF/Office/cell/bbox precision remains future route-specific refinement.

**Tech Stack:** Python worker modules, Python `unittest` through `node scripts/python-venv.mjs`, JSON artifact IO through `atomic_write_json`, KBPrep npm verification scripts.

---

## File Structure

- Modify: `python/kbprep_worker/canonical_nodes.py`
  - Add `transcript_cue`, line-range fields on internal `TypedNode`, and transcript context metadata.
- Create: `python/kbprep_worker/canonical_transcripts.py`
  - Share raw transcript cue parsing between typed-node and SourceSpan builders.
- Create: `python/kbprep_worker/canonical_spans.py`
  - Own SourceSpan schema, builder, writer, and artifact validator.
- Modify: `python/kbprep_worker/canonical_ir.py`
  - Write and validate `canonical_ir/source_spans.json`; update manifest artifacts and coverage.
- Modify: `python/kbprep_worker/quality/conversion_gate.py`
  - Add SourceSpan repair action mapping.
- Modify: `python/tests/test_canonical_ir_typed_nodes.py`
  - Add transcript cue parser coverage.
- Create: `python/tests/test_canonical_ir_source_spans.py`
  - Add SourceSpan writer and validator coverage.
- Modify: `python/tests/test_canonical_ir_schema.py`
  - Add manifest validator coverage for source spans and remove the old C1 rejection assumption.
- Modify: `python/tests/test_canonical_ir_manifest.py`
  - Assert prepare writes SourceSpan evidence.
- Modify: `python/tests/test_conversion_gate.py`
  - Assert malformed SourceSpan evidence blocks cleanup.
- Modify: `python/kbprep_worker/error_codes.py`
- Modify: `src/errorCodes.ts`
  - Register the SourceSpan invalid error code in the cross-language contract.
- Modify docs/status:
  - `docs/development/02-canonical-ir-contract.md`
  - `docs/development/development-roadmap.md`
  - `docs/development/kbprep-implementation-status.json`
  - `docs/known-issues.md`
  - this plan and the matching design doc

---

### Task 1: Add Failing Tests

**Files:**
- Modify: `python/tests/test_canonical_ir_typed_nodes.py`
- Create: `python/tests/test_canonical_ir_source_spans.py`
- Modify: `python/tests/test_canonical_ir_schema.py`
- Modify: `python/tests/test_canonical_ir_manifest.py`
- Modify: `python/tests/test_conversion_gate.py`

- [ ] **Step 1: Add transcript cue TypedNode test**

Add a test proving transcript context converts paragraphs to `transcript_cue` while preserving the heading:

```python
    def test_parser_builds_transcript_cue_nodes_in_transcript_context(self) -> None:
        markdown = """# Transcript

Host: Welcome to the lesson.

Guest: Set threshold to 0.8 and record the failure reason.
"""

        nodes = build_typed_nodes_from_markdown(markdown, source_type="subtitle_transcript")

        self.assertEqual([node.node_type for node in nodes], ["heading", "transcript_cue", "transcript_cue"])
        self.assertEqual(nodes[1].metadata, {"cue_index": 1, "speaker": "Host"})
        self.assertEqual(nodes[2].metadata, {"cue_index": 2, "speaker": "Guest"})
```

- [ ] **Step 2: Add SourceSpan writer tests**

Create `python/tests/test_canonical_ir_source_spans.py` with tests that:

- write typed nodes for a Markdown document
- write `source_spans.json`
- assert schema, artifact references, span ids, node ids, and converted line ranges
- verify subtitle transcript cues carry `cue_index`, `start_time`, and `end_time` when raw SRT cues provide them
- verify converter-added transcript introductions stay as paragraphs and do not shift cue timing
- verify CSV/TSV inputs use `structured_data` source kind

- [ ] **Step 3: Add manifest validator tests**

Update `python/tests/test_canonical_ir_schema.py` so validation:

- accepts a valid `source_spans.json` artifact when `coverage.source_spans_available` is true
- rejects `source_spans_available=true` without `artifacts.source_spans`
- rejects escaping SourceSpan artifact paths
- rejects malformed SourceSpan payloads with `E_CANONICAL_IR_SOURCE_SPANS_INVALID`
- rejects malformed SourceSpan `evidence` objects instead of accepting arbitrary non-empty JSON
- rejects SourceSpan node id/count mismatches against `typed_nodes.json`

- [ ] **Step 4: Add prepare and conversion-gate tests**

Update `python/tests/test_canonical_ir_manifest.py` to assert prepare writes:

```python
self.assertTrue(canonical_manifest["coverage"]["source_spans_available"])
self.assertEqual(canonical_manifest["artifacts"]["source_spans"], "canonical_ir/source_spans.json")
self.assertTrue((run_dir / "canonical_ir" / "source_spans.json").exists())
```

Update `python/tests/test_conversion_gate.py` with a malformed
`source_spans.json` case that fails pre-clean conversion with
`E_CANONICAL_IR_SOURCE_SPANS_INVALID` and a `regenerate_canonical_ir` action.

- [ ] **Step 5: Run tests and verify RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_source_spans python.tests.test_canonical_ir_manifest python.tests.test_canonical_ir_schema python.tests.test_conversion_gate -v
```

Expected: fail because `transcript_cue`, `canonical_spans.py`, and source-span manifest wiring do not exist yet.

---

### Task 2: Implement Transcript Cue Nodes

**Files:**
- Modify: `python/kbprep_worker/canonical_nodes.py`

- [ ] **Step 1: Extend supported node types and internal line ranges**

Add `transcript_cue` to `SUPPORTED_NODE_TYPES`. Extend the internal
`TypedNode` dataclass with `line_start` and `line_end`, but keep
`_typed_node_to_dict()` output limited to the existing JSON keys.

- [ ] **Step 2: Add transcript context handling**

Change `build_typed_nodes_from_markdown()` to accept optional
`source_type`, `conversion_route`, and transcript cue text keyword arguments.
If the context is transcript-like, convert paragraph nodes to `transcript_cue`
only when they match raw cue text, or when no raw cue text exists and a speaker
prefix is present. Add `cue_index` plus optional `speaker`.

- [ ] **Step 3: Run TypedNode tests and verify GREEN for this task**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes -v
```

Expected: TypedNode tests pass.

---

### Task 3: Implement SourceSpan Artifact

**Files:**
- Create: `python/kbprep_worker/canonical_transcripts.py`
- Create: `python/kbprep_worker/canonical_spans.py`
- Test: `python/tests/test_canonical_ir_source_spans.py`

- [ ] **Step 1: Add SourceSpan schema and writer**

Create `canonical_spans.py` with:

- `CANONICAL_IR_SOURCE_SPANS_SCHEMA`
- `SOURCE_SPANS_INVALID_CODE`
- `write_source_spans_artifact(...)`
- `validate_source_spans_artifact(...)`

The writer rebuilds typed nodes with the same transcript context and raw cue
text evidence, then creates one span per node.

- [ ] **Step 2: Add transcript cue timing extraction**

For `.srt` and `.vtt`-style inputs, parse cue timing lines containing `-->`.
Map timing evidence to transcript cue spans by matched cue index. Timing
evidence is optional for media transcripts because current local ASR output may
only provide plain text.

- [ ] **Step 3: Validate strict SourceSpan boundaries**

Validation must reject:

- invalid schema
- document id mismatch
- invalid or escaping artifact refs
- non-integer or mismatched `span_count`
- span keys other than `span_id`, `node_id`, `source_kind`, `location`,
  `evidence`
- non-contiguous `span_id`
- node id mismatch against typed nodes
- unsupported `source_kind`
- invalid converted line ranges
- non-object `location` or `evidence`
- `evidence` objects missing required keys or declaring precision that does not
  match location fields
- precision-specific location fields that are mixed together, such as
  `source_line_range` plus transcript timing

- [ ] **Step 4: Run SourceSpan tests and verify GREEN**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_source_spans -v
```

Expected: SourceSpan tests pass.

---

### Task 4: Wire SourceSpans Into Canonical IR And Gate

**Files:**
- Modify: `python/kbprep_worker/canonical_ir.py`
- Modify: `python/kbprep_worker/quality/conversion_gate.py`
- Test: `python/tests/test_canonical_ir_schema.py`
- Test: `python/tests/test_canonical_ir_manifest.py`
- Test: `python/tests/test_conversion_gate.py`

- [ ] **Step 1: Write source spans after typed nodes**

After `typed_nodes.json` validates, write `source_spans.json`, add
`artifacts.source_spans`, and set `coverage.source_spans_available` based on
SourceSpan validation.

- [ ] **Step 2: Validate source-span manifest references**

Allow legacy hand-written manifests to omit `artifacts.source_spans` only when
`source_spans_available` is false. When true, require the artifact to point to
`canonical_ir/source_spans.json` and validate it against typed nodes.

- [ ] **Step 3: Add conversion-gate repair action**

Map `E_CANONICAL_IR_SOURCE_SPANS_INVALID` to `regenerate_canonical_ir`.

- [ ] **Step 4: Run integration tests and verify GREEN**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_manifest python.tests.test_canonical_ir_schema python.tests.test_conversion_gate -v
```

Expected: all pass.

---

### Task 5: Update Docs And Status Conservatively

**Files:**
- Modify: `docs/development/02-canonical-ir-contract.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`
- Modify: `docs/known-issues.md`

- [ ] **Step 1: Update shipped boundary**

State that current Canonical IR writes validated `typed_nodes.json` and
`source_spans.json`, with transcript cue nodes included.

- [ ] **Step 2: Keep non-shipped claims out**

Keep `canonical_ir_contract` partial unless full fact-layer use, relationships,
assets, annotations, TransformationLedger, and Markdown regeneration are also
implemented. Keep route-native fine-grained spans as remaining precision work
when converters do not yet emit PDF bbox, DOCX run, PPTX shape, XLSX cell, or
YouTube cue evidence.

- [ ] **Step 3: Run stale-claim searches**

Run:

```powershell
rg -n "transcript cues, source spans, and universal|source_spans_available.*remains false|SourceSpan coverage is not yet complete|heading, paragraph, list, table, code, quote, formula, figure, and metadata nodes" docs/development docs/known-issues.md docs/capability-matrix.md README.md
rg -n "Canonical IR is the complete shipped worker fact layer|all conversion routes have complete Canonical IR gate coverage" docs/development docs/known-issues.md docs/capability-matrix.md README.md
```

Expected: no stale current-boundary wording except prohibited-claim guard text.

---

### Task 6: Full Verification, Commit, Merge, Push

**Files:**
- All task files above.

- [ ] **Step 1: Run focused Canonical IR suite**

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_source_spans python.tests.test_canonical_ir_manifest python.tests.test_canonical_ir_schema python.tests.test_conversion_gate -v
```

- [ ] **Step 2: Run Python and project checks**

```powershell
npm run python:test
npm run python:ruff
npm run python:typecheck
npm run dev:full-check
git diff --check
```

- [ ] **Step 3: Commit**

```powershell
git add docs/superpowers/specs/2026-06-22-c1b2-c2-source-spans-design.md docs/superpowers/plans/2026-06-22-c1b2-c2-source-spans.md python/kbprep_worker/canonical_nodes.py python/kbprep_worker/canonical_transcripts.py python/kbprep_worker/canonical_spans.py python/kbprep_worker/canonical_ir.py python/kbprep_worker/error_codes.py src/errorCodes.ts python/kbprep_worker/quality/conversion_gate.py python/tests/test_canonical_ir_typed_nodes.py python/tests/test_canonical_ir_source_spans.py python/tests/test_canonical_ir_manifest.py python/tests/test_canonical_ir_schema.py python/tests/test_conversion_gate.py docs/development/02-canonical-ir-contract.md docs/development/development-roadmap.md docs/development/kbprep-implementation-status.json docs/known-issues.md
git commit -m "feat: add canonical IR source spans"
```

- [ ] **Step 4: Merge and verify on main**

```powershell
git checkout main
git pull --ff-only origin main
git merge --ff-only codex/c1b2-c2-source-spans
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_source_spans python.tests.test_canonical_ir_manifest python.tests.test_canonical_ir_schema python.tests.test_conversion_gate -v
npm run dev:full-check
git push origin main
git branch -d codex/c1b2-c2-source-spans
```

Expected: `main` is clean, pushed, and synced with `origin/main`.

---

## Self-Review

- Spec coverage: covers transcript cues, SourceSpan artifact, manifest coverage,
  conversion-gate validation, status docs, checks, commit, merge, and push.
- Placeholder scan: no deferred or incomplete implementation markers remain.
- Type consistency: uses existing `TypedNode`, manifest, validation issue, and
  conversion-gate patterns.
- Scope check: C3 TransformationLedger, C4 full gate semantics, C5 IR-based
  conversion gate completeness, CleaningPatch, and Clean View remain outside
  this slice.
