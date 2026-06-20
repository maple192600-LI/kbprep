import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  makeEpubFixture,
  makeGarbledTextLayerPdf,
  makeImageOnlyPdf,
  makeLandscapeImagePdf,
  makeLandscapeTextPdf,
  makeOfficeFixtures,
  makeTextLayerPdf,
  normalizeMarkdownText,
  parseEnvelope,
  repoRoot,
  runPython,
  runPythonJson,
  runWorker,
  runWorkerRawInput,
} from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - output guards part 1", () => {
  it("copies local Markdown image assets into run and latest outputs", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-md-assets-"));
    try {
      const sourceDir = path.join(root, "source");
      const outputRoot = path.join(root, "out");
      const assetsDir = path.join(sourceDir, "assets");
      const imagesDir = path.join(sourceDir, "images");
      mkdirSync(assetsDir, { recursive: true });
      mkdirSync(imagesDir, { recursive: true });
      const png1x1 = Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
        "base64",
      );
      writeFileSync(path.join(assetsDir, "step.png"), png1x1);
      writeFileSync(path.join(assetsDir, "chart.png"), png1x1);
      writeFileSync(path.join(imagesDir, "result.png"), png1x1);

      const inputPath = path.join(sourceDir, "note.md");
      writeFileSync(
        inputPath,
        [
          "# 操作截图",
          "",
          "步骤 1：打开后台，把 threshold=0.8 填到配置项。",
          "![步骤截图](assets/step.png)",
          "",
          "步骤 2：检查结果图，确认参数没有丢。",
          "![[assets/chart.png]]",
          "",
          "![结果图](images/result.png)",
        ].join("\n"),
        "utf8",
      );

      const result = runWorker("prepare", {
        input_path: inputPath,
        output_root: outputRoot,
        profile: "standard",
        mode: "rules_only",
        language: "zh",
        source_type: "auto",
        splitter: "auto",
        force: true,
      });

      expect(result.ok).toBe(true);
      const latest = result.data.latest_outputs;
      const converted = readFileSync(latest.converted_md, "utf8");
      const cleaned = readFileSync(latest.cleaned_md, "utf8");
      const report = JSON.parse(readFileSync(latest.quality_report, "utf8"));

      expect(converted).toContain("![步骤截图](images/assets/step.png)");
      expect(converted).toContain("![](images/assets/chart.png)");
      expect(converted).toContain("![结果图](images/result.png)");
      expect(converted).not.toContain("images/images/result.png");
      expect(cleaned).toContain("threshold=0.8");
      expect(existsSync(path.join(result.data.run_dir, "images", "assets", "step.png"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "images", "assets", "step.png"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "images", "assets", "chart.png"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "images", "result.png"))).toBe(true);
      expect(latest.obsidian_dir).toBeNull();
      expect(latest.obsidian_index).toBeNull();
      expect(report.image_retention.missing_file_count).toBe(0);
      expect(report.strict_errors).toEqual([]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("fails prepare when strict quality gates fail instead of publishing latest outputs", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-strict-gate-"));
    try {
      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import prepare, quality",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "input_path.write_text('# Clean text\\n\\nStep 1: keep threshold=0.8.\\n', encoding='utf-8')",
          "def fake_quality(**kwargs):",
          "    return {",
          "        'strict_errors': ['E_QA_FAILED: forced strict error'],",
          "        'warnings': [],",
          "        'quality_gates': [{'name': 'export_readiness', 'status': 'fail'}],",
          "        'next_actions': [{'gate': 'export_readiness', 'action': 'block_export', 'target': 'latest_outputs'}],",
          "        'quality_tasks': {'schema': 'kbprep.quality_tasks.v1', 'tasks': [{'id': 'task-export-readiness', 'gate': 'export_readiness'}]},",
          "    }",
          "quality.run_quality_check = fake_quality",
          "stdout = io.StringIO()",
          "old_stdout = sys.stdout",
          "try:",
          "    sys.stdout = stdout",
          "    try:",
          "        prepare.run({'input_path': str(input_path), 'output_root': str(output_root), 'profile': 'lite', 'mode': 'rules_only', 'language': 'zh', 'source_type': 'auto', 'splitter': 'auto', 'force': True})",
          "    except SystemExit:",
          "        pass",
          "finally:",
          "    sys.stdout = old_stdout",
          "payload = json.loads(stdout.getvalue())",
          "assert payload['ok'] is False, payload",
          "assert payload['error']['code'] == 'E_QA_FAILED', payload",
          "assert payload['error']['details']['legacy_code'] == 'E_QA_FAILED', payload",
          "assert 'run_dir' in payload['error']['details'], payload",
          "assert payload['error']['details']['quality_gates'][0]['name'] == 'export_readiness', payload",
          "assert payload['error']['details']['next_actions'][0]['action'] == 'block_export', payload",
          "assert payload['error']['details']['quality_tasks']['schema'] == 'kbprep.quality_tasks.v1', payload",
          "assert payload['error']['details']['quality_tasks']['tasks'][0]['gate'] == 'export_readiness', payload",
          "assert not (output_root / 'latest.json').exists(), list(output_root.iterdir())",
        ].join("\n"),
        [path.join(root, "input.md"), path.join(root, "output")],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not render Obsidian vault outputs before strict quality gates pass", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-strict-obsidian-"));
    try {
      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import prepare, quality",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "input_path.write_text('# Clean text\\n\\nStep 1: keep threshold=0.8.\\n', encoding='utf-8')",
          "def fake_quality(**kwargs):",
          "    return {",
          "        'strict_errors': ['E_QA_FAILED: forced strict error'],",
          "        'warnings': [],",
          "        'quality_gates': [{'name': 'export_readiness', 'status': 'fail'}],",
          "        'next_actions': [{'gate': 'export_readiness', 'action': 'block_export', 'target': 'latest_outputs'}],",
          "        'quality_tasks': {'schema': 'kbprep.quality_tasks.v1', 'tasks': [{'id': 'task-export-readiness', 'gate': 'export_readiness'}]},",
          "    }",
          "quality.run_quality_check = fake_quality",
          "stdout = io.StringIO()",
          "old_stdout = sys.stdout",
          "try:",
          "    sys.stdout = stdout",
          "    try:",
          "        prepare.run({'input_path': str(input_path), 'output_root': str(output_root), 'profile': 'obsidian_kb', 'mode': 'rules_only', 'language': 'zh', 'source_type': 'auto', 'splitter': 'auto', 'force': True})",
          "    except SystemExit:",
          "        pass",
          "finally:",
          "    sys.stdout = old_stdout",
          "payload = json.loads(stdout.getvalue())",
          "assert payload['ok'] is False, payload",
          "run_dir = Path(payload['error']['details']['run_dir'])",
          "assert (run_dir / 'cleaned.md').exists(), list(run_dir.iterdir())",
          "assert not (run_dir / 'obsidian').exists(), list(run_dir.iterdir())",
          "assert payload['error']['details']['outputs']['obsidian_dir'] is None, payload",
          "assert not (output_root / 'obsidian').exists(), list(output_root.iterdir())",
          "assert not (output_root / 'latest.json').exists(), list(output_root.iterdir())",
        ].join("\n"),
        [path.join(root, "input.md"), path.join(root, "output")],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("blocks prepare when source headings and tables are lost during conversion", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-source-loss-gate-"));
    try {
      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import prepare",
          "from kbprep_worker.stages import pipeline",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "input_path.write_text('# Source Title\\n\\n## Critical Section\\n\\n| A | B |\\n|---|---|\\n| keep | threshold=0.8 |\\n', encoding='utf-8')",
          "def lossy_direct_source(path, *, run_dir):",
          "    return '# Source Title\\n\\nKeep threshold=0.8.\\n'",
          "pipeline._read_direct_source = lossy_direct_source",
          "stdout = io.StringIO()",
          "old_stdout = sys.stdout",
          "try:",
          "    sys.stdout = stdout",
          "    try:",
          "        prepare.run({'input_path': str(input_path), 'output_root': str(output_root), 'profile': 'obsidian_kb', 'mode': 'rules_only', 'language': 'zh', 'source_type': 'auto', 'splitter': 'auto', 'force': True})",
          "    except SystemExit:",
          "        pass",
          "finally:",
          "    sys.stdout = old_stdout",
          "payload = json.loads(stdout.getvalue())",
          "assert payload['ok'] is False, payload",
          "assert payload['error']['code'] == 'E_SOURCE_CONVERSION_LOSS', payload",
          "assert payload['error']['details']['legacy_code'] == 'E_QA_FAILED', payload",
          "run_dir = Path(payload['error']['details']['run_dir'])",
          "quality = json.loads((run_dir / 'quality_report.json').read_text(encoding='utf-8'))",
          "assert any('source headings missing from converted Markdown' in err for err in quality['strict_errors']), quality",
          "assert any('source tables missing from converted Markdown' in err for err in quality['strict_errors']), quality",
          "assert quality['source_conversion_integrity']['missing_heading_count'] == 1, quality",
          "assert quality['source_conversion_integrity']['missing_table_count'] == 1, quality",
          "gates = {gate['name']: gate for gate in quality['quality_gates']}",
          "assert gates['conversion_integrity']['status'] == 'fail', gates",
          "assert payload['error']['details']['outputs']['obsidian_dir'] is None, payload",
          "assert not (run_dir / 'obsidian').exists(), list(run_dir.iterdir())",
          "assert not (output_root / 'latest.json').exists(), list(output_root.iterdir())",
        ].join("\n"),
        [path.join(root, "input.md"), path.join(root, "output")],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("blocks prepare when cleaning deletes protected source body content", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-unsafe-cleaning-gate-"));
    try {
      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import clean_rules, prepare",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "input_path.write_text('# Source Title\\n\\nStep 1: keep threshold=0.8 and verify the account id.\\n', encoding='utf-8')",
          "def unsafe_clean(blocks, **kwargs):",
          "    for block in blocks:",
          "        if 'threshold=0.8' in block.get('text', ''):",
          "            block['type'] = 'operation_step'",
          "            block['protected'] = True",
          "            block['status'] = 'discard'",
          "            block['reason'] = 'simulated_unsafe_cleanup'",
          "    return blocks",
          "clean_rules.apply_clean_rules = unsafe_clean",
          "stdout = io.StringIO()",
          "old_stdout = sys.stdout",
          "try:",
          "    sys.stdout = stdout",
          "    try:",
          "        prepare.run({'input_path': str(input_path), 'output_root': str(output_root), 'profile': 'obsidian_kb', 'mode': 'rules_only', 'language': 'zh', 'source_type': 'auto', 'splitter': 'auto', 'force': True})",
          "    except SystemExit:",
          "        pass",
          "finally:",
          "    sys.stdout = old_stdout",
          "payload = json.loads(stdout.getvalue())",
          "assert payload['ok'] is False, payload",
          "assert payload['error']['code'] == 'E_PROTECTED_BLOCK_LOSS', payload",
          "assert payload['error']['details']['legacy_code'] == 'E_QA_FAILED', payload",
          "run_dir = Path(payload['error']['details']['run_dir'])",
          "quality = json.loads((run_dir / 'quality_report.json').read_text(encoding='utf-8'))",
          "assert any('protected blocks were discarded' in err for err in quality['strict_errors']), quality",
          "assert any('operation_step blocks were discarded' in err for err in quality['strict_errors']), quality",
          "gates = {gate['name']: gate for gate in quality['quality_gates']}",
          "assert gates['cleanup_safety']['status'] == 'fail', gates",
          "discarded = (run_dir / 'discarded.md').read_text(encoding='utf-8')",
          "assert 'threshold=0.8' in discarded, discarded",
          "assert payload['error']['details']['outputs']['obsidian_dir'] is None, payload",
          "assert not (run_dir / 'obsidian').exists(), list(run_dir.iterdir())",
          "assert not (output_root / 'latest.json').exists(), list(output_root.iterdir())",
        ].join("\n"),
        [path.join(root, "input.md"), path.join(root, "output")],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not reuse a cached run whose strict quality gates failed", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-failed-cache-"));
    try {
      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import prepare, quality",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "input_path.write_text('# Clean text\\n\\nStep 1: keep threshold=0.8.\\n', encoding='utf-8')",
          "calls = {'count': 0}",
          "def fake_quality(**kwargs):",
          "    calls['count'] += 1",
          "    if calls['count'] == 1:",
          "        return {",
          "            'strict_errors': ['E_QA_FAILED: first run failed'],",
          "            'warnings': [],",
          "            'quality_gates': [{'name': 'export_readiness', 'status': 'fail'}],",
          "            'next_actions': [{'gate': 'export_readiness', 'action': 'block_export', 'target': 'latest_outputs'}],",
          "        }",
          "    return {'strict_errors': [], 'warnings': [], 'quality_gates': [{'name': 'export_readiness', 'status': 'pass'}], 'next_actions': []}",
          "quality.run_quality_check = fake_quality",
          "def invoke(force):",
          "    stdout = io.StringIO()",
          "    old_stdout = sys.stdout",
          "    try:",
          "        sys.stdout = stdout",
          "        try:",
          "            prepare.run({'input_path': str(input_path), 'output_root': str(output_root), 'profile': 'lite', 'mode': 'rules_only', 'language': 'zh', 'source_type': 'auto', 'splitter': 'auto', 'force': force})",
          "        except SystemExit:",
          "            pass",
          "    finally:",
          "        sys.stdout = old_stdout",
          "    return json.loads(stdout.getvalue())",
          "first = invoke(True)",
          "second = invoke(False)",
          "assert first['ok'] is False, first",
          "assert second['ok'] is True, second",
          "assert second['data'].get('skipped') is not True, second",
          "assert calls['count'] == 2, calls",
          "assert (output_root / 'latest.json').exists(), list(output_root.iterdir())",
        ].join("\n"),
        [path.join(root, "input.md"), path.join(root, "output")],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("unwraps trusted PDF text-layer hard line breaks without merging structural lines", () => {
    runPython(
      [
        "from kbprep_worker.pdf_text import _normalize_page_text",
        "raw = '\\n'.join([",
        "    '2026AI+美妆消费趋势报告',",
        "    '科技赋能，精准定义新美学生态',",
        "    '',",
        "    'AI技术从产品研',",
        "    '发、消费者体验与品牌沟通模式重塑行业。',",
        "    '- 保留列表项一',",
        "    '- 保留列表项二',",
        "    '<!-- page: 2 -->',",
        "    '新的页面标记不能合并'",
        "])",
        "normalized = _normalize_page_text(raw)",
        "assert 'AI技术从产品研发、消费者体验与品牌沟通模式重塑行业。' in normalized, normalized",
        "assert '产品研\\n发、消费者' not in normalized, normalized",
        "assert '2026AI+美妆消费趋势报告\\n科技赋能，精准定义新美学生态' in normalized, normalized",
        "assert '- 保留列表项一\\n- 保留列表项二' in normalized, normalized",
        "assert '<!-- page: 2 -->\\n新的页面标记不能合并' in normalized, normalized",
      ].join("\n"),
      [],
    );
  });

});
