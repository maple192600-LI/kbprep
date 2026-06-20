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

- Canonical IR is not yet the complete internal fact layer.
- SourceSpan variants are not yet a full contract across all source kinds.
- CleaningPolicySnapshot is not yet the full reproducibility boundary.
- CleaningPatch and rejected patch reports are not yet the universal cleanup path.
- Clean View is not yet the required render source for all profiles.
- Optional media and YouTube routes require capability evidence before promotion.

## Acceptance

- `docs/development/kbprep-implementation-status.json` reflects current truth.
- No current doc claims a target-only capability is shipped.
- The flowchart, development plan, and status JSON use the same stage model.

## Risk And Rollback

Risk: overstating capability status can make users trust an unsafe result.

Rollback: restore the last status JSON and capability wording that match verified tests, then rerun governance checks.
