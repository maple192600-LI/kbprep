# KBPrep Completion Parallel Development Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish KBPrep from the current partial state to the protected design without overstating capabilities, while using parallel worktrees and reviewer subagents for speed and quality.

**Architecture:** Keep `main` as the integration branch and create one focused `codex/` branch per independent product slice. Parallel slices may run only when they do not edit the same contract files or promote the same capability status. Every slice must end with a reviewer pass, targeted checks, status-document alignment, and an integration check on the branch that will merge next.

**Tech Stack:** Node.js 22+, TypeScript, Vitest, TypeBox, Python 3.12 worker, unittest, ruff, mypy, KBPrep project commands only.

---

## Current Truth

Source of truth:

- `docs/development/kbprep-implementation-status.json`
- `docs/capability-matrix.md`
- `docs/development/development-roadmap.md`
- current code and project-environment tests

Current completion state:

- M1 is implemented.
- M2 / Phase C is partial.
- M3 / Phase D is implemented.
- M4 is implemented.
- Phase E / `job_status_envelope` is implemented.
- M5 is partial.
- M6 / Phase F is incomplete: local media is route-level `experimental`, YouTube is `design_only`, image OCR and legacy Office are `experimental`.

## Parallelization Rules

- Start every implementation slice from current `main` in a clean isolated worktree.
- Use branch names under `codex/`.
- Do not combine capability promotion with unrelated implementation.
- Do not let two branches edit the same status rows in `kbprep-implementation-status.json` or `docs/capability-matrix.md` at the same time.
- The branch merged second must rebase or fast-forward onto latest `main`, rerun affected checks, and rerun `npm run dev:check`.
- `npm run dev:full-check` is the final merge-readiness gate for runtime, route, quality gate, cleanup lifecycle, feedback promotion, publication, dependency, and release-level behavior.
- Reviewer subagents are mandatory before merging any branch that changes Canonical IR, conversion gates, feedback promotion, batch/rerun behavior, or optional route status.

## Worktree Setup Pattern

Run these steps for each slice:

- [ ] **Step 1: Confirm current state**

```powershell
git status --short --branch
git fetch --all --prune
git merge --ff-only origin/main
```

Expected: current `main` is not behind `origin/main`. If local uncommitted files exist, classify them before creating worktrees.

- [ ] **Step 2: Create focused worktree**

```powershell
git worktree add .worktrees/<slice-name> -b codex/<slice-name> main
```

Expected: new worktree exists at `.worktrees/<slice-name>` on branch `codex/<slice-name>`.

- [ ] **Step 3: Install and list verification command**

```powershell
cd .worktrees/<slice-name>
npm ci
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-kbprep.ps1 -List
```

Expected: dependencies install and the wrapper prints `npm run dev:check` for default verification.

## Subagent Role Contract

Use three roles for each non-trivial branch:

- `explorer`: read-only. Reads design docs, current code, tests, status files, and returns exact file/line evidence plus proposed slice boundary. No edits.
- `worker`: edits only files named in the slice. Uses TDD where behavior changes. Runs targeted checks before returning.
- `reviewer`: reviews the diff against the slice plan, checks overclaims, missing tests, contract drift, security/privacy risk, and verification gaps. Runs at least `git diff --check` and the slice's target tests.

Main agent responsibility:

- Verify subagent reports against current files and commands.
- Fix reviewer findings in the same branch before merge.
- Run final branch checks.
- Merge only after no Critical or Important reviewer findings remain.

## Wave 0: Close Current Documentation And Local Tail

Can run now in the current checkout because it only cleans status and planning residue.

**Files:**

- Modify: `.gitignore`
- Create: `SESSION_START.md`
- Create: `scripts/verify-kbprep.ps1`
- Modify: `docs/development/00-current-state-and-gap.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`
- Modify: `docs/known-issues.md`
- Modify: `docs/reports/kbprep-current-architecture.html`
- Modify: `scripts/checks/implementation-status.mjs`
- Modify: `src/test/scenarios/worker-governance-guards.test.ts`

- [ ] **Step 1: Keep `SESSION_START.md` tracked**

Ensure `.gitignore` contains:

```gitignore
!/SESSION_START.md
```

- [ ] **Step 2: Keep verification wrapper agent-neutral**

Ensure `SESSION_START.md` references:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-kbprep.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-kbprep.ps1 -Full
```

- [ ] **Step 3: Remove old agent-specific wrapper**

Run:

```powershell
Get-ChildItem scripts -Filter "verify-*.ps1" | Select-Object -ExpandProperty Name
```

Expected: `verify-kbprep.ps1`.

- [ ] **Step 4: Verify**

Run:

```powershell
node scripts/checks/implementation-status.mjs
npm run check:development-docs
npm run check:flowchart
npm run dev:check
npm run python:test
npm run python:ruff
npm run python:typecheck
git diff --check
```

Expected: all commands pass.

## Wave 1: M2 / Phase C Completion

Wave 1 is the highest priority. Phase D can stay implemented only because it uses the current Canonical IR artifacts; full project completion still requires M2 to close.

### Branch C1: Route-Native SourceSpan Precision

**Parallel:** Can run in parallel with C2 only if C1 owns `canonical_spans.py` route precision fields and C2 owns asset/relationship contracts. Avoid simultaneous edits to `canonical_coverage.py`.

**Branch:** `codex/c-route-native-spans`

**Files:**

- Modify: `python/kbprep_worker/canonical_spans.py`
- Modify: `python/kbprep_worker/canonical_ir.py`
- Modify: `python/kbprep_worker/canonical_coverage.py`
- Modify: `python/kbprep_worker/converters/office_xml.py`
- Modify: `python/kbprep_worker/pdf_text.py`
- Modify: `python/tests/test_canonical_ir_source_spans.py`
- Modify: `python/tests/test_canonical_ir_schema.py`
- Modify: `docs/development/02-canonical-ir-contract.md`

- [ ] **Step 1: Explorer evidence**

Explorer returns current SourceSpan schema, missing precision kinds, and tests that already cover converted line ranges and transcript cue timing.

- [ ] **Step 2: Worker adds failing tests**

Add tests that require:

```python
{"kind": "pdf_bbox", "page": 1, "bbox": [0.0, 0.0, 100.0, 20.0]}
{"kind": "docx_run_range", "paragraph_index": 0, "run_start": 0, "run_end": 2}
{"kind": "pptx_shape", "slide": 1, "shape_id": "title-1"}
{"kind": "xlsx_cell_range", "sheet": "Sheet1", "start": "A1", "end": "C3"}
```

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_source_spans python.tests.test_canonical_ir_schema -v
```

Expected before implementation: tests fail on unsupported precision kinds.

- [ ] **Step 3: Worker implements minimal schema and extraction**

Implement precision kinds only where the converter has evidence. If a converter cannot provide native evidence, record a precise gap in `coverage.report` instead of inventing positions.

- [ ] **Step 4: Verify branch**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_source_spans python.tests.test_canonical_ir_schema -v
npm run python:ruff
npm run python:typecheck
git diff --check
```

- [ ] **Step 5: Reviewer gate**

Reviewer checks that no route-native span is fabricated, no optional YouTube evidence is claimed before route support exists, and status remains partial unless all required evidence is present.

### Branch C2: Relationships, Assets, And Annotations

**Parallel:** Can run with C1 if it avoids `canonical_spans.py` and coordinates final `canonical_coverage.py` updates after C1 merges.

**Branch:** `codex/c-ir-relationships-assets`

**Files:**

- Create: `python/kbprep_worker/canonical_relationships.py`
- Create: `python/kbprep_worker/canonical_assets.py`
- Create: `python/kbprep_worker/canonical_annotations.py`
- Modify: `python/kbprep_worker/canonical_ir.py`
- Modify: `python/kbprep_worker/canonical_coverage.py`
- Create: `python/tests/test_canonical_ir_relationships.py`
- Create: `python/tests/test_canonical_ir_assets.py`
- Create: `python/tests/test_canonical_ir_annotations.py`
- Modify: `docs/development/02-canonical-ir-contract.md`

- [ ] **Step 1: Explorer evidence**

Explorer maps current image handling, link handling, figure nodes, table nodes, and metadata nodes.

- [ ] **Step 2: Worker adds failing tests**

Tests require:

```python
relationship = {"type": "contains", "from_node_id": "section-1", "to_node_id": "paragraph-1"}
asset = {"asset_id": "image-1", "kind": "image", "source_path": "images/a.png", "referenced_by": ["figure-1"]}
annotation = {"node_id": "paragraph-1", "kind": "quality_warning", "code": "W_LOW_COVERAGE"}
```

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_relationships python.tests.test_canonical_ir_assets python.tests.test_canonical_ir_annotations -v
```

Expected before implementation: tests fail because artifacts do not exist.

- [ ] **Step 3: Worker implements artifacts**

Write content-safe JSON artifacts under `canonical_ir/` and reference them from the manifest. Do not copy private source text into relationship, asset, or annotation records.

- [ ] **Step 4: Verify branch**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_relationships python.tests.test_canonical_ir_assets python.tests.test_canonical_ir_annotations -v
npm run python:ruff
npm run python:typecheck
git diff --check
```

- [ ] **Step 5: Reviewer gate**

Reviewer checks content safety, manifest consistency, and no status overpromotion.

### Branch C3: IR-Based Rendering And Conversion Gate Completion

**Parallel:** Must wait until C1 and C2 are merged.

**Branch:** `codex/c-ir-render-gate`

**Files:**

- Modify: `python/kbprep_worker/render_outputs.py`
- Modify: `python/kbprep_worker/quality/conversion_gate.py`
- Modify: `python/kbprep_worker/canonical_gate_evidence.py`
- Modify: `python/kbprep_worker/stages/pipeline_core.py`
- Modify: `python/tests/test_conversion_gate.py`
- Modify: `python/tests/test_clean_view.py`
- Modify: `python/tests/test_core_processing_paths.py`
- Modify: `docs/development/kbprep-implementation-status.json`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/capability-matrix.md`

- [ ] **Step 1: Worker adds failing tests**

Add tests proving cleaned Markdown can be rendered from Canonical IR plus accepted patches, and conversion gate blocks a route that claims complete IR coverage while missing required artifacts.

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_conversion_gate python.tests.test_clean_view python.tests.test_core_processing_paths -v
```

Expected before implementation: IR-regeneration and strict complete-IR gate tests fail.

- [ ] **Step 2: Worker implements minimal IR render path**

Use the assembled Clean View backed by Canonical IR artifacts. Keep existing fallback only for routes whose capability status remains partial or experimental.

- [ ] **Step 3: Promote status only if evidence is complete**

Change `canonical_ir_contract` and `conversion_quality_gate` from `partial` to `implemented` only when every required C1-C3 test passes and capability matrix claims remain honest.

- [ ] **Step 4: Verify branch**

Run:

```powershell
npm run dev:full-check
npm run check:development-docs
npm run check:flowchart
git diff --check
```

- [ ] **Step 5: Final reviewer gate**

Reviewer verifies M2 completion evidence, no fabricated source spans, no target-only YouTube claims, and no stale partial wording remains except for routes that truly remain partial or experimental.

## Wave 2: M5 Feedback And Selective Rerun

Wave 2 can start in parallel with C1/C2 for read-only exploration and proposal-state hardening. Executable rerun must wait until the Canonical IR ids and policy snapshot identity from Wave 1 are stable.

### Branch M5A: Feedback Proposal State Hardening

**Parallel:** Can run with C1 and C2.

**Branch:** `codex/m5-feedback-state`

**Files:**

- Modify: `python/kbprep_worker/feedback/proposals.py`
- Modify: `python/kbprep_worker/feedback/promotion_history.py`
- Modify: `python/tests/test_feedback_proposals.py`
- Modify: `python/tests/test_feedback_promotion.py`
- Modify: `docs/feedback-learning.md`
- Modify: `docs/development/09-feedback-rule-learning.md`

- [ ] **Step 1: Add failing tests**

Require proposal records to include `proposed`, `accepted`, `rejected`, `rerun_pending`, `rerun_passed`, `rerun_failed`, and `promotion_blocked` states.

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_feedback_proposals python.tests.test_feedback_promotion -v
```

Expected before implementation: missing states or transitions fail.

- [ ] **Step 2: Implement state transitions**

Keep one-sentence feedback proposal-first. Do not promote a permanent rule without owner confirmation, positive examples, counterexamples, and rerun evidence.

- [ ] **Step 3: Reviewer gate**

Reviewer checks that no broad deletion rule can be promoted from a single sentence.

### Branch M5B: Executable Selective Rerun

**Parallel:** Starts after C3 merges.

**Branch:** `codex/m5-selective-rerun`

**Files:**

- Modify: `python/kbprep_worker/feedback/rerun_verification.py`
- Modify: `python/kbprep_worker/feedback/command.py`
- Modify: `src/adapters/standalone/bin/feedback.ts`
- Modify: `src/test/scenarios/worker-feedback-rules-part1.test.ts`
- Modify: `src/test/scenarios/worker-feedback-rules-part2.test.ts`
- Modify: `python/tests/test_feedback.py`
- Modify: `docs/feedback-learning.md`
- Modify: `docs/standalone-cli.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [ ] **Step 1: Add failing CLI and Python tests**

Require `kbprep-feedback` to run an accepted proposal against only affected run ids, source ids, document type, and policy snapshot hash.

Run:

```powershell
npm test -- src/test/scenarios/worker-feedback-rules-part1.test.ts src/test/scenarios/worker-feedback-rules-part2.test.ts
node scripts/python-venv.mjs -m unittest python.tests.test_feedback -v
```

Expected before implementation: selective rerun command or evidence fails.

- [ ] **Step 2: Implement rerun command**

Use source evidence, Canonical IR ids, document type, and policy snapshot identity. Preserve failed promotion history when rerun evidence is weak.

- [ ] **Step 3: Promote M5 status only if complete**

Move `feedback_rule_learning` from `partial` only when proposal, acceptance, rejection, rerun, failed promotion, and operator docs all pass.

- [ ] **Step 4: Verify branch**

Run:

```powershell
npm run dev:full-check
git diff --check
```

## Wave 3: Batch, Playlist, And Rerun

Batch selective rerun can run after M5B. Playlist work must not start implementation until URL/network/copyright scope is approved and reflected in capability status.

### Branch BATCH1: Batch Selective Rerun

**Branch:** `codex/batch-selective-rerun`

**Files:**

- Modify: `python/kbprep_worker/batch_manifest.py`
- Modify: `python/kbprep_worker/prepare_batch.py`
- Modify: `python/tests/test_batch_status_manifest.py`
- Modify: `src/test/scenarios/worker-batch-long-docs-part1.test.ts`
- Modify: `src/test/scenarios/worker-batch-long-docs-part2.test.ts`
- Modify: `README.md`
- Modify: `docs/standalone-cli.md`
- Modify: `docs/development/10-batch-playlist-rerun.md`

- [ ] **Step 1: Add failing tests**

Require batch rerun scope to select failed, warning, skipped, or policy-affected children without rerunning unrelated successful children.

- [ ] **Step 2: Implement rerun scope**

Use `batch_manifest.json`, child run metadata, policy snapshot hash, and source hash. Do not rely on filename-only matching.

- [ ] **Step 3: Verify branch**

Run:

```powershell
npm test -- src/test/scenarios/worker-batch-long-docs-part1.test.ts src/test/scenarios/worker-batch-long-docs-part2.test.ts
node scripts/python-venv.mjs -m unittest python.tests.test_batch_status_manifest -v
npm run dev:check
git diff --check
```

### Branch PLAYLIST1: Playlist Scope Decision

**Branch:** `codex/playlist-scope-decision`

**Files:**

- Modify: `docs/development/10-batch-playlist-rerun.md`
- Modify: `docs/development/11-multimedia-youtube-optional.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/capability-matrix.md`

- [ ] **Step 1: Document owner-readable decision**

Choose one explicit state:

```text
playlist remains design_only and outside current release
```

or:

```text
playlist enters implementation scope with URL/network/copyright boundary and fixtures
```

- [ ] **Step 2: Run governance checks**

```powershell
npm run check:development-docs
npm run check:flowchart
git diff --check
```

Expected: docs are aligned and no playlist capability is overstated.

## Wave 4: M6 / Phase F Optional Routes

Wave 4 should run after M2 and M5 are stable. Local media fixture work can prepare in parallel, but capability promotion waits for real evidence.

### Branch F1: Local Media ASR Fixtures

**Branch:** `codex/f-local-media-fixtures`

**Files:**

- Modify: `python/kbprep_worker/converter_capabilities.py`
- Modify: `python/tests/golden/formats/manifest.json`
- Modify: `python/tests/test_golden_format_routes.py`
- Modify: `src/test/scenarios/worker-output-guards-part2.test.ts`
- Modify: `docs/capability-matrix.md`
- Modify: `docs/development/11-multimedia-youtube-optional.md`

- [ ] **Step 1: Add real or golden media fixture evidence**

Add fixture metadata with:

```json
{
  "real_fixture": true,
  "manual_acceptance_evidence": true,
  "promote_to_verified": false
}
```

Use `promote_to_verified: true` only after transcript quality and timing evidence pass.

- [ ] **Step 2: Add dependency failure and success tests**

Require clear errors for missing `ffmpeg` and `whisper`; require successful transcript text to enter quality gates and final outputs when dependencies are available.

- [ ] **Step 3: Promote status conservatively**

Change route status from `experimental` to `partial` or `verified` only when tests and fixtures justify it.

### Branch F2: Image OCR And Legacy Office Fixtures

**Branch:** `codex/f-external-format-fixtures`

**Files:**

- Modify: `python/kbprep_worker/converter_capabilities.py`
- Modify: `python/tests/golden/formats/manifest.json`
- Modify: `python/tests/test_golden_format_routes.py`
- Modify: `src/test/scenarios/worker-core-runtime-part2.test.ts`
- Modify: `docs/capability-matrix.md`

- [ ] **Step 1: Add real fixture evidence**

Add image OCR and legacy Office fixtures only when local dependencies are available and reproducible.

- [ ] **Step 2: Keep status honest**

If fixtures are mocked or dependency-only, keep status `experimental`.

### Branch F3: YouTube URL Route Boundary

**Branch:** `codex/f-youtube-boundary`

**Files:**

- Modify: `docs/development/11-multimedia-youtube-optional.md`
- Modify: `docs/capability-matrix.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/standalone-cli.md`

- [ ] **Step 1: Define boundary before code**

Document:

```text
Input: YouTube URL or video id
Preferred route: subtitle-first
Fallback route: media transcript only when dependencies are installed
Network behavior: explicit user-approved route, timeout, no hidden cost
Copyright behavior: user-provided or owner-approved content only
Failure mode: unsupported or dependency error before conversion
```

- [ ] **Step 2: Owner authorization gate**

Do not implement URL fetching, subtitle extraction, or media download until this boundary is explicitly accepted.

### Branch F4: YouTube Implementation

**Parallel:** Starts only after F3 is accepted.

**Branch:** `codex/f-youtube-route`

**Files:**

- Modify: `python/kbprep_worker/diagnose/format_detect.py`
- Modify: `python/kbprep_worker/converter_registry.py`
- Create: `python/kbprep_worker/converters/youtube.py`
- Create: `python/tests/test_youtube_converter.py`
- Modify: `src/adapters/standalone/cli.ts`
- Modify: `src/test/scenarios/worker-local-formats.test.ts`
- Modify: `docs/capability-matrix.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [ ] **Step 1: Add failing tests**

Require subtitle-first fixture, no-subtitle fallback, dependency failure, timeout failure, and no-network rejection.

- [ ] **Step 2: Implement subtitle-first route**

Do not download media unless fallback is explicitly enabled and dependencies are present.

- [ ] **Step 3: Verify branch**

Run:

```powershell
npm run dev:full-check
npm run check:development-docs
git diff --check
```

## Final Integration Sequence

Merge order:

1. Wave 0 cleanup.
2. C1 and C2 in either order, with second branch synchronized to latest `main`.
3. C3 after C1 and C2.
4. M5A.
5. M5B after C3.
6. BATCH1 after M5B.
7. PLAYLIST1 decision.
8. F1 and F2 fixture branches.
9. F3 YouTube boundary.
10. F4 YouTube implementation only after F3 is accepted.

Final release gate:

```powershell
npm run dev:full-check
npm run pack:check
npm run check:flowchart
npm run check:development-docs
git diff --check
```

External-quality routes also require real sample checks:

```powershell
npm run vault:pdf-phase-b
```

Add route-specific real sample commands for media, image OCR, legacy Office, and YouTube when those fixtures exist.

## Review And Fix Loop

Every branch follows this loop:

- [ ] Worker finishes target implementation and target tests.
- [ ] Reviewer subagent reviews branch diff and runs target tests.
- [ ] Worker fixes Critical and Important findings.
- [ ] Reviewer rechecks fixed files.
- [ ] Main agent runs branch verification.
- [ ] Branch updates status docs only if evidence supports promotion.
- [ ] Branch is merged only after checks and review pass.

Reviewer output format:

```text
APPROVED FINAL
```

or:

```text
CHANGES REQUIRED
- [Critical] file:line issue and required fix
- [Important] file:line issue and required fix
- [Minor] file:line issue and optional fix
```

Critical and Important findings block merge. Minor findings can be deferred only if they do not affect product correctness, status truth, privacy, security, or verification.

## Completion Definition

KBPrep is complete only when:

- `kbprep-implementation-status.json` has no unaccepted `partial`, `design_only`, or `claim_blocked` capability.
- `docs/capability-matrix.md` has no unaccepted `partial`, `experimental`, or `design_only` route.
- Any intentionally unsupported route is explicitly owner-accepted and documented as unsupported.
- `npm run dev:full-check` passes.
- Real sample checks pass for routes that depend on external tools or source quality.
- The maintained docs surface has no stale status wording.
