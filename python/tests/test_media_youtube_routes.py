import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.converter_capabilities import get_capability_for_extension
from kbprep_worker.converters.external_tools import (
    ExternalCommandResult,
    ExternalConversionResult,
    extract_youtube_transcript,
    transcribe_media_with_whisper,
)
from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.stages import external_conversion
from kbprep_worker.stages.pipeline import run as run_prepare


class TestMediaYoutubeRoute(unittest.TestCase):
    def test_local_media_fixture_transcribes_with_command_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.mp4"
            run_dir = root / "run"
            source.write_bytes(b"golden media placeholder")

            def runner(command: tuple[str, ...], cwd: Path | None, timeout_seconds: int) -> ExternalCommandResult:
                self.assertGreater(timeout_seconds, 0)
                if command[0] == "ffmpeg":
                    Path(command[-1]).write_bytes(b"wav")
                if command[0] == "whisper":
                    output_dir = Path(command[-1])
                    output_dir.mkdir(parents=True, exist_ok=True)
                    (output_dir / "lesson.txt").write_text("Step 1: keep threshold=0.8.\n", encoding="utf-8")
                return ExternalCommandResult(0, "", "")

            result = transcribe_media_with_whisper(
                source,
                run_dir,
                which=lambda tool: tool,
                runner=runner,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.report["route_decision"]["external_route"], "media_to_transcript")
            self.assertEqual(result.report["whisper_model"], "base")
            self.assertEqual(result.artifact_path.read_text(encoding="utf-8").strip(), "Step 1: keep threshold=0.8.")
            self.assertEqual(get_capability_for_extension(".mp4")["status"], "partial")

    def test_youtube_prefers_subtitles_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"

            def runner(command: tuple[str, ...], cwd: Path | None, timeout_seconds: int) -> ExternalCommandResult:
                self.assertIn("--skip-download", command)
                output_index = command.index("--output") + 1
                output_template = Path(command[output_index])
                output_template.parent.mkdir(parents=True, exist_ok=True)
                subtitle = output_template.with_name(f"{output_template.name}.en.vtt")
                subtitle.write_text(
                    "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nKeep setup step threshold=0.8.\n",
                    encoding="utf-8",
                )
                return ExternalCommandResult(0, "", "")

            result = extract_youtube_transcript(
                "https://www.youtube.com/watch?v=ExampleVideo01",
                run_dir,
                which=lambda tool: tool,
                runner=runner,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.report["route_decision"]["external_route"], "youtube_subtitle")
            self.assertEqual(result.report["route_decision"]["fallback_applied"], "false")
            self.assertIn("Keep setup step threshold=0.8.", result.artifact_path.read_text(encoding="utf-8"))

    def test_youtube_falls_back_to_media_transcript_when_subtitles_are_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"

            def runner(command: tuple[str, ...], cwd: Path | None, timeout_seconds: int) -> ExternalCommandResult:
                if "--skip-download" in command:
                    return ExternalCommandResult(1, "", "No subtitles are available for this video")
                if command[0] == "yt-dlp":
                    output_index = command.index("--output") + 1
                    Path(command[output_index]).write_bytes(b"media")
                    return ExternalCommandResult(0, "", "")
                if command[0] == "ffmpeg":
                    Path(command[-1]).write_bytes(b"wav")
                    return ExternalCommandResult(0, "", "")
                if command[0] == "whisper":
                    output_dir = Path(command[-1])
                    output_dir.mkdir(parents=True, exist_ok=True)
                    (output_dir / "ExampleVideo01.txt").write_text(
                        "Fallback transcript keeps retry_count=3.\n",
                        encoding="utf-8",
                    )
                    return ExternalCommandResult(0, "", "")
                return ExternalCommandResult(1, "", f"unexpected command: {command}")

            result = extract_youtube_transcript(
                "https://youtu.be/ExampleVideo01",
                run_dir,
                which=lambda tool: tool,
                runner=runner,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.report["route_decision"]["external_route"], "youtube_media_transcript")
            self.assertEqual(result.report["route_decision"]["fallback_from"], "youtube_subtitle")
            self.assertIn("Fallback transcript keeps retry_count=3.", result.artifact_path.read_text(encoding="utf-8"))

    def test_youtube_route_reports_missing_dependency_before_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = extract_youtube_transcript(
                "https://www.youtube.com/watch?v=ExampleVideo01",
                Path(tmp),
                which=lambda tool: None,
            )

            self.assertFalse(result.ok)
            self.assertEqual(result.report["failure_reason"]["code"], "E_ENV_MISSING")
            self.assertEqual(result.report["failure_reason"]["dependency"], "yt-dlp")

    def test_youtube_descriptor_pipeline_writes_transcript_without_bypassing_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.url"
            output_root = root / "output"
            source.write_text("[InternetShortcut]\nURL=https://www.youtube.com/watch?v=ExampleVideo01\n", encoding="utf-8")

            def fake_extract(source_url: str, run_dir: Path) -> object:
                transcript = run_dir / "external" / "youtube_subtitle" / "ExampleVideo01.txt"
                transcript.parent.mkdir(parents=True, exist_ok=True)
                transcript.write_text("00:00 Keep setup step threshold=0.8.\n", encoding="utf-8")
                return type("Result", (), {
                    "ok": True,
                    "artifact_path": transcript,
                    "report": {
                        "route_decision": {
                            "declared_route": "external_conversion_required",
                            "source_extension": ".url",
                            "external_route": "youtube_subtitle",
                            "next_route": "direct_text",
                            "status": "success",
                            "fallback_applied": "false",
                        },
                        "sanitized_commands": [["yt-dlp", "--skip-download", "{source_url}"]],
                        "artifact_path": str(transcript),
                        "failure_reason": None,
                    },
                })()

            with patch.object(external_conversion, "extract_youtube_transcript", side_effect=fake_extract):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(EnvelopeExit) as exit_context:
                        run_prepare({
                            "input_path": str(source),
                            "output_root": str(output_root),
                            "profile": "standard",
                            "mode": "rules_only",
                            "language": "en",
                            "force": True,
                        })
            self.assertEqual(exit_context.exception.code, 0)

            latest = json.loads((output_root / "latest.json").read_text(encoding="utf-8"))
            conversion = json.loads((Path(latest["run_dir"]) / "conversion_report.json").read_text(encoding="utf-8"))
            self.assertEqual(conversion["route_decision"]["declared_capability_id"], "youtube_url_routes")
            self.assertEqual(conversion["route_decision"]["actual_route"], "youtube_subtitle")
            self.assertTrue((root / "lesson.md").exists())
            self.assertIn("threshold=0.8", (root / "lesson.md").read_text(encoding="utf-8"))

    def test_failed_youtube_rerun_preserves_previous_successful_deliverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.url"
            output_root = root / "output"
            source.write_text("[InternetShortcut]\nURL=https://www.youtube.com/watch?v=ExampleVideo01\n", encoding="utf-8")

            def successful_extract(source_url: str, run_dir: Path) -> ExternalConversionResult:
                transcript = run_dir / "external" / "youtube_subtitle" / "ExampleVideo01.txt"
                transcript.parent.mkdir(parents=True, exist_ok=True)
                transcript.write_text("Keep first successful transcript.\n", encoding="utf-8")
                return _youtube_fixture_result(transcript, "success")

            def failed_extract(source_url: str, run_dir: Path) -> ExternalConversionResult:
                return ExternalConversionResult(
                    ok=False,
                    artifact_path=None,
                    report={
                        "route_decision": {
                            "external_route": "youtube_subtitle",
                            "status": "failed",
                        },
                        "failure_reason": {
                            "code": "E_ENV_MISSING",
                            "dependency": "yt-dlp",
                            "message": "Required external dependency is not available: yt-dlp.",
                        },
                    },
                )

            with patch.object(external_conversion, "extract_youtube_transcript", side_effect=successful_extract):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(EnvelopeExit) as success_exit:
                        run_prepare(_prepare_payload(source, output_root))
            self.assertEqual(success_exit.exception.code, 0)
            latest_before = json.loads((output_root / "latest.json").read_text(encoding="utf-8"))
            final_before = (root / "lesson.md").read_text(encoding="utf-8")

            with patch.object(external_conversion, "extract_youtube_transcript", side_effect=failed_extract):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(EnvelopeExit) as failure_exit:
                        run_prepare(_prepare_payload(source, output_root))

            self.assertEqual(failure_exit.exception.code, 1)
            latest_after = json.loads((output_root / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest_after["run_id"], latest_before["run_id"])
            self.assertEqual((root / "lesson.md").read_text(encoding="utf-8"), final_before)

def _prepare_payload(source: Path, output_root: Path) -> dict:
    return {
        "input_path": str(source),
        "output_root": str(output_root),
        "profile": "standard",
        "mode": "rules_only",
        "language": "en",
        "force": True,
    }


def _youtube_fixture_result(transcript: Path, status: str) -> ExternalConversionResult:
    return ExternalConversionResult(
        ok=True,
        artifact_path=transcript,
        report={
            "route_decision": {
                "declared_route": "external_conversion_required",
                "source_extension": ".url",
                "external_route": "youtube_subtitle",
                "next_route": "direct_text",
                "status": status,
                "fallback_applied": "false",
            },
            "sanitized_commands": [["yt-dlp", "--skip-download", "{source_url}"]],
            "artifact_path": str(transcript),
            "failure_reason": None,
        },
    )


if __name__ == "__main__":
    unittest.main()
