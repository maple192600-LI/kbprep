# Public Rules Audit

Date: 2026-06-21

## Scope

This audit covers packaged public rule files under:

- `rules/base/`
- `rules/document_types/`
- `rules/templates/`
- `rules/user/README.md`

Runtime feedback artifacts and private learned dictionaries must stay under `.kbprep/rules/`, not the packaged `rules/` tree.

## Boundary

Allowed public content:

- generic base cleaning rules
- generic document-type dictionaries
- generic reusable templates
- the public `rules/user/README.md` pointer that tells operators to use private `.kbprep/rules/user/`

Disallowed public content:

- feedback proposal JSONL files
- accepted or rejected user-rule JSONL files
- dictionary suggestion JSONL files
- promotion history JSONL files
- private source, platform, brand, author, or course-specific cleanup knowledge

## Current Guard

`scripts/checks/public-rules-boundary.mjs` is wired through policy checks and blocks:

- configured private or non-generic terms inside packaged rule files
- runtime feedback JSONL artifacts anywhere under public `rules/`
- public `rules/user/*.jsonl`

The guard currently recognizes these runtime artifact names:

- `accepted_rules.jsonl`
- `dictionary_suggestions.jsonl`
- `promotion_history.jsonl`
- `proposed_rules.jsonl`
- `protected_terms.jsonl`
- `rejected_rules.jsonl`
- `rule_proposals.jsonl`

## Current Evidence

On 2026-06-21, the current public rules tree passed:

```powershell
node scripts/checks/public-rules-boundary.mjs
node scripts/checks/private-info-redaction.mjs
node scripts/checks/private-info-redaction-sync.mjs
```

No public `rules/` file was changed by this audit.

## Promotion Safety

Dictionary promotion writes to `.kbprep/rules/document_types/<type>.json` by default. Later prepare runs load the matching private document-type dictionary for the current project and record only path/hash evidence in the cleaning policy snapshot. Writing the promoted dictionary file to packaged public `rules/` requires both `confirm_dictionary_update=true` and `confirm_public_write=true`; promotion history remains under private `.kbprep/rules/`, including later summary and resolution operations for that public target.

## Residual Risk

The automated guard catches known terms and runtime artifact names. Human review is still required before a promoted dictionary is accepted into public `rules/`, because a sanitized file can still contain rules that are too broad for all users.
