# KBPrep

KBPrep is a local CLI for turning source material into quality-checked, traceable Markdown deliverables.

The project boundary is the source-to-deliverable quality loop:

1. inspect the input and declare the selected capability
2. choose one deterministic conversion route
3. preserve source evidence in auditable artifacts
4. build toward a Canonical IR fact layer
5. run conversion quality checks before cleanup
6. classify document type from bounded evidence
7. compile deterministic cleanup rules and private user preferences
8. reject unsafe cleanup changes and preserve original text
9. publish source-side Markdown and assets only after hard gates pass
10. turn feedback into rule proposals before promotion

KBPrep does not maintain AI development agent adapters. Calling environments should use the CLI and documented JSON artifacts when they need their own skill, plugin, or host integration.

## Current State

The current codebase already has a Python worker, a Node CLI bridge, conversion routes, quality reports, source-side publication, and proposal-first feedback. It is not yet the full target architecture.

Target design and current status are tracked in:

- [docs/kbprep-core-flow-design.md](docs/kbprep-core-flow-design.md)
- [docs/kbprep-full-flowchart.html](docs/kbprep-full-flowchart.html)
- [docs/kbprep-development-implementation-plan.md](docs/kbprep-development-implementation-plan.md)
- [docs/development/kbprep-implementation-status.json](docs/development/kbprep-implementation-status.json)
- [docs/capability-matrix.md](docs/capability-matrix.md)
- [docs/quality-loop.md](docs/quality-loop.md)
- [docs/feedback-learning.md](docs/feedback-learning.md)
- [docs/standalone-cli.md](docs/standalone-cli.md)

Do not claim a source format or target route is fully supported unless the capability matrix links it to named tests or fixtures.

## CLI

Standalone commands:

```bash
kbprep-preflight --help
kbprep-analyze --input ./source.pdf --output ./.kbprep/analyze
kbprep-prepare --input ./source.pdf --output ./.kbprep/source --force
kbprep-apply-review --run-dir ./.kbprep/source/runs/<run-id> --patch-file review.patch.json
kbprep-feedback --run-dir ./.kbprep/source/runs/<run-id> --feedback-text "下次删除「关注公众号」这种污染"
kbprep-feedback --accept-proposal latest --confirm-rule-acceptance
kbprep-cleanup --output ./.kbprep/source --dry-run
kbprep-batch --input ./sources --output ./.kbprep/batch
```

The CLI prints JSON envelopes for worker results. Failures use the same shape with `ok: false`, an error code, warnings when available, and evidence paths when available.
Batch runs write `batch_manifest.json` with parent status, per-file status, skipped unsupported files, and evidence-backed rerun scope. This is the live batch status summary. After a batch output root is finalized with `kbprep-cleanup --action finalize`, cleanup writes `kbprep_batch_manifest.json`; that file is only the retention manifest proving final deliverables were preserved before temporary process artifacts were removed.

## Output

The maintained standard profile publishes beside the source:

```text
<source-folder>/<source-stem>.md
<source-folder>/<source-stem>.assets/
```

When the source is Markdown, KBPrep avoids overwriting it:

```text
<source-folder>/<source-stem>.cleaned.md
<source-folder>/<source-stem>.assets/
```

Process artifacts remain under the chosen output directory or job directory. Failed runs must not update the previous successful deliverable.

Successful runs expose `latest_outputs.publish_report`. Runs blocked after quality checks keep `publish_report.json` in the run directory so the owner can see why final publication did not happen. Runs blocked earlier by the pre-clean conversion gate report `conversion_quality_report.json` and `error_report.json` in the error envelope details instead.

## Runtime

KBPrep creates its own Python runtime at `.kbprep/venv` inside the package directory. It installs worker dependencies there instead of relying on system Python packages.

Current worker dependencies include converter and OCR tooling. KBPrep should use proven open-source tools where possible; it should not become a custom OCR project.

First-run setup is split into visible steps: create venv, upgrade packaging tools, install worker dependencies, and run the setup-env probe. Advanced operators can override the bootstrap Python with `KBPREP_BOOTSTRAP_PYTHON` or configured `python_path`; setup timeout failures include stderr evidence.

For direct Python worker development, use the managed project environment:

```bash
node scripts/python-venv.mjs --print-python
node scripts/python-venv.mjs -m kbprep_worker.cli --help
```

## Build And Test

```bash
npm install
npm run build
npm test
npm run pack:check
```

Use the release gate before publishing:

```bash
npm run release:check
```

When `F:\Obsidian-Vault` is available, run the isolated real-document smoke suite as an additional local release check:

```bash
npm run vault:smoke
```

`vault:smoke` copies representative files to a temporary directory before running prepare or batch. It must not write final Markdown or assets back into the original Obsidian vault.

## Agent Usage

Agents should treat KBPrep as a CLI tool plus documented protocols:

- call the CLI
- read quality and review artifacts
- return a validated patch or rule proposal
- let KBPrep apply changes and rerun gates

The repository intentionally does not ship AI development agent adapter logic.
