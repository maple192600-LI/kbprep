import tempfile
import unittest
from pathlib import Path

from kbprep_worker.stages.pipeline_core import PipelineError, PipelineState, _stage_convert


class PipelineStateContractTests(unittest.TestCase):
    def test_stage_precondition_failure_has_clear_error_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, "input.md")
            source.write_text("# Title\n", encoding="utf-8")
            state = PipelineState({"input_path": str(source), "output_root": str(Path(tmp, "out"))})

            with self.assertRaises(PipelineError) as raised:
                _stage_convert(state)

        self.assertEqual(raised.exception.code, "E_PIPELINE_STAGE_ORDER")
        self.assertIn("convert", raised.exception.message)


if __name__ == "__main__":
    unittest.main()
