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
| conversion_quality_gate | partial | Gate exists; must read Canonical IR evidence across every route. |
| canonical_ir_contract | partial | Only a minimal manifest; `typed_nodes_available` and `source_spans_available` hardcoded `False`. |
| document_type_classification | partial | Code writes `document_classification.json`; status JSON lists it as its own capability with code and test evidence. |
| cleaning_policy_snapshot | design_only | Reproducibility boundary defined; not the shipped cleanup contract. |
| patch_clean_view | design_only | Patch and Clean View model defined; current cleanup has not moved to it. |
| feedback_rule_learning | partial | Proposal-first model exists; selective rerun evidence partial. |
| batch_playlist_rerun | partial | Batch + parent status manifest exist; Playlist and selective rerun need more evidence. |
| pdf_three_tier_routing | partial | B1 diagnostic evidence now records recommended tier, route, reason, structure signals, image coverage, and large-PDF sampling; code still ships `pdf_text_layer` + `mineru_auto`/`mineru_ocr`; Tier 1 and the six fixtures are not implemented yet. |
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
The three-tier design is already defined at the design source (landed this cycle). This phase is implementation and fixtures only: replace the flat `pdf_text_layer` default with the three tiers and strengthen the current partial PDF capability evidence.

Slices:

- **B1** Landed: diagnostic evidence now records multi-column, table,
  image/text interleaving, CID/ToUnicode risk, image coverage ratio,
  large-PDF sampling, recommended PDF tier, recommended route, and reason.
- **B2** Tier 1 `pymupdf4llm` for trusted text layer + simple layout.
- **B3** Tier 2 `mineru_txt` / `mineru_auto` for trusted text layer + complex
  layout.
- **B4** Tier 3 `mineru_ocr` for untrusted text layer (consolidate existing
  path with new trigger evidence).
- **B5** The six acceptance fixtures defined in stage 03: simple single-column,
  English simple text, multi-column paper, table-heavy, scanned,
  CID/ToUnicode-damaged.

Acceptance: `conversion_report.json.route_decision` records selected tier, actual route, and
reason for every PDF; the six fixtures pass; `pdf_diagnosis_selected` moves
toward verified in `capability-matrix.md`.

### Phase C — Canonical IR Typed Nodes And Source Spans

Contract: `docs/development/02-canonical-ir-contract.md` and protected design
§6. Milestone M2. Goal: Canonical IR becomes the internal fact layer, not just
a metadata manifest.

Slices:

- **C1** `TypedNode` schema and builder (heading, paragraph, list, table, code,
  formula, figure, quote, transcript cue, metadata).
- **C2** `SourceSpan` variants per source kind (protected design §6 table).
- **C3** `TransformationLedger` append-only record.
- **C4** Flip `typed_nodes_available` and `source_spans_available` to `True`
  with builder coverage.
- **C5** Conversion quality gate reads typed-node evidence instead of relying
  on rendered Markdown.

Acceptance: `canonical_ir_contract` moves from partial to implemented;
`canonical_ir.py` is no longer "minimal"; renderable Markdown can be
regenerated from IR plus accepted changes.

### Phase D — CleaningPolicySnapshot, CleaningPatch, Clean View

Contract: `docs/development/06-...md`, `07-...md`, protected design §9–§12.
Milestone M3. Goal: deterministic cleanup runs from a recorded snapshot,
produces guarded patches, rejects unsafe patches, and assembles a complete
Clean View.

Slices:

- **D1** `CleaningPolicySnapshot` schema and compiler (rule set hash, dictionary
  hash, conflict resolutions, compiler version).
- **D2** `CleaningPatch` generation replacing direct cleanup writes.
- **D3** Patch gate (protected design §12 checks: node exists, rule in
  snapshot, protection hit, table/code/formula/link/image integrity, no
  whole-section deletion, evidence present).
- **D4** `rejected_patches.jsonl` for every rejected patch.
- **D5** `CleanViewAssembler` rebuilds the document from Canonical IR plus
  accepted patches in original order.
- **D6** `DocumentCleaningGate` over the assembled Clean View.

Acceptance: `cleaning_policy_snapshot` and `patch_clean_view` move from
design_only to implemented; same Canonical IR + snapshot produces the same
Clean View; unsafe patches preserve original text with a warning.

### Phase E — Generalized completed_with_warnings

Contract: protected design §16 and §17. Goal: `completed_with_warnings` works
as the general job status (currently only the batch parent uses it).

Slices:

- **E1** Single-source job status machine supports `completed_with_warnings`
  when hard gates pass but non-blocking warnings exist.
- **E2** Each quality gate classifies its findings as blocking (failed) or
  non-blocking (warning) and the publisher maps warnings to the status.

Acceptance: a single-source run that passes hard gates with a soft warning
publishes with status `completed_with_warnings`; tests cover the boundary
against both `completed` and `failed`.

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
| M3 Policy Snapshot And Patch Cleanup | Phase D | not started (design_only) |
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
