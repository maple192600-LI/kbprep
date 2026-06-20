# 11 Multimedia And YouTube Optional Routes

## Purpose

Define how media and YouTube capabilities enter the design without overstating current CLI support.

## Flowchart Mapping

This stage supports source inspection, route selection, dependency failure reporting, and capability promotion in the flowchart contract.

## Contract

- Local files are the maintained CLI path today.
- Media sources must become transcript evidence before classification.
- YouTube uses available subtitles before media transcript extraction.
- Media and YouTube routes require dependency checks, sample evidence, and capability matrix status before promotion.
- No route is verified without named tests or fixtures.

## Acceptance

- Capability matrix clearly separates current, partial, experimental, target, and unsupported behavior.
- Missing optional dependencies produce clear user-facing errors.
- Unsupported sources stop before conversion.

## Risk And Rollback

Risk: optional routes can create heavy setup cost or weak transcript quality.

Rollback: keep the route experimental or unsupported until dependency setup and sample evidence are reliable.
