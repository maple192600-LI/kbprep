import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from kbprep_worker import feedback
from kbprep_worker.feedback import _append_jsonl_locked
from kbprep_worker.feedback.rerun_verification import _rules_only_payload


class FeedbackTests(unittest.TestCase):
    def test_locked_jsonl_append_writes_complete_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "proposed_rules.jsonl")

            _append_jsonl_locked(path, {"id": "one", "text": "第一条"})
            _append_jsonl_locked(path, {"id": "two", "text": "第二条"})

            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual([json.loads(line)["id"] for line in lines], ["one", "two"])

    def test_locked_jsonl_append_uses_separate_lock_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "accepted_rules.jsonl")

            _append_jsonl_locked(path, {"id": "accepted"})

            self.assertTrue(path.exists())
            self.assertTrue(Path(tmp, "accepted_rules.jsonl.lock").exists())

    def test_selective_rerun_plan_from_run_metadata_records_required_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Note\n\n正文\n", encoding="utf-8")
            run_dir = root / "output" / "runs" / "run_001"
            run_dir.mkdir(parents=True)
            (run_dir / "run_metadata.json").write_text(
                json.dumps({
                    "schema": "kbprep.run_metadata.v1",
                    "run_id": "run_001",
                    "source_identity": {
                        "source_name": "source.md",
                        "source_path": str(source),
                    },
                    "document_type": "course",
                    "cleaning_policy_snapshot_hash": "hash-policy-123",
                    "prepare_payload": {
                        "input_path": str(source),
                        "output_root": str(root / "output"),
                        "profile": "standard",
                        "source_url": "https://www.youtube.com/watch?v=ExampleVideo01",
                        "allow_youtube_media_fallback": True,
                    },
                }),
                encoding="utf-8",
            )
            (run_dir / "quality_report.json").write_text(
                json.dumps({"profile": "standard", "document_type": "course"}),
                encoding="utf-8",
            )

            envelope = self._run_feedback({"plan_rerun": True, "run_dir": str(run_dir)})

        plan = envelope["data"]["rerun_plan"]
        self.assertTrue(envelope["ok"])
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["run_id"], "run_001")
        self.assertEqual(plan["document_type"], "course")
        self.assertEqual(plan["policy_snapshot_hash"], "hash-policy-123")
        self.assertEqual(plan["canonical_ir_binding"]["status"], "pending")
        self.assertEqual(plan["source_identity"]["source_name"], "source.md")
        self.assertEqual(plan["prepare_payload"]["mode"], "rules_only")
        self.assertEqual(plan["prepare_payload"]["source_url"], "https://www.youtube.com/watch?v=ExampleVideo01")
        self.assertEqual(plan["prepare_payload"]["allow_youtube_media_fallback"], True)
        self.assertTrue(plan["command_evidence"]["standalone_command"])

    def test_selective_rerun_plan_can_start_from_latest_accepted_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Note\n\n正文\n", encoding="utf-8")
            run_dir = self._metadata_run_dir(root, source, run_id="run_accepted")
            rules_dir = root / "rules" / "user"
            rules_dir.mkdir(parents=True)
            (rules_dir / "accepted_rules.jsonl").write_text(
                json.dumps({
                    "schema": "kbprep.rule_proposal.v1",
                    "id": "proposal-accepted",
                    "status": "accepted",
                    "action": "discard",
                    "scope": "user",
                    "match": "literal",
                    "pattern": "污染",
                    "created_from_run": str(run_dir),
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            envelope = self._run_feedback({
                "plan_rerun": True,
                "accepted_proposal": "latest",
                "rules_dir": str(rules_dir),
            })

        plan = envelope["data"]["rerun_plan"]
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["plan_source"], "accepted_proposal")
        self.assertEqual(plan["accepted_proposal_id"], "proposal-accepted")
        self.assertEqual(plan["run_id"], "run_accepted")
        self.assertEqual(plan["command_evidence"]["environment"]["KBPREP_USER_RULES_DIR"], str(rules_dir))

    def test_execute_selective_rerun_runs_planned_rules_only_prepare(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Note\n\n正文\n", encoding="utf-8")
            run_dir = self._metadata_run_dir(root, source, run_id="run_execute")
            rerun_run_dir = root / "output" / "runs" / "run_execute_rerun"
            cleaned_md = rerun_run_dir / "cleaned.md"
            stdout = json.dumps({
                "ok": True,
                "data": {
                    "run_id": "run_execute_rerun",
                    "run_dir": str(rerun_run_dir),
                    "latest_outputs": {
                        "cleaned_md": str(cleaned_md),
                        "quality_report": str(rerun_run_dir / "quality_report.json"),
                    },
                    "strict_errors": [],
                },
            })
            completed = CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

            with patch(
                "kbprep_worker.feedback.selective_rerun_execution._run_prepare_subprocess",
                return_value=(completed, ""),
            ) as run_prepare:
                envelope = self._run_feedback({
                    "execute_rerun": True,
                    "run_dir": str(run_dir),
                })

        execution = envelope["data"]["rerun_verification"]
        self.assertTrue(envelope["ok"])
        self.assertEqual(execution["status"], "passed")
        self.assertTrue(execution["ok"])
        self.assertEqual(execution["run_id"], "run_execute")
        self.assertEqual(execution["plan"]["status"], "planned")
        self.assertEqual(execution["plan"]["command_evidence"]["would_execute"], False)
        self.assertEqual(execution["command_evidence"]["actually_executed"], True)
        self.assertEqual(execution["command_evidence"]["payload"]["mode"], "rules_only")
        self.assertEqual(run_prepare.call_args.args[0]["source_url"], "https://www.youtube.com/watch?v=ExampleVideo01")
        self.assertEqual(run_prepare.call_args.args[0]["allow_youtube_media_fallback"], True)
        self.assertEqual(run_prepare.call_args.args[0]["input_path"], str(source))

    def test_execute_selective_rerun_can_start_from_latest_accepted_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Note\n\n正文\n", encoding="utf-8")
            run_dir = self._metadata_run_dir(root, source, run_id="run_execute_accepted")
            rules_dir = root / "rules" / "user"
            rules_dir.mkdir(parents=True)
            (rules_dir / "accepted_rules.jsonl").write_text(
                json.dumps({
                    "schema": "kbprep.rule_proposal.v1",
                    "id": "proposal-accepted",
                    "status": "accepted",
                    "action": "discard",
                    "scope": "user",
                    "match": "literal",
                    "pattern": "污染",
                    "created_from_run": str(run_dir),
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            completed = CompletedProcess(args=[], returncode=0, stdout=_success_rerun_stdout(root), stderr="")

            with patch(
                "kbprep_worker.feedback.selective_rerun_execution._run_prepare_subprocess",
                return_value=(completed, ""),
            ) as run_prepare:
                envelope = self._run_feedback({
                    "execute_rerun": True,
                    "accepted_proposal": "latest",
                    "rules_dir": str(rules_dir),
                })

        execution = envelope["data"]["rerun_verification"]
        self.assertTrue(envelope["ok"])
        self.assertEqual(execution["status"], "passed")
        self.assertEqual(execution["plan"]["plan_source"], "accepted_proposal")
        self.assertEqual(execution["plan"]["accepted_proposal_id"], "proposal-accepted")
        self.assertEqual(execution["command_evidence"]["environment"]["KBPREP_USER_RULES_DIR"], str(rules_dir))
        self.assertEqual(run_prepare.call_args.args[0]["input_path"], str(source))

    def test_execute_selective_rerun_can_start_from_document_type_promotion_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Note\n\n正文\n", encoding="utf-8")
            run_dir = self._metadata_run_dir(root, source, run_id="run_execute_history")
            target_rules_dir = root / "rules"
            target_rules_dir.mkdir()
            (target_rules_dir / "promotion_history.jsonl").write_text(
                json.dumps({
                    "schema": "kbprep.dictionary_promotion_history.v1",
                    "document_type": "course",
                    "regression_verification": {
                        "status": "passed",
                        "samples": [{"ok": True, "run_dir": str(run_dir)}],
                    },
                }) + "\n",
                encoding="utf-8",
            )
            completed = CompletedProcess(args=[], returncode=0, stdout=_success_rerun_stdout(root), stderr="")

            with patch(
                "kbprep_worker.feedback.selective_rerun_execution._run_prepare_subprocess",
                return_value=(completed, ""),
            ) as run_prepare:
                envelope = self._run_feedback({
                    "execute_rerun": True,
                    "document_type": "course",
                    "target_rules_dir": str(target_rules_dir),
                })

        execution = envelope["data"]["rerun_verification"]
        self.assertTrue(envelope["ok"])
        self.assertEqual(execution["status"], "passed")
        self.assertEqual(execution["plan"]["plan_source"], "promotion_history")
        self.assertEqual(execution["command_evidence"]["environment"]["KBPREP_RULES_ROOT"], str(target_rules_dir))
        self.assertEqual(run_prepare.call_args.args[0]["input_path"], str(source))

    def test_rules_only_payload_preserves_safe_prepare_context(self):
        payload = _rules_only_payload({
            "input_path": "source.url",
            "output_root": "out",
            "profile": "standard",
            "source_url": "https://www.youtube.com/watch?v=ExampleVideo01",
            "allow_youtube_media_fallback": True,
            "source_domain": "youtube.com",
            "unsafe_key": "drop-me",
            "mode": "rules_plus_review_pack",
            "force": False,
        })

        self.assertEqual(payload["mode"], "rules_only")
        self.assertEqual(payload["force"], True)
        self.assertEqual(payload["source_url"], "https://www.youtube.com/watch?v=ExampleVideo01")
        self.assertEqual(payload["allow_youtube_media_fallback"], True)
        self.assertEqual(payload["source_domain"], "youtube.com")
        self.assertNotIn("unsafe_key", payload)

    def test_execute_selective_rerun_returns_blocked_plan_without_executing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "runs" / "run_missing_input"
            rules_dir = root / "rules" / "user"
            run_dir.mkdir(parents=True)
            (run_dir / "run_metadata.json").write_text(
                json.dumps({
                    "schema": "kbprep.run_metadata.v1",
                    "run_id": "run_missing_input",
                    "document_type": "course",
                    "prepare_payload": {"output_root": str(root / "output")},
                }),
                encoding="utf-8",
            )

            with patch("kbprep_worker.feedback.selective_rerun_execution._run_prepare_subprocess") as run_prepare:
                envelope = self._run_feedback({
                    "execute_rerun": True,
                    "run_dir": str(run_dir),
                    "rules_dir": str(rules_dir),
                })
            history_path = rules_dir / "rerun_history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]

        execution = envelope["data"]["rerun_verification"]
        self.assertTrue(envelope["ok"])
        self.assertEqual(execution["status"], "blocked")
        self.assertFalse(execution["ok"])
        self.assertEqual(execution["plan"]["status"], "blocked")
        self.assertIn("input_path", execution["plan"]["missing_evidence"])
        self.assertEqual(history[-1]["status"], "blocked")
        run_prepare.assert_not_called()

    def test_selective_rerun_plan_preserves_failed_promotion_history_as_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_rules_dir = root / "rules"
            history_path = target_rules_dir / "promotion_history.jsonl"
            history_path.parent.mkdir(parents=True)
            history_path.write_text(
                json.dumps({
                    "schema": "kbprep.dictionary_promotion_history.v1",
                    "document_type": "course",
                    "regression_verification": {
                        "status": "failed",
                        "samples": [{
                            "run_dir": str(root / "missing-run"),
                            "reason": "representative metadata unavailable",
                        }],
                    },
                }) + "\n",
                encoding="utf-8",
            )

            envelope = self._run_feedback({
                "plan_rerun": True,
                "document_type": "course",
                "target_rules_dir": str(target_rules_dir),
            })

        plan = envelope["data"]["rerun_plan"]
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["plan_source"], "promotion_history")
        self.assertEqual(plan["promotion_history_status"], "failed")
        self.assertIn("representative metadata unavailable", plan["reason"])

    def test_selective_rerun_plan_requires_explicit_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Note\n\n正文\n", encoding="utf-8")
            run_dir = self._metadata_run_dir(root, source, run_id="run_history")
            target_rules_dir = root / "rules"
            target_rules_dir.mkdir()
            (target_rules_dir / "promotion_history.jsonl").write_text(
                json.dumps({
                    "schema": "kbprep.dictionary_promotion_history.v1",
                    "document_type": "course",
                    "regression_verification": {
                        "status": "passed",
                        "samples": [{"run_dir": str(run_dir), "ok": True}],
                    },
                }) + "\n",
                encoding="utf-8",
            )

            envelope = self._run_feedback({
                "plan_rerun": True,
                "target_rules_dir": str(target_rules_dir),
            })

        plan = envelope["data"]["rerun_plan"]
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["plan_source"], "selector")
        self.assertIn("rerun_selector", plan["missing_evidence"])

    def test_selective_rerun_plan_from_promotion_history_records_rules_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Note\n\n正文\n", encoding="utf-8")
            run_dir = self._metadata_run_dir(root, source, run_id="run_history")
            target_rules_dir = root / "rules"
            target_rules_dir.mkdir()
            (target_rules_dir / "promotion_history.jsonl").write_text(
                json.dumps({
                    "schema": "kbprep.dictionary_promotion_history.v1",
                    "document_type": "course",
                    "regression_verification": {
                        "status": "passed",
                        "samples": [{"run_dir": str(run_dir), "ok": True}],
                    },
                }) + "\n",
                encoding="utf-8",
            )

            envelope = self._run_feedback({
                "plan_rerun": True,
                "document_type": "course",
                "target_rules_dir": str(target_rules_dir),
            })

        plan = envelope["data"]["rerun_plan"]
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["plan_source"], "promotion_history")
        self.assertEqual(plan["command_evidence"]["environment"]["KBPREP_RULES_ROOT"], str(target_rules_dir))

    def test_selective_rerun_plan_blocks_and_records_history_when_metadata_is_insufficient(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "runs" / "run_missing_input"
            rules_dir = root / "rules" / "user"
            run_dir.mkdir(parents=True)
            (run_dir / "run_metadata.json").write_text(
                json.dumps({
                    "schema": "kbprep.run_metadata.v1",
                    "run_id": "run_missing_input",
                    "document_type": "course",
                    "prepare_payload": {
                        "output_root": str(root / "output"),
                        "profile": "standard",
                    },
                }),
                encoding="utf-8",
            )

            envelope = self._run_feedback({
                "plan_rerun": True,
                "run_dir": str(run_dir),
                "rules_dir": str(rules_dir),
            })
            history_path = rules_dir / "rerun_history.jsonl"
            history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]

        plan = envelope["data"]["rerun_plan"]
        self.assertTrue(envelope["ok"])
        self.assertEqual(plan["status"], "blocked")
        self.assertFalse(plan["ok"])
        self.assertIn("input_path", plan["missing_evidence"])
        self.assertEqual(history[-1]["status"], "blocked")
        self.assertEqual(history[-1]["run_id"], "run_missing_input")
        self.assertNotEqual(history[-1]["status"], "passed")

    def _metadata_run_dir(self, root: Path, source: Path, *, run_id: str = "run_001") -> Path:
        run_dir = root / "output" / "runs" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "run_metadata.json").write_text(
            json.dumps({
                "schema": "kbprep.run_metadata.v1",
                "run_id": run_id,
                "source_identity": {
                    "source_name": source.name,
                    "source_path": str(source),
                },
                "document_type": "course",
                "cleaning_policy_snapshot_hash": "hash-policy-123",
                "prepare_payload": {
                    "input_path": str(source),
                    "output_root": str(root / "output"),
                    "profile": "standard",
                    "source_url": "https://www.youtube.com/watch?v=ExampleVideo01",
                    "allow_youtube_media_fallback": True,
                },
            }),
            encoding="utf-8",
        )
        (run_dir / "quality_report.json").write_text(
            json.dumps({"profile": "standard", "document_type": "course"}),
            encoding="utf-8",
        )
        return run_dir

    def _run_feedback(self, payload: dict) -> dict:
        stdout = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = stdout
            try:
                feedback.run(payload)
            except SystemExit:
                pass
        finally:
            sys.stdout = old_stdout
        return json.loads(stdout.getvalue())


def _success_rerun_stdout(root: Path) -> str:
    rerun_run_dir = root / "output" / "runs" / "run_execute_rerun"
    return json.dumps({
        "ok": True,
        "data": {
            "run_id": "run_execute_rerun",
            "run_dir": str(rerun_run_dir),
            "latest_outputs": {
                "cleaned_md": str(rerun_run_dir / "cleaned.md"),
                "quality_report": str(rerun_run_dir / "quality_report.json"),
            },
            "strict_errors": [],
        },
    })


if __name__ == "__main__":
    unittest.main()
