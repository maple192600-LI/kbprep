# KBPrep Second-Round Audit Remediation

This ledger tracks the second strict review remediation. License review is
excluded by owner instruction.

## Baseline

- Branch: `codex/kbprep-fix-all-audit-issues`
- Initial `npm run dev:check`: passed
- Initial `npm test`: timed out after 184 seconds before a pass/fail result
- Initial `npm run python:coverage`: passed at 54% with the old 45% gate
- Initial `npm run python:ruff`: passed
- Final `npm run python:coverage`: passed at 81% measured line coverage with
  `--fail-under=80`.
- Final `npm run acceptance:round2`: passed all repeatable local acceptance
  samples: Markdown success, unknown suffix rejection, extensionless PDF
  sniffing, PDF text-layer fallback route records, missing local image error,
  and HTML content/script handling.

## Issues To Close

| Issue | Decision | Acceptance |
| --- | --- | --- |
| Converter route selection is still too implicit. | Fix with registered converters and content sniffing. | Route report explains matched converter and evidence. |
| Quality gate fallback uses substring guesses. | Fix with explicit error-code to gate mapping. | Words such as `location` and `education` do not route to cleanup. |
| Per-issue `legacy_code` is unused. | Remove from `quality_issues`; keep worker envelope compatibility only. | AI review still accepts quality failures by new codes or envelope legacy detail. |
| Broken code fence detection counts raw backticks. | Fix with Markdown fence scanning. | Inline backticks and longer fences are not false positives. |
| Accepted user rules are reparsed for every file. | Cache parsing by file stat signature; filter at runtime. | Repeated batch loads reuse parsed accepted rules. |
| Source-pattern matching is too broad. | Match only explicit identity fields. | URL logic applies only to URL fields; local path matching stays path/name based. |
| Cleaning registry only exposes paths. | Add route metadata for priority, cache behavior, and runtime filtering. | Tests prove default route order and accepted-user filtering metadata. |
| `quality_tasks` is verbose. | Replace repeated prose with compact task items. | Tasks keep evidence and commands without large repeated text fields. |
| Feedback promotion summary is over-statistical. | Keep latest status, timestamp, last failure reason, and recommended action. | Old aggregate counters are no longer required by tests or docs. |
| Pipeline state can be read before stages initialize it. | Add grouped state and stage precondition checks. | Wrong stage order fails clearly with `E_PIPELINE_STAGE_ORDER`. |
| Private helper imports are used as public APIs. | Promote shared helpers to public names. | Boundary tests reject cross-module `_` imports in quality runner. |
| No Python type-check gate. | Add dev-only mypy and `npm run python:typecheck`. | Full check includes type checking. |
| Rule schema has no migration guidance. | Add schema migration docs and pack validation. | Pack check validates rule groups and schema references. |
| Audit requested 80% Python coverage. | Completed with focused tests, without excluding business modules or lowering scope. | `npm run python:coverage` now enforces `--fail-under=80` and passed at 81%. |

## Final Round-2 Acceptance Evidence

- `npm run python:coverage`: passed at 81% measured line coverage with the
  active 80% gate.
- `npm run acceptance:round2`: passed and creates temporary samples for `.md`,
  `.weird`, extensionless PDF header, unknown binary, mocked PDF fallback, local
  Markdown images, missing Markdown images, and HTML.

## Out Of Scope

- MinerU/license assessment: explicitly excluded by owner instruction.
