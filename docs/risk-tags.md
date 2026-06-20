# KBPrep Risk Tags

KBPrep uses risk tags to explain why a block was kept, discarded, treated as evidence, or sent to review. Tags are audit hints, not permission to rewrite source text.

## Preserve-Or-Review Signals

- `operation_step`: concrete step, workflow, or sequence.
- `tool_instruction`: tool, platform, account, setup, command, or UI operation detail.
- `parameter_or_number`: threshold, count, version, price, timing, identifier, or other numeric detail.
- `prompt_or_code`: prompt text, code, shell command, config, or structured snippet.
- `case_or_failure`: example, failed attempt, caveat, exception, retry, or lesson learned.
- `link_or_reference`: link text, filename, title, citation, or named source.
- `table_or_structured_data`: table, checklist, form, CSV-like content, or field/value structure.

Blocks with these signals should usually stay in the main output or go to `review_needed.md`. They should not be silently discarded.

## Pollution Signals

- `marketing_cta`: trial card, scan-to-join, discount, community invitation, paid promotion, or sales wording.
- `identity_wrapper`: author bio, self-introduction, credential block, or personal branding that is not needed for the knowledge content.
- `navigation_noise`: repeated table of contents, header/footer, page chrome, platform UI, or unrelated menu text.
- `image_only_artifact`: image placeholder, cover page, decorative graphic, or OCR artifact with no recoverable content.
- `duplicated_boilerplate`: repeated disclaimer, update channel, companion-video ad, or copied wrapper text.

Pollution can be discarded only when it does not carry concrete knowledge details. If a block mixes pollution with useful steps, split or review it rather than deleting the whole block.

## Strict Safety Rule

AI or human review patches may change block metadata only. They must not rewrite source text, line/page trace, protected details, or output provenance.
