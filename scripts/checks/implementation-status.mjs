import { existsSync, readFileSync } from "node:fs";

const statusPath = "docs/development/kbprep-implementation-status.json";
const claimScanFiles = [
  "README.md",
  "docs/kbprep-development-implementation-plan.md",
  "docs/development/README.md",
  "docs/development/02-canonical-ir-contract.md",
  "docs/development/04-conversion-quality-gate.md",
  "docs/development/06-cleaning-policy-library.md",
  "docs/development/07-cleaning-unit-patch-clean-view.md",
  "docs/development/10-batch-playlist-rerun.md",
  "docs/development/11-multimedia-youtube-optional.md",
];
const allowedStatuses = new Set(["implemented", "partial", "design_only", "claim_blocked"]);
const failures = [];

if (!existsSync(statusPath)) {
  failures.push({ file: statusPath, reason: "implementation status contract is missing" });
} else {
  const contract = JSON.parse(readFileSync(statusPath, "utf8"));
  validateContract(contract);
}

if (failures.length) {
  process.stderr.write(JSON.stringify({ ok: false, failures }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(JSON.stringify({ ok: true, contract: statusPath }, null, 2));
process.stdout.write("\n");

function validateContract(contract) {
  if (contract.schema !== "kbprep.implementation_status.v1") {
    failures.push({ file: statusPath, reason: "schema must be kbprep.implementation_status.v1" });
  }
  if (!Array.isArray(contract.capabilities) || !contract.capabilities.length) {
    failures.push({ file: statusPath, reason: "capabilities must be a non-empty array" });
    return;
  }
  const scannedText = claimScanFiles
    .filter((file) => existsSync(file))
    .map((file) => [file, readFileSync(file, "utf8")]);
  for (const capability of contract.capabilities) {
    validateCapability(capability, scannedText);
  }
}

function validateCapability(capability, scannedText) {
  for (const key of ["id", "label", "status", "scope"]) {
    if (typeof capability[key] !== "string" || !capability[key].trim()) {
      failures.push({ file: statusPath, capability: capability.id, reason: `${key} must be a non-empty string` });
    }
  }
  if (!allowedStatuses.has(capability.status)) {
    failures.push({ file: statusPath, capability: capability.id, reason: `unsupported status: ${capability.status}` });
  }
  if (!Array.isArray(capability.evidence) || !capability.evidence.length) {
    failures.push({ file: statusPath, capability: capability.id, reason: "evidence must be a non-empty array" });
  }
  const prohibitedClaims = capability.prohibitedClaims ?? [];
  if (!Array.isArray(prohibitedClaims)) {
    failures.push({ file: statusPath, capability: capability.id, reason: "prohibitedClaims must be an array" });
    return;
  }
  if (capability.status === "claim_blocked" && prohibitedClaims.length === 0) {
    failures.push({ file: statusPath, capability: capability.id, reason: "claim_blocked capabilities must list prohibitedClaims" });
  }
  if (capability.status !== "implemented") {
    for (const phrase of prohibitedClaims) {
      for (const [file, text] of scannedText) {
        if (phrase && text.includes(phrase)) {
          failures.push({ file, capability: capability.id, reason: `prohibited completion claim appears: ${phrase}` });
        }
      }
    }
  }
}
