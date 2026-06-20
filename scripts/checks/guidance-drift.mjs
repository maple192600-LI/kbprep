import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const roots = [
  "docs",
];

const explicitFiles = [
  "AGENTS.md",
  "README.md",
  "CHANGELOG.md",
  "package.json",
  "src/adapters/standalone/cli.ts",
];

const forbiddenPhrases = [
  "openclaw-kbprep",
  "adapter id",
  "subagent compatibility",
  "src/adapters/host",
  "optional peer dependency",
  "legacy course/self-media",
  "Legacy `curated_obsidian_kb`",
  "tuned for Simplified Chinese self-media",
  "--output-root",
  "docs/index.html",
  "kbprep-capability-guide",
  "kbprep-project-explained",
  "kbprep-project-map-report",
  "kbprep-operator-workflows",
  "repository-index",
  "docs:serve",
  "serve-docs",
];

const checkedFiles = [
  ...explicitFiles,
  ...roots.flatMap(collectFiles),
].filter((file, index, all) => all.indexOf(file) === index && existsSync(path.join(repoRoot, file)));

const violations = [];
for (const relative of checkedFiles) {
  if (relative === "scripts/checks/guidance-drift.mjs") continue;
  const text = readFileSync(path.join(repoRoot, relative), "utf8");
  const lines = text.split(/\r?\n/);
  for (const [lineIndex, line] of lines.entries()) {
    for (const phrase of forbiddenPhrases) {
      if (line.includes(phrase)) {
        violations.push({ file: relative, line: lineIndex + 1, phrase });
      }
    }
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
  forbiddenPhrases: forbiddenPhrases.length,
}, null, 2));
process.stdout.write("\n");

function collectFiles(relativeRoot) {
  const absoluteRoot = path.join(repoRoot, relativeRoot);
  if (!existsSync(absoluteRoot)) return [];
  const files = [];
  function walk(absoluteDir) {
    for (const entry of readdirSync(absoluteDir)) {
      const absolutePath = path.join(absoluteDir, entry);
      const stat = statSync(absolutePath);
      if (stat.isDirectory()) {
        walk(absolutePath);
        continue;
      }
      const relative = path.relative(repoRoot, absolutePath).replaceAll(path.sep, "/");
      if (/\.(md|html|json|jsonl|ts|mjs)$/.test(relative)) files.push(relative);
    }
  }
  walk(absoluteRoot);
  return files;
}
