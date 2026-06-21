# Phase B PDF Routing Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore Phase B PDF routing so simple trusted real PDFs can use the Tier 1 `pymupdf4llm` path, complex PDFs still use MinerU appropriately, OCR is reserved for real text-layer risk, and future real-data checks fail on suspicious routing distributions instead of mislabeling them as missing samples.

**Architecture:** Fix the root causes at the diagnosis and route-policy boundaries, then protect them with real-data distribution checks and gray-zone fixtures. Keep threshold constants centralized in `DIAGNOSIS_THRESHOLDS`, share MinerU mode and fallback logic across main and external PDF paths, and update capability documentation only after current verification evidence is available.

**Tech Stack:** Python worker (`unittest`, Ruff, mypy), TypeScript/Vitest worker scenarios, Node.js vault smoke script, KBPrep project commands only.

---

## Scope And Evidence Baseline

- Current real-data failure: `npm run vault:pdf-phase-b` reports missing `simple_single_column` and `english_simple_text`.
- Current route distribution observed through project CLI on the local vault: `tier_1=0`, `tier_2=22`, `tier_3=8`.
- Confirmed code roots:
  - `python/kbprep_worker/diagnose/pdf_analysis.py` treats any positive structure-signal page as `complex`.
  - `python/kbprep_worker/diagnose/pdf_route_diagnostics.py` treats any positive `control` or `non_common` ratio as OCR risk.
  - `python/kbprep_worker/stages/external_conversion.py` has a separate generated-PDF route and fallback copy that does not fully honor Phase B strategy selection.
  - `scripts/check-vault-pdf-phase-b.mjs` validates class collection but does not reject abnormal tier distributions.

## Task 1: Record Red Tests For PDF Thresholds

**Files:**
- Modify: `python/tests/test_pdf_route_diagnostics.py`
- Modify or create: `python/tests/test_pdf_analysis.py`

- [ ] **Step 1: Add diagnostics tests for gray-zone trusted PDFs**

Add tests showing:

```python
def test_sparse_structure_signals_stay_tier_1(self) -> None:
    diagnosis = {
        "page_count": 126,
        "sampled_page_count": 22,
        "text_layer_health": "good",
        "needs_ocr": False,
        "pdf_subtype": "text_layer",
        "layout_profile": "document_pages",
        "layout_complexity": "simple",
        "multi_column_pages": 1,
        "table_pages": 1,
        "image_text_interleaved_pages": 0,
        "image_pages": 0,
        "text_pages": 22,
        "text_quality": {
            "unreadable_text_ratio": 0.0,
            "garbled_ratio": 0.0,
            "mojibake_ratio": 0.0,
            "replacement_char_ratio": 0.0,
            "control_ratio": 0.0,
            "non_common_unicode_ratio": 0.0,
        },
    }
    diagnostics = build_pdf_route_diagnostics(diagnosis)
    self.assertEqual(diagnostics["recommended_tier"], "tier_1")
    self.assertEqual(diagnostics["recommended_route"], "pymupdf4llm")
```

```python
def test_tiny_control_noise_stays_tier_1(self) -> None:
    diagnosis = {
        "page_count": 337,
        "sampled_page_count": 43,
        "text_layer_health": "good",
        "needs_ocr": False,
        "pdf_subtype": "text_layer",
        "layout_profile": "document_pages",
        "layout_complexity": "simple",
        "multi_column_pages": 0,
        "table_pages": 0,
        "image_text_interleaved_pages": 0,
        "image_pages": 0,
        "text_pages": 43,
        "text_quality": {
            "unreadable_text_ratio": 0.0,
            "garbled_ratio": 0.0,
            "mojibake_ratio": 0.0,
            "replacement_char_ratio": 0.0,
            "control_ratio": 0.0015,
            "non_common_unicode_ratio": 0.0,
        },
    }
    diagnostics = build_pdf_route_diagnostics(diagnosis)
    self.assertEqual(diagnostics["recommended_tier"], "tier_1")
    self.assertEqual(diagnostics["ocr_triggers"], [])
```

- [ ] **Step 2: Add boundary tests for real complex and OCR-risk PDFs**

Add tests showing:

```python
def test_systemic_structure_signals_route_tier_2(self) -> None:
    diagnosis = {
        "page_count": 20,
        "sampled_page_count": 20,
        "text_layer_health": "good",
        "needs_ocr": False,
        "pdf_subtype": "text_layer",
        "layout_profile": "document_pages",
        "layout_complexity": "complex",
        "multi_column_pages": 8,
        "table_pages": 1,
        "image_text_interleaved_pages": 0,
        "image_pages": 0,
        "text_pages": 20,
        "text_quality": {
            "unreadable_text_ratio": 0.0,
            "garbled_ratio": 0.0,
            "mojibake_ratio": 0.0,
            "replacement_char_ratio": 0.0,
            "control_ratio": 0.0,
            "non_common_unicode_ratio": 0.0,
        },
    }
    diagnostics = build_pdf_route_diagnostics(diagnosis)
    self.assertEqual(diagnostics["recommended_tier"], "tier_2")
```

```python
def test_high_control_ratio_routes_tier_3(self) -> None:
    diagnosis = {
        "page_count": 40,
        "sampled_page_count": 40,
        "text_layer_health": "good",
        "needs_ocr": False,
        "pdf_subtype": "text_layer",
        "layout_profile": "document_pages",
        "layout_complexity": "simple",
        "multi_column_pages": 0,
        "table_pages": 0,
        "image_text_interleaved_pages": 0,
        "image_pages": 0,
        "text_pages": 40,
        "text_quality": {
            "unreadable_text_ratio": 0.0,
            "garbled_ratio": 0.0,
            "mojibake_ratio": 0.0,
            "replacement_char_ratio": 0.0,
            "control_ratio": 0.03,
            "non_common_unicode_ratio": 0.0,
        },
    }
    diagnostics = build_pdf_route_diagnostics(diagnosis)
    self.assertEqual(diagnostics["recommended_tier"], "tier_3")
    self.assertIn("control_character_risk", diagnostics["ocr_triggers"])
```

- [ ] **Step 3: Run RED tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_diagnostics -v
```

Expected before implementation: sparse structure and tiny control noise tests fail because current code routes them away from Tier 1.

## Task 2: Implement PDF Threshold Fixes

**Files:**
- Modify: `python/kbprep_worker/quality/thresholds.py`
- Modify: `python/kbprep_worker/diagnose/pdf_analysis.py`
- Modify: `python/kbprep_worker/diagnose/pdf_route_diagnostics.py`

- [ ] **Step 1: Add named thresholds**

In `DIAGNOSIS_THRESHOLDS`, add:

```python
"pdf_structure_signal_ratio_complex": 0.20,
"pdf_text_risk_control_ratio": 0.02,
"pdf_text_risk_non_common_ratio": 0.02,
"pdf_text_risk_replacement_ratio": 0.02,
```

- [ ] **Step 2: Replace any-page structure complexity with ratio complexity**

Add a helper in `pdf_analysis.py`:

```python
def _structure_signal_ratio(result: dict) -> float:
    denominator = _page_ratio_denominator(result)
    if denominator <= 0:
        return 0.0
    signals = (
        _positive_count(result.get("multi_column_pages")),
        _positive_count(result.get("table_pages")),
        _positive_count(result.get("image_text_interleaved_pages")),
    )
    return max(signals) / denominator
```

Then change `_pdf_layout_complexity` to use:

```python
if _structure_signal_ratio(result) >= DIAGNOSIS_THRESHOLDS["pdf_structure_signal_ratio_complex"]:
    return "complex"
```

- [ ] **Step 3: Make route diagnostics use the same structure ratio**

In `pdf_route_diagnostics.py`, import `DIAGNOSIS_THRESHOLDS`, compute structure counts and ratio, and stop promoting `simple` to `complex` solely because any structure signal exists.

Expected helper shape:

```python
def _structure_signal_ratio(diagnosis: dict[str, Any]) -> float:
    denominator = _coverage_denominator(
        diagnosis,
        _int_value(diagnosis.get("page_count")),
        _int_value(diagnosis.get("sampled_page_count")),
    )
    if denominator <= 0:
        return 0.0
    counts = (
        _int_value(diagnosis.get("multi_column_pages")),
        _int_value(diagnosis.get("table_pages")),
        _int_value(diagnosis.get("image_text_interleaved_pages")),
    )
    return round(max(counts) / denominator, 4)
```

- [ ] **Step 4: Replace text-risk bare `> 0` checks**

Use the new thresholds:

```python
"replacement_character_risk": replacement >= DIAGNOSIS_THRESHOLDS["pdf_text_risk_replacement_ratio"],
"control_character_risk": control >= DIAGNOSIS_THRESHOLDS["pdf_text_risk_control_ratio"],
"private_use_or_control_risk": (
    non_common >= DIAGNOSIS_THRESHOLDS["pdf_text_risk_non_common_ratio"]
    or control >= DIAGNOSIS_THRESHOLDS["pdf_text_risk_control_ratio"]
),
```

- [ ] **Step 5: Run GREEN tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_diagnostics -v
```

Expected: all diagnostics tests pass.

## Task 3: Add Gray-Zone Worker Scenario

**Files:**
- Modify: `src/test/scenarios/worker-pdf-routing-part2.test.ts`

- [ ] **Step 1: Add a direct Python scenario test using a mocked gray-zone diagnosis**

Add a Vitest case that patches `kbprep_worker.diagnose.pdf_analysis.analyze_pdf` to return a trusted PDF diagnosis with sparse structure signals and tiny control noise, then runs `prepare.run()` with `pymupdf4llm_adapter.convert_pymupdf4llm_pdf` patched to produce readable Markdown.

Expected assertions:

```typescript
assert decision['selected_pdf_tier'] == 'tier_1', decision
assert decision['selected_route'] == 'pymupdf4llm', decision
assert report['converter'] == 'pymupdf4llm', report
```

- [ ] **Step 2: Run RED/GREEN around the scenario**

Run:

```powershell
npm test -- src/test/scenarios/worker-pdf-routing-part2.test.ts
```

Expected after Task 2: the new scenario passes and protects the gray-zone behavior through the TypeScript worker surface.

## Task 4: Unify PDF Strategy And Fallback For External Conversion

**Files:**
- Modify: `python/kbprep_worker/stages/pipeline_helpers.py`
- Modify: `python/kbprep_worker/stages/pipeline_conversion.py`
- Modify: `python/kbprep_worker/stages/external_conversion.py`
- Modify related Python tests or add `python/tests/test_external_conversion.py`

- [ ] **Step 1: Add RED test for generated PDF `mineru_txt` mode**

Add a test that makes `external_conversion._convert_generated_pdf()` receive a diagnosis with `pdf_route_diagnostics.recommended_route = "mineru_txt"` and asserts `_run_mineru_conversion` is called with mode `"txt"`.

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_external_conversion -v
```

Expected before implementation: it fails because current `external_conversion.py` maps non-OCR MinerU strategies to `"auto"`.

- [ ] **Step 2: Move `_mineru_mode_for_strategy` to `pipeline_helpers.py`**

Implement:

```python
def _mineru_mode_for_strategy(strategy: object) -> str:
    value = str(strategy or "")
    if value == "mineru_txt":
        return "txt"
    if value == "mineru_ocr":
        return "ocr"
    return "auto"
```

Import it in both `pipeline_conversion.py` and `external_conversion.py`.

- [ ] **Step 3: Move PDF markdown fallback to `pipeline_helpers.py`**

Move `_maybe_fallback_pdf_markdown_to_mineru()` and `_pdf_fallback_warning()` into `pipeline_helpers.py`. Keep the existing report fields:

```python
fallback["fallback_from"] = source_route
fallback["fallback_reason"] = "post_convert_text_unreadable"
fallback["rejected_text_layer_md"] = str(rejected_path)
fallback["rejected_markdown_path"] = str(rejected_path)
fallback["rejected_text_layer_quality"] = rejected_quality
fallback["post_convert_text_quality"] = _converted_text_quality(ocr_text)
```

- [ ] **Step 4: Update external generated-PDF conversion**

Use shared policy for generated PDFs:

```python
from ..pdf_route_policy import selected_pdf_strategy

strategy = selected_pdf_strategy(pdf_diagnosis)
if strategy in {"pymupdf4llm", "pdf_text_layer"}:
    artifacts = _convert_generated_pdf_text_route(pdf_path, converted_path, run_dir, language, strategy)
else:
    mode = _mineru_mode_for_strategy(strategy)
    artifacts = _run_mineru_conversion(pdf_path, converted_path, run_dir, language, mode)
    artifacts["mineru_mode"] = mode
```

Generated `pymupdf4llm` and `pdf_text_layer` routes should both use the shared fallback helper with `source_route` set correctly.

- [ ] **Step 5: Run GREEN tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_external_conversion -v
```

Expected: generated PDF `mineru_txt` test passes and fallback fields stay aligned.

## Task 5: Upgrade Real Vault Phase B Smoke

**Files:**
- Modify: `scripts/check-vault-pdf-phase-b.mjs`

- [ ] **Step 1: Add tier and route distribution reporting**

Add functions:

```javascript
function countBy(items, mapper) {
  const counts = {};
  for (const item of items) {
    const key = mapper(item) || "unknown";
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}
```

Include `tierCounts` and `routeCounts` in both success and failure output.

- [ ] **Step 2: Add zero-hit alarm for Tier 1**

Add:

```javascript
const MIN_TIER_1_HITS = Number(process.env.KBPREP_VAULT_PDF_MIN_TIER_1 || "3");
const tierCounts = countBy(diagnoses, tier);
if ((tierCounts.tier_1 || 0) < MIN_TIER_1_HITS) {
  failWithEvidence(
    `PDF diagnosis distribution is suspicious: tier_1 hit count ${tierCounts.tier_1 || 0} is below ${MIN_TIER_1_HITS}. This usually means thresholds or route diagnostics are over-gating simple PDFs.`,
    { pdfCount: pdfs.length, diagnosedCount: diagnoses.length, tierCounts, routeCounts: countBy(diagnoses, route), missing },
  );
}
```

- [ ] **Step 3: Make missing-class errors include evidence**

Replace bare `fail()` for missing classes with an evidence payload that distinguishes suspicious distribution from likely sample absence.

- [ ] **Step 4: Run the script**

Run:

```powershell
npm run vault:pdf-phase-b
```

Expected after Tasks 1-2: `tier_1` is no longer zero. If a class is still missing, the output must show whether the distribution itself is now healthy.

## Task 6: Update Capability Status And Docs From Fresh Evidence

**Files:**
- Modify: `python/kbprep_worker/converter_capabilities.py`
- Modify: `docs/capability-matrix.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/00-current-state-and-gap.md`
- Modify: `docs/known-issues.md`
- Modify: related tests that assert old blocker wording

- [ ] **Step 1: Decide status from fresh `npm run vault:pdf-phase-b` output**

If all six classes pass and tier distribution is healthy, promote `pdf_diagnosis_selected` to `verified` with named evidence. If a class remains missing but tier distribution is healthy, keep `partial` and write the blocker as sample absence after threshold calibration, not as uninvestigated missing classes.

- [ ] **Step 2: Remove stale root-cause wording**

Replace wording that implies the only problem is missing classes with wording that reflects the fresh evidence.

- [ ] **Step 3: Update tests that intentionally inspect blocker wording**

For example, update `src/test/scenarios/worker-core-runtime-part2.test.ts` if it asserts old `"golden"` wording that no longer matches the truth.

- [ ] **Step 4: Run governance-relevant checks later through `dev:full-check`**

Do not claim docs are aligned until the final verification suite completes.

## Task 7: Add Setup Environment Regression Coverage

**Files:**
- Modify or create: `python/tests/test_setup_env.py`
- Optionally move focused setup tests out of broad coverage-helper tests if this reduces duplication.

- [ ] **Step 1: Add tests for backend recommendation**

Cover:

```python
self.assertEqual(setup_env.suggest_mineru_backend({"available": False})[0], "pipeline")
self.assertEqual(setup_env.suggest_mineru_backend({"available": True, "vram_gb": 16, "device_name": "RTX"})[0], "hybrid-engine")
self.assertEqual(setup_env.suggest_mineru_backend({"available": True, "vram_gb": 6, "device_name": "RTX"})[0], "pipeline")
```

- [ ] **Step 2: Add tests for backend override**

Cover valid, invalid, and empty override through `choose_mineru_backend()`.

- [ ] **Step 3: Add tests for install order**

Mock subprocess so `setup_gpu(..., install_mineru=True)` records CUDA torch installation before `mineru[all]`.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_setup_env -v
```

Expected: setup-env pure logic tests pass without installing real dependencies.

## Task 8: Clarify Conservative Unknown-PDF Fallback

**Files:**
- Modify: `python/kbprep_worker/pdf_route_policy.py`

- [ ] **Step 1: Add a concise comment or docstring note**

Explain that when neither Phase B diagnostics nor a legacy strategy exists, KBPrep chooses `mineru_ocr` as a conservative fallback because unknown PDF evidence must not bypass OCR-safe handling.

- [ ] **Step 2: Keep existing behavior**

Do not change the fallback route unless tests and product evidence require it.

## Final Verification

Run these commands fresh, in this order:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_diagnostics -v
node scripts/python-venv.mjs -m unittest python.tests.test_external_conversion -v
node scripts/python-venv.mjs -m unittest python.tests.test_setup_env -v
npm test -- src/test/scenarios/worker-pdf-routing-part2.test.ts
npm run vault:pdf-phase-b
npm run dev:full-check
npm run python:ruff
npm run python:typecheck
git diff --check
```

Completion requires:

- Real vault smoke no longer has `tier_1=0`.
- The smoke script fails loudly if future runs produce suspicious zero-hit Tier 1 distributions.
- Main PDF and generated-PDF routes use the same Phase B strategy semantics.
- Capability docs match fresh evidence and do not confuse symptoms with root causes.
- Project-environment checks pass, or any remaining blocker is reported with command, output, product impact, and exact condition needed to finish.
