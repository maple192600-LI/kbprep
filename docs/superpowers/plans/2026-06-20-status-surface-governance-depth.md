# Status Surface And Governance Depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make KBPrep's owner-readable status surfaces accurately expose classification, local media, YouTube, and batch-manifest boundaries before more feature work starts.

**Architecture:** Keep the protected design documents unchanged. Treat `docs/development/kbprep-implementation-status.json` as the capability-status truth, `python/kbprep_worker/converter_capabilities.py` as the route-level code truth, and `docs/capability-matrix.md` as the reader-facing route summary. Strengthen governance so future docs cannot omit shipped/partial capabilities or cite prose-only evidence for implemented behavior.

**Tech Stack:** Node 22, Vitest, TypeScript governance scripts, Python unittest through `node scripts/python-venv.mjs`, KBPrep local Python worker modules.

---

## Current Progress Evidence

- Git baseline: `main...origin/main`, clean worktree before this plan was written.
- Baseline check: `npm run dev:check` passed on 2026-06-20 with 34 Vitest files and 215 tests passing.
- Current implemented status:
  - `design_source_alignment`: implemented.
  - `source_side_publish`: implemented.
  - `conversion_quality_gate`: partial.
  - `canonical_ir_contract`: partial.
  - `cleaning_policy_snapshot`: design_only.
  - `patch_clean_view`: design_only.
  - `feedback_rule_learning`: partial.
  - `batch_playlist_rerun`: partial.
- The previous combined optional-media status was design-only but too broad.
- Current route matrix:
  - 4 verified routes, 5 partial routes, 3 experimental routes, 1 unsupported route.
  - `media_local_transcript` already exists as an experimental route.
  - YouTube URL input has no explicit route row yet.
- Next task decision: execute Roadmap Phase A, because it prevents false completion claims before PDF routing, Canonical IR typed nodes, CleaningPolicySnapshot, CleaningPatch, and Clean View work.

## File Structure

- Modify: `src/test/scenarios/worker-governance-guards.test.ts`
  - Adds RED coverage proving implementation-status governance catches missing capabilities and prose-only evidence.
- Modify: `scripts/checks/implementation-status.mjs`
  - Adds repo-root parsing, required capability IDs, retired capability IDs, and code/test evidence enforcement.
- Modify: `docs/development/kbprep-implementation-status.json`
  - Adds `document_type_classification`, splits local media from YouTube, and links partial/implemented capabilities to code or tests.
- Modify: `python/kbprep_worker/converter_capabilities.py`
  - Adds an explicit target-only YouTube URL row for capability-matrix visibility.
- Modify: `docs/capability-matrix.md`
  - Adds `design_only` status wording and a YouTube row that cannot be mistaken for shipped support.
- Modify: `README.md`
  - Explains `batch_manifest.json` versus `kbprep_batch_manifest.json`.
- Modify: `docs/standalone-cli.md`
  - Gives the same operator-facing manifest distinction.
- Modify: `docs/development/development-roadmap.md`
  - Updates Phase A snapshot from "not listed" to "listed" and splits media/YouTube status.

Protected files not changed:

- `docs/kbprep-core-flow-design.md`
- `docs/kbprep-full-flowchart.html`
- `docs/flowchart/kbprep-flow.json`

## Forbidden Scope

- Do not implement YouTube download, subtitle extraction, URL fetching, or media download.
- Do not promote local media from `experimental` in `docs/capability-matrix.md`.
- Do not mark `canonical_ir_contract`, `conversion_quality_gate`, `cleaning_policy_snapshot`, or `patch_clean_view` as implemented.
- Do not edit protected design semantics.
- Do not create business logic for an AI agent host.
- Do not run direct system Python as evidence.

### Task 1: Add Governance RED Tests

**Files:**
- Modify: `src/test/scenarios/worker-governance-guards.test.ts`

- [x] **Step 1: Add implementation-status guard tests**

Append these tests inside the existing `describe("kbprep worker governance guards", () => { ... })` block:

```ts
  it("blocks implementation status files that omit required capability ids", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-implementation-status-required-"));
    try {
      const statusDir = path.join(root, "docs", "development");
      mkdirSync(statusDir, { recursive: true });
      writeFileSync(
        path.join(statusDir, "kbprep-implementation-status.json"),
        JSON.stringify({
          schema: "kbprep.implementation_status.v1",
          capabilities: [
            {
              id: "design_source_alignment",
              label: "Protected design and flowchart alignment",
              status: "implemented",
              scope: "Design sources are aligned.",
              evidence: ["docs/kbprep-core-flow-design.md", "scripts/checks/development-docs.mjs"],
              prohibitedClaims: [],
            },
          ],
        }, null, 2),
        "utf8",
      );

      const result = spawnSync(process.execPath, [
        "scripts/checks/implementation-status.mjs",
        "--repo-root",
        root,
      ], {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30_000,
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain("missing required capability id: document_type_classification");
      expect(result.stderr).toContain("missing required capability id: youtube_url_routes");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("requires implemented and partial status capabilities to cite code or test evidence", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-implementation-status-evidence-"));
    try {
      const statusDir = path.join(root, "docs", "development");
      mkdirSync(statusDir, { recursive: true });
      writeFileSync(
        path.join(statusDir, "kbprep-implementation-status.json"),
        JSON.stringify({
          schema: "kbprep.implementation_status.v1",
          capabilities: [
            statusCapability("design_source_alignment", "implemented", [
              "docs/kbprep-core-flow-design.md",
              "scripts/checks/development-docs.mjs",
            ]),
            statusCapability("source_side_publish", "implemented", [
              "README.md",
              "python/tests/test_publish_safety.py",
            ]),
            statusCapability("conversion_quality_gate", "partial", [
              "docs/development/04-conversion-quality-gate.md",
              "python/tests/test_conversion_gate.py",
            ]),
            statusCapability("canonical_ir_contract", "partial", [
              "docs/development/02-canonical-ir-contract.md",
              "python/tests/test_canonical_ir_manifest.py",
            ]),
            statusCapability("document_type_classification", "partial", [
              "docs/development/05-document-type-classification.md",
            ]),
            statusCapability("cleaning_policy_snapshot", "design_only", [
              "docs/development/06-cleaning-policy-library.md",
            ]),
            statusCapability("patch_clean_view", "design_only", [
              "docs/development/07-cleaning-unit-patch-clean-view.md",
            ]),
            statusCapability("feedback_rule_learning", "partial", [
              "docs/feedback-learning.md",
              "python/tests/test_feedback_proposals.py",
            ]),
            statusCapability("batch_playlist_rerun", "partial", [
              "python/tests/test_batch_status_manifest.py",
            ]),
            statusCapability("media_local_transcript", "partial", [
              "src/test/scenarios/worker-core-runtime-part2.test.ts",
            ]),
            statusCapability("youtube_url_routes", "design_only", [
              "docs/development/11-multimedia-youtube-optional.md",
            ]),
          ],
        }, null, 2),
        "utf8",
      );

      const result = spawnSync(process.execPath, [
        "scripts/checks/implementation-status.mjs",
        "--repo-root",
        root,
      ], {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30_000,
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain("implemented or partial capabilities must cite at least one code or test evidence file");
      expect(result.stderr).toContain("document_type_classification");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
```

Add this helper below the `describe` block:

```ts
function statusCapability(id: string, status: string, evidence: string[]) {
  return {
    id,
    label: id,
    status,
    scope: `${id} scope`,
    evidence,
    prohibitedClaims: status === "implemented" ? [] : [`${id} is fully implemented`],
  };
}
```

- [x] **Step 2: Run the RED tests**

Run:

```powershell
npm test -- src/test/scenarios/worker-governance-guards.test.ts
```

Expected: FAIL because `scripts/checks/implementation-status.mjs` currently ignores `--repo-root` and does not enforce required capability IDs or code/test evidence.

- [x] **Step 3: Commit the RED test**

```powershell
git add src/test/scenarios/worker-governance-guards.test.ts
git commit -m "test: cover implementation status governance gaps"
```

### Task 2: Implement Status Governance Guard

**Files:**
- Modify: `scripts/checks/implementation-status.mjs`

- [x] **Step 1: Replace the implementation-status script**

Replace `scripts/checks/implementation-status.mjs` with:

```js
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
      failures.push({ file: statusRelativePath, capability: requiredId, reason: `missing required capability id: ${requiredId}` });
    }
  }
  for (const retiredId of retiredCapabilityIds) {
    if (capabilitiesById.has(retiredId)) {
      failures.push({ file: statusRelativePath, capability: retiredId, reason: `retired capability id remains: ${retiredId}` });
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
    failures.push({ file: statusRelativePath, capability: capability.id, reason: "claim_blocked capabilities must list prohibitedClaims" });
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
  const relative = String(evidence || "").split("::")[0].replaceAll("\\", "/");
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
```

- [x] **Step 2: Run the target governance tests**

Run:

```powershell
npm test -- src/test/scenarios/worker-governance-guards.test.ts
```

Expected: FAIL on the real status JSON because `document_type_classification`, `media_local_transcript`, and `youtube_url_routes` are not yet represented correctly.

- [x] **Step 3: Commit the governance script**

```powershell
git add scripts/checks/implementation-status.mjs
git commit -m "chore: enforce implementation status coverage"
```

### Task 3: Update Implementation Status Truth

**Files:**
- Modify: `docs/development/kbprep-implementation-status.json`

- [x] **Step 1: Replace the status capabilities**

Replace the `capabilities` array with these entries. Keep `"schema": "kbprep.implementation_status.v1"` and update `"updated"` to the execution date.

```json
[
  {
    "id": "design_source_alignment",
    "label": "Protected design and flowchart alignment",
    "status": "implemented",
    "scope": "The protected Markdown design, HTML flowchart, JSON flowchart contract, and development docs describe the current target architecture.",
    "evidence": [
      "docs/kbprep-core-flow-design.md",
      "docs/kbprep-full-flowchart.html",
      "docs/flowchart/kbprep-flow.json",
      "scripts/checks/development-docs.mjs",
      "scripts/checks/flowchart-drift.mjs"
    ],
    "prohibitedClaims": []
  },
  {
    "id": "source_side_publish",
    "label": "Source-side standard deliverable",
    "status": "implemented",
    "scope": "The standard profile publishes source-side Markdown and assets when quality gates pass, preserves Markdown sources by using .cleaned.md, and records publish reports for published or blocked decisions.",
    "evidence": [
      "README.md",
      "docs/standalone-cli.md",
      "docs/quality-loop.md",
      "python/kbprep_worker/prepare_publish.py",
      "python/tests/test_publish_safety.py",
      "src/test/scenarios/worker-obsidian-output-part1.test.ts"
    ],
    "prohibitedClaims": []
  },
  {
    "id": "conversion_quality_gate",
    "label": "Conversion quality gate",
    "status": "partial",
    "scope": "Current code has conversion quality checks and manifest checks; the target gate must read complete Canonical IR typed-node and source-span evidence across every route.",
    "evidence": [
      "docs/development/04-conversion-quality-gate.md",
      "python/kbprep_worker/quality/conversion_gate.py",
      "python/tests/test_conversion_gate.py",
      "src/test/scenarios/worker-quality-gates-part1.test.ts"
    ],
    "prohibitedClaims": [
      "all conversion routes have complete Canonical IR gate coverage"
    ]
  },
  {
    "id": "canonical_ir_contract",
    "label": "Canonical IR contract",
    "status": "partial",
    "scope": "The worker emits a minimal partial Canonical IR manifest beside conversion artifacts; full typed nodes, source spans, and universal fact-layer usage are not shipped.",
    "evidence": [
      "docs/development/02-canonical-ir-contract.md",
      "python/kbprep_worker/canonical_ir.py",
      "python/tests/test_canonical_ir_manifest.py"
    ],
    "prohibitedClaims": [
      "Canonical IR is the complete shipped worker fact layer"
    ]
  },
  {
    "id": "document_type_classification",
    "label": "Document type classification",
    "status": "partial",
    "scope": "The worker writes document_classification.json with conservative policy-use gating; the full target ClassificationPack and DocumentTypeSnapshot contract is not complete.",
    "evidence": [
      "docs/development/05-document-type-classification.md",
      "python/kbprep_worker/document_type.py",
      "python/tests/test_document_classification.py"
    ],
    "prohibitedClaims": [
      "DocumentTypeSnapshot is the complete shipped classification contract"
    ]
  },
  {
    "id": "cleaning_policy_snapshot",
    "label": "CleaningPolicySnapshot",
    "status": "design_only",
    "scope": "The reproducibility boundary is defined, but full snapshot compilation is not yet the shipped cleanup contract.",
    "evidence": [
      "docs/development/06-cleaning-policy-library.md"
    ],
    "prohibitedClaims": [
      "CleaningPolicySnapshot fully reproduces every shipped cleanup run"
    ]
  },
  {
    "id": "patch_clean_view",
    "label": "CleaningPatch and Clean View",
    "status": "design_only",
    "scope": "The target patch and Clean View model is defined, but current cleanup artifacts have not fully moved to that contract.",
    "evidence": [
      "docs/development/07-cleaning-unit-patch-clean-view.md"
    ],
    "prohibitedClaims": [
      "every shipped cleanup change is a guarded CleaningPatch"
    ]
  },
  {
    "id": "feedback_rule_learning",
    "label": "Proposal-first feedback learning",
    "status": "partial",
    "scope": "Feedback proposals, acceptance, rejection, rerun evidence, proposal risk notes, and explicit owner confirmation status exist; the target design keeps this proposal-first model.",
    "evidence": [
      "docs/feedback-learning.md",
      "docs/development/09-feedback-rule-learning.md",
      "python/kbprep_worker/feedback/proposals.py",
      "python/tests/test_feedback_proposals.py",
      "src/test/scenarios/worker-feedback-proposals-part1.test.ts"
    ],
    "prohibitedClaims": [
      "feedback learning proves every promoted rule against all future sources"
    ]
  },
  {
    "id": "batch_playlist_rerun",
    "label": "Batch, Playlist, and rerun",
    "status": "partial",
    "scope": "Batch behavior exists for local sources and writes a parent status manifest with evidence-backed rerun scope; Playlist and executable selective rerun still require additional implementation and evidence.",
    "evidence": [
      "docs/development/10-batch-playlist-rerun.md",
      "python/kbprep_worker/batch_manifest.py",
      "python/tests/test_batch_status_manifest.py"
    ],
    "prohibitedClaims": [
      "Playlist processing is a verified shipped capability"
    ]
  },
  {
    "id": "media_local_transcript",
    "label": "Local media transcript route",
    "status": "partial",
    "scope": "Local audio/video detection and external transcript routing are declared, and dependency failures are surfaced; route-level status remains experimental until real ASR fixtures prove quality.",
    "evidence": [
      "docs/development/11-multimedia-youtube-optional.md",
      "docs/capability-matrix.md",
      "python/kbprep_worker/converter_capabilities.py",
      "src/test/scenarios/worker-core-runtime-part2.test.ts",
      "src/test/scenarios/worker-output-guards-part2.test.ts",
      "python/tests/golden/formats/manifest.json"
    ],
    "prohibitedClaims": [
      "local media transcript route is verified"
    ]
  },
  {
    "id": "youtube_url_routes",
    "label": "YouTube URL route",
    "status": "design_only",
    "scope": "YouTube URL processing is a target optional route only; no standalone CLI URL input, subtitle extraction, media download, or verified fixture support is shipped.",
    "evidence": [
      "docs/development/11-multimedia-youtube-optional.md",
      "docs/capability-matrix.md"
    ],
    "prohibitedClaims": [
      "YouTube input is a verified standalone CLI capability"
    ]
  }
]
```

- [x] **Step 2: Run implementation-status check**

Run:

```powershell
node scripts/checks/implementation-status.mjs
```

Expected: PASS for required IDs and evidence. If it fails, fix only the status JSON or the evidence rule that caused the failure.

- [x] **Step 3: Commit the status truth update**

```powershell
git add docs/development/kbprep-implementation-status.json
git commit -m "docs: expose status capabilities accurately"
```

### Task 4: Add YouTube As Target-Only Route Visibility

**Files:**
- Modify: `python/kbprep_worker/converter_capabilities.py`
- Modify: `docs/capability-matrix.md`

- [x] **Step 1: Extend converter capability statuses**

In `python/kbprep_worker/converter_capabilities.py`, update `capability_gap_report()` summary:

```python
summary = {"verified": 0, "partial": 0, "unsupported": 0, "experimental": 0, "design_only": 0}
```

Update `_default_promotion_blocker`:

```python
def _default_promotion_blocker(capability: Capability) -> str:
    status = capability.get("status")
    if status == "partial":
        return "Needs broader golden fixtures and preservation checks before being marked verified."
    if status == "design_only":
        return "Target-only until a reliable route, dependency boundary, and end-to-end fixtures exist."
    return "Unsupported until a reliable conversion route and end-to-end fixtures exist."
```

Update `_default_required_evidence`:

```python
def _default_required_evidence(capability: Capability) -> list[str]:
    status = capability.get("status")
    if status == "partial":
        return ["golden fixtures", "source-to-Markdown preservation checks"]
    if status == "design_only":
        return ["owner-approved route design", "subtitle-first fixtures", "dependency failure tests"]
    return ["explicit dependency/conversion route", "end-to-end fixture proving safe Markdown output"]
```

- [x] **Step 2: Add the YouTube capability row**

Add this capability after `media_local_transcript` and before `mobi_unsupported`:

```python
    {
        "id": "youtube_url_routes",
        "source_type": "remote_url",
        "extensions": [],
        "route": "unsupported",
        "dependencies": ["target-only: subtitle fetcher", "target-only: media transcript fallback"],
        "fallback": "Download or export a local subtitle, transcript, Markdown, text, PDF, or media file before running KBPrep.",
        "status": "design_only",
        "test_evidence": [],
        "required_evidence": [
            "owner-approved YouTube URL input contract",
            "subtitle-first golden fixtures",
            "fallback transcript fixtures",
            "dependency failure and no-network tests",
        ],
        "promotion_blocker": "No standalone CLI URL route, subtitle extraction, media download, or verified fixture support is shipped.",
        "preserves": ["target: subtitle order", "target: transcript text", "target: source URL evidence"],
        "risk": "URL processing can create network, copyright, dependency, and quality risks; it stays target-only.",
    },
```

- [x] **Step 3: Update the matrix status vocabulary**

In `docs/capability-matrix.md`, update the status list to include:

```markdown
- `design_only`: target route is documented, but no current local CLI support is shipped
```

- [x] **Step 4: Add the matrix row**

Add this row before `mobi_unsupported`:

```markdown
| youtube_url_routes | YouTube URLs | unsupported | design_only | target: subtitle order, transcript text, source URL evidence | none | URL processing can create network, copyright, dependency, and quality risks; it stays target-only until the owner approves the route and fixtures prove it. |
```

- [x] **Step 5: Run capability matrix checks**

Run:

```powershell
node scripts/checks/capability-matrix.mjs
node scripts/python-venv.mjs -m unittest discover -s python/tests -p test_golden_format_routes.py -v
```

Expected: PASS. The matrix check should report 14 capabilities and include `design_only` in `gapSummary`.

- [x] **Step 6: Commit route visibility**

```powershell
git add python/kbprep_worker/converter_capabilities.py docs/capability-matrix.md
git commit -m "docs: show youtube as target-only route"
```

### Task 5: Align Reader-Facing Docs And Roadmap

**Files:**
- Modify: `README.md`
- Modify: `docs/standalone-cli.md`
- Modify: `docs/development/development-roadmap.md`

- [x] **Step 1: Clarify batch manifest names in README**

Replace the current README batch manifest sentence with:

```markdown
Batch runs write `batch_manifest.json` with parent status, per-file status, skipped unsupported files, and evidence-backed rerun scope. This is the live batch status summary. After a batch output root is finalized with `kbprep-cleanup --action finalize`, cleanup writes `kbprep_batch_manifest.json`; that file is only the retention manifest proving final deliverables were preserved before temporary process artifacts were removed.
```

- [x] **Step 2: Clarify batch manifest names in standalone CLI docs**

Replace the current `docs/standalone-cli.md` batch manifest paragraph with:

```markdown
Batch runs write `batch_manifest.json` beside `results.json`, `progress.json`, and `failures.json`. Use `batch_manifest.json` to see parent status, per-file status, skipped unsupported files, and the evidence-backed rerun scope. Batch cleanup finalization writes a different file, `kbprep_batch_manifest.json`, after preserving final deliverables; use it only as cleanup-retention proof, not as the live batch run list.
```

- [x] **Step 3: Update the roadmap current snapshot**

In `docs/development/development-roadmap.md`, update the document classification
snapshot row to:

```markdown
| document_type_classification | partial | Code writes `document_classification.json`; status JSON lists it as its own capability with code and test evidence. |
```

Replace the old combined media/YouTube snapshot row with:

```markdown
| media_local_transcript | partial status surface; experimental route matrix | Local media detection and failure reporting exist; real ASR fixtures are still required before route promotion. |
| youtube_url_routes | design_only | YouTube is visible as a target-only matrix row; no URL input route is shipped. |
```

- [x] **Step 4: Update Phase A wording**

Replace the Phase A slices list with:

```markdown
- **A1** Add `document_type_classification` as its own capability in
  `kbprep-implementation-status.json` (partial), with evidence pointing at the
  classification code and tests.
- **A2** Keep `media_local_transcript` and `youtube_url_routes` separate in
  the status JSON.
- **A3** Add an explicit target-only YouTube row in `capability-matrix.md`
  while keeping the route unsupported/design-only until evidence exists.
- **A4** Strengthen governance: `implementation-status.mjs` checks required
  capability coverage and requires implemented/partial status evidence to
  reference code or tests.
- **A5** Document the two batch manifest names (`batch_manifest.json` run list
  vs `kbprep_batch_manifest.json` cleanup retention) in README and
  `docs/standalone-cli.md`.
```

- [x] **Step 5: Run drift searches**

Run:

```powershell
rg -n "media_youtube_optional_routes|partial \\(not listed\\)|YouTube has no matrix row yet|batch_manifest\\.json.*kbprep_batch_manifest\\.json" docs README.md scripts src python --glob "!docs/superpowers/plans/2026-06-20-status-surface-governance-depth.md"
```

Expected:

- No `media_youtube_optional_routes` outside the retired-ID guard in `scripts/checks/implementation-status.mjs`.
- No `partial (not listed)`.
- No `YouTube has no matrix row yet`.
- Any `batch_manifest.json` / `kbprep_batch_manifest.json` hit must be the new explicit distinction, not confused naming.

- [x] **Step 6: Commit reader-facing docs**

```powershell
git add README.md docs/standalone-cli.md docs/development/development-roadmap.md
git commit -m "docs: align phase a status guidance"
```

### Task 6: Full Verification And Closeout

**Files:**
- Inspect all changed files and repository status.

- [x] **Step 1: Run target checks**

```powershell
npm test -- src/test/scenarios/worker-governance-guards.test.ts
node scripts/checks/implementation-status.mjs
node scripts/checks/capability-matrix.mjs
node scripts/checks/development-docs.mjs
```

Expected: all PASS.

- [x] **Step 2: Run project checks**

```powershell
npm run dev:check
npm run python:ruff
npm run python:typecheck
git diff --check
```

Expected: all PASS. `npm run dev:check` must include `npm test`.

- [x] **Step 3: Check file sizes**

```powershell
npm run python:check-size
```

Expected: PASS with no new Python file over 800 lines and no Python function over 50 lines.

- [x] **Step 4: Review status claims**

Run:

```powershell
rg -n "Canonical IR is the complete shipped worker fact layer|all conversion routes have complete Canonical IR gate coverage|CleaningPolicySnapshot fully reproduces every shipped cleanup run|every shipped cleanup change is a guarded CleaningPatch|YouTube input is a verified standalone CLI capability|local media transcript route is verified" docs README.md AGENTS.md scripts src python
```

Expected: no hits outside `prohibitedClaims` arrays or this plan file.

- [x] **Step 5: Commit verification updates if checks required changes**

If verification required edits, stage only the task-owned files:

```powershell
git add src/test/scenarios/worker-governance-guards.test.ts scripts/checks/implementation-status.mjs docs/development/kbprep-implementation-status.json python/kbprep_worker/converter_capabilities.py docs/capability-matrix.md README.md docs/standalone-cli.md docs/development/development-roadmap.md
git commit -m "fix: close status governance verification"
```

- [x] **Step 6: Push the branch**

```powershell
git status --short --branch
git push
```

Expected: branch pushes cleanly. Do not merge or release.

## Acceptance Checklist

- `document_type_classification` appears in implementation status with partial status and code/test evidence.
- The old combined optional-media status ID is gone from implementation status.
- `media_local_transcript` and `youtube_url_routes` are separate status capabilities.
- `docs/capability-matrix.md` has an explicit YouTube row that is target-only and not shipped.
- `scripts/checks/implementation-status.mjs` fails when required capabilities are missing.
- `scripts/checks/implementation-status.mjs` fails when implemented/partial capabilities cite only prose docs.
- README and standalone CLI docs distinguish `batch_manifest.json` from `kbprep_batch_manifest.json`.
- `npm run dev:check`, `npm run python:ruff`, `npm run python:typecheck`, and `git diff --check` pass.

## Self-Review

- Spec coverage: all Phase A slices A1-A5 from `docs/development/development-roadmap.md` are covered by Tasks 1-5.
- Placeholder scan: no `TBD`, `TODO`, `implement later`, or "similar to" instructions are used as work steps.
- Type consistency: `document_type_classification`, `media_local_transcript`, and `youtube_url_routes` use the same IDs across status JSON, governance checks, roadmap, and capability matrix.
- Risk boundary: YouTube remains target-only; no URL route, dependency, network behavior, or cost is introduced.
