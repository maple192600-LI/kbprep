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
- created-from-run reference

Accepted proposals become deterministic rules only after explicit `confirm_rule_acceptance` confirmation. Rejected proposals are remembered but not loaded by cleanup.

## Acceptance

- A single sentence from the user never becomes a permanent rule silently.
- Proposal acceptance validates examples and counterexamples.
- Proposal acceptance refuses promotion until owner confirmation is recorded.
- Rerun verification reports whether the accepted rule helped.

## Risk And Rollback

Risk: feedback can be true for one source and unsafe for another.

Rollback: keep the proposal unaccepted, narrow the scope, or reject it and preserve the rejected pattern as memory.
