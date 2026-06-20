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

## Acceptance

- The compiled snapshot records every active rule source.
- Conflicts keep original text unless a more specific protection or cleanup rule wins.
- Dictionary entries have no deletion power without a cleanup rule.

## Risk And Rollback

Risk: a broad rule can remove useful body text across many sources.

Rollback: reject or disable the rule, keep rejected proposal memory, and rerun representative sources before promotion.
