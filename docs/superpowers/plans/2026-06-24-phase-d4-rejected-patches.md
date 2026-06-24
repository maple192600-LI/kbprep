# Phase D4 Rejected Patches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write a content-safe `rejected_patches.jsonl` artifact for every patch rejected by `patch_quality_gate`, without adding Clean View assembly or the final document cleaning gate.

**Architecture:** Reuse the D3 patch gate decision. Accepted patches continue to be written to `cleaning_patches.jsonl`. Rejected patches are written as safe JSONL records with reason code, patch identity, safe before/after metadata, policy snapshot hash, and location hints. Cache reuse must require a valid rejected-patch artifact so D3 runs cannot bypass D4 evidence.

**Non-goals:** Do not implement Clean View assembly, do not switch rendering to Clean View, do not add document-level cleaning gates, and do not store source text, text hashes, private rule paths, rule patterns, rule reasons, or heading text.

---

### Task 1: Rejected Patch Artifact Contract

**Files:**
- Modify: `python/kbprep_worker/cleaning_patch_gate.py`
- Modify: `python/tests/test_cleaning_patch_gate.py`

- [x] **Step 1: Write failing artifact tests**

Cover:
- Rejected patch records include current schema, reason code, patch id, block ids, change type, policy snapshot hash, safe before/after metadata, text-changed status, and location hints.
- Rejected patch records do not copy source text, text hashes, rule patterns, rule reasons, headings, or private paths.
- Validator rejects old, leaky, malformed, or extra-field records.

- [x] **Step 2: Implement writer and validator**

Expose small helpers:

```python
write_rejected_patches(path: Path, rejected_patches: list[dict[str, Any]]) -> None
validate_rejected_patches_artifact(path: Path) -> bool
```

### Task 2: Pipeline And Cache Wiring

**Files:**
- Modify: `python/kbprep_worker/stages/cleaning_stage.py`
- Modify: `python/kbprep_worker/stages/pipeline_core.py`
- Modify: `python/kbprep_worker/stages/pipeline_helpers.py`
- Modify: `python/tests/test_core_processing_paths.py`
- Modify: `src/test/scenarios/worker-output-guards-part1.test.ts`

- [x] **Step 1: Write rejected report during cleanup**

Write `rejected_patches.jsonl` beside `cleaning_patches.jsonl` and `cleaning_patch_gate.json`, including an empty valid file when no patches are rejected.

- [x] **Step 2: Expose rejected report path**

Add `rejected_patches` to run outputs and keep the report out of `latest_outputs` unless a future phase explicitly publishes it.

- [x] **Step 3: Require valid rejected report for cache reuse**

Add `rejected_patches.jsonl` to required cache artifacts and validate its schema. Old D3 runs without it must rerun.

### Task 3: Documentation And Status

**Files:**
- Modify: `docs/development/07-cleaning-unit-patch-clean-view.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [x] **Step 1: Mark only D4 rejected report as landed**

Keep `patch_clean_view` partial. Make clear Clean View assembly and document cleaning gate remain D5-D6.

- [x] **Step 2: Run development document checks**

Run:

```powershell
npm run check:development-docs
```

### Task 4: Review And Integration

- [x] **Step 1: Run targeted checks**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_cleaning_patch_gate python.tests.test_cleaning_patches python.tests.test_core_processing_paths -v
npm test -- src/test/scenarios/worker-output-guards-part1.test.ts
```

- [x] **Step 2: Run project checks**

Run:

```powershell
npm run python:ruff
npm run python:typecheck
npm run python:test
npm run dev:check
```

- [x] **Step 3: Request subagent review**

Reviewer must check artifact safety, cache compatibility, D5/D6 boundary discipline, and rejection report completeness.

- [x] **Step 4: Fix review findings**

- [x] **Step 5: Merge, push, verify CI, and clean the D4 worktree**
