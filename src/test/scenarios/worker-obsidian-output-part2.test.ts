import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  runWorker,
} from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - output lifecycle part 2", () => {
  it("finalizes a successful run by deleting intermediate artifacts and keeping only source-side deliverables", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-finalize-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "guide.txt");
      writeFileSync(sourcePath, ["# Guide", "", "Step 1: keep FINALIZE_MARKER and set threshold=0.8."].join("\n"), "utf8");

      const prepared = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      const finalPath = path.join(inputDir, "guide.md");
      expect(existsSync(finalPath)).toBe(true);
      expect(existsSync(path.join(outputRoot, "runs"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "converted.md"))).toBe(true);

      const cleanup = runWorker("cleanup", {
        output_root: outputRoot,
        action: "finalize",
      });

      expect(cleanup.ok).toBe(true);
      expect(existsSync(sourcePath)).toBe(true);
      expect(readFileSync(finalPath, "utf8")).toContain("FINALIZE_MARKER");
      expect(existsSync(path.join(outputRoot, "runs"))).toBe(false);
      expect(existsSync(path.join(outputRoot, "original"))).toBe(false);
      expect(existsSync(path.join(outputRoot, "converted.md"))).toBe(false);
      expect(existsSync(path.join(outputRoot, "cleaned.md"))).toBe(false);
      expect(existsSync(path.join(outputRoot, "discarded.md"))).toBe(false);
      expect(existsSync(path.join(outputRoot, "quality_report.json"))).toBe(false);
      const manifest = JSON.parse(readFileSync(path.join(outputRoot, "kbprep_manifest.json"), "utf8"));
      expect(manifest.status).toBe("finalized");
      expect(manifest.final_artifact_type).toBe("markdown");
      expect(manifest.final_md).toBe(finalPath);
      expect(manifest.source_path).toBe(sourcePath);
      expect(cleanup.data.deleted.length).toBeGreaterThan(0);
      expect(prepared.data.latest_outputs.final_md).toBe(finalPath);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("finalizes explicit curated Obsidian runs without deleting the Obsidian deliverable", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-curated-finalize-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "curated.md");
      writeFileSync(
        sourcePath,
        [
          "# AI 方法案例",
          "",
          "第一步：保留 CURATED_FINALIZE_MARKER，并记录参数 threshold=0.8。",
          "",
          "第二步：把流程拆成输入、判断、输出三个可验证节点。",
        ].join("\n"),
        "utf8",
      );

      const prepared = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "curated_obsidian_kb",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      const obsidianDir = prepared.data.latest_outputs.obsidian_dir;
      const obsidianIndex = prepared.data.latest_outputs.obsidian_index;
      const obsidianComplete = prepared.data.latest_outputs.obsidian_complete;
      expect(prepared.data.latest_outputs.final_md).toBe(null);
      expect(prepared.data.latest_outputs.final_artifact_type).toBe("obsidian_dir");
      expect(existsSync(obsidianIndex)).toBe(true);
      expect(obsidianComplete).toBe(path.join(obsidianDir, "curated.md"));
      expect(existsSync(obsidianComplete)).toBe(true);
      expect(existsSync(path.join(outputRoot, "runs"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "quality_report.json"))).toBe(true);

      const cleanup = runWorker("cleanup", {
        output_root: outputRoot,
        action: "finalize",
      });

      expect(cleanup.ok).toBe(true);
      expect(existsSync(sourcePath)).toBe(true);
      expect(existsSync(obsidianDir)).toBe(true);
      expect(readFileSync(obsidianIndex, "utf8")).toContain("[[curated|完整正文]]");
      expect(readFileSync(obsidianComplete, "utf8")).toContain("CURATED_FINALIZE_MARKER");
      expect(existsSync(path.join(outputRoot, "runs"))).toBe(false);
      expect(existsSync(path.join(outputRoot, "converted.md"))).toBe(false);
      expect(existsSync(path.join(outputRoot, "quality_report.json"))).toBe(false);
      const manifest = JSON.parse(readFileSync(path.join(outputRoot, "kbprep_manifest.json"), "utf8"));
      expect(manifest.final_artifact_type).toBe("obsidian_dir");
      expect(manifest.obsidian_dir).toBe(obsidianDir);
      expect(manifest.obsidian_index).toBe(obsidianIndex);
      expect(manifest.obsidian_complete).toBe(obsidianComplete);
      expect(cleanup.data.final_artifact_type).toBe("obsidian_dir");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("refuses finalize when review-needed content exists unless the user confirms cleanup", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-finalize-review-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "guide.txt");
      writeFileSync(sourcePath, ["# Guide", "", "Step 1: keep REVIEW_GUARD_MARKER."].join("\n"), "utf8");

      runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      writeFileSync(path.join(outputRoot, "review_needed.md"), "needs a human look", "utf8");

      const blocked = runWorker("cleanup", {
        output_root: outputRoot,
        action: "finalize",
      }, 1);

      expect(blocked.ok).toBe(false);
      expect(blocked.error.code).toBe("KBPREP_REVIEW_NEEDED");
      expect(existsSync(path.join(outputRoot, "runs"))).toBe(true);

      const confirmed = runWorker("cleanup", {
        output_root: outputRoot,
        action: "finalize",
        confirm_review_needed: true,
      });

      expect(confirmed.ok).toBe(true);
      expect(existsSync(path.join(outputRoot, "runs"))).toBe(false);
      expect(existsSync(path.join(inputDir, "guide.md"))).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("refuses curated finalize when review-needed content exists unless the user confirms cleanup", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-curated-finalize-review-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "curated-review.md");
      writeFileSync(
        sourcePath,
        ["# Curated Review", "", "第一步：保留 CURATED_REVIEW_GUARD_MARKER，并设置 threshold=0.8。"].join("\n"),
        "utf8",
      );

      const prepared = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "curated_obsidian_kb",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      writeFileSync(path.join(outputRoot, "review_needed.md"), "needs curated human review", "utf8");

      const blocked = runWorker("cleanup", {
        output_root: outputRoot,
        action: "finalize",
      }, 1);

      expect(blocked.ok).toBe(false);
      expect(blocked.error.code).toBe("KBPREP_REVIEW_NEEDED");
      expect(existsSync(path.join(outputRoot, "runs"))).toBe(true);
      expect(existsSync(prepared.data.latest_outputs.obsidian_index)).toBe(true);

      const confirmed = runWorker("cleanup", {
        output_root: outputRoot,
        action: "finalize",
        confirm_review_needed: true,
      });

      expect(confirmed.ok).toBe(true);
      expect(existsSync(path.join(outputRoot, "runs"))).toBe(false);
      expect(existsSync(prepared.data.latest_outputs.obsidian_index)).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("keeps cleanup-analysis paragraphs that mention QR or CTA pollution", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-cleanup-analysis-"));
    try {
      const inputPath = path.join(root, "analysis.md");
      const outputRoot = path.join(root, "out");
      writeFileSync(
        inputPath,
        [
          "# 清洗复盘",
          "",
          "当前清洗版的问题之一，是图片几乎没有进入清洗范围，所以营销图和二维码图仍然可能留在 `cleaned.md`。这句话是正文分析，不能当广告删除。",
          "",
          "扫码加入社群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: inputPath,
        output_root: outputRoot,
        profile: "standard",
        mode: "rules_only",
        force: true,
        language: "zh",
        source_type: "auto",
        splitter: "auto",
      });

      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(outputRoot, "discarded.md"), "utf8");

      expect(envelope.data.strict_errors).toEqual([]);
      expect(cleaned).toContain("二维码图仍然可能留在 `cleaned.md`");
      expect(discarded).toContain("扫码加入社群领取体验卡");
      expect(discarded).not.toContain("二维码图仍然可能留在 `cleaned.md`");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 15_000);

});
