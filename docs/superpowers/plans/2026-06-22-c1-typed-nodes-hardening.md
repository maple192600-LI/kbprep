# C1 Typed Nodes Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove duplicate conversion-gate repair actions for invalid TypedNode artifacts and lock the C1 TypedNode schema boundaries with regression tests.

**Architecture:** Keep the C1 Canonical IR surface partial and conservative. The conversion gate should still fail on invalid `canonical_ir/typed_nodes.json`, but `failure_actions` should contain one actionable repair entry per error code instead of repeated identical entries. TypedNode validation continues to enforce the existing schema: deterministic ids, contiguous ordinals, supported node types, non-empty text, metadata object, exact node keys, and validated `node_count`.

**Tech Stack:** Python worker modules under `python/kbprep_worker/`, Python `unittest` through `node scripts/python-venv.mjs`, project checks through npm scripts.

---

## File Structure

- Modify: `python/tests/test_conversion_gate.py`
  - Add a regression test proving repeated `E_CANONICAL_IR_TYPED_NODES_INVALID` issues produce one `failure_actions` entry.
- Modify: `python/tests/test_canonical_ir_schema.py`
  - Add schema-boundary tests for zero-node payloads, invalid `metadata`/`text` types, and missing required node keys.
- Modify: `python/kbprep_worker/quality/conversion_gate.py`
  - Deduplicate `failure_actions` by issue code while preserving first-seen order.

No design, flowchart, route, cleanup, publication, or capability-status files should change.

---

### Task 1: Add Failing Regression Coverage

**Files:**
- Modify: `python/tests/test_conversion_gate.py`
- Modify: `python/tests/test_canonical_ir_schema.py`

- [ ] **Step 1: Add conversion-gate regression test**

Add a test to `python/tests/test_conversion_gate.py` that creates a valid manifest pair, points it at a malformed `typed_nodes.json`, and asserts that the gate fails with one `regenerate_canonical_ir` action for `E_CANONICAL_IR_TYPED_NODES_INVALID`.

```python
    def test_pre_clean_conversion_gate_deduplicates_typed_node_failure_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Tutorial\n\nRecord acceptance criteria.\n", encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            manifest_path = run_dir / "canonical_ir" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"]["typed_nodes"] = "canonical_ir/typed_nodes.json"
            manifest["coverage"]["typed_nodes_available"] = True
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_typed_nodes.v1",
                    "document_id": "doc_test",
                    "source_artifact": "converted.md",
                    "node_count": 1,
                    "nodes": [
                        {
                            "node_id": "bad",
                            "ordinal": 2,
                            "type": "unknown",
                            "text": "",
                            "metadata": [],
                        }
                    ],
                }),
                encoding="utf-8",
            )

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        typed_node_actions = [
            action
            for action in report["failure_actions"]
            if action["code"] == "E_CANONICAL_IR_TYPED_NODES_INVALID"
        ]
        self.assertEqual(report["status"], "fail")
        self.assertGreaterEqual(
            sum(error.startswith("E_CANONICAL_IR_TYPED_NODES_INVALID") for error in report["strict_errors"]),
            2,
        )
        self.assertEqual(len(typed_node_actions), 1)
        self.assertEqual(typed_node_actions[0]["action"], "regenerate_canonical_ir")
```

- [ ] **Step 2: Add TypedNode schema-boundary tests**

Add tests to `python/tests/test_canonical_ir_schema.py`:

```python
    def test_validator_accepts_empty_typed_nodes_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"converted_md": "converted.md", "typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(node_count=0, nodes=[])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertEqual(issues, [])

    def test_validator_rejects_invalid_typed_node_text_and_metadata_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"converted_md": "converted.md", "typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            node = {"node_id": "n_000001", "ordinal": 1, "type": "heading", "text": None, "metadata": []}
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(nodes=[node])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        messages = [issue.message for issue in issues]
        self.assertIn("typed_nodes node text must be non-empty", messages)
        self.assertIn("typed_nodes node metadata must be an object", messages)

    def test_validator_rejects_typed_node_missing_required_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"converted_md": "converted.md", "typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            node = {"node_id": "n_000001", "ordinal": 1, "type": "heading", "text": "Title"}
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(nodes=[node])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.message == "typed_nodes node keys must match C1 schema exactly" for issue in issues))
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_conversion_gate python.tests.test_canonical_ir_schema -v
```

Expected: the new conversion-gate test fails because `failure_actions` currently contains repeated `E_CANONICAL_IR_TYPED_NODES_INVALID` actions. The schema-boundary tests may already pass because the validator logic exists.

---

### Task 2: Deduplicate Failure Actions

**Files:**
- Modify: `python/kbprep_worker/quality/conversion_gate.py`

- [ ] **Step 1: Implement ordered code deduplication**

Replace `_failure_actions` with:

```python
def _failure_actions(quality_issues: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    for issue in quality_issues:
        code = str(issue.get("code") or "")
        if code in seen_codes:
            continue
        seen_codes.add(code)
        actions.append(_failure_action(code))
    return actions
```

- [ ] **Step 2: Run target tests and verify GREEN**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_conversion_gate python.tests.test_canonical_ir_schema -v
```

Expected: all tests pass.

---

### Task 3: Broader Verification And Commit

**Files:**
- Verify only unless a check reveals a task-related issue.

- [ ] **Step 1: Run focused Canonical IR suite**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_schema python.tests.test_conversion_gate -v
```

Expected: all tests pass.

- [ ] **Step 2: Run Python worker checks**

Run:

```powershell
npm run python:test
npm run python:ruff
npm run python:typecheck
```

Expected: all checks pass.

- [ ] **Step 3: Run narrow project check and whitespace check**

Run:

```powershell
npm run dev:check
git diff --check
```

Expected: both pass.

- [ ] **Step 4: Commit the focused change**

Run:

```powershell
git status --short
git add docs/superpowers/plans/2026-06-22-c1-typed-nodes-hardening.md python/kbprep_worker/quality/conversion_gate.py python/tests/test_canonical_ir_schema.py python/tests/test_conversion_gate.py
git commit -m "fix: harden typed node conversion gate reporting"
```

Expected: commit succeeds with only the task-related files staged.

---

## Self-Review

- Spec coverage: covers the verified real defect (`failure_actions` duplication) and the validation test gaps judged worth fixing.
- Placeholder scan: no placeholders or deferred implementation steps.
- Type consistency: uses existing `unittest`, `Path`, `json`, `_write_valid_manifest_pair`, `_typed_nodes_payload`, and `validate_canonical_ir_manifests` helpers already present in the test files.
