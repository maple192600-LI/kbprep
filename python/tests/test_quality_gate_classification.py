import unittest
from pathlib import Path

from kbprep_worker.quality.gates import _quality_gate_for_message, _quality_tasks_from_actions
from kbprep_worker.quality.runner import _append_quality_issue
from kbprep_worker.stages.pipeline_helpers import _quality_gate_name_from_error


class QualityGateClassificationTests(unittest.TestCase):
    def test_plain_words_with_cta_or_qr_substrings_do_not_route_to_cleanup(self):
        self.assertEqual(_quality_gate_for_message("location lookup failed"), "export_readiness")
        self.assertEqual(_quality_gate_for_message("education parser failed"), "export_readiness")
        self.assertEqual(_quality_gate_for_message("sqlite qr cache path failed"), "export_readiness")

    def test_known_error_codes_route_to_declared_gates(self):
        self.assertEqual(_quality_gate_for_message("E_CTA_RESIDUE: CTA remains"), "cleanup_safety")
        self.assertEqual(_quality_gate_for_message("E_QR_RESIDUE: QR remains"), "cleanup_safety")
        self.assertEqual(_quality_gate_for_message("E_BROKEN_CODE_BLOCK: chunk broken"), "splitting_integrity")
        self.assertEqual(_quality_gate_for_message("E_IMAGE_FILE_MISSING: image missing"), "conversion_integrity")

    def test_unstructured_error_text_does_not_guess_gate_from_substrings(self):
        self.assertEqual(_quality_gate_for_message("3 chunks have broken code blocks"), "export_readiness")
        self.assertEqual(_quality_gate_for_message("converted tables missing from block trace"), "export_readiness")
        self.assertEqual(_quality_gate_name_from_error("3 chunks have broken code blocks"), "export_readiness")

    def test_legacy_qa_prefix_is_compatibility_only(self):
        self.assertEqual(_quality_gate_for_message("E_QA_FAILED: old quality error"), "cleanup_safety")
        self.assertEqual(_quality_gate_for_message("W_QA: old quality warning", is_warning=True), "cleanup_safety")

    def test_quality_issue_items_do_not_carry_legacy_code(self):
        strict_errors = []
        quality_issues = []

        _append_quality_issue(strict_errors, quality_issues, "E_CTA_RESIDUE", "cleanup_safety", "CTA remains")

        self.assertEqual(strict_errors, ["E_CTA_RESIDUE: CTA remains"])
        self.assertNotIn("legacy_code", quality_issues[0])

    def test_quality_tasks_are_compact_execution_items(self):
        tasks = _quality_tasks_from_actions(
            {
                "quality_gates": [
                    {
                        "name": "cleanup_safety",
                        "strict_errors": ["E_CTA_RESIDUE: CTA remains"],
                        "warnings": [],
                    }
                ],
                "quality_loop": {"status": "needs_iteration"},
            },
            [
                {
                    "gate": "cleanup_safety",
                    "action": "update_cleaning_rules_or_review_pack",
                    "target": "cleaning_rules",
                    "reason": "Cleaning issue",
                    "strict_error_count": 1,
                }
            ],
            Path("run"),
        )

        item = tasks["tasks"][0]
        self.assertEqual(set(item), {"id", "gate", "action", "reason", "evidence_paths", "commands", "acceptance_checks", "evidence"})
        self.assertNotIn("goal", item)
        self.assertNotIn("background", item)
        self.assertIn(str(Path("run") / "quality_report.json"), item["evidence_paths"])

    def test_quality_tasks_use_gate_specific_repair_commands(self):
        run_dir = Path("run")
        tasks = _quality_tasks_from_actions(
            {
                "quality_gates": [
                    {
                        "name": "conversion_integrity",
                        "strict_errors": ["E_SOURCE_CONVERSION_LOSS: missing text"],
                        "warnings": [],
                    },
                    {
                        "name": "cleanup_safety",
                        "strict_errors": ["E_DETAIL_BLOCK_DISCARDED: detail removed"],
                        "warnings": [],
                    },
                ],
                "quality_loop": {"status": "needs_iteration"},
            },
            [
                {
                    "gate": "conversion_integrity",
                    "action": "inspect_or_rerun_conversion",
                    "reason": "Conversion issue",
                    "strict_error_count": 1,
                },
                {
                    "gate": "cleanup_safety",
                    "action": "update_cleaning_rules_or_review_pack",
                    "reason": "Cleanup issue",
                    "strict_error_count": 1,
                },
            ],
            run_dir,
        )

        commands = [command for task in tasks["tasks"] for command in task["commands"]]
        self.assertNotIn("npm test", commands)
        self.assertNotIn("npm run dev:check", commands)
        self.assertNotIn("npm run python:coverage", commands)
        self.assertTrue(any("conversion_report.json" in command for command in commands))
        self.assertTrue(any("discarded.md" in command for command in commands))
        self.assertTrue(any("kbprep-feedback" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
