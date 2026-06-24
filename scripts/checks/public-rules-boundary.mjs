import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const publicRuleDirs = ["rules/base", "rules/document_types", "rules/templates"];
const publicRulesRoot = path.join(repoRoot, "rules");
const publicUserDir = path.join(repoRoot, "rules", "user");

const forbiddenTerms = [
  "生财",
  "生财有术",
  "生财AI宝典",
  "SCAI",
  "航海家",
  "花叔",
  "huasheng.ai",
  "公众号",
  "小红书",
  "视频号",
  "抖音",
  "B站",
  "哔哩",
  "微博",
  "知乎",
  "加微信",
  "微信号",
  "入群",
  "私域",
  "训练营",
  "社群",
  "圈友",
  "会员权益",
  "社群权益",
  "月入",
  "粉丝",
  "GMV",
];

const allowedTerms = ["MinerU", "Obsidian"];

const runtimeRuleArtifacts = new Set([
  "accepted_rules.jsonl",
  "dictionary_suggestions.jsonl",
  "promotion_history.jsonl",
  "proposed_rules.jsonl",
  "protected_terms.jsonl",
  "rejected_rules.jsonl",
  "rule_proposals.jsonl",
]);

const failures = [];

for (const dir of publicRuleDirs) {
  const absolute = path.join(repoRoot, dir);
  if (!existsSync(absolute)) continue;
  for (const file of collectRuleFiles(absolute)) {
    const relative = path.relative(repoRoot, file).replaceAll(path.sep, "/");
    const text = readFileSync(file, "utf8");
    for (const term of forbiddenTerms) {
      if (allowedTerms.includes(term)) continue;
      if (text.includes(term)) {
        failures.push({ file: relative, term });
      }
    }
  }
}
if (existsSync(publicUserDir)) {
  for (const file of collectRuleFiles(publicUserDir)) {
    if (file.endsWith(".jsonl")) {
      failures.push({
        file: path.relative(repoRoot, file).replaceAll(path.sep, "/"),
        term: "user_jsonl_in_public_rules",
      });
    }
  }
}
if (existsSync(publicRulesRoot)) {
  for (const file of collectRuleFiles(publicRulesRoot)) {
    if (runtimeRuleArtifacts.has(path.basename(file))) {
      failures.push({
        file: path.relative(repoRoot, file).replaceAll(path.sep, "/"),
        term: "runtime_rule_artifact_in_public_rules",
      });
    }
  }
}

if (failures.length) {
  process.stderr.write(JSON.stringify({ ok: false, failures }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(
  JSON.stringify(
    {
      ok: true,
      checkedDirs: publicRuleDirs,
      forbiddenTerms: forbiddenTerms.length,
      runtimeRuleArtifacts: runtimeRuleArtifacts.size,
    },
    null,
    2,
  ),
);
process.stdout.write("\n");

function collectRuleFiles(root) {
  const files = [];
  function walk(current) {
    for (const entry of readdirSync(current)) {
      const absolute = path.join(current, entry);
      const stat = statSync(absolute);
      if (stat.isDirectory()) {
        walk(absolute);
        continue;
      }
      if (entry.endsWith(".json") || entry.endsWith(".jsonl")) {
        files.push(absolute);
      }
    }
  }
  walk(root);
  return files.sort();
}
