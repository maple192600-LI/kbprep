import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { maybeRunAiReview } from "./aiReview.js";
import { buildBackend, type AIReviewBackend } from "./adapters/ai_review/index.js";
import {
  buildReviewBatches,
  buildReviewPrompt,
  extractJsonPatch,
  formatRejectedPatchWarning,
  validateAiReviewPatch,
} from "./adapters/ai_review/review_pipeline.js";
import type { WorkerResult } from "./worker.js";

describe("agent-independent AI review protocol", () => {
  it("builds retry prompts and splits large review packs into bounded batches", () => {
    const retryPrompt = buildReviewPrompt("{\"blocks\":[]}", 2, 3, 2);
    expect(retryPrompt).toContain("batch 2/3");
    expect(retryPrompt).toContain("Previous response was invalid or unsafe");

    const blocks = Array.from({ length: 6 }, (_unused, index) => ({
      block_id: `b${index}`,
      status: "review",
      text: "x".repeat(20_000),
    }));
    const batches = buildReviewBatches(JSON.stringify({ schema: "kbprep.review_pack.v1", blocks }));

    expect(batches.length).toBeGreaterThan(1);
    expect(JSON.parse(batches[0]).batching.original_block_count).toBe(6);
    expect(buildReviewBatches(`[${"x".repeat(80_100)}`)).toEqual([]);
  });

  it("extracts and validates only guarded AI review patch operations", () => {
    const extracted = extractJsonPatch([
      { content: "not a patch" },
      { text: "```json\n[{\"op\":\"add\",\"path\":\"/blocks/b1/risk_tags\",\"value\":\"needs_review\"}]\n```" },
    ]);
    expect(extracted).toEqual([
      { op: "add", path: "/blocks/b1/risk_tags", value: "needs_review" },
    ]);

    const result = validateAiReviewPatch([
      { op: "add", path: "/blocks/b1/risk_tags", value: "needs_review" },
      { op: "replace", path: "/blocks/b1/status", value: "archive" },
      { op: "add", path: "/blocks/b1/reason", value: "bad add" },
      { op: "replace", path: "/blocks/b1/confidence", value: 2 },
      { op: "remove", path: "/blocks/b1/status", value: "review" },
      { op: "replace", path: "/runs/b1/status", value: "review" },
    ]);

    expect(result.valid).toHaveLength(1);
    expect(result.rejected).toEqual([
      "invalid status archive",
      "add is not supported for field reason",
      "confidence must be a number between 0 and 1",
      "unsupported op remove",
      "invalid path /runs/b1/status",
    ]);
    expect(formatRejectedPatchWarning(1, 2, 2, result.rejected)).toContain("2 more");
  });

  it("treats specific quality failure codes as reviewable like the legacy QA code", async () => {
    const initial: WorkerResult<Record<string, unknown>> = {
      ok: false,
      error: {
        code: "E_CTA_RESIDUE",
        message: "Quality gate failed",
        details: {
          legacy_code: "E_QA_FAILED",
          run_dir: "run-dir",
          outputs: {},
        },
      },
      warnings: [],
    };

    const reviewed = await maybeRunAiReview(
      initial,
      { mode: "ai_review", ai_review_backend: "external" },
      {},
      { api: { runtime: {} }, toolCallId: "test-review-specific-quality-code" },
      { pythonPath: "python", timeoutMs: 60_000, workerConfig: {} },
    );

    expect(reviewed.ok).toBe(false);
    expect(reviewed.warnings?.some((warning) => warning.includes("AI review unavailable or review_pack missing"))).toBe(true);
  });

  it("can call a configured standalone external review command", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ai-review-command-"));
    const commandPath = path.join(root, "reviewer.mjs");
    writeFileSync(commandPath, [
      "let input = '';",
      "process.stdin.on('data', chunk => input += chunk);",
      "process.stdin.on('end', () => {",
      "  const payload = JSON.parse(input);",
      "  process.stdout.write(JSON.stringify({",
      "    messages: [JSON.stringify([{ op: 'replace', path: '/blocks/b1/status', value: 'review' }])],",
      "    warning: 'W_EXTERNAL_COMMAND_USED:' + payload.sessionKey,",
      "  }));",
      "});",
    ].join("\n"), "utf8");
    const backend = buildBackend("external", {
      externalCommand: [process.execPath, commandPath].map((part) => JSON.stringify(part)).join(" "),
    });

    try {
      const reviewed = await backend?.review({
        sessionKey: "session-1",
        message: "Review this pack",
        systemPrompt: "system",
        timeoutMs: 5_000,
      });

      expect(reviewed?.warning).toContain("W_EXTERNAL_COMMAND_USED:session-1");
      expect(reviewed?.messages).toHaveLength(1);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("reports external review command invalid JSON instead of treating it as review output", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ai-review-invalid-json-"));
    const commandPath = path.join(root, "reviewer.mjs");
    writeFileSync(commandPath, "process.stdout.write('not json');", "utf8");
    const backend = buildBackend("external", {
      externalCommand: [process.execPath, commandPath].map((part) => JSON.stringify(part)).join(" "),
    });

    try {
      await expect(backend?.review({
        sessionKey: "invalid-json",
        message: "Review this pack",
        systemPrompt: "system",
        timeoutMs: 5_000,
      })).rejects.toThrow(/invalid JSON/);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("reports external review command nonzero exits with stderr tail", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ai-review-nonzero-"));
    const commandPath = path.join(root, "reviewer.mjs");
    writeFileSync(commandPath, [
      "process.stderr.write('line before failure\\n');",
      "process.exit(7);",
    ].join("\n"), "utf8");
    const backend = buildBackend("external", {
      externalCommand: [process.execPath, commandPath].map((part) => JSON.stringify(part)).join(" "),
    });

    try {
      await expect(backend?.review({
        sessionKey: "nonzero",
        message: "Review this pack",
        systemPrompt: "system",
        timeoutMs: 5_000,
      })).rejects.toThrow(/exited 7: line before failure/);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("reports external review command timeout with stderr evidence", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ai-review-timeout-"));
    const commandPath = path.join(root, "reviewer.mjs");
    writeFileSync(commandPath, [
      "process.stderr.write('before external timeout\\n');",
      "setInterval(() => {}, 1000);",
    ].join("\n"), "utf8");
    const backend = buildBackend("external", {
      externalCommand: [process.execPath, commandPath].map((part) => JSON.stringify(part)).join(" "),
    });

    try {
      await expect(backend?.review({
        sessionKey: "timeout",
        message: "Review this pack",
        systemPrompt: "system",
        timeoutMs: 100,
      })).rejects.toThrow(/timed out after 100ms.*before external timeout/s);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not pretend standalone mode has a built-in external AI backend", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ai-review-unavailable-"));
    try {
      const runDir = path.join(root, "runs", "run-ai-review");
      mkdirSync(runDir, { recursive: true });
      const reviewPackPath = path.join(runDir, "review_pack.json");
      writeFileSync(reviewPackPath, JSON.stringify({
        schema: "kbprep.review_pack.v1",
        blocks: [{ block_id: "b1", status: "review", text: "needs review" }],
      }), "utf8");

      const initial: WorkerResult<Record<string, unknown>> = {
        ok: true,
        data: {
          run_id: "run-ai-review",
          run_dir: runDir,
          outputs: { review_pack: reviewPackPath },
          latest_outputs: {},
        },
        warnings: [],
      };

      const reviewed = await maybeRunAiReview(
        initial,
        { mode: "ai_review", ai_review_backend: "external" },
        {},
        { api: { runtime: {} }, toolCallId: "test-review-unavailable" },
        { pythonPath: "python", timeoutMs: 60_000, workerConfig: {} },
      );

      expect(reviewed.ok).toBe(true);
      expect(reviewed.data?.ai_review).toBeUndefined();
      expect(reviewed.warnings?.some((warning) => warning.includes("not built into standalone KBPrep"))).toBe(true);
      expect(reviewed.warnings?.some((warning) => warning.includes("all AI review batches failed"))).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("uses an injected generic backend and filters malformed patch operations before applying review", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ai-review-"));
    try {
      const outputRoot = path.join(root, "output");
      const runDir = path.join(outputRoot, "runs", "run-ai-review");
      mkdirSync(runDir, { recursive: true });
      mkdirSync(path.join(runDir, "chunks"));

      const block = {
        block_id: "b_review",
        source_sha256: "ai-review-source",
        status: "keep",
        type: "paragraph",
        text: "Standalone wrapper line for review.",
        protected: false,
        risk_tags: [],
        confidence: 0.6,
      };
      writeFileSync(path.join(runDir, "blocks.jsonl"), `${JSON.stringify(block)}\n`, "utf8");
      writeFileSync(path.join(runDir, "diagnosis_report.json"), JSON.stringify({ diagnosis: { file_id: "ai-review-source" } }), "utf8");
      writeFileSync(path.join(runDir, "quality_report.json"), JSON.stringify({
        source_type: "generic_block",
        source_sha256: "ai-review-source",
        plugin_version: "0.5.1",
      }), "utf8");
      const reviewPackPath = path.join(runDir, "review_pack.json");
      writeFileSync(path.join(runDir, "run_metadata.json"), JSON.stringify({
        input_path: path.join(root, "missing-source.bin"),
      }), "utf8");
      writeFileSync(reviewPackPath, JSON.stringify({
        schema: "kbprep.review_pack.v1",
        blocks: [block],
      }), "utf8");

      const seenPrompts: string[] = [];
      const backend: AIReviewBackend = {
        async review(params) {
          seenPrompts.push(params.message);
          return {
            messages: [JSON.stringify([
              { op: "replace", path: "/blocks/b_review/text", value: "rewritten text is not allowed" },
              { op: "replace", path: "/blocks/b_review/status", value: "review" },
              { op: "replace", path: "/blocks/b_review/reason", value: "external reviewer marked this for human review" },
            ])],
            warning: "W_TEST_BACKEND_USED",
          };
        },
      };

      const initial: WorkerResult<Record<string, unknown>> = {
        ok: true,
        data: {
          run_id: "run-ai-review",
          run_dir: runDir,
          outputs: { review_pack: reviewPackPath },
          latest_outputs: {},
        },
        warnings: [],
      };

      const reviewed = await maybeRunAiReview(
        initial,
        { mode: "ai_review", ai_review_backend: "external" },
        {},
        {
          api: { runtime: { aiReviewBackend: backend } },
          toolCallId: "test-review",
        },
        {
          pythonPath: "python",
          timeoutMs: 60_000,
          workerConfig: {},
        },
      );

      expect(reviewed.ok).toBe(true);
      expect(seenPrompts[0]).toContain("Allowed patch paths");
      expect(reviewed.warnings).toContain("W_TEST_BACKEND_USED");
      expect(reviewed.warnings?.some((warning) => warning.includes("field text is not allowed"))).toBe(true);
      expect(reviewed.data?.ai_review).toMatchObject({
        applied: 2,
        rejected: 0,
        patch_ops: 2,
      });

      const updatedBlocks = readFileSync(path.join(runDir, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      expect(updatedBlocks[0].text).toBe(block.text);
      expect(updatedBlocks[0].status).toBe("review");
      expect(updatedBlocks[0].reason).toBe("external reviewer marked this for human review");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
