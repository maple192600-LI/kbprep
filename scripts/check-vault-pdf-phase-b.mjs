import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vaultRoot = path.resolve(process.env.KBPREP_VAULT_SMOKE_ROOT || defaultVaultRoot());
const workRoot = mkdtempSync(path.join(tmpdir(), "kbprep-vault-pdf-phase-b-"));
const ignoredDirs = new Set([
  ".git",
  ".obsidian",
  ".trash",
  "build",
  "coverage",
  "dist",
  "kbprep-output",
  "node_modules",
]);

if (!existsSync(vaultRoot)) fail(`Vault root does not exist: ${vaultRoot}`);

const pdfs = collectFiles(vaultRoot).filter((file) => path.extname(file).toLowerCase() === ".pdf");
if (pdfs.length === 0) fail("No PDF files found in Vault");

const diagnoses = [];
for (const file of pdfs) {
  const diagnosis = diagnose(file);
  if (diagnosis) diagnoses.push(diagnosis);
}

const selected = selectSix(diagnoses);
const missing = Object.entries(selected)
  .filter(([, value]) => !value)
  .map(([name]) => name);

if (missing.length) {
  fail(`Missing required real PDF acceptance class(es): ${missing.join(", ")}`);
}

process.stdout.write(JSON.stringify({
  ok: true,
  pdfCount: pdfs.length,
  selected: Object.fromEntries(
    Object.entries(selected).map(([name, item]) => [name, publicEvidence(item)]),
  ),
}, null, 2));
process.stdout.write("\n");
rmSync(workRoot, { recursive: true, force: true });

function diagnose(file) {
  const result = spawnSync(process.execPath, [
    path.join(repoRoot, "scripts", "python-venv.mjs"),
    "-m",
    "kbprep_worker.cli",
    "diagnose",
    "--json-stdin",
  ], {
    cwd: repoRoot,
    input: JSON.stringify({ input_path: file, output_root: workRoot, source_type: "auto" }),
    encoding: "utf8",
    timeout: 120_000,
    env: { ...process.env, PYTHONUTF8: "1" },
  });
  if (result.status !== 0) return null;
  const lines = result.stdout.trim().split(/\r?\n/).filter(Boolean);
  const payload = JSON.parse(lines.at(-1) || "{}");
  if (!payload.ok || payload.data?.detected_format !== "pdf") return null;
  return { file, data: payload.data };
}

function selectSix(items) {
  return {
    simple_single_column: first(items, (item) => tier(item) === "tier_1" && language(item) !== "en"),
    english_simple_text: first(items, (item) => tier(item) === "tier_1" && language(item) === "en"),
    multi_column_paper: first(items, (item) => tier(item) === "tier_2" && item.data.multi_column_pages > 0),
    table_heavy: first(items, (item) => tier(item) === "tier_2" && item.data.table_pages > 0),
    scanned: first(items, (item) => tier(item) === "tier_3" && item.data.pdf_subtype === "image_only_or_scanned"),
    cid_or_tounicode_damaged: first(items, (item) => tier(item) === "tier_3" && item.data.pdf_subtype === "garbled_text_layer"),
  };
}

function first(items, predicate) {
  return items.find(predicate) || null;
}

function publicEvidence(item) {
  const diagnostics = item.data.pdf_route_diagnostics || {};
  return {
    id: createHash("sha256").update(path.relative(vaultRoot, item.file)).digest("hex").slice(0, 12),
    sizeMb: Number((statSync(item.file).size / 1024 / 1024).toFixed(1)),
    pageCount: item.data.page_count,
    sampledPageCount: item.data.sampled_page_count,
    pdfSubtype: item.data.pdf_subtype,
    textLayerHealth: item.data.text_layer_health,
    layoutComplexity: item.data.layout_complexity,
    recommendedTier: diagnostics.recommended_tier,
    recommendedRoute: diagnostics.recommended_route,
    warningCount: Array.isArray(item.data.warnings) ? item.data.warnings.length : 0,
  };
}

function tier(item) {
  return item.data.pdf_route_diagnostics?.recommended_tier || "";
}

function language(item) {
  return String(item.data.detected_language || "");
}

function collectFiles(root) {
  const collected = [];
  walk(root, collected);
  return collected;
}

function walk(dir, collected) {
  let entries = [];
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!ignoredDirs.has(entry.name)) walk(full, collected);
    } else if (entry.isFile()) {
      collected.push(full);
    }
  }
}

function defaultVaultRoot() {
  return process.platform === "win32" ? "F:\\Obsidian-Vault" : "/mnt/f/Obsidian-Vault";
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.stderr.write(`Isolated work root: ${workRoot}\n`);
  process.exit(1);
}
