import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runWorker } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - feedback proposals part 1", () => {
  it("records cleanup feedback as a reviewable rule proposal", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-"));
    try {
      const runDir = path.join(root, "run");
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(runDir, { recursive: true });

      const envelope = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        feedback_text: "下次删除「关注公众号」这种污染",
      });

      expect(envelope.ok).toBe(true);
      expect(envelope.data.proposal.action).toBe("discard");
      expect(envelope.data.proposal.scope).toBe("user");
      expect(envelope.data.proposal.pattern).toBe("关注公众号");
      expect(envelope.data.proposal.requires_confirmation).toBe(true);

      const lines = readFileSync(path.join(rulesDir, "proposed_rules.jsonl"), "utf8").trim().split(/\r?\n/);
      expect(lines.length).toBe(1);
      expect(JSON.parse(lines[0]).id).toBe(envelope.data.proposal.id);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("uses run artifacts to add proposal context, examples, and counterexamples", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-context-"));
    try {
      const runDir = path.join(root, "run");
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(runDir, { recursive: true });
      writeFileSync(
        path.join(runDir, "quality_report.json"),
        JSON.stringify({
          source_type: "markdown_note",
          profile: "standard",
          document_type: "webpage",
          strict_errors: ["E_QA_FAILED: CTA patterns found in non-protected cleaned blocks"],
          quality_gates: [
            { name: "cleanup_safety", status: "fail" },
            { name: "export_readiness", status: "fail" },
          ],
        }),
        "utf8",
      );
      writeFileSync(path.join(runDir, "discarded.md"), "关注公众号领取资料\n", "utf8");
      writeFileSync(path.join(runDir, "cleaned.md"), "案例：平台字段里出现关注公众号时，应作为样本值保留。\n", "utf8");
      writeFileSync(path.join(runDir, "review_needed.md"), "待复查：关注公众号是否是正文案例。\n", "utf8");

      const envelope = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        feedback_text: "下次删除「关注公众号」这种污染",
      });

      expect(envelope.ok).toBe(true);
      expect(envelope.data.proposal.artifact_context.source_type).toBe("markdown_note");
      expect(envelope.data.proposal.artifact_context.document_type).toBe("webpage");
      expect(envelope.data.proposal.artifact_context.failed_gates).toContain("cleanup_safety");
      expect(envelope.data.proposal.examples).toContain("关注公众号领取资料");
      expect(envelope.data.proposal.counterexamples).toContain("案例：平台字段里出现关注公众号时，应作为样本值保留。");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("blocks accepting feedback rules that would match counterexamples", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-counterexample-"));
    try {
      const runDir = path.join(root, "run");
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(runDir, { recursive: true });
      writeFileSync(path.join(runDir, "discarded.md"), "关注公众号领取资料\n", "utf8");
      writeFileSync(path.join(runDir, "cleaned.md"), "案例：字段值为关注公众号时表示渠道来源。\n", "utf8");
      writeFileSync(
        path.join(runDir, "quality_report.json"),
        JSON.stringify({
          source_type: "markdown_note",
          profile: "standard",
          document_type: "webpage",
          quality_gates: [{ name: "cleanup_safety", status: "fail" }],
          strict_errors: ["E_QA_FAILED: CTA patterns found in non-protected cleaned blocks"],
        }),
        "utf8",
      );

      const proposed = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        feedback_text: "下次删除「关注公众号」这种污染",
      });
      expect(proposed.data.proposal.counterexamples).toContain("案例：字段值为关注公众号时表示渠道来源。");

      const accepted = runWorker(
        "feedback",
        {
          rules_dir: rulesDir,
          accept_proposal: proposed.data.proposal.id,
          confirm_rule_acceptance: true,
        },
        1,
      );

      expect(accepted.ok).toBe(false);
      expect(accepted.error.code).toBe("E_RULE_VALIDATION_FAILED");
      expect(accepted.error.details.counterexample_matches[0]).toContain("关注公众号");
      expect(accepted.error.details.suggested_proposal.pattern).toBe("关注公众号领取资料");
      expect(accepted.error.details.suggested_proposal.scope).toBe("document_type");
      expect(accepted.error.details.suggested_proposal.document_type).toBe("webpage");
      expect(accepted.error.details.suggested_proposal.parent_proposal_id).toBe(proposed.data.proposal.id);
      expect(existsSync(path.join(rulesDir, "accepted_rules.jsonl"))).toBe(false);

      const proposals = readFileSync(path.join(rulesDir, "proposed_rules.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      expect(proposals.length).toBe(2);
      expect(proposals[1].pattern).toBe("关注公众号领取资料");
      expect(proposals[1].scope).toBe("document_type");
      expect(proposals[1].document_type).toBe("webpage");
      expect(proposals[1].counterexamples).toContain("案例：字段值为关注公众号时表示渠道来源。");

      const acceptedNarrowed = runWorker("feedback", {
        rules_dir: rulesDir,
        accept_proposal: proposals[1].id,
        confirm_rule_acceptance: true,
      });
      expect(acceptedNarrowed.ok).toBe(true);
      expect(acceptedNarrowed.data.accepted.pattern).toBe("关注公众号领取资料");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("narrows broad feedback proposals to source-pattern scope when run metadata identifies the source", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-source-narrow-"));
    try {
      const runDir = path.join(root, "output", "runs", "run-source-narrow");
      const rulesDir = path.join(root, "rules", "user");
      const sourcePath = path.join(root, "inputs", "site-a-page.md");
      mkdirSync(runDir, { recursive: true });
      mkdirSync(path.dirname(sourcePath), { recursive: true });
      writeFileSync(sourcePath, "# Site A\n", "utf8");
      writeFileSync(path.join(runDir, "discarded.md"), "站点广告 - site-a footer\n", "utf8");
      writeFileSync(path.join(runDir, "cleaned.md"), "案例：字段值为站点广告时表示投放来源。\n", "utf8");
      writeFileSync(
        path.join(runDir, "quality_report.json"),
        JSON.stringify({
          source_type: "markdown_note",
          profile: "standard",
          document_type: "unknown",
          quality_gates: [{ name: "cleanup_safety", status: "fail" }],
          strict_errors: ["E_QA_FAILED: cleanup residue"],
        }),
        "utf8",
      );
      writeFileSync(
        path.join(runDir, "run_metadata.json"),
        JSON.stringify({
          schema: "kbprep.run_metadata.v1",
          prepare_payload: {
            input_path: sourcePath,
            output_root: path.join(root, "output"),
            profile: "standard",
          },
        }),
        "utf8",
      );

      const proposed = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        feedback_text: "以后删除「站点广告」这种污染",
      });

      const accepted = runWorker(
        "feedback",
        {
          rules_dir: rulesDir,
          accept_proposal: proposed.data.proposal.id,
          confirm_rule_acceptance: true,
        },
        1,
      );

      expect(accepted.ok).toBe(false);
      expect(accepted.error.code).toBe("E_RULE_VALIDATION_FAILED");
      expect(accepted.error.details.suggested_proposal.pattern).toBe("站点广告 - site-a footer");
      expect(accepted.error.details.suggested_proposal.scope).toBe("source_pattern");
      expect(accepted.error.details.suggested_proposal.source_pattern).toBe("site-a-page.md");
      expect(accepted.error.details.suggested_proposal.narrowed_scope_reason).toContain("source");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not infer source-pattern scope from repeated feedback across runs", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-repeat-source-"));
    try {
      const rulesDir = path.join(root, "rules", "user");
      const firstRunDir = path.join(root, "output", "runs", "run-site-a-1");
      const secondRunDir = path.join(root, "output", "runs", "run-site-a-2");
      const firstSource = path.join(root, "inputs", "site-a-001.md");
      const secondSource = path.join(root, "inputs", "site-a-002.md");
      mkdirSync(firstRunDir, { recursive: true });
      mkdirSync(secondRunDir, { recursive: true });
      mkdirSync(path.dirname(firstSource), { recursive: true });
      writeFileSync(firstSource, "# Site A 1\n", "utf8");
      writeFileSync(secondSource, "# Site A 2\n", "utf8");

      for (const [runDir, sourcePath] of [
        [firstRunDir, firstSource],
        [secondRunDir, secondSource],
      ]) {
        writeFileSync(path.join(runDir, "discarded.md"), "站点页脚广告\n", "utf8");
        writeFileSync(
          path.join(runDir, "quality_report.json"),
          JSON.stringify({
            source_type: "markdown_note",
            profile: "standard",
            document_type: "unknown",
            quality_gates: [{ name: "cleanup_safety", status: "fail" }],
            strict_errors: ["E_QA_FAILED: cleanup residue"],
          }),
          "utf8",
        );
        writeFileSync(
          path.join(runDir, "run_metadata.json"),
          JSON.stringify({
            schema: "kbprep.run_metadata.v1",
            prepare_payload: {
              input_path: sourcePath,
              output_root: path.join(root, "output"),
              profile: "standard",
            },
          }),
          "utf8",
        );
      }

      const first = runWorker("feedback", {
        run_dir: firstRunDir,
        rules_dir: rulesDir,
        feedback_text: "以后删除「站点页脚广告」这种污染",
      });
      expect(first.ok).toBe(true);
      expect(first.data.proposal.scope).toBe("user");

      const second = runWorker("feedback", {
        run_dir: secondRunDir,
        rules_dir: rulesDir,
        feedback_text: "以后删除「站点页脚广告」这种污染",
      });

      expect(second.ok).toBe(true);
      expect(second.data.proposal.scope).toBe("user");
      expect(second.data.proposal.repeat_feedback).toBeUndefined();
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("infers source-domain only when source-pattern scope is explicit", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-repeat-source-identity-"));
    try {
      const rulesDir = path.join(root, "rules", "user");
      const firstRunDir = path.join(root, "output", "runs", "run-domain-1");
      const secondRunDir = path.join(root, "output", "runs", "run-domain-2");
      const firstSource = path.join(root, "inputs", "lesson-alpha.md");
      const secondSource = path.join(root, "inputs", "export-beta.md");
      mkdirSync(firstRunDir, { recursive: true });
      mkdirSync(secondRunDir, { recursive: true });
      mkdirSync(path.dirname(firstSource), { recursive: true });
      writeFileSync(firstSource, "# Lesson Alpha\n", "utf8");
      writeFileSync(secondSource, "# Export Beta\n", "utf8");

      for (const [runDir, sourcePath, sourceUrl] of [
        [firstRunDir, firstSource, "https://example.com/course/lesson-alpha"],
        [secondRunDir, secondSource, "https://example.com/course/export-beta"],
      ]) {
        writeFileSync(path.join(runDir, "discarded.md"), "来源专属广告\n", "utf8");
        writeFileSync(
          path.join(runDir, "quality_report.json"),
          JSON.stringify({
            source_type: "markdown_note",
            profile: "standard",
            document_type: "unknown",
            quality_gates: [{ name: "cleanup_safety", status: "fail" }],
            strict_errors: ["E_QA_FAILED: cleanup residue"],
          }),
          "utf8",
        );
        writeFileSync(
          path.join(runDir, "run_metadata.json"),
          JSON.stringify({
            schema: "kbprep.run_metadata.v1",
            source_identity: {
              input_path: sourcePath,
              source_name: path.basename(sourcePath),
              source_url: sourceUrl,
              source_domain: "example.com",
              site_name: "Example Course",
            },
            prepare_payload: {
              input_path: sourcePath,
              output_root: path.join(root, "output"),
              profile: "standard",
            },
          }),
          "utf8",
        );
      }

      const first = runWorker("feedback", {
        run_dir: firstRunDir,
        rules_dir: rulesDir,
        feedback_text: "以后删除「来源专属广告」这种污染",
      });
      expect(first.ok).toBe(true);
      expect(first.data.proposal.scope).toBe("user");

      const second = runWorker("feedback", {
        run_dir: secondRunDir,
        rules_dir: rulesDir,
        scope: "source_pattern",
        feedback_text: "以后删除「来源专属广告」这种污染",
      });

      expect(second.ok).toBe(true);
      expect(second.data.proposal.scope).toBe("source_pattern");
      expect(second.data.proposal.source_pattern).toBe("source_domain:example.com");
      expect(second.data.proposal.repeat_feedback).toBeUndefined();
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
