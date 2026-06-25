# KBPrep Standalone CLI

The standalone CLI is KBPrep's maintained agent-independent entry point. The stable core command surface is local-file oriented; YouTube direct URL and explicit `--youtube-video-id` input are partial optional routes that normalize into controlled local descriptors before entering the same quality pipeline.

## AI Review Backend

Standalone KBPrep remains agent-independent. It does not ship provider-specific review code.

For automated review, callers may inject an `AIReviewBackend` in-process or configure an external command backend. The external command receives JSON on stdin and must write validated JSON on stdout.

If no external command or injected backend is configured, review mode reports a clear warning and does not claim that AI patches were applied.

External command failures are explicit: invalid JSON, non-zero exit, and timeout surface as review errors or warnings with stderr evidence.

Automated review supports two runtime modes:

- `shadow`: validate model patch output and write `review_suggestions.json` without changing blocks, latest outputs, or final Markdown.
- `apply`: validate model patch output, then call Python `apply_review`; this remains the default for existing `mode=ai_review` callers that do not pass `review_mode`.

Use `shadow` for every new external model rollout. See `docs/ai-review-external-command.md` for the external command protocol.

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
kbprep-prepare --input https://www.youtube.com/watch?v=ExampleVideo01 --output ./.kbprep/youtube --force
kbprep-prepare --youtube-video-id ExampleVideo01 --output ./.kbprep/youtube --allow-youtube-media-fallback --force
kbprep-apply-review --run-dir ./.kbprep/source/runs/<run-id> --patch-file ./review.patch.json
kbprep-feedback --run-dir ./.kbprep/source/runs/<run-id> --feedback-text "下次删除「关注公众号」这种污染"
kbprep-feedback --accept-proposal latest --confirm-rule-acceptance
kbprep-feedback --plan-rerun --accepted-proposal latest
kbprep-feedback --plan-rerun --run-dir ./.kbprep/source/runs/<run-id>
kbprep-feedback --execute-rerun --run-dir ./.kbprep/source/runs/<run-id>
kbprep-feedback --suggest-dictionary-updates
kbprep-feedback --promote-dictionary-suggestion --document-type course --confirm-dictionary-update
kbprep-cleanup --output ./.kbprep/source --action finalize
kbprep-batch --input ./sources --output ./.kbprep/batch --mode rules_only
kbprep-batch --playlist https://www.youtube.com/playlist?list=ExamplePlaylist01 --output ./.kbprep/playlist --playlist-limit 25
kbprep-batch --rerun --batch-manifest ./.kbprep/batch/batch_manifest.json --rerun-scope failed_and_pending
```

Every command supports `--help`.
Batch runs write `batch_manifest.json` beside `results.json`, `progress.json`, and `failures.json`. Use `batch_manifest.json` to see parent status, per-file status, skipped unsupported files, source hashes, command defaults, and the evidence-backed rerun scope. `kbprep-batch --playlist <youtube-playlist-url>` expands the playlist into bounded local `.url` child descriptors, records `source_collection.kind=youtube_playlist`, and keeps every child video visible in the parent manifest. Use `kbprep-batch --rerun --batch-manifest <batch_manifest.json>` to rerun failed or pending children without rerunning unrelated successful children. Rerun uses the original command defaults from the manifest unless explicit CLI overrides are passed; `--force` is available when you want to force child reruns. Rerun writes `batch_rerun_manifest.json` and refuses missing or changed source files instead of claiming success. Batch cleanup finalization writes a different file, `kbprep_batch_manifest.json`, after preserving final deliverables; use it only as cleanup-retention proof, not as the live batch run list.

## PDF Routing

PDF routing is diagnosis-selected: simple trusted text-layer PDFs use `pymupdf4llm`, complex trusted PDFs use MinerU `txt` or `auto`, and scanned or untrusted text-layer PDFs use MinerU `ocr`. `conversion_report.json.route_decision` records the selected tier, actual route, fallback or upgrade, and reason.

## Modes

- `rules_only`: local deterministic cleanup only.
- `rules_plus_review_pack`: local cleanup plus review artifacts for human or external review.
- `ai_review`: available only when the caller injects a generic review backend through the runtime API.

The CLI-safe path is `rules_plus_review_pack`, then `kbprep-apply-review` with a validated patch.
The runtime API may run `ai_review` in `shadow` mode first; standalone CLI commands do not ship provider-specific model clients.

`--max-quality-iterations <n>` controls how many quality and review passes may be recorded before KBPrep stops the loop with an iteration-limit error.

## Output

`kbprep-prepare` writes process artifacts under the output directory and publishes a profile-specific final deliverable:

- default `--profile standard`: use `latest_outputs.final_md`, the source-side Markdown file beside the source
- explicit `--profile obsidian_kb`: use `latest_outputs.obsidian_dir`, `latest_outputs.obsidian_index`, and `latest_outputs.obsidian_complete`
- explicit `--profile curated_obsidian_kb`: compatibility Obsidian template for private local document families

Check `latest_outputs.publish_report` after a successful run. If publication is blocked after cleanup and quality checks, inspect the run directory's `publish_report.json` and `quality_report.json`; blocked runs do not update `latest.json`. If the run stopped at the pre-clean conversion gate, inspect the error envelope details for `conversion_quality_report.json` and `error_report.json` instead; `quality_report.json` and `publish_report.json` may not exist yet.

Use `kbprep-cleanup --action finalize` only after checking `quality_report.json`, `discarded.md`, and `review_needed.md`. Finalize preserves the final deliverable: Obsidian output for Obsidian profiles, or source-side Markdown and assets for standard runs.

`.kbprep/rules/` is local private configuration, not temporary output. Cleanup must not delete private rule libraries.

## Feedback

`kbprep-feedback` writes proposed rules first. Only an explicit accept command with `--confirm-rule-acceptance` promotes a proposal into accepted rules.

Use source-specific scope only when the cleanup should be limited to a known source family. Accepted source-specific rules match recorded source identity fields, not arbitrary body text.

Use `kbprep-feedback --plan-rerun` when you want selective rerun evidence before actually running the source again. It can start from `--accepted-proposal`, `--run-dir`, or promotion history for `--document-type`. A planned result records the run id, source identity, document type, policy snapshot hash when available, and command evidence with `would_execute=false`.

Use `kbprep-feedback --execute-rerun` with the same selectors when you want KBPrep to execute one evidence-backed `rules_only` rerun and return `rerun_verification`. Execution keeps the original plan in the response, adds command evidence with `actually_executed=true` when the worker process starts, and reports the rerun status, output paths, strict errors, and worker error evidence. If metadata is missing or promotion history is blocked, the result stays `status: blocked`, writes `rerun_history.jsonl`, and does not claim execution success.

`canonical_ir_binding.status` is intentionally `pending` until the Canonical IR C3 binding is implemented. The current public feedback rerun selectors are run directory, accepted proposal, and document type promotion history. Batch selective rerun is handled by `kbprep-batch --rerun` from `batch_manifest.json`. Canonical IR id-level targeting and playlist rerun remain outside the shipped claim.

Dictionary promotion writes to `.kbprep/rules/document_types/` by default. Later `kbprep-prepare` runs automatically load the matching private document-type dictionary for the current project and record its path/hash in the cleaning policy snapshot without copying private rule contents. Passing `--target-rules-dir rules` points at packaged public rules and also requires `--confirm-public-write`; use that only for generic, sanitized rules that are safe to version. Promotion history stays under private `.kbprep/rules/`, including later promotion-history summary and resolution commands for that public target.

## Path Safety

`--input` and batch `--input` are explicit user-authorized local reads, so absolute paths are allowed. Write and cleanup boundaries are stricter: output roots cannot point at filesystem roots, and patch/config/feedback file arguments must be real files within their size limits before the Python worker is called.
