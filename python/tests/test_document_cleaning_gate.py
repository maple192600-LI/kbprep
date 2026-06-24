import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.document_cleaning_gate import (
    DOCUMENT_CLEANING_GATE_SCHEMA,
    document_cleaning_gate_allows_publication,
    run_document_cleaning_gate,
    validate_document_cleaning_gate_artifact,
    write_document_cleaning_gate,
)


class DocumentCleaningGateTests(unittest.TestCase):
    def test_passes_valid_clean_view_without_rejections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_clean_view(run_dir, ["b_000001", "b_000002"])
            (run_dir / "rejected_patches.jsonl").write_text("", encoding="utf-8")
            (run_dir / "cleaned.md").write_text("# Title\n\nUseful body.", encoding="utf-8")

            report = run_document_cleaning_gate(run_dir=run_dir, blocks=[
                _block("b_000001", "section_heading", "keep"),
                _block("b_000002", "paragraph", "keep"),
            ])

        self.assertEqual(report["schema"], DOCUMENT_CLEANING_GATE_SCHEMA)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["strict_errors"], [])
        self.assertEqual(report["warnings"], [])

    def test_warns_for_rejected_patches_without_blocking_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_clean_view(run_dir, ["b_000001", "b_000002"])
            _write_rejected_patch(run_dir, "p_rejected", "b_000002", "protected_structure")
            (run_dir / "cleaned.md").write_text("# Title\n\nUseful body.", encoding="utf-8")

            report = run_document_cleaning_gate(run_dir=run_dir, blocks=[
                _block("b_000001", "section_heading", "keep"),
                _block("b_000002", "paragraph", "keep"),
            ])

        self.assertEqual(report["status"], "warn")
        self.assertEqual(report["strict_errors"], [])
        self.assertEqual(report["warnings"], ["W_REJECTED_CLEANING_PATCHES: 1 rejected cleanup patches preserved"])
        self.assertEqual(report["rejected_patch_count"], 1)
        self.assertEqual(report["rejected_patch_reason_counts"], {"protected_structure": 1})

    def test_fails_missing_or_incomplete_clean_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_clean_view(run_dir, ["b_000001"])
            (run_dir / "rejected_patches.jsonl").write_text("", encoding="utf-8")
            (run_dir / "cleaned.md").write_text("Useful body.", encoding="utf-8")

            report = run_document_cleaning_gate(run_dir=run_dir, blocks=[
                _block("b_000001", "paragraph", "keep"),
                _block("b_000002", "paragraph", "keep"),
            ])

        self.assertEqual(report["status"], "fail")
        self.assertIn("E_DOCUMENT_CLEANING_GATE_FAILED: Clean View does not cover every block id", report["strict_errors"])

    def test_fails_duplicate_clean_view_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_clean_view(run_dir, ["b_000001", "b_000001", "b_000002"])
            (run_dir / "rejected_patches.jsonl").write_text("", encoding="utf-8")
            (run_dir / "cleaned.md").write_text("Useful body.", encoding="utf-8")

            report = run_document_cleaning_gate(run_dir=run_dir, blocks=[
                _block("b_000001", "paragraph", "keep"),
                _block("b_000002", "paragraph", "keep"),
            ])

        self.assertEqual(report["status"], "fail")
        self.assertIn(
            "E_DOCUMENT_CLEANING_GATE_FAILED: Clean View does not map exactly one entry per block id",
            report["strict_errors"],
        )
        coverage_check = next(check for check in report["checks"] if check["name"] == "clean_view_covers_blocks")
        self.assertEqual(coverage_check["evidence"]["duplicate_block_ids"], ["b_000001"])

    def test_gate_artifact_is_content_safe_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            gate_path = run_dir / "document_cleaning_gate.json"
            _write_clean_view(run_dir, ["b_000001"])
            _write_rejected_patch(run_dir, "p_rejected", "b_000001", "rule_rejected")
            (run_dir / "cleaned.md").write_text("DO_NOT_LEAK_SOURCE_TEXT", encoding="utf-8")

            report = run_document_cleaning_gate(run_dir=run_dir, blocks=[_block("b_000001", "paragraph", "keep")])
            write_document_cleaning_gate(gate_path, report)

            serialized = json.dumps(report, ensure_ascii=False)

            self.assertTrue(validate_document_cleaning_gate_artifact(gate_path))
            self.assertNotIn("DO_NOT_LEAK_SOURCE_TEXT", serialized)
            self.assertNotIn("before", serialized)
            self.assertNotIn("after", serialized)
            self.assertNotIn(".kbprep", serialized)

    def test_validator_rejects_tampered_or_leaky_publication_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            gate_path = run_dir / "document_cleaning_gate.json"
            _write_clean_view(run_dir, ["b_000001"])
            (run_dir / "rejected_patches.jsonl").write_text("", encoding="utf-8")
            (run_dir / "cleaned.md").write_text("Useful body.", encoding="utf-8")
            report = run_document_cleaning_gate(run_dir=run_dir, blocks=[_block("b_000001", "paragraph", "keep")])

            tampered = dict(report)
            tampered["strict_errors"] = ["E_DOCUMENT_CLEANING_GATE_FAILED: manually injected failure"]
            write_document_cleaning_gate(gate_path, tampered)
            self.assertFalse(validate_document_cleaning_gate_artifact(gate_path))
            self.assertFalse(document_cleaning_gate_allows_publication(gate_path))

            leaky = dict(report)
            leaky["checks"] = [dict(check) for check in report["checks"]]
            leaky["checks"][0]["evidence"] = {"heading_text": "DO_NOT_LEAK_SOURCE_TEXT"}
            write_document_cleaning_gate(gate_path, leaky)
            self.assertFalse(validate_document_cleaning_gate_artifact(gate_path))
            self.assertFalse(document_cleaning_gate_allows_publication(gate_path))

            contradictory = dict(report)
            contradictory["checks"] = [dict(check) for check in report["checks"]]
            contradictory["checks"][1] = {
                **contradictory["checks"][1],
                "status": "pass",
                "severity": "error",
                "reason_code": "clean_view_incomplete",
                "evidence": {"missing_block_ids": ["b_000002"], "extra_block_ids": []},
            }
            write_document_cleaning_gate(gate_path, contradictory)
            self.assertFalse(validate_document_cleaning_gate_artifact(gate_path))
            self.assertFalse(document_cleaning_gate_allows_publication(gate_path))

            _write_rejected_patch(run_dir, "p_rejected", "b_000001", "protected_structure_change")
            warning_report = run_document_cleaning_gate(
                run_dir=run_dir,
                blocks=[_block("b_000001", "paragraph", "keep")],
            )
            contradictory_counts = dict(warning_report)
            contradictory_counts["rejected_patch_count"] = 0
            contradictory_counts["rejected_patch_reason_counts"] = {}
            write_document_cleaning_gate(gate_path, contradictory_counts)
            self.assertFalse(validate_document_cleaning_gate_artifact(gate_path))
            self.assertFalse(document_cleaning_gate_allows_publication(gate_path))


def _write_clean_view(run_dir: Path, block_ids: list[str]) -> None:
    entries = []
    for index, block_id in enumerate(block_ids, start=1):
        entries.append({
            "entry_id": f"cv_{index:06d}",
            "ordinal": index,
            "node_id": f"n_{index:06d}",
            "block_id": block_id,
            "parent_block_id": "",
            "entry_kind": "canonical_node",
            "type": "paragraph",
            "status": "keep",
            "patch_ids": [],
            "rule_ids": [],
            "location": {"line_start": index, "line_end": index, "page_start": None, "page_end": None},
        })
    (run_dir / "clean_view.json").write_text(
        json.dumps({
            "schema": "kbprep.clean_view.v1",
            "source_artifact": "canonical_ir/typed_nodes.json",
            "patch_artifact": "cleaning_patches.jsonl",
            "entry_count": len(entries),
            "entries": entries,
        }),
        encoding="utf-8",
    )


def _write_rejected_patch(run_dir: Path, patch_id: str, block_id: str, reason_code: str) -> None:
    record = {
        "schema": "kbprep.rejected_cleaning_patch.v1",
        "patch_id": patch_id,
        "block_id": block_id,
        "reason_code": reason_code,
        "policy_snapshot_hash": "abc123",
        "text_changed": False,
        "location": {"line_start": 1, "line_end": 1, "page_start": None, "page_end": None},
    }
    (run_dir / "rejected_patches.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")


def _block(block_id: str, block_type: str, status: str) -> dict:
    return {
        "block_id": block_id,
        "type": block_type,
        "status": status,
        "text": "Useful body",
        "line_start": 1,
        "line_end": 1,
        "page_start": None,
        "page_end": None,
    }


if __name__ == "__main__":
    unittest.main()
