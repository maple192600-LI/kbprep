# 12 Release Acceptance And Governance

## Purpose

Define the checks required before architecture, roadmap, workflow, or release claims are accepted.

## Flowchart Mapping

This stage verifies the whole flowchart contract and every stage document.

## Conflict Handling Rule

If the protected Markdown design and HTML flowchart conflict, the protected Markdown design owns process semantics and the HTML owns visualization. The default fix is to update the HTML flowchart and `docs/flowchart/kbprep-flow.json` to match the protected design.

## Required Checks

Use layered checks during development so quality stays high without forcing
every edit through the slowest gate. Targeted checks prove the current edit;
release-level checks prove merge readiness.

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

Phase D implementation loop:

```bash
node scripts/python-venv.mjs -m unittest <target-test-module> -v
npm run python:ruff
npm run python:typecheck
```

Phase D merge readiness:

```bash
npm run python:test
npm run dev:full-check
git diff --check
```

If parallel branches are active, the branch merged second must first
synchronize with the latest `main`, rerun its targeted checks, then rerun the
merge-readiness gate. Do not promote `cleaning_policy_snapshot` or
`patch_clean_view` status based only on targeted checks.

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
