# Canonical IR Typed Nodes Implementation Plan

> Supersession note, 2026-06-23: this C1 plan described the pre-SourceSpan slice where `coverage.source_spans_available` stayed false. The later C1b2/C2 SourceSpan work supersedes that statement: current Canonical IR may write `canonical_ir/source_spans.json`, and `coverage.source_spans_available` is true when the artifact validates successfully. Treat the old false-coverage steps below as historical context, not current implementation guidance.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first shipped Canonical IR TypedNode artifact so converted Markdown produces auditable structure nodes without changing publication behavior.

**Architecture:** Keep the existing `canonical_ir/manifest.json` and `document_manifest.json` contracts compatible, and add a sibling artifact at `canonical_ir/typed_nodes.json`. A focused Python builder parses `converted.md` into deterministic typed nodes, while the manifest records the artifact path and flips `coverage.typed_nodes_available` only when the artifact passes shared validation. Source spans remain out of scope for C1 and must stay `false`.

**Tech Stack:** Python worker modules under `python/kbprep_worker/`, Python `unittest` through `node scripts/python-venv.mjs`, JSON artifacts written through `atomic_write_json`, KBPrep governance checks through npm scripts.

---

## Scope And Boundaries

This is Roadmap Phase C1 only. It creates TypedNode schema and builder support for Markdown produced by existing converters.

It must not:

- implement SourceSpan variants
- change PDF routing or converters
- change cleanup behavior
- implement CleaningPatch or Clean View
- change source-side publication
- edit `docs/kbprep-core-flow-design.md` or `docs/kbprep-full-flowchart.html`
- promote `canonical_ir_contract` to `implemented`
- claim all conversion quality gates use complete Canonical IR evidence

## Artifact Contract

Create `canonical_ir/typed_nodes.json`:

```json
{
  "schema": "kbprep.canonical_ir_typed_nodes.v1",
  "document_id": "doc_<source hash prefix>",
  "source_artifact": "converted.md",
  "node_count": 6,
  "nodes": [
    {
      "node_id": "n_000001",
      "ordinal": 1,
      "type": "heading",
      "text": "操作教程",
      "metadata": {
        "heading_level": 1
      }
    }
  ]
}
```

Supported C1 node types:

- `heading`
- `paragraph`
- `list`
- `table`
- `code`
- `quote`

Required node fields:

- `node_id`: stable sequential id, `n_000001`
- `ordinal`: 1-based order
- `type`: one of the C1 node types
- `text`: non-empty source text for the node
- `metadata`: object, empty when no metadata exists

C1 does not write real source spans. Do not add fake source-span coverage.

Compatibility rule:

- New prepare runs must write `canonical_ir/typed_nodes.json`.
- Older test fixtures or hand-written manifests may omit `artifacts.typed_nodes` only when `coverage.typed_nodes_available` is `false`.
- If `coverage.typed_nodes_available` is `true`, `artifacts.typed_nodes` must exist, stay inside the run directory, point to a valid typed-node artifact, and pass typed-node validation.
- `coverage.source_spans_available` must be `false` for this C1 slice.

Typed-node validation must reject:

- invalid schema
- missing or escaping `source_artifact`
- `source_artifact` that does not point to `converted.md`
- `document_id` mismatch with the canonical manifest
- `node_count` mismatch with `len(nodes)`
- duplicate, missing, or non-contiguous `node_id` / `ordinal`
- unsupported node `type`
- empty `text`
- non-object `metadata`
- extra node keys such as `source_span`, `line_start`, or other fake span evidence

## Task 1: Add TypedNode Artifact Tests First

**Files:**

- Create: `python/tests/test_canonical_ir_typed_nodes.py`

- [ ] **Step 1: Write failing artifact builder tests**

Create `python/tests/test_canonical_ir_typed_nodes.py` with:

```python
import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.canonical_nodes import build_typed_nodes_from_markdown, write_typed_nodes_artifact


class CanonicalIrTypedNodesTests(unittest.TestCase):
    def test_builds_core_markdown_typed_nodes_in_source_order(self) -> None:
        markdown = """# 操作教程

第一段方法说明。

- 步骤1：收集素材
- 步骤2：记录判断标准

| 指标 | 含义 |
| --- | --- |
| 留存 | 是否持续使用 |

```python
threshold = 0.8
```

> 案例提醒：不要只看一次转化。
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["heading", "paragraph", "list", "table", "code", "quote"])
        self.assertEqual(nodes[0].node_id, "n_000001")
        self.assertEqual(nodes[0].metadata, {"heading_level": 1})
        self.assertEqual(nodes[2].text, "步骤1：收集素材\n步骤2：记录判断标准")
        self.assertEqual(nodes[3].metadata, {"rows": 3})
        self.assertEqual(nodes[4].metadata, {"language": "python"})

    def test_writes_typed_nodes_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# 标题\n\n正文内容。\n", encoding="utf-8")

            artifact_path = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
            )

            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "kbprep.canonical_ir_typed_nodes.v1")
            self.assertEqual(payload["document_id"], "doc_test")
            self.assertEqual(payload["source_artifact"], "converted.md")
            self.assertEqual(payload["node_count"], 2)
            self.assertEqual(payload["nodes"][0]["type"], "heading")
            self.assertEqual(payload["nodes"][1]["type"], "paragraph")

    def test_parser_keeps_code_fence_content_as_one_code_node(self) -> None:
        markdown = """```markdown
# Not a heading
- not a list item
> not a quote
| not | a table |
```
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["code"])
        self.assertIn("# Not a heading", nodes[0].text)
        self.assertEqual(nodes[0].metadata, {"language": "markdown"})

    def test_parser_does_not_treat_pipe_sentence_as_table(self) -> None:
        nodes = build_typed_nodes_from_markdown("这个判断标准 A | B 只是正文里的符号。\n")

        self.assertEqual([node.node_type for node in nodes], ["paragraph"])

    def test_parser_merges_ordered_list_and_multiline_paragraph(self) -> None:
        markdown = """第一行说明
第二行继续说明

1. 收集素材
2. 记录判断标准
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["paragraph", "list"])
        self.assertEqual(nodes[0].text, "第一行说明\n第二行继续说明")
        self.assertEqual(nodes[1].text, "收集素材\n记录判断标准")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new test and confirm RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes -v
```

Expected: fail with `ModuleNotFoundError: No module named 'kbprep_worker.canonical_nodes'`.

## Task 2: Implement The TypedNode Builder Module

**Files:**

- Create: `python/kbprep_worker/canonical_nodes.py`
- Test: `python/tests/test_canonical_ir_typed_nodes.py`

- [ ] **Step 1: Add the focused module**

Create `python/kbprep_worker/canonical_nodes.py` with a frozen dataclass, builder, serializer, and artifact writer. Keep functions under 50 lines.

Required public API names and responsibilities:

```python
CANONICAL_IR_TYPED_NODES_SCHEMA = "kbprep.canonical_ir_typed_nodes.v1"

@dataclass(frozen=True)
class TypedNode:
    node_id: str
    ordinal: int
    node_type: str
    text: str
    metadata: dict[str, object]
```

`build_typed_nodes_from_markdown(markdown: str) -> list[TypedNode]` returns source-order nodes with stable ids and metadata.

`write_typed_nodes_artifact(*, run_dir: Path, document_id: str, converted_path: Path) -> Path` writes `canonical_ir/typed_nodes.json` and returns that path.

Parsing rules:

- fenced code blocks become one `code` node; capture fence language as `metadata.language` when present
- ATX headings (`#`, `##`, etc.) become `heading` nodes with `metadata.heading_level`
- contiguous list lines starting with `- `, `* `, `+ `, or ordered markers become one `list` node
- contiguous Markdown table rows containing `|` become one `table` node with `metadata.rows` only when at least two adjacent table-like rows exist
- contiguous quote lines starting with `>` become one `quote` node
- other non-empty contiguous lines become one `paragraph` node
- code fence content must not be interpreted as heading, list, table, or quote nodes

- [ ] **Step 2: Run the typed-node tests and confirm GREEN**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes -v
```

Expected: 2 tests pass.

## Task 3: Integrate Typed Nodes With Existing Canonical IR Manifests

**Files:**

- Modify: `python/kbprep_worker/canonical_ir.py`
- Modify: `python/tests/test_canonical_ir_manifest.py`
- Modify: `python/tests/test_canonical_ir_schema.py`
- Test: `python/tests/test_canonical_ir_typed_nodes.py`

- [ ] **Step 1: Write failing manifest integration assertions**

Update `test_prepare_writes_canonical_ir_and_document_manifests` in `python/tests/test_canonical_ir_manifest.py` to assert:

```python
typed_nodes_path = run_dir / "canonical_ir" / "typed_nodes.json"
self.assertTrue(typed_nodes_path.exists())
self.assertEqual(canonical_manifest["artifacts"]["typed_nodes"], "canonical_ir/typed_nodes.json")
self.assertTrue(canonical_manifest["coverage"]["typed_nodes_available"])
self.assertFalse(canonical_manifest["coverage"]["source_spans_available"])

typed_nodes = json.loads(typed_nodes_path.read_text(encoding="utf-8"))
self.assertEqual(typed_nodes["schema"], "kbprep.canonical_ir_typed_nodes.v1")
self.assertGreaterEqual(typed_nodes["node_count"], 2)
```

Update the successful writer test in `python/tests/test_canonical_ir_schema.py` to assert that `typed_nodes` is referenced and validation returns no issues.

Add negative schema tests in `python/tests/test_canonical_ir_schema.py`:

- `test_validator_rejects_invalid_typed_nodes_artifact`: create an otherwise-valid canonical manifest with `artifacts.typed_nodes = "canonical_ir/typed_nodes.json"` and `coverage.typed_nodes_available = true`, write `typed_nodes.json` with schema `"wrong.schema"`, then assert `E_CANONICAL_IR_TYPED_NODES_INVALID`.
- `test_validator_rejects_typed_nodes_identity_and_count_mismatch`: write `typed_nodes.json` with `document_id = "doc_other"` and `node_count = 99` for one node, then assert `E_CANONICAL_IR_TYPED_NODES_INVALID`.
- `test_validator_rejects_fake_source_span_fields`: write a node containing `source_span` or `line_start`, then assert `E_CANONICAL_IR_TYPED_NODES_INVALID`.

Add conversion-gate coverage in `python/tests/test_conversion_gate.py`:

- `test_conversion_gate_fails_when_typed_nodes_are_invalid`: create otherwise-valid manifest evidence with `coverage.typed_nodes_available = true`, corrupt `typed_nodes.json`, then assert `run_pre_clean_conversion_gate` returns `status = "fail"` and `blocked_stage = "cleanup"`.

- [ ] **Step 2: Run integration tests and confirm RED**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_manifest python.tests.test_canonical_ir_schema -v
```

Expected: fail because `typed_nodes` artifact is not written or referenced.

- [ ] **Step 3: Wire the artifact into `canonical_ir.py`**

Required behavior:

- compute `document_id` once and reuse it for manifest and typed nodes
- call `write_typed_nodes_artifact(run_dir=run_dir, document_id=document_id, converted_path=converted_path)`
- add `artifacts.typed_nodes`
- update `_coverage_snapshot` so `typed_nodes_available` is true only after the typed-node artifact passes validation
- keep `source_spans_available` false
- validate `artifacts.typed_nodes` as a run-local reference when present
- validate the typed-nodes payload schema, `source_artifact`, `document_id`, `node_count`, node ids, ordinals, node type enum, non-empty text, metadata object, and exact node key set
- reject `coverage.source_spans_available = true` for this C1 slice

- [ ] **Step 4: Run the Canonical IR target suite and confirm GREEN**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_manifest python.tests.test_canonical_ir_schema python.tests.test_conversion_gate -v
```

Expected: all tests pass.

## Task 4: Update Current Status And Stage Docs Without Overclaiming

**Files:**

- Modify: `docs/development/02-canonical-ir-contract.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`
- Modify: `docs/known-issues.md`
- Review and either modify or explicitly leave unchanged: `docs/capability-matrix.md`

- [ ] **Step 1: Update status wording**

Keep `canonical_ir_contract.status` as `partial`.

Update the scope to state:

```text
The worker emits a partial Canonical IR manifest and a first TypedNode artifact for converted Markdown. Full source spans, relationships, assets, annotations, transformation ledger, and universal fact-layer use are not shipped.
```

Add evidence:

```json
"python/kbprep_worker/canonical_nodes.py",
"python/tests/test_canonical_ir_typed_nodes.py"
```

- [ ] **Step 2: Update roadmap and known issues**

Required wording:

- C1 is landed or in-progress with a first TypedNode artifact for `heading`, `paragraph`, `list`, `table`, `code`, and `quote`.
- The broader Phase C target still includes formula, figure, transcript cue, metadata, source spans, relationships, assets, annotations, and transformation ledger work.
- C2 SourceSpan coverage is still not complete.
- Do not remove the known issue that Canonical IR is not yet the complete internal fact layer.

`docs/capability-matrix.md` is route-level conversion truth. If no route status changes, leave it unchanged and document that decision in the PR body. If any text there mentions Canonical IR status in a way that becomes stale, update it conservatively.

- [ ] **Step 3: Run governance checks for docs/status changes**

Run:

```powershell
npm run check:development-docs
npm run check:flowchart
$env:KBPREP_ALLOW_CORE_DOC_EDIT='1'; npm run dev:check
```

Expected: pass.

## Task 5: Final Verification, Review, Commit, And PR

**Files:**

- All task files above

- [ ] **Step 1: Run focused verification**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_manifest python.tests.test_canonical_ir_schema python.tests.test_conversion_gate -v
npm run python:ruff
npm run python:typecheck
npm run check:development-docs
npm run check:flowchart
git diff --check
```

Expected: all pass.

- [ ] **Step 2: Run full project verification**

Run:

```powershell
npm run dev:full-check
```

Expected: pass, including TypeScript tests, TypeScript coverage, Python ruff, mypy, Python coverage, pack check, and Python tests.

- [ ] **Step 3: Review for forbidden claims**

Run:

```powershell
rg -n "Canonical IR is the complete shipped worker fact layer|canonical_ir_contract.*implemented|all conversion routes have complete Canonical IR gate coverage|every shipped cleanup change is a guarded CleaningPatch" docs README.md AGENTS.md scripts src python
```

Expected: only prohibited-claim guard text or negative assertions appear; no user-facing overclaim.

- [ ] **Step 4: Commit**

Run:

```powershell
git add python/kbprep_worker/canonical_nodes.py `
  python/kbprep_worker/canonical_ir.py `
  python/tests/test_canonical_ir_typed_nodes.py `
  python/tests/test_canonical_ir_manifest.py `
  python/tests/test_canonical_ir_schema.py `
  docs/development/02-canonical-ir-contract.md `
  docs/development/development-roadmap.md `
  docs/development/kbprep-implementation-status.json `
  docs/known-issues.md `
  docs/superpowers/plans/2026-06-22-canonical-ir-typed-nodes.md
git commit -m "feat: add canonical IR typed nodes"
```

- [ ] **Step 5: Push and open PR**

Run:

```powershell
git push -u origin codex/canonical-ir-typed-nodes
gh pr create --draft --base main --head codex/canonical-ir-typed-nodes --title "Add Canonical IR typed nodes" --body-file .kbprep/canonical-ir-typed-nodes-pr.md
```

The PR body must summarize:

- artifact name and schema
- node types supported
- source spans still out of scope
- why `docs/capability-matrix.md` was changed or intentionally left unchanged
- checks run
- why `canonical_ir_contract` remains partial

## Review Gates

Use read-only subagents before implementation to review:

1. artifact/schema fit against current code
2. docs/status/governance impact
3. TDD/test adequacy and missing regression risks

After each implementation module, perform two checks:

- spec compliance: compare changed files to this plan
- bug/code review: search for unstable IDs, overclaiming, unsafe path refs, source-span false claims, file/function-size drift

## Completion Requirements

C1 is complete only when:

- `canonical_ir/typed_nodes.json` is written during prepare runs
- manifest references the typed-node artifact
- coverage reports `typed_nodes_available: true`
- `source_spans_available` remains false
- target and full project checks pass
- status/docs remain partial and do not overclaim
- PR is created and merged to `main` only after verification succeeds
