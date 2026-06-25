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
            alpha = next(item for item in manifest["items"] if item["relative_path"] == "alpha.md")
            self.assertEqual(len(alpha["source_sha256"]), 64)

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

    def test_batch_rerun_executes_failed_and_pending_manifest_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "beta.md").write_text("# Beta", encoding="utf-8")
            (input_dir / "gamma.md").write_text("# Gamma", encoding="utf-8")

            def fail_first(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                if file_path.name == "alpha.md":
                    return {"ok": False, "error": {"code": "E_TEST_STRICT", "details": {"stage": "quality_check"}}}
                return _successful_child(file_path, output_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=fail_first):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])
            rerun_calls: list[str] = []

            def rerun_child(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                rerun_calls.append(file_path.relative_to(input_dir).as_posix())
                return _successful_child(file_path, output_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=rerun_child):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "rerun": True,
                        "batch_manifest_path": str(manifest_path),
                        "min_free_memory_gb": 0,
                    },
                )

            self.assertEqual(code, 0)
            self.assertEqual(rerun_calls, ["alpha.md", "beta.md", "gamma.md"])
            rerun_manifest = json.loads(Path(envelope["data"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(rerun_manifest["schema"], "kbprep.batch_rerun_manifest.v1")
            self.assertEqual(rerun_manifest["status"], "completed")
            self.assertEqual(rerun_manifest["source_batch_manifest"], str(manifest_path))
            self.assertEqual(rerun_manifest["scope"], "failed_and_pending")
            self.assertEqual(rerun_manifest["summary"]["selected"], 3)
            self.assertEqual(rerun_manifest["summary"]["succeeded"], 3)

    def test_batch_rerun_skips_unrelated_successful_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "beta.md").write_text("# Beta", encoding="utf-8")
            (input_dir / "gamma.md").write_text("# Gamma", encoding="utf-8")

            def mixed_result(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                if file_path.name == "beta.md":
                    return {"ok": False, "error": {"code": "E_TEST_STRICT", "details": {"stage": "quality_check"}}}
                return _successful_child(file_path, output_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=mixed_result):
                code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["data"]["batch_manifest_json"])
            rerun_calls: list[str] = []

            def rerun_child(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                rerun_calls.append(file_path.relative_to(input_dir).as_posix())
                return _successful_child(file_path, output_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=rerun_child):
                rerun_code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
                )

            rerun_manifest = json.loads(Path(envelope["data"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertEqual(rerun_code, 0)
            self.assertEqual(rerun_calls, ["beta.md"])
            self.assertEqual(rerun_manifest["selected"], ["beta.md"])
            self.assertEqual(rerun_manifest["scope"], "failed_only")

    def test_batch_manifest_records_rerun_command_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", side_effect=_successful_child):
                _code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "profile": "obsidian_kb",
                        "mode": "rules_plus_review_pack",
                        "language": "en",
                        "force": True,
                        "artifact_policy": "keep_all",
                        "max_quality_iterations": 7,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )

            manifest = json.loads(Path(envelope["data"]["batch_manifest_json"]).read_text(encoding="utf-8"))
            defaults = manifest["rerun"]["command_defaults"]
            self.assertEqual(defaults["profile"], "obsidian_kb")
            self.assertEqual(defaults["mode"], "rules_plus_review_pack")
            self.assertEqual(defaults["language"], "en")
            self.assertEqual(defaults["artifact_policy"], "keep_all")
            self.assertEqual(defaults["max_quality_iterations"], 7)

    def test_batch_rerun_reports_missing_sources_without_success_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            missing = input_dir / "missing.md"
            missing.write_text("# Missing", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])
            missing.unlink()

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
            )

            rerun_manifest = json.loads(Path(envelope["error"]["details"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(code, 1)
            self.assertEqual(envelope["status"], "failed")
            self.assertEqual(rerun_manifest["status"], "failed")
            self.assertEqual(rerun_manifest["failures"][0]["error"]["code"], "E_INPUT_NOT_FOUND")

    def test_batch_rerun_rejects_changed_source_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            source = input_dir / "alpha.md"
            source.write_text("# Alpha", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])
            source.write_text("# Alpha changed", encoding="utf-8")

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
            )

            rerun_manifest = json.loads(Path(envelope["error"]["details"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(code, 1)
            self.assertEqual(envelope["status"], "failed")
            self.assertEqual(rerun_manifest["failures"][0]["error"]["code"], "E_SOURCE_CHANGED")

    def test_batch_rerun_rejects_unsafe_manifest_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            source = input_dir / "alpha.md"
            source.write_text("# Alpha", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["output_root"] = str(Path.home())
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
            )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_INVALID_OUTPUT_ROOT")

    def test_batch_rerun_rejects_manifest_paths_outside_cli_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boundary = root / "boundary"
            outside = root / "outside"
            input_dir = boundary / "sources"
            output_root = outside / "batch"
            boundary.mkdir()
            outside.mkdir()
            input_dir.mkdir()
            source = input_dir / "alpha.md"
            source.write_text("# Alpha", encoding="utf-8")
            manifest_path = boundary / "batch_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema": "kbprep.batch_manifest.v1",
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "items": [
                            {
                                "relative_path": "alpha.md",
                                "status": "failed",
                                "rerunnable": True,
                                "source_sha256": "not-used",
                            },
                        ],
                        "rerun": {"recommended_scope": "failed_only", "failed_only": ["alpha.md"]},
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"KBPREP_CLI_BOUNDARY_DIR": str(boundary)}):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
                )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_INVALID_OUTPUT_ROOT")

    def test_batch_rerun_preserves_skipped_unsupported_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "archive.bin").write_text("skip", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])

            with patch.object(prepare_batch, "_process_one_file", side_effect=_successful_child):
                _code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
                )

            rerun_manifest = json.loads(Path(envelope["data"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(rerun_manifest["skipped_unsupported"], ["archive.bin"])

    def test_batch_rerun_with_no_selected_items_fails_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", side_effect=_successful_child):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["data"]["batch_manifest_json"])

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
            )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_BATCH_RERUN_EMPTY")

    def test_batch_rerun_rejects_policy_affected_scope_until_binding_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {"rerun": True, "batch_manifest_path": str(manifest_path), "rerun_scope": "affected", "min_free_memory_gb": 0},
            )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_INVALID_INPUT")

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
