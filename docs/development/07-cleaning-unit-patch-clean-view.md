# 07 Cleaning Unit, Patch, And Clean View

## Purpose

Make cleanup auditable through internal cleaning units, guarded patches, and complete Clean View assembly.

## Flowchart Mapping

This stage supports internal unit planning, patch creation, patch quality gate, rejected patch reporting, and Clean View assembly in the flowchart contract.

## Contract

- Cleaning units are internal execution scopes.
- Every cleanup change is proposed as a `CleaningPatch`.
- Unsafe patches are rejected and the original text is preserved.
- Clean View is assembled from Canonical IR plus accepted patches.
- Clean View assembly must not summarize, invent, or rewrite source content.

## Acceptance

- Accepted and rejected patches are both auditable.
- Protected structures remain intact.
- Clean View can be rendered into Markdown and assets.
- Warnings identify rejected patches without blocking safe changes.

## Risk And Rollback

Risk: patch logic can delete body text or damage tables, code, formulas, links, or images.

Rollback: reject the unsafe patch class, preserve original text, and keep the rest of the run auditable.
