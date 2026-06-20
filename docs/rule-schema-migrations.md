# Rule Schema Migrations

KBPrep rule files are runtime data. Changing their shape can change cleanup,
image classification, document-type detection, and feedback promotion behavior.

## Current Schemas

- `kbprep.cleaning_rules.v1`: cleanup rules, keyword sets, and optional `rule_groups`.
- `kbprep.document_type_signals.v1`: document-type detection signals.
- `kbprep.obsidian_template.v1`: Obsidian rendering templates.
- `kbprep.ocr_normalization.v1`: OCR normalization replacements.
- `kbprep.title_filters.v1`: title cleanup filters.

For `kbprep.cleaning_rules.v1`, `keyword_sets` names are validated against the
supported runtime vocabulary. String lists must contain non-empty strings.
Pattern lists such as `evidence_patterns` and `protected_patterns` must contain
objects with non-empty `label` and `pattern` fields.

## Migration Rules

1. Do not silently change an existing schema shape.
2. Add a new schema name when fields are removed, renamed, or their meaning changes.
3. Keep old schema readers until existing bundled rules are migrated.
4. Update `scripts/checks/rule-schema.mjs` in the same change as any schema change.
5. Add or update tests that load the affected rule file through the real loader.

## `rule_groups`

For `kbprep.cleaning_rules.v1`, `rule_groups` is metadata for auditability and
documentation. Default loading behavior is unchanged.

Each group may reference:

- `rules`: IDs that must exist in the same file's `rules[]`.
- `keyword_sets`: names that must exist in the same file's `keyword_sets`.

`npm run pack:check` runs `scripts/checks/rule-schema.mjs` and fails if a group
references a missing rule or keyword set, or if a cleanup keyword set uses an
unsupported name or value shape.

## Marketing Wrapper Passthrough Titles

`marketing_wrapper_passthrough_titles` keeps source-specific wrapper-title
exceptions in rule data instead of Python code. For example, a course title that
looks like a marketing wrapper can be preserved by the selected cleanup profile
without reintroducing a hardcoded business term into `classify_blocks.py`.

`npm run pack:check` validates that this field remains a string list, and
`scripts/checks/cleaning-hardcodes.mjs` verifies the source term lives in `rules/`
rather than in worker code.

## Owner-Facing Rule

Feedback does not become a permanent cleanup rule automatically. It first becomes
a proposal, and only an explicit accept command promotes it.
