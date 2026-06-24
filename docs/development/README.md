# KBPrep Development Documents

This directory turns the protected design into implementation work. The protected design remains authoritative:

- `docs/kbprep-core-flow-design.md`
- `docs/kbprep-full-flowchart.html`
- `docs/flowchart/kbprep-flow.json`

## Planning Entry Points

- `development-roadmap.md` — connected phase-by-phase path from the current state to the completed design (read first).
- `docs/kbprep-development-implementation-plan.md` — M1–M6 milestones and current-truth rules.
- `kbprep-implementation-status.json` — capability status source of truth.
- `docs/capability-matrix.md` — route-level capability status and evidence.

## Current Stage Set

1. `00-current-state-and-gap.md`
2. `01-design-source-sync.md`
3. `02-canonical-ir-contract.md`
4. `03-deterministic-conversion-routing.md`
5. `04-conversion-quality-gate.md`
6. `05-document-type-classification.md`
7. `06-cleaning-policy-library.md`
8. `07-cleaning-unit-patch-clean-view.md`
9. `08-source-side-publish.md`
10. `09-feedback-rule-learning.md`
11. `10-batch-playlist-rerun.md`
12. `11-multimedia-youtube-optional.md`
13. `12-release-acceptance-and-governance.md`

## Development Rules

- Every stage document must reference the flowchart contract.
- Canonical IR is the target internal fact layer for converted source evidence.
- Every stage document must include `## Risk And Rollback`.
- Current capability claims must match `docs/development/kbprep-implementation-status.json`.
- Target capabilities must not be described as shipped until tests or fixtures prove them.
- User feedback remains proposal-first.
- Final standard output is source-side Markdown and assets.

## Owner-Readable Contract

The user should be able to understand whether a capability is available, partial, target-only, or intentionally unsupported without reading source code.

## Risk And Rollback Rule

Any change to architecture, roadmap, stage sequence, quality gates, or acceptance checks must update the protected design, implementation plan, stage docs, README/operator docs, status JSON, and governance checks in the same turn.
