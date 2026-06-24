import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";

const npm = "npm";
const npx = "npx";

const steps = [
  ["Verify dependency lock dry-run", npm, ["ci", "--dry-run"]],
  ["Reject whitespace errors", "git", ["diff", "--check"]],
  ["Build untracked runtime files", "custom", ["build-dist-check"]],
  ["Type-check TypeScript", npx, ["tsc", "-p", "tsconfig.json", "--noEmit"]],
  ["Run TypeScript integration tests", npm, ["test"]],
  ["Run TypeScript coverage", npm, ["run", "test:coverage"]],
  ["Lint Python worker", npm, ["run", "python:ruff"]],
  ["Type-check Python worker", npm, ["run", "python:typecheck"]],
  ["Run measured Python coverage", npm, ["run", "python:coverage"]],
  ["Run audit guard checks", npm, ["run", "audit:check"]],
  ["Check npm package contents", npm, ["run", "pack:check"]],
  ["Audit npm dependencies", npm, ["audit", "--audit-level=moderate"]],
];

for (const [label, command, args] of steps) {
  process.stdout.write(`\n==> ${label}\n$ ${[command, ...args].join(" ")}\n`);
  if (command === "custom" && args[0] === "build-dist-check") {
    runBuildDistCheck(label);
    continue;
  }
  const result = runCommand(command, args, { stdio: "inherit" });
  if (result.status !== 0) {
    process.stderr.write(`\nrelease:check failed at: ${label}\n`);
    process.exit(result.status ?? 1);
  }
}

process.stdout.write("\nrelease:check passed\n");

function runBuildDistCheck(label) {
  const trackedDist = capture("git", ["ls-files", "dist"]).trim();
  if (trackedDist) {
    process.stderr.write(
      [
        "\ndist/ must not be tracked by git.",
        "Run: git rm -r --cached dist",
        "Tracked dist files:",
        trackedDist.split(/\r?\n/).slice(0, 40).join("\n"),
      ].join("\n"),
    );
    process.exit(1);
  }
  runOrFail(npm, ["run", "build"], label);
  const requiredDistFiles = [
    "dist/index.js",
    "dist/adapters/standalone/cli.js",
    "dist/adapters/standalone/bin/prepare.js",
    "dist/runtime/pythonRuntime.js",
  ];
  const missing = requiredDistFiles.filter((file) => !existsSync(file));
  if (missing.length) {
    process.stderr.write(`\nBuild did not produce required dist files:\n${missing.map((file) => `- ${file}`).join("\n")}\n`);
    process.exit(1);
  }
}

function runOrFail(command, args, label) {
  const result = runCommand(command, args, { stdio: "inherit" });
  if (result.status !== 0) {
    process.stderr.write(`\nrelease:check failed at: ${label}\n`);
    process.exit(result.status ?? 1);
  }
}

function capture(command, args) {
  const result = runCommand(command, args, { encoding: "utf8" });
  if (result.status !== 0 && result.status !== 1) {
    process.stderr.write(result.stderr || result.stdout || String(result.error || ""));
    process.exit(result.status ?? 1);
  }
  return result.stdout;
}

function runCommand(command, args, options) {
  if (process.platform === "win32" && (command === "npm" || command === "npx")) {
    return spawnSync("cmd.exe", ["/d", "/s", "/c", command, ...args], {
      ...options,
      shell: false,
    });
  }
  return spawnSync(command, args, {
    ...options,
    shell: false,
  });
}
