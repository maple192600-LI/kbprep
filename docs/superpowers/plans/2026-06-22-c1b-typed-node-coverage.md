# C1b Typed Node Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the C1b TypedNode coverage slice for formula, figure, and metadata nodes while preserving the existing partial Canonical IR contract.

**Architecture:** Extend the existing deterministic Markdown block builder in `canonical_nodes.py` with conservative block-level detectors. Keep the existing TypedNode JSON shape unchanged and only expand the supported node type enum. Update current-status documentation conservatively so it says formula, figure, and metadata are shipped, while transcript cues, SourceSpan, and universal fact-layer usage remain future work.

**Tech Stack:** Python worker modules under `python/kbprep_worker/`, Python `unittest` through `node scripts/python-venv.mjs`, project documentation under `docs/development/`, and KBPrep project checks through npm scripts.

---

## File Structure

- Create: `docs/superpowers/specs/2026-06-22-c1b-typed-node-coverage-design.md`
  - Records the approved C1b-1 scope and non-goals.
- Modify: `python/tests/test_canonical_ir_typed_nodes.py`
  - Adds builder tests for metadata, figure, display formula, standalone inline formula, and code-fence precedence.
- Modify: `python/tests/test_canonical_ir_schema.py`
  - Adds validator coverage proving `formula`, `figure`, and `metadata` are accepted supported node types.
- Modify: `python/kbprep_worker/canonical_nodes.py`
  - Adds block-level consumers for YAML frontmatter, Markdown image figures, and standalone math formulas.
- Modify: `docs/development/02-canonical-ir-contract.md`
  - Updates current shipped boundary.
- Modify: `docs/development/development-roadmap.md`
  - Marks C1b-1 as landed and keeps transcript cue as remaining C1b work.
- Modify: `docs/development/kbprep-implementation-status.json`
  - Updates canonical IR partial scope without promoting it to implemented.
- Modify: `docs/known-issues.md`
  - Narrows the known gap language to remaining route-wide typed-node and SourceSpan work.

---

### Task 1: Add Failing Tests

**Files:**
- Modify: `python/tests/test_canonical_ir_typed_nodes.py`
- Modify: `python/tests/test_canonical_ir_schema.py`

- [ ] **Step 1: Add builder test for C1b block nodes**

Add this test to `python/tests/test_canonical_ir_typed_nodes.py`:

```python
    def test_parser_builds_c1b_metadata_figure_and_formula_nodes(self) -> None:
        markdown = """---
title: Example Note
tags:
  - canonical-ir
---

![Architecture diagram](assets/diagram.png "Architecture")

$$
E = mc^2
$$

$a + b = c$
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["metadata", "figure", "formula", "formula"])
        self.assertEqual(nodes[0].metadata, {"format": "yaml_frontmatter", "lines": 3})
        self.assertIn("title: Example Note", nodes[0].text)
        self.assertEqual(nodes[1].metadata, {
            "alt": "Architecture diagram",
            "target": "assets/diagram.png",
            "title": "Architecture",
        })
        self.assertEqual(nodes[2].text, "E = mc^2")
        self.assertEqual(nodes[2].metadata, {"syntax": "dollar_block"})
        self.assertEqual(nodes[3].text, "a + b = c")
        self.assertEqual(nodes[3].metadata, {"syntax": "dollar_inline"})
```

- [ ] **Step 2: Add code-fence precedence regression test**

Add this test to `python/tests/test_canonical_ir_typed_nodes.py`:

```python
    def test_parser_keeps_c1b_syntax_inside_code_fence_as_code(self) -> None:
        markdown = """```markdown
---
title: Not metadata
---
![not a figure](image.png)
$$
not_formula()
$$
```
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["code"])
        self.assertIn("![not a figure](image.png)", nodes[0].text)
        self.assertIn("not_formula()", nodes[0].text)
```

- [ ] **Step 3: Add validator test for new node types**

Add this test to `python/tests/test_canonical_ir_schema.py`:

```python
    def test_validator_accepts_c1b_typed_node_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("---\ntitle: Example\n---\n\n![Alt](image.png)\n\n$$\nx\n$$\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"converted_md": "converted.md", "typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            nodes = [
                {"node_id": "n_000001", "ordinal": 1, "type": "metadata", "text": "title: Example", "metadata": {"format": "yaml_frontmatter"}},
                {"node_id": "n_000002", "ordinal": 2, "type": "figure", "text": "![Alt](image.png)", "metadata": {"alt": "Alt", "target": "image.png"}},
                {"node_id": "n_000003", "ordinal": 3, "type": "formula", "text": "x", "metadata": {"syntax": "dollar_block"}},
            ]
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(node_count=3, nodes=nodes)),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertEqual(issues, [])
```

- [ ] **Step 4: Run tests and verify RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_schema -v
```

Expected: fail because `metadata`, `figure`, and `formula` are not yet parsed or supported.

---

### Task 2: Implement C1b Node Builders

**Files:**
- Modify: `python/kbprep_worker/canonical_nodes.py`

- [ ] **Step 1: Expand supported node types**

Change:

```python
SUPPORTED_NODE_TYPES = frozenset({"heading", "paragraph", "list", "table", "code", "quote"})
```

to:

```python
SUPPORTED_NODE_TYPES = frozenset({
    "heading",
    "paragraph",
    "list",
    "table",
    "code",
    "quote",
    "formula",
    "figure",
    "metadata",
})
```

- [ ] **Step 2: Add conservative detectors and consumers**

Add helpers for:

```python
_is_yaml_frontmatter_start(lines: list[str], index: int) -> bool
_consume_metadata(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]
_figure_metadata(line: str) -> dict[str, object] | None
_consume_figure(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]
_is_formula_start(line: str) -> bool
_consume_formula(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]
```

Use these rules:

- Frontmatter is only recognized at `index == 0` and starts with `---`.
- A closing `---` ends frontmatter.
- A figure is one standalone Markdown image line.
- A display formula starts with a standalone `$$` line and ends at the next standalone `$$`.
- A one-line display formula `$$x$$` is also a formula.
- A standalone `$x$` line is a formula.

- [ ] **Step 3: Wire the detectors in `_consume_block` and `_is_special_block_start`**

Order:

1. code fence
2. metadata
3. formula
4. heading
5. list
6. table
7. quote
8. figure
9. paragraph

Expected: code fences continue to protect C1b syntax inside code blocks.

- [ ] **Step 4: Run target tests and verify GREEN**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_schema -v
```

Expected: all tests pass.

---

### Task 3: Update Current-Status Documentation

**Files:**
- Modify: `docs/development/02-canonical-ir-contract.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`
- Modify: `docs/known-issues.md`

- [ ] **Step 1: Update Canonical IR contract current boundary**

State that current TypedNode coverage includes heading, paragraph, list, table, code, quote, formula, figure, and metadata. Keep transcript cues, SourceSpan, relationship evidence, assets, annotations, transformation ledger, and Markdown regeneration as target work.

- [ ] **Step 2: Update roadmap and status JSON conservatively**

Mark C1b-1 as landed but keep `canonical_ir_contract` status as `partial`. Do not claim complete Canonical IR or route-wide gate coverage.

- [ ] **Step 3: Update known issues**

Keep the known issue focused on remaining route-specific typed-node coverage, transcript cues, SourceSpan, and universal fact-layer usage.

- [ ] **Step 4: Run docs/status checks with target tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_schema python.tests.test_conversion_gate -v
npm run dev:check
git diff --check
```

Expected: all checks pass.

---

### Task 4: Full Verification, Commit, Merge

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run Python quality checks**

Run:

```powershell
npm run python:test
npm run python:ruff
npm run python:typecheck
```

Expected: all checks pass.

- [ ] **Step 2: Run release-level check if the status docs changed**

Run:

```powershell
npm run dev:full-check
```

Expected: all checks pass.

- [ ] **Step 3: Commit**

Run:

```powershell
git status --short
git add docs/superpowers/specs/2026-06-22-c1b-typed-node-coverage-design.md docs/superpowers/plans/2026-06-22-c1b-typed-node-coverage.md python/kbprep_worker/canonical_nodes.py python/tests/test_canonical_ir_typed_nodes.py python/tests/test_canonical_ir_schema.py docs/development/02-canonical-ir-contract.md docs/development/development-roadmap.md docs/development/kbprep-implementation-status.json docs/known-issues.md
git commit -m "feat: add C1b typed node coverage"
```

- [ ] **Step 4: Merge and verify on main**

Run:

```powershell
git checkout main
git pull --ff-only origin main
git merge --ff-only codex/c1b-typed-node-coverage
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_schema python.tests.test_conversion_gate -v
npm run dev:full-check
git push origin main
git branch -d codex/c1b-typed-node-coverage
```

Expected: main is pushed, branch is deleted, and the worktree is clean.

---

## Self-Review

- Spec coverage: plan covers formula, figure, and metadata node support, validation, docs, checks, commit, merge, and push.
- Placeholder scan: no deferred implementation placeholders.
- Type consistency: uses existing `TypedNode`, `SUPPORTED_NODE_TYPES`, `_typed_nodes_payload`, and `validate_canonical_ir_manifests` names.
- Scope check: transcript cues and SourceSpan are intentionally excluded for follow-up slices.
