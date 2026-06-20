# PDF Diagnostic Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auditable PDF route diagnostic signals for Phase B1 so later Tier 1, Tier 2, and Tier 3 routing can change converter behavior with clear evidence.

**Architecture:** Keep the current converter behavior stable in this slice: trusted simple PDFs still use the existing `pdf_text_layer` route, complex trusted PDFs still use `mineru_auto`, and untrusted or scanned PDFs still use `mineru_ocr`. Add a structured `pdf_route_diagnostics` evidence object during diagnosis, copy a concise tier summary into `conversion_report.json.route_decision`, and preserve the full evidence in both diagnosis and conversion reports.

**Tech Stack:** Python worker modules under `python/kbprep_worker`, PyMuPDF via the project runtime, Python `unittest` through `node scripts/python-venv.mjs`, TypeScript Vitest scenario tests through `npm test`, KBPrep governance checks through `npm run dev:check`.

---

## Current Progress Evidence

- Current branch before this plan: `codex/status-surface-governance-depth`, clean against `origin/codex/status-surface-governance-depth`.
- Roadmap next phase: `docs/development/development-roadmap.md` names Phase B as PDF Three-Tier Routing.
- Roadmap next slice: B1 adds diagnostic signals for multi-column layout, table-heavy layout, image/text interleaving, CID or ToUnicode risk, image coverage ratio, and large-PDF sampling.
- Current PDF diagnosis truth: `python/kbprep_worker/diagnose/pdf_analysis.py` already computes `pdf_subtype`, `text_layer_health`, `image_page_ratio`, `layout_profile`, `layout_complexity`, `recommended_pipeline`, `conversion_strategy`, and `processing_hints`.
- Current report truth: `python/kbprep_worker/prepare_diagnosis.py` writes `diagnosis_report.json`; `python/kbprep_worker/stages/pipeline_helpers.py` writes `conversion_report.json` and `route_decision`.
- Current gap: no standardized `pdf_route_diagnostics` object exists, and `route_decision` does not record the recommended PDF tier or a tier reason.

## Next Development Decision

Implement **Phase B1: PDF diagnostic signals** first.

This is the smallest safe next task because it improves evidence without changing the actual conversion route or adding a new dependency. It also prevents B2-B4 from becoming a hidden behavior rewrite: once B1 lands, the project can compare “recommended tier” against “actual route” before it swaps Tier 1 to `pymupdf4llm` or splits Tier 2 MinerU modes.

## File Structure

- Create: `python/tests/test_pdf_route_diagnostics.py`
  - Unit coverage for the new diagnostic evidence contract without needing full pipeline setup.
- Create: `python/kbprep_worker/diagnose/pdf_route_diagnostics.py`
  - Builds the stable `pdf_route_diagnostics` object from PDF diagnosis data.
- Modify: `python/kbprep_worker/diagnose/pdf_analysis.py`
  - Adds structure signals and large-PDF sampling metadata while keeping ordinary small-PDF diagnosis behavior stable.
  - Calls `build_pdf_route_diagnostics()` before returning PDF diagnosis.
- Modify: `python/kbprep_worker/quality/thresholds.py`
  - Adds named thresholds for large-PDF sampling and structure heuristics.
- Modify: `python/kbprep_worker/prepare_diagnosis.py`
  - Exposes `pdf_route_diagnostics` at the top level of `diagnosis_report.json`.
- Modify: `python/kbprep_worker/stages/pipeline_helpers.py`
  - Exposes full `pdf_route_diagnostics` in `conversion_report.json`.
  - Adds `selected_pdf_tier`, `pdf_route_reason`, and `pdf_route_diagnostics_schema` to `route_decision` for PDFs.
- Modify: `src/test/scenarios/worker-batch-long-docs-part2.test.ts`
  - Scenario-level diagnosis assertions for existing PDF fixtures.
- Modify: `src/test/scenarios/worker-pdf-routing.test.ts`
  - Pipeline report assertions proving `route_decision` records the tier summary.
- Modify: `docs/development/development-roadmap.md`
  - Marks B1 as landed after tests pass, while leaving B2-B5 open.
- Modify: `docs/capability-matrix.md`
  - Updates the `pdf_diagnosis_selected` row evidence language to say diagnostic tier evidence exists, while keeping status `partial`.
- Modify: `docs/development/kbprep-implementation-status.json`
  - Adds B1 code and test evidence to the partial `pdf_three_tier_routing` capability entry if that entry exists in the current file at execution time.

Protected files not changed:

- `docs/kbprep-core-flow-design.md`
- `docs/kbprep-full-flowchart.html`
- `docs/flowchart/kbprep-flow.json`

## Forbidden Scope

- Do not change actual PDF conversion behavior in this slice.
- Do not add `pymupdf4llm` as a runtime dependency in this slice.
- Do not promote `pdf_diagnosis_selected` to `verified`.
- Do not claim six fixture acceptance is complete.
- Do not edit protected design semantics.
- Do not add agent-host adapter logic.
- Do not run direct system Python as completion evidence.

### Task 1: Add Python RED Tests For The Diagnostic Contract

**Files:**
- Create: `python/tests/test_pdf_route_diagnostics.py`

- [ ] **Step 1: Add the failing unit test file**

Create `python/tests/test_pdf_route_diagnostics.py` with this exact content:

```python
import unittest

from kbprep_worker.diagnose.pdf_route_diagnostics import build_pdf_route_diagnostics


class PDFRouteDiagnosticsTests(unittest.TestCase):
    def test_simple_trusted_text_layer_recommends_tier_1(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 2,
            "text_pages": 2,
            "image_pages": 0,
            "image_count": 0,
            "text_layer_health": "good",
            "needs_ocr": False,
            "layout_complexity": "simple",
            "layout_profile": "document_pages",
            "pdf_subtype": "text_layer",
            "text_quality": {
                "garbled_ratio": 0.0,
                "unreadable_text_ratio": 0.0,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.0,
                "control_ratio": 0.0,
            },
        })

        self.assertEqual(diagnostics["schema"], "kbprep.pdf_route_diagnostics.v1")
        self.assertTrue(diagnostics["text_layer"]["trusted"])
        self.assertEqual(diagnostics["image_coverage"]["ratio"], 0.0)
        self.assertEqual(diagnostics["layout_complexity"]["level"], "simple")
        self.assertEqual(diagnostics["recommended_tier"], "tier_1")
        self.assertEqual(diagnostics["recommended_route"], "pymupdf4llm")
        self.assertEqual(diagnostics["ocr_triggers"], [])

    def test_complex_trusted_text_layer_recommends_tier_2(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 4,
            "text_pages": 4,
            "image_pages": 0,
            "image_count": 0,
            "text_layer_health": "good",
            "needs_ocr": False,
            "layout_complexity": "complex",
            "layout_profile": "slide_deck_or_ppt_export",
            "pdf_subtype": "ppt_exported_text_layer",
            "multi_column_pages": 1,
            "table_pages": 0,
            "image_text_interleaved_pages": 0,
            "text_quality": {
                "garbled_ratio": 0.0,
                "unreadable_text_ratio": 0.0,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.0,
                "control_ratio": 0.0,
            },
        })

        self.assertTrue(diagnostics["text_layer"]["trusted"])
        self.assertEqual(diagnostics["layout_complexity"]["level"], "complex")
        self.assertTrue(diagnostics["structure_signals"]["multi_column"])
        self.assertTrue(diagnostics["structure_signals"]["slide_like"])
        self.assertEqual(diagnostics["recommended_tier"], "tier_2")
        self.assertEqual(diagnostics["recommended_route"], "mineru_auto")

    def test_untrusted_text_layer_recommends_tier_3(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 6,
            "text_pages": 6,
            "image_pages": 0,
            "image_count": 0,
            "text_layer_health": "bad",
            "needs_ocr": True,
            "layout_complexity": "simple",
            "layout_profile": "document_pages",
            "pdf_subtype": "garbled_text_layer",
            "text_quality": {
                "garbled_ratio": 0.3,
                "unreadable_text_ratio": 0.3,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.2,
                "control_ratio": 0.0,
            },
        })

        self.assertFalse(diagnostics["text_layer"]["trusted"])
        self.assertTrue(diagnostics["text_risk"]["cid_or_tounicode_risk"])
        self.assertIn("untrusted_text_layer", diagnostics["ocr_triggers"])
        self.assertEqual(diagnostics["recommended_tier"], "tier_3")
        self.assertEqual(diagnostics["recommended_route"], "mineru_ocr")

    def test_scanned_or_image_heavy_pdf_recommends_tier_3(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 10,
            "text_pages": 1,
            "image_pages": 9,
            "image_count": 9,
            "text_layer_health": "no_text_layer",
            "needs_ocr": True,
            "layout_complexity": "complex",
            "layout_profile": "image_heavy_document",
            "pdf_subtype": "image_only_or_scanned",
            "text_quality": {
                "garbled_ratio": 0.0,
                "unreadable_text_ratio": 0.0,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.0,
                "control_ratio": 0.0,
            },
        })

        self.assertEqual(diagnostics["image_coverage"]["ratio"], 0.9)
        self.assertEqual(diagnostics["image_coverage"]["level"], "high")
        self.assertIn("high_image_coverage", diagnostics["ocr_triggers"])
        self.assertEqual(diagnostics["recommended_tier"], "tier_3")

    def test_large_pdf_sampling_metadata_is_preserved(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 120,
            "text_pages": 15,
            "image_pages": 0,
            "image_count": 0,
            "text_layer_health": "good",
            "needs_ocr": False,
            "layout_complexity": "simple",
            "layout_profile": "document_pages",
            "large_pdf_sampling_applied": True,
            "large_pdf_sampled_pages": 21,
            "large_pdf_sample_strategy": "first_5_last_5_stride_10",
            "text_quality": {
                "garbled_ratio": 0.0,
                "unreadable_text_ratio": 0.0,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.0,
                "control_ratio": 0.0,
            },
        })

        self.assertTrue(diagnostics["large_pdf_sampling"]["applied"])
        self.assertEqual(diagnostics["large_pdf_sampling"]["sampled_pages"], 21)
        self.assertEqual(diagnostics["large_pdf_sampling"]["strategy"], "first_5_last_5_stride_10")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the RED test**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_diagnostics -v
```

Expected result:

```text
ModuleNotFoundError: No module named 'kbprep_worker.diagnose.pdf_route_diagnostics'
```

Commit nothing in this task.

### Task 2: Implement The PDF Route Diagnostics Builder

**Files:**
- Create: `python/kbprep_worker/diagnose/pdf_route_diagnostics.py`
- Test: `python/tests/test_pdf_route_diagnostics.py`

- [ ] **Step 1: Add the builder module**

Create `python/kbprep_worker/diagnose/pdf_route_diagnostics.py` with this exact content:

```python
"""Auditable PDF route diagnostic evidence."""

from __future__ import annotations

from typing import Any

PDF_ROUTE_DIAGNOSTICS_SCHEMA = "kbprep.pdf_route_diagnostics.v1"


def build_pdf_route_diagnostics(diagnosis: dict[str, Any]) -> dict[str, Any]:
    text_layer = _text_layer_summary(diagnosis)
    image_coverage = _image_coverage_summary(diagnosis)
    structure = _structure_signals(diagnosis)
    text_risk = _text_risk_signals(diagnosis)
    ocr_triggers = _ocr_triggers(diagnosis, text_layer, image_coverage, text_risk)
    layout = _layout_complexity_summary(diagnosis, structure)
    recommended_tier = _recommended_tier(text_layer, layout, image_coverage, ocr_triggers)
    return {
        "schema": PDF_ROUTE_DIAGNOSTICS_SCHEMA,
        "text_layer": text_layer,
        "layout_complexity": layout,
        "image_coverage": image_coverage,
        "structure_signals": structure,
        "text_risk": text_risk,
        "large_pdf_sampling": _large_pdf_sampling(diagnosis),
        "ocr_triggers": ocr_triggers,
        "recommended_tier": recommended_tier,
        "recommended_route": _recommended_route(recommended_tier),
        "reason": _reason(recommended_tier, text_layer, layout, image_coverage, ocr_triggers),
    }


def _text_layer_summary(diagnosis: dict[str, Any]) -> dict[str, Any]:
    health = str(diagnosis.get("text_layer_health") or "unknown")
    trusted = health == "good" and not bool(diagnosis.get("needs_ocr"))
    return {
        "health": health,
        "trusted": trusted,
        "pdf_subtype": diagnosis.get("pdf_subtype") or "unknown",
    }


def _image_coverage_summary(diagnosis: dict[str, Any]) -> dict[str, Any]:
    page_count = _int_value(diagnosis.get("page_count"))
    image_pages = _int_value(diagnosis.get("image_pages"))
    text_pages = _int_value(diagnosis.get("text_pages"))
    ratio = round(image_pages / page_count, 4) if page_count else 0.0
    if ratio >= 0.5:
        level = "high"
    elif ratio > 0:
        level = "low"
    else:
        level = "none"
    return {
        "page_count": page_count,
        "image_pages": image_pages,
        "text_pages": text_pages,
        "ratio": ratio,
        "level": level,
    }


def _structure_signals(diagnosis: dict[str, Any]) -> dict[str, bool]:
    layout_profile = str(diagnosis.get("layout_profile") or "")
    return {
        "multi_column": _int_value(diagnosis.get("multi_column_pages")) > 0,
        "table_heavy": _int_value(diagnosis.get("table_pages")) > 0,
        "image_text_interleaving": _int_value(diagnosis.get("image_text_interleaved_pages")) > 0,
        "slide_like": layout_profile == "slide_deck_or_ppt_export",
    }


def _text_risk_signals(diagnosis: dict[str, Any]) -> dict[str, bool]:
    quality = diagnosis.get("text_quality")
    text_quality = quality if isinstance(quality, dict) else {}
    unreadable = _float_value(text_quality.get("unreadable_text_ratio"))
    mojibake = _float_value(text_quality.get("mojibake_ratio"))
    replacement = _float_value(text_quality.get("replacement_char_ratio"))
    control = _float_value(text_quality.get("control_ratio"))
    untrusted = str(diagnosis.get("text_layer_health") or "") in {"bad", "degraded", "untrusted"}
    return {
        "cid_or_tounicode_risk": untrusted and (unreadable > 0 or mojibake > 0),
        "replacement_character_risk": replacement > 0,
        "control_character_risk": control > 0,
    }


def _ocr_triggers(
    diagnosis: dict[str, Any],
    text_layer: dict[str, Any],
    image_coverage: dict[str, Any],
    text_risk: dict[str, bool],
) -> list[str]:
    triggers: list[str] = []
    if bool(diagnosis.get("needs_ocr")):
        triggers.append("diagnosis_needs_ocr")
    if not text_layer["trusted"]:
        triggers.append("untrusted_text_layer")
    if image_coverage["level"] == "high":
        triggers.append("high_image_coverage")
    for key, enabled in text_risk.items():
        if enabled:
            triggers.append(key)
    return _dedupe(triggers)


def _layout_complexity_summary(diagnosis: dict[str, Any], structure: dict[str, bool]) -> dict[str, Any]:
    level = str(diagnosis.get("layout_complexity") or "unknown")
    if level == "unknown" and any(structure.values()):
        level = "complex"
    return {
        "level": level,
        "profile": diagnosis.get("layout_profile") or "unknown",
        "signals": [key for key, enabled in structure.items() if enabled],
    }


def _recommended_tier(
    text_layer: dict[str, Any],
    layout: dict[str, Any],
    image_coverage: dict[str, Any],
    ocr_triggers: list[str],
) -> str:
    if ocr_triggers or image_coverage["level"] == "high" or not text_layer["trusted"]:
        return "tier_3"
    if layout["level"] == "complex":
        return "tier_2"
    return "tier_1"


def _recommended_route(tier: str) -> str:
    routes = {
        "tier_1": "pymupdf4llm",
        "tier_2": "mineru_auto",
        "tier_3": "mineru_ocr",
    }
    return routes[tier]


def _reason(
    tier: str,
    text_layer: dict[str, Any],
    layout: dict[str, Any],
    image_coverage: dict[str, Any],
    ocr_triggers: list[str],
) -> str:
    if tier == "tier_3":
        trigger_text = ", ".join(ocr_triggers) if ocr_triggers else "high image coverage"
        return f"Tier 3 because OCR evidence is present: {trigger_text}."
    if tier == "tier_2":
        return f"Tier 2 because text is trusted but layout is {layout['level']}."
    return f"Tier 1 because text is trusted and layout is {layout['level']} with image coverage {image_coverage['ratio']}."


def _large_pdf_sampling(diagnosis: dict[str, Any]) -> dict[str, Any]:
    return {
        "applied": bool(diagnosis.get("large_pdf_sampling_applied")),
        "sampled_pages": _int_value(diagnosis.get("large_pdf_sampled_pages")),
        "page_count": _int_value(diagnosis.get("page_count")),
        "strategy": diagnosis.get("large_pdf_sample_strategy") or "full_scan",
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def _float_value(value: object) -> float:
    return value if isinstance(value, float | int) else 0.0
```

- [ ] **Step 2: Run the unit tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_diagnostics -v
```

Expected result:

```text
Ran 5 tests
OK
```

- [ ] **Step 3: Commit the builder and unit tests**

Run:

```powershell
git add python/tests/test_pdf_route_diagnostics.py python/kbprep_worker/diagnose/pdf_route_diagnostics.py
git commit -m "feat: add pdf route diagnostics contract"
```

### Task 3: Add Structure Signals And Large-PDF Sampling Metadata

**Files:**
- Modify: `python/kbprep_worker/quality/thresholds.py`
- Modify: `python/kbprep_worker/diagnose/pdf_analysis.py`
- Modify: `python/tests/test_pdf_route_diagnostics.py`

- [ ] **Step 1: Add RED tests for page sampling and generated structure fields**

Append these tests inside `PDFRouteDiagnosticsTests` in `python/tests/test_pdf_route_diagnostics.py`:

```python
    def test_diagnostic_page_indexes_scan_small_pdf_fully(self):
        from kbprep_worker.diagnose.pdf_analysis import diagnostic_page_indexes

        pages, applied = diagnostic_page_indexes(7)

        self.assertFalse(applied)
        self.assertEqual(pages, tuple(range(7)))

    def test_diagnostic_page_indexes_sample_large_pdf_predictably(self):
        from kbprep_worker.diagnose.pdf_analysis import diagnostic_page_indexes

        pages, applied = diagnostic_page_indexes(120)

        self.assertTrue(applied)
        self.assertEqual(pages[:5], (0, 1, 2, 3, 4))
        self.assertEqual(pages[-5:], (115, 116, 117, 118, 119))
        self.assertIn(50, pages)
        self.assertIn(100, pages)
```

- [ ] **Step 2: Run the RED tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_diagnostics -v
```

Expected result:

```text
ImportError: cannot import name 'diagnostic_page_indexes'
```

- [ ] **Step 3: Add named thresholds**

In `python/kbprep_worker/quality/thresholds.py`, add these keys to `DIAGNOSIS_THRESHOLDS`:

```python
    "pdf_large_page_count": 80,
    "pdf_large_sample_head_pages": 5,
    "pdf_large_sample_tail_pages": 5,
    "pdf_large_sample_stride": 10,
    "pdf_multi_column_min_blocks": 4,
```

- [ ] **Step 4: Replace PDF page-stat collection with sampled-page metadata**

In `python/kbprep_worker/diagnose/pdf_analysis.py`, add this public helper above `_collect_pdf_page_stats`:

```python
def diagnostic_page_indexes(page_count: int) -> tuple[tuple[int, ...], bool]:
    if page_count <= DIAGNOSIS_THRESHOLDS["pdf_large_page_count"]:
        return tuple(range(page_count)), False

    head = DIAGNOSIS_THRESHOLDS["pdf_large_sample_head_pages"]
    tail = DIAGNOSIS_THRESHOLDS["pdf_large_sample_tail_pages"]
    stride = DIAGNOSIS_THRESHOLDS["pdf_large_sample_stride"]
    pages = set(range(min(head, page_count)))
    pages.update(range(max(page_count - tail, 0), page_count))
    pages.update(range(0, page_count, stride))
    return tuple(sorted(pages)), True
```

Then replace the `for page_num in range(len(doc)):` loop in `_collect_pdf_page_stats` with:

```python
    page_indexes, sampling_applied = diagnostic_page_indexes(len(doc))
    multi_column_pages = 0
    table_pages = 0
    image_text_interleaved_pages = 0

    for page_num in page_indexes:
        page = doc[page_num]
        if page.rect.width > page.rect.height:
            landscape_pages += 1
        text = page.get_text("text").strip()
        images = page.get_images(full=True)
        image_count += len(images)
        max_image_count_on_page = max(max_image_count_on_page, len(images))

        if _page_has_multi_column_text(page):
            multi_column_pages += 1
        if _page_has_tables(page, text):
            table_pages += 1
        if text and images:
            image_text_interleaved_pages += 1

        if not text and images:
            image_pages += 1
        elif text:
            text_pages += 1
            total_text += text + "\n"
        else:
            empty_pages += 1
```

Then extend the `_collect_pdf_page_stats()` return dict with:

```python
        "sampled_page_count": len(page_indexes),
        "large_pdf_sampling_applied": sampling_applied,
        "large_pdf_sampled_pages": len(page_indexes),
        "large_pdf_sample_strategy": "first_5_last_5_stride_10" if sampling_applied else "full_scan",
        "multi_column_pages": multi_column_pages,
        "table_pages": table_pages,
        "image_text_interleaved_pages": image_text_interleaved_pages,
```

Then add these helpers below `_collect_pdf_page_stats`:

```python
def _page_has_multi_column_text(page: Any) -> bool:
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except (RuntimeError, ValueError, TypeError):
        return False
    text_boxes = [
        block["bbox"]
        for block in blocks
        if block.get("type") == 0 and _block_text(block).strip()
    ]
    if len(text_boxes) < DIAGNOSIS_THRESHOLDS["pdf_multi_column_min_blocks"]:
        return False
    width = float(page.rect.width)
    has_left = any(float(box[0]) < width * 0.45 for box in text_boxes)
    has_right = any(float(box[0]) > width * 0.45 for box in text_boxes)
    return has_left and has_right


def _block_text(block: dict) -> str:
    lines = block.get("lines")
    if not isinstance(lines, list):
        return ""
    spans: list[str] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        for span in line.get("spans", []):
            if isinstance(span, dict):
                spans.append(str(span.get("text") or ""))
    return "".join(spans)


def _page_has_tables(page: Any, text: str) -> bool:
    finder = getattr(page, "find_tables", None)
    if callable(finder):
        try:
            tables = finder()
            return bool(getattr(tables, "tables", []))
        except (RuntimeError, ValueError, TypeError):
            return False
    return "\t" in text
```

- [ ] **Step 5: Run the Python diagnostics tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_diagnostics -v
```

Expected result:

```text
Ran 7 tests
OK
```

- [ ] **Step 6: Commit sampling and structure metadata**

Run:

```powershell
git add python/tests/test_pdf_route_diagnostics.py python/kbprep_worker/quality/thresholds.py python/kbprep_worker/diagnose/pdf_analysis.py
git commit -m "feat: record pdf diagnostic structure signals"
```

### Task 4: Attach Diagnostics To PDF Diagnosis Results

**Files:**
- Modify: `python/kbprep_worker/diagnose/pdf_analysis.py`
- Modify: `src/test/scenarios/worker-batch-long-docs-part2.test.ts`

- [ ] **Step 1: Add scenario assertions for `pdf_route_diagnostics`**

In `src/test/scenarios/worker-batch-long-docs-part2.test.ts`, inside the existing PDF diagnosis scenario after the current `textDiag`, `imageDiag`, `slideDiag`, `slideTextDiag`, and `garbledDiag` assertions, add:

```ts
      expect(textDiag.data.pdf_route_diagnostics.schema).toBe("kbprep.pdf_route_diagnostics.v1");
      expect(textDiag.data.pdf_route_diagnostics.text_layer.trusted).toBe(true);
      expect(textDiag.data.pdf_route_diagnostics.layout_complexity.level).toBe("simple");
      expect(textDiag.data.pdf_route_diagnostics.image_coverage.ratio).toBe(0);
      expect(textDiag.data.pdf_route_diagnostics.recommended_tier).toBe("tier_1");
      expect(textDiag.data.pdf_route_diagnostics.recommended_route).toBe("pymupdf4llm");

      expect(imageDiag.data.pdf_route_diagnostics.text_layer.trusted).toBe(false);
      expect(imageDiag.data.pdf_route_diagnostics.image_coverage.level).toBe("high");
      expect(imageDiag.data.pdf_route_diagnostics.ocr_triggers).toContain("high_image_coverage");
      expect(imageDiag.data.pdf_route_diagnostics.recommended_tier).toBe("tier_3");
      expect(imageDiag.data.pdf_route_diagnostics.recommended_route).toBe("mineru_ocr");

      expect(slideTextDiag.data.pdf_route_diagnostics.text_layer.trusted).toBe(true);
      expect(slideTextDiag.data.pdf_route_diagnostics.layout_complexity.level).toBe("complex");
      expect(slideTextDiag.data.pdf_route_diagnostics.structure_signals.slide_like).toBe(true);
      expect(slideTextDiag.data.pdf_route_diagnostics.recommended_tier).toBe("tier_2");
      expect(slideTextDiag.data.pdf_route_diagnostics.recommended_route).toBe("mineru_auto");

      expect(garbledDiag.data.pdf_route_diagnostics.text_layer.trusted).toBe(false);
      expect(garbledDiag.data.pdf_route_diagnostics.text_risk.cid_or_tounicode_risk).toBe(true);
      expect(garbledDiag.data.pdf_route_diagnostics.ocr_triggers).toContain("untrusted_text_layer");
      expect(garbledDiag.data.pdf_route_diagnostics.recommended_tier).toBe("tier_3");
```

- [ ] **Step 2: Run the RED scenario test**

Run:

```powershell
npm test -- src/test/scenarios/worker-batch-long-docs-part2.test.ts
```

Expected result:

```text
FAIL src/test/scenarios/worker-batch-long-docs-part2.test.ts
Cannot read properties of undefined (reading 'schema')
```

- [ ] **Step 3: Wire the diagnostics builder into `analyze_pdf()`**

In `python/kbprep_worker/diagnose/pdf_analysis.py`, add this import near the other local imports:

```python
from .pdf_route_diagnostics import build_pdf_route_diagnostics
```

In the `except ImportError:` branch of `analyze_pdf()`, before `return result`, add:

```python
        result["pdf_route_diagnostics"] = build_pdf_route_diagnostics(result)
```

Near the final return of `analyze_pdf()`, after `result["warnings"] = warnings`, add:

```python
    result["pdf_route_diagnostics"] = build_pdf_route_diagnostics(result)
```

- [ ] **Step 4: Run the scenario test**

Run:

```powershell
npm test -- src/test/scenarios/worker-batch-long-docs-part2.test.ts
```

Expected result:

```text
Test Files  1 passed
```

- [ ] **Step 5: Commit diagnosis wiring**

Run:

```powershell
git add python/kbprep_worker/diagnose/pdf_analysis.py src/test/scenarios/worker-batch-long-docs-part2.test.ts
git commit -m "feat: attach pdf route diagnostics to diagnosis"
```

### Task 5: Expose Tier Evidence In Reports

**Files:**
- Modify: `python/kbprep_worker/prepare_diagnosis.py`
- Modify: `python/kbprep_worker/stages/pipeline_helpers.py`
- Modify: `src/test/scenarios/worker-pdf-routing.test.ts`

- [ ] **Step 1: Add RED route-report assertions**

In `src/test/scenarios/worker-pdf-routing.test.ts`, in the image-only scanned PDF scenario after:

```ts
          "assert decision['fallback_applied'] is False, decision",
```

add:

```ts
          "assert decision['selected_pdf_tier'] == 'tier_3', decision",
          "assert decision['pdf_route_diagnostics_schema'] == 'kbprep.pdf_route_diagnostics.v1', decision",
          "assert 'Tier 3' in decision['pdf_route_reason'], decision",
          "assert report['pdf_route_diagnostics']['recommended_tier'] == 'tier_3', report",
          "assert report['pdf_route_diagnostics']['recommended_route'] == 'mineru_ocr', report",
```

In the fallback scenario after:

```ts
          "assert decision['fallback_to'] == 'mineru_ocr', decision",
```

add:

```ts
          "assert decision['selected_pdf_tier'] == 'tier_1', decision",
          "assert decision['pdf_route_diagnostics_schema'] == 'kbprep.pdf_route_diagnostics.v1', decision",
          "assert 'Tier 1' in decision['pdf_route_reason'], decision",
          "assert report['pdf_route_diagnostics']['recommended_tier'] == 'tier_1', report",
```

This expected `tier_1` is intentional: the source PDF diagnosis trusted the input text layer, and the later fallback remains a post-conversion safety upgrade.

- [ ] **Step 2: Run the RED pipeline test**

Run:

```powershell
npm test -- src/test/scenarios/worker-pdf-routing.test.ts
```

Expected result:

```text
FAIL src/test/scenarios/worker-pdf-routing.test.ts
KeyError: 'selected_pdf_tier'
```

- [ ] **Step 3: Expose the full diagnostics in diagnosis report**

In `python/kbprep_worker/prepare_diagnosis.py`, add this key to the `report` dict in `write_diagnosis_report()` immediately after `"layout_profile": diagnosis.get("layout_profile"),`:

```python
        "pdf_route_diagnostics": diagnosis.get("pdf_route_diagnostics"),
```

- [ ] **Step 4: Expose the full diagnostics in conversion report**

In `python/kbprep_worker/stages/pipeline_helpers.py`, add this key to the conversion `report` dict immediately after `"layout_profile": diagnosis.get("layout_profile"),`:

```python
        "pdf_route_diagnostics": diagnosis.get("pdf_route_diagnostics"),
```

- [ ] **Step 5: Add tier summary fields to route decision**

In `python/kbprep_worker/stages/pipeline_helpers.py`, replace the direct `return { ... }` in `_conversion_route_decision()` with:

```python
    decision = {
        "declared_capability_id": capability.get("id", ""),
        "declared_route": capability.get("route", ""),
        "declared_status": capability.get("status", ""),
        "diagnosed_pipeline": diagnosis.get("recommended_pipeline", ""),
        "diagnosed_strategy": diagnosis.get("conversion_strategy", ""),
        "actual_converter": converter,
        "actual_route": actual_route,
        "matched_converter": route.matched_converter,
        "match_evidence": list(route.match_evidence),
        "selected_route": _selected_route_for_decision(route),
        "fallback_applied": fallback_applied,
        "fallback_from": fallback_from,
        "fallback_to": fallback_to,
    }
    pdf_route = diagnosis.get("pdf_route_diagnostics")
    if isinstance(pdf_route, dict):
        decision["selected_pdf_tier"] = pdf_route.get("recommended_tier")
        decision["pdf_route_reason"] = pdf_route.get("reason", "")
        decision["pdf_route_diagnostics_schema"] = pdf_route.get("schema")
    return decision
```

- [ ] **Step 6: Run the pipeline test**

Run:

```powershell
npm test -- src/test/scenarios/worker-pdf-routing.test.ts
```

Expected result:

```text
Test Files  1 passed
```

- [ ] **Step 7: Commit report evidence wiring**

Run:

```powershell
git add python/kbprep_worker/prepare_diagnosis.py python/kbprep_worker/stages/pipeline_helpers.py src/test/scenarios/worker-pdf-routing.test.ts
git commit -m "feat: expose pdf tier evidence in reports"
```

### Task 6: Update Status Documents Without Overclaiming

**Files:**
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/capability-matrix.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [ ] **Step 1: Update roadmap Phase B wording**

In `docs/development/development-roadmap.md`, replace this B1 bullet:

```markdown
- **B1** Add diagnostic signals: multi-column, table, image/text interleaving,
  CID/ToUnicode, image coverage ratio, large-PDF sampling.
```

with:

```markdown
- **B1** Landed: diagnostic evidence now records multi-column, table,
  image/text interleaving, CID/ToUnicode risk, image coverage ratio,
  large-PDF sampling, recommended PDF tier, recommended route, and reason.
```

- [ ] **Step 2: Keep later Phase B items open**

Confirm these bullets remain present and not marked landed:

```markdown
- **B2** Tier 1 `pymupdf4llm` for trusted text layer + simple layout.
- **B3** Tier 2 `mineru_txt` / `mineru_auto` for trusted text layer + complex
  layout.
- **B4** Tier 3 `mineru_ocr` for untrusted text layer (consolidate existing
  path with new trigger evidence).
- **B5** The six acceptance fixtures defined in stage 03: simple single-column,
  English simple text, multi-column paper, table-heavy, scanned,
  CID/ToUnicode-damaged.
```

- [ ] **Step 3: Update capability matrix evidence language**

In `docs/capability-matrix.md`, update only the `pdf_diagnosis_selected` row so the current-status note says:

```markdown
current implementation records structured B1 tier evidence in `pdf_route_diagnostics`, but remains partial until Tier 1 `pymupdf4llm`, Tier 2 mode split, Tier 3 trigger consolidation, and the six acceptance fixtures are complete
```

Keep the status value as `partial`.

- [ ] **Step 4: Update implementation status evidence if the capability exists**

Open `docs/development/kbprep-implementation-status.json` and locate the capability with `"id": "pdf_three_tier_routing"`.

If it exists, add these entries to its `evidence` array:

```json
"python/kbprep_worker/diagnose/pdf_route_diagnostics.py",
"python/tests/test_pdf_route_diagnostics.py",
"src/test/scenarios/worker-batch-long-docs-part2.test.ts",
"src/test/scenarios/worker-pdf-routing.test.ts"
```

Keep its `status` as `"partial"`.

If the capability is not present in the current file, do not invent a new status entry in this task; the roadmap and capability matrix already carry the partial status.

- [ ] **Step 5: Search for overclaims**

Run:

```powershell
rg -n "pdf_diagnosis_selected.*verified|PDF three-tier routing.*verified|six acceptance fixtures.*pass|pymupdf4llm.*implemented|B2.*Landed|B3.*Landed|B4.*Landed|B5.*Landed" docs python src -g "!docs/superpowers/plans/**"
```

Expected result:

```text
no matches
```

- [ ] **Step 6: Commit docs**

Run:

```powershell
git add docs/development/development-roadmap.md docs/capability-matrix.md docs/development/kbprep-implementation-status.json
git commit -m "docs: record pdf diagnostic signal status"
```

### Task 7: Run Verification And Close The Slice

**Files:**
- Verify all files changed by Tasks 1-6.

- [ ] **Step 1: Run targeted Python tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_diagnostics -v
```

Expected result:

```text
Ran 7 tests
OK
```

- [ ] **Step 2: Run targeted TypeScript scenario tests**

Run:

```powershell
npm test -- src/test/scenarios/worker-batch-long-docs-part2.test.ts src/test/scenarios/worker-pdf-routing.test.ts
```

Expected result:

```text
Test Files  2 passed
```

- [ ] **Step 3: Run Python worker checks**

Run:

```powershell
npm run python:test
```

Expected result:

```text
tests pass
```

Run:

```powershell
npm run python:ruff
```

Expected result:

```text
All checks passed
```

Run:

```powershell
npm run python:typecheck
```

Expected result:

```text
Success: no issues found
```

- [ ] **Step 4: Run TypeScript and governance checks**

Run:

```powershell
npm test
```

Expected result:

```text
all Vitest suites pass
```

Run:

```powershell
npm run dev:check
```

Expected result:

```text
dev:check passes
```

- [ ] **Step 5: Check file sizes and diff hygiene**

Run:

```powershell
npm run python:check-size
```

Expected result:

```text
all checked Python files stay within project size limits
```

Run:

```powershell
git diff --check
```

Expected result:

```text
no output
```

- [ ] **Step 6: Final commit if verification changed generated or docs files**

Run this only if verification changed tracked files:

```powershell
git status --short
git add <changed task-related files>
git commit -m "chore: finalize pdf diagnostic signal verification"
```

- [ ] **Step 7: Push the branch**

Run:

```powershell
git status --short
git push
```

Expected result:

```text
worktree clean and branch pushed
```

## Acceptance Criteria

- `diagnose` results for PDF files include `pdf_route_diagnostics.schema == "kbprep.pdf_route_diagnostics.v1"`.
- `pdf_route_diagnostics` records text-layer trust, layout complexity, image coverage, structure signals, text risk, large-PDF sampling, OCR triggers, recommended tier, recommended route, and a reason.
- `diagnosis_report.json` exposes `pdf_route_diagnostics`.
- `conversion_report.json` exposes `pdf_route_diagnostics`.
- `conversion_report.json.route_decision` exposes `selected_pdf_tier`, `pdf_route_reason`, and `pdf_route_diagnostics_schema` for PDFs.
- Existing conversion behavior remains stable in this slice.
- `pdf_diagnosis_selected` remains `partial`.
- B2-B5 remain open.
- Required project checks pass through project commands, not direct system Python.

## Self-Review

- Spec coverage: The plan covers B1 signals, report exposure, conservative status updates, and verification.
- Placeholder scan: The plan contains concrete file paths, commands, code blocks, expected failures, and expected pass conditions.
- Type consistency: The plan uses one stable object name, `pdf_route_diagnostics`, and one schema value, `kbprep.pdf_route_diagnostics.v1`, across Python tests, diagnosis results, reports, and TypeScript scenario tests.
- Overclaim guard: The plan explicitly keeps converter behavior unchanged and keeps `pdf_diagnosis_selected` partial.
