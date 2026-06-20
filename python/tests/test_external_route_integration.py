import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.converters.external_tools import ExternalConversionResult
from kbprep_worker.stages import pipeline_core


def _success_report(source: Path, external_route: str, next_route: str, artifact: Path) -> dict:
    return {
        "route_decision": {
            "declared_route": "external_conversion_required",
            "source_extension": source.suffix.lower(),
            "external_route": external_route,
            "next_route": next_route,
            "status": "success",
        },
        "sanitized_commands": [["tool", "{input_file}", "{artifact_path}"]],
        "artifact_path": str(artifact),
        "failure_reason": None,
    }


def _state(source: Path, run_dir: Path) -> pipeline_core.PipelineState:
    state = pipeline_core.PipelineState({
        "input_path": str(source),
        "output_root": str(run_dir.parent),
        "language": "en",
        "force": True,
    })
    state.run_dir = run_dir
    state.source_type = "pdf_like"
    state.runtime = {}
    state.file_hash = "hash"
    return state


class ExternalRouteIntegrationTests(unittest.TestCase):
    def test_image_route_wraps_pdf_then_runs_mineru_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "scan.png"
            source.write_bytes(b"png")
            run_dir = root / "run"
            run_dir.mkdir()
            pdf = run_dir / "external" / "image_pdf" / "scan.external.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.7")
            state = _state(source, run_dir)

            def fake_mineru(input_p: Path, output: Path, _run_dir: Path, _language: str, mode: str) -> dict:
                self.assertEqual(input_p, pdf)
                self.assertEqual(mode, "ocr")
                output.write_text("OCR text", encoding="utf-8")
                return {"source_md_path": str(output), "warnings": []}

            external = ExternalConversionResult(True, pdf, _success_report(source, "image_to_pdf", "mineru_ocr", pdf))
            with patch("kbprep_worker.converters.external_tools.wrap_image_as_pdf", return_value=external), \
                patch("kbprep_worker.stages.external_conversion._run_mineru_conversion", side_effect=fake_mineru):
                pipeline_core._stage_convert(state)

            report = json.loads((run_dir / "conversion_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["converter"], "image_to_pdf_ocr")
            self.assertEqual(report["mineru_artifacts"]["external_conversion"]["route_decision"]["external_route"], "image_to_pdf")

    def test_media_route_writes_transcript_as_converted_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.mp4"
            source.write_bytes(b"mp4")
            run_dir = root / "run"
            run_dir.mkdir()
            transcript = run_dir / "external" / "media_transcript" / "lesson.txt"
            transcript.parent.mkdir(parents=True)
            transcript.write_text("hello transcript", encoding="utf-8")
            state = _state(source, run_dir)
            state.source_type = "generic_block"

            external = ExternalConversionResult(
                True,
                transcript,
                _success_report(source, "media_to_transcript", "direct_text", transcript),
            )
            with patch("kbprep_worker.converters.external_tools.transcribe_media_with_whisper", return_value=external):
                pipeline_core._stage_convert(state)

            self.assertEqual((run_dir / "converted.md").read_text(encoding="utf-8"), "hello transcript\n")
            report = json.loads((run_dir / "conversion_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["route_decision"]["actual_route"], "media_to_transcript")

    def test_legacy_office_route_converts_pdf_then_uses_pdf_text_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "deck.ppt"
            source.write_bytes(b"ppt")
            run_dir = root / "run"
            run_dir.mkdir()
            pdf = run_dir / "external" / "legacy_office_pdf" / "deck.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.7")
            state = _state(source, run_dir)

            external = ExternalConversionResult(True, pdf, _success_report(source, "legacy_office_to_pdf", "pdf_route", pdf))

            def fake_pdf_text(_input: Path, output: Path, _run_dir: Path) -> dict:
                output.write_text("slide text", encoding="utf-8")
                return {"source_md_path": str(output), "converter": "pdf_text_layer", "warnings": []}

            with patch("kbprep_worker.converters.external_tools.convert_legacy_office_to_pdf", return_value=external), \
                patch("kbprep_worker.diagnose.pdf_analysis.analyze_pdf", return_value={
                    "conversion_strategy": "pdf_text_layer",
                    "recommended_pipeline": "pdf_text_layer",
                    "text_layer_health": "good",
                }), \
                patch("kbprep_worker.pdf_text.convert_text_layer_pdf", side_effect=fake_pdf_text):
                pipeline_core._stage_convert(state)

            report = json.loads((run_dir / "conversion_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["converter"], "legacy_office_pdf_text_layer")
            self.assertIn("generated_pdf_diagnosis", report["mineru_artifacts"])

    def test_legacy_office_generated_pdf_fallback_records_ocr_quality_and_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "deck.ppt"
            source.write_bytes(b"ppt")
            run_dir = root / "run"
            run_dir.mkdir()
            pdf = run_dir / "external" / "legacy_office_pdf" / "deck.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.7")
            state = _state(source, run_dir)

            external = ExternalConversionResult(True, pdf, _success_report(source, "legacy_office_to_pdf", "pdf_route", pdf))

            def bad_pdf_text(_input: Path, output: Path, _run_dir: Path) -> dict:
                output.write_text("���" * 80, encoding="utf-8")
                return {"source_md_path": str(output), "converter": "pdf_text_layer", "warnings": ["fake bad text layer"]}

            def fake_mineru(_input: Path, output: Path, _run_dir: Path, _language: str, mode: str) -> dict:
                self.assertEqual(mode, "ocr")
                output.write_text("OCR text with threshold=0.8", encoding="utf-8")
                return {"source_md_path": str(output), "converter": "mineru", "warnings": []}

            with patch("kbprep_worker.converters.external_tools.convert_legacy_office_to_pdf", return_value=external), \
                patch("kbprep_worker.diagnose.pdf_analysis.analyze_pdf", return_value={
                    "conversion_strategy": "pdf_text_layer",
                    "recommended_pipeline": "pdf_text_layer",
                    "text_layer_health": "good",
                }), \
                patch("kbprep_worker.pdf_text.convert_text_layer_pdf", side_effect=bad_pdf_text), \
                patch("kbprep_worker.stages.external_conversion._run_mineru_conversion", side_effect=fake_mineru):
                pipeline_core._stage_convert(state)

            report = json.loads((run_dir / "conversion_report.json").read_text(encoding="utf-8"))
            artifacts = report["mineru_artifacts"]
            decision = report["route_decision"]
            self.assertEqual(artifacts["fallback_from"], "pdf_text_layer")
            self.assertIn("rejected_text_layer_quality", artifacts)
            self.assertIn("post_convert_text_quality", artifacts)
            self.assertTrue(any("W_PDF_TEXT_LAYER_FALLBACK_TO_OCR" in warning for warning in report["warnings"]))
            self.assertTrue(decision["fallback_applied"])
            self.assertEqual(decision["actual_route"], "legacy_office_to_pdf_then_mineru_ocr")
            self.assertEqual(decision["fallback_to"], "legacy_office_to_pdf_then_mineru_ocr")


if __name__ == "__main__":
    unittest.main()
