# Phase D6 Document Cleaning Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a content-safe `document_cleaning_gate.json` over the assembled Clean View so final cleanup acceptance is explicit before source-side publication.

**Architecture:** Keep D6 as the last Phase D quality slice. The gate reads `clean_view.json`, `rejected_patches.jsonl`, `cleaned.md`, and in-memory block metadata. It writes counts, ids, reason codes, and pass/warn/fail decisions only; it must not copy source text, rejected patch text, rule patterns, private paths, or headings. Strict failures block publication through the existing quality path. Rejected patches produce owner-visible warnings without blocking otherwise safe output.

**Tech Stack:** Python worker quality modules and unittest through `node scripts/python-venv.mjs`; existing TypeScript worker output guards; development docs and implementation status checks.

**Non-goals:** Do not change the protected core design or flowchart, do not change source-side publication semantics beyond requiring the new gate artifact, do not introduce AI review behavior, and do not alter cleanup dictionaries.

---

### Task 1: Document Cleaning Gate Contract

**Files:**
- Create: `python/kbprep_worker/document_cleaning_gate.py`
- Create: `python/tests/test_document_cleaning_gate.py`

- [x] **Step 1: Write failing gate tests**

Cover:
- A valid Clean View, rendered `cleaned.md`, and no rejected patches returns `status="pass"`.
- Rejected patches return `status="warn"` and a warning code without strict errors.
- Missing or invalid Clean View returns `status="fail"` with a strict error code.
- The artifact is content-safe and contains only counts, ids, artifact paths, and reason codes.

- [x] **Step 2: Run the new tests and verify RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest discover -s python/tests -p test_document_cleaning_gate.py -v
```

Expected: fail because `kbprep_worker.document_cleaning_gate` does not exist.

- [x] **Step 3: Implement the minimal gate**

Add:

```python
DOCUMENT_CLEANING_GATE_SCHEMA = "kbprep.document_cleaning_gate.v1"

def run_document_cleaning_gate(*, run_dir: Path, blocks: list[dict]) -> dict[str, Any]:
    ...

def write_document_cleaning_gate(path: Path, payload: dict[str, Any]) -> None:
    ...

def validate_document_cleaning_gate_artifact(path: Path) -> bool:
    ...
```

Rules:
- Validate `clean_view.json` before trusting it.
- Fail when Clean View is missing, invalid, incomplete, or inconsistent with block ids.
- Warn when rejected patches exist, using reason codes and counts only.
- Fail when `cleaned.md` is missing after render.
- Do not copy any source text, patch before/after text, rule pattern, private path, or heading text.

- [x] **Step 4: Verify GREEN**

Run:

```powershell
node scripts/python-venv.mjs -m unittest discover -s python/tests -p test_document_cleaning_gate.py -v
```

Expected: all tests pass.

### Task 2: Quality, Cache, And Output Wiring

**Files:**
- Modify: `python/kbprep_worker/quality/runner.py`
- Modify: `python/kbprep_worker/quality/gates.py`
- Modify: `python/kbprep_worker/stages/pipeline_core.py`
- Modify: `python/kbprep_worker/stages/pipeline_helpers.py`
- Modify: `python/tests/test_core_processing_paths.py`
- Modify: `src/test/scenarios/worker-output-guards-part1.test.ts`

- [x] **Step 1: Write failing integration tests**

Cover:
- A successful prepare run writes `document_cleaning_gate.json`.
- Run outputs expose `document_cleaning_gate`.
- Cache reuse requires a valid gate artifact so D5-era runs rerun.
- Rejected patches become warnings and do not block safe publication.

- [x] **Step 2: Run integration tests and verify RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_core_processing_paths -v
npm test -- src/test/scenarios/worker-output-guards-part1.test.ts
```

Expected: fail because the new artifact/output is not wired yet.

- [x] **Step 3: Wire the gate into final quality**

Implement:
- `run_quality_check(...)` runs `DocumentCleaningGate` after render and includes the report in `quality_report.json`.
- Gate strict errors flow into existing `strict_errors`.
- Gate warnings flow into existing warnings and quality gate grouping.
- `_publish_cached_run_if_available(...)` requires a valid `document_cleaning_gate.json`.
- `_run_outputs(...)` exposes `document_cleaning_gate`.

- [x] **Step 4: Verify GREEN**

Run:

```powershell
node scripts/python-venv.mjs -m unittest discover -s python/tests -p test_document_cleaning_gate.py -v
node scripts/python-venv.mjs -m unittest python.tests.test_core_processing_paths -v
npm test -- src/test/scenarios/worker-output-guards-part1.test.ts
```

Expected: all tests pass.

### Task 3: Documentation And Capability Status

**Files:**
- Modify: `docs/development/07-cleaning-unit-patch-clean-view.md`
- Modify: `docs/development/08-source-side-publish.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [x] **Step 1: Mark Phase D6 as landed**

Update docs to say DocumentCleaningGate is shipped and Phase D is closed. Promote `patch_clean_view` to `implemented` with evidence for D1-D6, while keeping unrelated capabilities partial.

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
node scripts/python-venv.mjs -m unittest discover -s python/tests -p test_document_cleaning_gate.py -v
node scripts/python-venv.mjs -m unittest python.tests.test_cleaning_patch_gate python.tests.test_cleaning_patches python.tests.test_clean_view python.tests.test_core_processing_paths -v
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

Reviewer must check gate semantics, warning-vs-failure behavior, artifact safety, cache compatibility, publication blocking, and status promotion discipline.

- [x] **Step 4: Fix review findings and re-review**

- [x] **Step 5: Commit, push, merge, verify CI, and remove the D6 worktree without physical residue**
