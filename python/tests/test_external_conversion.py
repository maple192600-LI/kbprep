import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.stages import external_conversion


class ExternalConversionTests(unittest.TestCase):
    def test_generated_pdf_uses_mineru_txt_mode_from_phase_b_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "generated.pdf"
            converted_path = root / "converted.md"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            calls: list[str] = []

            def fake_mineru(
                input_p: Path,
                output_path: Path,
                run_dir: Path,
                language: str,
                mode: str,
            ) -> dict:
                calls.append(mode)
                output_path.write_text("# Converted\n\nKeep the text layer order.\n", encoding="utf-8")
                return {"source_md_path": str(output_path), "converter": "mineru", "warnings": []}

            diagnosis = {
                "detected_format": "pdf",
                "conversion_strategy": "mineru_auto",
                "pdf_route_diagnostics": {
                    "schema": "kbprep.pdf_route_diagnostics.v1",
                    "recommended_tier": "tier_2",
                    "recommended_route": "mineru_txt",
                    "reason": "Tier 2 because text is trusted but layout is complex.",
                },
            }

            with patch("kbprep_worker.diagnose.pdf_analysis.analyze_pdf", return_value=diagnosis), \
                patch.object(external_conversion, "_run_mineru_conversion", side_effect=fake_mineru):
                artifacts, pdf_diagnosis = external_conversion._convert_generated_pdf(
                    pdf_path,
                    converted_path,
                    root,
                    "zh",
                )

            self.assertEqual(calls, ["txt"])
            self.assertEqual(artifacts["mineru_mode"], "txt")
            self.assertEqual(pdf_diagnosis["pdf_route_diagnostics"]["recommended_route"], "mineru_txt")


if __name__ == "__main__":
    unittest.main()
