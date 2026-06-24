import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runWorker } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - direct content conversion part 1", () => {
  it("keeps short unnumbered case details that mention CTA phrases", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-case-cta-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      const sourcePath = path.join(inputDir, "case.md");
      writeFileSync(
        sourcePath,
        [
          "# 小红书账号违规案例拆解",
          "",
          "案例：这个账号在主页写“扫码加入社群领取体验卡”，被平台判定为引流违规；处理方式是删除主页广告语，并记录 risk_label=引流违规。",
          "",
          "判断标准：如果这句话出现在案例复盘里，要保留完整上下文、处理动作和字段值，不能只因为出现扫码、社群、体验卡就删除。",
          "",
          "扫码加入社群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        source_type: "auto",
      });

      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(outputRoot, "discarded.md"), "utf8");
      const blocks = readFileSync(path.join(outputRoot, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const caseBlock = blocks.find((block) => block.text.includes("risk_label=引流违规"));

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("主页写“扫码加入社群领取体验卡”");
      expect(cleaned).toContain("risk_label=引流违规");
      expect(discarded).toContain("扫码加入社群领取体验卡。");
      expect(discarded).not.toContain("risk_label=引流违规");
      expect(caseBlock.status).toBe("keep");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("keeps platform and conversion terms when they are report body, not CTA", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "report.md");
      writeFileSync(
        sourcePath,
        [
          "# AI 美妆社媒营销新赛道",
          "",
          "微信小程序可承接肤质诊断和会员复购提醒。",
          "",
          "转化层面：通过诊断结果直接关联产品组合推荐，实现“诊-购”一体化。",
          "",
          "引流层面：与平台合作，打造 AR 试妆滤镜，降低尝新门槛。",
          "",
          "喜欢在抖音/小红书玩“AI换脸试妆挑战”等互动玩法。",
          "",
          "扫码加入AI创业营社群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

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
      const reviewNeeded = readFileSync(path.join(runDir, "review_needed.md"), "utf8");
      const discarded = readFileSync(path.join(runDir, "discarded.md"), "utf8");

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("微信小程序可承接肤质诊断");
      expect(cleaned).toContain("转化层面：通过诊断结果");
      expect(cleaned).toContain("引流层面：与平台合作");
      expect(cleaned).toContain("抖音/小红书");
      expect(reviewNeeded).not.toContain("微信小程序可承接肤质诊断");
      expect(reviewNeeded).not.toContain("转化层面：通过诊断结果");
      expect(discarded).toContain("扫码加入AI创业营社群领取体验卡");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("writes detected document type into quality reports and loads document-type dictionaries", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-doc-type-report-"));
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
        profile: "standard",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      expect(envelope.ok).toBe(true);
      const quality = JSON.parse(readFileSync(path.join(envelope.data.run_dir, "quality_report.json"), "utf8"));
      expect(quality.document_type).toBe("report");
      expect(quality.document_type_detection.confidence).toBeGreaterThan(0);
      expect(quality.document_type_detection.reasons.length).toBeGreaterThan(0);
      const ruleSources = quality.cleaning_rule_sources.map((source: string) => source.replaceAll("\\", "/"));
      expect(ruleSources).toContain("rules/document_types/report.json");
      expect(ruleSources).not.toContain("rules/templates/self_media_course.json");

      const metadata = JSON.parse(readFileSync(path.join(envelope.data.run_dir, "run_metadata.json"), "utf8"));
      expect(metadata.document_type).toBe("report");
      expect(metadata.document_type_detection.document_type).toBe("report");
      expect(metadata.document_type_detection.reasons.length).toBeGreaterThan(0);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("normalizes local subtitle files into readable transcript markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "lesson.srt");
      writeFileSync(
        sourcePath,
        [
          "1",
          "00:00:01,000 --> 00:00:04,000",
          "第一步：打开后台，把参数 threshold 设置为 0.8。",
          "",
          "2",
          "00:00:05,000 --> 00:00:08,000",
          "第二步：记录失败原因，不要把细节总结掉。",
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

      const converted = readFileSync(path.join(envelope.data.run_dir, "converted.md"), "utf8");
      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");

      expect(envelope.data.strict_errors).toEqual([]);
      expect(converted).toContain("# Transcript");
      expect(converted).not.toContain("-->");
      expect(converted).not.toContain("00:00:01,000");
      expect(cleaned).toContain("threshold 设置为 0.8");
      expect(cleaned).toContain("不要把细节总结掉");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("removes pure transcript filler while keeping steps and experience details", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-transcript-filler-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "talk.srt");
      writeFileSync(
        sourcePath,
        [
          "1",
          "00:00:01,000 --> 00:00:02,000",
          "大家好",
          "",
          "2",
          "00:00:03,000 --> 00:00:07,000",
          "第一步：打开后台，把 threshold 设置为 0.8，并记录失败原因。",
          "",
          "3",
          "00:00:08,000 --> 00:00:12,000",
          "我踩过一个坑：不要把平台规则里的扫码案例直接删掉。",
          "",
          "4",
          "00:00:13,000 --> 00:00:15,000",
          "记得点赞关注",
          "",
          "5",
          "00:00:16,000 --> 00:00:17,000",
          "下期见",
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

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("threshold 设置为 0.8");
      expect(cleaned).toContain("我踩过一个坑");
      expect(cleaned).not.toContain("大家好");
      expect(cleaned).not.toContain("点赞关注");
      expect(cleaned).not.toContain("下期见");
      expect(discarded).toContain("大家好");
      expect(discarded).toContain("点赞关注");
      expect(discarded).toContain("下期见");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("removes English transcript filler while keeping tutorial details", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-english-transcript-filler-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "lesson.srt");
      writeFileSync(
        sourcePath,
        [
          "1",
          "00:00:01,000 --> 00:00:02,000",
          "Hey guys",
          "",
          "2",
          "00:00:03,000 --> 00:00:06,000",
          "Step 1: open the dashboard and set threshold=0.8.",
          "",
          "3",
          "00:00:07,000 --> 00:00:11,000",
          "My failure lesson: keep failure_reason=timeout and retry_count=3 for review.",
          "",
          "4",
          "00:00:12,000 --> 00:00:14,000",
          "Don't forget to like and subscribe",
          "",
          "5",
          "00:00:15,000 --> 00:00:16,000",
          "Thanks for watching",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "en",
        force: true,
      });

      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(outputRoot, "discarded.md"), "utf8");
      const quality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("Step 1: open the dashboard");
      expect(cleaned).toContain("threshold=0.8");
      expect(cleaned).toContain("failure_reason=timeout");
      expect(cleaned).toContain("retry_count=3");
      expect(cleaned).not.toContain("Hey guys");
      expect(cleaned).not.toContain("like and subscribe");
      expect(cleaned).not.toContain("Thanks for watching");
      expect(discarded).toContain("Hey guys");
      expect(discarded).toContain("like and subscribe");
      expect(discarded).toContain("Thanks for watching");
      expect(quality.detail_retention.operation_step.total_blocks).toBeGreaterThanOrEqual(1);
      expect(quality.output_retention.cleaned_md.parameter.missing_count).toBe(0);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
