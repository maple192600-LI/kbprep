import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const pythonVenvScript = "scripts/python-venv.mjs";

function loadCapabilities() {
  const code = [
    "import json",
    "from kbprep_worker.converter_capabilities import capability_gap_report, capability_matrix_rows",
    "print(json.dumps({'capabilities': capability_matrix_rows(), 'gap_report': capability_gap_report()}, ensure_ascii=False))",
  ].join("\n");
  const result = spawnSync(process.execPath, [pythonVenvScript, "-c", code], {
    cwd: repoRoot,
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONPATH: path.join(repoRoot, "python"),
      PYTHONUTF8: "1",
    },
  });
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || String(result.error || "failed to load capabilities"));
  }
  return JSON.parse(result.stdout);
}

function parseMatrix() {
  const matrixPath = path.join(repoRoot, "docs", "capability-matrix.md");
  const text = readFileSync(matrixPath, "utf8");
  const rows = new Map();
  for (const line of text.split(/\r?\n/)) {
    if (!line.startsWith("|")) continue;
    const cells = line
      .split("|")
      .slice(1, -1)
      .map((cell) => cell.trim());
    if (cells.length < 7 || cells[0] === "Capability ID" || /^-+$/.test(cells[0])) continue;
    rows.set(cells[0], {
      id: cells[0],
      sourceType: cells[1],
      route: cells[2],
      status: cells[3],
      preserves: cells[4],
      evidence: cells[5],
      risk: cells[6],
    });
  }
  return rows;
}

const loaded = loadCapabilities();
const capabilities = loaded.capabilities;
const gapReport = loaded.gap_report;
const matrixRows = parseMatrix();
const missing = [];
const mismatched = [];
const evidenceErrors = [];
const gapErrors = [];
const scenarioDir = path.join(repoRoot, "src", "test", "scenarios");
const workerTestFiles = [
  path.join(repoRoot, "src", "worker.test.ts"),
  ...(existsSync(scenarioDir)
    ? readdirSync(scenarioDir)
        .filter((file) => file.endsWith(".test.ts"))
        .sort()
        .map((file) => path.join(scenarioDir, file))
    : []),
].filter((file) => existsSync(file));
const workerTestText = workerTestFiles.map((file) => readFileSync(file, "utf8")).join("\n");
const gapsById = new Map((gapReport.gaps || []).map((gap) => [gap.id, gap]));

for (const capability of capabilities) {
  const row = matrixRows.get(capability.id);
  if (!row) {
    missing.push(capability.id);
    continue;
  }
  if (row.route !== capability.route || row.status !== capability.status) {
    mismatched.push({
      id: capability.id,
      expected: { route: capability.route, status: capability.status },
      found: { route: row.route, status: row.status },
    });
  }
  const evidence = Array.isArray(capability.test_evidence) ? capability.test_evidence : [];
  if (capability.status === "verified" && evidence.length === 0) {
    evidenceErrors.push({ id: capability.id, reason: "verified capability has no test_evidence" });
  }
  if (capability.status !== "verified") {
    const gap = gapsById.get(capability.id);
    if (!gap) {
      gapErrors.push({ id: capability.id, reason: "non-verified capability missing from capability_gap_report" });
    } else {
      if (!Array.isArray(gap.required_evidence) || gap.required_evidence.length === 0) {
        gapErrors.push({ id: capability.id, reason: "gap report missing required_evidence" });
      }
      if (!String(gap.promotion_blocker || "").trim()) {
        gapErrors.push({ id: capability.id, reason: "gap report missing promotion_blocker" });
      }
    }
  }
  if (evidence.length === 0 && !/^none$/i.test(row.evidence)) {
    evidenceErrors.push({
      id: capability.id,
      reason: "matrix evidence must be none when registry has no test_evidence",
      found: row.evidence,
    });
  }
  if (evidence.length > 0) {
    if (/^none$/i.test(row.evidence)) {
      evidenceErrors.push({ id: capability.id, reason: "matrix evidence says none but registry has test_evidence" });
    }
    for (const evidenceItem of evidence) {
      const testName = String(evidenceItem).split("::").pop() || "";
      if (!testName || !workerTestText.includes(testName)) {
        evidenceErrors.push({ id: capability.id, reason: "test_evidence does not match a worker test name", evidence: evidenceItem });
      }
      if (!row.evidence.includes(testName)) {
        evidenceErrors.push({ id: capability.id, reason: "matrix row omits registry test_evidence", evidence: evidenceItem });
      }
    }
  }
}

const extra = [...matrixRows.keys()].filter((id) => !capabilities.some((capability) => capability.id === id));

if (missing.length || mismatched.length || extra.length || evidenceErrors.length || gapErrors.length) {
  process.stderr.write(JSON.stringify({ missing, mismatched, extra, evidenceErrors, gapErrors }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(
  JSON.stringify(
    {
      checked: capabilities.length,
      missing,
      mismatched,
      extra,
      evidenceErrors,
      gapSummary: gapReport.summary,
      gapErrors,
    },
    null,
    2,
  ),
);
process.stdout.write("\n");
