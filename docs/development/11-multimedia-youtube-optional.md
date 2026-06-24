# 11 Multimedia And YouTube Optional Routes

## Purpose

Define how media and YouTube capabilities enter the design without overstating current CLI support.

## Flowchart Mapping

This stage supports source inspection, route selection, dependency failure reporting, and capability promotion in the flowchart contract.

## Contract

- Local files are the maintained CLI path today.
- Media sources must become transcript evidence before classification.
- YouTube uses available subtitles before media transcript extraction.
- YouTube support currently enters through local `.url` descriptor files or
  explicit source identity metadata, not account login, cookies, paid services,
  or direct real-network verification claims.
- Media and YouTube routes require dependency checks, sample evidence, and capability matrix status before promotion.
- No route is verified without named tests or fixtures.
- The YouTube boundary is a technical product contract: accepted URL shapes, dependency detection, network timeout, cache and artifact behavior, no-subtitle fallback, clear error messages, quality gates, and status evidence. There is no separate non-technical approval gate in front of this route.

## Acceptance

- Capability matrix clearly separates current, partial, experimental, target, and unsupported behavior.
- Missing optional dependencies produce clear user-facing errors.
- Unsupported sources stop before conversion.
- Failed optional route runs stop before publication and do not update previous successful deliverables.
- Current media and YouTube support remains partial until real local ASR and owner-approved YouTube samples pass.

## Risk And Rollback

Risk: optional routes can create heavy setup cost or weak transcript quality.

Rollback: keep the route partial, experimental, or unsupported until dependency setup and sample evidence are reliable.
