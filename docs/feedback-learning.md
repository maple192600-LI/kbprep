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
- `lifecycle_status`: current feedback lifecycle state. `status` stays load-bearing (`proposed`, `accepted`, or `rejected`), while `lifecycle_status` can record `proposed`, `accepted`, `rejected`, `rerun_pending`, `rerun_passed`, `rerun_failed`, or `promotion_blocked`.
- `lifecycle_history`: ordered lifecycle states already reached, used to show whether a confirmed rule still needs rerun evidence or has failed promotion history.

## Storage Direction

```text
.kbprep/
  rules/
    document_types/
      <type>.json
    promotion_history.jsonl
    user/
      proposed_rules.jsonl
      accepted_rules.jsonl
      rejected_rules.jsonl
      dictionary_suggestions.jsonl
      rerun_history.jsonl
      protected_terms.jsonl

rules/
  base/
  document_types/
  templates/
  user/
    README.md
```

Project feedback rules live under the current working directory's `.kbprep/rules/user/` by default. Generic packaged base rules must stay small and obvious. Private source, platform, brand, or course rules belong under `.kbprep/rules/`, not public `rules/`.

Dictionary suggestions are promoted to `.kbprep/rules/document_types/<type>.json` by default, with promotion history under `.kbprep/rules/promotion_history.jsonl`. Matching private document-type dictionaries are loaded automatically by later prepare runs for that project. Writing a promoted dictionary into packaged public `rules/` requires both `confirm_dictionary_update=true` and `confirm_public_write=true`; promotion history still remains private for later summary and resolution.

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
-> optionally generate a selective rerun plan from accepted proposal, promotion history, or run metadata
-> optionally execute one selective `rules_only` rerun when run metadata can locate the source
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
- proposal, accepted, and rejected records preserve lifecycle status and history without changing the load-bearing `status: accepted` contract
- source-specific accepted rules match explicit source identity fields
- invalid accepted rule files fail with file and line evidence
- rerun verification reports unavailable metadata instead of pretending proof exists
- selective rerun planning can emit command evidence without executing the rerun; the plan records run id, source identity, document type, policy snapshot hash when available, and `canonical_ir_binding.status: pending`
- selective rerun execution can use the same selectors as planning (`accepted_proposal`, `run_dir`, or promotion history by `document_type`) to execute one `rules_only` rerun and return verification evidence with `actually_executed=true`
- blocked selective rerun planning is recorded in `rerun_history.jsonl` so missing metadata or failed promotion history remains visible
- dictionary suggestions require explicit confirmation before promotion
- dictionary suggestion thresholds are scope-based: user/project/source-pattern evidence can start lower, document-type promotion needs more evidence, and global/public-style promotion needs the highest evidence count
- dictionary promotion defaults to private project rules and requires a second explicit confirmation before writing packaged public rules
- private document-type dictionary rules participate in later cleanup and policy snapshots without copying private rule contents into public artifacts
- promotion history records pass, fail, or unverified outcomes; failed history blocks new promotion by default
- overriding failed promotion history requires an explicit flag and reports the failed sample evidence in the response
- failed promotion history is surfaced as `lifecycle_status: promotion_blocked` so users can see that more rules should not be promoted until representative samples pass again

AI review should start in `shadow` mode for any new external model. Shadow suggestions do not mutate final Markdown; apply mode still routes through worker `apply_review` and the quality gates.

## Acceptance

Feedback learning is acceptable only when the user remains in control of long-term rules and the system keeps evidence for accepted, rejected, and unverified changes.
