import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";

const protectedFiles = [
  "docs/kbprep-core-flow-design.md",
  "docs/kbprep-full-flowchart.html",
];

const allowEdit = process.env.KBPREP_ALLOW_CORE_DOC_EDIT === "1";
const strictTracked = process.argv.includes("--strict-tracked");

const missing = protectedFiles.filter((file) => !existsSync(file));
const statusLines = git(["status", "--porcelain=v1", "--", ...protectedFiles])
  .split(/\r?\n/)
  .filter(Boolean);
const trackedWarnings = [];
const protectedChanges = [];

for (const file of protectedFiles) {
  const tracked = git(["ls-files", "--error-unmatch", file], { allowFailure: true }).trim();
  if (!tracked) {
    trackedWarnings.push(file);
  }
}

for (const line of statusLines) {
  const code = line.slice(0, 2);
  const file = line.slice(3).trim();
  if (code === "??") {
    continue;
  }
  protectedChanges.push({ file, status: code });
}

if (missing.length || (protectedChanges.length && !allowEdit) || (strictTracked && trackedWarnings.length)) {
  process.stderr.write(JSON.stringify({
    ok: false,
    missing,
    protectedChanges,
    untrackedProtectedFiles: trackedWarnings,
    allowEditEnv: "KBPREP_ALLOW_CORE_DOC_EDIT=1",
    strictTracked,
    message: "Protected KBPrep design documents cannot be edited unless the owner explicitly orders it.",
  }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(JSON.stringify({
  ok: true,
  protectedFiles,
  protectedChanges,
  untrackedProtectedFiles: trackedWarnings,
  warnings: trackedWarnings.length
    ? ["Protected design documents exist but are not tracked by git yet."]
    : [],
}, null, 2));
process.stdout.write("\n");

function git(args, options = {}) {
  const result = spawnSync("git", args, { encoding: "utf8" });
  if (result.status !== 0 && !options.allowFailure) {
    process.stderr.write(result.stderr || result.stdout || String(result.error || ""));
    process.exit(result.status ?? 1);
  }
  return result.stdout || "";
}
