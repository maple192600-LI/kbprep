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
| conversion_quality_gate | partial | Gate validates manifest evidence, typed-node evidence, source-span evidence, claimed transformation-ledger evidence, C4 coverage-report claims, and C5 complete-IR text-quality evidence when available; full route-wide IR semantics remain future work. |
| canonical_ir_contract | partial | Manifest plus `typed_nodes.json`, `source_spans.json`, `transformation_ledger.json`, embedded coverage report evidence, and pre-clean gate use of complete typed-node/source-span text evidence exist for heading, paragraph, list, table, code, quote, formula, figure, metadata, transcript cues, and conversion-phase ledger evidence; route-native fine-grained spans, renderer regeneration, and full fact-layer usage are not shipped. |
| document_type_classification | partial | Code writes `document_classification.json`; status JSON lists it as its own capability with code and test evidence. |
| cleaning_policy_snapshot | implemented | Worker records the compiled policy contract with active rule ids, dictionary ids, protection ids, disabled rule ids, conflict resolutions, preference selectors, section hashes, filtered accepted-rule fingerprints, and run metadata references. |
| patch_clean_view | implemented | CleaningPatch generation writes `cleaning_patches.jsonl`; patch rejection gates write `cleaning_patch_gate.json` and `rejected_patches.jsonl`; Clean View assembly writes `clean_view.json`; DocumentCleaningGate writes `document_cleaning_gate.json` and turns rejected patch evidence into warnings without blocking safe output. |
| feedback_rule_learning | partial | Proposal-first model exists; selective rerun evidence partial. |
| batch_playlist_rerun | partial | Batch + parent status manifest exist; Playlist and selective rerun need more evidence. |
| pdf_three_tier_routing | verified | B2-B4 routing is implemented: Tier 1 uses `pymupdf4llm`, Tier 2 uses MinerU `txt` or `auto`, and Tier 3 uses MinerU `ocr`; real Vault smoke now covers the six Phase B acceptance classes and rejects suspicious Tier 1 zero-hit distributions. |
| media_local_transcript | partial status surface; experimental route matrix | Local media detection and failure reporting exist; real ASR fixtures are still required before route promotion. |
| youtube_url_routes | design_only | YouTube is visible as a target-only matrix row; no URL input route is shipped. |

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

Goal: make the status surface report the real capability boundary, and make
governance checks catch missing coverage. This phase ships no user-facing
feature; it unblocks trust in every later phase.

Slices:

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

Acceptance: `npm run dev:check` passes; status JSON lists classification and
the split media/YouTube capabilities; capability matrix has a YouTube row;
governance catches a planted missing-coverage case.

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
  node, and transcript timing when source cues provide it. Route-native
  precision such as PDF bounding boxes, DOCX run ranges, PPTX shape ids, XLSX
  cells, and YouTube cue ids remains a converter-specific refinement before
  Phase C can be considered fully implemented.
- **C3** Landed: `TransformationLedger` append-only record for conversion-phase Canonical IR evidence, referenced by the manifest and validated by the pre-clean conversion gate when claimed.
- **C4** Landed: complete coverage reporting keeps `typed_nodes_available`,
  `source_spans_available`, and `transformation_ledger_available` tied to
  validated artifacts, and embeds `coverage.report` with counts, ratios,
  precision summaries, and remaining target gaps.
- **C5** Landed: the pre-clean conversion quality gate prefers complete
  typed-node and source-span Canonical IR text evidence when `coverage.report`
  proves full node/span coverage, and falls back to converter-provided quality
  or rendered Markdown only when complete IR evidence is unavailable.

Phase C remains partial until route-native spans, relationships, assets,
annotations, universal fact-layer use, and Markdown regeneration from IR plus
accepted changes are implemented with named evidence. Only then can
`canonical_ir_contract` move from partial to implemented.

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
  path now maps the warnings into the envelope `status`. `envelope.ok` defaults
  to `completed` so non-job commands stay valid under the required schema
  field, while `WorkerEnvelopeSchema` (TypeScript) marks `status` required.

Acceptance: a single-source run that passes hard gates with a soft warning
publishes with status `completed_with_warnings`; tests cover the boundary
against both `completed` and `failed`. Phase E is closed.

### Phase F — Optional Media And YouTube Routes

Contract: `docs/development/11-...md`. Milestone M6. Goal: optional routes
enter only when dependency setup, sample evidence, capability status, and
quality gates are ready.

Slices:

- **F1** Promote `media_local_transcript` from experimental toward verified
  with real or golden ASR fixtures.
- **F2** YouTube subtitle-first route, with media transcript fallback when
  subtitles are unavailable, plus fixtures.
- **F3** Update `capability-matrix.md` YouTube row from design_only toward
  partial/verified only after fixtures pass.

Acceptance: optional routes are clearly marked until verified; no promotion
without named tests; dependency failure messages are explicit.

## Dependency Order

```text
Phase A (status + governance) ── unblocks honest reporting for all later phases
      │
      ▼
Phase B (PDF routing)   Phase C (Canonical IR typed nodes)
                               │
                               ▼
                        Phase D (Snapshot + Patch + Clean View)
                               │
                               ▼
                        Phase E (completed_with_warnings generalization)
                               │
                               ▼
                        Phase F (media + YouTube optional)
```

- Phase D depends on Phase C (patches target typed nodes; Clean View assembles
  from Canonical IR).
- Phase E can run in parallel with C/D (status machine is independent).
- Phase F depends on a stable B/C/D core and on Phase A's honest status surface.
- Phase A should go first so later phases cannot ship overstated claims.

## Alignment With Implementation Plan M1–M6

| Plan milestone | Roadmap phase | Status |
| --- | --- | --- |
| M1 Design Source Aligned | Phase A (ongoing) | implemented, kept aligned |
| M2 Canonical IR Contract | Phase C | in progress (partial) |
| M3 Policy Snapshot And Patch Cleanup | Phase D | implemented |
| M4 Source-Side Publication | — | implemented |
| M5 Feedback And Selective Rerun | Phase A + D (rerun from Canonical IR) | partial |
| M6 Optional Source Expansion | Phase F | not started (design_only) |

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
