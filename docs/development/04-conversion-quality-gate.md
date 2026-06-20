# 04 Conversion Quality Gate

## Purpose

Block unsafe cleanup when conversion evidence is incomplete or unreadable.

## Flowchart Mapping

This stage owns `conversion_quality_gate` in the flowchart contract.

## Gate Inputs

- route decision
- Canonical IR manifest
- source evidence
- converter warnings
- dependency failures
- OCR or text-layer rejection evidence
- source coverage signals

## Acceptance

- Hard failures stop before classification and cleanup.
- PDF upgrade happens at most once and records `fallback_from`, `fallback_to`, `fallback_reason`, and the rejected Markdown path in `conversion_report.json`.
- Failure reports explain what the user can change or install.
- Passing the gate does not mean final output is accepted; it only allows cleanup to begin.

## Risk And Rollback

Risk: a weak gate lets a bad source representation enter cleanup.

Rollback: mark the affected capability lower, block publication, and keep the previous successful deliverable untouched.
