# Phase D2 CleaningPatch Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate auditable `CleaningPatch` records for cleanup-stage block changes before D3 adds patch rejection gates.

**Architecture:** Keep the existing rendered output behavior stable while adding a transition artifact, `cleaning_patches.jsonl`, after `clean_rules.apply_clean_rules()` mutates blocks. The artifact records safe metadata, source block ids, before/after status fields, rule ids, policy snapshot hash, text-changed status, and safe source-location hints instead of copying private source text, source-text hashes, private rule paths, or rule patterns.

**Tech Stack:** Python stdlib, existing block JSONL pipeline, `unittest`, existing KBPrep project checks.

---

### Task 1: Patch Artifact Contract

**Files:**
- Create: `python/kbprep_worker/cleaning_patches.py`
- Create or modify: `python/tests/test_cleaning_patches.py`

- [x] **Step 1: Write failing tests for patch generation**

Add tests that compare pre-clean and post-clean blocks and assert:

```python
patches = build_cleaning_patches(
    before_blocks=[{"block_id": "b1", "status": "keep", "text": "正文"}],
    after_blocks=[{"block_id": "b1", "status": "discard", "type": "marketing_cta", "text": "正文", "cleaning_rule_id": "rule.cta"}],
    policy_snapshot_hash="policy-1",
)
self.assertEqual(patches[0]["schema"], "kbprep.cleaning_patch.v1")
self.assertEqual(patches[0]["block_id"], "b1")
self.assertEqual(patches[0]["change_type"], "status_update")
self.assertEqual(patches[0]["before"]["status"], "keep")
self.assertEqual(patches[0]["after"]["status"], "discard")
self.assertEqual(patches[0]["rule_id"], "rule.cta")
self.assertEqual(patches[0]["policy_snapshot_hash"], "policy-1")
self.assertNotIn("正文", json.dumps(patches, ensure_ascii=False))
```

Also cover derived promotional-line blocks with `change_type == "derived_block"`.

- [x] **Step 2: Implement patch helpers**

`cleaning_patches.py` should expose:

```python
def build_cleaning_patches(
    before_blocks: list[dict],
    after_blocks: list[dict],
    policy_snapshot_hash: str,
) -> list[dict]:
    ...

def write_cleaning_patches(path: Path, patches: list[dict]) -> None:
    ...
```

Record text-change status and only safe block metadata. Do not write source-text hashes because short private text hashes are guessable.

### Task 2: Pipeline Wiring

**Files:**
- Modify: `python/kbprep_worker/stages/pipeline_core.py`
- Modify: `python/tests/test_core_processing_paths.py`

- [x] **Step 1: Preserve pre-clean blocks before mutation**

In `_stage_apply_cleaning_rules()`, copy `state.blocks` before calling `apply_clean_rules()`.

- [x] **Step 2: Write `cleaning_patches.jsonl` after cleaning**

After cleaning, call `build_cleaning_patches()` and `write_cleaning_patches(run_dir / "cleaning_patches.jsonl", patches)`.

- [x] **Step 3: Add output reference**

Expose the path in the existing output metadata where other run artifacts are listed, without changing `cleaned.md` behavior.

### Task 3: Documentation And Status

**Files:**
- Modify: `docs/development/07-cleaning-unit-patch-clean-view.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [x] **Step 1: Mark only D2 patch generation as landed**

Do not claim patch gating, rejected patches, or Clean View assembly.

- [x] **Step 2: Run development document checks**

Run:

```powershell
npm run check:development-docs
```

### Task 4: Review And Integration

- [x] **Step 1: Run targeted checks**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_cleaning_patches -v
node scripts/python-venv.mjs -m unittest python.tests.test_core_processing_paths -v
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

Reviewer must check patch contract completeness, private-content leakage, backward compatibility with current rendering, and whether D3 still owns rejection semantics.

- [x] **Step 4: Fix review findings**

Review closure: subagent review found and rechecked rule-source leakage, source-text hash leakage, cache artifact absence, unsafe cache artifact reuse, and D2 documentation scope. Final re-review reported no remaining Critical, Important, or Minor findings.

- [ ] **Step 5: Merge, push, verify CI, and clean the D2 worktree**
