import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runWorker } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - feedback proposals part 2", () => {
  it("suggests document-type dictionary updates from accepted and rejected feedback history", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-dictionary-suggest-"));
    try {
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(rulesDir, { recursive: true });
      const acceptedRules = [
        {
          schema: "kbprep.rule_proposal.v1",
          id: "proposal-course-join",
          status: "accepted",
          action: "discard",
          scope: "document_type",
          document_type: "course",
          match: "literal",
          pattern: "加入训练营领取资料",
          reason: "course wrapper pollution",
          risk_note: "test fixture risk reviewed",
          created_from_run: "run-course-1",
          owner_confirmation_status: "confirmed",
          requires_confirmation: true,
          examples: ["加入训练营领取资料"],
          counterexamples: ["课程正文"],
          accepted_rule_id: "user-feedback-course-join",
          artifact_context: { document_type: "course", source_name: "course-a.md" },
        },
        {
          schema: "kbprep.rule_proposal.v1",
          id: "proposal-course-consult",
          status: "accepted",
          action: "discard",
          scope: "document_type",
          document_type: "course",
          match: "literal",
          pattern: "私信老师领取课件",
          reason: "course wrapper pollution",
          risk_note: "test fixture risk reviewed",
          created_from_run: "run-course-2",
          owner_confirmation_status: "confirmed",
          requires_confirmation: true,
          examples: ["私信老师领取课件"],
          counterexamples: ["课程正文"],
          accepted_rule_id: "user-feedback-course-consult",
          artifact_context: { document_type: "course", source_name: "course-b.md" },
        },
        {
          schema: "kbprep.rule_proposal.v1",
          id: "proposal-report-noise",
          status: "accepted",
          action: "discard",
          scope: "document_type",
          document_type: "report",
          match: "literal",
          pattern: "下载完整白皮书",
          reason: "report wrapper pollution",
          risk_note: "test fixture risk reviewed",
          created_from_run: "run-report-1",
          owner_confirmation_status: "confirmed",
          requires_confirmation: true,
          examples: ["下载完整白皮书"],
          counterexamples: ["报告正文"],
          accepted_rule_id: "user-feedback-report-noise",
          artifact_context: { document_type: "report", source_name: "report-a.md" },
        },
        {
          schema: "kbprep.rule_proposal.v1",
          id: "proposal-course-community",
          status: "accepted",
          action: "discard",
          scope: "document_type",
          document_type: "course",
          match: "literal",
          pattern: "加入课程社群",
          reason: "course wrapper pollution",
          risk_note: "test fixture risk reviewed",
          created_from_run: "run-course-4",
          owner_confirmation_status: "confirmed",
          requires_confirmation: true,
          examples: ["加入课程社群"],
          counterexamples: ["课程正文"],
          accepted_rule_id: "user-feedback-course-community",
          artifact_context: { document_type: "course", source_name: "course-d.md" },
        },
      ];
      const rejectedRules = [
        {
          schema: "kbprep.rule_proposal.v1",
          id: "proposal-rejected-course",
          status: "rejected",
          action: "discard",
          scope: "document_type",
          document_type: "course",
          match: "literal",
          pattern: "扫码失败排查步骤",
          reason: "should be protected",
          risk_note: "rejected fixture should not become a cleanup rule",
          created_from_run: "run-course-3",
          owner_confirmation_status: "rejected",
          requires_confirmation: true,
          examples: ["扫码失败排查步骤"],
          counterexamples: ["扫码失败排查步骤"],
          artifact_context: { document_type: "course", source_name: "course-c.md" },
        },
      ];
      writeFileSync(
        path.join(rulesDir, "accepted_rules.jsonl"),
        acceptedRules.map((item) => JSON.stringify(item)).join("\n") + "\n",
        "utf8",
      );
      writeFileSync(
        path.join(rulesDir, "rejected_rules.jsonl"),
        rejectedRules.map((item) => JSON.stringify(item)).join("\n") + "\n",
        "utf8",
      );

      const envelope = runWorker("feedback", {
        rules_dir: rulesDir,
        suggest_dictionary_updates: true,
        min_feedback_count: 2,
      });

      expect(envelope.ok).toBe(true);
      expect(envelope.data.suggestions.schema).toBe("kbprep.dictionary_suggestions.v1");
      expect(envelope.data.suggestions.suggestions).toHaveLength(1);
      const suggestion = envelope.data.suggestions.suggestions[0];
      expect(suggestion.target).toBe("rules/document_types/course.json");
      expect(suggestion.document_type).toBe("course");
      expect(suggestion.required_confirmation).toBe(true);
      expect(suggestion.feedback_scope).toBe("document_type");
      expect(suggestion.min_feedback_count).toBe(3);
      expect(suggestion.proposed_rules.map((rule: { pattern: string }) => rule.pattern)).toEqual([
        "加入训练营领取资料",
        "私信老师领取课件",
        "加入课程社群",
      ]);
      expect(suggestion.proposed_rules.map((rule: { created_from_run: string }) => rule.created_from_run)).toEqual([
        "run-course-1",
        "run-course-2",
        "run-course-4",
      ]);
      expect(JSON.stringify(suggestion)).not.toContain("扫码失败排查步骤");
      expect(envelope.data.suggestions_path).toContain("dictionary_suggestions.jsonl");
      const written = readFileSync(path.join(rulesDir, "dictionary_suggestions.jsonl"), "utf8").trim();
      expect(JSON.parse(written).document_type).toBe("course");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("promotes a confirmed dictionary suggestion into a document-type cleaning dictionary", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-dictionary-promote-"));
    try {
      const rulesDir = path.join(root, "rules", "user");
      const targetRulesDir = path.join(root, "rules");
      mkdirSync(rulesDir, { recursive: true });
      writeFileSync(
        path.join(rulesDir, "dictionary_suggestions.jsonl"),
        JSON.stringify({
          schema: "kbprep.dictionary_suggestion.v1",
          document_type: "course",
          target: "rules/document_types/course.json",
          required_confirmation: true,
          feedback_count: 2,
          proposed_rules: [
            {
              action: "discard",
              match: "literal",
              pattern: "加入训练营领取资料",
              reason: "course wrapper pollution",
              examples: ["加入训练营领取资料"],
              source_proposal_id: "proposal-course-join",
              accepted_rule_id: "user-feedback-course-join",
            },
            {
              action: "discard",
              match: "literal",
              pattern: "私信老师领取课件",
              reason: "course wrapper pollution",
              examples: ["私信老师领取课件"],
              source_proposal_id: "proposal-course-consult",
              accepted_rule_id: "user-feedback-course-consult",
            },
          ],
        }) + "\n",
        "utf8",
      );

      const envelope = runWorker("feedback", {
        rules_dir: rulesDir,
        target_rules_dir: targetRulesDir,
        promote_dictionary_suggestion: true,
        document_type: "course",
        confirm_dictionary_update: true,
      });

      expect(envelope.ok).toBe(true);
      expect(envelope.data.promoted.document_type).toBe("course");
      expect(envelope.data.promoted.promoted_count).toBe(2);
      expect(envelope.data.promoted.target_path).toContain(path.join("rules", "document_types", "course.json"));
      const courseRules = JSON.parse(readFileSync(path.join(targetRulesDir, "document_types", "course.json"), "utf8"));
      expect(courseRules.schema).toBe("kbprep.cleaning_rules.v1");
      expect(courseRules.rules).toHaveLength(2);
      expect(courseRules.rules.map((rule: { pattern: string }) => rule.pattern)).toEqual(["加入训练营领取资料", "私信老师领取课件"]);
      expect(
        courseRules.rules.every(
          (rule: { type: string; risk_tag: string }) => rule.type === "promotional_line" && rule.risk_tag === "learned_feedback_course",
        ),
      ).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("reruns representative sources after promoting a document-type dictionary suggestion", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-dictionary-regression-"));
    try {
      const rulesDir = path.join(root, "rules", "user");
      const targetRulesDir = path.join(root, "rules");
      const sourcePath = path.join(root, "course-source.md");
      const outputRoot = path.join(root, "out");
      const runDir = path.join(root, "previous", "runs", "run-1");
      mkdirSync(rulesDir, { recursive: true });
      mkdirSync(runDir, { recursive: true });
      writeFileSync(
        sourcePath,
        [
          "# 第一课：自动化清洗",
          "",
          "学习目标：理解为什么清洗规则要先保护正文。",
          "",
          "加入训练营领取资料",
          "",
          "正文：这个步骤需要保留，因为它解释了质量复检。",
          "",
        ].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(runDir, "run_metadata.json"),
        JSON.stringify({
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
        }),
        "utf8",
      );
      writeFileSync(
        path.join(runDir, "quality_report.json"),
        JSON.stringify({
          profile: "standard",
          document_type: "course",
          strict_errors: [],
        }),
        "utf8",
      );
      writeFileSync(
        path.join(rulesDir, "dictionary_suggestions.jsonl"),
        JSON.stringify({
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
              examples: ["加入训练营领取资料"],
              created_from_run: runDir,
            },
          ],
        }) + "\n",
        "utf8",
      );

      const envelope = runWorker("feedback", {
        rules_dir: rulesDir,
        target_rules_dir: targetRulesDir,
        promote_dictionary_suggestion: true,
        document_type: "course",
        confirm_dictionary_update: true,
        rerun_after_promotion: true,
      });

      expect(envelope.ok).toBe(true);
      expect(envelope.data.promoted.regression_verification.status).toBe("passed");
      expect(envelope.data.promoted.regression_verification.sample_count).toBe(1);
      const sample = envelope.data.promoted.regression_verification.samples[0];
      expect(sample.ok).toBe(true);
      expect(sample.quality_report).toContain("quality_report.json");
      expect(readFileSync(sample.cleaned_md, "utf8")).not.toContain("加入训练营领取资料");
      expect(readFileSync(sample.cleaned_md, "utf8")).toContain("质量复检");
      expect(envelope.data.promoted.promotion_history_path).toContain("promotion_history.jsonl");
      const history = readFileSync(path.join(targetRulesDir, "promotion_history.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      expect(history).toHaveLength(1);
      expect(history[0].schema).toBe("kbprep.dictionary_promotion_history.v1");
      expect(history[0].document_type).toBe("course");
      expect(history[0].promoted_count).toBe(1);
      expect(history[0].regression_verification.status).toBe("passed");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
