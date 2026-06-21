# KBPrep Cleaning Stage Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make KBPrep cleanup safer, more traceable, and easier to improve from real samples while preserving deterministic cleanup and the existing agent-independent AI review boundary.

**Architecture:** Implement this as five focused PRs. PR1 protects private rule boundaries, PR2 moves cleanup knowledge into sample-backed dictionaries, PR3 adds a partial CleaningPolicySnapshot for policy-input reproducibility, PR4 improves the existing TypeScript AI review path with bounded context and shadow mode, and PR5 hardens feedback promotion plus closeout docs. Do not add provider-specific AI clients or parallel review infrastructure.

**Tech Stack:** TypeScript CLI bridge and Vitest under `src/`, Python worker and `unittest` under `python/kbprep_worker` and `python/tests`, JSON rule files under `rules/`, governance scripts under `scripts/checks/`, project checks through npm scripts only.

---

## Decision

Use **5 PRs**, not 7.

`PR0 docs-repo-index` is not a product-bearing cleanup change and should not block the real work. Its useful content becomes a short "existing implementation map" section inside PR1 docs or the PR handoff. The old `PR6 feedback-tune` is real work, but it belongs with the final feedback/closeout PR because it is the natural end of the same quality loop.

## Non-Negotiable Boundaries

- KBPrep core must not ship provider-specific AI clients for OpenAI, Anthropic, Ollama, vLLM, or any model vendor.
- AI review may see the minimum necessary review text, but it must not rewrite source text. It may only return guarded JSON Patch operations for whitelisted fields.
- The existing TypeScript AI review chain is the base: `src/aiReview.ts`, `src/adapters/ai_review/review_pipeline.ts`, and `src/adapters/ai_review/index.ts`.
- Public `rules/` must stay generic or sanitized. User-specific and private cleanup knowledge must live under `.kbprep/rules/`.
- CleaningPolicySnapshot can only be promoted to `partial` in this plan. Do not claim that every run is fully reproducible until Canonical IR and Clean View are complete enough to support that claim.
- Use only project-environment commands for tests and runtime checks.

## Existing Implementation Map

Before editing, confirm these facts against current files:

- `src/aiReview.ts` already reads `review_pack`, batches it, calls a backend, validates JSON Patch, then calls worker `apply_review`.
- `src/adapters/ai_review/index.ts` already supports injected backend, external command backend, and `local_rules`.
- `python/kbprep_worker/apply_patch.py` already guards patch application with field/status allowlists and protected block checks.
- `scripts/checks/public-rules-boundary.mjs` already exists and is wired through `scripts/check-policy.mjs`.
- `scripts/checks/private-info-redaction.mjs` and `scripts/checks/private-info-redaction-sync.mjs` already protect source/test/docs redaction.
- `docs/development/kbprep-implementation-status.json` currently treats `cleaning_policy_snapshot` as `design_only`, `canonical_ir_contract` as `partial`, and `patch_clean_view` as `design_only`.

## Verification Baseline

Use targeted tests first, then the broader checks for each PR.

Common commands:

```powershell
npm run build
npm test
npm run python:test
npm run python:ruff
npm run python:typecheck
git diff --check
```

For cleanup lifecycle, feedback promotion, AI review behavior, policy snapshot, or release-level behavior:

```powershell
npm run dev:full-check
```

For documentation or governance wiring:

```powershell
$env:KBPREP_ALLOW_CORE_DOC_EDIT='1'; npm run dev:check
```

---

## PR1: Private Rule Boundary And Public Rule Guard

**Outcome:** Feedback dictionary promotion writes to private `.kbprep/rules/` by default, while public `rules/` writes require a second explicit confirmation and remain protected by the existing guard script.

**Branch:** `codex/cleaning-private-rule-boundary`

**Files:**
- Modify: `python/kbprep_worker/feedback/support.py`
- Modify: `python/kbprep_worker/feedback/dictionary_suggestions.py`
- Modify: `python/kbprep_worker/feedback/promotion_history.py`
- Modify: `src/adapters/standalone/cli.ts`
- Modify: `scripts/checks/public-rules-boundary.mjs`
- Test: `python/tests/test_round2_coverage_feedback_promotions.py`
- Test: `src/test/scenarios/worker-feedback-promotion.test.ts`
- Test: `src/adapters/standalone/cli.test.ts`
- Create: `docs/audit-public-rules.md`
- Maybe modify: `docs/feedback-learning.md`, `docs/standalone-cli.md`

### Steps

- [ ] **Step 1: Confirm current dirty state and implementation facts**

Run:

```powershell
git status --short --branch
rg -n "_target_rules_dir|_rules_dir|project_private_rules_root|confirm_dictionary_update|target_rules_dir" python/kbprep_worker src tests python/tests
rg -n "public-rules-boundary|private-info-redaction" scripts package.json docs src python
```

Expected:

- No unrelated dirty files touched by this PR.
- `_target_rules_dir` defaults to `rules_root()`.
- `project_private_rules_root()` exists in `python/kbprep_worker/private_rules.py`.
- `public-rules-boundary.mjs` is already wired through `scripts/check-policy.mjs`.

- [ ] **Step 2: Write failing Python test for private default promotion**

Add or update a test that promotes a dictionary suggestion without `target_rules_dir` and asserts the output is under `.kbprep/rules/document_types/<type>.json`, not public `rules/`.

Use project command:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_round2_coverage_feedback_promotions -v
```

Expected before implementation: FAIL because the default target is public `rules_root()`.

- [ ] **Step 3: Change `_target_rules_dir` default**

In `python/kbprep_worker/feedback/support.py`:

- Import `project_private_rules_root`.
- Keep explicit `target_rules_dir` behavior unchanged.
- Change the default return from `rules_root()` to `project_private_rules_root()`.

Do not change `_rules_dir`; feedback proposal logs and accepted/rejected proposal records have their own default path.

- [ ] **Step 4: Add public write confirmation guard**

In `python/kbprep_worker/feedback/dictionary_suggestions.py`, before writing the target file:

- Resolve `target_rules_dir`.
- Detect whether it points at the repository public `rules/` root.
- If public and `confirm_public_write` is not exactly `True`, fail with `E_CONFIRMATION_REQUIRED`.
- Keep existing `confirm_dictionary_update` as the first confirmation for dictionary promotion.

The business meaning is:

- `confirm_dictionary_update=true`: user confirms the suggestion should be promoted.
- `confirm_public_write=true`: user explicitly accepts that this promotion writes to version-controlled public rules.

- [ ] **Step 5: Wire CLI input**

In `src/adapters/standalone/cli.ts`, add feedback option parsing for:

```ts
confirm_public_write: readBoolean(options, "confirm_public_write", false),
```

Keep option naming underscore-style to match current CLI input conventions.

- [ ] **Step 6: Strengthen existing public rule guard**

Modify `scripts/checks/public-rules-boundary.mjs`; do not create a second guard.

Add checks that fail if public `rules/` contains generated promotion history or user JSONL state, including:

- `promotion_history.jsonl`
- `accepted_rules.jsonl`
- `rejected_rules.jsonl`
- `rule_proposals.jsonl`
- `dictionary_suggestions.jsonl`

Keep generic Chinese marketing terms in tests allowed where they are already intentional. Do not move this concern into private redaction maps.

- [ ] **Step 7: Create public rules audit report**

Create `docs/audit-public-rules.md` with:

- audit date
- command used for current guard
- `git log -p --all -- rules/` sampling scope
- whether private terms were found
- any files intentionally not changed
- follow-up if real private data is found

Do not edit protected core design docs.

- [ ] **Step 8: Run targeted verification**

```powershell
node scripts/checks/public-rules-boundary.mjs
node scripts/checks/private-info-redaction.mjs
node scripts/checks/private-info-redaction-sync.mjs
node scripts/python-venv.mjs -m unittest python.tests.test_round2_coverage_feedback_promotions -v
npm test
git diff --check
```

- [ ] **Step 9: Run broader check**

```powershell
npm run dev:check
```

- [ ] **Step 10: Commit**

```powershell
git add python/kbprep_worker/feedback src/adapters/standalone/cli.ts scripts/checks/public-rules-boundary.mjs python/tests src/test src/adapters/standalone/cli.test.ts docs/audit-public-rules.md docs/feedback-learning.md docs/standalone-cli.md
git commit -m "fix: keep promoted cleanup dictionaries private by default"
```

---

## PR2: Sample-Backed Rule Dictionaries And Threshold Layers

**Outcome:** Cleanup knowledge moves from Python hardcoded Chinese expressions into rule files, and review thresholds become policy-driven enough to handle document type and source quality without broad rewrites.

**Branch:** `codex/cleaning-rule-dictionaries`

**Files:**
- Modify: `python/kbprep_worker/classify_blocks.py`
- Modify: `python/kbprep_worker/rule_loader.py`
- Modify: `python/kbprep_worker/quality/thresholds.py`
- Modify: `python/kbprep_worker/stages/pipeline_helpers.py`
- Modify: `rules/base/obvious_noise.json`
- Modify/Create: `rules/document_types/course.json`
- Modify/Create: `rules/document_types/transcript.json`
- Modify/Create: `rules/document_types/webpage.json`
- Modify/Create: `rules/document_types/interview.json`
- Test: `python/tests/test_core_processing_paths.py`
- Test: `python/tests/test_threshold_contract.py`
- Test: `src/test/scenarios/worker-cleaning-rules-part1.test.ts`
- Test: `src/test/scenarios/worker-cleaning-rules-part2.test.ts`

### Steps

- [ ] **Step 1: Gather sample evidence**

Run current cleanup against representative local samples only if available. If no owner-provided sample set exists yet, use existing repository fixtures and state this as a temporary limitation in the PR.

For each sample, inspect:

- `review_pack.json`
- `discarded.md`
- `cleaned.md`
- `review_needed.md`
- `quality_report.json`

Do not add private source text to version-controlled fixtures.

- [ ] **Step 2: Write failing tests for hardcoded migration**

Add regression tests proving:

- tutorial/case text that mentions CTA words is preserved
- true CTA wrappers still discard
- platform-rule examples are kept when they are method/case content
- hardcoded business cleanup terms do not remain in Python worker code

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_core_processing_paths -v
npm test
node scripts/checks/cleaning-hardcodes.mjs
```

Expected before implementation: at least the new hardcode-guard or behavior test fails.

- [ ] **Step 3: Extend rule schema usage without broad schema migration**

Prefer existing rule file structures when possible. Add only the minimum fields needed by `classify_blocks.py`, such as:

- `business_method_context_terms`
- `contextual_cta_terms`
- `knowledge_terms`
- `tutorial_indicators`
- `protected_patterns`

If `rule_schema.py` already validates equivalent fields, use them. If validation rejects necessary fields, add schema support and targeted schema tests in the same PR.

- [ ] **Step 4: Move hardcoded contextual regex logic into rules**

In `python/kbprep_worker/classify_blocks.py`:

- Replace the `_has_method_knowledge_signal` inline Chinese regex with loaded rule terms.
- Replace the `_is_contextual_cta_knowledge` inline Chinese regex with loaded rule terms.
- Preserve the existing priority chain and conservative protection behavior.

Do not refactor the whole classifier.

- [ ] **Step 5: Add sample-backed document type dictionaries**

Add or update rule files for current high-value types only:

- `course`
- `transcript`
- `webpage`
- `interview`

Each new rule group must have one of:

- a sanitized test fixture
- an existing test assertion
- a note in the PR explaining the owner-provided sample source without leaking private text

Do not invent a broad taxonomy beyond current evidence.

- [ ] **Step 6: Add review threshold helper**

In `python/kbprep_worker/quality/thresholds.py`, introduce a helper such as:

```python
def review_pack_low_confidence_threshold(*, source_quality: str = "", document_type: str = "") -> float:
    ...
```

Keep the existing numeric default `0.76` available for compatibility.

In `python/kbprep_worker/stages/pipeline_helpers.py`, replace direct dictionary access with this helper.

- [ ] **Step 7: Run targeted verification**

```powershell
node scripts/checks/cleaning-hardcodes.mjs
node scripts/python-venv.mjs -m unittest python.tests.test_core_processing_paths -v
node scripts/python-venv.mjs -m unittest python.tests.test_threshold_contract -v
npm test
git diff --check
```

- [ ] **Step 8: Run full cleanup-risk verification**

```powershell
npm run dev:full-check
```

- [ ] **Step 9: Commit**

```powershell
git add python/kbprep_worker rules python/tests src/test scripts/checks docs/hardcoded-cleaning-inventory.md
git commit -m "refactor: move cleanup signals into sample-backed rules"
```

---

## PR3: Cleaning Policy Snapshot Partial

**Outcome:** Each cleanup run records the active cleanup policy inputs and hashes so rule changes cannot accidentally reuse stale cached runs.

**Branch:** `codex/cleaning-policy-snapshot`

**Files:**
- Create: `python/kbprep_worker/cleaning_policy_snapshot.py`
- Modify: `python/kbprep_worker/stages/pipeline_core.py`
- Modify: `python/kbprep_worker/stages/pipeline_helpers.py`
- Modify: `python/kbprep_worker/quality/runner.py`
- Modify: `docs/development/kbprep-implementation-status.json`
- Modify: `docs/development/06-cleaning-policy-library.md`
- Modify: `docs/known-issues.md`
- Test: `python/tests/test_cleaning_policy_snapshot.py`
- Test: `python/tests/test_round2_coverage_pipeline_helpers.py`
- Test: `src/test/scenarios/worker-governance-guards.test.ts`

### Steps

- [ ] **Step 1: Write snapshot unit tests first**

Create `python/tests/test_cleaning_policy_snapshot.py` covering:

- snapshot schema is `kbprep.cleaning_policy_snapshot.v1`
- active route paths and SHA-256 values are included
- profile and document type are included
- threshold summary is included
- changing a rule file changes snapshot hash

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_cleaning_policy_snapshot -v
```

Expected before implementation: FAIL because the module does not exist.

- [ ] **Step 2: Implement focused snapshot module**

Create `python/kbprep_worker/cleaning_policy_snapshot.py`.

Responsibilities:

- collect active rule routes already selected by the loader/registry
- hash rule files with SHA-256
- summarize policy inputs without copying excessive private rule content into reports
- write `cleaning_policy_snapshot.json`
- return snapshot hash and path

Use `pathlib.Path`, typed functions, and frozen dataclasses for data containers where useful.

- [ ] **Step 3: Wire snapshot generation into prepare pipeline**

In `pipeline_core.py` and helpers:

- compile snapshot before classification/cleanup decisions are finalized
- store `cleaning_policy_snapshot.json` in the run directory
- pass snapshot hash into metadata and quality report context

Do not change route selection semantics in this PR.

- [ ] **Step 4: Add snapshot hash to cache matching**

In `_find_existing_run`, require matching `policy_snapshot_hash` when present.

Compatibility rule:

- old runs without snapshot hash must not be treated as equivalent to new snapshot-aware runs
- use `force` or new run when snapshot evidence is missing

- [ ] **Step 5: Add quality report and run metadata references**

Update:

- `run_metadata.json` with `cleaning_policy_snapshot` and `policy_snapshot_hash`
- `quality_report.json` with snapshot reference and hash

Keep `cleaning_rule_sources` for compatibility.

- [ ] **Step 6: Update status honestly**

In `docs/development/kbprep-implementation-status.json`:

- change `cleaning_policy_snapshot` from `design_only` to `partial`
- add evidence files and tests
- keep prohibited claim that it does not fully reproduce every shipped cleanup run

Do not mark `implemented` in this PR.

- [ ] **Step 7: Update docs without touching protected semantics**

In `docs/development/06-cleaning-policy-library.md` and `docs/known-issues.md`, state:

- the first shipped slice records cleanup policy inputs and hashes
- full run reproducibility still depends on future Canonical IR and Clean View completion

- [ ] **Step 8: Run targeted verification**

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_cleaning_policy_snapshot -v
node scripts/python-venv.mjs -m unittest python.tests.test_round2_coverage_pipeline_helpers -v
npm test
node scripts/checks/implementation-status.mjs
git diff --check
```

- [ ] **Step 9: Run full check**

```powershell
npm run dev:full-check
```

- [ ] **Step 10: Commit**

```powershell
git add python/kbprep_worker/cleaning_policy_snapshot.py python/kbprep_worker/stages python/kbprep_worker/quality python/tests src/test docs/development/kbprep-implementation-status.json docs/development/06-cleaning-policy-library.md docs/known-issues.md
git commit -m "feat: record cleanup policy snapshots"
```

---

## PR4: AI Review Context And Shadow Mode

**Outcome:** The existing AI review path receives bounded cleanup context and can run in shadow mode before applying model-generated patches.

**Branch:** `codex/cleaning-ai-review-shadow`

**Files:**
- Modify: `python/kbprep_worker/stages/pipeline_helpers.py`
- Modify: `src/aiReview.ts`
- Modify: `src/adapters/ai_review/review_pipeline.ts`
- Modify: `src/adapters/standalone/cli.ts`
- Modify: `src/aiReview.test.ts`
- Modify: `docs/standalone-cli.md`
- Create: `docs/ai-review-external-command.md`

### Steps

- [ ] **Step 1: Write tests for bounded review context**

Add tests proving `review_pack.json` includes:

- document type
- matched rule source summary
- heading path
- existing risk tags and reason
- a small policy context

Do not require full neighboring text by default.

Run:

```powershell
npm test
node scripts/python-venv.mjs -m unittest python.tests.test_core_processing_paths -v
```

Expected before implementation: FAIL for the new context assertions.

- [ ] **Step 2: Add minimal policy context to review pack**

In `pipeline_helpers.py`, extend `review_pack` with bounded context:

- `policy_context.document_type`
- `policy_context.profile`
- `policy_context.relevant_terms`
- `policy_context.protected_patterns`
- `policy_context.rule_sources`

Keep block text in the existing block payload. Correct security wording is: AI can see necessary review text, but cannot rewrite source text and can only return guarded patch operations.

- [ ] **Step 3: Keep neighbor text opt-in and evidence-backed**

Do not add previous/next block text globally.

If context is needed later, design it as:

- only for review candidates
- capped by character count
- recorded in `review_pack.context_policy`
- covered by tests

This PR should not implement broad neighbor inclusion unless existing tests prove context loss causes a real failure.

- [ ] **Step 4: Inject context into TypeScript prompt**

In `src/adapters/ai_review/review_pipeline.ts`, update prompt construction so the model sees the policy context clearly and briefly.

Keep existing rules:

- return only RFC 6902 JSON Patch
- allowed fields are `status`, `risk_tags`, `reason`, `confidence`
- never rewrite, summarize, or invent source text
- prefer keep/review when uncertain

- [ ] **Step 5: Add `review_mode` to AI review params**

Add `review_mode?: "shadow" | "apply"` to relevant TypeScript config/params.

Compatibility:

- existing `mode=ai_review` behavior remains apply when no `review_mode` is supplied
- docs must recommend `shadow` for any new external model rollout

- [ ] **Step 6: Implement shadow branch**

In `src/aiReview.ts`:

- run backend and patch validation as today
- if `review_mode === "shadow"`, do not call worker `apply_review`
- write `review_suggestions.json` beside the run artifacts
- include patch operations, rejected operations, original block status, warnings, and summary counters
- return original worker result with warning or metadata that shadow suggestions were produced

Do not change `apply_patch.py` safety boundaries.

- [ ] **Step 7: Add external command documentation**

Create `docs/ai-review-external-command.md`:

- define stdin payload shape
- define stdout `{ "messages": [...] }` shape
- show a minimal external command wrapper pattern
- explain that Ollama/OpenAI-compatible/Anthropic clients belong outside KBPrep core
- provide manual acceptance steps without requiring a real model in CI

- [ ] **Step 8: Add shadow/apply tests**

Tests must prove:

- shadow writes suggestions and does not call `apply_review`
- apply still calls worker `apply_review`
- malformed patch operations are rejected before worker application
- protected discard remains blocked
- missing backend returns clear `W_LLM_REVIEW_BACKEND_UNAVAILABLE` behavior

Use injected fake backends, not live model services.

- [ ] **Step 9: Run verification**

```powershell
npm run build
npm test
npm run python:test
git diff --check
```

Then:

```powershell
npm run dev:full-check
```

- [ ] **Step 10: Commit**

```powershell
git add src/aiReview.ts src/adapters/ai_review src/adapters/standalone/cli.ts src/aiReview.test.ts python/kbprep_worker/stages/pipeline_helpers.py python/tests docs/standalone-cli.md docs/ai-review-external-command.md
git commit -m "feat: add bounded AI review context and shadow mode"
```

---

## PR5: Feedback Hardening And Plan Closeout

**Outcome:** Feedback-to-rule promotion becomes more conservative, counterexamples are stronger, promotion history is harder to bypass silently, and operator docs/status reflect the true shipped state.

**Branch:** `codex/cleaning-feedback-hardening`

**Files:**
- Modify: `python/kbprep_worker/feedback/dictionary_suggestions.py`
- Modify: `python/kbprep_worker/feedback/proposals.py`
- Modify: `python/kbprep_worker/feedback/promotion_history.py`
- Modify: `docs/feedback-learning.md`
- Modify: `docs/quality-loop.md`
- Modify: `docs/known-issues.md`
- Maybe modify: `docs/capability-matrix.md`
- Maybe modify: `docs/development/kbprep-implementation-status.json`
- Test: `python/tests/test_feedback_proposals.py`
- Test: `python/tests/test_round2_coverage_feedback_promotions.py`
- Test: `src/test/scenarios/worker-feedback-proposals-part1.test.ts`
- Test: `src/test/scenarios/worker-feedback-promotion.test.ts`

### Steps

- [ ] **Step 1: Write failing tests for scope-based min count**

Cover:

- private/user scope allows low threshold
- document type scope requires medium threshold
- public/global scope requires higher threshold
- explicit `min_feedback_count` can raise but not dangerously lower public/global defaults

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_round2_coverage_feedback_promotions -v
```

Expected before implementation: FAIL for new threshold behavior.

- [ ] **Step 2: Implement scope-based suggestion threshold**

In `dictionary_suggestions.py`, replace a single hardcoded default with a helper such as:

```python
def _min_feedback_count_for_scope(scope: str, requested: object) -> int:
    ...
```

Keep behavior understandable in the response data so the owner can see why a suggestion is not yet promotable.

- [ ] **Step 3: Strengthen counterexample extraction**

In `proposals.py`, collect counterexamples from:

- `cleaned.md`
- `review_needed.md`
- nearby quality issues where the term appears as body knowledge
- existing explicit counterexamples supplied by user

Do not promote if counterexamples match the proposed discard pattern.

- [ ] **Step 4: Harden promotion history override**

In `promotion_history.py` and `dictionary_suggestions.py`:

- failed promotion history blocks new promotion by default
- override requires explicit flag and emits a strong warning in response data
- override response includes failed sample references where available

- [ ] **Step 5: Update docs and status conservatively**

Update operator docs to say:

- feedback creates proposals first
- private rules are default
- public promotion needs extra confirmation
- AI review shadow mode is recommended for new models
- CleaningPolicySnapshot is partial unless future PRs complete Clean View and Canonical IR coverage

Only update `docs/capability-matrix.md` or `kbprep-implementation-status.json` if the capability truth changes in this PR.

- [ ] **Step 6: Search for stale or overclaimed wording**

Run:

```powershell
rg -n "fully reproduces|provider-specific|implemented.*CleaningPolicySnapshot|all cleanup.*CleaningPatch|AI review.*built in|public rules.*default" README.md docs src python
```

Fix stale claims introduced by this plan's PRs.

- [ ] **Step 7: Run targeted tests**

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_feedback_proposals -v
node scripts/python-venv.mjs -m unittest python.tests.test_round2_coverage_feedback_promotions -v
npm test
```

- [ ] **Step 8: Run governance and release-level checks**

```powershell
node scripts/checks/implementation-status.mjs
node scripts/checks/private-info-redaction.mjs
node scripts/checks/private-info-redaction-sync.mjs
node scripts/checks/public-rules-boundary.mjs
node scripts/checks/cleaning-hardcodes.mjs
npm run dev:full-check
git diff --check
```

- [ ] **Step 9: Commit**

```powershell
git add python/kbprep_worker/feedback python/tests src/test docs/feedback-learning.md docs/quality-loop.md docs/known-issues.md docs/capability-matrix.md docs/development/kbprep-implementation-status.json
git commit -m "feat: harden feedback rule promotion"
```

---

## Final Acceptance For The Whole Series

The five PRs are complete only when all are true:

- Promotion defaults to private `.kbprep/rules/`.
- Public rule writes require explicit public confirmation.
- Public rules guard and private redaction checks pass.
- Cleanup classifier no longer hardcodes source/domain-specific Chinese cleanup knowledge in Python.
- New or changed dictionaries are sample-backed and tested.
- Review thresholds support the new policy shape without losing the default behavior.
- CleaningPolicySnapshot records active cleanup policy inputs and prevents stale cache reuse.
- `cleaning_policy_snapshot` status is no stronger than `partial`.
- AI review uses the existing TypeScript path, not new provider-specific client modules.
- Shadow mode can generate suggestions without changing final output.
- Apply mode still routes through worker `apply_review` and quality gates.
- Feedback promotion uses scope-based thresholds and stronger counterexamples.
- Docs do not claim provider-specific AI clients are shipped.
- Docs do not claim full run reproducibility or complete Clean View implementation.

Final project commands:

```powershell
npm run dev:full-check
npm run python:coverage
npm run test:coverage
git diff --check
```

If coverage commands fail due environment/tooling rather than assertions, capture exact output and run the closest target checks before reporting the gap.

## Manual Acceptance For Owner

After the final PR is merged into a feature branch, run a local source sample through the standard profile:

```powershell
kbprep-prepare --input <source-file> --output .kbprep/manual-check --mode rules_plus_review_pack --profile standard
```

Expected owner-visible result:

- final Markdown appears beside the source file when hard gates pass
- `quality_report.json` has no strict errors
- `discarded.md` contains only real cleanup removals
- `review_needed.md` is understandable
- `cleaning_policy_snapshot.json` exists in the run evidence
- feedback suggestions default to `.kbprep/rules/`
- AI shadow mode can produce `review_suggestions.json` without changing the final Markdown

Do not accept the series based only on a readable Markdown file. Inspect `quality_report.json`, `discarded.md`, `review_needed.md`, and policy snapshot evidence.

