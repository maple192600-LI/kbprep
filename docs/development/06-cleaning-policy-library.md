# 06 Cleaning Policy Library

## Purpose

Compile reusable rules, dictionaries, preferences, and protection rules into a reproducible cleanup policy.

## Flowchart Mapping

This stage supports cleaning policy snapshot compilation in the flowchart contract.

## Contract

The policy library separates:

- packaged base rules
- document-type rules
- source rules
- project rules
- user rules
- dictionaries
- protection rules
- examples and counterexamples
- accepted and rejected proposal memory

Private rules live under `.kbprep/rules/`. Public rules must remain generic or sanitized.

## Current Shipped Surface

The current worker has a partial snapshot slice: each cleanup run writes
`cleaning_policy_snapshot.json` after document type detection and before
cleanup rules run. The artifact records selected rule routes, resolved active
file paths, SHA-256 hashes, source identity summary, and the current cleanup
and review thresholds. The snapshot hash is copied into `run_metadata.json` and
`quality_report.json`. Cache matching is snapshot-aware after the document type
and policy hash are available. Accepted user rules are fingerprinted after the
document type and source filters run, so unrelated accepted rules do not change
the current run's policy hash.

This is not the full reproducible cleanup contract yet. The remaining target
still needs complete rule ids, dictionary ids, disabled rules, conflict
resolutions, project/user preference semantics, CleaningPatch, and Clean View
assembly.

## Acceptance

- The compiled snapshot records every active rule source.
- The partial shipped artifact records the active policy input files and hashes
  without copying private rule contents.
- Conflicts keep original text unless a more specific protection or cleanup rule wins.
- Dictionary entries have no deletion power without a cleanup rule.

## Risk And Rollback

Risk: a broad rule can remove useful body text across many sources.

Rollback: reject or disable the rule, keep rejected proposal memory, and rerun representative sources before promotion.
