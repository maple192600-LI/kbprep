import { copyFileSync, existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { repoRoot, runWorker } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - direct content conversion part 2", () => {
  it("treats English Step N tutorial lines as protected operation steps", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-english-steps-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "lesson.txt");
      writeFileSync(
        sourcePath,
        [
          "Step 1: open dashboard",
          "",
          "Set threshold=0.8 and record failure_reason=timeout.",
          "",
          "Step 2: export the result and keep retry_count=3 in the notes.",
        ].join("\n"),
        "utf8",
      );

      const diagnosis = runWorker("diagnose", {
        input_path: sourcePath,
        output_root: outputRoot,
        source_type: "auto",
      });
      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "en",
        force: true,
      });

      const blocks = readFileSync(path.join(outputRoot, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const quality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));
      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");

      expect(diagnosis.data.text_profile).toBe("tutorial");
      expect(envelope.data.strict_errors).toEqual([]);
      expect(blocks.filter((block) => block.type === "operation_step").length).toBeGreaterThanOrEqual(2);
      expect(quality.retention.operation_step_total).toBeGreaterThanOrEqual(2);
      expect(quality.detail_retention.operation_step.total_blocks).toBeGreaterThanOrEqual(2);
      expect(cleaned).toContain("Step 1: open dashboard");
      expect(cleaned).toContain("retry_count=3");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("preserves Obsidian markdown structure while removing standalone CTA pollution", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-obsidian-md-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "obsidian-note.md");
      writeFileSync(
        sourcePath,
        [
          "---",
          "tags: [kbprep, tutorial]",
          "aliases:",
          "  - 清洗插件测试",
          "---",
          "",
          "# Obsidian 清洗教程",
          "",
          "[[ExampleTool]] 和 [[MinerU]] 都要保留，因为它们是工具链细节。 #LLM-Wiki",
          "",
          "> [!warning] CTA 判断规则",
          "> 如果教程案例里出现“扫码入群”，不要按关键词删除；要记录 risk_label=possible_cta，并保留上下文。",
          "",
          "步骤1：打开插件输出目录，检查 cleaned.md、discarded.md、review_needed.md。",
          "",
          "扫码加入社群领取体验卡",
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

      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(outputRoot, "discarded.md"), "utf8");
      const quality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("tags: [kbprep, tutorial]");
      expect(cleaned).toContain("aliases:");
      expect(cleaned).toContain("[[ExampleTool]]");
      expect(cleaned).toContain("[[MinerU]]");
      expect(cleaned).toContain("#LLM-Wiki");
      expect(cleaned).toContain("> [!warning] CTA 判断规则");
      expect(cleaned).toContain("risk_label=possible_cta");
      expect(cleaned).toContain("步骤1：打开插件输出目录");
      expect(cleaned).not.toContain("扫码加入社群领取体验卡");
      expect(discarded).toContain("扫码加入社群领取体验卡");
      expect(quality.detail_retention.operation_step.total_blocks).toBeGreaterThanOrEqual(1);
      expect(quality.output_retention.cleaned_md.parameter.missing_count).toBe(0);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("converts a noisy HTML golden fixture while preserving method details", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-html-golden-"));
    try {
      const fixturePath = path.join(repoRoot, "src", "test", "fixtures", "html", "noisy-course-page.html");
      const sourcePath = path.join(root, "noisy-course-page.html");
      const expectedPath = path.join(repoRoot, "src", "test", "fixtures", "html", "noisy-course-page.expected-preserved.md");
      const outputRoot = path.join(root, "output");
      const expectedLines = readFileSync(expectedPath, "utf8").trim().split(/\r?\n/);
      copyFileSync(fixturePath, sourcePath);

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const conversionReport = JSON.parse(readFileSync(path.join(outputRoot, "conversion_report.json"), "utf8"));

      expect(envelope.data.strict_errors).toEqual([]);
      expect(conversionReport.route_decision.declared_capability_id).toBe("html_direct");
      expect(conversionReport.route_decision.declared_status).toBe("partial");
      for (const expectedLine of expectedLines) {
        expect(cleaned).toContain(expectedLine);
      }
      expect(cleaned).not.toContain("扫码加入社群领取体验卡");
      expect(cleaned).not.toContain("添加微信领取更多课程优惠");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 30_000);

  it("converts local HTML, JSON, and CSV sources into readable Markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-direct-formats-"));
    try {
      const inputDir = path.join(root, "input");
      mkdirSync(inputDir);
      const htmlAssetsDir = path.join(inputDir, "html-assets");
      mkdirSync(htmlAssetsDir);
      const png1x1 = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=", "base64");
      writeFileSync(path.join(htmlAssetsDir, "step.png"), png1x1);

      const htmlPath = path.join(inputDir, "saved-page.html");
      const htmlOut = path.join(root, "html-out");
      writeFileSync(
        htmlPath,
        [
          "<html><head><style>.ad{display:none}</style><script>alert('x')</script></head>",
          '<p>工具地址：<a href="https://example.com/tool?mode=kbprep">打开工具</a></p>',
          '<p><img src="html-assets/step.png" alt="后台截图"></p>',
          "<body><nav>扫码入群领取体验卡</nav><article>",
          "<h1>操作教程</h1><p>第一步：打开平台后台，设置 threshold=0.8。</p>",
          "<ul><li>保留工具名、参数和失败原因。</li></ul>",
          "</article></body></html>",
        ].join(""),
        "utf8",
      );

      const htmlDiagnosis = runWorker("diagnose", {
        input_path: htmlPath,
        output_root: htmlOut,
        source_type: "auto",
      });
      expect(htmlDiagnosis.data.detected_format).toBe("html");
      expect(htmlDiagnosis.data.recommended_pipeline).toBe("direct");
      expect(htmlDiagnosis.data.conversion_strategy).toBe("direct");
      expect(htmlDiagnosis.data.text_profile).toBe("tutorial");

      const htmlEnvelope = runWorker("prepare", {
        input_path: htmlPath,
        output_root: htmlOut,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      const htmlConverted = readFileSync(path.join(htmlEnvelope.data.run_dir, "converted.md"), "utf8");
      expect(htmlEnvelope.data.strict_errors).toEqual([]);
      expect(htmlConverted).toContain("# 操作教程");
      expect(htmlConverted).toContain("threshold=0.8");
      expect(htmlConverted).toContain("[打开工具](https://example.com/tool?mode=kbprep)");
      expect(htmlConverted).toContain("![后台截图](images/html-assets/step.png)");
      expect(htmlConverted).toContain("- 保留工具名、参数和失败原因。");
      expect(htmlConverted).not.toContain("<script>");
      expect(existsSync(path.join(htmlOut, "images", "html-assets", "step.png"))).toBe(true);
      expect(htmlConverted).not.toContain("扫码入群领取体验卡");

      const jsonPath = path.join(inputDir, "config.json");
      const jsonOut = path.join(root, "json-out");
      writeFileSync(jsonPath, JSON.stringify({ tool: "kbprep", threshold: 0.8, steps: ["detect", "clean"] }), "utf8");
      const jsonDiagnosis = runWorker("diagnose", {
        input_path: jsonPath,
        output_root: jsonOut,
        source_type: "auto",
      });
      expect(jsonDiagnosis.data.detected_format).toBe("json");
      expect(jsonDiagnosis.data.recommended_pipeline).toBe("direct");
      expect(jsonDiagnosis.data.conversion_strategy).toBe("direct");

      const jsonEnvelope = runWorker("prepare", {
        input_path: jsonPath,
        output_root: jsonOut,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      const jsonConverted = readFileSync(path.join(jsonEnvelope.data.run_dir, "converted.md"), "utf8");
      expect(jsonEnvelope.data.strict_errors).toEqual([]);
      expect(jsonConverted).toContain("```json");
      expect(jsonConverted).toContain('"threshold": 0.8');

      const csvPath = path.join(inputDir, "table.csv");
      const csvOut = path.join(root, "csv-out");
      writeFileSync(csvPath, "步骤,参数,说明\n第一步,threshold=0.8,保留失败原因\n", "utf8");
      const csvDiagnosis = runWorker("diagnose", {
        input_path: csvPath,
        output_root: csvOut,
        source_type: "auto",
      });
      expect(csvDiagnosis.data.detected_format).toBe("text");
      expect(csvDiagnosis.data.recommended_pipeline).toBe("direct");
      expect(csvDiagnosis.data.conversion_strategy).toBe("direct");

      const csvEnvelope = runWorker("prepare", {
        input_path: csvPath,
        output_root: csvOut,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      const csvConverted = readFileSync(path.join(csvEnvelope.data.run_dir, "converted.md"), "utf8");
      expect(csvEnvelope.data.strict_errors).toEqual([]);
      expect(csvConverted).toContain("| 步骤 | 参数 | 说明 |");
      expect(csvConverted).toContain("| 第一步 | threshold=0.8 | 保留失败原因 |");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 30_000);

  it("converts GitHub-style source and config files as fenced Markdown without summarizing code", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-code-source-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "workflow.py");
      writeFileSync(
        sourcePath,
        [
          "# GitHub example workflow",
          "CONFIG_URL = 'https://example.com/config'",
          "threshold = 0.82",
          "retry_count = 3",
          "",
          "def run_job(item):",
          "    if item.get('failed'):",
          "        failure_reason = 'timeout'",
          "        return {'status': 'review', 'failure_reason': failure_reason}",
          "    return {'status': 'keep'}",
        ].join("\n"),
        "utf8",
      );

      const diagnosis = runWorker("diagnose", {
        input_path: sourcePath,
        output_root: outputRoot,
        source_type: "auto",
      });
      expect(diagnosis.ok).toBe(true);
      expect(diagnosis.data.detected_format).toBe("code");
      expect(diagnosis.data.source_type).toBe("generic_block");
      expect(diagnosis.data.recommended_pipeline).toBe("direct");
      expect(diagnosis.data.conversion_strategy).toBe("direct_code");

      const prepared = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      expect(prepared.ok).toBe(true);

      const converted = readFileSync(path.join(outputRoot, "converted.md"), "utf8");
      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const quality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));
      const conversionReport = JSON.parse(readFileSync(path.join(outputRoot, "conversion_report.json"), "utf8"));

      expect(converted).toContain("```python");
      expect(converted).toContain("CONFIG_URL = 'https://example.com/config'");
      expect(converted).toContain("failure_reason = 'timeout'");
      expect(cleaned).toContain("retry_count = 3");
      expect(cleaned).toContain("return {'status': 'review'");
      expect(quality.strict_errors).toEqual([]);
      expect(quality.detail_retention.code.total_blocks).toBeGreaterThan(0);
      expect(quality.detail_retention.parameter.total_blocks).toBeGreaterThan(0);
      expect(quality.detail_retention.link.total_blocks).toBeGreaterThan(0);
      expect(conversionReport.converter).toBe("direct_code");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
