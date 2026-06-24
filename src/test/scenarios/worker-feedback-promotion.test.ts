import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  runWorker,
} from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - feedback promotion", () => {
  it("refuses to promote dictionary suggestions without explicit confirmation", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-dictionary-confirm-"));
    try {
      const rulesDir = path.join(root, "rules", "user");
      const targetRulesDir = path.join(root, "rules");
      mkdirSync(rulesDir, { recursive: true });
      writeFileSync(path.join(rulesDir, "dictionary_suggestions.jsonl"), JSON.stringify({
        schema: "kbprep.dictionary_suggestion.v1",
        document_type: "course",
        target: "rules/document_types/course.json",
        required_confirmation: true,
        feedback_count: 1,
        proposed_rules: [
          {
            action: "discard",
            match: "literal",
            pattern: "加入训练营领取资料",
            reason: "course wrapper pollution",
          },
        ],
      }) + "\n", "utf8");

      const envelope = runWorker("feedback", {
        rules_dir: rulesDir,
        target_rules_dir: targetRulesDir,
        promote_dictionary_suggestion: true,
        document_type: "course",
      }, 1);

      expect(envelope.ok).toBe(false);
      expect(envelope.error.code).toBe("E_CONFIRMATION_REQUIRED");
      expect(existsSync(path.join(targetRulesDir, "document_types", "course.json"))).toBe(false);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("summarizes dictionary promotion history by document type", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-promotion-summary-"));
    try {
      const targetRulesDir = path.join(root, "rules");
      mkdirSync(targetRulesDir, { recursive: true });
      const history = [
        {
          schema: "kbprep.dictionary_promotion_history.v1",
          created_at: "2026-06-01T00:00:00Z",
          document_type: "course",
          promoted_count: 2,
          skipped_duplicates: 0,
          promoted_rule_ids: ["course-a", "course-b"],
          regression_verification: {
            status: "passed",
            sample_count: 2,
            passed_count: 2,
            failed_count: 0,
            samples: [{ ok: true }, { ok: true }],
          },
        },
        {
          schema: "kbprep.dictionary_promotion_history.v1",
          created_at: "2026-06-02T00:00:00Z",
          document_type: "course",
          promoted_count: 1,
          skipped_duplicates: 1,
          promoted_rule_ids: ["course-c"],
          regression_verification: {
            status: "failed",
            sample_count: 2,
            passed_count: 1,
            failed_count: 1,
            samples: [{ ok: true }, { ok: false, reason: "discard_pattern_still_in_cleaned" }],
          },
        },
        {
          schema: "kbprep.dictionary_promotion_history.v1",
          created_at: "2026-06-03T00:00:00Z",
          document_type: "report",
          promoted_count: 1,
          skipped_duplicates: 0,
          promoted_rule_ids: ["report-a"],
          regression_verification: {
            status: "not_requested",
            sample_count: 0,
            passed_count: 0,
            failed_count: 0,
            samples: [],
          },
        },
      ];
      writeFileSync(path.join(targetRulesDir, "promotion_history.jsonl"), history.map((item) => JSON.stringify(item)).join("\n") + "\n", "utf8");

      const envelope = runWorker("feedback", {
        target_rules_dir: targetRulesDir,
        summarize_promotion_history: true,
      });

      expect(envelope.ok).toBe(true);
      expect(envelope.data.summary.schema).toBe("kbprep.dictionary_promotion_history_summary.v1");
      expect(envelope.data.summary.total_promotions).toBe(3);
      expect(envelope.data.summary.document_types).toHaveLength(2);
      const course = envelope.data.summary.document_types.find((item: { document_type: string }) => item.document_type === "course");
      expect(course.latest_status).toBe("failed");
      expect(course.last_failure_reason).toBe("discard_pattern_still_in_cleaned");
      expect(course.recommended_action).toContain("Stop promoting");
      const report = envelope.data.summary.document_types.find((item: { document_type: string }) => item.document_type === "report");
      expect(report.latest_status).toBe("not_requested");
      expect(report.recommended_action).toContain("Run regression");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("blocks dictionary promotion when the document type has failed promotion history", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-promotion-block-"));
    try {
      const rulesDir = path.join(root, "rules", "user");
      const targetRulesDir = path.join(root, "rules");
      mkdirSync(rulesDir, { recursive: true });
      mkdirSync(targetRulesDir, { recursive: true });
      writeFileSync(path.join(targetRulesDir, "promotion_history.jsonl"), JSON.stringify({
        schema: "kbprep.dictionary_promotion_history.v1",
        created_at: "2026-06-02T00:00:00Z",
        document_type: "course",
        promoted_count: 1,
        skipped_duplicates: 0,
        promoted_rule_ids: ["course-failed"],
        regression_verification: {
          status: "failed",
          sample_count: 1,
          passed_count: 0,
          failed_count: 1,
          samples: [{ ok: false, reason: "discard_pattern_still_in_cleaned" }],
        },
      }) + "\n", "utf8");
      writeFileSync(path.join(rulesDir, "dictionary_suggestions.jsonl"), JSON.stringify({
        schema: "kbprep.dictionary_suggestion.v1",
        document_type: "course",
        target: "rules/document_types/course.json",
        required_confirmation: true,
        feedback_count: 1,
        proposed_rules: [
          {
            action: "discard",
            match: "literal",
            pattern: "新的课程污染",
            reason: "course wrapper pollution",
          },
        ],
      }) + "\n", "utf8");

      const blocked = runWorker("feedback", {
        rules_dir: rulesDir,
        target_rules_dir: targetRulesDir,
        promote_dictionary_suggestion: true,
        document_type: "course",
        confirm_dictionary_update: true,
      }, 1);

      expect(blocked.ok).toBe(false);
      expect(blocked.error.code).toBe("E_PROMOTION_HISTORY_FAILED");
      expect(blocked.error.details.summary.latest_status).toBe("failed");
      expect(blocked.error.details.summary.last_failure_reason).toBe("discard_pattern_still_in_cleaned");
      expect(existsSync(path.join(targetRulesDir, "document_types", "course.json"))).toBe(false);

      const allowed = runWorker("feedback", {
        rules_dir: rulesDir,
        target_rules_dir: targetRulesDir,
        promote_dictionary_suggestion: true,
        document_type: "course",
        confirm_dictionary_update: true,
        allow_failed_promotion_history: true,
      });
      expect(allowed.ok).toBe(true);
      expect(allowed.data.promoted.history_risk.status).toBe("override_used");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("resolves failed promotion history after representative reruns pass", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-promotion-resolve-"));
    try {
      const targetRulesDir = path.join(root, "rules");
      const sourcePath = path.join(root, "course-source.md");
      const outputRoot = path.join(root, "out");
      const runDir = path.join(root, "previous", "runs", "run-1");
      mkdirSync(path.join(targetRulesDir, "document_types"), { recursive: true });
      mkdirSync(runDir, { recursive: true });
      writeFileSync(path.join(targetRulesDir, "promotion_history.jsonl"), JSON.stringify({
        schema: "kbprep.dictionary_promotion_history.v1",
        created_at: "2026-06-02T00:00:00Z",
        document_type: "course",
        promoted_count: 1,
        skipped_duplicates: 0,
        promoted_rule_ids: ["course-failed"],
        regression_verification: {
          status: "failed",
          sample_count: 1,
          passed_count: 0,
          failed_count: 1,
          samples: [{ ok: false, reason: "discard_pattern_still_in_cleaned" }],
        },
      }) + "\n", "utf8");
      writeFileSync(path.join(targetRulesDir, "document_types", "course.json"), JSON.stringify({
        schema: "kbprep.cleaning_rules.v1",
        description: "Course cleanup rules.",
        rules: [],
        keyword_sets: {
          cta_keywords: [],
          qr_image_markers: [],
          image_qr_indicators: [],
          image_marketing_indicators: [],
          image_operation_indicators: [],
          image_proof_indicators: [],
          image_educational_heading_indicators: [],
          tutorial_indicators: [],
          knowledge_terms: [],
          refund_patterns: [],
          footer_patterns: [],
          evidence_patterns: [],
          marketing_wrapper_heading_terms: [],
          marketing_wrapper_back_matter_terms: [],
          marketing_wrapper_line_patterns: [],
          business_method_context_terms: [],
          transcript_filler_patterns: [],
          protected_patterns: [],
          feedback_protect_intent_terms: [],
          feedback_discard_intent_terms: [],
        },
      }), "utf8");
      writeFileSync(
        sourcePath,
        "# 第一课：质量复检\n\n学习目标：确认失败样本已经可以通过。\n\n正文：这个步骤需要保留。\n",
        "utf8",
      );
      writeFileSync(path.join(runDir, "run_metadata.json"), JSON.stringify({
        schema: "kbprep.run_metadata.v1",
        prepare_payload: {
          input_path: sourcePath,
          output_root: outputRoot,
          profile: "standard",
          mode: "rules_only",
          language: "zh",
          source_type: "auto",
          splitter: "auto",
          artifact_policy: "keep_latest",
          force: true,
        },
      }), "utf8");
      writeFileSync(path.join(runDir, "quality_report.json"), JSON.stringify({
        profile: "standard",
        document_type: "course",
        strict_errors: [],
      }), "utf8");

      const resolved = runWorker("feedback", {
        target_rules_dir: targetRulesDir,
        resolve_promotion_failures: true,
        document_type: "course",
        confirm_failure_resolved: true,
        representative_run_dirs: [runDir],
      });

      expect(resolved.ok).toBe(true);
      expect(resolved.data.resolution.schema).toBe("kbprep.dictionary_promotion_resolution.v1");
      expect(resolved.data.resolution.regression_verification.status).toBe("passed");
      const lines = readFileSync(path.join(targetRulesDir, "promotion_history.jsonl"), "utf8").trim().split(/\r?\n/).map((line) => JSON.parse(line));
      expect(lines.at(-1).schema).toBe("kbprep.dictionary_promotion_resolution.v1");

      const summary = runWorker("feedback", {
        target_rules_dir: targetRulesDir,
        summarize_promotion_history: true,
        document_type: "course",
      });
      const course = summary.data.summary.document_types[0];
      expect(course.latest_status).toBe("resolved");
      expect(course.last_failure_reason).toBe("");
      expect(course.recommended_action).not.toContain("Stop promoting");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not infer number-variant regexes from one failed feedback proposal", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-regex-narrow-"));
    try {
      const runDir = path.join(root, "run");
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(runDir, { recursive: true });
      writeFileSync(
        path.join(runDir, "discarded.md"),
        "关注公众号领取第1期资料\n关注公众号领取第2期资料\n",
        "utf8",
      );
      writeFileSync(path.join(runDir, "cleaned.md"), "案例：字段值为关注公众号时表示渠道来源。\n", "utf8");
      writeFileSync(path.join(runDir, "quality_report.json"), JSON.stringify({
        source_type: "markdown_note",
        profile: "standard",
        document_type: "unknown",
        quality_gates: [{ name: "cleanup_safety", status: "fail" }],
        strict_errors: ["E_QA_FAILED: CTA patterns found in non-protected cleaned blocks"],
      }), "utf8");

      const proposed = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        feedback_text: "以后删除「关注公众号」这种污染",
      });

      const accepted = runWorker("feedback", {
        rules_dir: rulesDir,
        accept_proposal: proposed.data.proposal.id,
        confirm_rule_acceptance: true,
      }, 1);

      expect(accepted.ok).toBe(false);
      expect(accepted.error.code).toBe("E_RULE_VALIDATION_FAILED");
      expect(accepted.error.details.suggested_proposal).toBeUndefined();
      expect(accepted.error.details.counterexample_matches).toContain("案例：字段值为关注公众号时表示渠道来源。");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("turns mistaken deletion feedback into a protect proposal", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-protect-"));
    try {
      const runDir = path.join(root, "run");
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(runDir, { recursive: true });

      const envelope = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        feedback_text: "这句不该删：「关键案例：用户保留了原始证据」",
      });

      expect(envelope.ok).toBe(true);
      expect(envelope.data.proposal.action).toBe("protect");
      expect(envelope.data.proposal.pattern).toBe("关键案例：用户保留了原始证据");
      expect(envelope.data.proposal.requires_confirmation).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

});
