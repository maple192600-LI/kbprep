import { spawnSync } from "node:child_process";

const checks = [
  ["Capability matrix", "scripts/checks/capability-matrix.mjs"],
  ["Cleaning hardcode guard", "scripts/checks/cleaning-hardcodes.mjs"],
  ["Forbidden source patterns", "scripts/checks/forbidden-patterns.mjs"],
  ["Agent-neutral runtime", "scripts/checks/agent-neutral-runtime.mjs"],
  ["Audit remediation guard", "scripts/checks/audit-remediation.mjs"],
  ["Threshold guard", "scripts/checks/thresholds.mjs"],
  ["Rule schema", "scripts/checks/rule-schema.mjs"],
  ["Public rules boundary", "scripts/checks/public-rules-boundary.mjs"],
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
