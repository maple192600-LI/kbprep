import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.feedback import dictionary_suggestions, promotion_history, rerun_verification


def _capture_envelope(fn, payload):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fn(payload)
    except EnvelopeExit as exc:
        return exc.code, json.loads(out.getvalue())
    raise AssertionError("expected JSON envelope")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class FeedbackPromotionRound2CoverageTests(unittest.TestCase):
    def test_dictionary_suggestions_use_scope_based_feedback_thresholds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_dir = root / "rules"

            def accepted(rule_id: str, scope: str, pattern: str, document_type: str = "course") -> dict:
                return {
                    "schema": "kbprep.rule_proposal.v1",
                    "id": rule_id,
                    "status": "accepted",
                    "action": "discard",
                    "scope": scope,
                    "match": "literal",
                    "pattern": pattern,
                    "reason": "confirmed feedback",
                    "risk_note": "review before promotion",
                    "created_from_run": "run",
                    "requires_confirmation": True,
                    "owner_confirmation_status": "confirmed",
                    "examples": [pattern],
                    "counterexamples": ["正文案例：这是需要保留的方法内容。"],
                    "document_type": document_type,
                }

            _write_jsonl(rules_dir / "accepted_rules.jsonl", [
                accepted("user-1", "user", "用户污染1", "user_doc"),
                accepted("user-2", "user", "用户污染2", "user_doc"),
                accepted("doc-1", "document_type", "课程污染1", "doc_type"),
                accepted("doc-2", "document_type", "课程污染2", "doc_type"),
                accepted("global-1", "global", "全局污染1", "global_doc"),
                accepted("global-2", "global", "全局污染2", "global_doc"),
                accepted("global-3", "global", "全局污染3", "global_doc"),
                accepted("global-4", "global", "全局污染4", "global_doc"),
            ])

            code, envelope = _capture_envelope(
                dictionary_suggestions._suggest_dictionary_updates,
                {"rules_dir": str(rules_dir), "min_feedback_count": 1},
            )

            self.assertEqual(code, 0)
            suggestions = envelope["data"]["suggestions"]["suggestions"]
            self.assertEqual([item["document_type"] for item in suggestions], ["user_doc"])
            self.assertEqual(suggestions[0]["feedback_scope"], "user")
            self.assertEqual(suggestions[0]["min_feedback_count"], 2)
            self.assertEqual(envelope["data"]["suggestions"]["min_feedback_count_by_scope"]["global"], 5)

            _write_jsonl(rules_dir / "accepted_rules.jsonl", [
                accepted("doc-1", "document_type", "课程污染1", "doc_type"),
                accepted("doc-2", "document_type", "课程污染2", "doc_type"),
                accepted("doc-3", "document_type", "课程污染3", "doc_type"),
                accepted("global-1", "global", "全局污染1", "global_doc"),
                accepted("global-2", "global", "全局污染2", "global_doc"),
                accepted("global-3", "global", "全局污染3", "global_doc"),
                accepted("global-4", "global", "全局污染4", "global_doc"),
                accepted("global-5", "global", "全局污染5", "global_doc"),
            ])

            code, envelope = _capture_envelope(
                dictionary_suggestions._suggest_dictionary_updates,
                {"rules_dir": str(rules_dir), "min_feedback_count": 1},
            )

            self.assertEqual(code, 0)
            suggestions = envelope["data"]["suggestions"]["suggestions"]
            self.assertEqual(
                [(item["document_type"], item["feedback_scope"], item["min_feedback_count"]) for item in suggestions],
                [("doc_type", "document_type", 3), ("global_doc", "global", 5)],
            )

    def test_report_dictionary_suggestions_require_threshold_and_skip_rejected_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_dir = root / "rules"

            def accepted(rule_id: str, pattern: str, *, match: str = "literal") -> dict:
                return {
                    "schema": "kbprep.rule_proposal.v1",
                    "id": rule_id,
                    "status": "accepted",
                    "action": "discard",
                    "scope": "document_type",
                    "match": match,
                    "pattern": pattern,
                    "reason": "confirmed report wrapper pollution",
                    "risk_note": "review before promotion",
                    "created_from_run": "run",
                    "requires_confirmation": True,
                    "owner_confirmation_status": "confirmed",
                    "examples": [pattern],
                    "counterexamples": ["案例复盘：ExampleMemberCircle不是目标，留存指标才是判断标准。"],
                    "document_type": "report",
                }

            def rejected(rule_id: str, pattern: str, *, match: str = "literal") -> dict:
                return {
                    "schema": "kbprep.rule_proposal.v1",
                    "id": rule_id,
                    "status": "rejected",
                    "action": "discard",
                    "scope": "document_type",
                    "match": match,
                    "pattern": pattern,
                    "reason": "would remove useful method content",
                    "document_type": "report",
                }

            _write_jsonl(rules_dir / "accepted_rules.jsonl", [
                accepted("report-1", "ExampleTrainingCamp"),
                accepted("report-2", "ExampleAuthor"),
            ])

            code, envelope = _capture_envelope(
                dictionary_suggestions._suggest_dictionary_updates,
                {"rules_dir": str(rules_dir), "min_feedback_count": 1},
            )
            self.assertEqual(code, 0)
            self.assertEqual(envelope["data"]["suggestions"]["suggestions"], [])

            broad_pattern = ".*ExampleMemberCircle.*"
            _write_jsonl(rules_dir / "accepted_rules.jsonl", [
                accepted("report-1", "ExampleTrainingCamp"),
                accepted("report-2", "ExampleAuthor"),
                accepted("report-3", "ExampleTool"),
                accepted("report-4", broad_pattern, match="regex"),
            ])
            _write_jsonl(rules_dir / "rejected_rules.jsonl", [
                rejected("report-reject-1", broad_pattern, match="regex"),
            ])

            code, envelope = _capture_envelope(
                dictionary_suggestions._suggest_dictionary_updates,
                {"rules_dir": str(rules_dir), "min_feedback_count": 1},
            )

            self.assertEqual(code, 0)
            suggestions = envelope["data"]["suggestions"]["suggestions"]
            self.assertEqual(len(suggestions), 1)
            self.assertEqual(suggestions[0]["document_type"], "report")
            self.assertEqual(suggestions[0]["feedback_scope"], "document_type")
            self.assertEqual(suggestions[0]["min_feedback_count"], 3)
            proposed_patterns = [item["pattern"] for item in suggestions[0]["proposed_rules"]]
            self.assertEqual(proposed_patterns, ["ExampleTrainingCamp", "ExampleAuthor", "ExampleTool"])
            self.assertNotIn(broad_pattern, proposed_patterns)

    def test_promote_dictionary_suggestion_writes_rule_file_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_dir = root / "rules"
            target_rules_dir = root / "target"
            suggestion = {
                "schema": "kbprep.dictionary_suggestion.v1",
                "document_type": "course",
                "target": "rules/document_types/course.json",
                "required_confirmation": True,
                "proposed_rules": [
                    {
                        "action": "discard",
                        "match": "literal",
                        "pattern": "扫码关注",
                        "reason": "confirmed CTA",
                        "source_proposal_id": "p1",
                        "accepted_rule_id": "a1",
                    },
                    {
                        "action": "review",
                        "match": "regex",
                        "pattern": "可能营销.+",
                        "reason": "review boundary",
                    },
                ],
            }
            suggestions_path = rules_dir / "dictionary_suggestions.jsonl"
            _write_jsonl(suggestions_path, [suggestion])

            code, envelope = _capture_envelope(
                dictionary_suggestions._promote_dictionary_suggestion,
                {
                    "confirm_dictionary_update": True,
                    "document_type": "course",
                    "rules_dir": str(rules_dir),
                    "target_rules_dir": str(target_rules_dir),
                    "suggestions_file": str(suggestions_path),
                },
            )

            self.assertEqual(code, 0)
            promoted = envelope["data"]["promoted"]
            self.assertEqual(promoted["promoted_count"], 2)
            target_path = Path(promoted["target_path"])
            self.assertTrue(target_path.exists())
            target = json.loads(target_path.read_text(encoding="utf-8"))
            self.assertEqual(target["schema"], "kbprep.cleaning_rules.v1")
            self.assertEqual(len(target["rules"]), 2)
            history = target_rules_dir / "promotion_history.jsonl"
            self.assertTrue(history.exists())

            # A second promotion should skip duplicates and create a backup.
            code, envelope = _capture_envelope(
                dictionary_suggestions._promote_dictionary_suggestion,
                {
                    "confirm_dictionary_update": True,
                    "document_type": "course",
                    "rules_dir": str(rules_dir),
                    "target_rules_dir": str(target_rules_dir),
                    "suggestions_file": str(suggestions_path),
                },
            )
            self.assertEqual(envelope["data"]["promoted"]["promoted_count"], 0)
            self.assertEqual(envelope["data"]["promoted"]["skipped_duplicates"], 2)
            self.assertTrue(Path(envelope["data"]["promoted"]["backup_path"]).exists())

    def test_promotion_history_override_reports_failed_sample_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_dir = root / "rules"
            target_rules_dir = root / "target"
            suggestions_path = rules_dir / "dictionary_suggestions.jsonl"
            _write_jsonl(suggestions_path, [
                {
                    "schema": "kbprep.dictionary_suggestion.v1",
                    "document_type": "course",
                    "target": "rules/document_types/course.json",
                    "required_confirmation": True,
                    "proposed_rules": [
                        {
                            "action": "discard",
                            "match": "literal",
                            "pattern": "课程污染",
                            "reason": "confirmed CTA",
                        },
                    ],
                },
            ])
            _write_jsonl(target_rules_dir / "promotion_history.jsonl", [
                {
                    "schema": "kbprep.dictionary_promotion_history.v1",
                    "created_at": "2026-06-02T00:00:00Z",
                    "document_type": "course",
                    "regression_verification": {
                        "status": "failed",
                        "samples": [
                            {
                                "ok": False,
                                "run_dir": str(root / "runs" / "failed-course"),
                                "reason": "discard_pattern_still_in_cleaned",
                                "worker_error": {"code": "E_QA_FAILED"},
                            },
                        ],
                    },
                },
            ])

            code, envelope = _capture_envelope(
                dictionary_suggestions._promote_dictionary_suggestion,
                {
                    "confirm_dictionary_update": True,
                    "document_type": "course",
                    "rules_dir": str(rules_dir),
                    "target_rules_dir": str(target_rules_dir),
                    "suggestions_file": str(suggestions_path),
                },
            )
            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["details"]["failed_samples"][0]["reason"], "discard_pattern_still_in_cleaned")

            code, envelope = _capture_envelope(
                dictionary_suggestions._promote_dictionary_suggestion,
                {
                    "confirm_dictionary_update": True,
                    "document_type": "course",
                    "rules_dir": str(rules_dir),
                    "target_rules_dir": str(target_rules_dir),
                    "suggestions_file": str(suggestions_path),
                    "allow_failed_promotion_history": True,
                },
            )

            self.assertEqual(code, 0)
            history_risk = envelope["data"]["promoted"]["history_risk"]
            self.assertEqual(history_risk["status"], "override_used")
            self.assertIn("explicit override", history_risk["override_warning"])
            self.assertEqual(history_risk["failed_samples"][0]["worker_error_code"], "E_QA_FAILED")

    def test_dictionary_promotion_defaults_to_project_private_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_dir = root / "feedback" / "user"
            public_rules_dir = root / "public-rules"
            suggestions_path = rules_dir / "dictionary_suggestions.jsonl"
            _write_jsonl(suggestions_path, [
                {
                    "schema": "kbprep.dictionary_suggestion.v1",
                    "document_type": "course",
                    "target": "rules/document_types/course.json",
                    "required_confirmation": True,
                    "proposed_rules": [
                        {
                            "action": "discard",
                            "match": "literal",
                            "pattern": "扫码关注",
                            "reason": "confirmed CTA",
                        },
                    ],
                },
            ])

            with patch.dict("os.environ", {"KBPREP_PROJECT_ROOT": str(root), "KBPREP_RULES_ROOT": str(public_rules_dir)}):
                code, envelope = _capture_envelope(
                    dictionary_suggestions._promote_dictionary_suggestion,
                    {
                        "confirm_dictionary_update": True,
                        "document_type": "course",
                        "rules_dir": str(rules_dir),
                        "suggestions_file": str(suggestions_path),
                    },
                )

            self.assertEqual(code, 0)
            target_path = Path(envelope["data"]["promoted"]["target_path"])
            self.assertEqual(target_path, root / ".kbprep" / "rules" / "document_types" / "course.json")
            self.assertTrue(target_path.exists())
            self.assertFalse((public_rules_dir / "document_types" / "course.json").exists())

    def test_dictionary_promotion_requires_public_write_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_dir = root / "feedback" / "user"
            public_rules_dir = root / "public-rules"
            suggestions_path = rules_dir / "dictionary_suggestions.jsonl"
            _write_jsonl(suggestions_path, [
                {
                    "schema": "kbprep.dictionary_suggestion.v1",
                    "document_type": "course",
                    "target": "rules/document_types/course.json",
                    "required_confirmation": True,
                    "proposed_rules": [
                        {
                            "action": "discard",
                            "match": "literal",
                            "pattern": "扫码关注",
                            "reason": "confirmed CTA",
                        },
                    ],
                },
            ])
            payload = {
                "confirm_dictionary_update": True,
                "document_type": "course",
                "rules_dir": str(rules_dir),
                "target_rules_dir": str(public_rules_dir),
                "suggestions_file": str(suggestions_path),
            }

            with (
                patch.dict("os.environ", {"KBPREP_RULES_ROOT": str(public_rules_dir)}),
                patch("kbprep_worker.feedback.support.builtin_rules_root", return_value=public_rules_dir),
            ):
                code, envelope = _capture_envelope(
                    dictionary_suggestions._promote_dictionary_suggestion,
                    payload,
                )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_CONFIRMATION_REQUIRED")
            self.assertIn("confirm_public_write", envelope["error"]["message"])
            self.assertFalse((public_rules_dir / "document_types" / "course.json").exists())

            with (
                patch.dict("os.environ", {"KBPREP_PROJECT_ROOT": str(root), "KBPREP_RULES_ROOT": str(public_rules_dir)}),
                patch("kbprep_worker.feedback.support.builtin_rules_root", return_value=public_rules_dir),
            ):
                code, envelope = _capture_envelope(
                    dictionary_suggestions._promote_dictionary_suggestion,
                    {**payload, "confirm_public_write": True},
                )

            self.assertEqual(code, 0)
            self.assertTrue((public_rules_dir / "document_types" / "course.json").exists())
            self.assertEqual(Path(envelope["data"]["promoted"]["target_path"]).parent, public_rules_dir / "document_types")
            self.assertFalse((public_rules_dir / "promotion_history.jsonl").exists())
            private_history = root / ".kbprep" / "rules" / "promotion_history.jsonl"
            self.assertTrue(private_history.exists())
            self.assertEqual(Path(envelope["data"]["promoted"]["promotion_history_path"]), private_history)

            with (
                patch.dict("os.environ", {"KBPREP_PROJECT_ROOT": str(root)}),
                patch("kbprep_worker.feedback.support.builtin_rules_root", return_value=public_rules_dir),
            ):
                code, envelope = _capture_envelope(
                    promotion_history._summarize_promotion_history,
                    {"target_rules_dir": str(public_rules_dir), "document_type": "course"},
                )
            self.assertEqual(code, 0)
            self.assertEqual(envelope["data"]["summary"]["history_path"], str(private_history))
            self.assertEqual(envelope["data"]["summary"]["total_promotions"], 1)

            with (
                patch.dict("os.environ", {"KBPREP_PROJECT_ROOT": str(root)}),
                patch("kbprep_worker.feedback.support.builtin_rules_root", return_value=public_rules_dir),
            ):
                code, envelope = _capture_envelope(
                    promotion_history._resolve_promotion_failures,
                    {
                        "target_rules_dir": str(public_rules_dir),
                        "document_type": "course",
                        "confirm_failure_resolved": True,
                    },
                )
            self.assertEqual(code, 0)
            self.assertEqual(envelope["data"]["resolution"]["status"], "not_needed")

    def test_packaged_public_detection_ignores_rules_root_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_dir = root / "feedback" / "user"
            packaged_rules_dir = root / "packaged-rules"
            override_rules_dir = root / "override-rules"
            suggestions_path = rules_dir / "dictionary_suggestions.jsonl"
            _write_jsonl(suggestions_path, [
                {
                    "schema": "kbprep.dictionary_suggestion.v1",
                    "document_type": "course",
                    "target": "rules/document_types/course.json",
                    "required_confirmation": True,
                    "proposed_rules": [
                        {
                            "action": "discard",
                            "match": "literal",
                            "pattern": "扫码关注",
                            "reason": "confirmed CTA",
                        },
                    ],
                },
            ])

            with (
                patch.dict("os.environ", {"KBPREP_RULES_ROOT": str(override_rules_dir)}),
                patch("kbprep_worker.feedback.support.builtin_rules_root", return_value=packaged_rules_dir),
            ):
                code, envelope = _capture_envelope(
                    dictionary_suggestions._promote_dictionary_suggestion,
                    {
                        "confirm_dictionary_update": True,
                        "document_type": "course",
                        "rules_dir": str(rules_dir),
                        "target_rules_dir": str(packaged_rules_dir),
                        "suggestions_file": str(suggestions_path),
                    },
                )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_CONFIRMATION_REQUIRED")
            self.assertIn("confirm_public_write", envelope["error"]["message"])
            self.assertFalse((packaged_rules_dir / "document_types" / "course.json").exists())

    def test_dictionary_promotion_validation_failures_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            suggestions = root / "suggestions.jsonl"
            _write_jsonl(suggestions, [{"schema": "kbprep.dictionary_suggestion.v1", "document_type": "course"}])
            code, envelope = _capture_envelope(
                dictionary_suggestions._promote_dictionary_suggestion,
                {
                    "confirm_dictionary_update": True,
                    "document_type": "course",
                    "target_rules_dir": str(root / "target"),
                    "suggestions_file": str(suggestions),
                },
            )
            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_INVALID_INPUT")

            code, envelope = _capture_envelope(
                dictionary_suggestions._promote_dictionary_suggestion,
                {
                    "confirm_dictionary_update": False,
                    "document_type": "course",
                    "suggestions_file": str(suggestions),
                },
            )
            self.assertEqual(envelope["error"]["code"], "E_CONFIRMATION_REQUIRED")

    def test_promotion_history_summary_and_resolution_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_rules_dir = root / "target"
            history = target_rules_dir / "promotion_history.jsonl"
            _write_jsonl(history, [
                {
                    "schema": "kbprep.dictionary_promotion_history.v1",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "document_type": "course",
                    "regression_verification": {"status": "failed", "reason": "strict errors"},
                },
                {
                    "schema": "kbprep.dictionary_promotion_history.v1",
                    "created_at": "2026-01-02T00:00:00+00:00",
                    "document_type": "memo",
                    "regression_verification": {"status": "not_requested"},
                },
            ])

            code, envelope = _capture_envelope(
                promotion_history._summarize_promotion_history,
                {"target_rules_dir": str(target_rules_dir)},
            )
            self.assertEqual(code, 0)
            self.assertEqual(envelope["data"]["summary"]["total_promotions"], 2)
            self.assertIn("failed promotions", envelope["data"]["summary"]["recommendation"])
            risk = promotion_history._promotion_history_risk(target_rules_dir=target_rules_dir, document_type="course")
            self.assertEqual(risk["status"], "blocked")

            code, envelope = _capture_envelope(
                promotion_history._resolve_promotion_failures,
                {"target_rules_dir": str(target_rules_dir), "document_type": "course", "confirm_failure_resolved": False},
            )
            self.assertEqual(envelope["error"]["code"], "E_CONFIRMATION_REQUIRED")

            sample_run = root / "run"
            sample_run.mkdir()
            with patch("kbprep_worker.feedback.promotion_history._rerun_representative_source", return_value={"ok": True, "status": "passed"}):  # noqa: E501
                code, envelope = _capture_envelope(
                    promotion_history._resolve_promotion_failures,
                    {
                        "target_rules_dir": str(target_rules_dir),
                        "document_type": "course",
                        "confirm_failure_resolved": True,
                        "representative_run_dirs": [str(sample_run), str(sample_run)],
                    },
                )
            self.assertEqual(code, 0)
            self.assertEqual(envelope["data"]["resolution"]["resolved_failed_promotions"], 1)

            code, envelope = _capture_envelope(
                promotion_history._resolve_promotion_failures,
                {
                    "target_rules_dir": str(target_rules_dir),
                    "document_type": "course",
                    "confirm_failure_resolved": True,
                    "representative_run_dirs": [str(sample_run)],
                },
            )
            self.assertEqual(envelope["data"]["resolution"]["status"], "not_needed")

    def test_rerun_verification_subprocess_success_and_failure_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_root = root / "out"
            run_dir = output_root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            source = root / "source.md"
            source.write_text("正文", encoding="utf-8")
            cleaned = root / "cleaned.md"
            cleaned.write_text("参数保留", encoding="utf-8")
            (output_root / "latest.json").write_text(json.dumps({"input_path": str(source)}), encoding="utf-8")
            (run_dir / "quality_report.json").write_text(json.dumps({"profile": "standard"}), encoding="utf-8")

            success_stdout = json.dumps({
                "ok": True,
                "data": {
                    "run_dir": str(root / "new-run"),
                    "latest_outputs": {"cleaned_md": str(cleaned), "quality_report": str(root / "quality.json")},
                    "strict_errors": [],
                },
            })
            with patch("subprocess.run", return_value=subprocess.CompletedProcess(["py"], 0, stdout=success_stdout, stderr="")):
                sample = rerun_verification._rerun_representative_source(
                    run_dir=run_dir,
                    target_rules_dir=root / "rules",
                    promoted_rules=[
                        {"id": "discard", "action": "discard", "match": "literal", "pattern": "扫码"},
                        {"id": "protect", "action": "protect", "match": "literal", "pattern": "参数"},
                    ],
                )
            self.assertTrue(sample["ok"])
            self.assertEqual(sample["status"], "passed")

            fail_stdout = json.dumps({"ok": False, "error": {"code": "E_QA_FAILED"}})
            with patch("subprocess.run", return_value=subprocess.CompletedProcess(["py"], 1, stdout=fail_stdout, stderr="err")):
                failed = rerun_verification._rerun_after_accept(
                    {"created_from_run": str(run_dir), "action": "discard", "match": "literal", "pattern": "扫码"},
                    root / "rules",
                    {"rerun_after_accept": True},
                )
            self.assertFalse(failed["ok"])
            self.assertEqual(failed["worker_error"]["code"], "E_QA_FAILED")

            with patch("subprocess.run", side_effect=RuntimeError("boom")):
                errored = rerun_verification._rerun_after_accept(
                    {"created_from_run": str(run_dir), "action": "discard", "match": "literal", "pattern": "扫码"},
                    root / "rules",
                    {"rerun_after_accept": True},
                )
            self.assertFalse(errored["ok"])
            self.assertEqual(errored["status"], "failed")

            unavailable = rerun_verification._rerun_after_dictionary_promotion(
                suggestion={"proposed_rules": []},
                target_rules_dir=root / "rules",
                promoted_rules=[],
                data={"rerun_after_promotion": True},
            )
            self.assertEqual(unavailable["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
