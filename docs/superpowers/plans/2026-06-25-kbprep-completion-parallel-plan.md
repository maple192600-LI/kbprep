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
- M2 / Phase C baseline is `implemented` (`canonical_ir_contract` and `conversion_quality_gate` = `implemented`: typed nodes, source spans, ledger, and content-safe relationship/asset/annotation artifacts are validated). The `prohibitedClaims` depth items remain open: converter-native SourceSpan precision emission, route-wide relationship/asset semantics breadth, richer annotations, full renderer/profile coverage, and universal fact-layer use.
- M3 / Phase D is implemented.
- M4 is implemented.
- Phase E / `job_status_envelope` is implemented.
- M5 `feedback_rule_learning` is `implemented` (proposal, accept, reject, public single-source selective rerun, run-level Canonical IR manifest binding, failed-promotion blocking). Canonical IR node-id or cleaning-unit id-level selective narrowing remains future work (`id_level_narrowing=false` is explicit in the binding payload).
- M6 / Phase F is not closed: local media and YouTube are implemented as `partial` optional routes, image OCR and legacy Office remain `experimental`, and MOBI stays explicitly `unsupported` unless the owner reopens that scope.

## Parallelization Rules

- Start every implementation slice from current `main` in a clean isolated worktree.
- Use branch names under `codex/`.
- Do not combine capability promotion with unrelated implementation.
- Do not let two branches edit the same status rows in `kbprep-implementation-status.json` or `docs/capability-matrix.md` at the same time.
- The branch merged second must rebase or fast-forward onto latest `main`, rerun affected checks, and rerun `npm run dev:check`.
- `npm run dev:full-check` is the final merge-readiness gate for runtime, route, quality gate, cleanup lifecycle, feedback promotion, publication, dependency, and release-level behavior.
- Reviewer subagents are mandatory before merging any branch that changes Canonical IR, conversion gates, feedback promotion, batch/rerun behavior, optional route behavior, or optional route status. Small documentation wording fixes only need main-agent review plus the relevant governance check.

## Second Review Speed Revision

The first version was too conservative in three places. Use this revised flow. The rule is: develop independent code paths in parallel, but promote capability status only after evidence is complete and integration checks pass.

- Do not split YouTube into a separate approval branch. The YouTube branch is a product-flow implementation branch: accepted URL/id/playlist inputs, subtitle inventory, no-subtitle fallback through a Python video/media download library, local transcription, cleanup, quality gates, source-side Obsidian Markdown output, clear errors, and status evidence.
- Do not make all M5 rerun work wait for C3. Run the existing command/state coverage as M5B2 preflight, then implement affected-scope identity binding immediately with current stable ids. Attach Canonical IR id-level narrowing later when those ids are complete.
- Do not make all Phase F work wait for M2 and M5. F1 local media fixtures, F2 image/legacy fixtures, and the YouTube technical-contract tests can start immediately. Only capability promotion waits for passing fixtures and final gate evidence.
- Do not run a full reviewer loop for every small doc-only adjustment. Keep reviewer subagents for contract boundaries and merge readiness; use targeted checks during implementation and reserve `npm run dev:full-check` for merge-ready branches.
- Do not leave playlist as a decision-only tail. Explicit playlist input is merged, and playlist rerun now preserves playlist `source_collection` plus child `source_url` evidence in `batch_rerun_manifest.json`. Remaining playlist-adjacent work is policy/CIR affected targeting plus real-network/dependency/quality evidence before any promotion.

Speed correction:

- Do not restart landed C2 artifact work, landed playlist implementation, or landed YouTube URL routing as fresh implementation branches. Convert those plan entries into evidence hardening, route-native extraction, real-sample verification, or status-promotion work.
- Start the next independent branches immediately when file ownership does not collide: C-native SourceSpan extraction, Canonical IR route-semantics hardening, M5 affected-scope identity binding prep, real media fixtures, image/legacy fixture evidence, and YouTube real-network/dependency/timeout evidence.
- Hold only final capability promotion and final project-complete status for complete evidence. Do not hold implementation, fixture creation, timeout handling, or reviewer checks behind unrelated M2 or M5 completion.
- Merge small, verified branches frequently. The second branch touching status docs must synchronize with latest `main` and rerun the affected checks before merge.

## Third Review: No Duplicate Implementation

This review removes overcautious slices that would waste time by rebuilding shipped work.

- **C1/C2/C3/C4/C5/C6 naming:** Typed nodes, SourceSpan artifacts, TransformationLedger, coverage reporting, complete typed-node/source-span gate evidence, minimal IR Markdown regeneration, and content-safe relationships/assets/annotations artifacts are already present in current status evidence. Remaining M2 work is not "create C2 artifacts"; it is converter-native precision extraction, route-wide relationship/asset semantics, richer annotations, full renderer/profile coverage, and universal fact-layer use.
- **M5A/M5B1:** Proposal state hardening, public single-source selective rerun planning/execution, proposal risk notes, owner confirmation status, counterexamples, and failed-promotion blocking already exist. Remaining M5 work is affected-scope identity binding: source ids, policy snapshot identity, document type, Canonical IR ids or cleaning-unit identity, and reliable rerun evidence.
- **Playlist:** Explicit playlist input and playlist rerun evidence preservation are merged. The next playlist branch is real-network/dependency/quality evidence plus optional capability promotion, not another playlist implementation branch.
- **YouTube:** Direct URL, explicit video id, local `.url` descriptor, subtitle-first route, explicit media fallback, and playlist input are implemented through the existing `youtube_source`, `youtube_playlist`, external conversion, and CLI descriptor path. The next YouTube branch must harden the full flow around real network samples, bounded timeout behavior, dependency variance, no-subtitle fallback through the `yt-dlp` Python package, cache/artifact behavior, transcript quality, cleanup, and source-side Obsidian Markdown output. Do not create a duplicate `converters/youtube.py` route unless current code evidence proves the existing architecture cannot support the required behavior.
- **Speed audit:** M5A and M5B1 are no longer standalone development branches. They are fast preflight checks inside M5B2. If the existing tests pass, proceed directly to affected-scope identity binding; do not create a review-only branch.
- **YouTube flow:** Implement and verify the complete local CLI chain: URL/video id/playlist input, subtitle inventory and download, Python-library video/media download when subtitles are unavailable, transcription, deterministic cleanup, quality evidence, final Obsidian Markdown publication, and rerun-visible artifacts. Keep status `partial` until real samples, dependency variance, timeout behavior, and transcript quality prove the route.

## Immediate Parallel Work Sets

Use these write sets to maximize speed without creating merge conflicts. Status
docs should be updated at the end of each branch only after evidence exists; if
two branches need the same status row, the second branch must synchronize with
latest `main` before editing it.

- **Set A: Canonical IR native precision emitters.** Owns
  `python/kbprep_worker/canonical_spans.py`,
  `python/tests/test_canonical_ir_source_spans.py`, and
  `python/tests/test_canonical_ir_coverage.py`. Goal: turn validator-only native
  precision into real converter-emitted evidence where available.
- **Set B: M5 affected-scope feedback rerun binding.** Owns
  `python/kbprep_worker/feedback/rerun_verification.py`,
  `python/kbprep_worker/feedback/selective_rerun_execution.py`,
  `python/tests/test_feedback.py`, and
  `src/test/scenarios/worker-feedback-rules-part2.test.ts`. Do not touch batch
  rerun files in this branch.
- **Set C: Batch policy/CIR affected rerun.** Owns
  `python/kbprep_worker/prepare_batch_rerun.py` and
  `python/tests/test_batch_status_manifest.py`. Avoid public CLI changes unless
  the branch intentionally exposes an `affected` scope.
- **Set D: YouTube and playlist real-evidence hardening.** Owns
  `python/tests/test_media_youtube_routes.py`,
  `src/adapters/standalone/cli.test.ts`,
  `src/test/scenarios/worker-core-runtime-part2.test.ts`, relevant golden
  fixture metadata, and route docs. It may touch `youtube_source.py`,
  `youtube_playlist.py`, or external conversion modules only to fix evidence,
  timeout, dependency, fallback, artifact, or quality gaps.

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

## Wave 0: Completed Documentation And Local Tail

Wave 0 is closed. Do not create another Wave 0 implementation branch unless a
new regression appears. Current repository evidence already has:

- `.gitignore` keeping `SESSION_START.md` trackable.
- `SESSION_START.md` with agent-neutral verification wrapper commands.
- `scripts/verify-kbprep.ps1` as the sole `verify-*.ps1` script.
- Development docs, known issues, architecture report, status governance, and
  worker governance tests aligned with the current status surface.

Future doc-only drift fixes should be handled as small governance branches with
`npm run check:development-docs`, `npm run check:flowchart`, `npm run dev:check`,
and `git diff --check`, not as a repeated Wave 0 implementation.

## Wave 1: M2 / Phase C Completion

Wave 1 is the highest priority. Phase D can stay implemented only because it uses the current Canonical IR artifacts; full project completion still requires M2 to close.

### Branch C1R: Converter-Native SourceSpan Extraction

**Parallel:** Can run in parallel with Canonical IR route-semantics hardening if it owns converter extraction and SourceSpan mapping only. Coordinate any final `canonical_coverage.py` wording after whichever branch merges first.

**Branch:** `codex/c-native-span-extraction`

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

Explorer returns current SourceSpan schema, existing precision validators, missing converter-emitted precision kinds, and tests that already cover converted line ranges and transcript cue timing.

- [ ] **Step 2: Worker adds failing tests**

Do not test merely that these precision kinds are accepted by schema; that is already landed. Add tests that require the relevant converter path to emit native evidence when the source artifact contains it:

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

Expected before implementation: tests fail because converters still report missing native precision kinds or fall back to converted Markdown line ranges.

- [ ] **Step 3: Worker implements minimal extraction**

Emit precision kinds only where the converter has evidence. If a converter cannot provide native evidence, record a precise gap in `coverage.report` instead of inventing positions.

- [ ] **Step 4: Verify branch**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_source_spans python.tests.test_canonical_ir_schema -v
npm run python:ruff
npm run python:typecheck
git diff --check
```

- [ ] **Step 5: Reviewer gate**

Reviewer checks that no route-native span is fabricated, no optional YouTube evidence is claimed before route support exists, and the `prohibitedClaims` depth items on `canonical_ir_contract` stay open unless all required native-span evidence is present (the baseline is already `implemented`; this branch closes depth, not the baseline).

### Branch C2R: Relationship, Asset, And Annotation Semantics

**Parallel:** Can run with C1R if it avoids `canonical_spans.py` and owns only route-wide semantics and fixture coverage for already-created relationship, asset, and annotation artifacts.

**Branch:** `codex/c-ir-semantics-hardening`

**Files:**

- Modify: `python/kbprep_worker/canonical_relationships.py`
- Modify: `python/kbprep_worker/canonical_assets.py`
- Modify: `python/kbprep_worker/canonical_annotations.py`
- Modify: `python/kbprep_worker/canonical_ir.py`
- Modify: `python/kbprep_worker/canonical_coverage.py`
- Modify: `python/tests/test_canonical_ir_relationships.py`
- Modify: `python/tests/test_canonical_ir_assets.py`
- Modify: `python/tests/test_canonical_ir_annotations.py`
- Modify: `docs/development/02-canonical-ir-contract.md`

- [ ] **Step 1: Explorer evidence**

Explorer maps current relationship, asset, and annotation artifact records, then identifies which route semantics are still shallow or missing.

- [ ] **Step 2: Worker adds failing tests**

Do not add tests that only prove artifact files exist; that is already landed. Add tests that require route-wide semantics, such as:

```python
relationship = {"type": "contains", "from_node_id": "section-1", "to_node_id": "paragraph-1"}
asset = {"asset_id": "image-1", "kind": "image", "source_path": "images/a.png", "referenced_by": ["figure-1"]}
annotation = {"node_id": "paragraph-1", "kind": "quality_warning", "code": "W_LOW_COVERAGE"}
```

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_relationships python.tests.test_canonical_ir_assets python.tests.test_canonical_ir_annotations -v
```

Expected before implementation: tests fail because existing artifacts do not yet prove all required route-wide semantics.

- [ ] **Step 3: Worker hardens semantics**

Keep the content-safe JSON artifact contract and manifest references. Expand only evidence-backed relationships, asset references, and annotations. Do not copy private source text into relationship, asset, or annotation records.

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

### Branch C7: Full IR Fact-Layer Closure

**Parallel:** Must wait until C1R and C2R merge because it closes the shared `prohibitedClaims` depth items on `canonical_ir_contract` and `conversion_quality_gate` (the status rows are already `implemented`; this branch closes depth, not status).

**Branch:** `codex/c-ir-fact-layer-closure`

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

Add tests proving every promoted route can use Canonical IR as the complete fact layer: route-native spans, relationships, assets, annotations, accepted changes, renderer/profile coverage, and conversion gate blocking when a route claims complete IR coverage while missing required artifacts.

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_conversion_gate python.tests.test_clean_view python.tests.test_core_processing_paths -v
```

Expected before implementation: full fact-layer coverage fails even though the narrow standard Markdown regeneration path already exists.

- [ ] **Step 2: Worker completes route-wide IR use**

Use the assembled Clean View and Canonical IR artifacts across the required output profiles and route cases. Keep existing fallback only for routes whose capability status remains partial or experimental.

- [ ] **Step 3: Close prohibitedClaims depth only if evidence is complete**

The baseline is already `implemented`; this step closes the `prohibitedClaims` depth items on `canonical_ir_contract` and `conversion_quality_gate` (converter-native spans, route-wide relationship/asset/annotation semantics, full renderer/profile coverage, and universal fact-layer use) only when every required C1R, C2R, and C7 test passes and capability matrix claims remain honest. Remove the closed items from `prohibitedClaims` and drop any residual `partial` wording for these two capabilities.

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

Proposal state hardening and public single-source selective rerun scaffolding are already in the current implementation evidence. Wave 2 now focuses on affected-scope identity binding and closing the id-level narrowing depth (`feedback_rule_learning` is already `implemented`; promotion is not the goal); do not rebuild proposal states or the public rerun command unless current tests prove a regression.

### M5 Preflight: Existing Feedback And Command Coverage

**No standalone branch.** Run this as the first step of M5B2. These checks are speed guards, not development slices. If they pass, start affected-scope binding immediately. Create a fix only when a command proves a real regression.

```powershell
npm test -- src/test/scenarios/worker-feedback-rules-part1.test.ts src/test/scenarios/worker-feedback-rules-part2.test.ts
node scripts/python-venv.mjs -m unittest python.tests.test_feedback_proposals python.tests.test_feedback_promotion -v
node scripts/python-venv.mjs -m unittest python.tests.test_feedback -v
```

### Branch M5B2: Affected-Scope Evidence Binding

**Parallel:** Starts now. Use existing stable run ids, source ids, document type, and policy snapshot identity immediately. Canonical IR id-level narrowing can attach later when C1R/C2R/C7 makes those ids complete; do not block the whole branch on final M2 closure.

**Branch:** `codex/m5-rerun-evidence-binding`

**Files:**

- Modify: `python/kbprep_worker/feedback/rerun_verification.py`
- Modify: `python/tests/test_feedback.py`
- Modify: `docs/feedback-learning.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [ ] **Step 1: Add failing affected-scope tests**

Require selective rerun to bind accepted proposals to affected run ids, source ids, document type, policy snapshot hash, and run-level Canonical IR manifest evidence when available. Keep node-id or cleaning-unit id-level narrowing explicit as unavailable until those identities are stable.

- [ ] **Step 2: Implement final binding**

Use current stable run/source/document/policy evidence plus Canonical IR manifest evidence for the baseline binding. Add stable Canonical IR node ids or cleaning-unit ids later to avoid document-wide reruns when the changed rule affects only a known source span or cleaning unit.

- [ ] **Step 3: Close M5 depth only if complete**

`feedback_rule_learning` is already `implemented` (proposal, accept, reject, public single-source selective rerun, run-level Canonical IR manifest binding, failed-promotion blocking). This step closes the remaining depth — Canonical IR node-id or cleaning-unit id-level selective narrowing (currently `id_level_narrowing=false`) — only when stable identity evidence and named tests exist, then removes that future-work caveat from the status scope.

- [ ] **Step 4: Verify branch**

Run:

```powershell
npm run dev:full-check
git diff --check
```

## Wave 3: Batch, Playlist, And Rerun

Batch selective rerun is merged. Explicit playlist input and playlist rerun evidence preservation are merged. Remaining Wave 3 work is policy/CIR affected batch targeting plus real playlist evidence for any promotion.

### Branch BATCH1: Batch Selective Rerun

**Branch:** `codex/batch-selective-rerun`

**Files:**

- Modify: `python/kbprep_worker/batch_manifest.py`
- Modify: `python/kbprep_worker/prepare_batch.py`
- Create: `python/kbprep_worker/prepare_batch_rerun.py`
- Modify: `python/tests/test_batch_status_manifest.py`
- Modify: `src/test/scenarios/worker-batch-long-docs-part1.test.ts`
- Modify: `src/test/scenarios/worker-batch-long-docs-part2.test.ts`
- Modify: `README.md`
- Modify: `docs/standalone-cli.md`
- Modify: `docs/development/10-batch-playlist-rerun.md`

- [x] **Step 1: Add failing tests**

Require batch rerun scope to select failed or pending children without rerunning unrelated successful children. Require source hashes in the parent manifest and require rerun to refuse missing or changed source files.

- [x] **Step 2: Implement rerun scope**

Use `batch_manifest.json`, child run metadata, command defaults, and source hash. Do not rely on filename-only matching.

- [x] **Step 3: Verify branch**

Run:

```powershell
npm test -- src/test/scenarios/worker-batch-long-docs-part1.test.ts src/test/scenarios/worker-batch-long-docs-part2.test.ts
node scripts/python-venv.mjs -m unittest python.tests.test_batch_status_manifest -v
npm run dev:check
git diff --check
```

### Branch BATCH2: Policy-Affected Batch Targeting

**Parallel:** Starts after M5B2 and the stable Canonical IR identity binding are merged.

**Branch:** `codex/batch-policy-affected-rerun`

**Files:**

- Modify: `python/kbprep_worker/prepare_batch_rerun.py`
- Modify: `python/kbprep_worker/feedback/rerun_verification.py`
- Modify: `python/tests/test_batch_status_manifest.py`
- Modify: `python/tests/test_feedback.py`
- Modify: `docs/development/10-batch-playlist-rerun.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [ ] **Step 1: Add failing policy-affected tests**

Require accepted-rule or policy snapshot changes to select only children whose run evidence matches the affected policy/source identity.

- [ ] **Step 2: Implement policy/CIR binding**

Use M5B2 evidence binding and Canonical IR ids when available. Keep failed/pending parent-manifest rerun working for older manifests.

- [ ] **Step 3: Verify branch**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_batch_status_manifest python.tests.test_feedback -v
npm run dev:check
git diff --check
```

### Branch PLAYLIST2: Real Playlist Evidence And Hardening

**Parallel:** Can run with F3 YouTube evidence work if write sets are coordinated. Do not rebuild playlist expansion or rerun evidence preservation; both are merged.

**Branch:** `codex/playlist-real-evidence`

**Files:**

- Modify: `docs/development/10-batch-playlist-rerun.md`
- Modify: `docs/development/11-multimedia-youtube-optional.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/capability-matrix.md`
- Modify: `python/kbprep_worker/youtube_source.py`
- Modify: `python/kbprep_worker/youtube_playlist.py`
- Modify: `python/kbprep_worker/prepare_batch.py`
- Modify: `python/kbprep_worker/prepare_batch_rerun.py`
- Modify: `python/kbprep_worker/batch_manifest.py`
- Modify: `python/tests/test_media_youtube_routes.py`
- Modify: `python/tests/test_batch_status_manifest.py`
- Modify: `src/adapters/standalone/cli.ts`
- Modify: `src/adapters/standalone/cli.test.ts`

- [ ] **Step 1: Add real evidence tests or fixtures**

Require real-network or recorded-equivalent playlist evidence for bounded expansion, dependency failures, timeout behavior, per-video parent status, and source-side publication outcomes.

- [ ] **Step 2: Harden only missing behavior**

Reuse the existing YouTube subtitle-first child route through generated local `.url` descriptors. Fix only real evidence gaps, timeout/dependency behavior, or artifact/status issues found by Step 1.

- [ ] **Step 3: Verify**

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_media_youtube_routes python.tests.test_batch_status_manifest -v
npm run check:development-docs
npm run check:flowchart
git diff --check
```

Expected: playlist implementation remains present and the remaining blocker is only real evidence or dependency quality, not missing core playlist code.

## Wave 4: M6 / Phase F Optional Routes

Wave 4 starts now in parallel with M2, M5, and batch work for fixture, dependency, and route-contract work. Capability promotion waits for real evidence, but implementation and tests do not need to wait for M2 or M5 unless they edit the same status row.

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

### Branch F3: YouTube Real Evidence And Route Hardening

**Parallel:** Can start now. Coordinate write sets with PLAYLIST2. Do not create a duplicate converter route unless current code evidence proves the existing `youtube_source` / external conversion path cannot support the requirement.

**Branch:** `codex/f-youtube-evidence-hardening`

**Progress:** Recorded-equivalent subtitle inventory/report-contract evidence is landed in this branch: successful subtitle runs preserve source URL, inventory evidence JSON, selected subtitle language, subtitle/transcript artifact paths, and sanitized command evidence. The route remains `partial`; no-subtitle recorded fixtures, dependency variance, broader timeout evidence, cache/artifact behavior, transcript-quality checks, and real-network/manual acceptance evidence still remain before verified promotion.

**Files:**

- Modify: `python/kbprep_worker/youtube_source.py`
- Modify: `python/kbprep_worker/youtube_playlist.py`
- Modify: `python/kbprep_worker/converters/external_tools.py`
- Modify: `python/kbprep_worker/stages/external_conversion.py`
- Modify: `python/tests/test_media_youtube_routes.py`
- Modify: `src/adapters/standalone/cli.ts`
- Modify: `src/adapters/standalone/cli.test.ts`
- Modify: `src/test/scenarios/worker-core-runtime-part2.test.ts`
- Modify: `python/tests/golden/formats/manifest.json`
- Modify: `docs/development/11-multimedia-youtube-optional.md`
- Modify: `docs/capability-matrix.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/standalone-cli.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [ ] **Step 1: Add failing evidence-hardening tests**

Require real-network or recorded-equivalent subtitle fixture evidence, no-subtitle fallback, dependency failure, bounded timeout failure, no-network rejection when network is disabled, cache/artifact behavior, transcript-quality checks, and source URL evidence in artifacts.

- [ ] **Step 2: Confirm the route contract**

Document:

```text
Input: YouTube URL or video id
Preferred route: subtitle-first
Fallback route: media transcript only when dependencies are installed
Network behavior: explicit CLI URL route, timeout, deterministic failure messages, no hidden cost
Artifact behavior: preserve source URL evidence, subtitle order, transcript text, dependency report, and route decision
Failure mode: unsupported or dependency error before conversion
```

- [ ] **Step 3: Harden the existing subtitle-first route**

Do not download media unless fallback is explicitly enabled and dependencies are present. Fix only missing timeout, dependency, fallback, artifact, quality, or status evidence behavior.

- [ ] **Step 4: Promote status only from evidence**

Move `youtube_url_routes` from `partial` toward `verified` only if CLI behavior, real fixtures, dependency failures, timeout handling, and quality gates pass.

- [ ] **Step 5: Verify branch**

Run:

```powershell
npm run dev:full-check
npm run check:development-docs
git diff --check
```

## Test Sample Sources

All Wave 4 (F1/F2/F3) + PLAYLIST2 real-sample evidence comes from the owner's local Obsidian vault — **do not ask the owner for samples** (confirmed 2026-06-27; this has been asked for redundantly in the past and is a known error). Sample inventory verified to exist.

**Location:** `F:\Obsidian-Vault` (owner's local vault; machine-local path — documents may reference it as a resource pointer, but **code must NOT hardcode it**; pass via input/config per the path-portability rule).

| Route | Sample type | Path / source |
|---|---|---|
| F1 media ASR (video) | mp4 | `F:\Obsidian-Vault\69cbf59e000000001a025299.mp4`, `F:\Obsidian-Vault\codex教程.mp4`, `F:\Obsidian-Vault\YouTube\` |
| F1 media ASR (audio) | mp3 | `F:\Obsidian-Vault\03-Resources\audio_3DlXq9nsQOE.mp3`, or extract from any video: `ffmpeg -i <video>.mp4 -vn -acodec libmp3lame <audio>.mp3` |
| F2 image OCR | png/jpg | `F:\Obsidian-Vault\image-*.png`, `F:\Obsidian-Vault\04-Archive\base64-docs\kbprep-output\runs\*\images\*.jpg` |
| F2 legacy Office | pptx/docx | `F:\Obsidian-Vault\03-Resources\财务的变革与重塑11.pptx`, `F:\Obsidian-Vault\03-Resources\财务知识库建设手册_v2.0.docx` |
| PDF real evidence | pdf | `F:\Obsidian-Vault\03-Resources\*.pdf` (AI 编程实战三卷书, Loop-Engineering 橙皮书, Claude Code 从入门到精通, 会计准则分录大全, etc.) |
| F3 YouTube real-network | video | `https://www.youtube.com/watch?v=CAQ2pfhoPcs` (owner-designated test video, 2026-06-27) |
| PLAYLIST2 playlist evidence | playlist | derive from `F:\Obsidian-Vault\YouTube\` or an owner-provided playlist URL |

**Audio extraction (F1):** the owner explicitly said "any video → ffmpeg extract → audio sample". Do not block F1 on missing audio files; extract from an existing video.

## Final Integration Sequence

Merge order:

1. Wave 0 is already closed; skip it unless a new regression is found.
2. C1R, C2R, M5B2, F1, F2, F3, and PLAYLIST2 may merge in the order they become reviewed and verified, as long as the branch merged later synchronizes with latest `main`.
3. C7 full IR fact-layer closure after C1R and C2R.
4. M5B2 Canonical IR id-level narrowing (closing the `feedback_rule_learning` depth caveat) after the required Canonical IR or cleaning-unit identity semantics are stable, if the baseline M5B2 branch could not already include it.
5. BATCH2 after baseline M5B2; policy/CIR targeting can add deeper Canonical IR id narrowing when those ids are stable.
7. Capability-status promotion branches after their implementation evidence exists.

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
