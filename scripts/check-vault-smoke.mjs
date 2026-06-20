import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, statSync, copyFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vaultRoot = path.resolve(process.env.KBPREP_VAULT_SMOKE_ROOT || defaultVaultRoot());
const workRoot = mkdtempSync(path.join(tmpdir(), "kbprep-vault-smoke-"));

const ignoredDirs = new Set([
  ".obsidian",
  ".trash",
  ".git",
  "node_modules",
  "dist",
  "build",
  "coverage",
  "kbprep-output",
]);

if (!existsSync(vaultRoot)) {
  fail(`Vault root does not exist: ${vaultRoot}. Set KBPREP_VAULT_SMOKE_ROOT to override.`);
}

const files = collectFiles(vaultRoot);
const samples = selectSamples(files);
const results = [];

process.stdout.write(`Vault smoke root: ${vaultRoot}\n`);
process.stdout.write(`Isolated work root: ${workRoot}\n`);

runAnalyzeOnly("unsupported_media", samples.unsupportedMedia);
runPrepareExpectedPass("markdown_plain", samples.markdownPlain);
runMarkdownMissingAssetExpectedFail(samples.markdownWithMissingAssets);
runSyntheticMarkdownWithAsset(samples.markdownPlain, samples.imageAsset);
for (const [name, sample] of [
  ["pdf_text_layer", samples.pdf],
  ["pptx_office_xml", samples.pptx],
  ["docx_office_xml", samples.docx],
  ["epub_xhtml", samples.epub],
  ["html_direct", samples.html],
  ["vtt_transcript", samples.vtt],
  ["txt_direct", samples.txt],
]) {
  runPrepareExpectedPass(name, sample);
}
runBatchSmoke([samples.markdownPlain, samples.docx, samples.txt]);

process.stdout.write(JSON.stringify({
  ok: true,
  vaultRoot,
  workRoot,
  checked: results.length,
  results,
}, null, 2));
process.stdout.write("\n");

function runAnalyzeOnly(name, source) {
  const outDir = path.join(workRoot, `analyze-${safeName(name)}`);
  const result = runCli("analyze", ["--input", source, "--output", outDir]);
  if (result.status === 0) {
    const parsed = parseJsonOutput(result.stdout, name);
    const capability = parsed.data?.capability || {};
    if (!["experimental", "unsupported"].includes(capability.status)) {
      fail(`${name} should report experimental or unsupported capability, got ${capability.status || "<missing>"}`);
    }
    record(name, source, "pass", { capability: capability.id, status: capability.status });
    return;
  }
  const parsed = parseJsonOutput(result.stdout, name);
  record(name, source, "pass", { expectedFailure: parsed.error?.code || "analyze_failed" });
}

function runPrepareExpectedPass(name, source) {
  const input = copySource(source, path.join(workRoot, `input-${safeName(name)}`));
  const outDir = path.join(workRoot, `out-${safeName(name)}`);
  const result = runCli("prepare", ["--input", input, "--output", outDir, "--force", "--artifact-policy", "final_only"]);
  if (result.status !== 0) {
    fail(`${name} prepare failed unexpectedly:\n${result.stdout || result.stderr}`);
  }
  assertSuccessfulOutput(name, outDir);
  record(name, source, "pass", { output: outDir });
}

function runMarkdownMissingAssetExpectedFail(source) {
  const input = copySource(source, path.join(workRoot, "input-markdown-missing-assets"));
  const outDir = path.join(workRoot, "out-markdown-missing-assets");
  const result = runCli("prepare", ["--input", input, "--output", outDir, "--force", "--artifact-policy", "final_only"]);
  if (result.status === 0) {
    fail("markdown_missing_assets should fail because local image assets were not copied.");
  }
  const parsed = parseJsonOutput(result.stdout, "markdown_missing_assets");
  const strictErrors = parsed.error?.details?.strict_errors || [];
  if (!strictErrors.some((item) => String(item).includes("referenced image files are missing"))) {
    fail(`markdown_missing_assets failed for the wrong reason: ${JSON.stringify(strictErrors)}`);
  }
  record("markdown_missing_assets", source, "pass", { expectedFailure: strictErrors[0] });
}

function runSyntheticMarkdownWithAsset(textSource, imageSource) {
  const inputDir = path.join(workRoot, "input-markdown-with-assets");
  const assetsDir = path.join(inputDir, "assets");
  mkdirSync(assetsDir, { recursive: true });
  const text = readFileSync(textSource, "utf8").split(/\r?\n/).slice(0, 80).join("\n");
  const imageName = path.basename(imageSource);
  copyFileSync(imageSource, path.join(assetsDir, imageName));
  const input = path.join(inputDir, "vault-text-with-vault-image.md");
  writeFileSync(input, `${text}\n\n![vault image](assets/${imageName})\n`, "utf8");
  const outDir = path.join(workRoot, "out-markdown-with-assets");
  const result = runCli("prepare", ["--input", input, "--output", outDir, "--force", "--artifact-policy", "final_only"]);
  if (result.status !== 0) {
    fail(`markdown_with_assets prepare failed unexpectedly:\n${result.stdout || result.stderr}`);
  }
  assertSuccessfulOutput("markdown_with_assets", outDir);
  record("markdown_with_assets", input, "pass", { output: outDir, sourceText: textSource, sourceImage: imageSource });
}

function runBatchSmoke(sources) {
  const inputDir = path.join(workRoot, "batch-input");
  mkdirSync(inputDir, { recursive: true });
  for (const source of sources) {
    copySource(source, inputDir);
  }
  const outDir = path.join(workRoot, "batch-output");
  const result = runCli("batch", ["--input", inputDir, "--output", outDir, "--force", "--artifact-policy", "final_only"]);
  if (result.status !== 0) {
    fail(`batch smoke failed:\n${result.stdout || result.stderr}`);
  }
  const resultsPath = path.join(outDir, "results.json");
  if (!existsSync(resultsPath)) {
    fail("batch smoke did not write results.json");
  }
  const manifestPath = path.join(outDir, "batch_manifest.json");
  if (!existsSync(manifestPath)) {
    fail("batch smoke did not write batch_manifest.json");
  }
  const batchResults = JSON.parse(readFileSync(resultsPath, "utf8"));
  const batchManifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  if (batchManifest.schema !== "kbprep.batch_manifest.v1") {
    fail("batch smoke wrote an invalid batch manifest schema");
  }
  const failedCount = Number(batchManifest.summary?.failed || 0);
  if (failedCount > 0) {
    fail(`batch smoke manifest reported ${failedCount} failed item(s)`);
  }
  const failures = Array.isArray(batchResults.failures) ? batchResults.failures : [];
  if (failures.length > 0) {
    fail(`batch smoke reported failures: ${JSON.stringify(failures.slice(0, 3))}`);
  }
  record("batch_smoke", inputDir, "pass", { output: outDir });
}

function assertSuccessfulOutput(name, outDir) {
  const latest = path.join(outDir, "latest.json");
  const quality = path.join(outDir, "quality_report.json");
  const conversion = path.join(outDir, "conversion_report.json");
  const discarded = path.join(outDir, "discarded.md");
  const reviewNeeded = path.join(outDir, "review_needed.md");
  for (const file of [latest, quality, conversion, discarded, reviewNeeded]) {
    if (!existsSync(file)) fail(`${name} missing expected artifact: ${file}`);
  }
  const report = JSON.parse(readFileSync(quality, "utf8"));
  const strictErrors = report.strict_errors || [];
  if (strictErrors.length > 0) {
    fail(`${name} strict quality errors: ${JSON.stringify(strictErrors)}`);
  }
  const exportGate = (report.quality_gates || []).find((gate) => gate.name === "export_readiness");
  if (!exportGate || exportGate.status !== "pass") {
    fail(`${name} export_readiness did not pass`);
  }
}

function selectSamples(allFiles) {
  const preferred = {
    markdownPlain: "03-Resources/2026年AI时代财务考证思考.md",
    markdownWithMissingAssets: "04-Archive/ExampleCourse.md",
    pdf: "03-Resources/小企业会计准则分录大全.pdf",
    pptx: "03-Resources/财务的变革与重塑11.pptx",
    docx: "03-Resources/财务知识库建设手册_v2.0.docx",
    html: "财务AI产品设计/GPT讨论/preview (2).html",
  };
  const selected = {
    markdownPlain: pick(preferred.markdownPlain, [".md"], (file) => !hasMarkdownImage(file)),
    markdownWithMissingAssets: pick(preferred.markdownWithMissingAssets, [".md"], hasMarkdownImage),
    pdf: pick(preferred.pdf, [".pdf"], (file) => statSync(file).size < 2 * 1024 * 1024),
    pptx: pick(preferred.pptx, [".pptx"], (file) => statSync(file).size < 2 * 1024 * 1024),
    docx: pick(preferred.docx, [".docx"], (file) => statSync(file).size < 2 * 1024 * 1024),
    epub: pick(null, [".epub"], (file) => statSync(file).size < 2 * 1024 * 1024),
    html: pick(preferred.html, [".html"], (file) => statSync(file).size < 2 * 1024 * 1024),
    vtt: pick(null, [".vtt"], (file) => statSync(file).size < 2 * 1024 * 1024),
    txt: pick(null, [".txt"], (file) => statSync(file).size < 256 * 1024),
    unsupportedMedia: pick(null, [".mp3", ".png", ".jpg", ".jpeg"], (file) => statSync(file).size < 5 * 1024 * 1024),
    imageAsset: pick(null, [".jpg", ".jpeg", ".png"], (file) => statSync(file).size < 512 * 1024),
  };
  return selected;

  function pick(relativePreferred, extensions, predicate) {
    if (relativePreferred) {
      const exact = path.join(vaultRoot, ...relativePreferred.split("/"));
      if (existsSync(exact) && predicate(exact)) return exact;
    }
    const found = allFiles.find((file) => extensions.includes(path.extname(file).toLowerCase()) && predicate(file));
    if (!found) fail(`No Vault sample found for ${extensions.join(", ")}`);
    return found;
  }
}

function hasMarkdownImage(file) {
  const text = readFileSync(file, "utf8");
  return /!\[[^\]]*]\([^)]+[)]|!\[\[[^\]]+]]/.test(text);
}

function collectFiles(root) {
  const collected = [];
  function walk(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (ignoredDirs.has(entry.name)) continue;
        walk(full);
      } else if (entry.isFile()) {
        collected.push(full);
      }
    }
  }
  walk(root);
  return collected;
}

function copySource(source, targetDir) {
  mkdirSync(targetDir, { recursive: true });
  const target = path.join(targetDir, path.basename(source));
  copyFileSync(source, target);
  return target;
}

function runCli(command, args) {
  const binByCommand = {
    analyze: "analyze.js",
    prepare: "prepare.js",
    batch: "batch.js",
  };
  const bin = path.join(repoRoot, "dist", "adapters", "standalone", "bin", binByCommand[command]);
  if (!existsSync(bin)) fail(`Missing CLI bin ${bin}. Run npm run build first.`);
  const pythonPath = projectPythonPath();
  return spawnSync(process.execPath, [bin, ...args], {
    cwd: repoRoot,
    encoding: "utf8",
    timeout: command === "batch" ? 600_000 : 240_000,
    env: {
      ...process.env,
      KBPREP_SKIP_AUTO_SETUP: "1",
      KBPREP_PYTHON: pythonPath,
      PYTHONUTF8: "1",
    },
  });
}

function projectPythonPath() {
  const pythonPath = process.platform === "win32"
    ? path.join(repoRoot, ".kbprep", "venv", "Scripts", "python.exe")
    : path.join(repoRoot, ".kbprep", "venv", "bin", "python");
  if (!existsSync(pythonPath)) {
    fail(`Project Python runtime is missing: ${pythonPath}. Run npm run python:check-size first.`);
  }
  return pythonPath;
}

function parseJsonOutput(stdout, label) {
  try {
    return JSON.parse(stdout);
  } catch {
    const trimmed = String(stdout || "").trim();
    const first = trimmed.indexOf("{");
    const last = trimmed.lastIndexOf("}");
    if (first >= 0 && last > first) {
      return JSON.parse(trimmed.slice(first, last + 1));
    }
    fail(`${label} did not produce parseable JSON: ${trimmed.slice(0, 500)}`);
  }
}

function record(name, source, status, details) {
  results.push({
    name,
    status,
    source,
    details,
  });
}

function safeName(name) {
  return name.replace(/[^0-9A-Za-z._-]+/g, "_");
}

function defaultVaultRoot() {
  return process.platform === "win32" ? "F:\\Obsidian-Vault" : "/mnt/f/Obsidian-Vault";
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.stderr.write(`Isolated work root: ${workRoot}\n`);
  process.exit(1);
}
