import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const args = parseArgs(process.argv.slice(2));
const repoRoot = path.resolve(args.repoRoot ?? ".");
const statusRelativePath = args.status ?? "docs/development/kbprep-implementation-status.json";
const statusPath = path.join(repoRoot, statusRelativePath);
const claimScanFiles = [
  "README.md",
  "docs/kbprep-development-implementation-plan.md",
  "docs/development/README.md",
  "docs/development/development-roadmap.md",
  "docs/development/02-canonical-ir-contract.md",
  "docs/development/04-conversion-quality-gate.md",
  "docs/development/06-cleaning-policy-library.md",
  "docs/development/07-cleaning-unit-patch-clean-view.md",
  "docs/development/10-batch-playlist-rerun.md",
  "docs/development/11-multimedia-youtube-optional.md",
];
const requiredCapabilityIds = [
  "design_source_alignment",
  "source_side_publish",
  "conversion_quality_gate",
  "canonical_ir_contract",
  "document_type_classification",
  "cleaning_policy_snapshot",
  "patch_clean_view",
  "feedback_rule_learning",
  "batch_playlist_rerun",
  "media_local_transcript",
  "youtube_url_routes",
];
const retiredCapabilityIds = new Set(["media_youtube_optional_routes"]);
const allowedStatuses = new Set(["implemented", "partial", "design_only", "claim_blocked"]);
const codeOrTestEvidenceExemptions = new Set(["design_source_alignment"]);
const failures = [];

if (!existsSync(statusPath)) {
  failures.push({ file: statusRelativePath, reason: "implementation status contract is missing" });
} else {
  const contract = JSON.parse(readFileSync(statusPath, "utf8"));
  validateContract(contract);
}

if (failures.length) {
  process.stderr.write(JSON.stringify({ ok: false, failures }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(JSON.stringify({ ok: true, contract: statusRelativePath }, null, 2));
process.stdout.write("\n");

function validateContract(contract) {
  if (contract.schema !== "kbprep.implementation_status.v1") {
    failures.push({ file: statusRelativePath, reason: "schema must be kbprep.implementation_status.v1" });
  }
  if (!Array.isArray(contract.capabilities) || !contract.capabilities.length) {
    failures.push({ file: statusRelativePath, reason: "capabilities must be a non-empty array" });
    return;
  }
  const capabilitiesById = new Map();
  for (const capability of contract.capabilities) {
    if (typeof capability.id === "string") {
      if (capabilitiesById.has(capability.id)) {
        failures.push({ file: statusRelativePath, capability: capability.id, reason: "duplicate capability id" });
      }
      capabilitiesById.set(capability.id, capability);
    }
  }
  for (const requiredId of requiredCapabilityIds) {
    if (!capabilitiesById.has(requiredId)) {
      failures.push({
        file: statusRelativePath,
        capability: requiredId,
        reason: `missing required capability id: ${requiredId}`,
      });
    }
  }
  for (const retiredId of retiredCapabilityIds) {
    if (capabilitiesById.has(retiredId)) {
      failures.push({
        file: statusRelativePath,
        capability: retiredId,
        reason: `retired capability id remains: ${retiredId}`,
      });
    }
  }
  const scannedText = claimScanFiles
    .filter((file) => existsSync(resolveRepo(file)))
    .map((file) => [file, readFileSync(resolveRepo(file), "utf8")]);
  for (const capability of contract.capabilities) {
    validateCapability(capability, scannedText);
  }
}

function validateCapability(capability, scannedText) {
  for (const key of ["id", "label", "status", "scope"]) {
    if (typeof capability[key] !== "string" || !capability[key].trim()) {
      failures.push({ file: statusRelativePath, capability: capability.id, reason: `${key} must be a non-empty string` });
    }
  }
  if (!allowedStatuses.has(capability.status)) {
    failures.push({ file: statusRelativePath, capability: capability.id, reason: `unsupported status: ${capability.status}` });
  }
  if (!Array.isArray(capability.evidence) || !capability.evidence.length) {
    failures.push({ file: statusRelativePath, capability: capability.id, reason: "evidence must be a non-empty array" });
  }
  if (["implemented", "partial"].includes(capability.status) && !codeOrTestEvidenceExemptions.has(capability.id)) {
    const evidence = Array.isArray(capability.evidence) ? capability.evidence : [];
    if (!evidence.some(isCodeOrTestEvidence)) {
      failures.push({
        file: statusRelativePath,
        capability: capability.id,
        reason: "implemented or partial capabilities must cite at least one code or test evidence file",
      });
    }
  }
  const prohibitedClaims = capability.prohibitedClaims ?? [];
  if (!Array.isArray(prohibitedClaims)) {
    failures.push({ file: statusRelativePath, capability: capability.id, reason: "prohibitedClaims must be an array" });
    return;
  }
  if (capability.status === "claim_blocked" && prohibitedClaims.length === 0) {
    failures.push({
      file: statusRelativePath,
      capability: capability.id,
      reason: "claim_blocked capabilities must list prohibitedClaims",
    });
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

function isCodeOrTestEvidence(evidence) {
  const relative = String(evidence || "")
    .split("::")[0]
    .replaceAll("\\", "/");
  if (!/^(python\/kbprep_worker\/|python\/tests\/|src\/|scripts\/checks\/)/.test(relative)) {
    return false;
  }
  return existsSync(resolveRepo(relative));
}

function resolveRepo(relativePath) {
  return path.join(repoRoot, relativePath);
}

function parseArgs(rawArgs) {
  const parsed = {};
  for (let index = 0; index < rawArgs.length; index += 1) {
    const arg = rawArgs[index];
    if (arg === "--repo-root") {
      parsed.repoRoot = rawArgs[++index];
    } else if (arg === "--status") {
      parsed.status = rawArgs[++index];
    }
  }
  return parsed;
}
