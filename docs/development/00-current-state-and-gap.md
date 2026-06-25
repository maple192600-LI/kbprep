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
- Phase D cleanup artifacts exist: `cleaning_policy_snapshot.json`,
  `cleaning_patches.jsonl`, `rejected_patches.jsonl`, `clean_view.json`, and
  `document_cleaning_gate.json`.
- Worker envelopes now expose `completed`, `completed_with_warnings`, and
  `failed` job status for single-source and worker command results.

## Target Gaps

- Canonical IR now emits validated typed nodes, source spans, a conversion-phase TransformationLedger, and an embedded coverage report. The pre-clean conversion gate can use complete typed-node/source-span text evidence when coverage is complete, but Canonical IR is not yet the complete internal fact layer.
- SourceSpan variants validate route-native precision records only when required native fields are present, and the coverage report lists missing native precision kinds. Converter-specific evidence for PDF bounding boxes, DOCX run ranges, PPTX shape ids, XLSX cell ranges, transcript cue ids without timing, and YouTube cue ids still needs to be emitted before Phase C can close.
- Canonical IR still needs relationships, assets, annotations, full route-wide conversion-gate use of IR evidence, and Markdown regeneration from IR plus accepted changes before Phase C is complete.
- CleaningPolicySnapshot, CleaningPatch generation, rejected patch reports, Clean View assembly, and DocumentCleaningGate are shipped for the current cleanup path; future cleanup work should focus on broader fixtures, rule quality, and preserving the Phase D contract while finishing the remaining Canonical IR and rerun gaps.
- Optional media and YouTube routes require capability evidence before promotion.
- PDF routing now executes the target three-tier design and records route evidence in `pdf_route_diagnostics` and `conversion_report.json.route_decision`; the capability is verified by public route-shape tests, gray-zone threshold regression tests, generated-PDF route tests, and real Vault smoke distribution evidence.

## Acceptance

- `docs/development/kbprep-implementation-status.json` reflects current truth.
- No current doc claims a target-only capability is shipped.
- The flowchart, development plan, and status JSON use the same stage model.

## Risk And Rollback

Risk: overstating capability status can make users trust an unsafe result.

Rollback: restore the last status JSON and capability wording that match verified tests, then rerun governance checks.
