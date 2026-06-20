# KBPrep Development Implementation Plan

## 1. Target

The implementation target is the architecture defined by:

- `docs/kbprep-core-flow-design.md`
- `docs/kbprep-full-flowchart.html`
- `docs/flowchart/kbprep-flow.json`

The current product remains a local CLI. The implementation path must preserve the existing working demo path while replacing the internal planning model with Canonical IR, cleaning policy snapshots, guarded patches, Clean View, and source-side publication.

## 2. Product Rule

KBPrep must not claim success because a file was converted once. A successful run must prove:

1. the input route was explicit
2. conversion evidence was preserved
3. conversion quality passed before cleanup
4. cleanup used a recorded policy snapshot
5. risky edits were rejected and the original text was kept
6. the complete Clean View passed publication gates
7. the final deliverable was written beside the source without corrupting the previous successful result

## 3. Implementation Milestones

### M1: Design Source Aligned

Goal: the protected design document, HTML flowchart, flowchart JSON, development plan, stage documents, README, quality loop, capability matrix, CLI docs, status contract, and governance checks all describe the same product.

Required evidence:

- `npm run check:flowchart`
- `npm run check:development-docs`
- stale terminology search over current docs and scripts
- `KBPREP_ALLOW_CORE_DOC_EDIT=1 npm run dev:check`

### M2: Canonical IR Contract

Goal: the worker can expose a stable Canonical IR contract with source spans, typed nodes, assets, relationships, annotations, and an append-only transformation ledger.

Required evidence:

- schema tests for source span variants
- conversion report references to IR artifacts
- quality gate reads IR evidence rather than relying only on rendered Markdown

### M3: Policy Snapshot And Patch Cleanup

Goal: deterministic cleanup runs from a `CleaningPolicySnapshot`, creates auditable `CleaningPatch` records, rejects unsafe patches, and assembles a complete Clean View.

Required evidence:

- policy compiler tests
- patch gate tests
- rejected patch report tests
- Clean View render tests

### M4: Source-Side Publication And Failure Safety

Goal: standard profile publishes source-side Markdown and assets only after hard gates pass, and failed runs keep the previous successful output untouched.

Required evidence:

- publish gate tests
- source-side file naming tests
- failure-path tests proving old deliverables are preserved

### M5: Feedback And Selective Rerun

Goal: feedback produces proposals first, accepted rules can rerun affected sources, and rerun evidence proves whether the rule helped without unsafe deletion.

Required evidence:

- proposal validation tests
- accept and reject tests
- representative rerun tests
- promotion history tests

### M6: Optional Source Expansion

Goal: media and YouTube routes enter the product only when dependency setup, sample evidence, capability status, and quality gates are ready.

Required evidence:

- capability matrix update
- real or golden fixture evidence
- dependency failure messages
- no promotion to verified without named tests

## 4. Stage Documents

The development stage set is:

1. `docs/development/00-current-state-and-gap.md`
2. `docs/development/01-design-source-sync.md`
3. `docs/development/02-canonical-ir-contract.md`
4. `docs/development/03-deterministic-conversion-routing.md`
5. `docs/development/04-conversion-quality-gate.md`
6. `docs/development/05-document-type-classification.md`
7. `docs/development/06-cleaning-policy-library.md`
8. `docs/development/07-cleaning-unit-patch-clean-view.md`
9. `docs/development/08-source-side-publish.md`
10. `docs/development/09-feedback-rule-learning.md`
11. `docs/development/10-batch-playlist-rerun.md`
12. `docs/development/11-multimedia-youtube-optional.md`
13. `docs/development/12-release-acceptance-and-governance.md`

These documents are implementation guidance. They must not override the protected core design.

## 5. Current Truth Rules

- A capability is `verified` only when the converter registry and capability matrix link it to named tests or fixtures.
- A capability may be a target design without being shipped.
- Local files are the maintained CLI path today.
- YouTube and optional media routes must stay clearly marked until implemented and verified.
- The source-side output rule is mandatory for the standard profile.
- Feedback must stay proposal-first.
- Public rules must stay generic or sanitized; private rules belong under `.kbprep/rules/`.

## 6. Required Checks

For documentation and governance changes:

```bash
KBPREP_ALLOW_CORE_DOC_EDIT=1 npm run dev:check
npm run check:flowchart
npm run check:development-docs
```

For script changes:

```bash
npm test
```

For runtime, converter, quality, cleanup, feedback, or publish behavior changes:

```bash
npm run dev:full-check
```

Python tests are required only when Python files change.

## 7. Rollback

Documentation and governance changes roll back by reverting the affected docs and check scripts together. A rollback must keep the protected design document, flowchart HTML, flowchart JSON, development plan, stage documents, and governance checks in the same semantic state.
