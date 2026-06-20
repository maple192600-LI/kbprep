import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  makeEpubFixture,
  makeGarbledTextLayerPdf,
  makeImageOnlyPdf,
  makeLandscapeImagePdf,
  makeLandscapeTextPdf,
  makeOfficeFixtures,
  makeTextLayerPdf,
  normalizeMarkdownText,
  parseEnvelope,
  repoRoot,
  runPython,
  runPythonJson,
  runWorker,
  runWorkerRawInput,
} from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - feedback rules part 2", () => {
  it("can rerun the affected markdown source after accepting a feedback rule", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-rerun-"));
    try {
      const inputPath = path.join(root, "source.md");
      const outputRoot = path.join(root, "output");
      const rulesDir = path.join(root, ".kbprep", "rules", "user");
      writeFileSync(inputPath, "# Note\n\n正文段落。\n\n自动重跑污染\n", "utf8");

      const prepared = runWorker("prepare", {
        input_path: inputPath,
        output_root: outputRoot,
        profile: "standard",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      expect(prepared.ok).toBe(true);

      const proposed = runWorker("feedback", {
        run_dir: prepared.data.run_dir,
        rules_dir: rulesDir,
        feedback_text: "以后删除「自动重跑污染」这种污染",
      });

      const accepted = runWorker("feedback", {
        rules_dir: rulesDir,
        accept_proposal: proposed.data.proposal.id,
        confirm_rule_acceptance: true,
        rerun_after_accept: true,
      });

      expect(accepted.ok).toBe(true);
      expect(accepted.data.rerun_verification.status).toBe("passed");
      expect(accepted.data.rerun_verification.ok).toBe(true);
      expect(accepted.data.rerun_verification.rule_effect).toBe("discard_pattern_absent_from_cleaned");
      const rerunCleaned = readFileSync(accepted.data.rerun_verification.cleaned_md, "utf8");
      expect(rerunCleaned).not.toContain("自动重跑污染");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 30_000);

  it("can rerun a failed prepare run after accepting a feedback rule using run metadata", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-failed-rerun-"));
    try {
      runPython(
        [
          "import io, json, sys",
          "from pathlib import Path",
          "from kbprep_worker import prepare, quality, feedback",
          "input_path = Path(sys.argv[1])",
          "output_root = Path(sys.argv[2])",
          "rules_dir = Path(sys.argv[3])",
          "input_path.write_text('# Note\\n\\n正文段落。\\n\\n失败重跑污染\\n', encoding='utf-8')",
          "def fake_quality(**kwargs):",
          "    return {'strict_errors': ['E_QA_FAILED: forced first-run failure'], 'warnings': [], 'quality_gates': [{'name': 'export_readiness', 'status': 'fail'}], 'next_actions': []}",
          "quality.run_quality_check = fake_quality",
          "stdout = io.StringIO()",
          "old_stdout = sys.stdout",
          "try:",
          "    sys.stdout = stdout",
          "    try:",
          "        prepare.run({'input_path': str(input_path), 'output_root': str(output_root), 'profile': 'standard', 'mode': 'rules_only', 'language': 'zh', 'source_type': 'auto', 'splitter': 'auto', 'force': True})",
          "    except SystemExit:",
          "        pass",
          "finally:",
          "    sys.stdout = old_stdout",
          "first = json.loads(stdout.getvalue())",
          "assert first['ok'] is False, first",
          "assert not (output_root / 'latest.json').exists(), list(output_root.iterdir())",
          "run_dir = Path(first['error']['details']['run_dir'])",
          "assert (run_dir / 'run_metadata.json').exists(), list(run_dir.iterdir())",
          "def invoke_feedback(payload):",
          "    out = io.StringIO()",
          "    old = sys.stdout",
          "    try:",
          "        sys.stdout = out",
          "        try:",
          "            feedback.run(payload)",
          "        except SystemExit:",
          "            pass",
          "    finally:",
          "        sys.stdout = old",
          "    return json.loads(out.getvalue())",
          "proposed = invoke_feedback({'run_dir': str(run_dir), 'rules_dir': str(rules_dir), 'feedback_text': '以后删除「失败重跑污染」这种污染'})",
          "accepted = invoke_feedback({'rules_dir': str(rules_dir), 'accept_proposal': proposed['data']['proposal']['id'], 'confirm_rule_acceptance': True, 'rerun_after_accept': True})",
          "assert accepted['ok'] is True, accepted",
          "verification = accepted['data']['rerun_verification']",
          "assert verification['status'] == 'passed', verification",
          "assert verification['rule_effect'] == 'discard_pattern_absent_from_cleaned', verification",
          "assert '失败重跑污染' not in Path(verification['cleaned_md']).read_text(encoding='utf-8'), verification",
        ].join("\n"),
        [path.join(root, "source.md"), path.join(root, "output"), path.join(root, ".kbprep", "rules", "user")],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 30_000);

  it("defaults feedback proposals to the current project .kbprep rules directory", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-project-feedback-default-"));
    try {
      const result = runPythonJson([
        "import io, json, os, sys",
        "from pathlib import Path",
        "from kbprep_worker import feedback",
        "project = Path(sys.argv[1])",
        "run_dir = project / 'run'",
        "run_dir.mkdir(parents=True)",
        "os.chdir(project)",
        "stdout = io.StringIO()",
        "old_stdout = sys.stdout",
        "try:",
        "    sys.stdout = stdout",
        "    try:",
        "        feedback.run({'run_dir': str(run_dir), 'feedback_text': '下次删除「项目默认规则污染」'})",
        "    except SystemExit:",
        "        pass",
        "finally:",
        "    sys.stdout = old_stdout",
        "payload = json.loads(stdout.getvalue())",
        "print(json.dumps({",
        "  'ok': payload['ok'],",
        "  'proposal_path': payload['data']['proposal_path'],",
        "  'exists': (project / '.kbprep' / 'rules' / 'user' / 'proposed_rules.jsonl').exists()",
        "}, ensure_ascii=False))",
      ].join("\n"), [root]);

      expect(result.ok).toBe(true);
      expect(result.exists).toBe(true);
      expect(result.proposal_path).toContain(path.join(".kbprep", "rules", "user", "proposed_rules.jsonl"));
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("records source-pattern feedback proposals with an explicit source matcher", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-source-pattern-feedback-"));
    try {
      const runDir = path.join(root, "run");
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(runDir, { recursive: true });
      writeFileSync(
        path.join(runDir, "run_metadata.json"),
        JSON.stringify({
          schema: "kbprep.run_metadata.v1",
          prepare_payload: {
            input_path: path.join(root, "inputs", "site-a-page.md"),
          },
        }),
        "utf8",
      );

      const proposed = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        scope: "source_pattern",
        feedback_text: "这个来源以后删除「站点专属广告」这种污染",
      });

      expect(proposed.ok).toBe(true);
      expect(proposed.data.proposal.scope).toBe("source_pattern");
      expect(proposed.data.proposal.source_pattern).toBe("site-a-page.md");

      const explicit = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        scope: "source_pattern",
        source_pattern: "site-a",
        feedback_text: "这个来源以后删除「站点专属广告」这种污染",
      });
      expect(explicit.data.proposal.source_pattern).toBe("site-a");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("records rejected feedback proposals without activating them", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-rejected-"));
    try {
      const runDir = path.join(root, "run");
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(runDir, { recursive: true });

      const proposed = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        feedback_text: "以后删除「临时测试广告」这种污染",
      });

      const rejected = runWorker("feedback", {
        rules_dir: rulesDir,
        reject_proposal: proposed.data.proposal.id,
        reject_reason: "这是本次文档里的正常案例，不要作为通用清洗规则",
      });

      expect(rejected.ok).toBe(true);
      expect(rejected.data.rejected.status).toBe("rejected");
      expect(rejected.data.rejected.reject_reason).toContain("正常案例");
      expect(existsSync(path.join(rulesDir, "rejected_rules.jsonl"))).toBe(true);
      expect(existsSync(path.join(rulesDir, "accepted_rules.jsonl"))).toBe(false);

      const afterReject = runPythonJson([
        "import json",
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "load_cleaning_rules.cache_clear()",
        "blocks = [{'block_id': 'b1', 'status': 'unclassified', 'type': 'paragraph', 'text': '临时测试广告', 'risk_tags': [], 'protected': False}]",
        "print(json.dumps(apply_clean_rules(blocks)[0], ensure_ascii=False))",
      ].join("\n"), [], { KBPREP_USER_RULES_DIR: rulesDir });

      expect(afterReject.status).toBe("unclassified");

      const acceptedAfterReject = runWorker("feedback", {
        rules_dir: rulesDir,
        accept_proposal: proposed.data.proposal.id,
        confirm_rule_acceptance: true,
      }, 1);

      expect(acceptedAfterReject.ok).toBe(false);
      expect(acceptedAfterReject.error.code).toBe("E_INVALID_INPUT");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("lets accepted protect feedback override generic discard rules", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-protect-accepted-"));
    try {
      const runDir = path.join(root, "run");
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(runDir, { recursive: true });

      const proposed = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        action: "protect",
        feedback_text: "不要再删「扫码失败排查步骤」这种正文标题",
        counterexamples: ["普通扫码广告"],
      });
      runWorker("feedback", {
        rules_dir: rulesDir,
        accept_proposal: proposed.data.proposal.id,
        confirm_rule_acceptance: true,
      });

      const protectedBlock = runPythonJson([
        "import json",
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "load_cleaning_rules.cache_clear()",
        "blocks = [{'block_id': 'b1', 'status': 'unclassified', 'type': 'paragraph', 'text': '扫码失败排查步骤', 'risk_tags': [], 'protected': False}]",
        "print(json.dumps(apply_clean_rules(blocks)[0], ensure_ascii=False))",
      ].join("\n"), [], { KBPREP_USER_RULES_DIR: rulesDir });

      expect(protectedBlock.status).toBe("keep");
      expect(protectedBlock.protected).toBe(true);
      expect(protectedBlock.risk_tags).toContain("user_feedback_protect");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

});
