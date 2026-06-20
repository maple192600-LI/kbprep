import { spawnSync } from "node:child_process";

runScript("Governance checks", "scripts/check-governance.mjs");
runScript("Policy checks", "scripts/check-policy.mjs");

const requiredFiles = [
  "dist/index.js",
  "dist/adapters/standalone/cli.js",
  "dist/adapters/standalone/bin/preflight.js",
  "dist/adapters/standalone/bin/analyze.js",
  "dist/adapters/standalone/bin/prepare.js",
  "dist/adapters/standalone/bin/apply-review.js",
  "dist/adapters/standalone/bin/feedback.js",
  "dist/adapters/standalone/bin/cleanup.js",
  "dist/adapters/standalone/bin/batch.js",
  "dist/runtime/pythonRuntime.js",
  "python/kbprep_worker/obsidian_kb/__init__.py",
  "python/kbprep_worker/obsidian_kb/body_notes.py",
  "python/kbprep_worker/obsidian_kb/context.py",
  "python/kbprep_worker/obsidian_kb/frontmatter.py",
  "python/kbprep_worker/obsidian_kb/links.py",
  "python/kbprep_worker/obsidian_kb/policy.py",
  "python/kbprep_worker/obsidian_kb/signals.py",
  "python/kbprep_worker/obsidian_kb/titles.py",
  "python/kbprep_worker/diagnose/__init__.py",
  "python/kbprep_worker/obsidian_template.py",
  "python/kbprep_worker/private_rules.py",
  "python/kbprep_worker/converter_capabilities.py",
  "python/kbprep_worker/converter_registry.py",
  "python/kbprep_worker/cleaning_registry.py",
  "python/kbprep_worker/document_type_signals.py",
  "python/kbprep_worker/prepare_diagnosis.py",
  "python/kbprep_worker/prepare_runtime.py",
  "python/kbprep_worker/quality/__init__.py",
  "python/kbprep_worker/quality/conversion_gate.py",
  "python/kbprep_worker/quality/runner.py",
  "python/kbprep_worker/quality/gates.py",
  "python/kbprep_worker/quality/retention.py",
  "python/kbprep_worker/feedback/__init__.py",
  "python/kbprep_worker/feedback/command.py",
  "python/kbprep_worker/feedback/dictionary_suggestions.py",
  "python/kbprep_worker/feedback/promotion_history.py",
  "python/kbprep_worker/feedback/proposals.py",
  "python/kbprep_worker/feedback/rerun_verification.py",
  "python/kbprep_worker/feedback/support.py",
  "python/kbprep_worker/stages/pipeline_conversion.py",
  "python/kbprep_worker/title_filters.py",
  "rules/base/obvious_noise.json",
  "rules/base/document_type_signals.json",
  "rules/base/ocr_normalization.json",
  "rules/base/title_filters.json",
  "rules/templates/obsidian_generic.json",
  "rules/templates/README.md",
  "rules/user/README.md",
  "AGENTS.md",
  "docs/agent-neutral.md",
  "docs/audit-remediation.md",
  "docs/audit-remediation-round2.md",
  "docs/capability-matrix.md",
  "docs/development/README.md",
  "docs/development/00-current-state-and-gap.md",
  "docs/development/01-design-source-sync.md",
  "docs/development/02-canonical-ir-contract.md",
  "docs/development/03-deterministic-conversion-routing.md",
  "docs/development/04-conversion-quality-gate.md",
  "docs/development/05-document-type-classification.md",
  "docs/development/06-cleaning-policy-library.md",
  "docs/development/07-cleaning-unit-patch-clean-view.md",
  "docs/development/08-source-side-publish.md",
  "docs/development/09-feedback-rule-learning.md",
  "docs/development/10-batch-playlist-rerun.md",
  "docs/development/11-multimedia-youtube-optional.md",
  "docs/development/12-release-acceptance-and-governance.md",
  "docs/development/kbprep-implementation-status.json",
  "docs/quality-loop.md",
  "docs/rule-schema-migrations.md",
  "docs/feedback-learning.md",
  "docs/flowchart/kbprep-flow.json",
  "docs/reports/kbprep-current-architecture.html",
  "docs/hardcoded-cleaning-inventory.md",
  "docs/kbprep-core-flow-design.md",
  "docs/kbprep-development-implementation-plan.md",
  "docs/kbprep-full-flowchart.html",
  "docs/known-issues.md",
  "docs/risk-tags.md",
  "docs/standalone-cli.md",
  "CHANGELOG.md",
  "LICENSE",
];

const npmCommand = process.platform === "win32" ? "cmd.exe" : "npm";
const npmArgs = process.platform === "win32"
  ? ["/d", "/s", "/c", "npm", "pack", "--dry-run", "--json"]
  : ["pack", "--dry-run", "--json"];
const result = spawnSync(npmCommand, npmArgs, {
  encoding: "utf-8",
});

if (result.status !== 0) {
  process.stderr.write(result.stderr || result.stdout || String(result.error || ""));
  process.exit(result.status ?? 1);
}

let pack;
try {
  pack = JSON.parse(result.stdout)[0];
} catch (error) {
  process.stderr.write(`Failed to parse npm pack JSON: ${error}\n${result.stdout}`);
  process.exit(1);
}

const files = new Set(pack.files.map((file) => file.path));
const missing = requiredFiles.filter((file) => !files.has(file));
const forbidden = [...files].filter((file) => (
  file.startsWith("rules/user/") && file.endsWith(".jsonl")
) || file.startsWith(".kbprep/")
  || file === "rules/templates/self_media_course.json"
  || file === "rules/templates/obsidian_course_kb.json");

if (missing.length > 0) {
  process.stderr.write(`npm package is missing required files:\n${missing.map((file) => `- ${file}`).join("\n")}\n`);
  process.exit(1);
}
if (forbidden.length > 0) {
  process.stderr.write(`npm package contains private rule files:\n${forbidden.map((file) => `- ${file}`).join("\n")}\n`);
  process.exit(1);
}

process.stdout.write(JSON.stringify({
  filename: pack.filename,
  version: pack.version,
  fileCount: pack.files.length,
  checked: requiredFiles.length,
}, null, 2));
process.stdout.write("\n");

function runScript(label, script) {
  const result = spawnSync(process.execPath, [script], { encoding: "utf-8" });
  if (result.status === 0) return;
  process.stderr.write(`\n${label} failed (${script})\n`);
  process.stderr.write(result.stderr || result.stdout || String(result.error || ""));
  process.exit(result.status ?? 1);
}
