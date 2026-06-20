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

describe("kbprep worker pipeline - feedback rules part 1", () => {
  it("applies accepted feedback rules while ignoring unaccepted proposals", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-accepted-"));
    try {
      const runDir = path.join(root, "run");
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(runDir, { recursive: true });

      const proposed = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        feedback_text: "以后删除「内部训练营限时招募」这种污染",
        counterexamples: ["正文段落"],
      });

      const beforeAccept = runPythonJson([
        "import json",
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "load_cleaning_rules.cache_clear()",
        "blocks = [{'block_id': 'b1', 'status': 'unclassified', 'type': 'paragraph', 'text': '内部训练营限时招募', 'risk_tags': [], 'protected': False}]",
        "print(json.dumps(apply_clean_rules(blocks)[0], ensure_ascii=False))",
      ].join("\n"), [], { KBPREP_USER_RULES_DIR: rulesDir });

      expect(beforeAccept.status).toBe("unclassified");

      const accepted = runWorker("feedback", {
        rules_dir: rulesDir,
        accept_proposal: proposed.data.proposal.id,
        confirm_rule_acceptance: true,
      });

      expect(accepted.ok).toBe(true);
      expect(accepted.data.accepted.status).toBe("accepted");

      const afterAccept = runPythonJson([
        "import json",
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "load_cleaning_rules.cache_clear()",
        "blocks = [{'block_id': 'b1', 'status': 'unclassified', 'type': 'paragraph', 'text': '内部训练营限时招募', 'risk_tags': [], 'protected': False}]",
        "print(json.dumps(apply_clean_rules(blocks)[0], ensure_ascii=False))",
      ].join("\n"), [], { KBPREP_USER_RULES_DIR: rulesDir });

      expect(afterAccept.status).toBe("discard");
      expect(afterAccept.cleaning_rule_id).toContain(proposed.data.proposal.id);
      expect(afterAccept.cleaning_rule_source).toContain("accepted_rules.jsonl");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("loads project-local accepted feedback rules without environment variables", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-project-rules-"));
    try {
      const result = runPythonJson([
        "import json, os, sys",
        "from pathlib import Path",
        "project = Path(sys.argv[1])",
        "rules_dir = project / '.kbprep' / 'rules' / 'user'",
        "rules_dir.mkdir(parents=True)",
        "(rules_dir / 'accepted_rules.jsonl').write_text(json.dumps({",
        "  'schema': 'kbprep.rule_proposal.v1',",
        "  'id': 'proposal-project-local',",
        "  'status': 'accepted',",
        "  'action': 'discard',",
        "  'scope': 'project',",
        "  'match': 'literal',",
        "  'pattern': '项目本地污染短语',",
        "  'reason': 'project local rule test',",
        "  'risk_note': 'test fixture risk reviewed',",
        "  'created_from_run': str(project / 'run'),",
        "  'owner_confirmation_status': 'confirmed',",
        "  'requires_confirmation': True,",
        "  'examples': ['项目本地污染短语'],",
        "  'counterexamples': ['正文段落'],",
        "  'accepted_rule_id': 'user-feedback-project-local'",
        "}, ensure_ascii=False) + '\\n', encoding='utf-8')",
        "os.chdir(project)",
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "load_cleaning_rules.cache_clear()",
        "blocks = [{'block_id': 'b1', 'status': 'unclassified', 'type': 'paragraph', 'text': '项目本地污染短语', 'risk_tags': [], 'protected': False}]",
        "print(json.dumps(apply_clean_rules(blocks)[0], ensure_ascii=False))",
      ].join("\n"), [root]);

      expect(result.status).toBe("discard");
      expect(result.cleaning_rule_source.replaceAll("\\\\", "/")).toContain(".kbprep/rules/user/accepted_rules.jsonl");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("applies accepted source-pattern feedback rules only to matching sources", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-source-pattern-rule-"));
    try {
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(rulesDir, { recursive: true });
      writeFileSync(
        path.join(rulesDir, "accepted_rules.jsonl"),
        JSON.stringify({
          schema: "kbprep.rule_proposal.v1",
          id: "proposal-source-pattern",
          status: "accepted",
          action: "discard",
          scope: "source_pattern",
          source_pattern: "site-a",
          match: "literal",
          pattern: "站点专属广告",
          reason: "only site-a uses this wrapper",
          risk_note: "test fixture risk reviewed",
          created_from_run: "test-run",
          owner_confirmation_status: "confirmed",
          requires_confirmation: true,
          examples: ["站点专属广告"],
          counterexamples: ["正文段落"],
          accepted_rule_id: "user-feedback-source-pattern",
        }) + "\n",
        "utf8",
      );

      const result = runPythonJson([
        "import json, os, sys",
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "os.environ['KBPREP_USER_RULES_DIR'] = sys.argv[1]",
        "def apply(source_identity):",
        "    load_cleaning_rules.cache_clear()",
        "    blocks = [{'block_id': 'b1', 'status': 'unclassified', 'type': 'paragraph', 'text': '站点专属广告', 'risk_tags': [], 'protected': False}]",
        "    return apply_clean_rules(blocks, source_identity=source_identity)[0]",
        "print(json.dumps({'matching': apply('inputs/site-a/page.md'), 'other': apply('inputs/site-b/page.md')}, ensure_ascii=False))",
      ].join("\n"), [rulesDir]);

      expect(result.matching.status).toBe("discard");
      expect(result.matching.cleaning_rule_id).toBe("user-feedback-source-pattern");
      expect(result.other.status).toBe("unclassified");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("matches accepted source-pattern rules against structured source identity metadata", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-source-identity-rule-"));
    try {
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(rulesDir, { recursive: true });
      writeFileSync(
        path.join(rulesDir, "accepted_rules.jsonl"),
        JSON.stringify({
          schema: "kbprep.rule_proposal.v1",
          id: "proposal-source-domain",
          status: "accepted",
          action: "discard",
          scope: "source_pattern",
          source_pattern: "source_domain:example.com",
          match: "literal",
          pattern: "来源专属广告",
          reason: "only this source family uses this wrapper",
          risk_note: "test fixture risk reviewed",
          created_from_run: "test-run",
          owner_confirmation_status: "confirmed",
          requires_confirmation: true,
          examples: ["来源专属广告"],
          counterexamples: ["正文段落"],
          accepted_rule_id: "user-feedback-source-domain",
        }) + "\n",
        "utf8",
      );

      const result = runPythonJson([
        "import json, os, sys",
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "os.environ['KBPREP_USER_RULES_DIR'] = sys.argv[1]",
        "def apply(source_identity):",
        "    load_cleaning_rules.cache_clear()",
        "    blocks = [{'block_id': 'b1', 'status': 'unclassified', 'type': 'paragraph', 'text': '来源专属广告', 'risk_tags': [], 'protected': False}]",
        "    return apply_clean_rules(blocks, source_identity=source_identity)[0]",
        "matching_identity = json.dumps({'input_path': 'exports/random-file.md', 'source_url': 'https://example.com/course/lesson-1', 'source_domain': 'example.com', 'site_name': 'Example Course'}, ensure_ascii=False)",
        "other_identity = json.dumps({'input_path': 'exports/random-file.md', 'source_url': 'https://other.example.net/course/lesson-1', 'source_domain': 'other.example.net'}, ensure_ascii=False)",
        "print(json.dumps({'matching': apply(matching_identity), 'other': apply(other_identity)}, ensure_ascii=False))",
      ].join("\n"), [rulesDir]);

      expect(result.matching.status).toBe("discard");
      expect(result.matching.cleaning_rule_id).toBe("user-feedback-source-domain");
      expect(result.other.status).toBe("unclassified");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("passes structured source identity metadata through prepare cleanup", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-prepare-source-identity-"));
    try {
      const inputPath = path.join(root, "random-export.md");
      const outputRoot = path.join(root, "out");
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(rulesDir, { recursive: true });
      writeFileSync(
        inputPath,
        "# 来源身份测试\n\n正文：这个步骤需要保留。\n\n来源专属广告\n",
        "utf8",
      );
      writeFileSync(
        path.join(rulesDir, "accepted_rules.jsonl"),
        JSON.stringify({
          schema: "kbprep.rule_proposal.v1",
          id: "proposal-prepare-source-domain",
          status: "accepted",
          action: "discard",
          scope: "source_pattern",
          source_pattern: "source_domain:example.com",
          match: "literal",
          pattern: "来源专属广告",
          reason: "source-domain cleanup",
          risk_note: "test fixture risk reviewed",
          created_from_run: "test-run",
          owner_confirmation_status: "confirmed",
          requires_confirmation: true,
          examples: ["来源专属广告"],
          counterexamples: ["正文段落"],
          accepted_rule_id: "user-feedback-prepare-source-domain",
        }) + "\n",
        "utf8",
      );

      const result = runPythonJson([
        "import contextlib, io, json, os, sys",
        "from pathlib import Path",
        "from kbprep_worker import prepare",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "os.environ['KBPREP_USER_RULES_DIR'] = sys.argv[3]",
        "load_cleaning_rules.cache_clear()",
        "buffer = io.StringIO()",
        "try:",
        "    with contextlib.redirect_stdout(buffer):",
        "        prepare.run({",
        "            'input_path': sys.argv[1],",
        "            'output_root': sys.argv[2],",
        "            'profile': 'standard',",
        "            'mode': 'rules_only',",
        "            'language': 'zh',",
        "            'source_type': 'auto',",
        "            'splitter': 'auto',",
        "            'force': True,",
        "            'source_url': 'https://example.com/course/lesson-1',",
        "            'source_domain': 'example.com',",
        "            'site_name': 'Example Course'",
        "        })",
        "except SystemExit as exc:",
        "    if exc.code not in (0, None):",
        "        raise",
        "envelope = json.loads([line for line in buffer.getvalue().splitlines() if line][-1])",
        "cleaned = Path(envelope['data']['outputs']['cleaned_md']).read_text(encoding='utf-8')",
        "metadata = json.loads((Path(envelope['data']['run_dir']) / 'run_metadata.json').read_text(encoding='utf-8'))",
        "print(json.dumps({'cleaned': cleaned, 'source_identity': metadata.get('source_identity')}, ensure_ascii=False))",
      ].join("\n"), [inputPath, outputRoot, rulesDir]);

      expect(result.cleaned).not.toContain("来源专属广告");
      expect(result.cleaned).toContain("这个步骤需要保留");
      expect(result.source_identity.source_domain).toBe("example.com");
      expect(result.source_identity.source_url).toContain("example.com/course");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not load public packaged user JSONL rules from rules/user", () => {
    runPython(
      [
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.rule_loader import load_cleaning_rules, rules_root",
        "accepted = rules_root() / 'user' / 'accepted_rules.jsonl'",
        "original = accepted.read_text(encoding='utf-8') if accepted.exists() else None",
        "try:",
        "    accepted.parent.mkdir(parents=True, exist_ok=True)",
        "    accepted.write_text('{\"schema\":\"kbprep.rule_proposal.v1\",\"id\":\"proposal-packaged-skill\",\"status\":\"accepted\",\"action\":\"discard\",\"scope\":\"user\",\"match\":\"literal\",\"pattern\":\"PACKAGED_SKILL_RULE_POLLUTION\",\"reason\":\"packaged skill user rule\",\"risk_note\":\"test fixture risk reviewed\",\"created_from_run\":\"packaged\",\"owner_confirmation_status\":\"confirmed\",\"requires_confirmation\":true,\"examples\":[\"PACKAGED_SKILL_RULE_POLLUTION\"],\"counterexamples\":[\"body paragraph\"],\"accepted_rule_id\":\"user-feedback-packaged-skill\"}\\n', encoding='utf-8')",
        "    load_cleaning_rules.cache_clear()",
        "    rules = load_cleaning_rules()",
        "    assert not any(source.replace('\\\\', '/').endswith('rules/user/accepted_rules.jsonl') for source in rules.sources), rules.sources",
        "    blocks = [{'block_id': 'p1', 'status': 'unclassified', 'type': 'paragraph', 'text': 'PACKAGED_SKILL_RULE_POLLUTION', 'risk_tags': []}]",
        "    cleaned = apply_clean_rules(blocks)",
        "    assert cleaned[0]['status'] == 'unclassified', cleaned",
        "    assert cleaned[0].get('cleaning_rule_id') != 'user-feedback-packaged-skill', cleaned",
        "finally:",
        "    if original is None:",
        "        accepted.unlink(missing_ok=True)",
        "    else:",
        "        accepted.write_text(original, encoding='utf-8')",
        "    load_cleaning_rules.cache_clear()",
      ].join("\n"),
      [],
    );
  });

  it("fails loudly when an accepted feedback rule contains an invalid regex", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-bad-user-rule-"));
    try {
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(rulesDir, { recursive: true });
      writeFileSync(
        path.join(rulesDir, "accepted_rules.jsonl"),
        JSON.stringify({
          schema: "kbprep.rule_proposal.v1",
          id: "proposal-bad-regex",
          status: "accepted",
          action: "discard",
          scope: "user",
          match: "regex",
          pattern: "(",
          reason: "invalid regex should stop rule loading",
          risk_note: "test fixture risk reviewed",
          created_from_run: "test-run",
          owner_confirmation_status: "confirmed",
          requires_confirmation: true,
          examples: ["bad"],
          counterexamples: ["body paragraph"],
          accepted_rule_id: "user-feedback-bad-regex",
        }) + "\n",
        "utf8",
      );

      runPython(
        [
          "import os, sys",
          "from kbprep_worker.rule_loader import load_cleaning_rules",
          "os.environ['KBPREP_USER_RULES_DIR'] = sys.argv[1]",
          "load_cleaning_rules.cache_clear()",
          "try:",
          "    load_cleaning_rules()",
          "except ValueError as exc:",
          "    message = str(exc)",
          "    assert 'accepted_rules.jsonl:1' in message, message",
          "    assert 'pattern is not a valid regex' in message, message",
          "else:",
          "    raise AssertionError('invalid accepted feedback regex did not fail rule loading')",
        ].join("\n"),
        [rulesDir],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("fails loudly with file and line when accepted feedback JSONL is invalid", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-bad-user-jsonl-"));
    try {
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(rulesDir, { recursive: true });
      writeFileSync(path.join(rulesDir, "accepted_rules.jsonl"), "{\"schema\":\n", "utf8");

      runPython(
        [
          "import os, sys",
          "from kbprep_worker.rule_loader import load_cleaning_rules",
          "os.environ['KBPREP_USER_RULES_DIR'] = sys.argv[1]",
          "load_cleaning_rules.cache_clear()",
          "try:",
          "    load_cleaning_rules()",
          "except ValueError as exc:",
          "    message = str(exc)",
          "    assert 'accepted_rules.jsonl:1' in message, message",
          "    assert 'invalid JSON' in message, message",
          "else:",
          "    raise AssertionError('invalid accepted feedback JSONL did not fail rule loading')",
        ].join("\n"),
        [rulesDir],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

});
