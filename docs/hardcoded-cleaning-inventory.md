# Hardcoded Cleaning Inventory

This inventory records known hardcoded cleanup behavior that must move into cleaning dictionaries or document templates.

The goal is not to delete useful cleanup knowledge. The goal is to stop applying one source/domain's cleanup rules to every document.

## Must Move To Dictionaries

| File | Current hardcoding | Target |
| --- | --- | --- |
| `python/kbprep_worker/clean_rules.py` | `PROMOTIONAL_LINE_RE` contains public account, short-video, subscription, QR, group, and purchase language | `rules/base/obvious_noise.json` for universal CTA; `.kbprep/rules/templates/self_media_course.json` for private platform/source terms |
| `python/kbprep_worker/clean_rules.py` | `CONTEXTUAL_CTA_KEYWORDS`, `TUTORIAL_INDICATORS`, and knowledge-term heuristics are constants | rule dictionaries with document-type scope and provenance |
| `python/kbprep_worker/classify_blocks.py` | Classification previously embedded CTA, refund, footer, evidence, marketing-wrapper, wrapper-title passthrough, business-context, transcript-filler, step, prompt, and tool/parameter regexes | main classification signals now load from dictionaries; remaining code-only checks are structural shape checks such as code/table markup and garbled-text ratio |
| `python/kbprep_worker/images.py` | QR/social/platform image filtering terms were embedded in regex and allow lists | migrated to image cleanup indicators in dictionaries |
| `python/kbprep_worker/diagnose/` | QR/CTA/profile noise detection was embedded in source diagnosis | migrated to dictionary-backed diagnosis signals |
| `python/kbprep_worker/prepare_diagnosis.py` | source title heuristics included platform and publishing-wrapper terms | migrated to `rules/base/title_filters.json` |
| `python/kbprep_worker/quality/` | CTA leak detection included fixed Chinese purchase/group phrases and QR image markers | migrated to the same cleaning dictionaries used by cleanup |
| `python/kbprep_worker/obsidian_kb/` | social platforms, author bio terms, case/method/cognition categories, source-brand replacements, and brand-program packaging terms were constants | generic Obsidian export now defaults to `rules/templates/obsidian_generic.json`; private course/self-media behavior requires `.kbprep/rules/templates/obsidian_course_kb.json` |
| `python/kbprep_worker/feedback/` | feedback action detection included fixed cleanup/marketing intent words | migrated to `feedback_protect_intent_terms` and `feedback_discard_intent_terms` in cleaning dictionaries |
| `python/kbprep_worker/document_type.py` | document type classification embedded report/course/transcript/webpage keyword regexes | migrated to `rules/base/document_type_signals.json` |

## Migration Progress

- `python/kbprep_worker/clean_rules.py`: first migration complete. Promotional-line patterns, CTA keywords, tutorial indicators, and knowledge protection terms now load from JSON dictionaries instead of Python constants.
- `python/kbprep_worker/quality/`: first migration complete. CTA text and QR image pollution gates now load from the same JSON dictionaries as cleanup, and the quality report records `cleaning_rule_sources`.
- `python/kbprep_worker/images.py`: first migration complete. QR/CTA image, marketing image, operation screenshot, proof screenshot, and educational-heading indicators now load from JSON dictionaries.
- `python/kbprep_worker/diagnose/`: first migration complete. Readable QR/CTA text diagnosis now uses the same JSON dictionaries and reports `cleaning_rule_sources`.
- `python/kbprep_worker/classify_blocks.py`: main classification migration complete. CTA, refund, footer, evidence, marketing-wrapper, wrapper-title passthrough, back-matter, business-method context, transcript-filler, operation-step, prompt, and tool/parameter protection signals now load from cleaning dictionaries, and the pipeline passes the selected profile into the classifier.
- `python/kbprep_worker/obsidian_kb/`: migration complete. Generic Obsidian export uses `rules/templates/obsidian_generic.json`; curated course/self-media category names, author/profile terms, source-brand replacements, and brand-program packaging terms load through explicit `ObsidianContext` from `.kbprep/rules/templates/obsidian_course_kb.json`.
- `python/kbprep_worker/prepare_diagnosis.py`: first migration complete. Source title split/reject terms now load from `rules/base/title_filters.json`.
- `python/kbprep_worker/feedback/`: first migration complete. Feedback action intent terms now load from cleaning dictionaries instead of Python regex constants.
- `python/kbprep_worker/document_type.py`: first migration complete. Document type format hints and content patterns now load from `rules/base/document_type_signals.json`.
- `python/kbprep_worker/cleaning_registry.py`: cleaning rule package selection now uses a declared registry, so base rules, document-type rules, profile templates, requested templates, and accepted user rules have visible route reasons instead of being hidden in one loader function.
- `python/kbprep_worker/rule_loader.py`: loaded rules are grouped by use case (`cleaning`, `image`, `classification`, `feedback`) while preserving compatibility properties for existing code.
- `scripts/checks/cleaning-hardcodes.mjs`: scans key Python worker files, decodes Python string literals through AST, and fails if platform/marketing cleanup terms are reintroduced into code instead of `rules/`.
- `rules/base/obvious_noise.json`: generic cleanup signals that apply by default.
- `rules/base/document_type_signals.json`: generic document type classification signals used before document-type-specific cleaning.
- `rules/base/title_filters.json`: title/source wrapper filters used before rendering output names.
- `rules/templates/obsidian_generic.json`: default generic Obsidian output template.
- `.kbprep/rules/templates/self_media_course.json`: optional private self-media/course platform cleanup. It is not loaded by the generic `standard` profile unless requested or selected by profile.
- `.kbprep/rules/templates/obsidian_course_kb.json`: optional private curated course/self-media Obsidian output template. It is not the generic Obsidian exporter and is excluded from git and npm packaging.

## Important Distinction

Some terms are useful universal signals, such as QR codes or obvious purchase calls. They still need to be represented as rules, not buried as Python constants, so users can inspect, disable, override, or extend them.

## Verification Target

After migration, release checks run:

```bash
node scripts/checks/cleaning-hardcodes.mjs
```
