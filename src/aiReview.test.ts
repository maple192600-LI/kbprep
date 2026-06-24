import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
    const retryPrompt = buildReviewPrompt('{"blocks":[]}', 2, 3, 2);
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

  it("summarizes review pack policy context in the prompt", () => {
    const prompt = buildReviewPrompt(
      JSON.stringify({
        schema: "kbprep.review_pack.v1",
        policy_context: {
          document_type: "course",
          profile: "curated_obsidian_kb",
          relevant_terms: ["步骤", "案例"],
          protected_patterns: [{ label: "prompt", pattern: "^Prompt" }],
          rule_sources: ["rules/base/obvious_noise.json"],
        },
        blocks: [],
      }),
    );

    expect(prompt).toContain("Policy context");
    expect(prompt).toContain("document_type: course");
    expect(prompt).toContain("profile: curated_obsidian_kb");
    expect(prompt).toContain("relevant terms: 步骤, 案例");
    expect(prompt).toContain("protected patterns: prompt");
  });

  it("extracts and validates only guarded AI review patch operations", () => {
    const extracted = extractJsonPatch([
      { content: "not a patch" },
      { text: '```json\n[{"op":"add","path":"/blocks/b1/risk_tags","value":"needs_review"}]\n```' },
    ]);
    expect(extracted).toEqual([{ op: "add", path: "/blocks/b1/risk_tags", value: "needs_review" }]);

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
    writeFileSync(
      commandPath,
      [
        "let input = '';",
        "process.stdin.on('data', chunk => input += chunk);",
        "process.stdin.on('end', () => {",
        "  const payload = JSON.parse(input);",
        "  process.stdout.write(JSON.stringify({",
        "    messages: [JSON.stringify([{ op: 'replace', path: '/blocks/b1/status', value: 'review' }])],",
        "    warning: 'W_EXTERNAL_COMMAND_USED:' + payload.sessionKey,",
        "  }));",
        "});",
      ].join("\n"),
      "utf8",
    );
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
      await expect(
        backend?.review({
          sessionKey: "invalid-json",
          message: "Review this pack",
          systemPrompt: "system",
          timeoutMs: 5_000,
        }),
      ).rejects.toThrow(/invalid JSON/);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("reports external review command nonzero exits with stderr tail", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ai-review-nonzero-"));
    const commandPath = path.join(root, "reviewer.mjs");
    writeFileSync(commandPath, ["process.stderr.write('line before failure\\n');", "process.exit(7);"].join("\n"), "utf8");
    const backend = buildBackend("external", {
      externalCommand: [process.execPath, commandPath].map((part) => JSON.stringify(part)).join(" "),
    });

    try {
      await expect(
        backend?.review({
          sessionKey: "nonzero",
          message: "Review this pack",
          systemPrompt: "system",
          timeoutMs: 5_000,
        }),
      ).rejects.toThrow(/exited 7: line before failure/);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("reports external review command timeout with stderr evidence", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ai-review-timeout-"));
    const commandPath = path.join(root, "reviewer.mjs");
    writeFileSync(commandPath, ["process.stderr.write('before external timeout\\n');", "setInterval(() => {}, 1000);"].join("\n"), "utf8");
    const backend = buildBackend("external", {
      externalCommand: [process.execPath, commandPath].map((part) => JSON.stringify(part)).join(" "),
    });

    try {
      await expect(
        backend?.review({
          sessionKey: "timeout",
          message: "Review this pack",
          systemPrompt: "system",
          timeoutMs: 100,
        }),
      ).rejects.toThrow(/timed out after 100ms.*before external timeout/s);
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
      writeFileSync(
        reviewPackPath,
        JSON.stringify({
          schema: "kbprep.review_pack.v1",
          blocks: [{ block_id: "b1", status: "review", text: "needs review" }],
        }),
        "utf8",
      );

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

  it("does not apply or publish review when the AI returns an empty patch", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ai-review-empty-patch-"));
    try {
      const outputRoot = path.join(root, "output");
      const runDir = path.join(outputRoot, "runs", "run-ai-review-empty");
      mkdirSync(runDir, { recursive: true });
      mkdirSync(path.join(runDir, "chunks"));

      const block = {
        block_id: "b_review",
        source_sha256: "ai-review-source",
        status: "keep",
        type: "paragraph",
        text: "No change is needed.",
        protected: false,
        risk_tags: [],
        confidence: 0.9,
      };
      const blocksPath = path.join(runDir, "blocks.jsonl");
      writeFileSync(blocksPath, `${JSON.stringify(block)}\n`, "utf8");
      writeFileSync(path.join(runDir, "diagnosis_report.json"), JSON.stringify({ diagnosis: { file_id: "ai-review-source" } }), "utf8");
      writeFileSync(
        path.join(runDir, "quality_report.json"),
        JSON.stringify({
          source_type: "generic_block",
          source_sha256: "ai-review-source",
          plugin_version: "0.5.1",
        }),
        "utf8",
      );
      const reviewPackPath = path.join(runDir, "review_pack.json");
      writeFileSync(
        reviewPackPath,
        JSON.stringify({
          schema: "kbprep.review_pack.v1",
          blocks: [block],
        }),
        "utf8",
      );

      const seenPrompts: string[] = [];
      const backend: AIReviewBackend = {
        async review(params) {
          seenPrompts.push(params.message);
          return {
            messages: [JSON.stringify([])],
            warning: "W_TEST_BACKEND_USED",
          };
        },
      };

      const initial: WorkerResult<Record<string, unknown>> = {
        ok: true,
        data: {
          run_id: "run-ai-review-empty",
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
          toolCallId: "test-review-empty",
        },
        {
          pythonPath: "python",
          timeoutMs: 60_000,
          workerConfig: {},
        },
      );

      expect(reviewed.ok).toBe(true);
      expect(seenPrompts).toHaveLength(1);
      expect(reviewed.data?.ai_review).toBeUndefined();
      expect(reviewed.warnings).toContain("W_TEST_BACKEND_USED");
      expect(
        reviewed.warnings?.some((warning) => warning.includes("W_LLM_REVIEW_SKIPPED") && warning.includes("no patch operations")),
      ).toBe(true);
      expect(existsSync(path.join(outputRoot, "latest.json"))).toBe(false);
      expect(readFileSync(blocksPath, "utf8")).toBe(`${JSON.stringify(block)}\n`);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("writes shadow review suggestions without applying safe patches", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ai-review-shadow-"));
    try {
      const outputRoot = path.join(root, "output");
      const runDir = path.join(outputRoot, "runs", "run-ai-review-shadow");
      mkdirSync(runDir, { recursive: true });
      mkdirSync(path.join(runDir, "chunks"));

      const block = {
        block_id: "b_review",
        source_sha256: "ai-review-source",
        status: "keep",
        type: "paragraph",
        text: "Shadow mode must not change this block.",
        protected: false,
        risk_tags: [],
        reason: "initial",
        confidence: 0.6,
      };
      const blocksPath = path.join(runDir, "blocks.jsonl");
      writeFileSync(blocksPath, `${JSON.stringify(block)}\n`, "utf8");
      const reviewPackPath = path.join(runDir, "review_pack.json");
      writeFileSync(
        reviewPackPath,
        JSON.stringify({
          schema: "kbprep.review_pack.v1",
          policy_context: {
            document_type: "course",
            profile: "curated_obsidian_kb",
            relevant_terms: ["步骤"],
            protected_patterns: [],
            rule_sources: ["rules/base/obvious_noise.json"],
          },
          blocks: [block],
        }),
        "utf8",
      );

      const backend: AIReviewBackend = {
        async review() {
          return {
            messages: [
              JSON.stringify([
                { op: "replace", path: "/blocks/b_review/text", value: "rewritten text is not allowed" },
                { op: "replace", path: "/blocks/b_review/status", value: "review" },
              ]),
            ],
            warning: "W_TEST_BACKEND_USED",
          };
        },
      };
      const initial: WorkerResult<Record<string, unknown>> = {
        ok: true,
        data: {
          run_id: "run-ai-review-shadow",
          run_dir: runDir,
          outputs: { review_pack: reviewPackPath },
          latest_outputs: {},
        },
        warnings: [],
      };

      const reviewed = await maybeRunAiReview(
        initial,
        { mode: "ai_review", ai_review_backend: "external", review_mode: "shadow" },
        {},
        {
          api: { runtime: { aiReviewBackend: backend } },
          toolCallId: "test-review-shadow",
        },
        {
          pythonPath: "python",
          timeoutMs: 60_000,
          workerConfig: {},
        },
      );

      const suggestionsPath = path.join(runDir, "review_suggestions.json");
      const suggestions = JSON.parse(readFileSync(suggestionsPath, "utf8"));
      expect(reviewed.ok).toBe(true);
      expect(reviewed.data?.ai_review).toMatchObject({
        mode: "shadow",
        applied: false,
        patch_ops: 1,
        rejected_patch_ops: 1,
      });
      expect(reviewed.warnings).toContain("W_TEST_BACKEND_USED");
      expect(reviewed.warnings?.some((warning) => warning.includes("shadow suggestions"))).toBe(true);
      expect(suggestions.summary).toMatchObject({
        valid_patch_ops: 1,
        rejected_patch_ops: 1,
      });
      expect(suggestions.rejected_operations[0]).toMatchObject({
        operation: { path: "/blocks/b_review/text" },
        reason: "field text is not allowed",
      });
      expect(suggestions.original_blocks.b_review.status).toBe("keep");
      expect(suggestions.patch_operations).toEqual([{ op: "replace", path: "/blocks/b_review/status", value: "review" }]);
      expect(readFileSync(blocksPath, "utf8")).toBe(`${JSON.stringify(block)}\n`);
      expect(existsSync(path.join(outputRoot, "latest.json"))).toBe(false);
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
      writeFileSync(
        path.join(runDir, "quality_report.json"),
        JSON.stringify({
          source_type: "generic_block",
          source_sha256: "ai-review-source",
          plugin_version: "0.5.1",
        }),
        "utf8",
      );
      const reviewPackPath = path.join(runDir, "review_pack.json");
      writeFileSync(
        path.join(runDir, "run_metadata.json"),
        JSON.stringify({
          input_path: path.join(root, "missing-source.bin"),
        }),
        "utf8",
      );
      writeFileSync(
        reviewPackPath,
        JSON.stringify({
          schema: "kbprep.review_pack.v1",
          blocks: [block],
        }),
        "utf8",
      );

      const seenPrompts: string[] = [];
      const backend: AIReviewBackend = {
        async review(params) {
          seenPrompts.push(params.message);
          return {
            messages: [
              JSON.stringify([
                { op: "replace", path: "/blocks/b_review/text", value: "rewritten text is not allowed" },
                { op: "replace", path: "/blocks/b_review/status", value: "review" },
                { op: "replace", path: "/blocks/b_review/reason", value: "external reviewer marked this for human review" },
              ]),
            ],
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

  it("keeps protected blocks safe when apply mode receives a discard patch", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ai-review-protected-"));
    try {
      const outputRoot = path.join(root, "output");
      const runDir = path.join(outputRoot, "runs", "run-ai-review-protected");
      mkdirSync(runDir, { recursive: true });
      mkdirSync(path.join(runDir, "chunks"));

      const block = {
        block_id: "prompt_block",
        source_sha256: "ai-review-source",
        status: "keep",
        type: "prompt",
        text: "Prompt：请保留完整操作步骤。",
        protected: true,
        risk_tags: [],
        confidence: 0.9,
      };
      const blocksPath = path.join(runDir, "blocks.jsonl");
      writeFileSync(blocksPath, `${JSON.stringify(block)}\n`, "utf8");
      writeFileSync(path.join(runDir, "diagnosis_report.json"), JSON.stringify({ diagnosis: { file_id: "ai-review-source" } }), "utf8");
      writeFileSync(
        path.join(runDir, "quality_report.json"),
        JSON.stringify({
          source_type: "generic_block",
          source_sha256: "ai-review-source",
          plugin_version: "0.5.1",
        }),
        "utf8",
      );
      writeFileSync(
        path.join(runDir, "run_metadata.json"),
        JSON.stringify({
          input_path: path.join(root, "missing-source.bin"),
        }),
        "utf8",
      );
      const reviewPackPath = path.join(runDir, "review_pack.json");
      writeFileSync(
        reviewPackPath,
        JSON.stringify({
          schema: "kbprep.review_pack.v1",
          blocks: [block],
        }),
        "utf8",
      );

      const backend: AIReviewBackend = {
        async review() {
          return {
            messages: [JSON.stringify([{ op: "replace", path: "/blocks/prompt_block/status", value: "discard" }])],
          };
        },
      };
      const initial: WorkerResult<Record<string, unknown>> = {
        ok: true,
        data: {
          run_id: "run-ai-review-protected",
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
          toolCallId: "test-review-protected",
        },
        {
          pythonPath: "python",
          timeoutMs: 60_000,
          workerConfig: {},
        },
      );

      expect(reviewed.ok).toBe(true);
      expect(reviewed.data?.ai_review).toMatchObject({
        applied: 0,
        rejected: 1,
        patch_ops: 1,
      });
      expect(JSON.stringify(reviewed.data?.ai_review)).toContain("cannot discard");
      const updatedBlock = JSON.parse(readFileSync(blocksPath, "utf8").trim());
      expect(updatedBlock.status).toBe("keep");
      expect(updatedBlock.text).toBe(block.text);
      expect(updatedBlock.protected).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
