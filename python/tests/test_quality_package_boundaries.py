import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.quality import (
    detail_categories,
    is_known_pollution_without_detail,
    run_quality_check,
)
from kbprep_worker.quality.conversion_integrity import (
    source_conversion_integrity,
    source_text_layer_status,
)
from kbprep_worker.quality.gates import build_quality_gates
from kbprep_worker.quality.retention import detail_retention_stats, output_retention_stats


class QualityPackageBoundaryTests(unittest.TestCase):
    def test_quality_runner_does_not_import_private_cross_module_helpers(self):
        root = Path(__file__).resolve().parents[2]
        runner_source = (root / "python" / "kbprep_worker" / "quality" / "runner.py").read_text(encoding="utf-8")

        self.assertNotRegex(runner_source, r"from \.[a-z_]+ import \(\s*\n\s*_")
        self.assertNotRegex(runner_source, r"from \.[a-z_]+ import _")

    def test_public_compatibility_exports_still_work(self):
        self.assertTrue(callable(run_quality_check))
        categories = detail_categories({
            "type": "paragraph",
            "text": "步骤1：设置 threshold=0.82 并访问 https://example.com/config。",
        })
        self.assertIn("operation_step", categories)
        self.assertFalse(is_known_pollution_without_detail({"type": "paragraph", "text": "正文"}, categories))

    def test_conversion_integrity_helpers_remain_importable(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "source.md"
            converted = run_dir / "converted.md"
            source.write_text("# Title\n\n## Critical\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n", encoding="utf-8")
            converted.write_text("# Title\n\nBody only.\n", encoding="utf-8")
            (run_dir / "run_metadata.json").write_text(json.dumps({"input_path": str(source)}), encoding="utf-8")
            report = {
                "input_extension": ".md",
                "converter": "direct_text",
                "converted_md": str(converted),
            }

            integrity = source_conversion_integrity(run_dir, report)
            layer = source_text_layer_status(
                {
                    "needs_ocr": True,
                    "pdf_subtype": "garbled_text_layer",
                    "text_quality": {"unreadable_text_ratio": 0.5},
                },
                {"converter": "mineru", "converted_bytes": 100},
            )

        self.assertTrue(integrity["checked"])
        self.assertEqual(integrity["missing_heading_count"], 1)
        self.assertEqual(integrity["missing_table_count"], 1)
        self.assertTrue(layer["superseded_by_conversion"])

    def test_source_conversion_integrity_checks_html_direct_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "source.html"
            converted = run_dir / "converted.md"
            source.write_text(
                "<html><body><h1>Title</h1><h2>Critical Section</h2>"
                "<table><tr><th>A</th></tr><tr><td>B</td></tr></table></body></html>",
                encoding="utf-8",
            )
            converted.write_text("# Title\n\nBody only.\n", encoding="utf-8")
            (run_dir / "run_metadata.json").write_text(json.dumps({"input_path": str(source)}), encoding="utf-8")
            report = {
                "input_extension": ".html",
                "converter": "direct_text",
                "converted_md": str(converted),
            }

            integrity = source_conversion_integrity(run_dir, report)

        self.assertTrue(integrity["checked"])
        self.assertEqual(integrity["missing_heading_count"], 1)
        self.assertEqual(integrity["missing_headings"], ["critical section"])
        self.assertEqual(integrity["missing_table_count"], 1)

    def test_retention_and_gate_helpers_remain_importable(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "cleaned.md").write_text("步骤1：设置 threshold=0.82。\n", encoding="utf-8")
            blocks = [
                {
                    "block_id": "step1",
                    "status": "keep",
                    "type": "operation_step",
                    "text": "步骤1：设置 threshold=0.82。",
                },
                {
                    "block_id": "lost",
                    "status": "discard",
                    "type": "operation_step",
                    "text": "Step 1: record the failure_reason before retry.",
                },
            ]
            detail = detail_retention_stats(blocks)
            output = output_retention_stats(blocks, run_dir)
            gates, actions = build_quality_gates(
                ["E_SOURCE_CONVERSION_LOSS: 1 source headings missing from converted Markdown"],
                [],
                {"source_type": "markdown_note"},
            )

        self.assertEqual(detail["discarded_detail_block_ids"], ["lost"])
        self.assertEqual(output["cleaned_md"]["missing_total"], 0)
        self.assertEqual(gates[0]["name"], "conversion_integrity")
        self.assertEqual(gates[0]["status"], "fail")
        self.assertEqual(actions[0]["gate"], "conversion_integrity")


if __name__ == "__main__":
    unittest.main()
