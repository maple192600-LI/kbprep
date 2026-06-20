import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

from kbprep_worker import prepare_batch
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


def _successful_child(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
    out = Path(output_root)
    out.mkdir(parents=True, exist_ok=True)
    final = out / f"{file_path.stem}.cleaned.md"
    final.write_text(f"# {file_path.stem}", encoding="utf-8")
    return {
        "ok": True,
        "data": {
            "run_id": file_path.stem,
            "strict_errors": [],
            "latest_outputs": {
                "final_artifact_type": "markdown",
                "final_md": str(final),
            },
        },
    }


class BatchStatusManifestTests(unittest.TestCase):
    def test_all_successful_children_write_completed_parent_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "beta.txt").write_text("Beta", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", side_effect=_successful_child):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )

            self.assertEqual(code, 0)
            manifest_path = Path(envelope["data"]["batch_manifest_json"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["summary"]["succeeded"], 2)
            self.assertEqual(manifest["summary"]["failed"], 0)
            self.assertEqual(manifest["summary"]["skipped_unsupported"], 0)
            self.assertEqual(manifest["rerun"]["recommended_scope"], "none")

    def test_batch_writes_status_manifest_with_skips_and_empty_rerun_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "beta.txt").write_text("Beta", encoding="utf-8")
            (input_dir / "archive.bin").write_text("skip", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", side_effect=_successful_child):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )

            self.assertEqual(code, 0)
            manifest_path = Path(envelope["data"]["batch_manifest_json"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["schema"], "kbprep.batch_manifest.v1")
            self.assertEqual(manifest["status"], "completed_with_warnings")
            self.assertEqual(manifest["summary"]["succeeded"], 2)
            self.assertEqual(manifest["summary"]["skipped_unsupported"], 1)
            self.assertEqual(manifest["rerun"]["failed_only"], [])
            self.assertEqual(manifest["rerun"]["recommended_scope"], "none")
            statuses = {item["relative_path"]: item["status"] for item in manifest["items"]}
            self.assertEqual(statuses["alpha.md"], "succeeded")
            self.assertEqual(statuses["beta.txt"], "succeeded")
            self.assertEqual(statuses["archive.bin"], "skipped_unsupported")

    def test_failed_sample_writes_manifest_with_failed_and_pending_rerun_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "beta.md").write_text("# Beta", encoding="utf-8")

            def fail_first(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                if file_path.name == "alpha.md":
                    return {
                        "ok": False,
                        "error": {
                            "code": "E_TEST_STRICT",
                            "message": "forced sample failure",
                            "details": {"stage": "quality_check"},
                        },
                    }
                return _successful_child(file_path, output_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=fail_first):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )

            manifest_path = Path(envelope["error"]["details"]["batch_manifest_json"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(code, 1)
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["summary"]["processed"], 1)
            self.assertEqual(manifest["summary"]["failed"], 1)
            self.assertEqual(manifest["summary"]["pending"], 1)
            self.assertEqual(manifest["rerun"]["recommended_scope"], "failed_and_pending")
            self.assertEqual(manifest["rerun"]["failed_only"], ["alpha.md"])
            self.assertEqual(manifest["rerun"]["pending"], ["beta.md"])
            items = {item["relative_path"]: item for item in manifest["items"]}
            self.assertEqual(items["alpha.md"]["failure_stage"], "quality_check")
            self.assertEqual(items["beta.md"]["status"], "pending")

    def test_single_file_prepare_does_not_create_batch_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "guide.txt"
            output_root = root / "out"
            source.write_text("# Guide\n\nKeep SINGLE_PREP_MARKER.", encoding="utf-8")

            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(output_root), "force": True, "profile": "standard"},
            )

            self.assertEqual(code, 0)
            self.assertNotIn("batch_manifest_json", envelope["data"])
            self.assertFalse((output_root / "batch_manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
