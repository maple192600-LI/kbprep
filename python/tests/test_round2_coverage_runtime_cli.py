import argparse
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker import cli, mineru_adapter, prepare_diagnosis
from kbprep_worker.diagnose import runtime as diagnose_runtime


class PrepareDiagnosisRound2CoverageTests(unittest.TestCase):
    def test_diagnosis_fallback_and_title_extraction_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html_source = root / "page.html"
            html_source.write_text("<h1>ignored</h1>", encoding="utf-8")
            converted = root / "converted.md"
            converted.write_text("# 页面标题\n正文", encoding="utf-8")
            self.assertEqual(prepare_diagnosis.source_title_for_render(html_source, converted), "页面标题")

            pdf_source = root / "book.pdf"
            converted.write_text("The Founder's Playbook示例手册\n\n目录  1\n正文", encoding="utf-8")
            self.assertEqual(prepare_diagnosis.source_title_for_render(pdf_source, converted), "示例手册")
            converted.write_text("AI Operations Manual\n\n普通中文正文段落不是标题\n", encoding="utf-8")
            self.assertEqual(prepare_diagnosis.source_title_for_render(pdf_source, converted), "AI Operations Manual")
            converted.write_text("<!-- page: 1 -->\n12\nResources\n", encoding="utf-8")
            self.assertEqual(prepare_diagnosis.source_title_for_render(pdf_source, converted), "book")

            self.assertEqual(prepare_diagnosis.diagnosis_fallback(root / "x.md")["conversion_strategy"], "direct")
            self.assertEqual(prepare_diagnosis.diagnosis_fallback(root / "x.docx")["conversion_strategy"], "office_xml")
            self.assertEqual(prepare_diagnosis.diagnosis_fallback(root / "x.epub")["conversion_strategy"], "epub_xhtml")
            self.assertEqual(prepare_diagnosis.diagnosis_fallback(root / "x.mp3")["conversion_strategy"], "media_to_transcript")
            extensionless_pdf = root / "extensionless-pdf"
            extensionless_pdf.write_bytes(b"%PDF-1.7\n% fixture")
            self.assertEqual(prepare_diagnosis.diagnosis_fallback(extensionless_pdf)["conversion_strategy"], "mineru_ocr")
            self.assertEqual(
                prepare_diagnosis.diagnosis_fallback(root / "x.unknown")["conversion_strategy"],
                "unsupported_extension",
            )

            run_dir = root / "run"
            run_dir.mkdir()
            prepare_diagnosis.write_diagnosis_report(
                run_dir,
                pdf_source,
                "hash",
                "pdf",
                {"detected_format": "pdf", "needs_ocr": True, "processing_hints": ["ocr"]},
                {"python_version": "3"},
                ["warn"],
            )
            report = json.loads((run_dir / "diagnosis_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["source_sha256"], "hash")
            self.assertTrue(report["needs_ocr"])

            diagnosis = diagnose_runtime._diagnosis_result(
                pdf_source,
                "hash",
                12,
                "pdf",
                "book",
                {"level": "partial"},
                {"recommended_pipeline": "mineru_ocr"},
                [],
            )
            self.assertNotIn("ok", diagnosis)


class MinerUAdapterRound2CoverageTests(unittest.TestCase):
    def test_mineru_environment_preserves_user_network_choices(self):
        with patch("kbprep_worker.mineru_adapter.detect_device", return_value="cuda"), \
            patch.dict(os.environ, {"NO_PROXY": "example.local"}, clear=True):
            env = mineru_adapter._mineru_environment()

        self.assertEqual(env["NO_PROXY"], "example.local,localhost,127.0.0.1")
        self.assertEqual(env["no_proxy"], "example.local,localhost,127.0.0.1")
        self.assertNotIn("MINERU_TOOLS_SOURCE", env)

        with patch("kbprep_worker.mineru_adapter.detect_device", return_value="cuda"), \
            patch.dict(os.environ, {"KBPREP_MINERU_TOOLS_SOURCE": "huggingface"}, clear=True):
            env = mineru_adapter._mineru_environment()

        self.assertEqual(env["MINERU_TOOLS_SOURCE"], "huggingface")

    def test_language_timeout_find_and_successful_output_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_python = root / "python.exe"
            fake_python.write_text("", encoding="utf-8")
            fake_mineru = root / "mineru.exe"
            fake_mineru.write_text("", encoding="utf-8")
            source = root / "sample.pdf"
            source.write_bytes(b"%PDF-")
            out_dir = root / "out"

            def fake_run(cmd, **kwargs):
                assets = out_dir / "mineru_raw" / "sample" / "auto"
                assets.mkdir(parents=True)
                (assets / "sample.md").write_text("OCR 正文", encoding="utf-8")
                (assets / "sample_content_list.json").write_text("[]", encoding="utf-8")
                (assets / "sample_content_list_v2.json").write_text("[]", encoding="utf-8")
                (assets / "sample_middle.json").write_text("{}", encoding="utf-8")
                (assets / "sample_layout.pdf").write_bytes(b"debug")
                return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

            with patch("sys.executable", str(fake_python)), \
                patch("kbprep_worker.mineru_adapter.detect_device", return_value="cpu"), \
                patch("subprocess.run", side_effect=fake_run), \
                patch.dict(os.environ, {"KBPREP_MINERU_TIMEOUT_SECONDS": "45"}, clear=False):
                self.assertEqual(mineru_adapter.find_mineru(), str(fake_mineru))
                result = mineru_adapter.run_mineru(str(source), str(out_dir), language="zh-TW", keep_debug_files=False)

            self.assertEqual(Path(result["source_md_path"]).read_text(encoding="utf-8"), "OCR 正文")
            self.assertEqual(result["mineru_timeout_seconds"], 45)
            self.assertIn("ch", result["mineru_command"])
            self.assertFalse(any(path.name.endswith("_layout.pdf") for path in (out_dir / "mineru_raw").rglob("*.pdf")))
            self.assertEqual(mineru_adapter.normalize_mineru_language(None), "en")
            self.assertEqual(mineru_adapter.normalize_mineru_language("en"), "en")

    def test_mineru_failure_timeout_and_missing_outputs_are_explainable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_mineru = root / "mineru"
            fake_mineru.write_text("", encoding="utf-8")
            source = root / "sample.pdf"
            source.write_bytes(b"%PDF-")

            with patch("kbprep_worker.mineru_adapter.find_mineru", return_value=str(fake_mineru)), \
                patch("kbprep_worker.mineru_adapter.detect_device", return_value="cuda"), \
                patch("subprocess.run", return_value=subprocess.CompletedProcess(["mineru"], 2, stdout="out\nx", stderr="err\nlast")):
                with self.assertRaises(mineru_adapter.MinerUProcessError) as raised:
                    mineru_adapter.run_mineru(str(source), str(root / "fail"))
            self.assertEqual(raised.exception.details["mineru_exit_code"], 2)

            with patch("kbprep_worker.mineru_adapter.find_mineru", return_value=str(fake_mineru)), \
                patch("kbprep_worker.mineru_adapter.detect_device", return_value="cpu"), \
                patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["mineru"], 30)), \
                patch.dict(os.environ, {"KBPREP_MINERU_TIMEOUT_SECONDS": "bad"}, clear=False):
                with self.assertRaises(TimeoutError):
                    mineru_adapter.run_mineru(str(source), str(root / "timeout"))

            with patch("kbprep_worker.mineru_adapter.find_mineru", return_value=str(fake_mineru)), \
                patch("kbprep_worker.mineru_adapter.detect_device", return_value="cpu"), \
                patch("subprocess.run", return_value=subprocess.CompletedProcess(["mineru"], 0, stdout="", stderr="")):
                with self.assertRaises(RuntimeError):
                    mineru_adapter.run_mineru(str(source), str(root / "empty"))

            empty_python_dir = root / "empty-python"
            empty_python_dir.mkdir()
            with patch("sys.executable", str(empty_python_dir / "python.exe")):
                with self.assertRaises(FileNotFoundError):
                    mineru_adapter.find_mineru()


class CliRound2CoverageTests(unittest.TestCase):
    def test_cli_dispatches_commands_and_reports_invalid_json(self):
        commands = {
            "preflight": "cmd_preflight",
            "setup-env": "cmd_setup_env",
            "diagnose": "cmd_diagnose",
            "prepare": "cmd_prepare",
            "apply-review": "cmd_apply_review",
            "feedback": "cmd_feedback",
            "prepare-batch": "cmd_prepare_batch",
            "cleanup": "cmd_cleanup",
        }
        for command, handler_name in commands.items():
            with self.subTest(command=command):
                seen = []
                with (
                    patch.object(cli, handler_name,
                                side_effect=lambda data, seen=seen: seen.append(data)),
                    patch.object(cli, "setup_stderr_logging"),
                    patch.object(cli.argparse.ArgumentParser, "parse_args",
                                return_value=argparse.Namespace(
                                    command=command, json_stdin=True)),
                    patch("sys.stdin", io.StringIO('{"ok": true}')),
                ):
                    cli.main()
                self.assertEqual(seen, [{"ok": True}])

        captured = {}
        with (
            patch.object(cli, "setup_stderr_logging"),
            patch.object(cli.argparse.ArgumentParser, "parse_args",
                        return_value=argparse.Namespace(command="prepare", json_stdin=True)),
            patch("sys.stdin", io.StringIO("{bad")),
            patch("kbprep_worker.cli.fail",
                  side_effect=lambda code, message, **kwargs:
                      captured.update({"code": code, "message": message})),
        ):
            cli.main()
        self.assertEqual(captured["code"], "E_INVALID_INPUT")

    def test_cli_wraps_unhandled_handler_error(self):
        captured = {}
        with (
            patch.object(cli, "setup_stderr_logging"),
            patch.object(cli.argparse.ArgumentParser, "parse_args",
                        return_value=argparse.Namespace(command="prepare", json_stdin=True)),
            patch("sys.stdin", io.StringIO("{}")),
            patch.object(cli, "cmd_prepare", side_effect=RuntimeError("boom")),
            patch("kbprep_worker.cli.fail",
                  side_effect=lambda code, message, **kwargs:
                      captured.update({"code": code, "message": message,
                                       "details": kwargs.get("details")})),
        ):
            cli.main()
        self.assertEqual(captured["code"], "E_INTERNAL")
        self.assertEqual(captured["details"]["exception_type"], "RuntimeError")


if __name__ == "__main__":
    unittest.main()
