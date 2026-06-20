# 12 Release Acceptance And Governance

## Purpose

Define the checks required before architecture, roadmap, workflow, or release claims are accepted.

## Flowchart Mapping

This stage verifies the whole flowchart contract and every stage document.

## Conflict Handling Rule

If the protected Markdown design and HTML flowchart conflict, the protected Markdown design owns process semantics and the HTML owns visualization. The default fix is to update the HTML flowchart and `docs/flowchart/kbprep-flow.json` to match the protected design.

## Required Checks

Documentation and governance changes:

```bash
KBPREP_ALLOW_CORE_DOC_EDIT=1 npm run dev:check
npm run check:flowchart
npm run check:development-docs
```

Script changes:

```bash
npm test
```

Runtime pipeline changes:

```bash
npm run dev:full-check
```

## One-Sentence Feedback Behavior

KBPrep must not silently turn one sentence into a permanent rule; it prepares a safe proposal, shows evidence, and waits for explicit confirmation.

## Release Acceptance

- Protected design docs are aligned.
- Flowchart JSON matches HTML constants.
- Implementation plan and stage docs use the current architecture.
- README and operator docs do not claim target-only capabilities are shipped.
- Capability matrix matches code-level capability declarations.
- Status JSON blocks unproven completion claims.
- Pack checks include the current required docs.

## Risk And Rollback

Risk: release checks can pass while docs describe an older product model.

Rollback: restore the last aligned design-plan-check set and rerun governance checks before continuing development.
