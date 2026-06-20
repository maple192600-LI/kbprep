# KBPrep Agent Notes

KBPrep is a local CLI project. Do not add business logic for a specific AI development agent host.

## Product Stage

Treat this project as a local self-use tool unless the owner explicitly changes the stage. Keep the main demo path stable, recoverable, and easy to verify. Do not expand it into a SaaS, cloud service, payment system, multi-tenant app, or complex permission system without owner approval.

## Highest Development References

These two files are the highest project development references:

1. `docs/kbprep-core-flow-design.md`
2. `docs/kbprep-full-flowchart.html`

The Markdown design document defines the development rules, process semantics, quality gates, data artifacts, and acceptance standards. The HTML flowchart defines the end-to-end visual operating flow. When code, older docs, or plans conflict with these two files, treat the two files as the target direction and make the gap explicit before changing implementation.

If the Markdown core design and the HTML flowchart conflict with each other, the core design owns the process semantics and the HTML owns visualization. Default fix: update the flowchart and `docs/flowchart/kbprep-flow.json` to match the core design. Do not change the core design semantics unless the owner explicitly authorizes that outcome.

Do not edit either file unless the owner explicitly orders it. Read them as references only.

## Project Goal

KBPrep converts local source files into clean, traceable Markdown deliverables for Obsidian or knowledge-base workflows.

The intended pipeline is:

1. Detect file type and choose the best conversion route.
2. Convert through auditable route artifacts and move toward Canonical IR as the internal fact layer.
3. Compare converted evidence with source evidence and report loss risk.
4. Classify document type.
5. Apply deterministic cleanup from rule dictionaries.
6. Use AI or human review only through guarded patch or proposal artifacts.
7. Recheck quality before publishing the final Markdown or Obsidian deliverable.
8. Record user feedback as rule proposals before promotion.

The current development metric is not "produces Markdown once." The metric is that each change preserves the core quality loop: choose an explicit route, preserve source evidence, verify conversion, clean with policy snapshots and protection rules, reject unsafe patches, generate repair tasks or rule proposals on failure, rerun only evidence-backed scopes, then publish only after final checks pass.

## Boundaries

- Do not create AI development agent host adapter code in this repository.
- Provide CLI commands, core flow docs, and package/runtime docs only.
- Let each calling environment package this project with its own external tooling.
- Do not hardcode self-media, platform, author, or course-brand cleanup in Python logic. Put reusable cleanup knowledge in `rules/`.
- Public `rules/` contains only generic or sanitized rules. User-specific JSONL rules and private templates live in `.kbprep/rules/`, which is long-term local configuration even though `.kbprep/` is gitignored.
- Do not build OCR from scratch. Use the existing converter/OCR route and keep its quality evidence auditable.
- Do not let any tool path bypass the quality gates and write a final result directly.
- Do not treat user feedback as an accepted long-term rule until scope, positive evidence, negative examples, and owner or maintainer confirmation are recorded.
- The Python worker rejects unsafe `output_root` (filesystem root, user home, protected OS directories) and unsafe `input_path` (device files, implausibly large files) at the pipeline entry (`fs_safety.is_safe_output_root` / `is_safe_input_path`). TypeScript-layer path boundary protection is opt-in via `KBPREP_CLI_BOUNDARY_DIR`.

## Private Information Redaction

KBPrep is open-source. Real private information (personal names, brand names, social handles, UIDs, revenue figures) must not appear in version-controlled source, tests, or fixtures.

- The single source of truth is `scripts/redact-map.json` (`mapping` + `privateTerms`), mirrored by `src/test/fixtures/redact-map.ts` and `python/tests/redact_map.py`. `scripts/checks/private-info-redaction-sync.mjs` keeps the three in sync.
- `scripts/checks/private-info-redaction.mjs` scans `src/`, `scripts/`, `python/`, `docs/`, `rules/` and fails on any `privateTerms` hit. It is wired into `npm run check:governance` (and therefore `pack:check` and `release:check`).
- Generic Chinese marketing terms (公众号/扫码/入群/训练营/社群/体验卡/小红书/B站/抖音/视频号/二维码/加微信 etc.) are legitimate cleaning-rule test samples and are intentionally NOT redacted — they are common vocabulary, not private information.
- When adding test data that needs a private-looking label, use the `Example*` placeholders from the redact map, not real names/brands.

## Change Protocol

Before editing code, explain to the owner:

- What will change.
- Why it is needed.
- Which working feature or demo path could be affected.
- Whether there is a lighter alternative.

Keep each task small and reversible. Do not refactor unrelated code. For file, data, OCR, conversion, cleanup, or feedback-learning work, be extra conservative: preserve source evidence, audit discarded content, and make failure reasons understandable to a non-developer.

## Workflow Closure Protocol

When a task has a natural completion step that is technically necessary to deliver or hand off the result, complete that step automatically after the relevant checks pass instead of sending the owner a technical question. This includes, when appropriate, staging the exact task-related files, creating a focused commit on the current feature branch, pushing that branch, regenerating required derived artifacts, rerunning required checks after generated files change, and leaving a clear handoff note.

Do not ask the owner to choose routine engineering mechanics. Ask or stop only when the next action crosses a real permission boundary: merging into the main branch, releasing, changing production configuration, deleting real data, changing credentials or permissions, creating cost, or making a hard-to-rollback system-level change. If a routine completion step fails, investigate the cause and either fix it or report the concrete blocker and impact.

## Full Issue Closure Rule

When any issue, failing check, bug, contradiction, false success, documentation drift, or implementation gap is discovered while working on this project, treat it as part of the current quality closure until proven otherwise. Do not leave known problems as silent residue, optional follow-up, or vague "remaining work."

The agent must fully close every discovered issue by default:

- Reproduce or verify the issue with current project evidence.
- Trace the root cause instead of patching only the symptom.
- Fix every affected layer needed for the issue to stay fixed: code, tests, docs, governance checks, package scripts, and acceptance rules when relevant.
- Rerun the project-environment checks that prove the original issue and any related regressions are resolved.
- Search for related instances of the same problem pattern and fix them in the same workflow.

The only acceptable reason to leave an issue unresolved is a real boundary: explicit owner permission is required, external access is missing, the fix would create cost, the fix would change production or real data, or the issue is outside this repository and cannot be verified here. In that case, stop treating the task as complete and report the item as a blocker with the concrete evidence, impact, and exact condition needed to finish it.

## Global Planning Closure Protocol

When modifying any plan, roadmap, development workflow, architecture document, governance document, or stage document, treat the change as a system-wide consistency task, not a local edit.

Before the final response, the agent must complete these checks:

1. Impact propagation
   - Identify every document, checklist, stage plan, command, and acceptance rule affected by the change.
   - Update all affected files in the same turn unless explicitly blocked.
   - If any affected file is not updated, list it under "not changed" with the concrete reason.

2. Source-of-truth alignment
   - Verify alignment between highest design documents, implementation plan, stage documents, README/operator docs, test/check commands, and package/governance checks when relevant.
   - Do not let an old priority order or old stage sequence remain after a new plan is introduced.

3. Contradiction search
   - Search for stale stage names, stale priority order, outdated commands, old artifact names, and conflicting wording.
   - Remove or update stale references before claiming the planning work is complete.

4. Non-developer explanation
   - Explain product impact in plain language first.
   - Avoid unexplained engineering terms. If a technical term is necessary, explain what user outcome or project risk it affects.

5. Completion report
   - Every final response for planning or governance work must include what changed, which related files were updated, what was intentionally not changed, what remains incomplete, which checks ran, and the next implementation step.

If the owner points out that a prior plan was incomplete, the agent must not only fix the named issue. It must audit the whole plan family for related inconsistencies and update all affected documents before answering.

## Verification

After each implementation change, verify the affected demo path. Prefer existing commands when relevant:

## Main Commands

- `npm run dev:check`
- `npm run build`
- `npm test`
- `npm run pack:check`
- `npm run dev:full-check`

Use `kbprep-feedback` for review feedback. It writes proposed rules first. Only an explicit `kbprep-feedback --accept-proposal <id|latest>` may promote a proposal into accepted user cleanup rules.

If automated tests are not enough for the change, provide manual acceptance steps in product terms: how to start, what to upload or type, where to click or which CLI command to run, what success should look like, and which error text the owner should send back if it fails.

## Project Guardrails

- Run `npm run dev:check` for documentation, configuration, packaging, and narrow implementation changes.
- Run `npm run dev:full-check` for converter routes, quality gates, cleanup lifecycle, feedback promotion, release, dependency, or runtime changes.
- `npm run pack:check` also verifies protected design documents, project governance wiring, capability matrix drift, hardcoded cleanup terms, agent-independent runtime boundaries, audit guard checks, thresholds, and npm package contents.
- `npm run pack:check` also verifies development-plan closure: stage docs must include flowchart mapping, risk/rollback, release acceptance, and owner-readable feedback guidance.
- Do not claim a KBPrep output is accepted unless `quality_report.json` has no strict errors and the successful run published the expected `latest_outputs`.
- Do not promote a `partial` or `unsupported` capability to `verified` without golden fixtures and named test evidence in `python/kbprep_worker/converter_capabilities.py`.
- If a check cannot run, report the exact command, the reason it could not run, and the remaining manual acceptance steps.

## Engineering Standards

### Rule Enforcement

These rules are enforced by the Stop Hook in `.codex/hooks.json`. Violations cause the Hook to block task completion — Codex must fix issues before finishing.

### File & Function Size

- Python: single file ≤ 800 lines, single function ≤ 50 lines.
- TypeScript: single file ≤ 800 lines, single function ≤ 50 lines.
- When a file exceeds the limit, split by responsibility before adding new logic.
- When a function exceeds the limit, extract sub-functions with descriptive names.

### Python Code Quality

- All functions must have type hints on parameters and return types.
- Use `dataclass(frozen=True)` for data containers. No mutable global state.
- Never use `except:` (bare except). Always catch specific exceptions.
- Never use `__getattr__` for module-level delegation. Use explicit imports.
- Never use `setattr()` or monkey-patching to modify other modules at runtime.
- Use `pathlib.Path` instead of `os.path` for new code.
- Use `logging` module, never `print()` for production code.
- When a library is already a dependency (e.g., beautifulsoup4), use it instead of regex for HTML parsing.

### TypeScript Code Quality

- No `any` type without explicit justification in a comment.
- No `as unknown as T` double assertions. Refactor the type instead.
- No unused imports, variables, functions, or types.
- Use `const` by default. Use `let` only when reassignment is needed.

### Lint & Format

- Python: `ruff check` must pass with rules E, F, W, I, N, UP enabled (configured in `python/pyproject.toml`).
- Python: `mypy` must pass with config in `python/pyproject.toml`.
- TypeScript: `tsc --noEmit` must pass.
- The Stop Hook runs `npm run dev:check`, `npm run python:ruff`, and `npm run python:typecheck` automatically. `dev:check` must include `npm test`.

### Testing

- New functions and modules must have corresponding test files.
- TypeScript coverage floors (measured by `npm run test:coverage`): lines ≥85%, functions ≥80%, branches ≥70%, statements ≥80%. Python coverage must stay ≥80% (`npm run python:coverage`). Branches is the most volatile metric — new control flow must ship with tests.
- `src/runtime/pythonRuntime.ts` line coverage must stay ≥ 80%; this file owns the managed project runtime path and must not become a hidden weak spot.
- After modifying Python code, run `npm run python:test`.
- After modifying TypeScript code, run `npm test`.
- Release-level checks must run measured TypeScript coverage through `npm run test:coverage`.

### Cross-Language Contract

- When modifying `python/kbprep_worker/error_codes.py`, you MUST also update `src/errorCodes.ts` to match.
- When modifying the JSON envelope schema in Python, verify TypeScript TypeBox schemas still validate.
- Run the error-code contract test after any change: `npm run python:test-contract`.

### Project Structure

- Every TypeScript project must have a `package.json` with name, version, scripts, and dependencies.
- Every Python package must have a `pyproject.toml` with lint config (ruff select ≥ E, F, W, I).
- Never create a file without a clear, single responsibility.
- `__init__.py` files should be minimal — only re-export public API.

### Forbidden Patterns

- No regex parsing of HTML when BS4/lxml is available.
- No hardcoded paths, magic numbers, or hardcoded thresholds in source code.
- No duplicate constant sets (if two sets have the same content, use one).
- No f-string YAML generation — use a YAML library or ensure escaping.
- No writing files without checking the directory exists first.
- No claiming a feature is done without running the relevant test or check command.

### Rule-To-Check Mapping

| Rule | Enforcement | Command or check |
|------|-------------|------------------|
| Python file <= 800 lines and function <= 50 lines | Stop Hook and `dev:check` | `npm run python:check-size` |
| Python and TypeScript error codes stay synced | Stop Hook | `npm run python:test-contract` |
| Python lint rules E/F/W/I/N/UP pass | Stop Hook | `npm run python:ruff` |
| Python worker type checks pass | Stop Hook | `npm run python:typecheck` |
| TypeScript compiles and integration tests stay green | `dev:check` | `npm run build`, `npm test` |
| Hardcoded cleanup terms stay out of worker logic | `pack:check` | `scripts/checks/cleaning-hardcodes.mjs` |
| HTML parsing does not use regex when a parser is available | `pack:check` | `scripts/checks/forbidden-patterns.mjs` |
| YAML/frontmatter generation avoids unsafe multiline f-strings | `pack:check` | `scripts/checks/forbidden-patterns.mjs` |
| Protected design and governance docs stay wired | `pack:check` | `scripts/checks/protected-docs.mjs`, `scripts/checks/project-governance.mjs` |
| Python tests and coverage run before release-level acceptance | `dev:full-check` | `npm run python:test`, `npm run python:coverage` through `release:check` |
| TypeScript integration tests and measured coverage run before release-level acceptance | `dev:full-check` | `npm test`, `npm run test:coverage` through `release:check`; TypeScript lines >=85%, functions >=80%, branches >=70%, statements >=80%, `src/runtime/pythonRuntime.ts` lines >=80% |

### Before Finishing Any Task

1. Run `npm run dev:check` (or `npm run dev:full-check` for core pipeline changes).
2. Run `npm run python:test` for Python changes.
3. Check: did I create or modify any file over 800 lines? If yes, split it first.
4. Check: did I modify error codes? If yes, sync both sides and run contract test.
5. Report what commands ran and what they output. If a command cannot run, say so explicitly.
6. Note: The Stop Hook runs `npm run dev:check`, `npm run python:ruff`, and `npm run python:typecheck` automatically; `dev:check` includes `npm test`. Fixing issues proactively saves a retry loop.
