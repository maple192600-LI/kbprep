import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.detail_signal_rules import load_detail_signals
from kbprep_worker.quality.retention import (
    _detail_retention_stats,
    _image_retention_stats,
    _output_retention_stats,
)

ROOT = Path(__file__).resolve().parents[2]


class QualityRetentionBehaviorTests(unittest.TestCase):
    def test_detail_signals_are_loaded_from_rules_not_retention_source(self):
        signals = load_detail_signals()
        source = (ROOT / "python/kbprep_worker/quality/retention.py").read_text(encoding="utf-8")

        self.assertIn("tool_or_platform", signals.patterns)
        self.assertIsNotNone(signals.patterns["tool_or_platform"].search("打开 Obsidian 平台"))
        self.assertIsNotNone(signals.patterns["parameter"].search("set threshold=0.8"))
        self.assertNotIn("DETAIL_SIGNAL_PATTERNS", source)

    def test_chinese_and_english_detail_signals_work_from_rules(self):
        blocks = [
            {
                "block_id": "zh_tool",
                "status": "discard",
                "type": "paragraph",
                "text": "打开 Obsidian 平台后台，并记录参数 threshold=0.8。",
            },
            {
                "block_id": "en_step",
                "status": "discard",
                "type": "paragraph",
                "text": "Step 1: configure retry_count=3.",
            },
        ]

        stats = _detail_retention_stats(blocks)

        self.assertEqual(stats["tool_or_platform"]["discarded_blocks"], 1)
        self.assertEqual(stats["parameter"]["discarded_blocks"], 2)
        self.assertEqual(stats["operation_step"]["discarded_blocks"], 1)
        self.assertIn("en_step", stats["discarded_detail_block_ids"])

    def test_rules_root_override_without_detail_file_falls_back_to_builtin(self):
        with tempfile.TemporaryDirectory() as tmp:
            load_detail_signals.cache_clear()
            with patch.dict("os.environ", {"KBPREP_RULES_ROOT": tmp}):
                signals = load_detail_signals()
        load_detail_signals.cache_clear()

        self.assertIsNotNone(signals.patterns["parameter"].search("threshold=0.8"))

    def test_output_retention_tolerates_safe_markdown_formatting_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "cleaned.md").write_text(
                "\n".join(
                    [
                        "Step 1: configure threshold=0.8.",
                        "",
                        "```js",
                        "const    value = 1;",
                        "```",
                        "",
                        "|Field|Value|",
                        "|---|---|",
                        "|retry_count|3|",
                        "",
                        "[Docs](https://example.com/docs)",
                    ]
                ),
                encoding="utf-8",
            )
            blocks = [
                {
                    "block_id": "param",
                    "status": "keep",
                    "type": "operation_step",
                    "text": "Step 1: configure threshold = 0.8.",
                },
                {
                    "block_id": "code",
                    "status": "keep",
                    "type": "code",
                    "text": "```js\n    const value = 1;\n```",
                },
                {
                    "block_id": "table",
                    "status": "keep",
                    "type": "table",
                    "text": "| Field | Value |\n| --- | --- |\n| retry_count | 3 |",
                },
                {
                    "block_id": "link",
                    "status": "keep",
                    "type": "paragraph",
                    "text": "Docs: https://example.com/docs",
                },
            ]

            stats = _output_retention_stats(blocks, run_dir)

        self.assertEqual(stats["missing_total"], 0)
        self.assertEqual(stats["parameter"]["missing_count"], 0)
        self.assertEqual(stats["code"]["missing_count"], 0)
        self.assertEqual(stats["table"]["missing_count"], 0)
        self.assertEqual(stats["link"]["missing_count"], 0)

    def test_output_retention_still_fails_when_url_is_removed_or_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "cleaned.md").write_text("Docs: https://short.example/x", encoding="utf-8")
            blocks = [
                {
                    "block_id": "link",
                    "status": "keep",
                    "type": "paragraph",
                    "text": "Docs: https://example.com/docs",
                }
            ]

            stats = _output_retention_stats(blocks, run_dir)

        self.assertEqual(stats["link"]["missing"], ["https://example.com/docs"])
        self.assertFalse(stats["link"]["strict"])
        self.assertEqual(stats["missing_total"], 0)

    def test_discarded_plain_url_pollution_does_not_count_as_detail_loss(self):
        blocks = [
            {
                "block_id": "footer_link",
                "status": "discard",
                "type": "paragraph",
                "text": "More updates at https://example.com/news",
            },
            {
                "block_id": "kept_step",
                "status": "keep",
                "type": "operation_step",
                "text": "Step 1: set threshold=0.8.",
            },
        ]

        stats = _detail_retention_stats(blocks)

        self.assertEqual(stats["discarded_detail_block_ids"], [])
        self.assertEqual(stats["link"]["discarded_blocks"], 1)

    def test_discarded_url_with_strong_detail_signal_still_counts_as_detail_loss(self):
        blocks = [
                {
                    "block_id": "lost_config",
                    "status": "discard",
                    "type": "operation_step",
                    "text": "Step 1: set threshold=0.8 and open https://example.com/config.",
                }
            ]

        stats = _detail_retention_stats(blocks)

        self.assertEqual(stats["discarded_detail_block_ids"], ["lost_config"])

    def test_svg_retention_accepts_responsive_and_single_quote_svg_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "responsive.svg").write_text(
                "<svg viewBox='0 0 100 100'><path d='M0 0h100v100z'/></svg>",
                encoding="utf-8",
            )
            (run_dir / "lowercase.svg").write_text(
                "<svg viewbox='0 0 100 100'><path d='M0 0h100v100z'/></svg>",
                encoding="utf-8",
            )
            blocks = [
                {
                    "block_id": "responsive",
                    "status": "keep",
                    "type": "image",
                    "text": "![responsive](responsive.svg)",
                },
                {
                    "block_id": "lowercase",
                    "status": "keep",
                    "type": "image",
                    "text": "![lowercase](lowercase.svg)",
                },
            ]

            stats = _image_retention_stats(blocks, run_dir)

        self.assertEqual(stats["missing_file_count"], 0)
        self.assertEqual(stats["invalid_svg_count"], 0)

    def test_svg_retention_rejects_non_svg_files_referenced_as_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "broken.svg").write_text("not svg", encoding="utf-8")
            blocks = [
                {
                    "block_id": "broken",
                    "status": "keep",
                    "type": "image",
                    "text": "![broken](broken.svg)",
                }
            ]

            stats = _image_retention_stats(blocks, run_dir)

        self.assertEqual(stats["invalid_svg_files"], ["broken.svg"])


if __name__ == "__main__":
    unittest.main()
