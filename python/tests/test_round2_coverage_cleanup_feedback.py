import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker import cleanup as cleanup_mod
from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.feedback import command as feedback_command
from kbprep_worker.feedback import proposals as feedback_proposals
from kbprep_worker.feedback import support as feedback_support


def _capture_envelope(fn, *args, **kwargs):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        with unittest.TestCase().assertRaises(EnvelopeExit) as raised:
            fn(*args, **kwargs)
    return raised.exception.code, json.loads(stdout.getvalue())


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class CleanupLifecycleCoverageTests(unittest.TestCase):
    def test_finalize_single_writes_manifest_and_deletes_temporary_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            final_md = root / "source.cleaned.md"
            final_md.write_text("# Final\n", encoding="utf-8")
            (root / "latest.json").write_text(json.dumps({
                "input_path": str(root / "source.md"),
                "source_sha256": "abc",
                "source_type": "markdown_note",
                "run_id": "run1",
                "latest_outputs": {
                    "final_artifact_type": "markdown",
                    "final_md": str(final_md),
                    "final_assets_dir": None,
                },
            }), encoding="utf-8")
            for name in ["converted.md", "cleaned.md", "quality_report.json", "review_needed.md"]:
                (root / name).write_text("" if name == "review_needed.md" else "tmp", encoding="utf-8")
            (root / "runs").mkdir()
            (root / "runs" / "old").mkdir()

            code, envelope = _capture_envelope(cleanup_mod.run, {"output_root": str(root), "action": "finalize"})

            self.assertEqual(code, 0)
            self.assertTrue(envelope["ok"])
            self.assertTrue((root / "kbprep_manifest.json").exists())
            self.assertFalse((root / "converted.md").exists())
            self.assertTrue(final_md.exists())

    def test_finalize_blocks_when_review_needed_has_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            final_md = root / "final.md"
            final_md.write_text("accepted", encoding="utf-8")
            (root / "latest.json").write_text(json.dumps({
                "latest_outputs": {"final_artifact_type": "markdown", "final_md": str(final_md)}
            }), encoding="utf-8")
            (root / "review_needed.md").write_text("needs review", encoding="utf-8")

            code, envelope = _capture_envelope(cleanup_mod.run, {"output_root": str(root), "action": "finalize"})

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "KBPREP_REVIEW_NEEDED")

    def test_finalize_batch_and_cleanup_expired_and_all_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file_root = root / "files" / "a"
            file_root.mkdir(parents=True)
            final_md = file_root / "a.md"
            final_md.write_text("final", encoding="utf-8")
            (file_root / "review_needed.md").write_text("", encoding="utf-8")
            (root / "results.json").write_text(json.dumps([
                {
                    "ok": True,
                    "output_root": str(file_root),
                    "relative_path": "a.md",
                    "run_id": "run-a",
                    "batch_final_md": str(final_md),
                },
                {"ok": False, "file": "failed.md"},
            ]), encoding="utf-8")
            (root / "runs").mkdir()
            expired = root / "runs" / "expired"
            expired.mkdir()
            (root / "converted.md").write_text("tmp", encoding="utf-8")

            code, batch = _capture_envelope(cleanup_mod.run, {"output_root": str(root), "action": "finalize"})
            self.assertEqual(code, 0)
            self.assertEqual(batch["data"]["total_finalized"] if "total_finalized" in batch["data"] else len(batch["data"]["finalized"]), 1)

            code, expired_envelope = _capture_envelope(
                cleanup_mod.run,
                {"output_root": str(root), "action": "expired", "older_than_days": 0, "dry_run": True},
            )
            self.assertEqual(code, 0)
            self.assertEqual(expired_envelope["data"]["action"], "expired")

            (root / "converted.md").write_text("tmp", encoding="utf-8")
            code, all_envelope = _capture_envelope(cleanup_mod.run, {"output_root": str(root), "action": "all", "dry_run": True})
            self.assertEqual(code, 0)
            self.assertIn(str(root / "converted.md"), all_envelope["data"]["deleted"])

    def test_cleanup_rejects_invalid_action_and_missing_output_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code, invalid = _capture_envelope(cleanup_mod.run, {"output_root": str(root), "action": "bad"})
            self.assertEqual(code, 1)
            self.assertEqual(invalid["error"]["code"], "E_INVALID_INPUT")

            code, missing = _capture_envelope(cleanup_mod.run, {"output_root": str(root / "missing"), "action": "all"})
            self.assertEqual(code, 1)
            self.assertEqual(missing["error"]["code"], "E_INVALID_INPUT")


class FeedbackCoverageTests(unittest.TestCase):
    def _write_run_artifacts(self, root: Path) -> tuple[Path, Path]:
        run_dir = root / "runs" / "run1"
        run_dir.mkdir(parents=True)
        source = root / "exports" / "course-a.md"
        source.parent.mkdir()
        source.write_text("source", encoding="utf-8")
        (run_dir / "quality_report.json").write_text(json.dumps({
            "source_type": "markdown_note",
            "profile": "standard",
            "document_type": "tutorial",
            "quality_gates": [{"name": "cleanup_safety", "status": "fail"}],
            "strict_errors": ["E_CTA_RESIDUE: cleanup residue"],
        }), encoding="utf-8")
        (run_dir / "run_metadata.json").write_text(json.dumps({
            "prepare_payload": {"input_path": str(source), "profile": "standard"},
            "source_identity": {
                "source_name": "course-a.md",
                "source_url": "https://example.com/course-a",
                "source_domain": "example.com",
            },
        }), encoding="utf-8")
        (run_dir / "discarded.md").write_text("扫码入群领取资料\n", encoding="utf-8")
        (run_dir / "cleaned.md").write_text("正文案例：扫码入群不是这里要删的正文参数。\n", encoding="utf-8")
        (run_dir / "review_needed.md").write_text("扫码入群领取资料\n", encoding="utf-8")
        return run_dir, source

    def test_feedback_run_creates_source_pattern_proposal_and_accepts_then_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir, _ = self._write_run_artifacts(root)
            rules_dir = root / "rules"

            code, proposal_env = _capture_envelope(feedback_command.run, {
                "run_dir": str(run_dir),
                "rules_dir": str(rules_dir),
                "feedback_text": "以后删除「扫码入群领取资料」",
                "scope": "source_pattern",
                "action": "discard",
                "pattern": "扫码入群领取资料",
            })
            self.assertEqual(code, 0)
            proposal = proposal_env["data"]["proposal"]
            self.assertEqual(proposal["scope"], "source_pattern")
            self.assertEqual(proposal["source_pattern"], "source_domain:example.com")

            with patch("kbprep_worker.feedback.proposals._rerun_after_accept", return_value={"status": "skipped"}):
                code, accepted = _capture_envelope(feedback_command.run, {
                    "rules_dir": str(rules_dir),
                    "accept_proposal": "latest",
                    "confirm_rule_acceptance": True,
                })
            self.assertEqual(code, 0)
            self.assertEqual(accepted["data"]["accepted"]["status"], "accepted")
            self.assertEqual(_jsonl(rules_dir / "accepted_rules.jsonl")[0]["status"], "accepted")

            code, reject_existing = _capture_envelope(feedback_command.run, {
                "rules_dir": str(rules_dir),
                "reject_proposal": "latest",
            })
            self.assertEqual(code, 1)
            self.assertEqual(reject_existing["error"]["code"], "E_INVALID_INPUT")

    def test_feedback_helpers_validate_examples_and_suggest_narrowing(self):
        artifacts = {
            "texts": {
                "discarded": "扫码入群领取资料\n",
                "review_needed": "扫码入群领取资料\n",
                "cleaned": "正文案例：扫码入群是案例字段\n",
            }
        }
        examples = feedback_proposals._examples({}, "删掉", "扫码入群", "literal", "discard", artifacts)
        counterexamples = feedback_proposals._counterexamples({}, "扫码入群", "literal", "discard", artifacts)
        validation = feedback_proposals._validate_proposal_acceptance({
            "pattern": "扫码入群",
            "match": "literal",
            "examples": examples,
            "counterexamples": counterexamples,
        })
        with tempfile.TemporaryDirectory() as tmp:
            narrowed = feedback_proposals._suggest_narrowed_proposal({
                "schema": "kbprep.rule_proposal.v1",
                "id": "proposal-old",
                "status": "proposed",
                "action": "discard",
                "scope": "user",
                "match": "literal",
                "pattern": "扫码入群",
                "examples": ["扫码入群领取资料"],
                "counterexamples": ["正文案例：扫码入群是案例字段"],
                "reason": "test",
                "risk_note": "Fixture proposal may delete body text if accepted broadly.",
                "owner_confirmation_status": "pending",
                "requires_confirmation": True,
                "created_from_run": tmp,
            }, validation)

        self.assertFalse(validation["ok"])
        self.assertIsNotNone(narrowed)
        self.assertEqual(narrowed["pattern"], "扫码入群领取资料")

    def test_feedback_support_source_identity_and_invalid_inputs(self):
        context = {"source_identity": {"source_metadata": {"source_url": "https://www.example.org/a"}}}
        self.assertEqual(feedback_support._source_domain_from_context(context), "example.org")
        self.assertEqual(feedback_support._positive_int("bad", 3), 3)
        self.assertEqual(feedback_support._pattern({"examples": ["  保留这句  "]}, ""), "保留这句")
        self.assertTrue(feedback_support._matches_pattern("ABC", "abc", "literal"))
        self.assertFalse(feedback_support._matches_pattern("ABC", "[", "regex"))


if __name__ == "__main__":
    unittest.main()
