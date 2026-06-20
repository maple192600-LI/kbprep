# Quality Loop

KBPrep's target is not "convert once and clean once". The target is a gated source-to-deliverable loop.

## Required Flow

```text
inspect source
-> select deterministic route
-> convert with evidence
-> build Canonical IR target artifacts
-> run conversion quality gate
-> classify document type from bounded evidence
-> compile cleaning policy snapshot
-> generate guarded cleaning patches
-> reject unsafe patches and keep original text
-> assemble Clean View
-> run document cleaning gate
-> render Markdown and assets
-> run publish gate
-> publish source-side deliverable
-> create feedback proposals when the user gives feedback
```

## Gate Categories

Conversion integrity:

- route decision evidence
- dependency availability
- readable text where expected
- page, slide, sheet, cue, or record order
- headings, tables, images, links, code, formulas, and transcript cues where detectable
- OCR or text-layer rejection evidence
- source evidence coverage

Patch safety:

- useful body text must not be removed by broad rules
- protected structures must remain intact
- dictionaries cannot delete without a rule
- unsafe patches are rejected and recorded

Document cleaning safety:

- Clean View keeps document order
- accepted patches have evidence
- rejected patches have warnings
- strict errors block rendering and publication

Publish safety:

- final Markdown and assets exist
- quality report has no strict errors
- previous successful output remains safe on failure
- source-side paths follow the active profile

## Reports

`quality_report.json` is the user-readable and machine-readable gate summary.
`publish_report.json` records whether the final deliverable was published or blocked.
It should identify:

- gate status
- strict errors
- warnings
- evidence paths
- next actions
- quality tasks
- whether publication was blocked

`batch_manifest.json` is the batch parent status summary for multi-file runs. It identifies parent status, per-file status, skipped unsupported files, artifact paths, and rerun scope.

Run artifacts should also preserve conversion reports, discarded content, rejected patches, review-needed material, and publish reports when those artifacts exist for the profile.

## Export Rule

Final output is blocked when strict quality errors remain. A run may still emit audit files for diagnosis, but it must not publish a new source-side deliverable or update `latest_outputs` until hard gates pass.

## Feedback Loop

Feedback does not mutate long-term cleanup behavior directly. KBPrep creates a rule proposal, validates examples and counterexamples, requires a risk note and owner confirmation status, accepts only with `confirm_rule_acceptance=true`, and reruns representative sources when run metadata allows it.
