# KBPrep Cleaning Stage Execution Flow

## Decision

Use one isolated git worktree for the cleanup stage and run PRs sequentially.
Use subagents inside each PR for implementation and review, but do not run multiple implementation agents against overlapping files.

This means:

- One branch per PR.
- One implementer loop per task slice.
- Spec review before code-quality review.
- Fix every review finding before the next task.
- Run project-environment checks before commit and before push.
- Do not merge to `main` without owner authorization.

## Why Not Parallel Worktrees For The Five PRs

The five PRs are dependent:

1. Private rule boundary.
2. Sample-backed rule dictionaries.
3. Policy snapshot.
4. AI review context and shadow mode.
5. Feedback hardening and closeout.

Running them in parallel would create conflicts in feedback code, rule loading, docs, tests, and status files. The safe parallelism is review parallelism and narrowly scoped subagent work, not independent PR branches racing ahead.

## Per-PR Loop

Each PR follows this loop:

1. Start from latest `main` or the previous accepted PR branch.
2. Confirm git status and current evidence.
3. Extract the PR task text from `docs/superpowers/plans/2026-06-21-cleaning-stage-rework.md`.
4. Dispatch an implementer subagent for the smallest coherent task slice.
5. Implementer writes tests first where practical, implements, runs target checks, and reports changed files.
6. Run spec-compliance review against the PR task text.
7. Fix every spec gap and rerun spec review.
8. Run code-quality and bug-risk review.
9. Fix every critical or important finding and rerun review.
10. Run the required project checks.
11. Run stale-claim and forbidden-pattern searches when docs or capability wording changed.
12. Commit only task-related files.
13. Push branch.
14. Stop before merging to `main` unless owner explicitly authorizes the merge.

## PR1 Required Loop

Branch:

```powershell
codex/cleaning-private-rule-boundary
```

Required checks before push:

```powershell
node scripts/checks/public-rules-boundary.mjs
node scripts/checks/private-info-redaction.mjs
node scripts/checks/private-info-redaction-sync.mjs
node scripts/python-venv.mjs -m unittest python.tests.test_round2_coverage_feedback_promotions -v
npm test
npm run dev:check
git diff --check
```

Required review gates:

- Spec review: PR1 outcome, boundaries, and test coverage match the plan.
- Code review: no unsafe public rule writes, no duplicate guard script, no broad refactor, no private data leakage.
- Bug review: CLI flag passes through, explicit public writes still work, private default does not break proposal storage.

## Completion Boundary

The cleanup stage is not complete after PR1. PR1 completion only means the private/public rule boundary is safe enough to proceed to PR2.

The full stage is complete only after PR5 passes final acceptance in `2026-06-21-cleaning-stage-rework.md`.

