# KBPrep Audit Remediation

This file tracks the remediation plan for the 2026-06-08 engineering audit and
keeps future reports from overstating evidence.

## Evidence Rules

- 真实 coverage means a coverage tool executed the Python tests and reported
  measured lines, missing lines, and a total percentage.
- 测试体量 is only a size signal, such as test file count, test case count, or
  test-line/source-line ratio. It must not be called coverage.
- TS scenario 集成测试 exercises the TypeScript worker harness and Python worker
  through subprocess-style flows. It is valuable integration evidence, not a
  replacement for focused Python unit tests.
- 能力矩阵证据 comes from `docs/capability-matrix.md` and
  `python/kbprep_worker/converter_capabilities.py`; partial routes stay partial
  until golden fixtures prove preservation.

## Remediation Status

| Finding | Classification | Remediation |
| --- | --- | --- |
| Python test evidence was described with a line-ratio coverage proxy. | Audit wording error | Added this evidence rule and `scripts/checks/audit-remediation.mjs`. |
| Python unit tests were thin around cleanup, HTML, curation, thresholds, and filesystem deletion. | Real gap | Added focused regression tests under `python/tests/`. |
| Business thresholds were scattered as unnamed literals. | Real gap | Added named threshold dictionaries and `scripts/checks/thresholds.mjs`. |
| Recursive deletion used direct `shutil.rmtree` in user-facing artifact paths. | Real gap | Added `kbprep_worker.fs_safety` and routed cleanup/publishing deletes through it. |
| Python lint and coverage were absent from CI. | Real gap | Added dev extras, npm scripts, CI gates for ruff, mypy, and measured coverage, and raised the coverage gate to 80%. |
| Partial converters need more golden fixtures before promotion. | Documented gap | Capability matrix remains the source of truth; this remediation does not promote partial routes. |

## Completion Evidence

Fresh completion evidence must include:

- `npm run build`
- `npm test`
- `npm run python:test`
- `npm run python:coverage`
- `npm run acceptance:round2`
- `npm run python:ruff`
- `npm run python:typecheck`
- `npm run audit:check`
- `npm run pack:check`
- `npm audit --audit-level=moderate`
