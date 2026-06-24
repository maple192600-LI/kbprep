import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Guard: no private/PII terms may appear in version-controlled source.
 *
 * Why this exists: KBPrep is open-source. Real private information (personal
 * names, brand names, social handles, UIDs, revenue figures) leaked into test
 * fixtures and source in the past. public-rules-boundary.mjs only scans the
 * rules/ directory, so PII in src/, scripts/, python/ slipped through. This
 * guard closes that blind spot.
 *
 * The term list comes from scripts/redact-map.json (`privateTerms`), which is
 * the single source of truth shared with src/test/fixtures/redact-map.ts and
 * python/tests/redact_map.py. Generic marketing terms (公众号/扫码/入群/etc.)
 * are intentionally NOT in privateTerms — they are legitimate cleaning-rule
 * test samples.
 *
 * Files exempted:
 * - the redact map itself (defines the mapping; keys ARE the private terms)
 * - guard scripts whose forbiddenTerms list legitimately enumerates the terms
 *   as the rule definition
 */
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const mapPath = path.join(repoRoot, "scripts", "redact-map.json");
const map = JSON.parse(readFileSync(mapPath, "utf8"));
const privateTerms = map.privateTerms;

if (!Array.isArray(privateTerms) || privateTerms.length === 0) {
  process.stderr.write(`private-info-redaction: no privateTerms found in ${mapPath}\n`);
  process.exit(1);
}

// privateTerms is the scan list. It may contain short prefixes (e.g.
// "高客单赛道") that catch variants of longer mapping keys, so it is NOT
// required to be a subset of mapping keys. The sync guard checks that the
// three mapping copies stay identical.

const scanDirs = ["src", "scripts", "python", "docs", "rules"];
const scanExts = new Set([".ts", ".tsx", ".js", ".mjs", ".cjs", ".py", ".json", ".md", ".html"]);
const skipDirs = new Set(["node_modules", "dist", "coverage", "__pycache__", ".mypy_cache", ".ruff_cache", ".git", ".kbprep"]);

const exempt = new Set([
  "scripts/redact-map.json",
  "src/test/fixtures/redact-map.ts",
  "python/tests/redact_map.py",
  "scripts/checks/private-info-redaction.mjs",
  "scripts/checks/private-info-redaction-sync.mjs",
  "scripts/checks/public-rules-boundary.mjs",
  "scripts/checks/cleaning-hardcodes.mjs",
]);

const failures = [];
for (const dir of scanDirs) {
  const abs = path.join(repoRoot, dir);
  if (!existsSync(abs)) continue;
  for (const file of collectSourceFiles(abs)) {
    const rel = path.relative(repoRoot, file).replaceAll(path.sep, "/");
    if (exempt.has(rel)) continue;
    const text = readFileSync(file, "utf8");
    for (const term of privateTerms) {
      if (text.includes(term)) {
        failures.push({ file: rel, term });
      }
    }
  }
}

if (failures.length) {
  process.stderr.write(`private-info-redaction failed: ${failures.length} private term hit(s)\n`);
  process.stderr.write(JSON.stringify(failures, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(JSON.stringify({ ok: true, privateTerms: privateTerms.length, scannedDirs: scanDirs }, null, 2));
process.stdout.write("\n");

function collectSourceFiles(root) {
  const files = [];
  function walk(current) {
    let entries;
    try {
      entries = readdirSync(current);
    } catch {
      return;
    }
    for (const entry of entries) {
      const absolute = path.join(current, entry);
      let st;
      try {
        st = statSync(absolute);
      } catch {
        continue;
      }
      if (st.isDirectory()) {
        if (skipDirs.has(entry)) continue;
        walk(absolute);
      } else if (scanExts.has(path.extname(entry))) {
        files.push(absolute);
      }
    }
  }
  walk(root);
  return files.sort();
}
