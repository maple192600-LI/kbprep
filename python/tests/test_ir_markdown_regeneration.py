import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.render_outputs import render


class IrMarkdownRegenerationTests(unittest.TestCase):
    def test_render_regenerates_cleaned_markdown_from_ir_and_accepted_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_typed_nodes(run_dir, [
                _node("n_000001", 1, "heading", "Canonical Title", {"heading_level": 1}),
                _node("n_000002", 2, "paragraph", "Canonical body from IR.", {}),
                _node("n_000003", 3, "paragraph", "Original text before accepted cleanup.", {}),
            ])
            blocks = [
                _block("b_000001", "# Legacy Title", "section_heading", "keep"),
                _block("b_000002", "Legacy body should not render.", "paragraph", "keep"),
                _block("b_000003", "Accepted cleanup text.", "paragraph", "keep"),
                _block("b_000004", "Discarded accepted change.", "marketing_cta", "discard"),
            ]
            clean_view = {
                "schema": "kbprep.clean_view.v1",
                "source_artifact": "canonical_ir/typed_nodes.json",
                "patch_artifact": "cleaning_patches.jsonl",
                "entry_count": 4,
                "entries": [
                    _entry("cv_000001", 1, "n_000001", "b_000001", "keep", []),
                    _entry("cv_000002", 2, "n_000002", "b_000002", "keep", []),
                    _entry("cv_000003", 3, "n_000003", "b_000003", "keep", ["p_accepted"]),
                    _entry("cv_000004", 4, "", "b_000004", "discard", ["p_discarded"]),
                ],
            }

            render(blocks, str(run_dir), "source", "run", clean_view=clean_view)

            cleaned = (run_dir / "cleaned.md").read_text(encoding="utf-8")
            discarded = (run_dir / "discarded.md").read_text(encoding="utf-8")

        self.assertIn("# Canonical Title", cleaned)
        self.assertIn("Canonical body from IR.", cleaned)
        self.assertIn("Accepted cleanup text.", cleaned)
        self.assertNotIn("Legacy Title", cleaned)
        self.assertNotIn("Legacy body should not render", cleaned)
        self.assertNotIn("Original text before accepted cleanup", cleaned)
        self.assertIn("Discarded accepted change.", discarded)

    def test_non_standard_profile_keeps_profile_curated_block_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_typed_nodes(run_dir, [
                _node("n_000001", 1, "heading", "ExampleCreator: Raw IR Title", {"heading_level": 1}),
            ])
            blocks = [
                _block("b_000001", "# Curated Title", "section_heading", "keep"),
            ]
            clean_view = {
                "schema": "kbprep.clean_view.v1",
                "source_artifact": "canonical_ir/typed_nodes.json",
                "patch_artifact": "cleaning_patches.jsonl",
                "entry_count": 1,
                "entries": [_entry("cv_000001", 1, "n_000001", "b_000001", "keep", [])],
            }

            render(blocks, str(run_dir), "source", "run", profile="curated_obsidian_kb", clean_view=clean_view)

            cleaned = (run_dir / "cleaned.md").read_text(encoding="utf-8")

        self.assertIn("# Curated Title", cleaned)
        self.assertNotIn("ExampleCreator:", cleaned)


def _write_typed_nodes(run_dir: Path, nodes: list[dict]) -> None:
    canonical_dir = run_dir / "canonical_ir"
    canonical_dir.mkdir(parents=True)
    (canonical_dir / "typed_nodes.json").write_text(
        json.dumps({
            "schema": "kbprep.canonical_ir_typed_nodes.v1",
            "document_id": "doc_test",
            "source_artifact": "converted.md",
            "node_count": len(nodes),
            "nodes": nodes,
        }),
        encoding="utf-8",
    )


def _node(node_id: str, ordinal: int, node_type: str, text: str, metadata: dict) -> dict:
    return {
        "node_id": node_id,
        "ordinal": ordinal,
        "type": node_type,
        "text": text,
        "metadata": metadata,
    }


def _block(block_id: str, text: str, block_type: str, status: str) -> dict:
    return {
        "block_id": block_id,
        "text": text,
        "type": block_type,
        "status": status,
        "line_start": 1,
        "line_end": 1,
        "page_start": None,
        "page_end": None,
    }


def _entry(
    entry_id: str,
    ordinal: int,
    node_id: str,
    block_id: str,
    status: str,
    patch_ids: list[str],
) -> dict:
    return {
        "entry_id": entry_id,
        "ordinal": ordinal,
        "node_id": node_id,
        "block_id": block_id,
        "parent_block_id": "",
        "entry_kind": "canonical_node" if node_id else "unmapped_block",
        "type": "paragraph",
        "status": status,
        "patch_ids": patch_ids,
        "rule_ids": [],
        "location": {"line_start": 1, "line_end": 1, "page_start": None, "page_end": None},
    }


if __name__ == "__main__":
    unittest.main()
