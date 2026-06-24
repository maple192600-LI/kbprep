import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runPython, runWorker } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - output guards part 2", () => {
  it("rejects AI review patches that rewrite text, drop protected blocks, or use invalid metadata", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "review-safety.md");
      writeFileSync(
        sourcePath,
        [
          "# Review Safety",
          "",
          "第一步：保留 REVIEW_STEP_MARKER，把参数 threshold 设置为 0.8，并记录失败原因。",
          "",
          "扫码加入社群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

      const prepared = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_plus_review_pack",
        language: "zh",
        force: true,
      });

      const initialQuality = JSON.parse(readFileSync(path.join(prepared.data.run_dir, "quality_report.json"), "utf8"));
      expect(initialQuality.quality_loop.current_iteration).toBe(1);
      expect(initialQuality.quality_loop.max_iterations).toBeGreaterThanOrEqual(1);

      const blocks = readFileSync(path.join(prepared.data.run_dir, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const stepBlock = blocks.find((block) => block.type === "operation_step");
      const ctaBlock = blocks.find((block) => block.type === "marketing_cta");
      expect(stepBlock).toBeDefined();
      expect(ctaBlock).toBeDefined();

      const patched = runWorker("apply_review", {
        run_dir: prepared.data.run_dir,
        patch_json: [
          { op: "replace", path: `/blocks/${stepBlock.block_id}/text`, value: "总结成一句话" },
          { op: "replace", path: `/blocks/${stepBlock.block_id}/status`, value: "discard" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/status`, value: "gone" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/status/extra`, value: "evidence" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/risk_tags`, value: "not-array" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/confidence`, value: "high" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/status`, value: "review" },
          { op: "replace", path: `/blocks/${ctaBlock.block_id}/reason`, value: "needs human review" },
        ],
      });

      const cleaned = readFileSync(path.join(prepared.data.run_dir, "cleaned.md"), "utf8");
      const reviewNeeded = readFileSync(path.join(prepared.data.run_dir, "review_needed.md"), "utf8");
      const topLevelReviewNeeded = readFileSync(path.join(outputRoot, "review_needed.md"), "utf8");
      const latest = JSON.parse(readFileSync(path.join(outputRoot, "latest.json"), "utf8"));
      const updatedQuality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));
      const updatedBlocks = readFileSync(path.join(prepared.data.run_dir, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const updatedStep = updatedBlocks.find((block) => block.block_id === stepBlock.block_id);
      const updatedCta = updatedBlocks.find((block) => block.block_id === ctaBlock.block_id);

      expect(patched.data.applied).toBe(2);
      expect(patched.data.rejected).toBe(6);
      expect(patched.data.published).toBe(true);
      expect(updatedStep.text).toContain("REVIEW_STEP_MARKER");
      expect(updatedStep.status).toBe("keep");
      expect(updatedCta.status).toBe("review");
      expect(Array.isArray(updatedCta.risk_tags)).toBe(true);
      expect(typeof updatedCta.confidence).toBe("number");
      expect(cleaned).toContain("REVIEW_STEP_MARKER");
      expect(topLevelReviewNeeded).toContain("needs human review");
      expect(latest.review_applied_at).toBeTypeOf("number");
      expect(updatedQuality.runtime_cache_key).toBeTypeOf("string");
      expect(updatedQuality.runtime.python_executable).toContain("python");
      expect(updatedQuality.plugin_version).toBe(JSON.parse(readFileSync("package.json", "utf8")).version);
      expect(updatedQuality.review_applied_at).toBeTypeOf("number");
      expect(updatedQuality.quality_loop.current_iteration).toBe(2);
      expect(updatedQuality.quality_loop.previous_iteration).toBe(1);
      expect(updatedQuality.quality_loop.max_iterations).toBe(initialQuality.quality_loop.max_iterations);
      const qualityGates = Object.fromEntries(updatedQuality.quality_gates.map((gate: { name: string }) => [gate.name, gate]));
      expect(qualityGates.review_safety.checked).toBe(true);
      expect(qualityGates.review_safety.status).toBe("pass");
      expect(reviewNeeded).toContain("扫码加入社群领取体验卡");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects review patches that discard unprotected detail-bearing paragraphs", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-review-detail-"));
    try {
      runPython(
        [
          "import json, sys",
          "from pathlib import Path",
          "from kbprep_worker.apply_patch import run",
          "run_dir = Path(sys.argv[1])",
          "run_dir.mkdir(parents=True, exist_ok=True)",
          "(run_dir / 'chunks').mkdir()",
          "(run_dir / 'diagnosis_report.json').write_text(json.dumps({'diagnosis': {'file_id': 'review-detail'}}), encoding='utf-8')",
          "(run_dir / 'quality_report.json').write_text(json.dumps({'source_type': 'markdown_note', 'source_sha256': 'review-detail', 'plugin_version': '0.4.1'}), encoding='utf-8')",
          "blocks = [",
          "  {'block_id': 'detail1', 'source_sha256': 'review-detail', 'status': 'keep', 'type': 'paragraph', 'text': '失败经验：连续 3 次失败时，记录 failure_reason 并人工复查。', 'protected': False, 'risk_tags': [], 'confidence': 0.7},",
          "  {'block_id': 'cta1', 'source_sha256': 'review-detail', 'status': 'discard', 'type': 'marketing_cta', 'text': '扫码入群领取体验卡', 'protected': False, 'risk_tags': [], 'confidence': 0.95},",
          "]",
          "(run_dir / 'blocks.jsonl').write_text('\\n'.join(json.dumps(b, ensure_ascii=False) for b in blocks) + '\\n', encoding='utf-8')",
          "run({'run_dir': str(run_dir), 'patch_json': [",
          "  {'op': 'replace', 'path': '/blocks/detail1/status', 'value': 'discard'},",
          "  {'op': 'replace', 'path': '/blocks/cta1/status', 'value': 'review'},",
          "]})",
        ].join("\n"),
        [root],
      );

      const blocks = readFileSync(path.join(root, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const detailBlock = blocks.find((block) => block.block_id === "detail1");
      const ctaBlock = blocks.find((block) => block.block_id === "cta1");
      const quality = JSON.parse(readFileSync(path.join(root, "quality_report.json"), "utf8"));

      expect(detailBlock.status).toBe("keep");
      expect(ctaBlock.status).toBe("review");
      expect(quality.detail_retention.discarded_detail_block_ids).toEqual([]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("fails invalid PPTX inputs before publishing cleaned outputs", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "broken.pptx");
      writeFileSync(sourcePath, "this is not a valid office zip container", "utf8");

      const envelope = runWorker(
        "prepare",
        {
          input_path: sourcePath,
          output_root: outputRoot,
          profile: "tutorial",
          mode: "rules_only",
          language: "zh",
          force: true,
        },
        1,
      );

      const originalsDir = path.join(outputRoot, "original");
      const originalBackups = existsSync(originalsDir) ? readdirSync(originalsDir).filter((name) => name.endsWith(".pptx")) : [];

      expect(envelope.ok).toBe(false);
      expect(envelope.error.code).toBe("E_CONVERT_INPUT_INVALID");
      expect(envelope.error.message).toContain("not a valid Office ZIP container");
      expect(envelope.error.details.run_dir).toContain("runs");
      expect(envelope.error.details.original_file).toContain(".pptx");
      expect(existsSync(envelope.error.details.error_report)).toBe(true);
      const errorReport = JSON.parse(readFileSync(envelope.error.details.error_report, "utf8"));
      expect(errorReport.code).toBe("E_CONVERT_INPUT_INVALID");
      expect(errorReport.original_file).toContain(".pptx");
      expect(errorReport.runtime.python_executable).toContain("python");
      expect(originalBackups.length).toBe(1);
      expect(existsSync(path.join(outputRoot, "cleaned.md"))).toBe(false);
      expect(existsSync(path.join(outputRoot, "latest.json"))).toBe(false);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("fails audio/video conversion clearly when local ASR cannot process the file", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "lesson.mp4");
      writeFileSync(sourcePath, "not a real video", "utf8");

      const envelope = runWorker(
        "prepare",
        {
          input_path: sourcePath,
          output_root: outputRoot,
          profile: "tutorial",
          mode: "rules_only",
          language: "zh",
          force: true,
        },
        1,
      );

      expect(envelope.ok).toBe(false);
      expect(["E_ENV_MISSING", "E_CONVERT_FAILED"]).toContain(envelope.error.code);
      expect(envelope.error.details.external_conversion.route_decision.external_route).toBe("media_to_transcript");
      expect(envelope.error.details.external_conversion.failure_reason).toBeDefined();
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
