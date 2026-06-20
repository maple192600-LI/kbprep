# KBPrep Audit Clearance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clear the remaining audit findings that could still allow false success, environment bypass, or unproven quality-gate behavior.

**Architecture:** Keep the highest design documents unchanged. Close the remaining gaps with regression tests, stricter governance scanning, CI command alignment, and project-environment verification only.

**Tech Stack:** Node 22, Vitest, TypeScript, Python unittest through `node scripts/python-venv.mjs`, KBPrep local `.kbprep/venv`.

---

## Scope

- `document_manifest.json` negative validation and conversion gate coverage.
- `kbprep-feedback` standalone CLI negative acceptance coverage without `--confirm-rule-acceptance`.
- CI and test governance that prevents system Python command regressions.
- Existing source-side publication, Canonical IR partial status, Clean View target status, and user-facing output rules are not changed.

## Forbidden Scope

- Do not edit `docs/kbprep-core-flow-design.md` or `docs/kbprep-full-flowchart.html`.
- Do not mark Canonical IR as fully implemented.
- Do not replace existing `converted.md`, `normalized.md`, `blocks.jsonl`, `chunk_manifest.jsonl`, or `quality_report.json` compatibility artifacts.
- Do not use system Python command output as verification evidence.
- Do not change cleanup policy semantics or publish location semantics.

### Task 1: Document Manifest Gate Coverage

**Files:**
- Modify: `python/tests/test_canonical_ir_schema.py`
- Modify: `python/tests/test_canonical_ir_manifest.py`

- [x] Add validator coverage for missing `document_manifest.json`.
- [x] Add validator coverage for `document_manifest.json` references that escape the run directory.
- [x] Add conversion gate coverage proving missing or invalid document manifest blocks cleanup with `E_DOCUMENT_MANIFEST_*`.
- [x] Run: `node scripts/python-venv.mjs -m unittest discover -s python/tests -p "test_canonical_ir_schema.py" -v`
- [x] Run: `node scripts/python-venv.mjs -m unittest discover -s python/tests -p "test_canonical_ir_manifest.py" -v`

### Task 2: Feedback Standalone CLI Confirmation Coverage

**Files:**
- Modify: `src/test/scenarios/worker-feedback-promotion.test.ts`

- [x] Add a scenario that creates a feedback proposal through the managed worker harness.
- [x] Accept it through `runStandaloneCli("feedback", ...)` without `--confirm-rule-acceptance`.
- [x] Assert the CLI exits nonzero with `E_CONFIRMATION_REQUIRED`.
- [x] Assert `accepted_rules.jsonl` is not written.
- [x] Run: `npm test -- src/test/scenarios/worker-feedback-cli.test.ts`

### Task 3: Project Environment Governance Closure

**Files:**
- Modify: `scripts/checks/project-env-commands.mjs`
- Modify: `src/test/scenarios/worker-governance-guards.test.ts`
- Modify: `python/tests/test_review_regression_guards.py`
- Modify: `.github/workflows/ci.yml`

- [x] Make `project-env-commands.mjs` scan `.github/workflows` and `python/tests`.
- [x] Add a governance test proving `.github` and Python test system-Python regressions are blocked.
- [x] Replace Python test subprocess usage of `"python"` with `sys.executable`.
- [x] Replace CI Python runtime/test commands with `node scripts/python-venv.mjs ...`.
- [x] Run: `npm test -- src/test/scenarios/worker-governance-guards.test.ts`
- [x] Run: `node scripts/python-venv.mjs -m unittest discover -s python/tests -p "test_review_regression_guards.py" -v`

### Task 4: Full Verification And Closeout

**Files:**
- Inspect all changed files and repository status.

- [x] Run: `npm run dev:full-check`
- [x] Run: `git diff --check`
- [x] Run stale-command search for `.github`, docs, scripts, src tests, and Python tests.
- [ ] Commit and push if verification passes.
