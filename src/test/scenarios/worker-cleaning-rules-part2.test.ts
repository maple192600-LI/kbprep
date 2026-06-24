import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runPython, runWorker } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - cleanup rules part 2", () => {
  it("keeps short policy-analysis paragraphs that mention public account CTA terms", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-cta-policy-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "policy.md");
      writeFileSync(sourcePath, ["# 平台规则分析", "", "平台规则：不得诱导关注公众号，这类文案要作为违规案例记录。"].join("\n"), "utf8");

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "standard",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const runDir = envelope.data.run_dir;
      const cleaned = readFileSync(path.join(runDir, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(runDir, "discarded.md"), "utf8");

      expect(envelope.ok).toBe(true);
      expect(cleaned).toContain("不得诱导关注公众号");
      expect(discarded).not.toContain("不得诱导关注公众号");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("detects English language and preserves tutorial CTA examples", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-english-cta-"));
    try {
      const inputPath = path.join(root, "english.md");
      const outputRoot = path.join(root, "out");
      writeFileSync(
        inputPath,
        [
          "# Platform Policy Tutorial",
          "",
          "Step 1: record threshold=0.8 and retry_count=3 before changing the campaign.",
          "",
          'Policy example: do not write "scan the QR code to join our Discord" in the landing page CTA.',
          "",
          "Scan the QR code to join our Discord and claim your free trial.",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: inputPath,
        output_root: outputRoot,
        profile: "standard",
        mode: "rules_only",
        language: "en",
        force: true,
      });

      const quality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));
      const cleaned = readFileSync(envelope.data.latest_outputs.cleaned_md, "utf8");
      const discarded = readFileSync(envelope.data.latest_outputs.discarded_md, "utf8");
      expect(quality.language_detected).toBe("en");
      expect(cleaned).toContain("threshold=0.8");
      expect(cleaned).toContain("Policy example");
      expect(cleaned).not.toContain("claim your free trial");
      expect(discarded).toContain("claim your free trial");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("cleans real Chinese CTA while preserving tutorial context", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-real-zh-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "tutorial.md");
      writeFileSync(
        sourcePath,
        [
          "# 小红书账号规则教程",
          "",
          "第一步：检查文案里是否出现“扫码加入社群”。如果是在讲平台规则或违规案例，这句话必须保留，因为它是判断标准，不是广告。",
          "",
          "第二步：把检测结果记录到字段 risk_label，并把参数 threshold 设置为 0.8，方便后续复盘误判原因。",
          "",
          "扫码入群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const runDir = envelope.data.run_dir;
      const cleaned = readFileSync(path.join(runDir, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(runDir, "discarded.md"), "utf8");
      const quality = JSON.parse(readFileSync(path.join(runDir, "quality_report.json"), "utf8"));

      expect(envelope.data.strict_errors).toEqual([]);
      expect(quality.strict_errors).toEqual([]);
      expect(cleaned).toContain("讲平台规则或违规案例");
      expect(cleaned).toContain("threshold 设置为 0.8");
      expect(cleaned).not.toContain("扫码入群领取体验卡");
      expect(discarded).toContain("扫码入群领取体验卡");
      expect(discarded).not.toContain("讲平台规则或违规案例");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("removes community marketing wrapper sections from knowledge-base output", () => {
    runPython(
      [
        "from pathlib import Path",
        "from tempfile import TemporaryDirectory",
        "import json, os",
        "from kbprep_worker.classify_blocks import classify_blocks",
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "from kbprep_worker.render_outputs import render",
        "from kbprep_worker.quality import run_quality_check",
        "with TemporaryDirectory() as tmp:",
        "    run_dir = Path(tmp)",
        "    private_root = run_dir / '.kbprep' / 'rules'",
        "    template_dir = private_root / 'templates'",
        "    template_dir.mkdir(parents=True)",
        "    (template_dir / 'self_media_course.json').write_text(json.dumps({",
        "        'schema': 'kbprep.cleaning_rules.v1',",
        "        'description': 'test private self-media cleanup template',",
        "        'rules': [],",
        "        'keyword_sets': {",
        "            'marketing_wrapper_passthrough_titles': ['ExampleCourse', '《ExampleCourse》'],",
        "            'marketing_wrapper_heading_terms': ['找项目', '版权声明', '致谢', 'ExampleProgram3'],",
        "            'marketing_wrapper_back_matter_terms': ['写在最后', '版权声明', '致谢'],",
        "            'marketing_wrapper_line_patterns': ['和\\\\s*\\\\d{4,}\\\\+\\\\s*实战派同行', '3\\\\s*天内无理由退款', '扫码体验.*ExampleProgram3'],",
        "            'cta_keywords': ['扫码体验'],",
        "        },",
        "    }, ensure_ascii=False), encoding='utf-8')",
        "    os.environ['KBPREP_USER_RULES_DIR'] = str(private_root)",
        "    load_cleaning_rules.cache_clear()",
        "    blocks = [",
        "        {'block_id': 'title', 'type': 'section_heading', 'status': 'unclassified', 'text': '# ExampleCourse', 'heading_path': ['ExampleCourse']},",
        "        {'block_id': 'promo_h1', 'type': 'section_heading', 'status': 'unclassified', 'text': '# \\u627e\\u9879\\u76ee\\uff0c\\u505a\\u526f\\u4e1a\\uff0c\\u5b66AI\\u6765ExampleCommunity', 'heading_path': ['\\u627e\\u9879\\u76ee\\uff0c\\u505a\\u526f\\u4e1a\\uff0c\\u5b66AI\\u6765ExampleCommunity']},",
        "        {'block_id': 'promo_p1', 'type': 'paragraph', 'status': 'unclassified', 'text': '\\u548c30000+ \\u5b9e\\u6218\\u6d3e\\u540c\\u884c\\u5728AI\\u65f6\\u4ee3\\u66f4\\u6709\\u9009\\u62e9\\u6743', 'heading_path': ['\\u627e\\u9879\\u76ee\\uff0c\\u505a\\u526f\\u4e1a\\uff0c\\u5b66AI\\u6765ExampleCommunity']},",
        "        {'block_id': 'refund', 'type': 'paragraph', 'status': 'unclassified', 'text': '3\\u5929\\u5185\\u65e0\\u7406\\u7531\\u9000\\u6b3e', 'heading_path': ['\\u627e\\u9879\\u76ee\\uff0c\\u505a\\u526f\\u4e1a\\uff0c\\u5b66AI\\u6765ExampleCommunity']},",
        "        {'block_id': 'assistant', 'type': 'paragraph', 'status': 'unclassified', 'text': 'ExampleCommunityExampleProgram3\\n\\u626b\\u7801\\u4f53\\u9a8cExampleCommunityExampleProgram3', 'heading_path': ['ExampleCommunityExampleProgram3']},",
        "        {'block_id': 'body_h1', 'type': 'section_heading', 'status': 'unclassified', 'text': '# ExampleCommunity\\u8981\\u5982\\u4f55\\u5e26\\u7740\\u5927\\u5bb6All in AI', 'heading_path': ['ExampleCommunity\\u8981\\u5982\\u4f55\\u5e26\\u7740\\u5927\\u5bb6All in AI']},",
        "        {'block_id': 'body_step', 'type': 'paragraph', 'status': 'unclassified', 'text': '\\u7b2c\\u4e00\\u6b65\\uff1a\\u6253\\u5f00 Example Agent\\uff0c\\u8bb0\\u5f55 threshold=0.8 \\u548c failure_reason\\uff0c\\u7136\\u540e\\u590d\\u76d8\\u6848\\u4f8b\\u65b9\\u6cd5\\u3002', 'heading_path': ['ExampleCommunity\\u8981\\u5982\\u4f55\\u5e26\\u7740\\u5927\\u5bb6All in AI']},",
        "        {'block_id': 'back_h1', 'type': 'section_heading', 'status': 'unclassified', 'text': '## \\u5199\\u5728\\u6700\\u540e\\u00b7\\u5173\\u4e8e《ExampleCourse》', 'heading_path': ['\\u5199\\u5728\\u6700\\u540e\\u00b7\\u5173\\u4e8e《ExampleCourse》']},",
        "        {'block_id': 'back_p1', 'type': 'paragraph', 'status': 'unclassified', 'text': '\\u672c\\u4e66\\u5185\\u5bb9\\u4ec5\\u4f9b\\u5b66\\u4e60\\u4e0e\\u53c2\\u8003\\u4e4b\\u7528\\uff0c\\u4e0d\\u6784\\u6210\\u4efb\\u4f55\\u5f62\\u5f0f\\u7684\\u6295\\u8d44\\u51b3\\u7b56\\u5efa\\u8bae\\u3002', 'heading_path': ['\\u5199\\u5728\\u6700\\u540e\\u00b7\\u5173\\u4e8e《ExampleCourse》']},",
        "        {'block_id': 'copyright', 'type': 'section_heading', 'status': 'unclassified', 'text': '## \\u7248\\u6743\\u58f0\\u660e', 'heading_path': ['\\u7248\\u6743\\u58f0\\u660e']},",
        "        {'block_id': 'thanks', 'type': 'section_heading', 'status': 'unclassified', 'text': '## \\u81f4\\u8c22\\u00b7\\u5171\\u521b\\u7684\\u529b\\u91cf', 'heading_path': ['\\u81f4\\u8c22\\u00b7\\u5171\\u521b\\u7684\\u529b\\u91cf']},",
        "    ]",
        "    blocks = classify_blocks(blocks, profile='curated_obsidian_kb', rule_templates=['self_media_course'])",
        "    blocks = apply_clean_rules(blocks, profile='curated_obsidian_kb', rule_templates=['self_media_course'])",
        "    render(blocks, str(run_dir), 'sha', 'run')",
        "    report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'marketing-wrapper-test'}, rule_templates=['self_media_course'])",
        "    cleaned = (run_dir / 'cleaned.md').read_text(encoding='utf-8')",
        "    discarded = (run_dir / 'discarded.md').read_text(encoding='utf-8')",
        "    assert 'ExampleCourse' in cleaned, cleaned",
        "    assert 'threshold=0.8' in cleaned, cleaned",
        "    assert '\\u627e\\u9879\\u76ee' not in cleaned, cleaned",
        "    assert '30000+' not in cleaned, cleaned",
        "    assert '3\\u5929\\u5185\\u65e0\\u7406\\u7531\\u9000\\u6b3e' not in cleaned, cleaned",
        "    assert 'ExampleProgram3' not in cleaned, cleaned",
        "    assert '\\u7248\\u6743\\u58f0\\u660e' not in cleaned, cleaned",
        "    assert '\\u81f4\\u8c22' not in cleaned, cleaned",
        "    assert '\\u627e\\u9879\\u76ee' in discarded, discarded",
        "    assert '3\\u5929\\u5185\\u65e0\\u7406\\u7531\\u9000\\u6b3e' in discarded, discarded",
        "    assert not report['strict_errors'], report",
      ].join("\n"),
      [],
    );
  });

  it("keeps marketing-domain methods while removing direct promotion", () => {
    runPython(
      [
        "from kbprep_worker.classify_blocks import classify_blocks",
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "blocks = [",
        "  {'block_id': 'account_matrix', 'type': 'paragraph', 'status': 'unclassified', 'text': '\\u50cf\\u89c6\\u9891\\u53f7\\u662f\\u7528\\u5fae\\u4fe1\\u6ce8\\u518c\\uff0c\\u4e00\\u4e2a\\u5fae\\u4fe1\\u7ed1\\u5b9a\\u4e00\\u4e2a\\u89c6\\u9891\\u53f7\\uff0c\\u4f46\\u662f\\u8981\\u5f00\\u901a\\u521b\\u4f5c\\u8005\\u5206\\u6210\\u5e76\\u7a33\\u5b9a\\u6536\\u76ca\\uff0c\\u662f\\u9700\\u8981\\u8fdb\\u884c\\u5b9e\\u540d\\u8ba4\\u8bc1\\u7684\\u30021\\u4e2a\\u8eab\\u4efd\\u8bc1\\u53ef\\u4ee5\\u8ba4\\u8bc15\\u4e2a\\u5fae\\u4fe1\\u53f7\\uff0c2\\u4e2a\\u89c6\\u9891\\u53f7\\u3002', 'heading_path': ['LC AIGCExampleFounder2\\uff1aAI\\u8d4b\\u80fd\\u89c6\\u9891\\u53f7\\u5982\\u4f55\\u901a\\u8fc7\\u8d26\\u53f7\\u77e9\\u9635\\u5b9e\\u73b0ExampleRevenue3']},",
        "  {'block_id': 'ending_lead', 'type': 'paragraph', 'status': 'unclassified', 'text': '1\\uff09\\u6587\\u672b\\u5f15\\u5bfc\\uff1a\\u5728\\u6587\\u7ae0\\u7ed3\\u5c3e\\u52a0\\u201c\\u798f\\u5229\\u201d\\uff0c\\u6bd4\\u5982\\u201c\\u6211\\u6574\\u7406\\u4e86\\u300a100\\u7bc7\\u8bfb\\u4e66\\u53f7\\u7206\\u6587\\u6807\\u9898\\u6a21\\u677f\\u300b\\uff0c\\u60f3\\u62ff\\u7684\\u670b\\u53cb\\u53ef\\u4ee5\\u52a0\\u6211\\u5fae\\u4fe1\\u3010XXX\\u3011\\uff0c\\u56de\\u590d\\u6807\\u9898\\u76f4\\u63a5\\u9886\\u201d\\uff0c\\u6ce8\\u610f\\u7528\\u6635\\u79f0+\\u5173\\u952e\\u8bcd\\u7684\\u5f62\\u5f0f\\uff0c\\u522b\\u76f4\\u63a5\\u53d1\\u5fae\\u4fe1\\u53f7\\uff0c\\u907f\\u514d\\u88ab\\u5e73\\u53f0\\u9650\\u6d41\\uff1b', 'heading_path': ['\\u5218\\u667a\\u884c\\uff1a\\u7528AI\\u8d4b\\u80fd\\u5782\\u76f4\\u5c0f\\u53f7\\u6253\\u9020\\u51fa20\\u4e2a\\u7206\\u6b3e\\u8d5b\\u9053\\u8d26\\u53f7', '2.\\u7528\\u6237\\u8fd0\\u8425']},",
        "  {'block_id': 'tool_lead', 'type': 'paragraph', 'status': 'unclassified', 'text': '\\u5148\\u5356\\u5bf9\\u6807\\u4ea7\\u54c1\\u9a8c\\u8bc1\\u9700\\u6c42\\uff0c\\u7528\\u81ea\\u5df1AI\\u5f00\\u53d1\\u7684\\u5de5\\u5177\\u53d1\\u7b14\\u8bb0\\u5f15\\u6d41\\uff1b\\u4f1a\\u5728\\u5de5\\u5177\\u4e2d\\u5d4c\\u5165\\u5fae\\u4fe1\\u53f7\\uff0c\\u81ea\\u52a8\\u5bfc\\u6d41\\u7cbe\\u51c6\\u5ba2\\u7fa4\\uff1b\\u627e\\u4eba\\u6301\\u7eed\\u4f18\\u5316\\uff0c20\\u591a\\u5929\\u8fed\\u4ee3\\u4e8610-20\\u8f6e\\u3002', 'heading_path': ['\\u661f\\u57ce\\uff1a\\u505a\\u51fa\\u6d77\\u4e1a\\u52a1\\u6211\\u65e5\\u5e38\\u662f\\u600e\\u4e48\\u7528AI\\u7684\\uff1f']},",
        "  {'block_id': 'pure_cta', 'type': 'paragraph', 'status': 'unclassified', 'text': '\\u626b\\u7801\\u52a0\\u5165\\u793e\\u7fa4\\u514d\\u8d39\\u9886\\u53d6\\u4f53\\u9a8c\\u5361\\u3002', 'heading_path': []},",
        "]",
        "cleaned = apply_clean_rules(classify_blocks(blocks))",
        "by_id = {b['block_id']: b for b in cleaned}",
        "assert by_id['account_matrix']['status'] == 'keep', by_id['account_matrix']",
        "assert by_id['ending_lead']['status'] == 'keep', by_id['ending_lead']",
        "assert by_id['tool_lead']['status'] == 'keep', by_id['tool_lead']",
        "assert by_id['pure_cta']['status'] == 'discard', by_id['pure_cta']",
      ].join("\n"),
      [],
    );
  });

  it("loads a generic Obsidian template by default and keeps course categories explicit", () => {
    runPython(
      [
        "from kbprep_worker.obsidian_template import load_obsidian_template",
        "generic = load_obsidian_template()",
        "course = load_obsidian_template('obsidian_course_kb')",
        "assert generic.source.replace('\\\\', '/').endswith('rules/templates/obsidian_generic.json'), generic",
        "assert course.source.replace('\\\\', '/').endswith('.kbprep/rules/templates/obsidian_course_kb.json'), course",
        "assert generic.categories != ('认知', '方法', '案例'), generic.categories",
        "assert course.categories == ('认知', '方法', '案例'), course.categories",
      ].join("\n"),
      [],
    );
  });

  it("prepares generic Obsidian outputs without course or self-media category folders", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-generic-obsidian-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      const sourcePath = path.join(inputDir, "industry-report.md");
      writeFileSync(
        sourcePath,
        [
          "# 2026 AI 行业趋势报告",
          "",
          "## 摘要",
          "",
          "本报告分析市场规模、同比增长、样本方法和主要风险。",
          "",
          "## 数据结论",
          "",
          "2026 年用户规模同比增长 20%，样本量 n=1200。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "obsidian_kb",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      expect(envelope.ok).toBe(true);
      const obsidianDir = path.join(outputRoot, "obsidian");
      expect(envelope.data.latest_outputs.final_artifact_type).toBe("obsidian_dir");
      expect(envelope.data.latest_outputs.obsidian_dir).toBe(obsidianDir);
      expect(existsSync(path.join(obsidianDir, "00-索引.md"))).toBe(true);
      expect(existsSync(path.join(obsidianDir, "Notes"))).toBe(true);
      expect(existsSync(path.join(obsidianDir, "认知"))).toBe(false);
      expect(existsSync(path.join(obsidianDir, "方法"))).toBe(false);
      expect(existsSync(path.join(obsidianDir, "案例"))).toBe(false);
      const index = readFileSync(path.join(obsidianDir, "00-索引.md"), "utf8");
      expect(index).toContain("kbprep_profile: obsidian_kb");
      expect(index).toContain("## Notes");
      expect(index).not.toContain("[[案例/");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
