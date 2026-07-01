# 09 Feedback Rule Learning

## Purpose

Turn user feedback into safe rule proposals before any long-term cleanup behavior changes.

## Flowchart Mapping

This stage supports feedback recording, proposal creation, accepted proposal promotion, and future-run policy compilation in the flowchart contract.

## Contract

Feedback creates proposals with:

- action
- scope
- examples
- counterexamples
- source evidence
- reason
- risk note
- confirmation requirement
- owner confirmation status
- lifecycle status and lifecycle history
- created-from-run reference

Accepted proposals become deterministic rules only after explicit `confirm_rule_acceptance` confirmation. Rejected proposals are remembered but not loaded by cleanup. The `status` field remains the load-bearing proposal state (`proposed`, `accepted`, or `rejected`); rerun and promotion safety states are recorded in `lifecycle_status` and `lifecycle_history`.

## Acceptance

- A single sentence from the user never becomes a permanent rule silently.
- Proposal acceptance validates examples and counterexamples.
- Proposal acceptance refuses promotion until owner confirmation is recorded.
- Rerun verification reports whether the accepted rule helped.
- Public selective rerun can be planned or executed from an accepted proposal, a run directory, or document-type promotion history when run metadata is sufficient.
- Selective rerun plans bind run-level Canonical IR manifest evidence when the selected run has it. Node-id targeting is available via `target_node_ids` (`--node-ids`), which narrows worker cleaning to the affected blocks; cleaning-unit id-level targeting remains future work.
- Failed rerun or promotion evidence is visible as `rerun_failed` or `promotion_blocked` without changing the accepted-rule loading contract.

## Risk And Rollback

Risk: feedback can be true for one source and unsafe for another.

Rollback: keep the proposal unaccepted, narrow the scope, or reject it and preserve the rejected pattern as memory.
