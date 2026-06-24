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

## Current Shipped Surface

The worker now writes accepted `CleaningPatch` records to
`cleaning_patches.jsonl` during the cleanup stage. The artifact records
cleanup-stage block changes with block ids, change type, before/after status
metadata, rule ids, the `CleaningPolicySnapshot` hash, text-changed status, and
source location hints.

The patch artifact is intentionally content-safe: it does not copy source text,
source-text hashes, private rule file paths, private rule patterns, private
rule reasons, or heading text into the JSONL records. `cleaning_patch_gate.json`
records a summary of accepted and rejected patch counts and safe rejection
reason codes. `rejected_patches.jsonl` records one content-safe rejected patch
entry per rejected patch, including reason code, patch identity, policy
snapshot hash, safe before/after metadata, text-changed status, and location
hints. Rejected unsafe patches are restored in memory before the current
renderer runs.

Patch generation, the first patch quality gate, and rejected patch reporting
are shipped. Clean View assembly and the final document cleaning gate remain
Phase D target work.

## Phase D Acceptance Target

- Accepted and rejected patches are both auditable.
- Patch generation writes `cleaning_patches.jsonl` without source-text leakage.
- Protected structures remain intact.
- Clean View can be rendered into Markdown and assets.
- Warnings identify rejected patches without blocking safe changes.

Current status: patch generation, the first patch quality gate, and rejected
patch reporting are shipped. Clean View rendering and rejected-patch warnings
remain D5-D6 work.

## Risk And Rollback

Risk: patch logic can delete body text or damage tables, code, formulas, links, or images.

Rollback: reject the unsafe patch class, preserve original text, and keep the rest of the run auditable.
