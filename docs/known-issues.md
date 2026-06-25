# KBPrep Known Issues And Roadmap

This file tracks known product and engineering gaps that are not hidden defects.

## Current Target Gaps

- Canonical IR is documented as the target fact layer, and the worker now writes validated `typed_nodes.json`, `source_spans.json`, `transformation_ledger.json`, C2 `relationships.json`, `assets.json`, `annotations.json`, and manifest coverage-report evidence with core text, formula, figure, metadata, transcript cue nodes, conversion-phase ledger evidence, content-safe structure links, figure image references, coverage warnings, and pre-clean gate use of complete typed-node/source-span text evidence. Every route-specific structure has not fully moved to that contract.
- SourceSpan artifact coverage exists for typed nodes, converted Markdown line ranges, strict evidence schema validation, structured-data text sources, and transcript cue timing when raw cue evidence is available. The schema validates route-native precision records and coverage now lists missing native precision kinds, but converters still need to emit real PDF bounding boxes, DOCX run ranges, PPTX shape ids, XLSX cell ranges, transcript cue ids without timing, and YouTube cue ids before Phase C can close.
- CleaningPolicySnapshot, CleaningPatch generation, rejected patch reporting, Clean View assembly, and DocumentCleaningGate are shipped for the current cleanup path; remaining cleanup risk is rule quality and fixture breadth, not Phase D migration.
- Optional media and YouTube routes are partial CLI capabilities; verified promotion still needs broader real-sample, dependency, timeout, and transcript-quality evidence.
- Batch manifests now report evidence-backed rerun scope and executable failed/pending rerun. YouTube playlist input now expands into bounded child jobs with per-video parent status, but playlist rerun and deeper policy-affected or Canonical IR id-level batch targeting remain tied to later M5/C3 work.

## Closed Workflow Risks

- Default `standard` delivery publishes source-side Markdown through `latest_outputs.final_md`.
- Phase D cleanup now runs through `CleaningPolicySnapshot`, guarded `CleaningPatch` evidence, Clean View assembly, and DocumentCleaningGate before publication.
- Compatibility `curated_obsidian_kb` delivery is Obsidian-first and must be selected explicitly.
- `kbprep-cleanup --action finalize` must preserve the profile-specific final deliverable.
- CLI path safety distinguishes read and write boundaries.
- Provider-specific AI review clients are not maintained in this repository.
- Public rules must stay generic or sanitized; private rules belong under `.kbprep/rules/`.
- New external AI review integrations should run in shadow mode before apply mode.

## Review Closure Guards

- OCR normalization rules live in `rules/base/ocr_normalization.json`.
- Heading-level repair is intentionally pass-through by default.
- Standalone AI review uses caller-injected backends or an agent-independent external command protocol.
- Worker scenario coverage is split across `src/test/scenarios/*.test.ts`.
- Node subprocess timeout behavior is centralized in `src/runtime/subprocess.ts`.
- Pipeline orchestration should stay thin and delegate work to focused modules.

## Maintained Docs Surface

- `docs/kbprep-core-flow-design.md`
- `docs/kbprep-full-flowchart.html`
- `docs/flowchart/kbprep-flow.json`
- `docs/kbprep-development-implementation-plan.md`
- `docs/development/README.md`
- `docs/development/kbprep-implementation-status.json`
- `docs/capability-matrix.md`
- `docs/quality-loop.md`
- `docs/feedback-learning.md`
- `docs/known-issues.md`
- `docs/risk-tags.md`
- `docs/standalone-cli.md`
- `docs/agent-neutral.md`
- `docs/audit-remediation.md`
- `docs/hardcoded-cleaning-inventory.md`

Old generated showcase pages, historical implementation notes, and duplicate architecture summaries are not maintained design sources.

## Packaged `dist`

`dist/` is intentionally included in npm packages after build, but it is not tracked in git.
