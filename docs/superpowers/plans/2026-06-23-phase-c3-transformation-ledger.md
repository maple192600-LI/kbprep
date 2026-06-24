# Phase C3 TransformationLedger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every development stage must finish with an independent reviewer subagent before the next stage begins.

**Goal:** Add a validated Canonical IR `TransformationLedger` artifact that records conversion-phase evidence as ordered, append-only ledger entries and is referenced by the Canonical IR manifest.

**Architecture:** Keep the shipped Canonical IR status `partial`. Add a focused `canonical_ledger.py` module for ledger schema, writer, and validator; integrate it through `canonical_ir.py` so the existing conversion-stage artifact writer emits the ledger before the pre-clean conversion gate runs. The conversion gate continues to validate through `validate_canonical_ir_manifests()`, which now checks ledger references and payloads when the manifest claims a ledger artifact.

**Tech Stack:** Python worker, project unittest via `node scripts/python-venv.mjs`, TypeScript/Vitest scenario checks through existing npm scripts, GitHub Actions CI.

---

## Product Outcome

C3 gives the user an auditable record of what happened during conversion and Canonical IR construction. After `kbprep prepare`, the run directory should include:

- `canonical_ir/transformation_ledger.json`
- a `canonical_ir/manifest.json` reference to that ledger
- conversion-gate validation that rejects broken claimed ledger evidence before cleanup starts

This is not a promotion of `canonical_ir_contract` to `implemented`. Remaining Phase C work still includes route-native source-span precision, relationships, assets, annotations, C4 coverage reporting, C5 gate semantics, and Markdown regeneration from IR plus accepted changes.

## Scope

### Modify

- `python/kbprep_worker/canonical_ir.py`
  - Add the ledger artifact to `CanonicalArtifactState`.
  - Call the new ledger writer after typed nodes/source spans are written and validated.
  - Add ledger path to the Canonical IR manifest `artifacts`.
  - Add `transformation_ledger_available` to manifest `coverage`.
  - Validate ledger manifest references.
- `python/kbprep_worker/canonical_nodes.py`
  - Keep typed-node artifact validation separate from manifest/ledger orchestration so `canonical_ir.py` stays within the project size boundary.
- `python/kbprep_worker/error_codes.py`
  - Register the ledger validation error code used by the conversion gate.
- `python/kbprep_worker/quality/conversion_gate.py`
  - Ensure ledger validation issues map to conversion-gate strict errors and an actionable failure message.
- `python/tests/test_canonical_ir_ledger.py`
  - Add ledger artifact schema, reference, and manifest-validator tests.
- `python/tests/test_canonical_ir_manifest.py`
  - Add end-to-end prepare/gate tests proving ledger emission and gate blocking for broken claimed ledger evidence.
- `src/errorCodes.ts`
  - Keep the TypeScript error-code contract in sync with the Python worker.
- `docs/development/00-current-state-and-gap.md`
  - Narrow the Canonical IR gap after C3.
- `docs/development/02-canonical-ir-contract.md`
  - Move `TransformationLedger` from target-only wording into the shipped partial boundary.
- `docs/development/development-roadmap.md`
  - Mark C3 as landed after implementation.
- `docs/development/kbprep-implementation-status.json`
  - Keep `canonical_ir_contract.status` as `partial`, but add ledger implementation and tests to scope/evidence.
- `docs/known-issues.md`
  - Remove or narrow stale ledger-missing wording while keeping remaining IR gaps honest.

### Create

- `python/kbprep_worker/canonical_ledger.py`
  - Own the ledger schema, event construction, path-safe validation, and error type.
- `python/tests/test_canonical_ir_ledger.py`
  - Own isolated ledger unit tests.

### Do Not Modify

- `docs/kbprep-core-flow-design.md`
- `docs/kbprep-full-flowchart.html`
- `docs/flowchart/kbprep-flow.json`
- `docs/capability-matrix.md` route rows
- README main workflow wording

These sources already describe the target design or route-level capabilities. C3 implements an existing target slice and does not change route support.

## Artifact Contract

Write `canonical_ir/transformation_ledger.json` as a JSON object, not JSONL, so it can carry the same header and run-reference safety model as `typed_nodes.json` and `source_spans.json`.

```json
{
  "schema": "kbprep.canonical_ir_transformation_ledger.v1",
  "document_id": "doc_aabbccddeeff0011",
  "canonical_ir_manifest": "canonical_ir/manifest.json",
  "converted_artifact": "converted.md",
  "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
  "source_spans_artifact": "canonical_ir/source_spans.json",
  "created_from_run": "run_example",
  "entry_count": 6,
  "entries": [
    {
      "entry_id": "e_000001",
      "ordinal": 1,
      "stage": "conversion",
      "operation": "route_decision_recorded",
      "producer": "canonical_ir",
      "target_node_ids": [],
      "target_span_ids": [],
      "evidence_refs": ["conversion_report.json"],
      "details": {
        "converter": "direct_text",
        "actual_route": "direct_text",
        "route_decision_hash": "0123456789abcdef"
      },
      "details_hash": "fedcba9876543210"
    }
  ]
}
```

Required initial operations:

- `route_decision_recorded`
- `converted_markdown_written`
- `typed_nodes_artifact_written`
- `typed_nodes_artifact_validated`
- `source_spans_artifact_written`
- `source_spans_artifact_validated`

Validation rules:

- `schema` must equal `kbprep.canonical_ir_transformation_ledger.v1`.
- `document_id` must match the Canonical IR manifest.
- `canonical_ir_manifest`, `converted_artifact`, `typed_nodes_artifact`, and `source_spans_artifact` must be relative run paths and must not escape `run_dir`.
- `entry_count` must equal `len(entries)`.
- `entries` must be a list.
- Each entry `ordinal` must equal its 1-based position.
- Each entry `entry_id` must equal `e_000001`, `e_000002`, and so on.
- `stage`, `operation`, and `producer` must be non-empty strings.
- `target_node_ids`, `target_span_ids`, and `evidence_refs` must be lists of strings.
- Every `evidence_refs` item must be a safe run-relative path.
- `details` must be a JSON object.
- `details_hash` must equal the stable hash of `details`.
- The six required initial operations must appear exactly once in order.

Compatibility rule:

- New C3 writer output must always include `artifacts.transformation_ledger` and `coverage.transformation_ledger_available: true`.
- Validator should continue allowing older partial manifests that do not claim a transformation ledger, so historical run artifacts remain readable.
- If a manifest claims `coverage.transformation_ledger_available: true`, it must reference and validate `artifacts.transformation_ledger`.
- If `artifacts.transformation_ledger` exists, `coverage.transformation_ledger_available` must be `true`.

## Parallel Development Strategy

Safe parallel work:

- Read-only exploration can run in parallel. Already completed:
  - Canonical IR schema/manifest exploration.
  - Pipeline/conversion-gate exploration.
  - Docs/status/capability exploration.
- After Stage 2 and Stage 3 implementation, target tests, and independent reviewer approvals are complete, a docs worker can execute Stage 4 documentation updates while a separate read-only reviewer inspects final Python integration evidence; both must avoid editing the same files.
- Independent review subagents can run after each stage and after final integration.

Do not parallelize:

- Do not run multiple implementation agents against `canonical_ir.py`, `canonical_ledger.py`, or manifest validation at the same time.
- Do not update status/docs before Stage 2/3 implementation, target tests, and independent reviewer approvals prove the shipped boundary.
- Do not merge or push the C3 branch until independent final review and full checks pass.

## Stage Review Rule

After each stage below:

1. Run the stage's target tests.
2. Spawn an independent reviewer subagent.
3. The reviewer must inspect the changed files for that stage and run at least the stage target test.
4. If the reviewer says `CHANGES REQUIRED`, fix every issue and re-review.
5. Continue only after the reviewer says `APPROVED`.

This is mandatory because the owner requires every discovered issue to be fixed immediately, with no deferral or downgrade.

---

### Stage 1: Ledger Schema, Writer, And Validator

**Files:**
- Create: `python/kbprep_worker/canonical_ledger.py`
- Create: `python/tests/test_canonical_ir_ledger.py`

- [ ] **Step 1: Write failing ledger writer test**

Add this test to `python/tests/test_canonical_ir_ledger.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.canonical_ledger import (
    CANONICAL_IR_TRANSFORMATION_LEDGER_SCHEMA,
    validate_transformation_ledger_artifact,
    write_transformation_ledger_artifact,
)


class CanonicalIrTransformationLedgerTests(unittest.TestCase):
    def test_writer_records_conversion_and_ir_artifact_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            canonical_dir = run_dir / "canonical_ir"
            canonical_dir.mkdir()
            converted = run_dir / "converted.md"
            typed_nodes = canonical_dir / "typed_nodes.json"
            source_spans = canonical_dir / "source_spans.json"
            converted.write_text("# Note\n", encoding="utf-8")
            typed_nodes.write_text('{"node_count": 1}', encoding="utf-8")
            source_spans.write_text('{"span_count": 1}', encoding="utf-8")

            ledger_path = write_transformation_ledger_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                run_id="run_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                typed_nodes_available=True,
                source_spans_path=source_spans,
                source_spans_available=True,
                conversion={
                    "converter": "direct_text",
                    "actual_route": "direct_text",
                    "route_decision_hash": "abc123",
                },
            )

            payload = json.loads(ledger_path.read_text(encoding="utf-8"))
            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger_path,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertEqual(payload["schema"], CANONICAL_IR_TRANSFORMATION_LEDGER_SCHEMA)
        self.assertEqual(payload["document_id"], "doc_test")
        self.assertEqual(payload["canonical_ir_manifest"], "canonical_ir/manifest.json")
        self.assertEqual(payload["converted_artifact"], "converted.md")
        self.assertEqual(payload["typed_nodes_artifact"], "canonical_ir/typed_nodes.json")
        self.assertEqual(payload["source_spans_artifact"], "canonical_ir/source_spans.json")
        self.assertEqual(payload["created_from_run"], "run_test")
        self.assertEqual(payload["entry_count"], 6)
        self.assertEqual([entry["ordinal"] for entry in payload["entries"]], [1, 2, 3, 4, 5, 6])
        self.assertEqual([entry["entry_id"] for entry in payload["entries"]], [
            "e_000001",
            "e_000002",
            "e_000003",
            "e_000004",
            "e_000005",
            "e_000006",
        ])
        self.assertEqual([entry["operation"] for entry in payload["entries"]], [
            "route_decision_recorded",
            "converted_markdown_written",
            "typed_nodes_artifact_written",
            "typed_nodes_artifact_validated",
            "source_spans_artifact_written",
            "source_spans_artifact_validated",
        ])
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_ledger -v
```

Expected: fail with `ModuleNotFoundError` for `kbprep_worker.canonical_ledger`.

- [ ] **Step 3: Implement `canonical_ledger.py`**

Create `python/kbprep_worker/canonical_ledger.py` with this structure:

```python
"""Canonical IR TransformationLedger artifact builder and validator."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .canonical_routes import dict_or_empty

CANONICAL_IR_TRANSFORMATION_LEDGER_SCHEMA = "kbprep.canonical_ir_transformation_ledger.v1"
TRANSFORMATION_LEDGER_INVALID_CODE = "E_CANONICAL_IR_TRANSFORMATION_LEDGER_INVALID"
_REQUIRED_OPERATIONS = (
    "route_decision_recorded",
    "converted_markdown_written",
    "typed_nodes_artifact_written",
    "typed_nodes_artifact_validated",
    "source_spans_artifact_written",
    "source_spans_artifact_validated",
)
_ENTRY_ID_RE = re.compile(r"^e_\d{6}$")


@dataclass(frozen=True)
class TransformationLedgerValidationIssue:
    code: str
    message: str
    evidence: dict[str, Any]
```

Then implement:

- `write_transformation_ledger_artifact(...) -> Path`
- `_ledger_payload(...) -> dict[str, Any]`
- `_ledger_entries(...) -> list[dict[str, Any]]`
- `_entry(...) -> dict[str, Any]`
- `_artifact_summary(...) -> dict[str, Any]`
- `_stable_hash(payload: dict[str, Any]) -> str`
- `_relative_run_path(run_dir: Path, path: Path) -> str`
- `validate_transformation_ledger_artifact(...) -> list[TransformationLedgerValidationIssue]`
- `validate_transformation_ledger_reference(...) -> list[TransformationLedgerValidationIssue]`
- private validation helpers for header, entries, details hash, and safe run references

The implementation must use `atomic_write_json(..., trailing_newline=False)` and `pathlib.Path`.

Use these public function shapes:

```python
def write_transformation_ledger_artifact(
    *,
    run_dir: Path,
    document_id: str,
    run_id: str,
    converted_path: Path,
    typed_nodes_path: Path,
    typed_nodes_available: bool,
    source_spans_path: Path,
    source_spans_available: bool,
    conversion: dict[str, Any],
) -> Path:
    artifact_path = run_dir / "canonical_ir" / "transformation_ledger.json"
    payload = _ledger_payload(
        run_dir=run_dir,
        document_id=document_id,
        run_id=run_id,
        converted_path=converted_path,
        typed_nodes_path=typed_nodes_path,
        typed_nodes_available=typed_nodes_available,
        source_spans_path=source_spans_path,
        source_spans_available=source_spans_available,
        conversion=conversion,
    )
    atomic_write_json(artifact_path, payload, indent=2, trailing_newline=False)
    return artifact_path
```

```python
def validate_transformation_ledger_reference(
    *,
    run_dir: Path,
    artifacts: dict[str, Any],
    coverage: dict[str, Any],
    document_id: str,
    converted_path: Path,
) -> list[TransformationLedgerValidationIssue]:
    issues: list[TransformationLedgerValidationIssue] = []
    raw_ref = artifacts.get("transformation_ledger")
    if raw_ref is None:
        if coverage.get("transformation_ledger_available") is True:
            _add_issue(
                issues,
                "coverage.transformation_ledger_available requires artifacts.transformation_ledger",
                {"transformation_ledger_available": coverage.get("transformation_ledger_available")},
            )
        return issues
    if coverage.get("transformation_ledger_available") is not True:
        _add_issue(
            issues,
            "coverage.transformation_ledger_available must be true when artifacts.transformation_ledger exists",
            {"transformation_ledger_available": coverage.get("transformation_ledger_available")},
        )
        return issues
    ledger_path = _resolve_run_reference(run_dir, raw_ref, "transformation_ledger", issues)
    typed_nodes_path = _resolve_run_reference(run_dir, artifacts.get("typed_nodes"), "typed_nodes", issues)
    source_spans_path = _resolve_run_reference(run_dir, artifacts.get("source_spans"), "source_spans", issues)
    if ledger_path is None or typed_nodes_path is None or source_spans_path is None:
        return issues
    expected = run_dir / "canonical_ir" / "transformation_ledger.json"
    if ledger_path != expected.resolve():
        _add_issue(
            issues,
            "artifacts.transformation_ledger must reference canonical_ir/transformation_ledger.json",
            {"transformation_ledger": raw_ref, "expected": "canonical_ir/transformation_ledger.json"},
        )
    issues.extend(validate_transformation_ledger_artifact(
        run_dir=run_dir,
        ledger_path=ledger_path,
        document_id=document_id,
        converted_path=converted_path,
        typed_nodes_path=typed_nodes_path,
        source_spans_path=source_spans_path,
    ))
    return issues
```

Use this payload shape and entry helper:

```python
def _ledger_payload(
    *,
    run_dir: Path,
    document_id: str,
    run_id: str,
    converted_path: Path,
    typed_nodes_path: Path,
    typed_nodes_available: bool,
    source_spans_path: Path,
    source_spans_available: bool,
    conversion: dict[str, Any],
) -> dict[str, Any]:
    entries = _ledger_entries(
        run_dir=run_dir,
        converted_path=converted_path,
        typed_nodes_path=typed_nodes_path,
        typed_nodes_available=typed_nodes_available,
        source_spans_path=source_spans_path,
        source_spans_available=source_spans_available,
        conversion=conversion,
    )
    return {
        "schema": CANONICAL_IR_TRANSFORMATION_LEDGER_SCHEMA,
        "document_id": document_id,
        "canonical_ir_manifest": "canonical_ir/manifest.json",
        "converted_artifact": _relative_run_path(run_dir, converted_path),
        "typed_nodes_artifact": _relative_run_path(run_dir, typed_nodes_path),
        "source_spans_artifact": _relative_run_path(run_dir, source_spans_path),
        "created_from_run": run_id,
        "entry_count": len(entries),
        "entries": entries,
    }


def _entry(
    ordinal: int,
    *,
    stage: str,
    operation: str,
    evidence_refs: list[str],
    details: dict[str, Any],
    target_node_ids: list[str] | None = None,
    target_span_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "entry_id": f"e_{ordinal:06d}",
        "ordinal": ordinal,
        "stage": stage,
        "operation": operation,
        "producer": "canonical_ir",
        "target_node_ids": target_node_ids or [],
        "target_span_ids": target_span_ids or [],
        "evidence_refs": evidence_refs,
        "details": details,
        "details_hash": _stable_hash(details),
    }
```

Use this `validate_transformation_ledger_artifact(...)` flow:

```python
def validate_transformation_ledger_artifact(
    *,
    run_dir: Path,
    ledger_path: Path,
    document_id: str,
    converted_path: Path,
    typed_nodes_path: Path,
    source_spans_path: Path,
) -> list[TransformationLedgerValidationIssue]:
    issues: list[TransformationLedgerValidationIssue] = []
    payload = _read_required_json(ledger_path, "canonical_ir/transformation_ledger.json", issues)
    if payload is None:
        return issues
    _validate_header(
        run_dir=run_dir,
        payload=payload,
        document_id=document_id,
        converted_path=converted_path,
        typed_nodes_path=typed_nodes_path,
        source_spans_path=source_spans_path,
        issues=issues,
    )
    entries = payload.get("entries")
    if not isinstance(entries, list):
        _add_issue(issues, "transformation_ledger.entries must be a list", {"entries": entries})
        return issues
    _validate_entry_count(payload.get("entry_count"), len(entries), issues)
    _validate_entries(entries, run_dir, issues)
    return issues
```

Required private helper behavior:

- `_validate_header(...)` checks schema, document id, and the four artifact references.
- `_validate_entries(...)` checks entry id, ordinal, required string fields, list fields, safe evidence refs, details mapping, details hash, and exact required operation order.
- `_resolve_run_reference(...)` mirrors the run-dir boundary behavior from `canonical_spans.py`: reject non-string refs, absolute paths, `..`, and resolved paths outside `run_dir`.
- `_stable_hash(...)` must use `json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")`, SHA-256, and return the first 16 hex chars.
- `_add_issue(...)` always uses `TRANSFORMATION_LEDGER_INVALID_CODE`.

- [ ] **Step 4: Add validation failure tests**

Add tests to `python/tests/test_canonical_ir_ledger.py`:

```python
    def test_validator_rejects_entry_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["entry_count"] = 99
            ledger.write_text(json.dumps(payload), encoding="utf-8")

            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertTrue(any("entry_count must equal len(entries)" in issue.message for issue in issues))

    def test_validator_rejects_reordered_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["entries"][0], payload["entries"][1] = payload["entries"][1], payload["entries"][0]
            ledger.write_text(json.dumps(payload), encoding="utf-8")

            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertTrue(any("ordinal must match entry position" in issue.message for issue in issues))

    def test_validator_rejects_evidence_ref_that_escapes_run_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["entries"][0]["evidence_refs"] = ["../conversion_report.json"]
            ledger.write_text(json.dumps(payload), encoding="utf-8")

            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertTrue(any("evidence_refs must stay inside the run directory" in issue.message for issue in issues))

    def test_validator_rejects_details_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["entries"][0]["details"]["actual_route"] = "tampered"
            ledger.write_text(json.dumps(payload), encoding="utf-8")

            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertTrue(any("details_hash must match details" in issue.message for issue in issues))
```

Also add `_write_valid_ledger_fixture(root: Path) -> tuple[Path, Path, Path, Path, Path]` in the test file.

- [ ] **Step 5: Run ledger tests until they pass**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_ledger -v
```

Expected: all ledger tests pass.

- [ ] **Step 6: Stage 1 independent review**

Spawn an independent reviewer subagent with this task:

```text
Review Stage 1 only. Inspect python/kbprep_worker/canonical_ledger.py and python/tests/test_canonical_ir_ledger.py. Verify the ledger schema is versioned, document-bound, run-path safe, ordered, append-only by entry id/ordinal, details_hash-protected, and covered by tests. Run node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_ledger -v. Report APPROVED or CHANGES REQUIRED with concrete file/line issues.
```

Do not continue to Stage 2 until the reviewer says `APPROVED`.

---

### Stage 2: Manifest And Conversion Gate Integration

**Files:**
- Modify: `python/kbprep_worker/canonical_ir.py`
- Modify: `python/kbprep_worker/canonical_nodes.py`
- Modify: `python/kbprep_worker/error_codes.py`
- Modify: `python/kbprep_worker/quality/conversion_gate.py`
- Modify: `python/tests/test_canonical_ir_ledger.py`
- Modify: `python/tests/test_canonical_ir_manifest.py`
- Modify: `src/errorCodes.ts`
- Regression only: `python/tests/test_canonical_ir_schema.py` must stay in the focused test command, but C3 ledger-specific tests should not be added there.

- [ ] **Step 1: Add failing ledger manifest/reference assertions**

In `python/tests/test_canonical_ir_ledger.py`, add ledger-specific manifest/reference tests that assert:

```python
ledger_path = run_dir / "canonical_ir" / "transformation_ledger.json"
self.assertEqual(canonical_manifest["artifacts"]["transformation_ledger"], "canonical_ir/transformation_ledger.json")
self.assertTrue(canonical_manifest["coverage"]["transformation_ledger_available"])
self.assertTrue(ledger_path.exists())
self.assertEqual(ledger["schema"], "kbprep.canonical_ir_transformation_ledger.v1")
self.assertEqual(ledger["document_id"], canonical_manifest["document_id"])
```

- [ ] **Step 2: Add failing validator consistency tests**

Add tests to `python/tests/test_canonical_ir_ledger.py`:

```python
    def test_validator_rejects_transformation_ledger_available_without_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(run_dir, converted, coverage={"transformation_ledger_available": True})

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any("coverage.transformation_ledger_available requires artifacts.transformation_ledger" in issue.message for issue in issues))

    def test_validator_rejects_transformation_ledger_artifact_when_coverage_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"transformation_ledger": "canonical_ir/transformation_ledger.json"},
                coverage={"transformation_ledger_available": False},
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any("coverage.transformation_ledger_available must be true when artifacts.transformation_ledger exists" in issue.message for issue in issues))
```

Also add a positive control that a manifest with valid typed-node, source-span, and ledger artifact references returns no manifest-validator issues. This keeps ledger tests from being polluted by unrelated `E_CANONICAL_IR_SOURCE_SPANS_INVALID` failures.

- [ ] **Step 3: Add failing gate action test**

In `python/tests/test_canonical_ir_manifest.py`, add a test that writes a manifest claiming a ledger artifact, writes an invalid ledger payload, runs `run_pre_clean_conversion_gate`, and asserts:

```python
self.assertEqual(report["status"], "fail")
self.assertEqual(report["blocked_stage"], "cleanup")
self.assertEqual(report["canonical_ir_status"], "missing_or_invalid")
self.assertTrue(any(error.startswith("E_CANONICAL_IR_TRANSFORMATION_LEDGER_INVALID") for error in report["strict_errors"]))
self.assertTrue(any(action["action"] == "regenerate_canonical_ir" for action in report["failure_actions"]))
```

- [ ] **Step 4: Run tests and verify failures**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_ledger python.tests.test_canonical_ir_manifest python.tests.test_canonical_ir_schema -v
```

Expected: fail because manifest writer and validator do not yet know the ledger artifact.

- [ ] **Step 5: Integrate ledger into `canonical_ir.py`**

Update imports:

```python
from .canonical_ledger import (
    validate_transformation_ledger_reference,
    write_transformation_ledger_artifact,
)
```

Extend `CanonicalArtifactState`:

```python
    transformation_ledger_path: Path
    transformation_ledger_available: bool
```

After source spans are written and validated in `_write_canonical_artifacts`, call:

```python
    ledger_path, ledger_available = _write_validated_transformation_ledger(
        run_dir=run_dir,
        document_id=document_id,
        run_id=run_id,
        converted_path=converted_path,
        typed_nodes_path=typed_path,
        typed_nodes_available=typed_available,
        source_spans_path=spans_path,
        source_spans_available=spans_available,
        conversion=_conversion_snapshot(conversion_report, route_decision),
    )
```

Pass `run_id` into `_write_canonical_artifacts(...)`.

Add `_write_validated_transformation_ledger(...) -> tuple[Path, bool]` beside the typed/source-span helper functions.

Extend `_artifact_snapshot(...)` to include:

```python
"transformation_ledger": _relative_run_path(run_dir, transformation_ledger_path)
```

Extend `_coverage_snapshot(...)` to include:

```python
"transformation_ledger_available": transformation_ledger_available
```

Extend `_validate_coverage_snapshot(...)` to require boolean `transformation_ledger_available` only when the field is present, preserving older partial manifests that do not claim a ledger.

Extend `_validate_canonical_manifest(...)` after source-span validation:

```python
        for issue in validate_transformation_ledger_reference(
            run_dir=run_dir,
            artifacts=artifacts,
            coverage=coverage,
            document_id=str(manifest.get("document_id") or ""),
            converted_path=converted,
        ):
            _add_issue(issues, issue.code, issue.message, issue.evidence)
```

- [ ] **Step 6: Add conversion-gate failure action**

In `python/kbprep_worker/quality/conversion_gate.py::_failure_action`, add:

```python
    if code == "E_CANONICAL_IR_TRANSFORMATION_LEDGER_INVALID":
        return _action(code, "regenerate_canonical_ir", "Regenerate Canonical IR transformation ledger evidence before cleanup.")
```

- [ ] **Step 7: Run integration tests until they pass**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_ledger python.tests.test_canonical_ir_schema python.tests.test_canonical_ir_manifest -v
```

Expected: all tests pass.

- [ ] **Step 8: Stage 2 independent review**

Spawn an independent reviewer subagent:

```text
Review Stage 2 only. Inspect python/kbprep_worker/canonical_ir.py, python/kbprep_worker/canonical_nodes.py, python/kbprep_worker/error_codes.py, python/kbprep_worker/quality/conversion_gate.py, python/tests/test_canonical_ir_ledger.py, python/tests/test_canonical_ir_manifest.py, and src/errorCodes.ts. Verify transformation_ledger manifest references, coverage consistency, validator behavior, conversion-gate failure actions, error-code contract sync, and backward compatibility for old partial manifests that do not claim a ledger. Run node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_ledger python.tests.test_canonical_ir_schema python.tests.test_canonical_ir_manifest -v, treating python.tests.test_canonical_ir_schema as regression coverage only. Report APPROVED or CHANGES REQUIRED with concrete file/line issues.
```

Do not continue to Stage 3 until the reviewer says `APPROVED`.

---

### Stage 3: Pipeline And Scenario Coverage

**Files:**
- Modify: `python/tests/test_canonical_ir_manifest.py`
- Modify: `src/test/scenarios/worker-quality-gates-part1.test.ts` if the existing scenario can assert ledger presence without making tests brittle.

- [ ] **Step 1: Strengthen prepare end-to-end test**

In `python/tests/test_canonical_ir_manifest.py::test_prepare_writes_canonical_ir_and_document_manifests`, assert:

```python
            ledger_path = run_dir / "canonical_ir" / "transformation_ledger.json"
            self.assertTrue(ledger_path.exists())
            self.assertEqual(canonical_manifest["artifacts"]["transformation_ledger"], "canonical_ir/transformation_ledger.json")
            self.assertTrue(canonical_manifest["coverage"]["transformation_ledger_available"])
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertEqual(ledger["created_from_run"], envelope["data"]["run_id"])
            self.assertEqual(ledger["document_id"], canonical_manifest["document_id"])
            self.assertEqual(ledger["entry_count"], len(ledger["entries"]))
```

- [ ] **Step 2: Add scenario coverage only if a stable run-dir assertion already exists**

If `src/test/scenarios/worker-quality-gates-part1.test.ts` already creates a prepare run and inspects run artifacts, add an assertion for:

```ts
expect(readJson(path.join(runDir, "canonical_ir", "transformation_ledger.json")).schema)
  .toBe("kbprep.canonical_ir_transformation_ledger.v1");
```

If the existing scenario does not expose a stable run directory, do not add a broad new TypeScript scenario. The Python end-to-end test is sufficient for the runtime worker path, and `dev:full-check` covers package integration.

- [ ] **Step 3: Run target pipeline tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_manifest python.tests.test_conversion_gate python.tests.test_core_processing_paths -v
```

If TypeScript scenario assertions were added, also run:

```powershell
npm test -- src/test/scenarios/worker-quality-gates-part1.test.ts
```

- [ ] **Step 4: Stage 3 independent review**

Spawn an independent reviewer subagent:

```text
Review Stage 3 only. Inspect pipeline-facing tests and any TypeScript scenario change. Verify prepare writes transformation_ledger before the conversion gate, the ledger is referenced by manifest, and the tests do not rely on unstable temp paths. Run the Stage 3 target commands. Report APPROVED or CHANGES REQUIRED with concrete file/line issues.
```

---

### Stage 4: Documentation And Status Alignment

**Files:**
- Modify: `docs/development/00-current-state-and-gap.md`
- Modify: `docs/development/02-canonical-ir-contract.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`
- Modify: `docs/known-issues.md`

- [ ] **Step 1: Update current-state gap**

In `docs/development/00-current-state-and-gap.md`, replace:

```markdown
- Canonical IR is not yet the complete internal fact layer.
- SourceSpan variants are not yet a full contract across all source kinds.
```

with:

```markdown
- Canonical IR now emits validated typed nodes, source spans, and a conversion-phase TransformationLedger, but it is not yet the complete internal fact layer.
- SourceSpan variants are not yet a full contract across all source kinds; route-native precision such as PDF bounding boxes, DOCX run ranges, PPTX shape ids, XLSX cells, and YouTube cue ids still needs converter-specific evidence.
- Canonical IR still needs relationships, assets, annotations, complete coverage reporting, conversion-gate use of full IR evidence, and Markdown regeneration from IR plus accepted changes before Phase C is complete.
```

- [ ] **Step 2: Update Canonical IR stage doc**

In `docs/development/02-canonical-ir-contract.md`, replace the current shipped-boundary paragraph that starts with:

```markdown
The current worker ships a partial Canonical IR contract. It writes
`canonical_ir/manifest.json`, `document_manifest.json`, a validated
`canonical_ir/typed_nodes.json` artifact, and a validated
`canonical_ir/source_spans.json` artifact for converted Markdown blocks.
```

with:

```markdown
The current worker ships a partial Canonical IR contract. It writes
`canonical_ir/manifest.json`, `document_manifest.json`, a validated
`canonical_ir/typed_nodes.json` artifact, a validated
`canonical_ir/source_spans.json` artifact, and a validated
`canonical_ir/transformation_ledger.json` artifact for conversion-phase
Canonical IR evidence.
```

In the same section, replace the sentence:

```markdown
Relationship evidence, assets, annotations, a
transformation ledger, and Markdown regeneration from IR plus accepted changes
are still target work.
```

with:

```markdown
The TransformationLedger currently records ordered conversion-phase evidence
for route decisions, converted Markdown, typed nodes, and source spans, and the
pre-clean conversion gate validates it when the manifest claims the artifact.
Relationship evidence, assets, annotations, route-native fine-grained spans,
complete coverage reporting, gate use of full IR semantics, and Markdown
regeneration from IR plus accepted changes are still target work.
```

- [ ] **Step 3: Update roadmap**

In `docs/development/development-roadmap.md`, change C3 from:

```markdown
- **C3** `TransformationLedger` append-only record.
```

to:

```markdown
- **C3** Landed: `TransformationLedger` append-only record for conversion-phase Canonical IR evidence, referenced by the manifest and validated by the pre-clean conversion gate when claimed.
```

Keep C4 and C5 as remaining work.

- [ ] **Step 4: Update implementation status JSON**

In `docs/development/kbprep-implementation-status.json`, keep:

```json
"status": "partial"
```

For `canonical_ir_contract.scope`, use this exact replacement:

```json
"The worker emits a partial Canonical IR manifest plus validated canonical_ir/typed_nodes.json, canonical_ir/source_spans.json, and canonical_ir/transformation_ledger.json artifacts for heading, paragraph, list, table, code, quote, formula, figure, metadata, and transcript cue nodes. SourceSpans cover converted Markdown line ranges for every typed node, strict evidence schema validation, structured-data text sources, and transcript cue timing when raw cue evidence is available. The TransformationLedger records ordered conversion-phase evidence for route decisions, converted Markdown, typed nodes, and source spans. Full route-native span precision, relationship evidence, assets, annotations, complete coverage reporting, Markdown regeneration, and universal fact-layer usage are not shipped."
```

Add evidence:

```json
"python/kbprep_worker/canonical_ledger.py",
"python/tests/test_canonical_ir_ledger.py"
```

Keep prohibited claim:

```json
"Canonical IR is the complete shipped worker fact layer"
```

- [ ] **Step 5: Update known issues**

In `docs/known-issues.md`, replace the first Canonical IR bullet under `## Current Target Gaps` with:

```markdown
- Canonical IR is documented as the target fact layer, and the worker now writes validated `typed_nodes.json`, `source_spans.json`, and `transformation_ledger.json` artifacts with core text, formula, figure, metadata, transcript cue nodes, and conversion-phase ledger evidence, but every route-specific structure has not fully moved to that contract.
```

Keep the existing SourceSpan route-native precision bullet. Do not remove known issues for CleaningPolicySnapshot, CleaningPatch, Clean View, optional routes, or selective rerun.

- [ ] **Step 6: Search for stale/overclaim text**

Run:

```powershell
rg -n "Canonical IR is the complete shipped worker fact layer|canonical_ir_contract.*implemented|all conversion routes have complete Canonical IR gate coverage|TransformationLedger|append-only transformation ledger|Markdown regeneration|rendered Markdown can be regenerated|full fact-layer usage|not yet the complete internal fact layer|route-native|minimal Canonical IR manifest writer|status must be partial for this slice" docs README.md python scripts
```

Interpretation:

- Hits in protected design describing target semantics are allowed.
- Hits in status docs must be accurate after C3.
- Hits in code comments that still say "Minimal Canonical IR manifest writer" must be updated if the module now writes manifest plus typed nodes, source spans, and ledger.

- [ ] **Step 7: Run documentation/governance checks**

Run:

```powershell
$env:KBPREP_ALLOW_CORE_DOC_EDIT='1'; npm run dev:check
npm run check:development-docs
```

Do not edit protected core design or flowchart files for C3 unless a check proves they are inconsistent with the existing target design.

- [ ] **Step 8: Stage 4 independent review**

Spawn an independent reviewer subagent:

```text
Review Stage 4 only. Inspect docs/development/00-current-state-and-gap.md, docs/development/02-canonical-ir-contract.md, docs/development/development-roadmap.md, docs/development/kbprep-implementation-status.json, docs/known-issues.md, and stale-text search output. Verify C3 is described as shipped partial evidence, canonical_ir_contract remains partial, protected design was not changed, route capabilities were not overpromoted, and stale ledger-missing wording is gone. Run the Stage 4 documentation checks. Report APPROVED or CHANGES REQUIRED with concrete file/line issues.
```

---

### Stage 5: Full Verification, Final Review, Commit, Push, Owner-Authorized Merge

**Files:**
- All files touched by Stages 1-4.

- [ ] **Step 1: Run full project checks**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_ledger python.tests.test_canonical_ir_schema python.tests.test_canonical_ir_manifest python.tests.test_conversion_gate python.tests.test_core_processing_paths -v
npm run python:test
npm run python:ruff
npm run python:typecheck
npm run dev:full-check
git diff --check
```

Expected:

- all Python target tests pass
- `npm run python:test` passes
- `npm run python:ruff` passes
- `npm run python:typecheck` passes
- `npm run dev:full-check` passes
- `git diff --check` prints no output and exits 0

- [ ] **Step 2: Final independent review**

Spawn an independent reviewer subagent:

```text
Final review for Phase C3 TransformationLedger. Review all changed files on branch codex/phase-c3-transformation-ledger. Verify the plan is complete, every stage review was completed, ledger schema/writer/validator/gate/docs/status are aligned, no capability is overpromoted, no stale C3 gap wording remains, and verification commands match the risk. Run git diff --check and the focused Canonical IR tests. Report APPROVED FINAL or CHANGES REQUIRED with concrete file/line issues.
```

If `CHANGES REQUIRED`, fix all issues and re-review.

- [ ] **Step 3: Commit**

Run:

```powershell
git status --short --branch
git add -- python/kbprep_worker/canonical_ledger.py python/kbprep_worker/canonical_ir.py python/kbprep_worker/canonical_nodes.py python/kbprep_worker/error_codes.py python/kbprep_worker/quality/conversion_gate.py python/tests/test_canonical_ir_ledger.py python/tests/test_canonical_ir_manifest.py src/errorCodes.ts docs/development/00-current-state-and-gap.md docs/development/02-canonical-ir-contract.md docs/development/development-roadmap.md docs/development/kbprep-implementation-status.json docs/known-issues.md docs/superpowers/plans/2026-06-23-phase-c3-transformation-ledger.md
git commit -m "feat: add canonical IR transformation ledger"
```

Adjust the `git add` list to include `python/tests/test_canonical_ir_schema.py` or any TypeScript scenario file only if the actual implementation changed one.

- [ ] **Step 4: Push branch**

Run:

```powershell
git push -u origin codex/phase-c3-transformation-ledger
```

- [ ] **Step 5: Merge to main after checks pass**

Permission boundary: merging into `main` normally requires explicit owner authorization. For this task, the active owner objective explicitly authorizes final push, commit, and merge after independent review and checks pass. If this plan is executed outside that objective, stop here and request owner authorization before running the merge commands.

If branch CI passes or no branch CI is configured, and the authorization condition above still holds:

```powershell
git switch main
git pull --ff-only origin main
git merge --ff-only codex/phase-c3-transformation-ledger
git push origin main
git ls-remote origin refs/heads/main
```

Verify remote `origin/main` points to the C3 commit SHA.

- [ ] **Step 6: Watch remote CI**

Run:

```powershell
$c3Commit = git rev-parse HEAD
gh run list --branch main --commit $c3Commit --limit 10 --json databaseId,workflowName,status,conclusion,url
$runId = gh run list --branch main --commit $c3Commit --limit 1 --json databaseId --jq '.[0].databaseId'
gh run watch $runId --exit-status --interval 20
```

If CI fails, inspect logs, fix the root cause on `codex/phase-c3-transformation-ledger`, repeat review/checks, merge, push, and watch CI again.

## Acceptance

### Branch Acceptance

C3 branch implementation is accepted only when all are true:

- `canonical_ir/transformation_ledger.json` is emitted for current prepare runs.
- Canonical IR manifest references the ledger.
- Coverage reports `transformation_ledger_available: true` for current writer output.
- Validator rejects claimed missing, escaped, malformed, reordered, or tampered ledger evidence.
- Conversion gate blocks cleanup when a claimed ledger is invalid.
- `canonical_ir_contract` remains `partial`.
- Docs narrow C3 gaps without claiming complete Canonical IR.
- Independent reviewer subagents approve every stage and final implementation.
- Local `dev:full-check` passes.
- Feature branch is pushed.

### Owner-Authorized Integration Acceptance

Merging to `main` and watching remote CI are integration steps, not branch-implementation acceptance. They require explicit owner authorization. In the current execution, the owner has authorized final commit, push, and merge after independent review and checks pass. Outside that explicit objective, stop before the merge and request owner authorization.

Integration is accepted only when all are true:

- C3 is merged to `main`.
- `origin/main` points to the C3 commit.
- Remote CI for the C3 commit passes.

## Rollback

Rollback is one focused revert of the C3 commit. Because the ledger is additive and manifest-referenced, reverting must remove:

- `canonical_ledger.py`
- ledger tests
- manifest/gate ledger references
- docs/status C3 shipped wording
- plan file

After rollback, run:

```powershell
npm run dev:full-check
git diff --check
```
