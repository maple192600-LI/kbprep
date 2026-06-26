import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.converters.asr import (
    transcribe_media,
    transcribe_media_with_qwen3_asr,
    transcribe_media_with_whisper,
)
from kbprep_worker.converters.external_tools import (
    IMAGE_SOURCE_EXTENSIONS,
    LEGACY_OFFICE_SOURCE_EXTENSIONS,
    MEDIA_SOURCE_EXTENSIONS,
    ExternalCommandResult,
    ExternalConversionResult,
    convert_legacy_office_to_pdf,
    wrap_image_as_pdf,
)


class ExternalToolConversionTests(unittest.TestCase):
    def test_image_wrapper_creates_pdf_report_for_mineru_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "scan.png"
            source.write_bytes(b"png")

            def render(source_path: Path, target_path: Path) -> None:
                self.assertEqual(source_path, source)
                target_path.write_bytes(b"%PDF-1.7 wrapped image")

            result = wrap_image_as_pdf(source, root / "run", renderer=render)

        self.assertTrue(result.ok)
        self.assertEqual(result.report["route_decision"]["external_route"], "image_to_pdf")
        self.assertEqual(result.report["route_decision"]["next_route"], "mineru_ocr")
        self.assertTrue(str(result.artifact_path).endswith("scan.external.pdf"))
        self.assertIsNone(result.report["failure_reason"])
        self.assertNotIn(str(root), " ".join(result.report["sanitized_commands"][0]))

    def test_missing_libreoffice_returns_assertable_failure_without_running_command(self):
        calls: list[tuple[str, ...]] = []

        def runner(command: tuple[str, ...], cwd: Path | None, timeout_seconds: int) -> ExternalCommandResult:
            calls.append(command)
            return ExternalCommandResult(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, "legacy.doc")
            source.write_bytes(b"doc")

            result = convert_legacy_office_to_pdf(source, Path(tmp, "run"), which=lambda _name: None, runner=runner)

        self.assertFalse(result.ok)
        self.assertEqual(calls, [])
        self.assertIsNone(result.artifact_path)
        self.assertEqual(result.report["failure_reason"]["code"], "E_ENV_MISSING")
        self.assertEqual(result.report["failure_reason"]["dependency"], "libreoffice")

    def test_libreoffice_success_reports_pdf_artifact_and_sanitized_command(self):
        seen_commands: list[tuple[str, ...]] = []

        def runner(command: tuple[str, ...], cwd: Path | None, timeout_seconds: int) -> ExternalCommandResult:
            seen_commands.append(command)
            out_dir = Path(command[command.index("--outdir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            Path(out_dir, "deck.pdf").write_bytes(b"%PDF-1.7")
            return ExternalCommandResult(returncode=0, stdout="convert ok", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "deck.ppt"
            source.write_bytes(b"ppt")
            result = convert_legacy_office_to_pdf(
                source,
                root / "run",
                which=lambda name: f"C:/Tools/LibreOffice/program/{name}.exe" if name == "soffice" else None,
                runner=runner,
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.report["route_decision"]["external_route"], "legacy_office_to_pdf")
        self.assertEqual(result.report["route_decision"]["next_route"], "pdf_route")
        self.assertTrue(Path(result.report["artifact_path"]).name.endswith(".pdf"))
        self.assertIn("soffice.exe", result.report["sanitized_commands"][0][0])
        self.assertNotIn(str(root), " ".join(result.report["sanitized_commands"][0]))
        self.assertEqual(len(seen_commands), 1)

    def test_media_transcription_uses_env_model_and_reports_transcript(self):
        seen_commands: list[tuple[str, ...]] = []

        def runner(command: tuple[str, ...], cwd: Path | None, timeout_seconds: int) -> ExternalCommandResult:
            seen_commands.append(command)
            if "ffmpeg" in Path(command[0]).name:
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_bytes(b"wav")
            else:
                out_dir = Path(command[command.index("--output_dir") + 1])
                out_dir.mkdir(parents=True, exist_ok=True)
                Path(out_dir, "lesson.txt").write_text("hello transcript", encoding="utf-8")
            return ExternalCommandResult(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.mp4"
            source.write_bytes(b"mp4")
            result = transcribe_media_with_whisper(
                source,
                root / "run",
                env={"KBPREP_WHISPER_MODEL": "small"},
                which=lambda name: f"C:/Tools/{name}.exe",
                runner=runner,
            )
            transcript_text = Path(result.report["artifact_path"]).read_text(encoding="utf-8")

        self.assertTrue(result.ok)
        self.assertEqual(result.report["route_decision"]["external_route"], "media_to_transcript")
        self.assertEqual(result.report["route_decision"]["next_route"], "direct_text")
        self.assertEqual(result.report["whisper_model"], "small")
        self.assertEqual(transcript_text, "hello transcript")
        self.assertEqual(len(seen_commands), 2)
        self.assertNotIn(str(root), " ".join(" ".join(command) for command in result.report["sanitized_commands"]))

    def test_transcribe_media_routes_chinese_to_qwen3_asr(self):
        with patch("kbprep_worker.converters.asr.transcribe_media_with_qwen3_asr") as qwen, patch(
            "kbprep_worker.converters.asr.transcribe_media_with_whisper"
        ) as whisper:
            qwen.return_value = ExternalConversionResult(
                ok=True, artifact_path=None, report={"asr_provider": "qwen3_asr"}
            )
            transcribe_media(Path("note.mp4"), Path("run"), env={"KBPREP_ASR_LANGUAGE": "zh"})
            qwen.assert_called_once()
            whisper.assert_not_called()

    def test_transcribe_media_routes_english_to_whisper(self):
        with patch("kbprep_worker.converters.asr.transcribe_media_with_qwen3_asr") as qwen, patch(
            "kbprep_worker.converters.asr.transcribe_media_with_whisper"
        ) as whisper:
            whisper.return_value = ExternalConversionResult(
                ok=True, artifact_path=None, report={"whisper_model": "large-v3"}
            )
            transcribe_media(Path("note.mp4"), Path("run"), env={"KBPREP_ASR_LANGUAGE": "en"})
            whisper.assert_called_once()
            qwen.assert_not_called()

    def test_qwen3_asr_transcribes_chinese_audio_with_mock_inference(self):
        def runner(command: tuple[str, ...], cwd: Path | None, timeout_seconds: int) -> ExternalCommandResult:
            Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(command[-1]).write_bytes(b"wav")
            return ExternalCommandResult(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.mp4"
            source.write_bytes(b"mp4")
            with patch("kbprep_worker.converters.asr.find_spec", return_value=object()), patch(
                "kbprep_worker.converters.asr._run_qwen3_asr_inference",
                return_value="中文转写内容 Qwen3-ASR",
            ):
                result = transcribe_media_with_qwen3_asr(
                    source,
                    root / "run",
                    env={"KBPREP_ASR_LANGUAGE": "zh"},
                    which=lambda name: f"C:/Tools/{name}.exe",
                    runner=runner,
                )
            transcript_text = Path(result.report["artifact_path"]).read_text(encoding="utf-8")

        self.assertTrue(result.ok)
        self.assertEqual(result.report["asr_provider"], "qwen3_asr")
        self.assertEqual(result.report["qwen3_asr_language"], "Chinese")
        self.assertIn("中文转写内容", transcript_text)

    def test_qwen3_asr_reports_missing_asr_extra_with_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.mp4"
            source.write_bytes(b"mp4")
            with patch("kbprep_worker.converters.asr.find_spec", return_value=None):
                result = transcribe_media_with_qwen3_asr(
                    source,
                    root / "run",
                    which=lambda name: f"C:/Tools/{name}.exe",
                    runner=lambda *args: ExternalCommandResult(returncode=0, stdout="", stderr=""),
                )
        self.assertFalse(result.ok)
        self.assertEqual(result.report["failure_reason"]["dependency"], "qwen-asr")
        self.assertIn("asr extra", result.report["failure_reason"]["message"])

    def test_qwen3_asr_empty_inference_does_not_write_transcript(self):
        def runner(command: tuple[str, ...], cwd: Path | None, timeout_seconds: int) -> ExternalCommandResult:
            Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(command[-1]).write_bytes(b"wav")
            return ExternalCommandResult(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.mp4"
            source.write_bytes(b"mp4")
            run_dir = root / "run"
            with patch("kbprep_worker.converters.asr.find_spec", return_value=object()), patch(
                "kbprep_worker.converters.asr._run_qwen3_asr_inference",
                return_value="",
            ):
                result = transcribe_media_with_qwen3_asr(
                    source,
                    run_dir,
                    env={"KBPREP_ASR_LANGUAGE": "zh"},
                    which=lambda name: f"C:/Tools/{name}.exe",
                    runner=runner,
                )
            transcript_path = run_dir / "external" / "media_transcript" / "note.txt"
            self.assertFalse(result.ok)
            self.assertFalse(transcript_path.exists())

    def test_mobi_is_outside_external_tools_module_scope(self):
        supported = IMAGE_SOURCE_EXTENSIONS | LEGACY_OFFICE_SOURCE_EXTENSIONS | MEDIA_SOURCE_EXTENSIONS

        self.assertNotIn(".mobi", supported)


if __name__ == "__main__":
    unittest.main()
