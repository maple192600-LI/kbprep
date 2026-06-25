import { spawnSync } from "node:child_process";

const checks = [
  ["Protected design docs", "scripts/checks/protected-docs.mjs"],
  ["Project governance wiring", "scripts/checks/project-governance.mjs"],
  ["Development docs closure", "scripts/checks/development-docs.mjs"],
  ["Flowchart drift", "scripts/checks/flowchart-drift.mjs"],
  ["Implementation status", "scripts/checks/implementation-status.mjs"],
  ["Subagent worktree discipline", "scripts/checks/subagent-worktree-discipline.mjs"],
  ["Guidance drift", "scripts/checks/guidance-drift.mjs"],
  ["Project environment commands", "scripts/checks/project-env-commands.mjs"],
  ["Private info redaction", "scripts/checks/private-info-redaction.mjs"],
  ["Private info redaction sync", "scripts/checks/private-info-redaction-sync.mjs"],
];

for (const [label, script] of checks) {
  runCheck(label, script);
}

process.stdout.write(JSON.stringify({ ok: true, checked: checks.map(([, script]) => script) }, null, 2));
process.stdout.write("\n");

function runCheck(label, script) {
  const result = spawnSync(process.execPath, [script], { encoding: "utf8" });
  if (result.status === 0) return;
  process.stderr.write(`\n${label} failed (${script})\n`);
  process.stderr.write(result.stderr || result.stdout || String(result.error || ""));
  process.exit(result.status ?? 1);
}
