import { mkdtempSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  makeChineseTextLayerPdf,
  makeGarbledTextLayerPdf,
  makeImageOnlyPdf,
  makeMultiColumnTextPdf,
  makeTableHeavyPdf,
  makeTextLayerPdf,
  runPython,
  runWorker,
} from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - PDF routing part 2", () => {
  it("classifies the six Phase B public PDF acceptance shapes", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-phase-b-public-"));
    try {
      const outputRoot = path.join(root, "output");
      mkdirSync(outputRoot);
      const cases = [
        {
          name: "simple",
          maker: () => makeChineseTextLayerPdf(path.join(root, "simple.pdf")),
          file: "simple.pdf",
          tier: "tier_1",
          route: "pymupdf4llm",
        },
        {
          name: "english",
          maker: () => makeTextLayerPdf(path.join(root, "english.pdf")),
          file: "english.pdf",
          tier: "tier_1",
          route: "pymupdf4llm",
        },
        {
          name: "multi-column",
          maker: () => makeMultiColumnTextPdf(path.join(root, "multi-column.pdf")),
          file: "multi-column.pdf",
          tier: "tier_2",
          route: "mineru_txt",
        },
        {
          name: "table-heavy",
          maker: () => makeTableHeavyPdf(path.join(root, "table-heavy.pdf")),
          file: "table-heavy.pdf",
          tier: "tier_2",
          route: "mineru_auto",
        },
        {
          name: "scanned",
          maker: () => makeImageOnlyPdf(path.join(root, "scanned.pdf"), path.join(root, "scanned.png")),
          file: "scanned.pdf",
          tier: "tier_3",
          route: "mineru_ocr",
        },
        {
          name: "cid-damaged",
          maker: () => makeGarbledTextLayerPdf(path.join(root, "cid-damaged.pdf")),
          file: "cid-damaged.pdf",
          tier: "tier_3",
          route: "mineru_ocr",
        },
      ];

      for (const item of cases) {
        item.maker();
        const diagnosis = runWorker("diagnose", {
          input_path: path.join(root, item.file),
          output_root: outputRoot,
          source_type: "auto",
        });
        const pdfRoute = diagnosis.data.pdf_route_diagnostics;
        expect(pdfRoute.recommended_tier, item.name).toBe(item.tier);
        expect(pdfRoute.recommended_route, item.name).toBe(item.route);
        expect(pdfRoute.reason, item.name).toContain(`Tier ${item.tier.slice(-1)}`);
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("routes trusted multi-column PDFs through MinerU txt mode", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-multicolumn-pdf-route-"));
    try {
      const inputPath = path.join(root, "multi-column.pdf");
      const outputRoot = path.join(root, "output");
      makeMultiColumnTextPdf(inputPath);

      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import mineru_adapter, prepare",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "calls = []",
          "def fake_mineru(**kwargs):",
          "    calls.append(kwargs.get('mode'))",
          "    out = Path(kwargs['output_dir']) / 'mineru_txt.md'",
          "    out.write_text('# Multi-column text result\\n\\nKeep threshold=0.8 and retry_count=3 from both columns.\\n', encoding='utf-8')",
          "    return {",
          "        'source_md_path': str(out),",
          "        'content_list_path': None,",
          "        'content_list_v2_path': None,",
          "        'middle_json_path': None,",
          "        'assets_dir': None,",
          "        'converter': 'mineru',",
          "        'warnings': ['fake multi-column txt'],",
          "    }",
          "mineru_adapter.run_mineru = fake_mineru",
          "stdout = io.StringIO()",
          "old_stdout = sys.stdout",
          "try:",
          "    sys.stdout = stdout",
          "    try:",
          "        prepare.run({",
          "            'input_path': str(input_path),",
          "            'output_root': str(output_root),",
          "            'profile': 'standard',",
          "            'mode': 'rules_only',",
          "            'language': 'zh',",
          "            'source_type': 'auto',",
          "            'splitter': 'auto',",
          "            'force': True,",
          "        })",
          "    except SystemExit:",
          "        pass",
          "finally:",
          "    sys.stdout = old_stdout",
          "payload = json.loads(stdout.getvalue())",
          "assert payload['ok'] is True, payload",
          "assert calls == ['txt'], calls",
          "cleaned = Path(payload['data']['latest_outputs']['cleaned_md']).read_text(encoding='utf-8')",
          "diagnosis = json.loads(Path(payload['data']['latest_outputs']['diagnosis_report']).read_text(encoding='utf-8'))",
          "report = json.loads(Path(payload['data']['latest_outputs']['conversion_report']).read_text(encoding='utf-8'))",
          "assert 'threshold=0.8' in cleaned, cleaned",
          "assert diagnosis['text_layer_health'] == 'good', diagnosis",
          "assert diagnosis['needs_ocr'] is False, diagnosis",
          "assert diagnosis['layout_complexity'] == 'complex', diagnosis",
          "assert diagnosis['multi_column_pages'] >= 1, diagnosis",
          "assert diagnosis['conversion_strategy'] == 'mineru_txt', diagnosis",
          "assert report['converter'] == 'mineru', report",
          "decision = report['route_decision']",
          "assert decision['declared_route'] == 'pdf_diagnosis_selected', decision",
          "assert decision['diagnosed_strategy'] == 'mineru_txt', decision",
          "assert decision['actual_converter'] == 'mineru', decision",
          "assert decision['actual_route'] == 'mineru_txt', decision",
          "assert decision['selected_route'] == 'mineru_txt', decision",
          "assert decision['fallback_applied'] is False, decision",
          "assert decision['selected_pdf_tier'] == 'tier_2', decision",
          "assert 'Tier 2' in decision['pdf_route_reason'], decision",
          "assert report['mineru_artifacts']['mineru_mode'] == 'txt', report",
          "assert report['pdf_route_diagnostics']['recommended_tier'] == 'tier_2', report",
          "assert report['pdf_route_diagnostics']['recommended_route'] == 'mineru_txt', report",
          "assert report['pdf_route_diagnostics']['structure_signals']['multi_column'] is True, report",
        ].join("\n"),
        [inputPath, outputRoot],
        true,
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 10_000);

  it("falls back to MinerU when a trusted Tier 1 PDF conversion produces unreadable Markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-pdf-fallback-"));
    try {
      const inputPath = path.join(root, "tutorial.pdf");
      const outputRoot = path.join(root, "output");
      makeTextLayerPdf(inputPath);

      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import mineru_adapter, prepare, pymupdf4llm_adapter",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "calls = []",
          "def bad_tier_1(input_path, output_path, run_dir):",
          "    output_path.write_text(('Ჭ䌦圳➉ᵜⰭ䕇✮⦽ ' * 120) + '\\n', encoding='utf-8')",
          "    content_list = run_dir / 'pymupdf4llm_content_list.json'",
          "    content_list.write_text('[]', encoding='utf-8')",
          "    return {",
          "        'source_md_path': str(output_path),",
          "        'content_list_path': str(content_list),",
          "        'content_list_v2_path': None,",
          "        'middle_json_path': None,",
          "        'assets_dir': None,",
          "        'converter': 'pymupdf4llm',",
          "        'warnings': ['fake bad tier 1'],",
          "    }",
          "def fake_mineru(**kwargs):",
          "    calls.append(kwargs.get('mode'))",
          "    out = Path(kwargs['output_dir']) / 'mineru_ocr.md'",
          "    out.write_text('# OCR result\\n\\n1. Open settings and keep threshold=0.8.\\n\\nRetry_count=3 must stay.\\n', encoding='utf-8')",
          "    return {",
          "        'source_md_path': str(out),",
          "        'content_list_path': None,",
          "        'content_list_v2_path': None,",
          "        'middle_json_path': None,",
          "        'assets_dir': None,",
          "        'converter': 'mineru',",
          "        'warnings': ['fake mineru fallback'],",
          "    }",
          "pymupdf4llm_adapter.convert_pymupdf4llm_pdf = bad_tier_1",
          "mineru_adapter.run_mineru = fake_mineru",
          "stdout = io.StringIO()",
          "old_stdout = sys.stdout",
          "try:",
          "    sys.stdout = stdout",
          "    try:",
          "        prepare.run({",
          "            'input_path': str(input_path),",
          "            'output_root': str(output_root),",
          "            'profile': 'standard',",
          "            'mode': 'rules_only',",
          "            'language': 'zh',",
          "            'source_type': 'auto',",
          "            'splitter': 'auto',",
          "            'force': True,",
          "        })",
          "    except SystemExit:",
          "        pass",
          "finally:",
          "    sys.stdout = old_stdout",
          "payload = json.loads(stdout.getvalue())",
          "assert payload['ok'] is True, payload",
          "assert calls == ['ocr'], calls",
          "cleaned = Path(payload['data']['latest_outputs']['cleaned_md']).read_text(encoding='utf-8')",
          "report = json.loads(Path(payload['data']['latest_outputs']['conversion_report']).read_text(encoding='utf-8'))",
          "assert 'threshold=0.8' in cleaned, cleaned",
          "assert 'Ჭ䌦圳' not in cleaned, cleaned",
          "assert report['converter'] == 'mineru_after_pymupdf4llm_fallback', report",
          "decision = report['route_decision']",
          "assert decision['declared_route'] == 'pdf_diagnosis_selected', decision",
          "assert decision['diagnosed_strategy'] == 'pdf_text_layer', decision",
          "assert decision['actual_converter'] == 'mineru_after_pymupdf4llm_fallback', decision",
          "assert decision['actual_route'] == 'mineru_ocr', decision",
          "assert decision['fallback_applied'] is True, decision",
          "assert decision['fallback_from'] == 'pymupdf4llm', decision",
          "assert decision['fallback_to'] == 'mineru_ocr', decision",
          "assert decision['selected_pdf_tier'] == 'tier_1', decision",
          "assert decision['pdf_route_diagnostics_schema'] == 'kbprep.pdf_route_diagnostics.v1', decision",
          "assert 'Tier 1' in decision['pdf_route_reason'], decision",
          "assert report['pdf_route_diagnostics']['recommended_tier'] == 'tier_1', report",
          "assert report['mineru_artifacts']['fallback_from'] == 'pymupdf4llm', report",
          "assert any('W_PDF_MARKDOWN_FALLBACK_TO_OCR' in warning for warning in report['warnings']), report",
        ].join("\n"),
        [inputPath, outputRoot],
        true,
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 10_000);
});
