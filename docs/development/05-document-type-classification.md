# 05 Document Type Classification

## Purpose

Classify document content after conversion quality passes and before cleanup policy is compiled.

## Flowchart Mapping

This stage supports classification pack generation and document type snapshot nodes in the flowchart contract.

## Contract

The classifier receives a bounded `ClassificationPack`.

The output is `DocumentTypeSnapshot`:

- primary content type (emitted as `document_type`)
- content form
- content traits
- confidence
- schema version
- evidence refs
- warnings

## Acceptance

- Cleanup rule changes do not force reclassification.
- Reclassification requires source, IR, pack, or schema changes.
- Missing classifier support falls back to conservative generic cleanup rather than unsafe deletion.

## Risk And Rollback

Risk: wrong classification can select overly broad cleanup rules.

Rollback: use generic cleanup, preserve original text on conflict, and keep a warning in the report.
