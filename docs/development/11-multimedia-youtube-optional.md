# 11 Multimedia And YouTube Optional Routes

## Purpose

Define how media and YouTube capabilities enter the design without overstating current CLI support.

## Flowchart Mapping

This stage supports source inspection, route selection, dependency failure reporting, and capability promotion in the flowchart contract.

## Contract

- Local files remain the stable core CLI path; YouTube direct URL, explicit `--youtube-video-id`, and explicit playlist inputs are normalized into controlled local descriptors before entering the same quality pipeline.
- Media sources must become transcript evidence before classification.
- YouTube uses available subtitles before media transcript extraction.
- YouTube support enters through direct URLs, explicit video ids, local `.url` descriptor
  files, explicit playlist input, or explicit source identity metadata. The accepted public URL shapes
  are `youtube.com/watch?v=...`, `m.youtube.com/watch?v=...`, `youtu.be/...`,
  `youtube.com/shorts/...`, and `youtube.com/embed/...`.
- Explicit playlist input uses `kbprep-batch --playlist`; it expands the playlist
  into bounded local `.url` child descriptors before each child enters the
  subtitle-first route and normal quality gates.
- Media and YouTube routes require dependency checks, sample evidence, and capability matrix status before promotion.
- No route is verified without named tests or fixtures.
- The YouTube boundary is an engineering product contract; there is no external compliance approval step in this plan. Implement the requested user-facing capability through accepted URL/id/playlist inputs, dependency detection, bounded network timeout, cache and artifact behavior, no-subtitle fallback, clear error messages, quality gates, and status evidence.
- If logged-in, cookie, or credential-based sources are required by the feature, implement them as explicit operator-provided local inputs with deterministic errors; do not silently discover, store, or reuse secrets.

## Acceptance

- Capability matrix clearly separates current, partial, experimental, target, and unsupported behavior.
- Missing optional dependencies produce clear user-facing errors.
- Unsupported sources stop before conversion.
- Failed optional route runs stop before publication and do not update previous successful deliverables.
- Current media and YouTube support remains partial until real local ASR evidence, real-network YouTube samples, timeout behavior, dependency variance, and transcript-quality checks pass.

## Risk And Rollback

Risk: optional routes can create heavy setup cost or weak transcript quality.

Rollback: keep the route partial, experimental, or unsupported until dependency setup and sample evidence are reliable.
