# 08 Source-Side Publish

## Purpose

Publish the final standard-profile deliverable beside the source only after hard gates pass.

## Flowchart Mapping

This stage supports document cleaning gate, rendering, publish gate, atomic source-side publication, and terminal status nodes in the flowchart contract.

## Contract

Standard profile output:

```text
<source-folder>/<source-stem>.md
<source-folder>/<source-stem>.assets/
```

Markdown source output:

```text
<source-folder>/<source-stem>.cleaned.md
<source-folder>/<source-stem>.assets/
```

Failed runs do not update source-side outputs or `latest_outputs`.

Every publish decision is preceded by `document_cleaning_gate.json`, which
validates the assembled Clean View and records rejected patch warnings without
copying source text. Every publish decision writes `publish_report.json`:

- successful runs copy it to `output_root` and reference it from `latest_outputs`
- blocked runs keep it in the run directory with the strict errors that stopped publication
- the report names the final artifact, process evidence, and cleanup command

## Acceptance

- Publish gate checks final Markdown, assets, quality report, DocumentCleaningGate, and old-output safety.
- Atomic publication either completes fully or leaves the previous successful deliverable intact.
- Publish reports are available for both successful and blocked publish decisions.
- Cleanup can remove process artifacts without deleting final deliverables or private rules.

## Risk And Rollback

Risk: a failed run could overwrite a good output.

Rollback: restore from the previous successful deliverable and block publication until the gate proves atomic behavior.
