# Phase D3 CleaningPatch Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first `patch_quality_gate` over generated `CleaningPatch` records so unsafe cleanup changes are rejected before rendering, while leaving rejected patch reporting and Clean View assembly to D4-D6.

**Architecture:** Keep D3 narrow. After cleaning rules generate candidate blocks and `cleaning_patches.jsonl`, run a deterministic gate against pre-clean blocks, post-clean blocks, patch records, and the compiled policy snapshot. Accepted patches keep the existing cleaned block changes. Rejected patches restore the original block or remove unsafe derived blocks before the current renderer runs. D3 records only a machine-readable gate summary; D4 will own `rejected_patches.jsonl`.

**Non-goals:** Do not add Clean View assembly, do not claim full `patch_clean_view`, do not write final rejected patch reports, and do not change protected design documents.

---

### Task 1: Gate Contract

**Files:**
- Create: `python/kbprep_worker/cleaning_patch_gate.py`
- Create: `python/tests/test_cleaning_patch_gate.py`

- [x] **Step 1: Write failing gate tests**

Cover:
- Missing target block is rejected.
- Rule id not present in `compiled_policy.active_rule_ids` is rejected.
- Protected/table/code/image/formula-like blocks cannot be discarded or content-changed.
- Whole section-heading deletion is rejected.
- Safe rule-backed CTA discard is accepted.
- Derived unsafe block can be rejected without keeping a new derived block.

- [x] **Step 2: Implement gate helpers**

Expose a small typed result:

```python
apply_patch_quality_gate(
    before_blocks: list[dict],
    cleaned_blocks: list[dict],
    patches: list[dict],
    compiled_policy: dict,
) -> PatchGateResult
```

Return gated blocks, accepted patches, rejected patch metadata, and summary counts.

### Task 2: Pipeline Wiring

**Files:**
- Modify: `python/kbprep_worker/stages/cleaning_stage.py`
- Modify: `python/kbprep_worker/stages/pipeline_core.py`
- Modify: `python/tests/test_core_processing_paths.py`

- [x] **Step 1: Pass compiled policy into cleaning stage**

Use the existing `CleaningPolicySnapshot` payload. Do not recompile policy independently.

- [x] **Step 2: Apply gate before image classification/rendering**

After candidate patches are built, gate them, restore rejected changes in memory, then write `cleaning_patches.jsonl` from accepted patch records. Write `cleaning_patch_gate.json` as summary evidence.

- [x] **Step 3: Expose gate summary path**

Add `cleaning_patch_gate` to run outputs. Do not add `rejected_patches.jsonl` in D3.

### Task 3: Documentation And Status

**Files:**
- Modify: `docs/development/07-cleaning-unit-patch-clean-view.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [x] **Step 1: Mark only D3 patch gate as landed**

Keep `patch_clean_view` partial. Make clear rejected patch reports and Clean View assembly remain D4-D6.

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

Reviewer must check restoration correctness, D4/D5 boundary discipline, private-content leakage in gate evidence, and backward compatibility for safe cleanup.

- [x] **Step 4: Fix review findings**

- [x] **Step 5: Merge, push, verify CI, and clean the D3 worktree**
