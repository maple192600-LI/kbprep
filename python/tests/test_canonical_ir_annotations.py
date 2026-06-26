import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.stages import pipeline_core


def _capture_envelope(fn, payload):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fn(payload)
    except EnvelopeExit as exc:
        return exc.code, json.loads(out.getvalue())
    raise AssertionError("worker command did not write a JSON envelope")


class CanonicalIrAnnotationTests(unittest.TestCase):
    def test_prepare_writes_coverage_warning_annotations_without_source_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            source.write_text("# Lesson\n\nSensitive source sentence should stay out of annotations.\n", encoding="utf-8")

            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(root / "out"), "force": True, "profile": "standard"},
            )

            self.assertEqual(code, 0)
            run_dir = Path(envelope["data"]["run_dir"])
            manifest = json.loads((run_dir / "canonical_ir" / "manifest.json").read_text(encoding="utf-8"))
            annotations = json.loads((run_dir / "canonical_ir" / "annotations.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["artifacts"]["annotations"], "canonical_ir/annotations.json")
        self.assertTrue(manifest["coverage"]["annotations_available"])
        self.assertEqual(manifest["coverage"]["report"]["gaps"]["annotations"]["status"], "partial")
        self.assertEqual(annotations["schema"], "kbprep.canonical_ir_annotations.v1")
        self.assertGreaterEqual(annotations["annotation_count"], 1)
        self.assertTrue(any(item["kind"] == "coverage_warning" for item in annotations["annotations"]))
        self.assertFalse(any("Sensitive source sentence" in json.dumps(item) for item in annotations["annotations"]))

    def test_prepare_writes_quality_warning_for_empty_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            source.write_text(
                "# Lesson\n\nReal intro paragraph.\n\n## Empty Section\n\n## Following Section\n\nContent here.\n",
                encoding="utf-8",
            )
            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(root / "out"), "force": True, "profile": "standard"},
            )
            self.assertEqual(code, 0)
            run_dir = Path(envelope["data"]["run_dir"])
            annotations = json.loads((run_dir / "canonical_ir" / "annotations.json").read_text(encoding="utf-8"))
        empty_heading_warnings = [
            item for item in annotations["annotations"]
            if item["kind"] == "quality_warning" and item["message_code"] == "W_EMPTY_HEADING"
        ]
        self.assertTrue(empty_heading_warnings)
        warn = empty_heading_warnings[0]
        self.assertTrue(warn["target"].startswith("n_"))
        self.assertFalse(any("Real intro" in json.dumps(item) for item in annotations["annotations"]))


if __name__ == "__main__":
    unittest.main()
