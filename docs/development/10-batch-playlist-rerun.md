# 10 Batch, Playlist, And Rerun

## Purpose

Run multiple sources as independent child jobs while preserving per-source evidence and final deliverables.

## Flowchart Mapping

This stage supports batch or Playlist controller, child job execution, and parent status summary nodes in the flowchart contract.

## Contract

- Each child job runs the same gates as a single source.
- A parent job records child status, warnings, and failed items.
- At least one successful child can produce `completed_with_warnings`.
- All children failed means parent `failed`.
- Rerun uses existing run metadata only when the source can be safely located.
- Current public selective rerun execution includes single-source feedback rerun and batch failed/pending rerun from `batch_manifest.json`. Playlist rerun uses the same parent manifest path and preserves playlist source-collection evidence in `batch_rerun_manifest.json`.
- `batch_manifest.json` records parent status, per-file status, skipped unsupported files, source hashes, source URLs when available, artifact paths, command defaults, and rerun scope.
- Batch rerun writes `batch_rerun_manifest.json` with selected children, successes, failures, skipped unsupported visibility, source-manifest evidence, and playlist source-collection evidence when rerunning explicit playlist child descriptors.
- Playlist input expands into bounded local `.url` child jobs that reuse the YouTube subtitle-first route and keep per-video status visible through `source_collection` metadata.

## Acceptance

- Batch failure does not hide successful child deliverables.
- Child jobs publish source-side results independently.
- Rerun reports unavailable metadata instead of pretending evidence exists.
- Single-source feedback rerun can execute one evidence-backed `rules_only` rerun.
- Batch rerun can execute `failed_only`, `pending_only`, `failed_and_pending`, or recommended parent-manifest scope without rerunning unrelated successful children. Policy-affected and Canonical IR id-level batch targeting are separate later work.
- Batch rerun refuses missing or changed source files and records the failure in `batch_rerun_manifest.json` instead of claiming success.
- Batch status manifest exists for successful, partially successful, and sample-failed runs.
- Playlist status records every child video, preserves successful child deliverables, and reports mixed success as completed with warnings.
- Playlist rerun preserves `source_collection` plus child `source_url` evidence in `batch_rerun_manifest.json`.
- Playlist input is explicit (`kbprep-batch --playlist`) and does not make directory batch process arbitrary `.url` files unless the user chose the playlist path.

## Risk And Rollback

Risk: parent status can imply all outputs succeeded when some failed.

Rollback: mark the parent status conservatively and require a failed-items report.
