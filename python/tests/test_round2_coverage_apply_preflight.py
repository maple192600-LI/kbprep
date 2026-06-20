import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker import apply_patch as apply_patch_mod
from kbprep_worker import preflight as preflight_mod
from kbprep_worker.envelope import EnvelopeExit


def _capture_envelope(fn, *args, **kwargs):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        with unittest.TestCase().assertRaises(EnvelopeExit) as raised:
            fn(*args, **kwargs)
    return raised.exception.code, json.loads(stdout.getvalue())


class ApplyPatchCoverageTests(unittest.TestCase):
    def _write_run(self, root: Path) -> Path:
        run_dir = root / "runs" / "run1"
        run_dir.mkdir(parents=True)
        blocks = [
            {
                "block_id": "b1",
                "source_sha256": "abc",
                "type": "paragraph",
                "status": "keep",
                "text": "普通正文",
                "risk_tags": [],
                "protected": False,
            },
            {
                "block_id": "step1",
                "source_sha256": "abc",
                "type": "operation_step",
                "status": "keep",
                "text": "步骤1：打开后台。",
                "risk_tags": [],
                "protected": True,
            },
        ]
        (run_dir / "blocks.jsonl").write_text(
            "\n".join(json.dumps(block, ensure_ascii=False) for block in blocks) + "\n",
            encoding="utf-8",
        )
        (run_dir / "quality_report.json").write_text(
            json.dumps({
                "source_type": "markdown_note",
                "quality_loop": {"current_iteration": 1, "max_iterations": 3},
                "source_sha256": "abc",
            }),
            encoding="utf-8",
        )
        (run_dir / "diagnosis_report.json").write_text(json.dumps({"split_strategy": "by_heading"}), encoding="utf-8")
        (root / "latest.json").write_text(json.dumps({"input_path": str(root / "source.md")}), encoding="utf-8")
        return run_dir

    def test_apply_review_patch_records_rejections_and_republishes_when_quality_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self._write_run(root)
            patches = [
                {"op": "replace", "path": "/blocks/b1/status", "value": "review"},
                {"op": "add", "path": "/blocks/b1/risk_tags", "value": "needs_human"},
                {"op": "replace", "path": "/blocks/step1/status", "value": "discard"},
                {"op": "replace", "path": "/blocks/missing/status", "value": "keep"},
                {"op": "remove", "path": "/blocks/b1/status", "value": "keep"},
            ]
            with (
                patch("kbprep_worker.render_outputs.render") as render,
                patch("kbprep_worker.split.split_into_chunks", return_value={"chunk_count": 1}) as split,
                patch("kbprep_worker.quality.run_quality_check", return_value={"strict_errors": [], "warnings": []}) as quality,
                patch("kbprep_worker.apply_patch._publish_latest_outputs", return_value={"cleaned_md": "out.md"}) as publish,
                patch("kbprep_worker.apply_patch._update_latest_json") as update_latest,
            ):
                code, envelope = _capture_envelope(
                    apply_patch_mod.run,
                    {"run_dir": str(run_dir), "patch_json": patches},
                )

            self.assertEqual(code, 0)
            self.assertTrue(envelope["ok"])
            self.assertEqual(envelope["data"]["applied"], 2)
            self.assertEqual(envelope["data"]["rejected"], 3)
            self.assertTrue(envelope["data"]["published"])
            self.assertIn("cannot discard", json.dumps(envelope["data"]["rejected_details"], ensure_ascii=False))
            render.assert_called_once()
            split.assert_called_once()
            quality.assert_called_once()
            publish.assert_called_once()
            update_latest.assert_called_once()

    def test_apply_review_patch_blocks_missing_blocks_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, envelope = _capture_envelope(
                apply_patch_mod.run,
                {"run_dir": tmp, "patch_json": []},
            )
        self.assertEqual(code, 1)
        self.assertEqual(envelope["error"]["code"], "E_INPUT_NOT_FOUND")

    def test_apply_patch_helpers_publish_and_rewrite_source_side_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("source", encoding="utf-8")
            run_dir = root / "runs" / "run2"
            (run_dir / "images").mkdir(parents=True)
            (run_dir / "parts").mkdir()
            (run_dir / "cleaned.md").write_text("![x](images/a.png)\n", encoding="utf-8")
            (run_dir / "images" / "a.png").write_bytes(b"png")
            for name in ["converted.md", "diagnosis_report.json", "blocks.jsonl", "discarded.md", "review_needed.md", "quality_report.json"]:  # noqa: E501
                (run_dir / name).write_text("{}", encoding="utf-8")
            (root / "latest.json").write_text(json.dumps({"input_path": str(source)}), encoding="utf-8")

            outputs = apply_patch_mod._publish_latest_outputs(run_dir, root, profile="standard")

            self.assertTrue(Path(outputs["final_md"]).exists())
            self.assertTrue(Path(outputs["final_assets_dir"], "a.png").exists())
            self.assertIn("source.assets/a.png", Path(outputs["final_md"]).read_text(encoding="utf-8"))
            self.assertEqual(apply_patch_mod._positive_int("bad", 2), 2)
            self.assertEqual(apply_patch_mod._positive_int(True, 2), 2)
            self.assertEqual(apply_patch_mod._source_title_from_previous_quality({"input_file": str(source)}, run_dir), "source")


class PreflightCoverageTests(unittest.TestCase):
    def test_preflight_success_reports_runtime_versions_and_warnings(self):
        fake_fitz = types.SimpleNamespace(__version__="1.27.0")
        fake_props = types.SimpleNamespace(total_memory=8 * 1024**3)
        fake_torch = types.SimpleNamespace(
            __version__="2.8.0",
            version=types.SimpleNamespace(cuda="12.4"),
            cuda=types.SimpleNamespace(
                is_available=lambda: True,
                device_count=lambda: 1,
                get_device_properties=lambda index: fake_props,
                get_device_name=lambda index: "Test GPU",
            ),
        )
        fake_psutil = types.SimpleNamespace(
            virtual_memory=lambda: types.SimpleNamespace(total=32 * 1024**3, available=16 * 1024**3)
        )
        completed = types.SimpleNamespace(returncode=0, stdout="mineru 3.2.1")
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.dict(sys.modules, {"fitz": fake_fitz, "torch": fake_torch, "psutil": fake_psutil}),
                patch("kbprep_worker.preflight.find_mineru", return_value="mineru"),
                patch("kbprep_worker.preflight.subprocess.run", return_value=completed),
                patch("kbprep_worker.preflight.detect_device", return_value="cuda"),
            ):
                code, envelope = _capture_envelope(preflight_mod.run, {"workspace_path": tmp, "profile": "lite"})

        self.assertEqual(code, 0)
        self.assertNotIn("ok", envelope["data"])
        versions = envelope["data"]["versions"]
        self.assertEqual(versions["pymupdf"], "1.27.0")
        self.assertEqual(versions["mineru"], "mineru 3.2.1")
        self.assertEqual(versions["gpu_name"], "Test GPU")

    def test_preflight_failure_reports_missing_mineru_and_low_disk(self):
        fake_torch = types.SimpleNamespace(
            __version__="2.8.0",
            version=types.SimpleNamespace(cuda=None),
            cuda=types.SimpleNamespace(is_available=lambda: False, device_count=lambda: 0),
        )
        usage = types.SimpleNamespace(total=10 * 1024**3, used=9 * 1024**3, free=1 * 1024**3)
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.dict(sys.modules, {"torch": fake_torch}),
                patch("kbprep_worker.preflight.find_mineru", side_effect=FileNotFoundError("missing")),
                patch("kbprep_worker.preflight.detect_device", return_value="cpu"),
                patch("kbprep_worker.preflight.shutil.which", return_value="nvidia-smi"),
                patch("kbprep_worker.preflight.shutil.disk_usage", return_value=usage),
            ):
                code, envelope = _capture_envelope(preflight_mod.run, {"workspace_path": tmp, "profile": "standard"})

        self.assertEqual(code, 1)
        self.assertEqual(envelope["error"]["code"], "KBPREP_WORKER_NOT_READY")
        self.assertIn("MinerU not found", envelope["error"]["message"])
        self.assertIn("Disk space low", envelope["error"]["message"])


if __name__ == "__main__":
    unittest.main()
