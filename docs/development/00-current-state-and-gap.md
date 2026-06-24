# 00 Current State And Gap

## Purpose

Record the difference between the current implementation and the target design.

## Flowchart Mapping

This stage maps the current codebase against the flowchart contract in `docs/flowchart/kbprep-flow.json`.

## Current Implemented Surface

- Node CLI and Python worker exist.
- Conversion routes and capability declarations exist.
- Source-side final output exists for the standard profile.
- Quality reports and proposal-first feedback exist.
- Public and private rule boundaries exist.

## Target Gaps

- Canonical IR now emits validated typed nodes, source spans, a conversion-phase TransformationLedger, and an embedded coverage report, but it is not yet the complete internal fact layer.
- SourceSpan variants are not yet a full contract across all source kinds; route-native precision such as PDF bounding boxes, DOCX run ranges, PPTX shape ids, XLSX cells, and YouTube cue ids still needs converter-specific evidence.
- Canonical IR still needs relationships, assets, annotations, conversion-gate use of full IR evidence, and Markdown regeneration from IR plus accepted changes before Phase C is complete.
- CleaningPolicySnapshot records the first policy input/hash artifact, but is not yet the full reproducibility boundary.
- CleaningPatch and rejected patch reports are not yet the universal cleanup path.
- Clean View is not yet the required render source for all profiles.
- Optional media and YouTube routes require capability evidence before promotion.
- PDF routing now executes the target three-tier design and records route evidence in `pdf_route_diagnostics` and `conversion_report.json.route_decision`; the capability is verified by public route-shape tests, gray-zone threshold regression tests, generated-PDF route tests, and real Vault smoke distribution evidence.

## Acceptance

- `docs/development/kbprep-implementation-status.json` reflects current truth.
- No current doc claims a target-only capability is shipped.
- The flowchart, development plan, and status JSON use the same stage model.

## Risk And Rollback

Risk: overstating capability status can make users trust an unsafe result.

Rollback: restore the last status JSON and capability wording that match verified tests, then rerun governance checks.
