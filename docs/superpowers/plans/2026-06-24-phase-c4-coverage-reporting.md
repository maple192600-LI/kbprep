# Phase C4 Coverage Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add complete Canonical IR coverage reporting for the currently shipped typed-node, source-span, and TransformationLedger artifacts without promoting Phase C or the Canonical IR contract to complete.

**Architecture:** Keep `python/kbprep_worker/canonical_ir.py` below the file-size limit by adding a focused `canonical_coverage.py` module. The manifest will keep existing booleans for compatibility and add a structured `coverage.report` object that records node counts, span counts, coverage ratios, validation state, and route-native precision gaps. The pre-clean conversion gate will validate the report when the manifest claims typed-node or source-span availability.

**Tech Stack:** Python worker modules, `unittest` through `node scripts/python-venv.mjs`, existing manifest validation, project docs and governance checks.

---

## Scope

Allowed code changes:

- Create `python/kbprep_worker/canonical_coverage.py`
- Modify `python/kbprep_worker/canonical_ir.py`
- Modify `python/tests/test_canonical_ir_manifest.py`
- Modify `python/tests/test_conversion_gate.py`

Allowed docs changes:

- Modify `docs/development/README.md`
- Modify `docs/development/development-roadmap.md`
- Modify `docs/development/00-current-state-and-gap.md`
- Modify `docs/development/02-canonical-ir-contract.md`
- Modify `docs/development/04-conversion-quality-gate.md`
- Modify `docs/development/kbprep-implementation-status.json`
- Modify `docs/known-issues.md`

Forbidden scope:

- Do not edit `docs/kbprep-core-flow-design.md` or `docs/kbprep-full-flowchart.html`.
- Do not promote `canonical_ir_contract` or `conversion_quality_gate` to `implemented`.
- Do not make C5 changes where cleanup or final publication depends on full IR semantics.
- Do not change converter routing, source-side publication, cleanup rules, or feedback promotion behavior.

## Task 1: Add Coverage Report Artifact Logic

- [ ] **Step 1: Write failing manifest test**

Add assertions in `python/tests/test_canonical_ir_manifest.py::CanonicalIrManifestTests.test_prepare_writes_canonical_ir_and_document_manifests` that expect:

```python
coverage_report = canonical_manifest["coverage"]["report"]
self.assertEqual(coverage_report["schema"], "kbprep.canonical_ir_coverage_report.v1")
self.assertEqual(coverage_report["typed_nodes"]["status"], "validated")
self.assertEqual(coverage_report["typed_nodes"]["node_count"], typed_nodes["node_count"])
self.assertEqual(coverage_report["source_spans"]["status"], "validated")
self.assertEqual(coverage_report["source_spans"]["span_count"], typed_nodes["node_count"])
self.assertEqual(coverage_report["source_spans"]["typed_node_coverage_ratio"], 1.0)
self.assertIn("route_native_precision", coverage_report["gaps"])
self.assertEqual(coverage_report["transformation_ledger"]["status"], "validated")
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_manifest.CanonicalIrManifestTests.test_prepare_writes_canonical_ir_and_document_manifests -v
```

Expected: fail with missing `coverage["report"]`.

- [ ] **Step 3: Implement coverage module**

Create `python/kbprep_worker/canonical_coverage.py` with:

- constants for `kbprep.canonical_ir_coverage_report.v1`
- frozen dataclass `CoverageReportValidationIssue`
- `build_canonical_ir_coverage_report(...)`
- `validate_canonical_ir_coverage_report(...)`
- small private helpers that read JSON, count typed-node types and span precision, compute source-span coverage ratio, report validation status, and flag target gaps for route-native precision, relationships, assets, annotations, and IR markdown regeneration.

- [ ] **Step 4: Thread report into manifest**

Modify `python/kbprep_worker/canonical_ir.py` so `_coverage_snapshot(...)` includes:

```python
"report": build_canonical_ir_coverage_report(...)
```

Keep existing booleans unchanged for compatibility.

- [ ] **Step 5: Verify GREEN**

Run the same target test and expect pass.

## Task 2: Make The Conversion Gate Validate Coverage Claims

- [ ] **Step 1: Write failing gate tests**

Add two tests in `python/tests/test_conversion_gate.py`:

- `test_pre_clean_conversion_gate_fails_when_typed_nodes_available_lacks_coverage_report`
- `test_pre_clean_conversion_gate_fails_when_source_span_coverage_report_is_incomplete`

Both tests should use valid artifacts, then corrupt only `coverage.report`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_conversion_gate.ConversionGateTests.test_pre_clean_conversion_gate_fails_when_typed_nodes_available_lacks_coverage_report python.tests.test_conversion_gate.ConversionGateTests.test_pre_clean_conversion_gate_fails_when_source_span_coverage_report_is_incomplete -v
```

Expected: fail because the gate does not yet validate `coverage.report`.

- [ ] **Step 3: Implement manifest validation**

Modify `python/kbprep_worker/canonical_ir.py` to call `validate_canonical_ir_coverage_report(...)` from `_validate_coverage_snapshot(...)` after the existing boolean shape checks.

Expected validation behavior:

- If `typed_nodes_available` is true, report must have `typed_nodes.status == "validated"` and a positive `node_count`.
- If `source_spans_available` is true, report must have `source_spans.status == "validated"` and `typed_node_coverage_ratio == 1.0`.
- If `transformation_ledger_available` is true, report must have `transformation_ledger.status == "validated"`.

- [ ] **Step 4: Verify GREEN**

Run both target gate tests again and expect pass.

## Task 3: Sync Docs And Status

- [ ] **Step 1: Fix README drift**

Change `docs/development/README.md` planning entry from:

```markdown
- `kbprep-development-implementation-plan.md`
```

to:

```markdown
- `docs/kbprep-development-implementation-plan.md`
```

- [ ] **Step 2: Update Phase C docs conservatively**

Update the roadmap, current-state gap doc, Canonical IR stage doc, conversion gate stage doc, status JSON, and known issues to say C4 coverage reporting is landed but C5 and full Canonical IR fact-layer use remain open.

- [ ] **Step 3: Search stale claims**

Run:

```powershell
rg -n "C4|complete coverage reporting|canonical_ir_contract.*implemented|Phase C.*complete|Canonical IR is the complete shipped worker fact layer|quality gate reads complete typed-node" docs python src -g "!docs/superpowers/plans/**"
```

Expected: no overclaiming that Phase C or Canonical IR is fully implemented.

## Task 4: Review And Verification

- [ ] **Step 1: Run focused Python checks**

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_manifest python.tests.test_conversion_gate python.tests.test_canonical_ir_source_spans python.tests.test_canonical_ir_ledger -v
```

- [ ] **Step 2: Run required project checks**

```powershell
npm run python:test
npm run python:ruff
npm run python:typecheck
$env:KBPREP_ALLOW_CORE_DOC_EDIT='1'; npm run dev:check
git diff --check
```

- [ ] **Step 3: Subagent review**

Dispatch a reviewer subagent to inspect the branch for C4 scope, correctness, missing tests, docs drift, and overclaiming. Fix all Critical and Important findings, then run a second reviewer pass.

## Acceptance

C4 is accepted only when all are true:

- Canonical IR manifest contains a structured `coverage.report`.
- Existing `typed_nodes_available`, `source_spans_available`, and `transformation_ledger_available` booleans remain backward compatible.
- The conversion gate rejects manifest claims when coverage report evidence is missing or incomplete.
- Docs mark C4 as landed without promoting C5 or full Phase C.
- `docs/development/README.md` no longer points at a nonexistent relative implementation-plan path.
- Required checks pass, or any failure is reported with exact command, cause, and product impact.
