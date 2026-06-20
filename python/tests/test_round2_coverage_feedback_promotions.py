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
