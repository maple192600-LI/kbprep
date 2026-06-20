# KBPrep Standalone CLI

The standalone CLI is KBPrep's maintained agent-independent entry point. The maintained command surface is local-file oriented today. URL, YouTube, and heavier media routes are target or optional capabilities until the capability matrix and tests promote them.

## AI Review Backend

Standalone KBPrep remains agent-independent. It does not ship provider-specific review code.

For automated review, callers may inject an `AIReviewBackend` in-process or configure an external command backend. The external command receives JSON on stdin and must write validated JSON on stdout.

If no external command or injected backend is configured, review mode reports a clear warning and does not claim that AI patches were applied.

External command failures are explicit: invalid JSON, non-zero exit, and timeout surface as review errors or warnings with stderr evidence.

## Runtime Setup

On first use, KBPrep creates a package-local Python runtime under `.kbprep/venv`.

Setup is reported as structured steps:

1. create venv
2. upgrade packaging tools
3. install worker dependencies
4. run the setup-env probe

Advanced operators may override setup timeouts with:

- `KBPREP_CREATE_VENV_TIMEOUT_MS`
- `KBPREP_UPGRADE_PACKAGING_TIMEOUT_MS`
- `KBPREP_INSTALL_WORKER_TIMEOUT_MS`
- `KBPREP_PROBE_ENVIRONMENT_TIMEOUT_MS`

Use `KBPREP_BOOTSTRAP_PYTHON`, `KBPREP_PYTHON`, or `--config-file` with `python_path` when a specific Python executable is required.

## Commands

```bash
kbprep-preflight --workdir ./.kbprep/check
kbprep-analyze --input ./source.pdf --output ./.kbprep/source
kbprep-prepare --input ./source.pdf --output ./.kbprep/source --mode rules_only --force
kbprep-apply-review --run-dir ./.kbprep/source/runs/<run-id> --patch-file ./review.patch.json
kbprep-feedback --run-dir ./.kbprep/source/runs/<run-id> --feedback-text "下次删除「关注公众号」这种污染"
kbprep-feedback --accept-proposal latest --confirm-rule-acceptance
kbprep-cleanup --output ./.kbprep/source --action finalize
kbprep-batch --input ./sources --output ./.kbprep/batch --mode rules_only
```

Every command supports `--help`.
Batch runs write `batch_manifest.json` beside `results.json`, `progress.json`, and `failures.json`. Use it to see parent status, per-file status, skipped unsupported files, and the evidence-backed rerun scope.

## Modes

- `rules_only`: local deterministic cleanup only.
- `rules_plus_review_pack`: local cleanup plus review artifacts for human or external review.
- `ai_review`: available only when the caller injects a generic review backend through the runtime API.

The CLI-safe path is `rules_plus_review_pack`, then `kbprep-apply-review` with a validated patch.

`--max-quality-iterations <n>` controls how many quality and review passes may be recorded before KBPrep stops the loop with an iteration-limit error.

## Output

`kbprep-prepare` writes process artifacts under the output directory and publishes a profile-specific final deliverable:

- default `--profile standard`: use `latest_outputs.final_md`, the source-side Markdown file beside the source
- explicit `--profile obsidian_kb`: use `latest_outputs.obsidian_dir`, `latest_outputs.obsidian_index`, and `latest_outputs.obsidian_complete`
- explicit `--profile curated_obsidian_kb`: compatibility Obsidian template for private local document families

Check `latest_outputs.publish_report` after a successful run. If publication is blocked, inspect the run directory's `publish_report.json` and `quality_report.json`; blocked runs do not update `latest.json`.

Use `kbprep-cleanup --action finalize` only after checking `quality_report.json`, `discarded.md`, and `review_needed.md`. Finalize preserves the final deliverable: Obsidian output for Obsidian profiles, or source-side Markdown and assets for standard runs.

`.kbprep/rules/` is local private configuration, not temporary output. Cleanup must not delete private rule libraries.

## Feedback

`kbprep-feedback` writes proposed rules first. Only an explicit accept command with `--confirm-rule-acceptance` promotes a proposal into accepted rules.

Use source-specific scope only when the cleanup should be limited to a known source family. Accepted source-specific rules match recorded source identity fields, not arbitrary body text.

## Path Safety

`--input` and batch `--input` are explicit user-authorized local reads, so absolute paths are allowed. Write and cleanup boundaries are stricter: output roots cannot point at filesystem roots, and patch/config/feedback file arguments must be real files within their size limits before the Python worker is called.
