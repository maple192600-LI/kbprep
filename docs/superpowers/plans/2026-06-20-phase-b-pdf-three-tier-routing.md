# Phase B PDF Three-Tier Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Phase B so PDF conversion chooses one auditable route from B1 evidence: Tier 1 `pymupdf4llm`, Tier 2 `mineru_txt` or `mineru_auto`, and Tier 3 `mineru_ocr`, then prove the behavior with six PDF acceptance cases.

**Architecture:** Reuse the landed B1 `pdf_route_diagnostics` object as the routing evidence layer. Add a small route-policy module that maps diagnostics to an executable conversion strategy, add a `pymupdf4llm` adapter for simple trusted text-layer PDFs, keep MinerU behind the existing adapter with explicit `txt` / `auto` / `ocr` modes, and keep conversion reports as the audit surface. Real PDF samples from `F:\Obsidian-Vault` are used for local acceptance when available; private paths, names, and content are never committed.

**Tech Stack:** Python worker modules under `python/kbprep_worker`, PyMuPDF / PyMuPDF4LLM, MinerU CLI through `python/kbprep_worker/mineru_adapter.py`, TypeScript Vitest scenario tests, Python `unittest` through `node scripts/python-venv.mjs`, KBPrep checks through `npm run dev:full-check`.

---

## Current State

- B1 is landed on the current branch: `pdf_route_diagnostics` records text-layer trust, layout complexity, image coverage, structure signals, text risk, large-PDF sampling, recommended tier, recommended route, and reason.
- The actual converter still uses `pdf_text_layer` for simple trusted PDFs and MinerU for complex or OCR paths.
- `docs/development/development-roadmap.md` marks Phase B as partial: B2, B3, B4, and B5 remain open.
- `docs/development/mineru-install-design.md` exists in the current working tree as an untracked file. Treat it as user or prior-agent work. Do not edit, stage, or rely on it as a committed source of truth during this plan.

## Product Rules

- Do not edit `docs/kbprep-core-flow-design.md` or `docs/kbprep-full-flowchart.html` in this plan. They already define the Phase B target.
- Do not commit real Vault sample files, real Vault paths, private file names, or extracted private PDF text.
- If `F:\Obsidian-Vault` contains a required PDF sample class, use that real sample for local acceptance instead of inventing a sample for product proof.
- Public CI tests may still generate minimal sanitized PDFs to keep the repository open-source and deterministic. Those tests prove code paths; Vault smoke proves local real-sample behavior.
- Do not promote `pdf_diagnosis_selected` to `verified` unless the six acceptance cases pass and the evidence is named in `docs/capability-matrix.md`.
- Use only project-environment commands as completion evidence.

## File Map

- Create `python/kbprep_worker/pdf_route_policy.py`
  - Owns mapping from `pdf_route_diagnostics` to executable conversion strategy.
  - Keeps fallback behavior explicit when diagnostics are missing.
- Create `python/kbprep_worker/pymupdf4llm_adapter.py`
  - Converts Tier 1 PDFs to Markdown with `pymupdf4llm.to_markdown`.
  - Writes a MinerU-shaped artifact payload so downstream reports and page mapping keep working.
- Modify `python/pyproject.toml`
  - Add `pymupdf4llm` as a worker dependency.
- Modify `src/runtime/pythonRuntime.ts`
  - Keep the TypeScript runtime dependency marker in sync with `python/pyproject.toml`.
- Modify `python/kbprep_worker/converter_registry.py`
  - Add a route for `pymupdf4llm`.
  - Allow MinerU strategies `mineru_txt`, `mineru_auto`, and `mineru_ocr`.
- Modify `python/kbprep_worker/diagnose/pdf_route_diagnostics.py`
  - Split Tier 2 recommendation between `mineru_txt` and `mineru_auto`.
- Modify `python/kbprep_worker/diagnose/pdf_analysis.py`
  - Preserve legacy diagnosis fields while ensuring the B1 evidence can drive Phase B routing.
- Modify `python/kbprep_worker/stages/pipeline_conversion.py`
  - Execute `pymupdf4llm`, MinerU `txt`, MinerU `auto`, and MinerU `ocr` modes explicitly.
- Modify `python/kbprep_worker/stages/pipeline_helpers.py`
  - Report selected tier, selected route, actual route, MinerU mode, fallback/upgrade evidence, and route reason.
- Modify `python/kbprep_worker/converter_capabilities.py`
  - Keep status partial until B5 is complete; update evidence only after named checks pass.
- Modify `docs/capability-matrix.md`, `docs/development/development-roadmap.md`, `docs/development/00-current-state-and-gap.md`, and `docs/known-issues.md`
  - Update only after behavior and evidence support the wording.
- Create or modify tests:
  - `python/tests/test_pdf_route_policy.py`
  - `python/tests/test_pymupdf4llm_adapter.py`
  - `python/tests/test_pdf_route_diagnostics.py`
  - `src/test/scenarios/worker-pdf-routing.test.ts`
  - `src/test/scenarios/worker-batch-long-docs-part2.test.ts`
  - `src/test/scenarios/worker-local-formats.test.ts`
- Create `scripts/check-vault-pdf-phase-b.mjs`
  - Finds real local Vault samples for the six PDF acceptance classes.
  - Outputs anonymized evidence only.
- Modify `package.json`
  - Add `vault:pdf-phase-b` script.

---

## Task 1: Add PDF Route Policy Contract

**Files:**
- Create: `python/kbprep_worker/pdf_route_policy.py`
- Create: `python/tests/test_pdf_route_policy.py`
- Modify: `python/kbprep_worker/converter_registry.py`

- [ ] **Step 1: Write the failing route-policy tests**

Create `python/tests/test_pdf_route_policy.py`:

```python
import unittest

from kbprep_worker.pdf_route_policy import selected_pdf_strategy


class PDFRoutePolicyTests(unittest.TestCase):
    def test_tier_1_selects_pymupdf4llm(self):
        diagnosis = {
            "conversion_strategy": "pdf_text_layer",
            "pdf_route_diagnostics": {
                "schema": "kbprep.pdf_route_diagnostics.v1",
                "recommended_tier": "tier_1",
                "recommended_route": "pymupdf4llm",
                "reason": "Tier 1 because text is trusted and layout is simple.",
            },
        }

        strategy = selected_pdf_strategy(diagnosis)

        self.assertEqual(strategy, "pymupdf4llm")

    def test_tier_2_selects_mineru_txt_or_auto(self):
        for route in ("mineru_txt", "mineru_auto"):
            with self.subTest(route=route):
                diagnosis = {
                    "conversion_strategy": "mineru_auto",
                    "pdf_route_diagnostics": {
                        "schema": "kbprep.pdf_route_diagnostics.v1",
                        "recommended_tier": "tier_2",
                        "recommended_route": route,
                        "reason": "Tier 2 because trusted text has complex layout.",
                    },
                }

                strategy = selected_pdf_strategy(diagnosis)

                self.assertEqual(strategy, route)

    def test_tier_3_selects_mineru_ocr(self):
        diagnosis = {
            "conversion_strategy": "mineru_ocr",
            "pdf_route_diagnostics": {
                "schema": "kbprep.pdf_route_diagnostics.v1",
                "recommended_tier": "tier_3",
                "recommended_route": "mineru_ocr",
                "reason": "Tier 3 because OCR evidence is present.",
            },
        }

        strategy = selected_pdf_strategy(diagnosis)

        self.assertEqual(strategy, "mineru_ocr")

    def test_missing_diagnostics_preserves_legacy_strategy(self):
        diagnosis = {"conversion_strategy": "pdf_text_layer"}

        strategy = selected_pdf_strategy(diagnosis)

        self.assertEqual(strategy, "pdf_text_layer")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the target test and confirm RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_policy -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'kbprep_worker.pdf_route_policy'`.

- [ ] **Step 3: Implement `pdf_route_policy.py`**

Create `python/kbprep_worker/pdf_route_policy.py`:

```python
"""PDF route policy derived from auditable diagnosis evidence."""

from __future__ import annotations

from typing import Any

PDF_ROUTE_DIAGNOSTICS_SCHEMA = "kbprep.pdf_route_diagnostics.v1"
PDF_PHASE_B_STRATEGIES = {"pymupdf4llm", "mineru_txt", "mineru_auto", "mineru_ocr"}
LEGACY_PDF_STRATEGIES = {"pdf_text_layer", "mineru_auto", "mineru_ocr", "mineru_mixed_text_image"}


def selected_pdf_strategy(diagnosis: dict[str, Any]) -> str:
    """Return the executable PDF conversion strategy for a diagnosis result."""
    diagnostics = diagnosis.get("pdf_route_diagnostics")
    if isinstance(diagnostics, dict) and diagnostics.get("schema") == PDF_ROUTE_DIAGNOSTICS_SCHEMA:
        route = str(diagnostics.get("recommended_route") or "")
        if route in PDF_PHASE_B_STRATEGIES:
            return route

    legacy = str(diagnosis.get("conversion_strategy") or "")
    if legacy in LEGACY_PDF_STRATEGIES:
        return legacy
    return "mineru_auto"
```

- [ ] **Step 4: Update converter registry to call route policy for PDFs**

In `python/kbprep_worker/converter_registry.py`, import the policy:

```python
from .pdf_route_policy import selected_pdf_strategy
```

Add a new enum member without removing existing values:

```python
class ConversionRouteKind(str, Enum):
    DIRECT_TEXT = "direct_text"
    OFFICE_XML = "office_xml"
    EPUB_XHTML = "epub_xhtml"
    PDF_PYMUPDF4LLM = "pymupdf4llm"
    PDF_TEXT_LAYER = "pdf_text_layer"
    MINERU_OCR = "mineru_ocr"
    IMAGE_TO_PDF_OCR = "image_to_pdf_ocr"
    LEGACY_OFFICE_TO_PDF = "legacy_office_to_pdf"
    MEDIA_TRANSCRIPT = "media_transcript"
    MEDIA_TRANSCRIPT_REQUIRED = "media_transcript_required"
    UNSUPPORTED = "unsupported"
```

Add a registration before `pdf_text_layer`:

```python
    ConverterRegistration(
        id="pymupdf4llm",
        kind=ConversionRouteKind.PDF_PYMUPDF4LLM,
        priority=39,
        extensions=(".pdf",),
        mime_types=("application/pdf",),
        signatures=("pdf_header",),
        converter="pymupdf4llm",
        conversion_strategy="pymupdf4llm",
    ),
```

Change the top of `select_conversion_route()` after `strategy = ...`:

```python
    strategy = selected_pdf_strategy(diagnosis) if ext in PDF_EXTENSIONS else str(diagnosis.get("conversion_strategy") or "")
```

Update `_strategy_for_registration()`:

```python
def _strategy_for_registration(registration: ConverterRegistration, strategy: str) -> str | None:
    if registration.id == "pymupdf4llm":
        return "pymupdf4llm" if strategy == "pymupdf4llm" else None
    if registration.id == "pdf_text_layer":
        return "pdf_text_layer" if strategy == "pdf_text_layer" else None
    if registration.id == "mineru":
        if strategy in {"mineru_pipeline", "mineru_pipeline_ocr"}:
            return "mineru_ocr"
        allowed = {"", "mineru_txt", "mineru_ocr", "mineru_auto", "mineru_mixed_text_image"}
        return (strategy or registration.conversion_strategy) if strategy in allowed else None
    return registration.conversion_strategy
```

- [ ] **Step 5: Add registry tests for the new strategies**

Append to `python/tests/test_converter_registry.py`:

```python
    def test_pdf_route_policy_selects_pymupdf4llm_registration(self):
        route = select_conversion_route(".pdf", {
            "conversion_strategy": "pdf_text_layer",
            "pdf_route_diagnostics": {
                "schema": "kbprep.pdf_route_diagnostics.v1",
                "recommended_route": "pymupdf4llm",
            },
        })

        self.assertEqual(route.kind, ConversionRouteKind.PDF_PYMUPDF4LLM)
        self.assertEqual(route.converter, "pymupdf4llm")
        self.assertEqual(route.conversion_strategy, "pymupdf4llm")

    def test_pdf_route_policy_selects_mineru_txt_registration(self):
        route = select_conversion_route(".pdf", {
            "conversion_strategy": "mineru_auto",
            "pdf_route_diagnostics": {
                "schema": "kbprep.pdf_route_diagnostics.v1",
                "recommended_route": "mineru_txt",
            },
        })

        self.assertEqual(route.kind, ConversionRouteKind.MINERU_OCR)
        self.assertEqual(route.converter, "mineru")
        self.assertEqual(route.conversion_strategy, "mineru_txt")
```

- [ ] **Step 6: Run target tests and commit**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_policy python.tests.test_converter_registry -v
```

Expected: PASS.

Commit:

```powershell
git add python/kbprep_worker/pdf_route_policy.py python/kbprep_worker/converter_registry.py python/tests/test_pdf_route_policy.py python/tests/test_converter_registry.py
git commit -m "feat: add pdf route policy"
```

---

## Task 2: Implement Tier 1 `pymupdf4llm`

**Files:**
- Create: `python/kbprep_worker/pymupdf4llm_adapter.py`
- Create: `python/tests/test_pymupdf4llm_adapter.py`
- Modify: `python/pyproject.toml`
- Modify: `src/runtime/pythonRuntime.ts`
- Modify: `python/kbprep_worker/stages/pipeline_conversion.py`
- Modify: `src/test/scenarios/worker-local-formats.test.ts`
- Modify: `src/runtime/pythonRuntime.test.ts`
- Modify: `src/index.test.ts`

- [ ] **Step 1: Add dependency expectations to tests**

In `src/runtime/pythonRuntime.test.ts` and `src/index.test.ts`, update expected dependency strings from:

```text
mineru[all]>=3.2.1,<4;PyMuPDF>=1.27,<2;beautifulsoup4==4.14.3;lxml==6.0.2
```

to:

```text
mineru[all]>=3.2.1,<4;PyMuPDF>=1.27,<2;pymupdf4llm>=0.0.27,<1;beautifulsoup4==4.14.3;lxml==6.0.2
```

- [ ] **Step 2: Write adapter tests with a fake `pymupdf4llm` module**

Create `python/tests/test_pymupdf4llm_adapter.py`:

```python
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from kbprep_worker.pymupdf4llm_adapter import convert_pymupdf4llm_pdf


class PyMuPDF4LLMAdapterTests(unittest.TestCase):
    def test_converts_page_chunks_to_markdown_and_content_list(self):
        fake = types.SimpleNamespace()
        calls = []

        def to_markdown(doc, *, page_chunks=False, write_images=False, image_path=None, image_format=None, dpi=None):
            calls.append({
                "doc": doc,
                "page_chunks": page_chunks,
                "write_images": write_images,
                "image_path": image_path,
                "image_format": image_format,
                "dpi": dpi,
            })
            self.assertTrue(page_chunks)
            return [
                {"metadata": {"page_number": 1, "title": "First"}, "text": "Step 1: keep threshold=0.8."},
                {"metadata": {"page_number": 2, "title": "Second"}, "text": "Step 2: keep retry_count=3."},
            ]

        fake.to_markdown = to_markdown
        old_module = sys.modules.get("pymupdf4llm")
        sys.modules["pymupdf4llm"] = fake
        try:
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                input_path = root / "simple.pdf"
                output_path = root / "converted.md"
                input_path.write_bytes(b"%PDF-1.7\n")

                result = convert_pymupdf4llm_pdf(input_path, output_path, root)

                markdown = output_path.read_text(encoding="utf-8")
                self.assertIn("<!-- page: 1 -->", markdown)
                self.assertIn("threshold=0.8", markdown)
                self.assertIn("retry_count=3", markdown)
                self.assertEqual(result["converter"], "pymupdf4llm")
                self.assertTrue(Path(str(result["content_list_path"])).exists())
                self.assertEqual(calls[0]["image_format"], "png")
                self.assertEqual(calls[0]["dpi"], 150)
        finally:
            if old_module is None:
                sys.modules.pop("pymupdf4llm", None)
            else:
                sys.modules["pymupdf4llm"] = old_module

    def test_rejects_empty_markdown(self):
        fake = types.SimpleNamespace(to_markdown=lambda *args, **kwargs: [{"metadata": {"page_number": 1}, "text": ""}])
        old_module = sys.modules.get("pymupdf4llm")
        sys.modules["pymupdf4llm"] = fake
        try:
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                input_path = root / "empty.pdf"
                output_path = root / "converted.md"
                input_path.write_bytes(b"%PDF-1.7\n")

                with self.assertRaises(RuntimeError):
                    convert_pymupdf4llm_pdf(input_path, output_path, root)
        finally:
            if old_module is None:
                sys.modules.pop("pymupdf4llm", None)
            else:
                sys.modules["pymupdf4llm"] = old_module


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run adapter tests and confirm RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pymupdf4llm_adapter -v
```

Expected: FAIL because `kbprep_worker.pymupdf4llm_adapter` does not exist.

- [ ] **Step 4: Add dependency to Python and TypeScript runtime marker**

In `python/pyproject.toml`, add:

```toml
    "pymupdf4llm>=0.0.27,<1",
```

immediately after the `PyMuPDF` dependency.

In `src/runtime/pythonRuntime.ts`, update:

```ts
const PYTHON_WORKER_DEPENDENCY_SPEC = "mineru[all]>=3.2.1,<4;PyMuPDF>=1.27,<2;pymupdf4llm>=0.0.27,<1;beautifulsoup4==4.14.3;lxml==6.0.2";
```

- [ ] **Step 5: Implement `pymupdf4llm_adapter.py`**

Create `python/kbprep_worker/pymupdf4llm_adapter.py`:

```python
"""Tier 1 PDF conversion using PyMuPDF4LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json, atomic_write_text


def convert_pymupdf4llm_pdf(input_path: Path, output_path: Path, run_dir: Path) -> dict[str, Any]:
    chunks = _to_markdown_chunks(input_path, run_dir)
    markdown, content_list = _markdown_and_content_list(chunks)
    if not markdown.strip():
        raise RuntimeError(f"{input_path.name} produced empty Markdown with pymupdf4llm")

    atomic_write_text(output_path, markdown.rstrip() + "\n")
    content_list_path = run_dir / "pymupdf4llm_content_list.json"
    atomic_write_json(content_list_path, content_list, indent=2, trailing_newline=False)
    return {
        "source_md_path": str(output_path),
        "content_list_path": str(content_list_path),
        "content_list_v2_path": None,
        "middle_json_path": None,
        "assets_dir": str(run_dir / "images" / "pymupdf4llm"),
        "converter": "pymupdf4llm",
        "warnings": [
            "W_PDF_PYMUPDF4LLM_CONVERTER_USED: used trusted text-layer PDF route with PyMuPDF4LLM."
        ],
    }


def _to_markdown_chunks(input_path: Path, run_dir: Path) -> list[dict[str, Any]]:
    try:
        import pymupdf4llm
    except ImportError as exc:
        raise RuntimeError("pymupdf4llm is required for Tier 1 PDF conversion") from exc

    image_dir = run_dir / "images" / "pymupdf4llm"
    image_dir.mkdir(parents=True, exist_ok=True)
    chunks = pymupdf4llm.to_markdown(
        str(input_path),
        page_chunks=True,
        write_images=True,
        image_path=str(image_dir),
        image_format="png",
        dpi=150,
    )
    if isinstance(chunks, str):
        return [{"metadata": {"page_number": 1}, "text": chunks}]
    if isinstance(chunks, list):
        return [chunk for chunk in chunks if isinstance(chunk, dict)]
    raise RuntimeError("pymupdf4llm returned an unsupported Markdown payload")


def _markdown_and_content_list(chunks: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    markdown_parts: list[str] = []
    content_list: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
        page_number = _page_number(metadata, index)
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        markdown_parts.append(f"<!-- page: {page_number} -->\n\n{text}")
        content_list.append({
            "type": "text",
            "page_idx": page_number - 1,
            "text": text,
            "metadata": json.loads(json.dumps(metadata, ensure_ascii=False, default=str)),
        })
    return "\n\n".join(markdown_parts), content_list


def _page_number(metadata: dict[str, Any], fallback_index: int) -> int:
    raw = metadata.get("page_number")
    return raw if isinstance(raw, int) and raw > 0 else fallback_index + 1
```

- [ ] **Step 6: Wire Tier 1 into conversion stage**

In `python/kbprep_worker/stages/pipeline_conversion.py`, import remains local. Add a branch before `PDF_TEXT_LAYER`:

```python
    elif route.kind == ConversionRouteKind.PDF_PYMUPDF4LLM:
        _convert_pymupdf4llm_route(state, converted_path, run_dir)
```

Add the function:

```python
def _convert_pymupdf4llm_route(state: PipelineState, converted_path: Path, run_dir: Path) -> None:
    from ..pymupdf4llm_adapter import convert_pymupdf4llm_pdf
    result = convert_pymupdf4llm_pdf(state.input_p, converted_path, run_dir)
    state.mineru_artifacts = result
    state.warnings.extend(result.get("warnings", []))
    _stderr_log("info", "convert", "PDF converted with PyMuPDF4LLM")
```

Update `_conversion_report_converter()`:

```python
    if route == ConversionRouteKind.PDF_PYMUPDF4LLM:
        return "pymupdf4llm"
```

- [ ] **Step 7: Update the trusted text-layer scenario**

In `src/test/scenarios/worker-local-formats.test.ts`, rename the case from:

```ts
it("converts trusted text-layer PDFs without invoking MinerU", () => {
```

to:

```ts
it("converts trusted simple PDFs through Tier 1 PyMuPDF4LLM", () => {
```

Update expectations:

```ts
expect(conversionReport.converter).toBe("pymupdf4llm");
expect(conversionReport.diagnosed_strategy).toBe("pdf_text_layer");
expect(conversionReport.route_decision.declared_route).toBe("pdf_diagnosis_selected");
expect(conversionReport.route_decision.selected_pdf_tier).toBe("tier_1");
expect(conversionReport.route_decision.actual_converter).toBe("pymupdf4llm");
expect(conversionReport.route_decision.actual_route).toBe("pymupdf4llm");
expect(conversionReport.route_decision.fallback_applied).toBe(false);
expect(conversionReport.mineru_artifacts.source_md_path).toContain("converted.md");
expect(conversionReport.mineru_artifacts.content_list_path).toContain("pymupdf4llm_content_list.json");
```

- [ ] **Step 8: Run target checks and commit**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pymupdf4llm_adapter python.tests.test_pdf_route_policy python.tests.test_converter_registry -v
npm test -- src/test/scenarios/worker-local-formats.test.ts src/runtime/pythonRuntime.test.ts src/index.test.ts
```

Expected: all selected tests PASS.

Commit:

```powershell
git add python/pyproject.toml src/runtime/pythonRuntime.ts src/runtime/pythonRuntime.test.ts src/index.test.ts python/kbprep_worker/pymupdf4llm_adapter.py python/kbprep_worker/stages/pipeline_conversion.py python/tests/test_pymupdf4llm_adapter.py src/test/scenarios/worker-local-formats.test.ts
git commit -m "feat: add tier 1 pymupdf4llm pdf route"
```

---

## Task 3: Split Tier 2 MinerU Modes

**Files:**
- Modify: `python/kbprep_worker/diagnose/pdf_route_diagnostics.py`
- Modify: `python/kbprep_worker/stages/pipeline_conversion.py`
- Modify: `python/kbprep_worker/stages/pipeline_helpers.py`
- Modify: `python/tests/test_pdf_route_diagnostics.py`
- Modify: `src/test/scenarios/worker-batch-long-docs-part2.test.ts`
- Modify: `src/test/scenarios/worker-pdf-routing.test.ts`

- [ ] **Step 1: Add diagnostics tests for `mineru_txt` vs `mineru_auto`**

Append to `python/tests/test_pdf_route_diagnostics.py`:

```python
    def test_multi_column_text_prefers_mineru_txt(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 12,
            "text_pages": 12,
            "image_pages": 0,
            "text_layer_health": "good",
            "needs_ocr": False,
            "layout_complexity": "complex",
            "layout_profile": "document_pages",
            "multi_column_pages": 4,
            "table_pages": 0,
            "image_text_interleaved_pages": 0,
            "pdf_subtype": "text_layer",
            "text_quality": {
                "garbled_ratio": 0.0,
                "unreadable_text_ratio": 0.0,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.0,
                "control_ratio": 0.0,
            },
        })

        self.assertEqual(diagnostics["recommended_tier"], "tier_2")
        self.assertEqual(diagnostics["recommended_route"], "mineru_txt")

    def test_table_or_image_interleaving_prefers_mineru_auto(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 12,
            "text_pages": 12,
            "image_pages": 3,
            "text_layer_health": "good",
            "needs_ocr": False,
            "layout_complexity": "complex",
            "layout_profile": "document_pages",
            "multi_column_pages": 0,
            "table_pages": 2,
            "image_text_interleaved_pages": 1,
            "pdf_subtype": "mixed_text_image",
            "text_quality": {
                "garbled_ratio": 0.0,
                "unreadable_text_ratio": 0.0,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.0,
                "control_ratio": 0.0,
            },
        })

        self.assertEqual(diagnostics["recommended_tier"], "tier_2")
        self.assertEqual(diagnostics["recommended_route"], "mineru_auto")
```

- [ ] **Step 2: Run diagnostics tests and confirm RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_diagnostics -v
```

Expected: FAIL because Tier 2 currently always recommends `mineru_auto`.

- [ ] **Step 3: Implement Tier 2 route selection**

In `python/kbprep_worker/diagnose/pdf_route_diagnostics.py`, replace `_recommended_route()` with:

```python
def _recommended_route(tier: str, structure: dict[str, bool] | None = None, image_coverage: dict[str, Any] | None = None) -> str:
    if tier == "tier_1":
        return "pymupdf4llm"
    if tier == "tier_3":
        return "mineru_ocr"
    structure = structure or {}
    image_coverage = image_coverage or {}
    complex_visual = (
        structure.get("table_heavy")
        or structure.get("image_text_interleaving")
        or structure.get("slide_like")
        or image_coverage.get("level") == "high"
    )
    return "mineru_auto" if complex_visual else "mineru_txt"
```

Update the caller in `build_pdf_route_diagnostics()`:

```python
        "recommended_route": _recommended_route(recommended_tier, structure, image_coverage),
```

Update `_reason()` for Tier 2:

```python
    if tier == "tier_2":
        signals = ", ".join(layout["signals"]) or "reading-order risk"
        return f"Tier 2 because text is trusted but layout is {layout['level']} ({signals})."
```

- [ ] **Step 4: Execute MinerU mode from conversion strategy**

In `python/kbprep_worker/stages/pipeline_conversion.py`, replace `_convert_mineru_ocr_route()` body with:

```python
def _convert_mineru_ocr_route(state: PipelineState, converted_path: Path, run_dir: Path, route: Any | None = None) -> None:
    mode = _mineru_mode_for_strategy(route.conversion_strategy if route else state.diagnosis.get("conversion_strategy"))
    result = _run_mineru_conversion(state.input_p, converted_path, run_dir, state.language, mode)
    result["mineru_mode"] = mode
    state.mineru_artifacts = result
    state.warnings.extend(result.get("warnings", []))
    _stderr_log("info", "convert", f"MinerU conversion complete in {mode} mode")
```

Update the caller:

```python
    elif route.kind == ConversionRouteKind.MINERU_OCR:
        _convert_mineru_ocr_route(state, converted_path, run_dir, route)
```

Add:

```python
def _mineru_mode_for_strategy(strategy: object) -> str:
    value = str(strategy or "")
    if value == "mineru_txt":
        return "txt"
    if value == "mineru_ocr":
        return "ocr"
    return "auto"
```

- [ ] **Step 5: Add scenario tests for Tier 2 mode selection**

In `src/test/scenarios/worker-pdf-routing.test.ts`, add a case that fakes MinerU and asserts `txt` mode:

```ts
  it("routes trusted multi-column PDFs through Tier 2 MinerU txt mode", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-tier2-txt-"));
    try {
      const inputPath = path.join(root, "multi-column.pdf");
      const outputRoot = path.join(root, "output");
      makeTextLayerPdf(inputPath);

      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import mineru_adapter, prepare",
          "from kbprep_worker.diagnose import pdf_analysis",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "calls = []",
          "original_analyze_pdf = pdf_analysis.analyze_pdf",
          "def fake_analyze_pdf(path):",
          "    diagnosis = original_analyze_pdf(path)",
          "    diagnosis['layout_complexity'] = 'complex'",
          "    diagnosis['multi_column_pages'] = 2",
          "    diagnosis['table_pages'] = 0",
          "    diagnosis['image_text_interleaved_pages'] = 0",
          "    diagnosis['pdf_route_diagnostics'] = {",
          "        **diagnosis['pdf_route_diagnostics'],",
          "        'recommended_tier': 'tier_2',",
          "        'recommended_route': 'mineru_txt',",
          "        'reason': 'Tier 2 because trusted text has multi-column reading-order risk.'",
          "    }",
          "    return diagnosis",
          "def fake_mineru(**kwargs):",
          "    calls.append(kwargs.get('mode'))",
          "    out = Path(kwargs['output_dir']) / 'mineru_txt.md'",
          "    out.write_text('# Multi Column Result\\n\\nKeep threshold=0.8 and retry_count=3.\\n', encoding='utf-8')",
          "    return {'source_md_path': str(out), 'converter': 'mineru', 'warnings': []}",
          "pdf_analysis.analyze_pdf = fake_analyze_pdf",
          "mineru_adapter.run_mineru = fake_mineru",
          "stdout = io.StringIO()",
          "old_stdout = sys.stdout",
          "try:",
          "    sys.stdout = stdout",
          "    prepare.run({'input_path': str(input_path), 'output_root': str(output_root), 'profile': 'standard', 'mode': 'rules_only', 'language': 'zh', 'source_type': 'auto', 'splitter': 'auto', 'force': True})",
          "finally:",
          "    sys.stdout = old_stdout",
          "payload = json.loads(stdout.getvalue())",
          "assert payload['ok'] is True, payload",
          "assert calls == ['txt'], calls",
          "report = json.loads(Path(payload['data']['latest_outputs']['conversion_report']).read_text(encoding='utf-8'))",
          "assert report['route_decision']['selected_pdf_tier'] == 'tier_2', report",
          "assert report['route_decision']['actual_route'] == 'mineru_txt', report",
          "assert report['mineru_artifacts']['mineru_mode'] == 'txt', report",
        ].join(\"\\n\"),
        [inputPath, outputRoot],
        true,
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 10_000);
```

- [ ] **Step 6: Update route report actual route**

In `python/kbprep_worker/stages/pipeline_helpers.py`, update `_actual_route_for_converter()`:

```python
    if converter == "mineru":
        strategy = str(diagnosis.get("conversion_strategy") or "")
        pdf_route = diagnosis.get("pdf_route_diagnostics")
        if isinstance(pdf_route, dict) and pdf_route.get("recommended_route") in {"mineru_txt", "mineru_auto", "mineru_ocr"}:
            return str(pdf_route["recommended_route"])
        if strategy in {"mineru_txt", "mineru_ocr", "mineru_auto", "mineru_mixed_text_image"}:
            return strategy
        return "mineru"
```

- [ ] **Step 7: Run target checks and commit**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_pdf_route_diagnostics python.tests.test_pdf_route_policy -v
npm test -- src/test/scenarios/worker-pdf-routing.test.ts src/test/scenarios/worker-batch-long-docs-part2.test.ts
```

Expected: all selected tests PASS.

Commit:

```powershell
git add python/kbprep_worker/diagnose/pdf_route_diagnostics.py python/kbprep_worker/stages/pipeline_conversion.py python/kbprep_worker/stages/pipeline_helpers.py python/tests/test_pdf_route_diagnostics.py src/test/scenarios/worker-pdf-routing.test.ts src/test/scenarios/worker-batch-long-docs-part2.test.ts
git commit -m "feat: split tier 2 mineru pdf modes"
```

---

## Task 4: Consolidate Tier 3 OCR And One-Upgrade Evidence

**Files:**
- Modify: `python/kbprep_worker/stages/pipeline_conversion.py`
- Modify: `python/kbprep_worker/stages/pipeline_helpers.py`
- Modify: `src/test/scenarios/worker-pdf-routing.test.ts`
- Modify: `docs/development/04-conversion-quality-gate.md`

- [ ] **Step 1: Add Tier 3 no-fallback and one-upgrade assertions**

In `src/test/scenarios/worker-pdf-routing.test.ts`, update the existing scanned PDF test to assert:

```ts
assert calls == ['ocr'], calls
assert decision['selected_pdf_tier'] == 'tier_3', decision
assert decision['actual_route'] == 'mineru_ocr', decision
assert decision['fallback_applied'] is False, decision
assert report['pdf_route_diagnostics']['ocr_triggers'], report
```

Update the existing text-layer fallback test to assert:

```ts
assert calls == ['ocr'], calls
assert report['mineru_artifacts']['fallback_from'] == 'pymupdf4llm', report
assert report['mineru_artifacts']['fallback_reason'] == 'post_convert_text_unreadable', report
assert decision['fallback_applied'] is True, decision
assert decision['fallback_to'] == 'mineru_ocr', decision
```

- [ ] **Step 2: Run PDF routing test and confirm RED where old fallback names remain**

Run:

```powershell
npm test -- src/test/scenarios/worker-pdf-routing.test.ts
```

Expected: FAIL if fallback still reports `pdf_text_layer` after Tier 1 has moved to `pymupdf4llm`.

- [ ] **Step 3: Generalize fallback naming**

In `python/kbprep_worker/stages/pipeline_conversion.py`, rename `_maybe_fallback_pdf_text_layer_to_mineru()` to:

```python
def _maybe_fallback_pdf_markdown_to_mineru(
    input_p: Path,
    converted_path: Path,
    run_dir: Path,
    language: str,
    source_route: str,
    source_artifacts: dict,
) -> dict | None:
```

Set fallback values:

```python
    rejected_path = run_dir / f"converted.{source_route}.rejected.md"
    fallback["fallback_from"] = source_route
    fallback["fallback_reason"] = "post_convert_text_unreadable"
    fallback["rejected_text_layer_md"] = str(rejected_path)
```

Call it from both `_convert_pymupdf4llm_route()` and `_convert_pdf_text_layer_route()`:

```python
    fallback = _maybe_fallback_pdf_markdown_to_mineru(
        input_p=state.input_p,
        converted_path=converted_path,
        run_dir=run_dir,
        language=state.language,
        source_route="pymupdf4llm",
        source_artifacts=result,
    )
```

and:

```python
    fallback = _maybe_fallback_pdf_markdown_to_mineru(
        input_p=state.input_p,
        converted_path=converted_path,
        run_dir=run_dir,
        language=state.language,
        source_route="pdf_text_layer",
        source_artifacts=result,
    )
```

- [ ] **Step 4: Update report fallback logic**

In `python/kbprep_worker/stages/pipeline_conversion.py`, update `_conversion_report_converter()`:

```python
    if artifacts.get("fallback_from") == "pymupdf4llm":
        return "mineru_after_pymupdf4llm_fallback"
    if artifacts.get("fallback_from") == "pdf_text_layer":
        return "mineru_after_pdf_text_layer_fallback"
```

In `python/kbprep_worker/stages/pipeline_helpers.py`, update `_actual_route_for_converter()`:

```python
    if converter in {"mineru_after_pdf_text_layer_fallback", "mineru_after_pymupdf4llm_fallback"}:
        return "mineru_ocr"
```

- [ ] **Step 5: Update quality-gate doc wording**

In `docs/development/04-conversion-quality-gate.md`, ensure the PDF upgrade wording says:

```markdown
- PDF upgrade happens at most once and records `fallback_from`, `fallback_to`, `fallback_reason`, and the rejected Markdown path in `conversion_report.json`.
```

- [ ] **Step 6: Run target checks and commit**

Run:

```powershell
npm test -- src/test/scenarios/worker-pdf-routing.test.ts
git diff --check
```

Expected: PASS and no whitespace errors.

Commit:

```powershell
git add python/kbprep_worker/stages/pipeline_conversion.py python/kbprep_worker/stages/pipeline_helpers.py src/test/scenarios/worker-pdf-routing.test.ts docs/development/04-conversion-quality-gate.md
git commit -m "feat: record pdf tier 3 upgrade evidence"
```

---

## Task 5: Add Public Acceptance Fixtures And Real Vault PDF Smoke

**Files:**
- Modify: `src/test/helpers/workerHarness.ts`
- Modify: `src/test/scenarios/worker-pdf-routing.test.ts`
- Create: `scripts/check-vault-pdf-phase-b.mjs`
- Modify: `package.json`

- [ ] **Step 1: Add public sanitized fixture helpers**

In `src/test/helpers/workerHarness.ts`, add two helpers. These are not product proof when real Vault samples are available; they keep CI deterministic and open-source safe.

```ts
export function makeMultiColumnTextPdf(pdfPath: string) {
  runPython(
    [
      "import fitz, sys",
      "pdf_path = sys.argv[1]",
      "doc = fitz.open()",
      "page = doc.new_page(width=595, height=842)",
      "left = fitz.Rect(72, 72, 260, 760)",
      "right = fitz.Rect(320, 72, 520, 760)",
      "page.insert_textbox(left, 'Left column step A keeps threshold=0.8.\\nLeft column step B keeps retry_count=3.')",
      "page.insert_textbox(right, 'Right column case note keeps failure_reason=timeout.\\nRight column conclusion stays ordered.')",
      "doc.save(pdf_path)",
    ].join(\"\\n\"),
    [pdfPath],
    true,
  );
}

export function makeTableHeavyPdf(pdfPath: string) {
  runPython(
    [
      "import fitz, sys",
      "pdf_path = sys.argv[1]",
      "doc = fitz.open()",
      "page = doc.new_page(width=595, height=842)",
      "page.insert_text((72, 72), 'Metric\\tValue\\tReason')",
      "page.insert_text((72, 100), 'threshold\\t0.8\\tkept for setup')",
      "page.insert_text((72, 128), 'retry_count\\t3\\tkept for replay')",
      "doc.save(pdf_path)",
    ].join(\"\\n\"),
    [pdfPath],
    true,
  );
}
```

- [ ] **Step 2: Add six public scenario cases**

In `src/test/scenarios/worker-pdf-routing.test.ts`, add a table-driven diagnosis test:

```ts
  it("classifies the six Phase B public PDF acceptance shapes", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-phase-b-public-"));
    try {
      const outputRoot = path.join(root, "output");
      mkdirSync(outputRoot);
      const cases = [
        { name: "simple", maker: () => makeTextLayerPdf(path.join(root, "simple.pdf")), file: "simple.pdf", tier: "tier_1" },
        { name: "english", maker: () => makeTextLayerPdf(path.join(root, "english.pdf")), file: "english.pdf", tier: "tier_1" },
        { name: "multi-column", maker: () => makeMultiColumnTextPdf(path.join(root, "multi-column.pdf")), file: "multi-column.pdf", tier: "tier_2" },
        { name: "table-heavy", maker: () => makeTableHeavyPdf(path.join(root, "table-heavy.pdf")), file: "table-heavy.pdf", tier: "tier_2" },
        { name: "scanned", maker: () => makeImageOnlyPdf(path.join(root, "scanned.pdf"), path.join(root, "scanned.png")), file: "scanned.pdf", tier: "tier_3" },
        { name: "cid-damaged", maker: () => makeGarbledTextLayerPdf(path.join(root, "cid-damaged.pdf")), file: "cid-damaged.pdf", tier: "tier_3" },
      ];

      for (const item of cases) {
        item.maker();
        const diagnosis = runWorker("diagnose", {
          input_path: path.join(root, item.file),
          output_root: outputRoot,
          source_type: "auto",
        });
        expect(diagnosis.data.pdf_route_diagnostics.recommended_tier).toBe(item.tier);
        expect(diagnosis.data.pdf_route_diagnostics.reason).toContain(`Tier ${item.tier.slice(-1)}`);
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
```

Update imports to include:

```ts
  makeMultiColumnTextPdf,
  makeTableHeavyPdf,
```

- [ ] **Step 3: Create real Vault PDF selector**

Create `scripts/check-vault-pdf-phase-b.mjs`:

```js
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, statSync, rmSync } from "node:fs";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vaultRoot = path.resolve(process.env.KBPREP_VAULT_SMOKE_ROOT || defaultVaultRoot());
const workRoot = mkdtempSync(path.join(tmpdir(), "kbprep-vault-pdf-phase-b-"));
const ignoredDirs = new Set([".obsidian", ".trash", ".git", "node_modules", "dist", "build", "coverage", "kbprep-output"]);

if (!existsSync(vaultRoot)) fail(`Vault root does not exist: ${vaultRoot}`);

const pdfs = collectFiles(vaultRoot).filter((file) => path.extname(file).toLowerCase() === ".pdf");
if (pdfs.length === 0) fail("No PDF files found in Vault");

const diagnoses = pdfs.map((file) => diagnose(file)).filter(Boolean);
const selected = selectSix(diagnoses);
const missing = Object.entries(selected).filter(([, value]) => !value).map(([name]) => name);
if (missing.length) {
  fail(`Missing required real PDF acceptance class(es): ${missing.join(", ")}`);
}

process.stdout.write(JSON.stringify({
  ok: true,
  pdfCount: pdfs.length,
  workRoot,
  selected: Object.fromEntries(Object.entries(selected).map(([name, item]) => [name, publicEvidence(item)])),
}, null, 2));
process.stdout.write("\n");
rmSync(workRoot, { recursive: true, force: true });

function diagnose(file) {
  const result = spawnSync(process.execPath, [
    path.join(repoRoot, "scripts", "python-venv.mjs"),
    "-m",
    "kbprep_worker.cli",
    "diagnose",
    "--json-stdin",
  ], {
    cwd: repoRoot,
    input: JSON.stringify({ input_path: file, output_root: workRoot, source_type: "auto" }),
    encoding: "utf8",
    timeout: 120_000,
    env: { ...process.env, PYTHONUTF8: "1" },
  });
  if (result.status !== 0) return null;
  const lines = result.stdout.trim().split(/\r?\n/).filter(Boolean);
  const payload = JSON.parse(lines.at(-1) || "{}");
  if (!payload.ok || payload.data?.detected_format !== "pdf") return null;
  return { file, data: payload.data };
}

function selectSix(items) {
  return {
    simple_single_column: first(items, (item) => tier(item) === "tier_1" && pages(item) > 0 && !isEnglishRiskProbe(item)),
    english_simple_text: first(items, (item) => tier(item) === "tier_1" && language(item) === "en"),
    multi_column_paper: first(items, (item) => tier(item) === "tier_2" && item.data.multi_column_pages > 0),
    table_heavy: first(items, (item) => tier(item) === "tier_2" && item.data.table_pages > 0),
    scanned: first(items, (item) => tier(item) === "tier_3" && item.data.pdf_subtype === "image_only_or_scanned"),
    cid_or_tounicode_damaged: first(items, (item) => tier(item) === "tier_3" && item.data.pdf_subtype === "garbled_text_layer"),
  };
}

function first(items, predicate) {
  return items.find(predicate) || null;
}

function publicEvidence(item) {
  const diagnostics = item.data.pdf_route_diagnostics || {};
  return {
    id: createHash("sha256").update(path.relative(vaultRoot, item.file)).digest("hex").slice(0, 12),
    sizeMb: Number((statSync(item.file).size / 1024 / 1024).toFixed(1)),
    pageCount: item.data.page_count,
    sampledPageCount: item.data.sampled_page_count,
    pdfSubtype: item.data.pdf_subtype,
    textLayerHealth: item.data.text_layer_health,
    layoutComplexity: item.data.layout_complexity,
    recommendedTier: diagnostics.recommended_tier,
    recommendedRoute: diagnostics.recommended_route,
    warningCount: Array.isArray(item.data.warnings) ? item.data.warnings.length : 0,
  };
}

function tier(item) {
  return item.data.pdf_route_diagnostics?.recommended_tier || "";
}

function pages(item) {
  return Number(item.data.page_count || 0);
}

function language(item) {
  return String(item.data.detected_language || "");
}

function isEnglishRiskProbe(item) {
  return language(item) === "en";
}

function collectFiles(root) {
  const collected = [];
  function walk(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (ignoredDirs.has(entry.name)) continue;
        walk(full);
      } else if (entry.isFile()) {
        collected.push(full);
      }
    }
  }
  walk(root);
  return collected;
}

function defaultVaultRoot() {
  return process.platform === "win32" ? "F:\\Obsidian-Vault" : "/mnt/f/Obsidian-Vault";
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.stderr.write(`Isolated work root: ${workRoot}\n`);
  process.exit(1);
}
```

- [ ] **Step 4: Add npm script**

In `package.json`, add:

```json
"vault:pdf-phase-b": "node scripts/check-vault-pdf-phase-b.mjs"
```

Place it next to the existing `vault:smoke` script.

- [ ] **Step 5: Run public and Vault acceptance checks**

Run:

```powershell
npm test -- src/test/scenarios/worker-pdf-routing.test.ts
npm run vault:pdf-phase-b
```

Expected:

- The public scenario test passes.
- `npm run vault:pdf-phase-b` passes only if all six real sample classes are found in `F:\Obsidian-Vault`.
- If Vault lacks a class, do not invent it. Record the missing class in the final report and keep `pdf_diagnosis_selected` partial.

- [ ] **Step 6: Commit public tests and script**

Commit:

```powershell
git add src/test/helpers/workerHarness.ts src/test/scenarios/worker-pdf-routing.test.ts scripts/check-vault-pdf-phase-b.mjs package.json
git commit -m "test: add phase b pdf acceptance checks"
```

---

## Task 6: Update Capability Status And Operator Docs

**Files:**
- Modify: `python/kbprep_worker/converter_capabilities.py`
- Modify: `docs/capability-matrix.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/00-current-state-and-gap.md`
- Modify: `docs/known-issues.md`
- Modify: `README.md`
- Modify: `docs/standalone-cli.md`

- [ ] **Step 1: Update capability evidence conservatively**

If Task 5 found all six real Vault classes and all public tests pass, update the `pdf_diagnosis_selected` entry in `python/kbprep_worker/converter_capabilities.py`:

```python
        "status": "verified",
        "test_evidence": [
            "python/tests/test_pdf_route_diagnostics.py",
            "python/tests/test_pdf_route_policy.py",
            "python/tests/test_pymupdf4llm_adapter.py",
            "src/test/scenarios/worker-pdf-routing.test.ts::classifies the six Phase B public PDF acceptance shapes",
            "src/test/scenarios/worker-pdf-routing.test.ts::routes trusted multi-column PDFs through Tier 2 MinerU txt mode",
            "scripts/check-vault-pdf-phase-b.mjs",
        ],
```

If Task 5 reports a missing Vault class, keep:

```python
        "status": "partial",
```

and update `promotion_blocker` to name the exact missing class names from the script output.

- [ ] **Step 2: Update reader-facing matrix**

In `docs/capability-matrix.md`, update only the PDF row.

Verified wording when all evidence passes:

```markdown
| pdf_diagnosis_selected | PDF | pdf_diagnosis_selected | verified | page order, trusted text-layer structure, layout evidence, OCR text when routed to MinerU, image evidence | `python/tests/test_pdf_route_diagnostics.py`; `python/tests/test_pdf_route_policy.py`; `python/tests/test_pymupdf4llm_adapter.py`; `src/test/scenarios/worker-pdf-routing.test.ts::classifies the six Phase B public PDF acceptance shapes`; `scripts/check-vault-pdf-phase-b.mjs` | route quality still depends on local dependency availability and source PDF quality; failed quality gates block publication |
```

Partial wording when a Vault class is missing:

```markdown
| pdf_diagnosis_selected | PDF | pdf_diagnosis_selected | partial | page order, trusted text-layer structure, layout evidence, OCR text when routed to MinerU, image evidence | `python/tests/test_pdf_route_diagnostics.py`; `python/tests/test_pdf_route_policy.py`; `python/tests/test_pymupdf4llm_adapter.py`; `src/test/scenarios/worker-pdf-routing.test.ts` | Phase B route behavior exists, but promotion remains blocked by the concrete missing real-sample class names printed by `npm run vault:pdf-phase-b`. |
```

Use the exact missing class list from script output. Do not write a generic phrase if the script names concrete gaps.

- [ ] **Step 3: Update roadmap and known issues**

In `docs/development/development-roadmap.md`, update B2-B5 bullets only after tests pass:

```markdown
- **B2** Landed: Tier 1 `pymupdf4llm` handles trusted text layer + simple layout.
- **B3** Landed: Tier 2 selects `mineru_txt` or `mineru_auto` for trusted text layer + complex layout.
- **B4** Landed: Tier 3 `mineru_ocr` is selected from untrusted text-layer evidence and one-upgrade fallback records its reason.
- **B5** Landed: the six acceptance cases are covered by public route tests and real Vault smoke evidence.
```

If Vault evidence is incomplete, keep B5 open:

```markdown
- **B5** Open: the six acceptance cases require real Vault smoke evidence before capability promotion.
```

In `docs/known-issues.md`, remove the old Phase B gap only when B5 is fully proved. If B5 is incomplete, replace it with:

```markdown
- PDF routing now executes the protected three-tier design, but capability promotion remains blocked until real Vault smoke evidence covers the missing Phase B acceptance classes.
```

- [ ] **Step 4: Update operator docs**

In `README.md` and `docs/standalone-cli.md`, add a short PDF route note:

```markdown
PDF routing is diagnosis-selected: simple trusted text-layer PDFs use `pymupdf4llm`, complex trusted PDFs use MinerU `txt` or `auto`, and scanned or untrusted text-layer PDFs use MinerU `ocr`. `conversion_report.json.route_decision` records the selected tier, actual route, fallback or upgrade, and reason.
```

- [ ] **Step 5: Search for stale claims**

Run:

```powershell
rg -n "pdf_text_layer.*default|Tier 1.*not implemented|B2.*Open|B3.*Open|B4.*Open|B5.*Open|pdf_diagnosis_selected.*partial" docs python src -g "!docs/superpowers/plans/**"
```

Expected when fully verified: no stale matches except historical notes that explicitly say they are historical.

Expected when B5 remains incomplete: matches are allowed only where the wording says exactly which real sample classes are missing.

- [ ] **Step 6: Run governance checks and commit**

Run:

```powershell
npm run check:development-docs
npm run pack:check
git diff --check
```

Expected: PASS.

Commit:

```powershell
git add python/kbprep_worker/converter_capabilities.py docs/capability-matrix.md docs/development/development-roadmap.md docs/development/00-current-state-and-gap.md docs/known-issues.md README.md docs/standalone-cli.md
git commit -m "docs: record phase b pdf routing status"
```

---

## Task 7: Final Verification, Review, And Push

**Files:**
- Review every changed file from Tasks 1-6.

- [ ] **Step 1: Run complete project verification**

Run:

```powershell
npm run dev:full-check
npm run vault:pdf-phase-b
git diff --check
```

Expected:

- `npm run dev:full-check` passes.
- `npm run vault:pdf-phase-b` passes or reports exact missing real sample classes.
- `git diff --check` has no output.

- [ ] **Step 2: File-size and code-quality review**

Run:

```powershell
npm run python:check-size
npm run python:ruff
npm run python:typecheck
npm test
```

Expected:

- Python files stay under 800 lines.
- Python functions stay at or under 50 lines.
- Ruff and mypy pass.
- TypeScript/Vitest suite passes.

- [ ] **Step 3: Bug review search**

Run:

```powershell
rg -n "except:|print\\(|setattr\\(|as unknown as|\\bany\\b|T[O]DO|T[B]D" python/kbprep_worker python/tests src scripts docs -g "!docs/superpowers/plans/**"
rg -n "pdf_diagnosis_selected.*verified|Phase B.*complete|B5.*Landed" docs python src -g "!docs/superpowers/plans/**"
```

Expected:

- First command has no new production-code hits from this phase.
- Second command is allowed only if Task 5 fully passed and capability docs name the supporting evidence.

- [ ] **Step 4: Inspect git status and commit or amend only task-related changes**

Run:

```powershell
git status --short --branch
git log --oneline -8
```

Expected:

- Only task-related files are modified or committed.
- Existing unrelated untracked files remain untouched unless the owner separately asks to handle them.

- [ ] **Step 5: Push branch**

Run:

```powershell
git push -u origin HEAD
```

Expected: branch is pushed and ready for PR or follow-up review.

---

## Acceptance Checklist

- `conversion_report.json.route_decision` records selected PDF tier, actual route, fallback/upgrade fields, and reason for every PDF.
- Tier 1 simple trusted PDFs execute `pymupdf4llm`.
- Tier 2 trusted complex PDFs execute MinerU `txt` or `auto` with explicit mode evidence.
- Tier 3 untrusted/scanned PDFs execute MinerU `ocr`.
- PDF upgrade happens at most once and records rejected Markdown evidence.
- Six public route-shape tests pass.
- Real Vault PDF smoke either passes all six classes or blocks capability promotion with exact missing class names.
- `pdf_diagnosis_selected` is promoted only when the evidence supports it.
- No real Vault sample files, names, paths, or extracted private text are committed.
- `npm run dev:full-check` passes.
- Code review and bug review show zero unresolved issues before completion.
