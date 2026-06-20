import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.stages import pipeline_core


def _capture_envelope(fn: Callable[[dict[str, Any]], None], payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fn(payload)
    except EnvelopeExit as exc:
        return exc.code, json.loads(out.getvalue())
    raise AssertionError("worker command did not write a JSON envelope")


class PublishSafetyTests(unittest.TestCase):
    def test_successful_prepare_writes_owner_readable_publish_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "guide.txt"
            output_root = root / "out"
            source.write_text("# Guide\n\nKeep PUBLISH_REPORT_MARKER and threshold=0.8.\n", encoding="utf-8")

            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(output_root), "force": True, "profile": "standard"},
            )

            self.assertEqual(code, 0)
            publish_report = Path(envelope["data"]["latest_outputs"]["publish_report"])
            report = json.loads(publish_report.read_text(encoding="utf-8"))

            self.assertTrue(publish_report.exists())
            self.assertEqual(report["schema"], "kbprep.publish_report.v1")
            self.assertEqual(report["status"], "published")
            self.assertTrue(report["published"])
            self.assertEqual(report["final_artifact"]["final_md"], str(root / "guide.md"))
            self.assertIn("quality_report", report["process_evidence"])
            self.assertIn("cleanup_command", report["cleanup_guidance"])

    def test_obsidian_publish_report_points_to_published_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "guide.md"
            output_root = root / "out"
            source.write_text("# Guide\n\n步骤1：保留 OBSIDIAN_REPORT_MARKER 并记录 threshold=0.8。\n", encoding="utf-8")

            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(output_root), "force": True, "profile": "obsidian_kb"},
            )

            self.assertEqual(code, 0)
            latest_outputs = envelope["data"]["latest_outputs"]
            publish_report = Path(latest_outputs["publish_report"])
            report = json.loads(publish_report.read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "published")
            self.assertTrue(report["published"])
            self.assertEqual(report["final_artifact"]["final_artifact_type"], "obsidian_dir")
            self.assertEqual(report["final_artifact"]["obsidian_dir"], latest_outputs["obsidian_dir"])
            self.assertEqual(report["final_artifact"]["obsidian_index"], latest_outputs["obsidian_index"])
            self.assertEqual(report["final_artifact"]["obsidian_complete"], latest_outputs["obsidian_complete"])
            self.assertTrue(Path(report["final_artifact"]["obsidian_index"]).exists())
            self.assertTrue(Path(report["final_artifact"]["obsidian_complete"]).exists())

    def test_quality_failure_blocks_source_side_publish_and_writes_blocked_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "guide.txt"
            output_root = root / "out"
            source.write_text("# Guide\n\nKeep BLOCKED_PUBLISH_MARKER and threshold=0.8.\n", encoding="utf-8")

            def fake_quality(**_kwargs: Any) -> dict[str, Any]:
                return {
                    "strict_errors": ["E_TEST_STRICT: forced publish block"],
                    "warnings": [],
                    "quality_issues": [{"code": "E_TEST_STRICT", "message": "forced publish block"}],
                    "quality_gates": [{"name": "export_readiness", "status": "fail"}],
                    "next_actions": [],
                    "quality_tasks": {},
                }

            with patch("kbprep_worker.quality.run_quality_check", side_effect=fake_quality):
                code, envelope = _capture_envelope(
                    pipeline_core.run,
                    {"input_path": str(source), "output_root": str(output_root), "force": True, "profile": "standard"},
                )

            run_dir = Path(envelope["error"]["details"]["run_dir"])
            publish_report = run_dir / "publish_report.json"
            report = json.loads(publish_report.read_text(encoding="utf-8"))

            self.assertEqual(code, 1)
            self.assertFalse((root / "guide.md").exists())
            self.assertFalse((output_root / "latest.json").exists())
            self.assertTrue(publish_report.exists())
            self.assertEqual(report["status"], "blocked")
            self.assertFalse(report["published"])
            self.assertIsNone(report["final_artifact"])
            self.assertFalse(report["cleanup_guidance"]["can_finalize"])
            self.assertIsNone(report["cleanup_guidance"]["cleanup_command"])
            self.assertEqual(report["blocked_reason"]["strict_errors"], ["E_TEST_STRICT: forced publish block"])


if __name__ == "__main__":
    unittest.main()
