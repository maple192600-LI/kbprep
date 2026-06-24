import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.clean_view import (
    CLEAN_VIEW_SCHEMA,
    assemble_clean_view,
    validate_clean_view_artifact,
    write_clean_view,
)
from kbprep_worker.render_outputs import render


class CleanViewTests(unittest.TestCase):
    def test_assembles_clean_view_in_canonical_order_without_text_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_typed_nodes(run_dir, [
                {"node_id": "n_000001", "ordinal": 1, "type": "heading", "text": "Title", "metadata": {}},
                {"node_id": "n_000002", "ordinal": 2, "type": "paragraph", "text": "Useful method.", "metadata": {}},
            ])
            blocks = [
                _block("b_000002", "Useful method.", "paragraph", "keep", 3, 3),
                _block("b_000001", "# Title", "section_heading", "keep", 1, 1),
            ]
            patches = [_patch("p1", "b_000002", "status_update", "keep")]

            payload = assemble_clean_view(run_dir=run_dir, blocks=blocks, accepted_patches=patches)

        self.assertEqual(payload["schema"], CLEAN_VIEW_SCHEMA)
        self.assertEqual(payload["source_artifact"], "canonical_ir/typed_nodes.json")
        self.assertEqual(payload["patch_artifact"], "cleaning_patches.jsonl")
        self.assertEqual(payload["entry_count"], 2)
        self.assertEqual([entry["block_id"] for entry in payload["entries"]], ["b_000001", "b_000002"])
        self.assertEqual(payload["entries"][0]["node_id"], "n_000001")
        self.assertEqual(payload["entries"][1]["patch_ids"], ["p1"])
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Useful method", serialized)
        self.assertNotIn("# Title", serialized)
        self.assertNotIn("before", serialized)
        self.assertNotIn("after", serialized)

    def test_places_derived_patch_entry_after_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_typed_nodes(run_dir, [
                {"node_id": "n_000001", "ordinal": 1, "type": "paragraph", "text": "Body line\nPromo line", "metadata": {}},
                {"node_id": "n_000002", "ordinal": 2, "type": "paragraph", "text": "Next body.", "metadata": {}},
            ])
            blocks = [
                _block("b_000001", "Body line", "paragraph", "keep", 1, 1),
                _block("b_000001_promo_001", "Promo line", "marketing_cta", "discard", 2, 2),
                _block("b_000002", "Next body.", "paragraph", "keep", 4, 4),
            ]
            patches = [
                _patch("p-parent", "b_000001", "content_update", "keep"),
                _patch("p-derived", "b_000001_promo_001", "derived_block", "discard", parent="b_000001"),
            ]

            payload = assemble_clean_view(run_dir=run_dir, blocks=blocks, accepted_patches=patches)

        self.assertEqual(
            [entry["block_id"] for entry in payload["entries"]],
            ["b_000001", "b_000001_promo_001", "b_000002"],
        )
        derived = payload["entries"][1]
        self.assertEqual(derived["entry_kind"], "derived_block")
        self.assertEqual(derived["parent_block_id"], "b_000001")
        self.assertEqual(derived["patch_ids"], ["p-derived"])

    def test_sanitizes_non_token_rule_ids_without_leaking_rule_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            blocks = [_block("b_000001", "Useful method.", "paragraph", "discard", 1, 1)]
            patches = [_patch("p1", "b_000001", "status_update", "discard")]
            patches[0]["rule_id"] = "learned-course-加入训练营领取资料"

            payload = assemble_clean_view(run_dir=run_dir, blocks=blocks, accepted_patches=patches)
            clean_view_path = run_dir / "clean_view.json"
            write_clean_view(clean_view_path, payload)

            self.assertEqual(len(payload["entries"][0]["rule_ids"]), 1)
            self.assertTrue(payload["entries"][0]["rule_ids"][0].startswith("rule_"))
            self.assertNotIn("加入训练营", json.dumps(payload, ensure_ascii=False))
            self.assertTrue(validate_clean_view_artifact(clean_view_path))

    def test_validator_rejects_leaky_or_malformed_clean_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clean_view.json"
            path.write_text(
                json.dumps({
                    "schema": CLEAN_VIEW_SCHEMA,
                    "source_artifact": "canonical_ir/typed_nodes.json",
                    "patch_artifact": "cleaning_patches.jsonl",
                    "entry_count": 1,
                    "entries": [{
                        "entry_id": "cv_000001",
                        "ordinal": 1,
                        "node_id": "n_000001",
                        "block_id": "b_000001",
                        "parent_block_id": "",
                        "entry_kind": "canonical_node",
                        "type": "paragraph",
                        "status": "keep",
                        "patch_ids": [],
                        "rule_ids": [],
                        "location": {"line_start": 1, "line_end": 1, "page_start": None, "page_end": None},
                        "text": "DO_NOT_LEAK",
                    }],
                }),
                encoding="utf-8",
            )

            self.assertFalse(validate_clean_view_artifact(path))

            payload = {
                "schema": CLEAN_VIEW_SCHEMA,
                "source_artifact": "canonical_ir/typed_nodes.json",
                "patch_artifact": "cleaning_patches.jsonl",
                "entry_count": 0,
                "entries": [],
            }
            write_clean_view(path, payload)

            self.assertTrue(validate_clean_view_artifact(path))

    def test_validator_rejects_bad_references_or_leaky_allowed_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clean_view.json"
            payload = _valid_payload()

            payload["source_artifact"] = "../canonical_ir/typed_nodes.json"
            write_clean_view(path, payload)
            self.assertFalse(validate_clean_view_artifact(path))

            payload = _valid_payload()
            payload["entries"][0]["rule_ids"] = ["C:/Users/Example/.kbprep/rules/private.jsonl"]
            write_clean_view(path, payload)
            self.assertFalse(validate_clean_view_artifact(path))

            payload = _valid_payload()
            payload["entries"][0]["block_id"] = "DO_NOT_LEAK_SOURCE_TEXT"
            write_clean_view(path, payload)
            self.assertFalse(validate_clean_view_artifact(path))

    def test_validator_rejects_empty_required_fields_or_invalid_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clean_view.json"
            for field_name, bad_value in (("block_id", ""), ("type", ""), ("status", "accepted")):
                payload = _valid_payload()
                payload["entries"][0][field_name] = bad_value
                write_clean_view(path, payload)

                self.assertFalse(validate_clean_view_artifact(path), field_name)

    def test_renderer_uses_complete_clean_view_order_and_falls_back_when_incomplete(self) -> None:
        blocks = [
            _block("b_000001", "First body", "paragraph", "keep", 1, 1),
            _block("b_000002", "Second body", "paragraph", "keep", 2, 2),
        ]
        complete_clean_view = {
            "schema": CLEAN_VIEW_SCHEMA,
            "entries": [
                _entry("cv_000001", 1, "b_000002", "keep"),
                _entry("cv_000002", 2, "b_000001", "keep"),
            ],
        }
        incomplete_clean_view = {
            "schema": CLEAN_VIEW_SCHEMA,
            "entries": [_entry("cv_000001", 1, "b_000002", "keep")],
        }

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            render(blocks, str(run_dir), "source", "run", clean_view=complete_clean_view)
            ordered = (run_dir / "cleaned.md").read_text(encoding="utf-8")

            render(blocks, str(run_dir), "source", "run", clean_view=incomplete_clean_view)
            fallback = (run_dir / "cleaned.md").read_text(encoding="utf-8")

        self.assertLess(ordered.index("Second body"), ordered.index("First body"))
        self.assertLess(fallback.index("First body"), fallback.index("Second body"))


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


def _block(block_id: str, text: str, block_type: str, status: str, line_start: int, line_end: int) -> dict:
    return {
        "block_id": block_id,
        "text": text,
        "type": block_type,
        "status": status,
        "line_start": line_start,
        "line_end": line_end,
        "page_start": None,
        "page_end": None,
    }


def _patch(patch_id: str, block_id: str, change_type: str, status: str, *, parent: str = "") -> dict:
    return {
        "schema": "kbprep.cleaning_patch.v1",
        "patch_id": patch_id,
        "block_id": block_id,
        "parent_block_id": parent,
        "change_type": change_type,
        "rule_id": "rule.clean",
        "rule_source": "rules/base/obvious_noise.json",
        "after": {"status": status},
        "location": {"line_start": 1, "line_end": 1, "page_start": None, "page_end": None},
    }


def _valid_payload() -> dict:
    return {
        "schema": CLEAN_VIEW_SCHEMA,
        "source_artifact": "canonical_ir/typed_nodes.json",
        "patch_artifact": "cleaning_patches.jsonl",
        "entry_count": 1,
        "entries": [_entry("cv_000001", 1, "b_000001", "keep")],
    }


def _entry(entry_id: str, ordinal: int, block_id: str, status: str) -> dict:
    return {
        "entry_id": entry_id,
        "ordinal": ordinal,
        "node_id": "n_000001",
        "block_id": block_id,
        "parent_block_id": "",
        "entry_kind": "canonical_node",
        "type": "paragraph",
        "status": status,
        "patch_ids": [],
        "rule_ids": [],
        "location": {"line_start": 1, "line_end": 1, "page_start": None, "page_end": None},
    }


if __name__ == "__main__":
    unittest.main()
