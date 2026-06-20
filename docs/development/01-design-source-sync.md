# 01 Design Source Sync

## Purpose

Keep the protected design document, HTML flowchart, JSON flowchart contract, implementation plan, and supporting docs aligned.

## Flowchart Mapping

This stage owns the alignment between `docs/kbprep-core-flow-design.md`, `docs/kbprep-full-flowchart.html`, and the flowchart contract.

## Required Work

- Update protected design semantics first.
- Update HTML visualization without adding non-design commentary.
- Update `docs/flowchart/kbprep-flow.json` with matching nodes, edges, stages, and quality gates.
- Update all current roadmap and operator docs that mention changed behavior.
- Update governance checks so stale plan text cannot pass.

## Acceptance

- `npm run check:flowchart` passes.
- `npm run check:development-docs` passes.
- Protected design docs and flowchart contract identify the same quality gates.

## Risk And Rollback

Risk: changing only one design source creates conflicting instructions for future development.

Rollback: revert the protected design, HTML flowchart, JSON contract, plan docs, and checks as one group.
