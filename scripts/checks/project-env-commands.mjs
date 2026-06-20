import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const defaultRepoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const args = parseArgs(process.argv.slice(2));
const repoRoot = path.resolve(args.repoRoot ?? defaultRepoRoot);
const checkedFiles = args.check.length ? args.check : defaultCheckedFiles();
const violations = [];
const selfTestFiles = new Set([
  "src/test/scenarios/worker-governance-guards.test.ts",
]);

const commandRules = [
  {
    rule: "direct_system_python_command",
    pattern: /(^|[\s`"'])py\s+-3\b/,
  },
  {
    rule: "direct_system_python_command",
    pattern: /(^|[\s`"'])python3(?:\s|$)/,
  },
  {
    rule: "direct_system_python_command",
    pattern: /\bpython\s+-m\s+(?:pytest|unittest|kbprep_worker\.cli)\b/,
  },
  {
    rule: "direct_pythonpath_command",
    pattern: /\bPYTHONPATH=python\b/,
  },
  {
    rule: "github_actions_pythonpath",
    pattern: /^\s*PYTHONPATH:\s*python\s*$/,
  },
  {
    rule: "system_package_install",
    pattern: /\buv\s+pip\s+install\s+--system\b/,
  },
  {
    rule: "direct_test_runner_command",
    pattern: /\bnpx\s+vitest\b/,
  },
  {
    rule: "direct_python_directory_test_command",
    pattern: /\bcd\s+python\b/,
  },
  {
    rule: "test_harness_python_override",
    pattern: /\bKBPREP_TEST_PYTHON\b/,
  },
  {
    rule: "test_harness_system_python_command",
    pattern: /command:\s*["']py["']/,
  },
  {
    rule: "test_harness_system_python_command",
    pattern: /command:\s*["']python3["']/,
  },
  {
    rule: "test_harness_manual_pythonpath",
    pattern: /PYTHONPATH:\s*path\.join\(repoRoot,\s*["']python["']\)/,
  },
];

const textRules = [
  {
    rule: "python_test_subprocess_system_python",
    appliesTo: (relative) => relative.replaceAll(path.sep, "/").startsWith("python/tests/"),
    pattern: /subprocess\.(?:run|Popen|check_call|check_output)\(\s*\[\s*["']python["']/g,
  },
];

for (const relative of checkedFiles) {
  if (selfTestFiles.has(relative.replaceAll(path.sep, "/"))) continue;
  const absolute = path.join(repoRoot, relative);
  if (!existsSync(absolute)) continue;
  const text = readFileSync(absolute, "utf8");
  const lines = text.split(/\r?\n/);
  for (const [lineIndex, line] of lines.entries()) {
    for (const { rule, pattern } of commandRules) {
      if (!pattern.test(line)) continue;
      violations.push({
        file: relative.replaceAll(path.sep, "/"),
        line: lineIndex + 1,
        rule,
        text: line.trim().slice(0, 180),
      });
    }
  }
  for (const violation of textRuleViolations(relative, text)) {
    violations.push(violation);
  }
}

if (violations.length) {
  process.stderr.write(JSON.stringify({ ok: false, violations }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(JSON.stringify({
  ok: true,
  checkedFiles: checkedFiles.length,
  rules: commandRules.length,
}, null, 2));
process.stdout.write("\n");

function defaultCheckedFiles() {
  return [
    "AGENTS.md",
    "README.md",
    "package.json",
    ...collectFiles(".github/workflows", /\.(ya?ml)$/),
    ...collectFiles("docs"),
    ...collectFiles("src/test"),
    ...collectFiles("python/tests", /\.py$/),
  ].filter((file, index, all) => all.indexOf(file) === index);
}

function collectFiles(relativeRoot, allowedPattern = /\.(md|html|json|jsonl|ts|mjs)$/) {
  const absoluteRoot = path.join(repoRoot, relativeRoot);
  if (!existsSync(absoluteRoot)) return [];
  const files = [];
  function walk(absoluteDir) {
    for (const entry of readdirSync(absoluteDir, { withFileTypes: true })) {
      const absolutePath = path.join(absoluteDir, entry.name);
      const stat = statSync(absolutePath);
      if (stat.isDirectory()) {
        if (["node_modules", "dist", "build", ".git", ".kbprep"].includes(entry.name)) continue;
        walk(absolutePath);
        continue;
      }
      if (!stat.isFile()) continue;
      const relative = path.relative(repoRoot, absolutePath).replaceAll(path.sep, "/");
      if (allowedPattern.test(relative)) files.push(relative);
    }
  }
  walk(absoluteRoot);
  return files;
}

function textRuleViolations(relative, text) {
  const normalized = relative.replaceAll(path.sep, "/");
  const found = [];
  for (const { rule, appliesTo, pattern } of textRules) {
    if (!appliesTo(normalized)) continue;
    for (const match of text.matchAll(pattern)) {
      const line = text.slice(0, match.index ?? 0).split(/\r?\n/).length;
      found.push({
        file: normalized,
        line,
        rule,
        text: (match[0] || "").replace(/\s+/g, " ").trim().slice(0, 180),
      });
    }
  }
  return found;
}

function parseArgs(rawArgs) {
  const result = { check: [] };
  for (let index = 0; index < rawArgs.length; index += 1) {
    const arg = rawArgs[index];
    if (arg === "--repo-root") {
      result.repoRoot = rawArgs[++index];
    } else if (arg === "--check") {
      result.check.push(rawArgs[++index]);
    }
  }
  return result;
}
