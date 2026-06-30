# KBPrep Core Flow Design

## 1. Product Boundary

KBPrep is a local CLI and core workflow for turning source material into clean, traceable Markdown deliverables.

KBPrep owns:

- source inspection
- deterministic conversion routing
- Canonical IR construction
- source evidence preservation
- quality gates
- deterministic cleanup
- guarded review patches
- source-side publication
- feedback-to-rule proposals

KBPrep does not own:

- vector databases
- search indexes
- graph databases
- SaaS operation
- payment systems
- multi-tenant permissions
- provider-specific AI clients
- AI development agent host adapters
- custom OCR engine development

The maintained interface is CLI commands, worker contracts, and JSON artifacts. External agent hosts may call those interfaces, but their host-specific code does not belong in this repository.

## 2. Design Principles

1. The source is never overwritten.
2. Canonical IR is the immutable fact layer after conversion.
3. Markdown is the final user-facing render target, not the internal source of truth.
4. Every conversion route is explicit, auditable, and reproducible.
5. Conversion quality is checked before classification and cleanup.
6. Cleanup is deterministic by default and must not require a model on the hot path.
7. AI or human review may only return guarded patch or rule-proposal data.
8. Risky cleanup keeps the original text and records a warning.
9. A failed run does not update the last successful deliverable.
10. User feedback becomes a proposal first, never an accepted long-term rule automatically.

## 3. End-To-End Flow

```text
user input
-> job orchestration
-> input inspection
-> route selection
-> converter adapter
-> Canonical IR builder
-> conversion quality gate
-> non-destructive normalization
-> structure manifest
-> classification pack
-> document type snapshot
-> cleaning policy snapshot
-> internal cleaning-unit plan
-> deterministic cleaning patches
-> patch quality gate
-> Clean View assembly
-> document cleaning gate
-> Markdown and assets render
-> publish gate
-> atomic source-side publication
-> feedback proposal path when the user gives feedback
```

If the input is unsupported, the job stops before conversion. If the input is supported but cannot pass a hard quality gate, the job fails and no final deliverable is updated.

## 4. Input And Source Identity

Supported input sources are explicit local files, local folders, and future URL sources that have a declared route.

Each job records a `SourceSnapshot`:

- source path or URL
- source kind
- source size
- content hash
- collected time
- owner-supplied options
- output profile
- route eligibility
- dependency requirements

Local files are the maintained CLI path. YouTube and media routes are target capabilities until the capability matrix and tests mark them available.

## 5. Conversion Routing

Each source kind has one default conversion route. Route selection is not an engine competition.

Route policy:

- Markdown, text, code, JSON, CSV, TSV, subtitles, and similar text sources use direct readers.
- Modern Office sources use the declared Office route.
- EPUB uses the declared EPUB route.
- PDF uses the diagnosis-selected three-tier route defined below.
- Images use the declared OCR route only when the dependency is available.
- Legacy Office is intentionally unsupported (owner declined adaptation); convert it to PDF or modern Office first.
- Local audio and video must become transcript evidence before classification.
- YouTube uses available subtitles first; if subtitles are unavailable, the media transcript route may be used when dependencies are available.
- MOBI remains unsupported until the owner reopens the scope.

PDF route policy:

1. Tier 1, `pymupdf4llm`: use when the text layer is trusted and layout is simple, such as single-column pages with low image density and no complex table or mixed visual structure. This tier replaces flat `get_text("text")` output as the target lightweight PDF path.
2. Tier 2, `mineru_txt` or `mineru_auto`: use when the text layer is trusted but layout is complex, such as multi-column papers, table-heavy reports, image/text interleaving, slide-like pages, or sources where reading order cannot be trusted from flat text extraction.
3. Tier 3, `mineru_ocr`: use when the text layer is not trusted, including scanned pages, garbled text, CID or ToUnicode mapping risk, high image coverage, or other evidence that embedded text should be superseded.

PDF diagnosis must record the evidence used to choose the tier. The minimum evidence set is:

- text-layer trust signals
- layout complexity signals
- image coverage signals
- table or multi-column signals when available
- CID, ToUnicode, replacement-character, private-use, or control-character signals when available
- dependency availability and selected route

For large PDFs, diagnosis may use representative page sampling, but the sample strategy must be recorded. Sampling must not hide a hard failure discovered by the conversion quality gate.

PDF may perform one automatic upgrade after the first conversion attempt when the conversion quality gate rejects the result. The upgrade must use recorded evidence and must not become an engine competition. Other source kinds do not silently cascade through multiple engines.

Required PDF routing acceptance cases:

- simple single-column PDF -> Tier 1 `pymupdf4llm`
- English simple text PDF -> Tier 1 without Chinese-ratio false rejection
- multi-column paper -> Tier 2 `mineru_txt` or `mineru_auto`
- table-heavy PDF -> Tier 2 `mineru_txt` or `mineru_auto`
- scanned PDF -> Tier 3 `mineru_ocr`
- CID or ToUnicode-damaged PDF -> Tier 3 `mineru_ocr`

## 6. Canonical IR

Canonical IR is the internal document model used after conversion and before cleanup.

Required objects:

- `CanonicalDocument`
- `SourceSnapshot`
- `TypedNode`
- `SourceSpan`
- `Asset`
- `Relationship`
- `AnnotationSet`
- `TransformationLedger`

`TypedNode` may represent headings, paragraphs, lists, tables, code, formulas, figures, quotes, transcript cues, metadata, or structured data.

`SourceSpan` must point back to the source:

| Source | Required location evidence |
| --- | --- |
| PDF | page, bounding box or text block, image reference when available |
| DOCX | paragraph index, run range, table index, relationship id when available |
| PPTX | slide number, shape id, z-order, notes reference when available |
| XLSX | sheet name, cell range, formula reference, merged-cell evidence when available |
| HTML | DOM path, text range, asset reference when available |
| Markdown or text | line range or byte range |
| Transcript | start time, end time, speaker or cue id when available |
| YouTube | video id, subtitle cue, chapter, playlist item when available |

Canonical IR is append-only for evidence. Cleanup and rendering create derived views and ledger records instead of rewriting the source facts.

## 7. Conversion Quality Gate

The conversion quality gate runs after Canonical IR construction and before classification or cleanup.

It checks:

- route decision evidence
- readable text where text is expected
- page, sheet, slide, cue, or record order
- missing headings, tables, images, links, code, formulas, and transcript cues where detectable
- OCR or text-layer rejection evidence
- source span coverage
- conversion warnings and dependency failures

Hard failure means:

- classification does not run
- cleanup does not run
- final output is not published
- the user receives a concrete failure report

## 8. Classification

Classification happens after the conversion quality gate and before cleanup.

The classifier receives a bounded `ClassificationPack`, not an unlimited source dump.

The result is saved as `DocumentTypeSnapshot`:

- `primary_content_type`
- `content_form`
- `content_traits`
- classifier version
- schema version
- source evidence references
- confidence and warnings

Changing cleanup rules must not force reclassification. Reclassification is required only when source content, Canonical IR, classification pack, or classification schema changes.

## 9. Cleaning Policy Library

The Cleaning Policy Library contains:

- packaged base rules
- document-type rules
- source rules
- project rules
- user rules
- dictionaries
- protection rules
- accepted proposals
- rejected proposal memory
- examples and counterexamples
- promotion history

Private user rules live under `.kbprep/rules/`. Public `rules/` contains only generic or sanitized rules.

Policy priority:

```text
system structural protection
-> current job rules
-> source-specific rules
-> project rules
-> user rules
-> document-type rules
-> content-form rules
-> packaged base rules
```

Conflict handling:

- protect wins over remove
- more specific scope wins over broader scope
- same-scope conflict keeps original text and records a warning
- uncertainty keeps original text

## 10. Cleaning Policy Snapshot

`CleaningPolicySnapshot` records the exact policy used for a run:

- document type snapshot hash
- active rule ids
- active dictionary ids
- active protection ids
- disabled rule ids
- rule sources
- conflict resolutions
- user and project preferences
- compiler version
- rule set hash
- dictionary hash

The same Canonical IR, document type snapshot, and cleaning policy snapshot must produce the same Clean View.

## 11. Internal Cleaning Units

Cleaning units are internal execution units. They are not user-facing output, retrieval material, or final document structure.

Planning rules:

- natural document sections stay together
- tables, code, formulas, prompt examples, ordered steps, and transcript cues remain protected
- each unit has read-only neighboring context when needed
- each unit may only modify nodes assigned to it
- unit ids must be traceable in patch and quality reports

The final deliverable is a complete document, not a set of unit outputs.

## 12. Cleaning Patch And Clean View

Cleanup creates `CleaningPatch` records before any change is applied.

Each patch records:

- patch id
- document id
- cleaning unit id
- target node id
- action
- before text or structure
- after text or structure
- rule id
- reason code
- source span
- evidence refs
- policy snapshot hash

The patch gate rejects unsafe changes and keeps the original text. Rejected patches are recorded in `rejected_patches.jsonl`.

Clean View is assembled from Canonical IR plus accepted patches in original document order. Clean View assembly may restore structural continuity, but it must not summarize, rewrite, or invent source content.

## 13. Quality Gates

| Gate | Position | Blocks publication |
| --- | --- | --- |
| `conversion_quality_gate` | after Canonical IR construction | yes |
| `patch_quality_gate` | before a cleaning patch is accepted | unsafe patch only |
| `document_cleaning_gate` | after Clean View assembly | yes |
| `publish_quality_gate` | before final files are written | yes |

Quality reports must be user-readable and machine-readable. Strict errors block publication. Warnings are allowed only when the final deliverable remains safe to use.

## 14. Publication

Standard profile output is source-side:

```text
<source-folder>/<source-stem>.md
<source-folder>/<source-stem>.assets/
```

When the source itself is Markdown:

```text
<source-folder>/<source-stem>.cleaned.md
<source-folder>/<source-stem>.assets/
```

The job directory under `.kbprep/jobs/<job_id>/` stores process evidence, quality reports, failure reports, rejected patches, discarded content, and logs.

`latest_outputs` points to the active profile deliverable. Failed runs must not update the last successful output.

## 15. Feedback Learning

Feedback creates proposals first.

Proposal records include:

- action
- scope
- pattern or structured matcher
- examples
- counterexamples
- source evidence
- reason
- confidence
- confirmation requirement
- created-from-run reference

Only an explicit accept command promotes a proposal into accepted rules. Rejected proposals are remembered and not loaded by deterministic cleanup.

## 16. Batch And Playlist Behavior

A batch parent job expands input into child jobs. Each child job runs the same gates as a single source.

Parent status:

- all children succeed: `completed`
- some children succeed and some fail: `completed_with_warnings`
- all children fail: `failed`
- expansion fails before child jobs exist: `failed`

Each successful child publishes its own source-side deliverable and evidence.

## 17. Job Status

| Status | Meaning |
| --- | --- |
| `completed` | all hard gates passed and final deliverable was published |
| `completed_with_warnings` | final deliverable was published with non-blocking warnings |
| `failed` | supported input entered processing but could not pass a hard gate |
| `unsupported` | input kind is not in the supported capability set |
| `cancelled` | user cancelled before completion |

There is no final `review_required` status. Uncertain content is preserved with warnings or proposals. Unsafe publication is a failure.

## 18. Acceptance Standard

A KBPrep change is acceptable only when:

- source evidence remains traceable
- conversion quality is checked before cleanup
- deterministic cleanup can run without a model
- guarded review cannot bypass quality gates
- source-side publication preserves previous successful output on failure
- feedback remains proposal-first
- capability claims match tests or fixtures
- protected design, flowchart, implementation plan, and governance checks agree
