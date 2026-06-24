# KBPrep Known Issues And Roadmap

This file tracks known product and engineering gaps that are not hidden defects.

## Current Target Gaps

- Canonical IR is documented as the target fact layer, and the worker now writes validated `typed_nodes.json`, `source_spans.json`, `transformation_ledger.json`, and manifest coverage-report evidence with core text, formula, figure, metadata, transcript cue nodes, conversion-phase ledger evidence, and pre-clean gate use of complete typed-node/source-span text evidence. Every route-specific structure has not fully moved to that contract.
- SourceSpan artifact coverage exists for typed nodes, converted Markdown line ranges, strict evidence schema validation, structured-data text sources, and transcript cue timing when raw cue evidence is available, but route-native precision such as PDF bounding boxes, DOCX run ranges, PPTX shape ids, XLSX cells, and YouTube cue ids still needs converter-specific evidence.
- CleaningPolicySnapshot now records the first policy input/hash artifact, but full reproducibility coverage still needs implementation.
- CleaningPatch and Clean View are target contracts; current cleanup artifacts are not fully migrated.
- Optional media and YouTube routes require dependency checks, sample evidence, and capability promotion before they are current CLI promises.
- Batch manifests now report evidence-backed rerun scope, but executable selective rerun remains limited by available run metadata and current worker contracts.

## Closed Workflow Risks

- Default `standard` delivery publishes source-side Markdown through `latest_outputs.final_md`.
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
