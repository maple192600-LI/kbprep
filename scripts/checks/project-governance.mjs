import { existsSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const strict = process.argv.includes("--strict");

const coreDocs = ["docs/kbprep-core-flow-design.md", "docs/kbprep-full-flowchart.html"];
const governanceDocs = [...coreDocs, "docs/kbprep-development-implementation-plan.md"];
const requiredPackageScripts = [
  "check:governance",
  "check:policy",
  "check:protected-docs",
  "check:guidance-drift",
  "check:development-docs",
  "check:forbidden-patterns",
  "check:project-governance",
  "dev:check",
  "dev:full-check",
  "test:coverage",
];

const failures = [];
const warnings = [];

for (const file of governanceDocs) {
  if (!existsSync(file)) {
    failures.push({ file, reason: "required governance document is missing" });
  }
}

const agentsText = readText("AGENTS.md");
for (const file of coreDocs) {
  if (!agentsText.includes(file)) {
    failures.push({ file: "AGENTS.md", reason: `missing highest-reference doc ${file}` });
  }
}
for (const phrase of [
  "Do not edit either file unless the owner explicitly orders it.",
  'The current development metric is not "produces Markdown once."',
  "Before editing code, explain to the owner:",
]) {
  if (!agentsText.includes(phrase)) {
    failures.push({ file: "AGENTS.md", reason: `missing governance phrase: ${phrase}` });
  }
}

const packageJson = JSON.parse(readText("package.json"));
for (const scriptName of requiredPackageScripts) {
  if (!packageJson.scripts?.[scriptName]) {
    failures.push({ file: "package.json", reason: `missing script ${scriptName}` });
  }
}
if (!/\bnpm test\b/.test(packageJson.scripts?.["dev:check"] ?? "")) {
  failures.push({ file: "package.json", reason: "dev:check must run TypeScript integration tests via npm test" });
}
if (!(packageJson.scripts?.["test:coverage"] ?? "").includes("--coverage")) {
  failures.push({ file: "package.json", reason: "test:coverage must run Vitest with measured coverage" });
}
for (const [metric, floor] of [
  ["lines", "85"],
  ["branches", "70"],
  ["functions", "80"],
  ["statements", "80"],
]) {
  if (!(packageJson.scripts?.["test:coverage"] ?? "").includes(`coverage.thresholds.${metric}=${floor}`)) {
    failures.push({ file: "package.json", reason: `test:coverage must enforce at least ${floor}% TypeScript ${metric} coverage` });
  }
}
if (!(packageJson.scripts?.["test:coverage"] ?? "").includes("scripts/checks/ts-coverage-floor.mjs")) {
  failures.push({ file: "package.json", reason: "test:coverage must run the TypeScript file coverage floor check" });
}
if (!(packageJson.scripts?.["test:coverage"] ?? "").includes("--file src/runtime/pythonRuntime.ts --file-lines 80")) {
  failures.push({ file: "package.json", reason: "test:coverage must keep pythonRuntime.ts line coverage at or above 80%" });
}
if (!packageJson.devDependencies?.["@vitest/coverage-v8"]) {
  failures.push({ file: "package.json", reason: "missing @vitest/coverage-v8 devDependency for measured TypeScript coverage" });
}
for (const file of governanceDocs) {
  if (!packageJson.files?.includes(file)) {
    failures.push({ file: "package.json", reason: `package files does not include ${file}` });
  }
}

const releaseCheckText = readText("scripts/release-check.mjs");
if (!releaseCheckText.includes("Run TypeScript coverage") || !releaseCheckText.includes("test:coverage")) {
  failures.push({ file: "scripts/release-check.mjs", reason: "release:check must run TypeScript coverage" });
}

const checkPackText = readText("scripts/check-pack.mjs");
for (const file of governanceDocs) {
  if (!checkPackText.includes(file)) {
    failures.push({ file: "scripts/check-pack.mjs", reason: `requiredFiles does not include ${file}` });
  }
}
for (const script of ["check-governance.mjs", "check-policy.mjs"]) {
  if (!checkPackText.includes(script)) {
    failures.push({ file: "scripts/check-pack.mjs", reason: `does not run ${script}` });
  }
}

const untracked = [];
for (const file of governanceDocs) {
  const tracked = git(["ls-files", "--error-unmatch", file], { allowFailure: true }).trim();
  if (!tracked) {
    untracked.push(file);
  }
}
if (untracked.length) {
  const issue = { files: untracked, reason: "governance document is not tracked by git yet" };
  if (strict) {
    failures.push(issue);
  } else {
    warnings.push(issue);
  }
}

if (failures.length) {
  process.stderr.write(
    JSON.stringify(
      {
        ok: false,
        strict,
        failures,
        warnings,
      },
      null,
      2,
    ),
  );
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(
  JSON.stringify(
    {
      ok: true,
      strict,
      checkedGovernanceDocs: governanceDocs,
      warnings,
    },
    null,
    2,
  ),
);
process.stdout.write("\n");

function readText(file) {
  if (!existsSync(file)) {
    return "";
  }
  return readFileSync(file, "utf8");
}

function git(args, options = {}) {
  const result = spawnSync("git", args, { encoding: "utf8" });
  if (result.status !== 0 && !options.allowFailure) {
    process.stderr.write(result.stderr || result.stdout || String(result.error || ""));
    process.exit(result.status ?? 1);
  }
  return result.stdout || "";
}
