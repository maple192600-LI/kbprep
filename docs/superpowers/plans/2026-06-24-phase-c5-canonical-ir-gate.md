# Phase C5 Canonical IR Gate Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the pre-clean conversion gate prefer complete Canonical IR typed-node and source-span evidence when rendered Markdown quality must be evaluated.

**Architecture:** Add a small Canonical IR gate-evidence reader that summarizes validated `typed_nodes.json`, `source_spans.json`, and manifest `coverage.report`. The pre-clean conversion gate keeps existing report and Markdown fallbacks, but when coverage proves complete typed-node/source-span evidence, the gate analyzes typed-node text instead of reading rendered `converted.md`.

**Tech Stack:** Python worker, `unittest`, existing KBPrep project commands, current Canonical IR manifest/schema helpers.

---

### Task 1: Gate Evidence Contract

**Files:**
- Create: `python/kbprep_worker/canonical_gate_evidence.py`
- Modify: `python/tests/test_conversion_gate.py`

- [x] **Step 1: Write the failing test**

Add `test_pre_clean_conversion_gate_uses_complete_canonical_ir_text_quality_before_rendered_markdown` to `ConversionGateTests`. The test creates a run where `converted.md` contains mojibake, but validated typed nodes/source spans and a complete coverage report contain clean node text. Expected result: the pre-clean gate passes, reports `text_quality_source == "canonical_ir"`, and exposes `canonical_ir_gate_evidence.complete == True`.

- [x] **Step 2: Run RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_conversion_gate.ConversionGateTests.test_pre_clean_conversion_gate_uses_complete_canonical_ir_text_quality_before_rendered_markdown -v
```

Expected: FAIL because the current gate reads `converted.md` and emits `E_CONVERTED_TEXT_*`.

- [x] **Step 3: Implement the evidence reader**

Create `canonical_gate_evidence.py` with:

- `build_canonical_ir_gate_evidence(run_dir: Path) -> dict[str, Any]`
- Safe JSON reads that return incomplete evidence instead of throwing.
- Complete status only when typed nodes and source spans are available, validated in the coverage report, span coverage ratio is `1.0`, and span count equals typed-node count.
- `text_quality` based on joined typed-node text through existing `analyze_text_quality`.

- [x] **Step 4: Integrate the pre-clean gate**

Modify `python/kbprep_worker/quality/conversion_gate.py` so `_converted_quality` accepts Canonical IR gate evidence. Priority:

1. Complete Canonical IR typed-node text quality.
2. Converter-provided post-convert quality from `conversion_report`.
3. Existing rendered Markdown fallback.

Report fields:

- `text_quality_source`
- `canonical_ir_gate_evidence`
- existing `converted_text_quality` remains for compatibility.

- [x] **Step 5: Run GREEN**

Run the RED command again. Expected: PASS.

### Task 2: Regression Boundaries

**Files:**
- Modify: `python/tests/test_conversion_gate.py`

- [x] **Step 1: Add incomplete IR fallback test**

Add `test_pre_clean_conversion_gate_falls_back_to_rendered_markdown_when_ir_coverage_is_incomplete`. It uses the same garbled `converted.md` but a coverage ratio below `1.0`. Expected result: gate fails with `E_CANONICAL_IR_COVERAGE_REPORT_INVALID` or converted-text quality failure and reports `text_quality_source != "canonical_ir"`.

- [x] **Step 2: Run targeted tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_conversion_gate -v
```

Expected: all conversion gate tests pass.

### Task 3: Stage And Status Docs

**Files:**
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`
- Modify: `docs/development/00-current-state-and-gap.md`
- Modify: `docs/development/02-canonical-ir-contract.md`
- Modify: `docs/development/04-conversion-quality-gate.md`
- Modify: `docs/quality-loop.md`
- Modify: `docs/known-issues.md`

- [x] **Step 1: Update wording conservatively**

Mark C5 as landed for the pre-clean gate evidence slice, but keep `canonical_ir_contract` and `conversion_quality_gate` as `partial`. State that route-native spans, relationships, assets, annotations, Markdown regeneration from IR, and universal fact-layer usage remain future work.

- [x] **Step 2: Add evidence references**

Add `python/kbprep_worker/canonical_gate_evidence.py` and `python/tests/test_conversion_gate.py` to relevant status evidence.

- [x] **Step 3: Search for overclaims**

Run:

```powershell
rg -n "canonical_ir_contract.*implemented|Canonical IR is the complete|all conversion routes have complete|renderable Markdown can be regenerated" docs python src -g "!**/__pycache__/**"
```

Expected: only conservative target or prohibited-claim wording remains.

### Task 4: Verification And Closure

**Files:**
- All task-related files.

- [x] **Step 1: Run focused Python checks**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_conversion_gate python.tests.test_canonical_ir_manifest python.tests.test_canonical_ir_schema -v
npm run python:test
npm run python:ruff
npm run python:typecheck
npm run python:check-size
```

- [x] **Step 2: Run governance and full checks**

Run:

```powershell
npm run check:development-docs
npm run check:flowchart
$env:KBPREP_ALLOW_CORE_DOC_EDIT='1'; npm run dev:check
npm run dev:full-check
git diff --check
```

- [x] **Step 3: Subagent review**

Dispatch a reviewer for C5 spec compliance and code quality. Fix Critical or Important issues, then dispatch re-review.

- [x] **Step 4: Commit, push, and authorized merge**

After verification and review pass, stage only task-related files, commit, and push `codex/phase-c5-canonical-ir-gate`. Merge to `main` and push `main` only when the active owner request explicitly authorizes that outcome, then verify remote CI if available.
