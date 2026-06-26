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


class CanonicalIrRelationshipTests(unittest.TestCase):
    def test_prepare_writes_structure_relationship_artifact_and_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            source.write_text("# Lesson\n\nIntro paragraph.\n\n## Step One\n\nDo the work.\n", encoding="utf-8")

            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(root / "out"), "force": True, "profile": "standard"},
            )

            self.assertEqual(code, 0)
            run_dir = Path(envelope["data"]["run_dir"])
            manifest = json.loads((run_dir / "canonical_ir" / "manifest.json").read_text(encoding="utf-8"))
            relationships = json.loads((run_dir / "canonical_ir" / "relationships.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["artifacts"]["relationships"], "canonical_ir/relationships.json")
        self.assertTrue(manifest["coverage"]["relationships_available"])
        self.assertEqual(manifest["coverage"]["report"]["gaps"]["relationships"]["status"], "partial")
        self.assertEqual(relationships["schema"], "kbprep.canonical_ir_relationships.v1")
        self.assertEqual(relationships["relationship_count"], len(relationships["relationships"]))
        relation_types = {item["type"] for item in relationships["relationships"]}
        self.assertIn("contains", relation_types)
        self.assertIn("next_sibling", relation_types)
        self.assertFalse(any("Intro paragraph" in json.dumps(item) for item in relationships["relationships"]))

    def test_prepare_writes_references_relationship_linking_paragraph_to_adjacent_figure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            asset_dir = root / "assets"
            asset_dir.mkdir()
            (asset_dir / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            source.write_text(
                "# Lesson\n\nIntro paragraph referencing the chart.\n\n![Chart](assets/chart.png)\n",
                encoding="utf-8",
            )
            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(root / "out"), "force": True, "profile": "standard"},
            )
            self.assertEqual(code, 0)
            run_dir = Path(envelope["data"]["run_dir"])
            relationships = json.loads((run_dir / "canonical_ir" / "relationships.json").read_text(encoding="utf-8"))
        relation_types = {item["type"] for item in relationships["relationships"]}
        self.assertIn("references", relation_types)
        references_records = [item for item in relationships["relationships"] if item["type"] == "references"]
        self.assertTrue(references_records)
        ref = references_records[0]
        self.assertTrue(ref["source_node_id"].startswith("n_"))
        self.assertTrue(ref["target_node_id"].startswith("n_"))
        self.assertNotEqual(ref["source_node_id"], ref["target_node_id"])
        self.assertFalse(any("Intro paragraph" in json.dumps(item) for item in references_records))


if __name__ == "__main__":
    unittest.main()
