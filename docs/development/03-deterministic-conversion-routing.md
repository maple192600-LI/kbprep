# 03 Deterministic Conversion Routing

## Purpose

Make every source kind choose one auditable default conversion route.

## Flowchart Mapping

This stage supports input inspection, unsupported exits, route selection, and the PDF upgrade loop in the flowchart contract.

## Routing Rules

- Route selection is deterministic.
- Unsupported input stops before conversion.
- Missing dependencies produce clear errors.
- PDF can upgrade once from trusted text-layer conversion to MinerU OCR when the gate rejects the first result.
- Other routes do not silently cascade through multiple engines.
- Optional media and YouTube routes stay target or experimental until evidence promotes them.

## Acceptance

- `diagnosis_report.json` records selected capability and dependency status.
- `route_decision.json` records declared route, actual route, fallback, and reason.
- Capability status matches `docs/capability-matrix.md`.

## Risk And Rollback

Risk: implicit route fallback can hide bad conversion evidence.

Rollback: disable the new route or fallback and return the capability to partial, experimental, or unsupported status.
