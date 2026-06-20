import tempfile
import unittest
from pathlib import Path

from kbprep_worker.diagnose import DiagnoseError, diagnose_file
from kbprep_worker.stages import pipeline


class DiagnoseTests(unittest.TestCase):
    def test_diagnose_file_returns_data_without_writing_cli_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp, "note.md")
            input_path.write_text("# Title\n\nStep 1: set threshold=0.8\n", encoding="utf-8")

            result, warnings = diagnose_file({
                "input_path": str(input_path),
                "output_root": tmp,
                "source_type": "auto",
            })

        self.assertTrue(result["ok"])
        self.assertEqual(result["file_name"], "note.md")
        self.assertEqual(result["detected_format"], "markdown")
        self.assertIsInstance(warnings, list)

    def test_diagnose_file_raises_structured_error_for_missing_input(self):
        with self.assertRaises(DiagnoseError) as raised:
            diagnose_file({"input_path": "missing.md"})

        self.assertEqual(raised.exception.code, "E_INPUT_NOT_FOUND")

    def test_pipeline_diagnose_helper_does_not_spawn_a_nested_cli_process(self):
        source = Path(pipeline.__file__).read_text(encoding="utf-8")

        self.assertNotIn("subprocess.run", source)
        self.assertNotIn("kbprep_worker.cli\", \"diagnose", source)


if __name__ == "__main__":
    unittest.main()
