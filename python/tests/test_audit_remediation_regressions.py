import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.converter_capabilities import capability_matrix_rows
from kbprep_worker.feedback import proposals
from kbprep_worker.feedback.promotion_history import _promotion_history_document_summary
from kbprep_worker.quality import thresholds
from kbprep_worker.quality.gates import _build_quality_gates
from kbprep_worker.quality.runner import run_quality_check
from kbprep_worker.rule_loader import load_cleaning_rules
from kbprep_worker.stages import pipeline_core


class AuditRemediationRegressionTests(unittest.TestCase):
    def test_unknown_single_file_extension_is_unsupported_not_mineru_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "notes.rtf"
            source.write_text("{\\rtf1 unsupported}", encoding="utf-8")
            state = pipeline_core.PipelineState({"input_path": str(source), "output_root": str(root / "out")})
            state.run_dir = root / "out" / "runs" / "run"
            state.run_dir.mkdir(parents=True)
            state.converted_path = state.run_dir / "converted.md"

            with patch.object(pipeline_core, "_run_mineru_conversion", side_effect=AssertionError("MinerU must not run")):
                with self.assertRaises(pipeline_core.PipelineError) as ctx:
                    pipeline_core._stage_convert(state)

        self.assertEqual(ctx.exception.code, "E_UNSUPPORTED_TYPE")
        self.assertEqual(ctx.exception.details["conversion_strategy"], "unsupported_extension")

    def test_existing_run_lookup_scans_only_recent_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            runs.mkdir()
            for index in range(25):
                run_dir = runs / f"20260611_{index:02d}"
                run_dir.mkdir()
                (run_dir / "quality_report.json").write_text(
                    json.dumps({
                        "source_sha256": "match" if index == 0 else f"other-{index}",
                        "config_hash": "cfg",
                        "plugin_version": "0.5.1",
                        "runtime_cache_key": "runtime",
                        "strict_errors": [],
                    }),
                    encoding="utf-8",
                )

            found = pipeline_core._find_existing_run(root, "match", "cfg", "0.5.1", "runtime")

        self.assertIsNone(found)

    def test_quality_gates_use_structured_issue_gate_not_message_guessing(self):
        gates, actions = _build_quality_gates(
            ["E_CTA_RESIDUE: cta patterns found in non-protected cleaned blocks"],
            [],
            {
                "quality_issues": [
                    {
                        "code": "E_CTA_RESIDUE",
                        "gate": "cleanup_safety",
                        "message": "cta patterns found in non-protected cleaned blocks",
                    }
                ]
            },
        )

        by_name = {gate["name"]: gate for gate in gates}
        self.assertEqual(by_name["cleanup_safety"]["status"], "fail")
        self.assertEqual(by_name["export_readiness"]["status"], "fail")
        self.assertEqual(actions[0]["gate"], "cleanup_safety")

    def test_quality_report_exposes_specific_codes_and_structured_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "conversion_report.json").write_text("{}", encoding="utf-8")
            (run_dir / "converted.md").write_text("protected detail\n", encoding="utf-8")
            (run_dir / "cleaned.md").write_text("", encoding="utf-8")
            (run_dir / "chunks").mkdir()
            blocks = [
                {
                    "block_id": "p1",
                    "protected": True,
                    "status": "discard",
                    "type": "operation_step",
                    "text": "Step 1: keep threshold=0.8 and failure_reason.",
                }
            ]

            report = run_quality_check(blocks, str(run_dir), "generic_block", {"file_id": "sha"})

        codes = [issue["code"] for issue in report["quality_issues"]]
        self.assertIn("E_PROTECTED_BLOCK_LOSS", codes)
        self.assertIn("E_OPERATION_STEP_LOSS", codes)
        self.assertTrue(all(issue.get("gate") for issue in report["quality_issues"]))
        self.assertTrue(any(error.startswith("E_PROTECTED_BLOCK_LOSS") for error in report["strict_errors"]))

    def test_review_pack_threshold_is_named(self):
        self.assertEqual(thresholds.REVIEW_THRESHOLDS["review_pack_low_confidence"], 0.76)

    def test_cleaning_rule_cache_ignores_source_identity_for_base_rules(self):
        if hasattr(load_cleaning_rules, "cache_clear"):
            load_cleaning_rules.cache_clear()
        load_cleaning_rules(source_identity=json.dumps({"source_name": "alpha.md"}))
        load_cleaning_rules(source_identity=json.dumps({"source_name": "beta.md"}))

        self.assertLessEqual(load_cleaning_rules.cache_info().currsize, 1)

    def test_feedback_no_longer_generates_number_variant_regex(self):
        self.assertFalse(hasattr(proposals, "_number_variant_regex"))

    def test_promotion_history_summary_is_owner_readable(self):
        summary = _promotion_history_document_summary("course", [
            {
                "schema": "kbprep.dictionary_promotion_history.v1",
                "created_at": "2026-06-01T00:00:00Z",
                "document_type": "course",
                "promoted_count": 2,
                "skipped_duplicates": 1,
                "regression_verification": {
                    "status": "failed",
                    "sample_count": 2,
                    "passed_count": 1,
                    "failed_count": 1,
                    "samples": [{"ok": False, "error": "CTA residue"}],
                },
            }
        ])

        self.assertEqual(set(summary), {
            "document_type",
            "latest_status",
            "latest_created_at",
            "last_failure_reason",
            "recommended_action",
        })
        self.assertEqual(summary["latest_status"], "failed")
        self.assertEqual(summary["last_failure_reason"], "CTA residue")

    def test_obvious_noise_rules_are_grouped_for_maintenance(self):
        rule_path = Path(__file__).resolve().parents[2] / "rules" / "base" / "obvious_noise.json"
        rule_file = json.loads(rule_path.read_text(encoding="utf-8"))

        self.assertEqual(set(rule_file["rule_groups"]), {
            "generic_cta",
            "english_cta",
            "chinese_cta",
            "web_navigation_footer",
            "image_qr_signals",
        })
        self.assertIn("cta_keywords", rule_file["rule_groups"]["generic_cta"]["keyword_sets"])

    def test_converter_capability_evidence_uses_current_scenario_paths(self):
        for capability in capability_matrix_rows():
            for evidence in capability.get("test_evidence", []):
                self.assertTrue(
                    str(evidence).startswith("src/test/scenarios/"),
                    f"{capability['id']} has stale evidence path: {evidence}",
                )


if __name__ == "__main__":
    unittest.main()
