# KBPrep Development Roadmap

## Purpose

This document is the single connected path from the current implementation
state to the completed target design defined in `docs/kbprep-core-flow-design.md`.

The protected design, the implementation plan (M1–M6), the stage documents
(00–12), `kbprep-implementation-status.json`, `capability-matrix.md`, and the
problem list are the ingredients. This roadmap is the assembly order: what to
do first, second, third, until the protected design is fully shipped.

This roadmap does not override the protected design. It sequences the work and
binds each phase to the existing contracts and acceptance gates.

## Flowchart Mapping

This roadmap covers every flowchart stage from input inspection to atomic
source-side publication and the feedback proposal path.

## Current Progress Snapshot

Source of truth: `docs/development/kbprep-implementation-status.json` and
`docs/capability-matrix.md`.

| Capability | Current status | Notes |
| --- | --- | --- |
| design_source_alignment | implemented | Protected design, flowchart, and dev docs aligned. |
| source_side_publish | implemented | Standard profile publishes source-side Markdown + assets; failure keeps prior output. |
| conversion_quality_gate | implemented | Gate validates manifest, typed-node, source-span, transformation-ledger, and coverage-report evidence, reads complete route-wide IR semantics (relationships/assets/annotations) when the manifest declares them available, and uses complete typed-node/source-span text quality when coverage is complete. YouTube/media/image optional routes stay partial (Wave 4); route-wide semantics, renderer/profile coverage, and universal fact-layer depth stay open in `prohibitedClaims`. |
| canonical_ir_contract | implemented | Manifest plus typed_nodes/source_spans/transformation_ledger/relationships/assets/annotations artifacts, route-native precision (PDF bbox via MinerU content_list, DOCX run range, PPTX shape id, XLSX cell range) when converters provide evidence, C2 content-safe route-wide semantics, coverage reports listing missing native precision kinds without fabricating, and pre-clean gate consuming complete IR when coverage is complete. YouTube/media/image optional routes stay partial (Wave 4); converter-native span breadth, full Markdown renderer/profile coverage, and universal fact-layer usage stay open as `prohibitedClaims` depth. |
| document_type_classification | partial | Code writes `document_classification.json`; status JSON lists it as its own capability with code and test evidence. |
| cleaning_policy_snapshot | implemented | Worker records the compiled policy contract with active rule ids, dictionary ids, protection ids, disabled rule ids, conflict resolutions, preference selectors, section hashes, filtered accepted-rule fingerprints, and run metadata references. |
| patch_clean_view | implemented | CleaningPatch generation writes `cleaning_patches.jsonl`; patch rejection gates write `cleaning_patch_gate.json` and `rejected_patches.jsonl`; Clean View assembly writes `clean_view.json`; DocumentCleaningGate writes `document_cleaning_gate.json` and turns rejected patch evidence into warnings without blocking safe output. |
| job_status_envelope | implemented | Phase E is landed: single-source and worker envelopes carry `completed`, `completed_with_warnings`, or `failed` status, with Python and TypeScript contract tests. |
| feedback_rule_learning | implemented | Proposal-first model, public single-source selective rerun execution, and run-level Canonical IR manifest binding (document_id, source, document type, policy snapshot hash); Canonical IR node-id or cleaning-unit id-level narrowing remains future work (run-level binding ships now). |
| batch_playlist_rerun | partial | Batch + parent status manifest, failed/pending batch rerun, explicit YouTube playlist input, and playlist rerun evidence preservation exist; worker-level policy_affected rerun filters children by run-evidence identity, while Canonical IR id-level (node-id) narrowing and CLI exposure still need implementation and evidence. |
| pdf_three_tier_routing | verified | B2-B4 routing is implemented: Tier 1 uses `pymupdf4llm`, Tier 2 uses MinerU `txt` or `auto`, and Tier 3 uses MinerU `ocr`; real Vault smoke now covers the six Phase B acceptance classes and rejects suspicious Tier 1 zero-hit distributions. |
| media_local_transcript | partial | Local media detection, dependency failure reporting (ffmpeg/whisper), command evidence, and mocked golden transcript fixtures exist; real ASR dual-track manual acceptance evidence recorded (zh fixture via qwen3-asr + en fixture via Whisper, transcript enters cleanup + final outputs, quality gates pass); verified promotion still needs a reproducible version-controlled fixture. |
| youtube_url_routes | partial | Direct YouTube URLs, explicit video ids, and local `.url` descriptors route subtitle-first; successful subtitle reports preserve source URL, recorded-equivalent inventory evidence, selected language, subtitle/transcript artifact paths, and sanitized command evidence. Media fallback is explicit, downloads video/media through the `yt-dlp` Python package, and is covered with mocked fixtures. Real-network breadth, timeout behavior, dependency variance, and transcript-quality evidence are not verified. |

## Guiding Principles

1. Status truth comes from `kbprep-implementation-status.json` and
   `capability-matrix.md`, never from prose in other docs.
2. Each slice ships as a TDD cycle with explicit acceptance commands.
3. No target-only capability is claimed shipped until named tests or fixtures
   prove it.
4. Each completed slice updates `kbprep-implementation-status.json`,
   `capability-matrix.md`, and the relevant stage doc in the same turn
   (per `docs/development/README.md`).
5. Protected design edits require `KBPREP_ALLOW_CORE_DOC_EDIT=1` and stay
   aligned with the flowchart contract.

## Phases

### Phase A — Status Surface And Governance Depth

Status: completed. This phase made the status surface report the real
capability boundary and made governance checks catch missing coverage. It
should not be restarted as a future implementation phase unless a new drift
regression appears.

Slices:

- **A1** Landed: `document_type_classification` is its own capability in
  `kbprep-implementation-status.json` (partial), with evidence pointing at the
  classification code and tests.
- **A2** Landed: `media_local_transcript` and `youtube_url_routes` are separate in
  the status JSON.
- **A3** Landed: YouTube is represented in `capability-matrix.md` as a
  partial optional route with named current evidence and promotion blockers.
- **A4** Landed: `implementation-status.mjs` checks required
  capability coverage and requires implemented/partial status evidence to
  reference code or tests.
- **A5** Landed: the two batch manifest names (`batch_manifest.json` run list
  vs `kbprep_batch_manifest.json` cleanup retention) in README and
  `docs/standalone-cli.md`.

Acceptance now means keeping those surfaces aligned during later work:
`npm run check:development-docs`, `npm run check:flowchart`, and
`npm run dev:check` must pass after status or planning changes.

### Phase B — PDF Three-Tier Routing

Contract: protected design §5 and `docs/development/03-deterministic-conversion-routing.md`.
The three-tier design is already defined at the design source (landed this cycle). This phase implements those tiers and keeps the PDF capability partial until real sample evidence supports promotion.

Slices:

- **B1** Landed: diagnostic evidence now records multi-column, table,
  image/text interleaving, CID/ToUnicode risk, image coverage ratio,
  large-PDF sampling, recommended PDF tier, recommended route, and reason.
- **B2** Landed: Tier 1 `pymupdf4llm` handles trusted text layer + simple
  layout.
- **B3** Landed: Tier 2 selects `mineru_txt` or `mineru_auto` for trusted text
  layer + complex layout.
- **B4** Landed: Tier 3 `mineru_ocr` is selected from untrusted text-layer
  evidence and one-upgrade fallback records its reason.
- **B5** Landed: the six public acceptance shapes pass, real Vault smoke covers
  `simple_single_column`, `english_simple_text`, `multi_column_paper`,
  `table_heavy`, `scanned`, and `cid_or_tounicode_damaged`, and the smoke check
  now reports tier/route distribution so zero-hit Tier 1 regressions fail as
  diagnosis problems instead of being mislabeled as missing samples.

Acceptance: `conversion_report.json.route_decision` records selected tier,
actual route, fallback or upgrade, and reason for every PDF; public route-shape
tests pass; `pdf_diagnosis_selected` is verified by named tests and real Vault
smoke distribution evidence.

### Phase C — Canonical IR Typed Nodes And Source Spans

Contract: `docs/development/02-canonical-ir-contract.md` and protected design
§6. Milestone M2. Goal: Canonical IR becomes the internal fact layer, not just
a metadata manifest.

Slices:

- **C1** Landed first slice: `TypedNode` schema and builder for heading,
  paragraph, list, table, code, and quote, with a validated
  `canonical_ir/typed_nodes.json` artifact.
- **C1b-1** Landed: formula, figure, and metadata typed-node coverage
  for converted Markdown.
- **C1b-2** Landed: transcript cue typed-node coverage for transcript
  contexts, using raw cue-text matching when available and speaker metadata
  when detectable.
- **C2** Landed base SourceSpan artifact: one validated span per typed node,
  strict evidence schema validation, converted Markdown line ranges for every
  node, and transcript timing when source cues provide it.
- **C2b** Landed first route-native precision guardrail: SourceSpan validation
  now accepts PDF bbox, DOCX run-range, PPTX shape-id, XLSX cell-range, and
  future YouTube cue-id precision only when required native fields are present.
  Coverage reports list the missing native precision kinds instead of
  fabricating converter evidence. Converter-native extraction remains required
  before Phase C can be considered fully implemented.
- **C3** Landed: `TransformationLedger` append-only record for conversion-phase Canonical IR evidence, referenced by the manifest and validated by the pre-clean conversion gate when claimed.
- **C4** Landed: complete coverage reporting keeps `typed_nodes_available`,
  `source_spans_available`, and `transformation_ledger_available` tied to
  validated artifacts, and embeds `coverage.report` with counts, ratios,
  precision summaries, and remaining target gaps.
- **C5** Landed: the pre-clean conversion quality gate prefers complete
  typed-node and source-span Canonical IR text evidence when `coverage.report`
  proves full node/span coverage, and falls back to converter-provided quality
  or rendered Markdown only when complete IR evidence is unavailable.
- **C6** Landed narrow slice: standard Markdown rendering can regenerate
  `cleaned.md` from Canonical IR typed-node text plus Clean View accepted
  change identity. Accepted patch entries still render from accepted in-memory
  cleanup block content, while `cleaning_patches.jsonl` remains content-safe
  and does not carry source or cleaned text.

Phase C baseline is implemented: typed nodes, source spans, the transformation
ledger, and content-safe relationship/asset/annotation artifacts are validated
with named evidence, so `canonical_ir_contract` and `conversion_quality_gate`
are promoted to `implemented`. The remaining work is the depth registered in
their `prohibitedClaims`, not a partial baseline: converter-native SourceSpan
precision emission, route-wide relationship/asset semantics breadth, richer
annotations, full renderer/profile coverage, and universal fact-layer use.
These depth items stay explicit todos until named evidence closes them; they
do not roll the baseline back to partial.

### Phase D — CleaningPolicySnapshot, CleaningPatch, Clean View

Contract: `docs/development/06-...md`, `07-...md`, protected design §9–§12.
Milestone M3. Goal: deterministic cleanup runs from a recorded snapshot,
produces guarded patches, rejects unsafe patches, and assembles a complete
Clean View.

Execution model: Phase D should run as parallel, focused slices when ownership
does not overlap. Each slice starts from current `main` in a clean worktree,
uses targeted project-environment tests during implementation, and saves
`npm run dev:full-check` for merge readiness. The branch merged second must
synchronize with latest `main` and rerun its affected checks plus the final
gate. Reviewer subagents are required for schema/compiler completion, patch
safety, Clean View assembly, document cleaning gates, publication behavior, and
capability promotion; small claim or typo corrections use governance checks
unless they change acceptance semantics.

Slices:

- **D1** Landed: `CleaningPolicySnapshot` schema and compiler record selected
  policy input files, resolved active paths, file SHA-256 hashes, filtered
  accepted-rule fingerprints, active rule ids, dictionary ids, protection ids,
  disabled rule ids, conflict resolutions, preference selectors, compiler
  version, threshold summary, section hashes, and a snapshot hash. Cache
  matching uses the snapshot hash after document type detection.
- **D2** Landed: cleanup-stage block changes generate
  `cleaning_patches.jsonl` with block ids, change type, before/after safe
  metadata, rule ids, policy snapshot hash, location hints, and text-changed
  status without copying source text, source-text hashes, private rule paths,
  or private rule content. Existing rendered outputs stay stable until D5
  assembles Clean View.
- **D3** Landed: `patch_quality_gate` rejects unsafe candidate patches before
  rendering, restores rejected changes in memory, writes accepted patch records
  to `cleaning_patches.jsonl`, and writes a safe `cleaning_patch_gate.json`
  summary. The gate checks target node existence, active policy rule ids,
  protected structure changes, whole-section deletion, and evidence presence.
- **D4** Landed: `rejected_patches.jsonl` records one content-safe rejected
  patch entry for every patch rejected by `patch_quality_gate`, including
  reason code, patch identity, safe before/after metadata, policy snapshot
  hash, text-changed status, and location hints. Cache reuse requires a valid
  rejected report, so older D3 runs rerun instead of bypassing D4 evidence.
- **D5** Landed: `CleanViewAssembler` rebuilds the document from Canonical IR
  plus accepted patches in original order, writes content-safe
  `clean_view.json`, and renders `cleaned.md` through the assembled Clean View.
- **D6** Landed: `DocumentCleaningGate` validates the assembled Clean View,
  writes content-safe `document_cleaning_gate.json`, blocks publication on
  invalid or incomplete final cleanup evidence, and reports rejected patch
  counts as warnings when output remains safe.

Acceptance: `cleaning_policy_snapshot` is implemented and `patch_clean_view`
is implemented. Phase D is closed: same Canonical IR + snapshot produces the
same Clean View; unsafe patches preserve original text with a warning; final
publication requires a valid DocumentCleaningGate artifact.

### Phase E — Generalized completed_with_warnings

Contract: protected design §16 and §17. Goal: `completed_with_warnings` works
as the general job status (currently only the batch parent uses it).

Slices:

- **E1** Landed: the single-source job status machine now emits
  `completed_with_warnings` when hard gates pass but non-blocking warnings
  remain. `envelope.status_from_findings` maps strict errors / warnings to
  `failed` / `completed_with_warnings` / `completed`, and `pipeline_core.
  _emit_success` passes the resolved status into the published envelope.
- **E2** Landed: the quality runner already classifies findings as
  `strict_errors` (blocking) vs `warnings` (non-blocking); the success publish
  path now maps the warnings into the envelope `status`. `envelope.ok(status=...)`
  defaults to `completed` so non-job commands stay valid under the required schema
  field, while `WorkerEnvelopeSchema` (TypeScript) marks `status` required.

Acceptance: a single-source run that passes hard gates with a soft warning
publishes with status `completed_with_warnings`; tests cover the boundary
against both `completed` and `failed`. Phase E is closed.

### Phase F — Optional Media And YouTube Routes

Contract: `docs/development/11-...md`. Milestone M6. Goal: optional routes
enter only when dependency setup, sample evidence, capability status, and
quality gates are ready.

Slices:

- **F1** Landed: `media_local_transcript` moved from experimental to partial
  with mocked golden transcript route evidence, command evidence, and dependency
  failure reporting. Verified promotion still requires real local ASR samples.
- **F2** Landed: direct YouTube URLs, explicit video ids, and local `.url` descriptors
  use a subtitle-first route. Successful subtitle reports preserve
  recorded-equivalent inventory evidence, selected language, source URL,
  subtitle/transcript artifact paths, and sanitized commands. Media fallback is
  explicit, downloads video/media through the `yt-dlp` Python package, and only runs when enabled.
  Fixtures mock `yt-dlp`, Python-library media download, `ffmpeg`, and Whisper; real-network breadth,
  timeout behavior, dependency variance, and transcript quality still need
  broader evidence before verified promotion.
- **F3** Landed: `capability-matrix.md`, status JSON, README/operator guidance,
  and golden format manifest keep media and YouTube partial, not verified.

Acceptance: optional routes are clearly marked until verified; no promotion
without named tests; dependency failure messages are explicit.

## Dependency Order

```text
Completed baseline: Phase A status/governance, Phase B PDF routing,
Phase D cleanup, Phase E job status, and M4 source-side publication.

Current critical path:

Phase C / M2 remaining IR fact-layer work
      │
      ├── M5 affected-scope feedback/rerun binding
      │       └── BATCH2 policy/CIR affected batch targeting
      │
      └── optional-route evidence work can run in parallel:
          media ASR fixtures, image/legacy fixtures, YouTube/playlist evidence
```

- Phase D is implemented against the current Canonical IR artifacts. Full
  project completion still requires M2 to close the remaining IR fact-layer
  gaps.
- Phase E is implemented.
- Phase F implementation and evidence work can run in parallel with M2/M5.
  Phase F capability promotion depends on stable route evidence, dependency
  behavior, quality gates, and status docs.
- Phase A remains the completed governance baseline; later work must keep it
  aligned instead of treating it as an open phase.

Development execution is parallel where file ownership and contracts do not
collide. Capability promotion and final release acceptance remain evidence
gated. That means M2, M5, media fixtures, YouTube route hardening, real playlist
evidence, and policy/CIR affected targeting can be developed in parallel slices,
but a status row moves out of `partial` only after its code, tests, docs, and
sample evidence agree.

## Alignment With Implementation Plan M1–M6

| Plan milestone | Roadmap phase | Status |
| --- | --- | --- |
| M1 Design Source Aligned | Phase A | implemented, kept aligned |
| M2 Canonical IR Contract | Phase C | implemented |
| M3 Policy Snapshot And Patch Cleanup | Phase D | implemented |
| M4 Source-Side Publication | — | implemented |
| M5 Feedback And Selective Rerun | feedback docs + proposal code + future rerun slices | implemented |
| M6 Optional Source Expansion | Phase F | local media and YouTube are partial; verified promotion still needs broader real-sample evidence |

Phase A-F is the delivery roadmap, not a strict one-to-one replacement for
M1-M6. Phase B (PDF routing), Phase D (cleanup), and Phase E (job status)
landed while Phase C depth work was still open because their slices could ship
against the current Canonical IR artifacts without completing every
route-native span, relationship, asset, annotation, and IR-regeneration
requirement in M2. Phase C baseline has since been promoted to `implemented`
(typed nodes, source spans, ledger, and content-safe relationship/asset/
annotation artifacts are validated); the remaining route-native span,
relationship, asset, annotation, renderer/profile, and fact-layer work is
tracked as `prohibitedClaims` depth, not as a partial baseline.

## Current Completion Flow

This is the ordered path from the current repository state to the completed
protected design. Status must move only when `kbprep-implementation-status.json`,
`docs/capability-matrix.md`, code, and named tests agree.

### 1. Deepen M2 / Phase C (baseline implemented, depth open)

Goal: close the `prohibitedClaims` depth items so Canonical IR becomes the
complete internal fact layer. The baseline (`canonical_ir_contract` and
`conversion_quality_gate` = `implemented`) already ships typed nodes, source
spans, the transformation ledger, and content-safe relationship/asset/
annotation artifacts; this section tracks the remaining depth, not a partial
baseline.

Required slices:

- Add converter-native SourceSpan extraction for PDF bounding boxes, DOCX run
  ranges, PPTX shape ids, XLSX cells, transcript cue ids, and future YouTube
  cue ids when the converter provides that evidence. The schema and coverage
  gap tracking are in place; converters must still emit real native positions.
- Harden route-wide relationship evidence, asset registry evidence, and
  annotation evidence. Content-safe artifacts already exist; the remaining work
  is semantic breadth and representative route coverage, not creating those
  files from scratch.
- Make conversion gates consume complete route-wide IR semantics for every
  verified or promoted route.
- Extend Markdown regeneration from the minimal standard path to all required
  output profiles and route cases, with named tests proving accepted changes
  and IR ordering stay coherent.
- Close the `prohibitedClaims` depth items on `canonical_ir_contract` and
  `conversion_quality_gate` only after named tests cover the above across
  representative routes.

Execution: run converter-native SourceSpan extraction and Canonical IR
relationship/asset/annotation semantics hardening in parallel when they avoid
overlapping files. Run full IR fact-layer closure after those evidence branches
merge.

Acceptance: the `prohibitedClaims` depth items on `canonical_ir_contract` and
`conversion_quality_gate` are closed with named tests; no route claims complete
IR coverage without tests, and no stale `partial` wording remains for these two
capabilities.

### 2. Close M5 / Feedback And Selective Rerun

Goal: feedback remains proposal-first, but accepted rules can safely rerun only
the affected evidence-backed scope.

Required slices:

- Complete rerun scope selection from source evidence, run-level Canonical IR
  manifest evidence, document type, and policy snapshot identity.
- Extend public selective rerun beyond the current run directory,
  accepted-proposal, and document-type promotion-history selectors to
  Canonical IR id-level or cleaning-unit targeting when stable identity
  evidence exists.
- Preserve failed-promotion history and counterexamples when rerun evidence is
  weak or negative.
- Prove accepted rules do not silently become broad permanent deletion rules.
- Update operator docs so a non-developer can see proposed, accepted, rejected,
  rerun, and failed-promotion states.

Execution: proposal-state hardening and public rerun command scaffolding are
already landed; only add regression guards for proven gaps. Affected-scope
identity binding starts with current run/source/policy evidence and run-level
Canonical IR manifest evidence, then finishes when stable Canonical IR node ids
or cleaning-unit identity are available.

Acceptance: `feedback_rule_learning` is `implemented` — proposal, acceptance,
rerun, rejection, and failed-promotion paths have named tests, and run-level
Canonical IR manifest binding ships (document_id, source, document type,
policy snapshot hash). Canonical IR node-id or cleaning-unit id-level selective
narrowing remains future work (`id_level_narrowing=false`); this section closes
when that narrowing lands with named tests and the future-work caveat is
removed from the status scope.

### 3. Close Batch / Playlist Rerun Gaps

Goal: batch stays source-safe while playlist and rerun behavior become
executable, inspectable, and recoverable.

Required slices:

- Add executable selective batch rerun using the parent status manifest and
  child run evidence. Landed slice: failed/pending parent-manifest rerun,
  source hash verification, command defaults, and `batch_rerun_manifest.json`.
- Keep unsupported files visible as skipped, not silent failures.
- Prove partial batch success, completed-with-warnings, failed children, and
  rerun scopes with tests.
- Explicit YouTube playlist input is implemented: `kbprep-batch --playlist`
  expands the playlist into bounded local `.url` child jobs and records
  per-video parent status. Playlist rerun now preserves playlist
  `source_collection` and child `source_url` evidence in
  `batch_rerun_manifest.json`. Remaining work is policy/CIR affected targeting
  plus broader real-network/dependency evidence before any verified promotion.

Acceptance: `batch_playlist_rerun` moves from `partial` only when selective
rerun and policy/CIR affected targeting are implemented with evidence, and
playlist real-network/dependency evidence is sufficient for any requested
promotion, or a concrete dependency blocker is documented without overstating
completion.

### 4. Close M6 / Phase F

Goal: optional media and YouTube routes become real product promises only after
dependency setup, fixtures, quality gates, and status promotion are complete.

Current truth:

- `media_local_transcript` has local detection and an external transcript route,
  but capability status is still partial because real ASR fixtures and
  timing-quality evidence are missing.
- `youtube_url_routes` is partial. Standalone CLI direct URL / explicit video id input,
  descriptor routing, accepted public URL-shape evidence, subtitle extraction,
  subtitle report inventory/language/artifact evidence, explicit media fallback,
  and mocked failure fixtures exist; verified promotion
  still needs broader real-network, timeout, dependency-variance, fallback, and
  transcript-quality evidence.
- Image OCR route is also experimental and needs real fixtures before
  promotion. Legacy Office is intentionally unsupported (owner declined
  adaptation).

Required slices:

- Add real or golden media ASR fixtures with stable transcript snapshots,
  timing evidence, dependency failure tests, and final-output quality checks.
- Promote local media only after those fixtures pass and the capability matrix
  changes from experimental toward partial or verified.
- Add YouTube timeout, dependency-variance, cache/artifact, and no-subtitle
  fallback evidence against the existing partial URL contract and subtitle-first
  route.
- Add YouTube fixtures for subtitles, no subtitles, failure modes, playlist
  expansion, playlist child publication, and final source-side publication.

Execution: start local media fixtures, image/legacy format fixtures, and YouTube
technical-contract work now in parallel with M2/M5/batch work when file ownership
does not collide. Do not wait for M2 or M5 to begin implementation. Wait only
before promoting the capability status to `verified` or final complete.

Acceptance: `youtube_url_routes` moves from `partial` to `verified` only after
broader real-network fixtures, dependency variance, timeout behavior, media
fallback evidence, and final quality-gate checks pass. M6 is complete only when
every optional route in scope is either verified/partial with evidence or
explicitly kept unsupported with owner-readable guidance.

### 5. Final Release Closure

Run release-level acceptance only after M2, M5, batch/rerun, and M6 status are
honest and aligned:

- `npm run dev:full-check`
- `npm run pack:check`
- `npm run check:flowchart`
- `npm run check:development-docs`
- real sample or vault checks for routes whose quality depends on external
  tools, especially PDF, media, image OCR, and YouTube.

The project is fully complete only when no capability remains `partial`,
`experimental`, or `design_only` unless the owner explicitly accepts that scope
as intentionally unsupported or deferred.

## Slice Pattern

Each slice follows the proven `docs/superpowers/plans/` format. Before starting
a slice, write its plan with:

- Summary and scope (files allowed to modify, files allowed to add).
- Artifact contract (schema and required fields).
- TDD plan (RED failing test first, then GREEN).
- Forbidden scope (what this slice must not touch).
- Acceptance commands.
- Drift checks (banned claims and stale terminology search).

Reference template: `docs/superpowers/plans/2026-06-19-canonical-ir-first-slice.md`.

## Acceptance

Per `docs/development/12-release-acceptance-and-governance.md`:

- Documentation/governance changes: `KBPREP_ALLOW_CORE_DOC_EDIT=1 npm run dev:check`,
  `npm run check:flowchart`, `npm run check:development-docs`.
- Script changes: `npm test`.
- Runtime pipeline changes: `npm run dev:full-check`.
- Python changes: `npm run python:test`, `npm run python:ruff`, `npm run python:typecheck`.

A phase is done only when its capabilities move in `kbprep-implementation-status.json`
and `capability-matrix.md`, with named tests or fixtures as evidence, and no
target-only capability is claimed shipped.

## Risk And Rollback

Risk: a phase can pass its own checks while the status surface still overstates
capability, letting later phases build on an unproven base.

Rollback: if a phase regresses, revert the slice, restore the prior
`kbprep-implementation-status.json` and capability wording, and rerun governance
checks before continuing. Protected design, flowchart, implementation plan,
stage docs, status JSON, and governance checks must stay in the same semantic
state.
