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
- Current public selective rerun execution is single-source feedback rerun only; batch selective rerun and playlist rerun are not shipped.
- `batch_manifest.json` records parent status, per-file status, skipped unsupported files, artifact paths, and rerun scope.
- Playlist input expands into bounded child jobs that reuse the YouTube subtitle-first route and keep per-video status visible.

## Acceptance

- Batch failure does not hide successful child deliverables.
- Child jobs publish source-side results independently.
- Rerun reports unavailable metadata instead of pretending evidence exists.
- Single-source feedback rerun can execute one evidence-backed `rules_only` rerun; batch rerun still requires parent-manifest execution evidence.
- Batch status manifest exists for successful, partially successful, and sample-failed runs.
- Playlist status records every child video, preserves successful child deliverables, and reports mixed success as completed with warnings.

## Risk And Rollback

Risk: parent status can imply all outputs succeeded when some failed.

Rollback: mark the parent status conservatively and require a failed-items report.
