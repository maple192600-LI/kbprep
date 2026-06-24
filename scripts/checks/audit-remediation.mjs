import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const remediationPath = path.join(repoRoot, "docs", "audit-remediation.md");

if (!existsSync(remediationPath)) {
  fail("docs/audit-remediation.md is required");
}

const remediation = readFileSync(remediationPath, "utf8");
for (const required of [
  "真实 coverage",
  "测试体量",
  "TS scenario 集成测试",
  "能力矩阵证据",
]) {
  if (!remediation.includes(required)) {
    fail(`docs/audit-remediation.md must mention: ${required}`);
  }
}

const bannedPatterns = [
  /测试\s*\/\s*源码比[^。\n]*(?:覆盖率|coverage)/i,
  /测试代码行数\s*\/\s*源码行数[^。\n]*(?:覆盖率|coverage)/i,
  /line\s*ratio[^.\n]*(?:coverage)/i,
];

const violations = [];
for (const file of markdownFiles(path.join(repoRoot, "docs"))) {
  const relative = path.relative(repoRoot, file).replaceAll(path.sep, "/");
  const text = readFileSync(file, "utf8");
  const lines = text.split(/\r?\n/);
  for (const [index, line] of lines.entries()) {
    if (bannedPatterns.some((pattern) => pattern.test(line))) {
      violations.push({ file: relative, line: index + 1, text: line.trim() });
    }
  }
}

if (violations.length) {
  process.stderr.write(JSON.stringify({ violations }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(JSON.stringify({ checkedDocs: markdownFiles(path.join(repoRoot, "docs")).length }, null, 2));
process.stdout.write("\n");

function markdownFiles(root) {
  if (!existsSync(root)) return [];
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const child = path.join(root, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "assets") return [];
      return markdownFiles(child);
    }
    return entry.isFile() && entry.name.endsWith(".md") ? [child] : [];
  });
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}
