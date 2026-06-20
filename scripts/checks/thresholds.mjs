import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const checkedFiles = [
  "python/kbprep_worker/classify_blocks.py",
  "python/kbprep_worker/diagnose",
  "python/kbprep_worker/obsidian_kb",
  "python/kbprep_worker/cleanup.py",
  "python/kbprep_worker/prepare_artifacts.py",
  "python/kbprep_worker/apply_patch.py",
  "python/kbprep_worker/stages/pipeline_core.py",
];

const forbidden = [
  { name: "literal confidence assignment", pattern: /confidence"\]\s*=\s*0\.\d+/ },
  { name: "literal obsidian discard confidence", pattern: /_discard\([^\n]+,\s*0\.\d+\)/ },
  { name: "bare PDF unreadable threshold", pattern: />\s*0\.25\b/ },
  { name: "bare PDF strict mojibake threshold", pattern: />\s*0\.08\b/ },
  { name: "bare PDF warning mojibake threshold", pattern: />\s*0\.03\b/ },
  { name: "bare PDF image ratio threshold", pattern: />\s*0\.5\b/ },
  { name: "bare landscape threshold", pattern: />=\s*0\.8\b/ },
  { name: "unwrapped recursive delete", pattern: /shutil\.rmtree\(/ },
];

const violations = [];
for (const relative of checkedFiles) {
  const absolute = path.join(repoRoot, relative);
  for (const file of pythonFiles(absolute)) {
    const fileRelative = path.relative(repoRoot, file).replaceAll(path.sep, "/");
    const text = readFileSync(file, "utf8");
    const lines = text.split(/\r?\n/);
    for (const [index, line] of lines.entries()) {
      for (const item of forbidden) {
        if (item.pattern.test(line)) {
          violations.push({ file: fileRelative, line: index + 1, rule: item.name, text: line.trim() });
        }
      }
    }
  }
}

function pythonFiles(target) {
  const stat = statSync(target);
  if (stat.isFile()) return target.endsWith(".py") ? [target] : [];
  return readdirSync(target, { withFileTypes: true }).flatMap((entry) => {
    const child = path.join(target, entry.name);
    if (entry.isDirectory()) return pythonFiles(child);
    return entry.isFile() && entry.name.endsWith(".py") ? [child] : [];
  });
}

if (violations.length) {
  process.stderr.write(JSON.stringify({ violations }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(JSON.stringify({ checkedFiles: checkedFiles.length, violations: 0 }, null, 2));
process.stdout.write("\n");
