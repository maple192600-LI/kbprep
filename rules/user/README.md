# User Rule Placeholder

`rules/user/` is public documentation only. Real user feedback rules must stay in the local private rule area:

```text
.kbprep/rules/user/accepted_rules.jsonl
.kbprep/rules/user/proposed_rules.jsonl
.kbprep/rules/user/rejected_rules.jsonl
```

Those files are ignored by git and excluded from the npm package.

Advanced callers may still set `KBPREP_USER_RULES_DIR`, but the default local project location is `.kbprep/rules/user/`.
