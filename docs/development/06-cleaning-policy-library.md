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

The current worker writes `cleaning_policy_snapshot.json` after document type
detection and before cleanup rules run. The artifact records selected rule
routes, resolved active file paths, SHA-256 hashes, source identity summary, the
current cleanup and review thresholds, and a compiled policy summary with active
rule ids, dictionary ids, protection ids, disabled rule ids, conflict
resolutions, preference selectors, compiler version, and section hashes.

The snapshot hash is copied into `run_metadata.json` and `quality_report.json`.
Cache matching is snapshot-aware after the document type and policy hash are
available. Accepted user rules are fingerprinted after the document type and
source filters run, so unrelated accepted rules do not change the current run's
policy hash. The compiled summary records ids and hashes only; it does not copy
private rule bodies, private dictionary values, accepted-rule patterns, or
source text into the run artifact.

The policy snapshot contract is shipped for the current cleanup rule semantics.
Phase D now uses the snapshot as the policy input for patch-based cleanup:
CleaningPatch generation, patch rejection evidence, Clean View assembly, and
the DocumentCleaningGate are shipped in the current worker path.

## Acceptance

- The compiled snapshot records every active rule source and active rule id.
- The shipped artifact records active policy input files, policy section
  hashes, and private-rule fingerprints without copying private rule contents.
- Conflicts keep original text unless a more specific protection or cleanup rule wins.
- Dictionary entries have no deletion power without a cleanup rule.

## Risk And Rollback

Risk: a broad rule can remove useful body text across many sources.

Rollback: reject or disable the rule, keep rejected proposal memory, and rerun representative sources before promotion.
