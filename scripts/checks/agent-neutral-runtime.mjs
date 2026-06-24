import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const roots = ["src", "python/kbprep_worker", "scripts", ".github/workflows"];

const explicitFiles = ["package.json"];

const allowlistedFiles = new Set(["scripts/checks/agent-neutral-runtime.mjs", "scripts/checks/guidance-drift.mjs"]);
const namedAgentTerms = ["claude", "codex", "openclaw", "hermes"];

function collectFiles(relativeRoot) {
  const absoluteRoot = path.join(repoRoot, relativeRoot);
  const files = [];
  function walk(absoluteDir) {
    for (const entry of readdirSync(absoluteDir)) {
      const absolutePath = path.join(absoluteDir, entry);
      const stat = statSync(absolutePath);
      if (stat.isDirectory()) {
        if (["__pycache__", "node_modules", "dist"].includes(entry)) continue;
        walk(absolutePath);
        continue;
      }
      const relative = path.relative(repoRoot, absolutePath).replaceAll(path.sep, "/");
      if (!/\.(ts|js|mjs|py|yml|yaml)$/.test(relative)) continue;
      if (/\.(test|spec)\.ts$/.test(relative)) continue;
      if (relative.startsWith("src/test/")) continue;
      files.push(relative);
    }
  }
  walk(absoluteRoot);
  return files;
}

const checkedFiles = [...explicitFiles, ...roots.flatMap(collectFiles)].filter((file, index, all) => all.indexOf(file) === index);

const violations = [];
for (const relative of checkedFiles) {
  if (allowlistedFiles.has(relative)) continue;
  const text = readFileSync(path.join(repoRoot, relative), "utf8");
  const lines = text.split(/\r?\n/);
  for (const [index, line] of lines.entries()) {
    const lowered = line.toLowerCase();
    for (const term of namedAgentTerms) {
      if (lowered.includes(term)) {
        violations.push({ file: relative, line: index + 1, term });
      }
    }
  }
}

if (violations.length) {
  process.stderr.write(JSON.stringify({ violations }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(
  JSON.stringify(
    {
      checkedFiles: checkedFiles.length,
      namedAgentTerms: namedAgentTerms.length,
      violations,
    },
    null,
    2,
  ),
);
process.stdout.write("\n");
