# Feedback Learning

KBPrep learns from user feedback without trusting a model or a single sentence blindly.

## Plain-Language Behavior

The user should not need to understand rule files, proposal ids, promotion history, or dictionary internals.

When the user says something like:

```text
以后这种“关注公众号领取资料”的内容都删掉。
```

KBPrep should behave like this:

1. Draft a cleanup suggestion.
2. Show which text it would delete.
3. Show which similar text it must not delete.
4. Recommend whether to accept, narrow, or reject the suggestion.
5. Ask for explicit confirmation before the suggestion becomes a long-term rule.
6. Rerun a representative source when possible to prove the rule helped and did not delete useful body text.

KBPrep must not silently turn one sentence into a permanent rule. A sentence that is advertising noise in one document can be useful body text in another document.

The desired simple user experience is "say it once, KBPrep prepares the safe change, then the user confirms." The internal proposal and verification steps exist to protect the user's knowledge base from accidental over-deletion.

## Rule Proposal Shape

Each proposal should contain:

- `action`: `discard`, `review`, or `protect`
- `scope`: `global`, `user`, `project`, `document_type`, or `source_pattern`
- `document_type`: optional classifier target
- `source_pattern`: required when `scope` is `source_pattern`
- `pattern`: literal text, regex, or structured matcher
- `examples`: source snippets that triggered the proposal
- `counterexamples`: text that must not match
- `reason`: plain-language explanation
- `risk_note`: what could go wrong if the rule is too broad
- `created_from_run`: run id or run directory
- `artifact_context`: bounded context from the affected run
- `confidence`: numeric score or enum
- `owner_confirmation_status`: `pending`, `confirmed`, or `rejected`
- `requires_confirmation`: always true before promotion

## Storage Direction

```text
.kbprep/
  rules/
    user/
      proposed_rules.jsonl
      accepted_rules.jsonl
      rejected_rules.jsonl
      protected_terms.jsonl

rules/
  base/
  document_types/
  templates/
  user/
    README.md
```

Project feedback rules live under the current working directory's `.kbprep/rules/user/` by default. Generic packaged base rules must stay small and obvious. Private source, platform, brand, or course rules belong under `.kbprep/rules/`, not public `rules/`.

## Feedback Flow

```text
user feedback
-> analyze affected run artifacts
-> propose reusable rules
-> validate schema
-> require confirmation
-> validate examples and counterexamples before acceptance
-> accept with `confirm_rule_acceptance=true` or reject the proposal
-> write accepted rules only after approval
-> optionally rerun the affected source when run metadata can locate it
-> report whether rerun evidence supports the change
```

## Implemented Surface

`kbprep-feedback` records user feedback as proposals by default.

Implemented behavior includes:

- quoted text can become the first proposed literal pattern
- examples can be pulled from run artifacts
- proposal schema requires positive examples, counterexamples, a risk note, and owner confirmation status
- broad discard proposals can be rejected or narrowed
- accepted proposals are copied to accepted rules only when `confirm_rule_acceptance=true`
- rejected proposals are remembered but never loaded by deterministic cleanup
- source-specific accepted rules match explicit source identity fields
- invalid accepted rule files fail with file and line evidence
- rerun verification reports unavailable metadata instead of pretending proof exists
- dictionary suggestions require explicit confirmation before promotion
- promotion history records pass, fail, or unverified outcomes

## Acceptance

Feedback learning is acceptable only when the user remains in control of long-term rules and the system keeps evidence for accepted, rejected, and unverified changes.
