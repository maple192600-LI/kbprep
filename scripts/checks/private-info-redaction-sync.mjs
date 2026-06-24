import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Guard: the redact map must stay in sync across its three homes.
 *
 * scripts/redact-map.json is the single source of truth. src/test/fixtures/
 * redact-map.ts and python/tests/redact_map.py mirror it so tests can import
 * the mapping without runtime file reads. This guard asserts the three copies
 * define the identical key->value mapping, preventing silent drift.
 */
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const jsonMap = JSON.parse(readFileSync(path.join(repoRoot, "scripts", "redact-map.json"), "utf8")).mapping;

const tsText = readFileSync(path.join(repoRoot, "src/test/fixtures/redact-map.ts"), "utf8");
const pyText = readFileSync(path.join(repoRoot, "python/tests/redact_map.py"), "utf8");

const tsMap = extractQuotedMap(tsText);
const pyMap = extractQuotedMap(pyText);

const failures = [];
compare("json", "ts", jsonMap, tsMap, failures);
compare("json", "py", jsonMap, pyMap, failures);
compare("ts", "py", tsMap, pyMap, failures);

if (failures.length) {
  process.stderr.write(`private-info-redaction-sync failed:\n${failures.join("\n")}\n`);
  process.exit(1);
}

process.stdout.write(JSON.stringify({ ok: true, entries: Object.keys(jsonMap).length }, null, 2));
process.stdout.write("\n");

function extractQuotedMap(text) {
  // Match "key": "value" pairs from the REDACT_MAP literal. Mapping keys and
  // values contain no embedded quotes, so a simple character class suffices
  // and avoids backtracking pathologies on long CJK keys.
  const map = {};
  const re = /"([^"]*)"\s*:\s*"([^"]*)"\s*,?/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    map[m[1]] = m[2];
  }
  return map;
}

function compare(labelA, labelB, a, b, failures) {
  const keysA = new Set(Object.keys(a));
  const keysB = new Set(Object.keys(b));
  for (const key of keysA) {
    if (!keysB.has(key)) {
      failures.push(`${labelA} has key "${key}" missing in ${labelB}`);
    } else if (a[key] !== b[key]) {
      failures.push(`key "${key}": ${labelA}="${a[key]}" vs ${labelB}="${b[key]}"`);
    }
  }
  for (const key of keysB) {
    if (!keysA.has(key)) {
      failures.push(`${labelB} has key "${key}" missing in ${labelA}`);
    }
  }
}
