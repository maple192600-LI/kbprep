# Phase D5 Clean View Assembler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a content-safe `clean_view.json` artifact that assembles the renderable document from Canonical IR typed nodes plus accepted CleaningPatch records in original document order.

**Architecture:** Keep D5 as an assembly slice, not a final document gate. A new Python module reads `canonical_ir/typed_nodes.json`, accepted `cleaning_patches.jsonl`, and gated cleanup blocks, then writes `clean_view.json` with ordered entries and renderable block ids. The existing Markdown renderer may consume the assembled entries, but D6 remains responsible for document-level acceptance and warnings.

**Tech Stack:** Python worker modules and unittest via `node scripts/python-venv.mjs`; existing JSON artifact helpers and pipeline stage wiring.

**Non-goals:** Do not implement `DocumentCleaningGate`, do not change source-side publication semantics, do not promote `patch_clean_view` to implemented, and do not copy rejected patch details, private rule paths, rule patterns, rule reasons, source-text hashes, or raw patch before/after text into the Clean View artifact.

---

### Task 1: Clean View Artifact Contract

**Files:**
- Create: `python/kbprep_worker/clean_view.py`
- Create: `python/tests/test_clean_view.py`

- [x] **Step 1: Write failing artifact tests**

Cover:
- `assemble_clean_view(...)` returns `schema="kbprep.clean_view.v1"`, `source_artifact="canonical_ir/typed_nodes.json"`, `patch_artifact="cleaning_patches.jsonl"`, `entry_count`, and ordered `entries`.
- Entries follow Canonical IR order when typed nodes exist.
- Accepted patch state decides whether an entry is `keep`, `discard`, `evidence`, or `review`.
- A `derived_block` accepted patch appears immediately after its parent block.
- The artifact does not include source text, patch before/after payloads, private paths, rule reasons, headings, or source-text hashes.

- [x] **Step 2: Run the new tests and verify RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest discover -s python/tests -p test_clean_view.py -v
```

Expected: fail because `kbprep_worker.clean_view` does not exist.

- [x] **Step 3: Implement the minimal assembler**

Add:

```python
CLEAN_VIEW_SCHEMA = "kbprep.clean_view.v1"

def assemble_clean_view(
    *,
    run_dir: Path,
    blocks: list[dict],
    accepted_patches: list[dict[str, Any]],
) -> dict[str, Any]:
    ...

def write_clean_view(path: Path, payload: dict[str, Any]) -> None:
    ...

def validate_clean_view_artifact(path: Path) -> bool:
    ...
```

Rules:
- Map typed-node ordinal to block order by normalized text when possible, falling back to block order for unmapped blocks.
- Store entry ids, node ids, block ids, block type, status, patch ids, rule ids, location hints, and derived-parent linkage.
- Exclude raw text and every forbidden key already banned from patch artifacts.

- [x] **Step 4: Verify GREEN**

Run:

```powershell
node scripts/python-venv.mjs -m unittest discover -s python/tests -p test_clean_view.py -v
```

Expected: all tests pass.

### Task 2: Pipeline And Renderer Wiring

**Files:**
- Modify: `python/kbprep_worker/stages/cleaning_stage.py`
- Modify: `python/kbprep_worker/stages/pipeline_core.py`
- Modify: `python/kbprep_worker/stages/pipeline_helpers.py`
- Modify: `python/kbprep_worker/render_outputs.py`
- Modify: `python/tests/test_core_processing_paths.py`
- Modify: `src/test/scenarios/worker-output-guards-part1.test.ts`

- [x] **Step 1: Write failing pipeline tests**

Cover:
- A successful prepare run writes `clean_view.json`.
- Run outputs include `clean_view`.
- Cache reuse requires a valid `clean_view.json` so D4-era runs rerun.
- `cleaned.md` still contains the same kept body content after Clean View rendering.

- [x] **Step 2: Run pipeline tests and verify RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_core_processing_paths -v
npm test -- src/test/scenarios/worker-output-guards-part1.test.ts
```

Expected: fail because `clean_view.json` is not written or exposed yet.

- [x] **Step 3: Wire Clean View into cleanup/rendering**

Implement:
- `apply_cleaning_rules_stage(...)` writes `clean_view.json` after patch gate acceptance.
- `_publish_cached_run_if_available(...)` requires `clean_view.json`.
- `_run_outputs(...)` exposes `clean_view`.
- `render_outputs.render(...)` can render from assembled Clean View entries while retaining existing block behavior for callers that do not provide Clean View.

- [x] **Step 4: Verify GREEN**

Run:

```powershell
node scripts/python-venv.mjs -m unittest discover -s python/tests -p test_clean_view.py -v
node scripts/python-venv.mjs -m unittest python.tests.test_core_processing_paths -v
npm test -- src/test/scenarios/worker-output-guards-part1.test.ts
```

Expected: all tests pass.

### Task 3: Documentation And Status

**Files:**
- Modify: `docs/development/07-cleaning-unit-patch-clean-view.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [x] **Step 1: Mark only D5 as landed**

Update docs to say Clean View assembly is shipped, while the final document cleaning gate remains D6. Keep `patch_clean_view` status `partial`.

- [x] **Step 2: Run development document checks**

Run:

```powershell
npm run check:development-docs
```

Expected: pass.

### Task 4: Review And Integration

- [x] **Step 1: Run targeted checks**

Run:

```powershell
node scripts/python-venv.mjs -m unittest discover -s python/tests -p test_clean_view.py -v
node scripts/python-venv.mjs -m unittest python.tests.test_cleaning_patch_gate python.tests.test_cleaning_patches python.tests.test_core_processing_paths -v
npm test -- src/test/scenarios/worker-output-guards-part1.test.ts
```

- [x] **Step 2: Run project checks**

Run:

```powershell
npm run format:check
npm run lint:check
npm run python:ruff
npm run python:typecheck
npm run python:test
npm run dev:check
npm run dev:full-check
git diff --check
```

- [x] **Step 3: Request subagent review**

Reviewer must check D5/D6 boundary discipline, Clean View ordering, artifact safety, cache compatibility, renderer compatibility, and status overclaiming.

- [x] **Step 4: Fix review findings and re-review**

- [ ] **Step 5: Commit, push, merge, verify CI, and remove the D5 worktree without physical residue**
