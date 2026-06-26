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


class CanonicalIrAssetTests(unittest.TestCase):
    def test_prepare_writes_figure_asset_artifact_without_copying_alt_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            asset_dir = root / "assets"
            asset_dir.mkdir()
            (asset_dir / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            source.write_text('# Lesson\n\n![Private Alt Text](assets/chart.png "Private Title")\n', encoding="utf-8")

            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(root / "out"), "force": True, "profile": "standard"},
            )

            self.assertEqual(code, 0)
            run_dir = Path(envelope["data"]["run_dir"])
            manifest = json.loads((run_dir / "canonical_ir" / "manifest.json").read_text(encoding="utf-8"))
            assets = json.loads((run_dir / "canonical_ir" / "assets.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["artifacts"]["assets"], "canonical_ir/assets.json")
        self.assertTrue(manifest["coverage"]["assets_available"])
        self.assertEqual(manifest["coverage"]["report"]["gaps"]["assets"]["status"], "partial")
        self.assertEqual(assets["schema"], "kbprep.canonical_ir_assets.v1")
        self.assertEqual(assets["asset_count"], 1)
        asset = assets["assets"][0]
        self.assertEqual(asset["asset_type"], "image")
        self.assertEqual(asset["reference"], "images/assets/chart.png")
        self.assertEqual(asset["source_node_id"], "n_000002")
        self.assertNotIn("Private Alt Text", json.dumps(asset))
        self.assertNotIn("Private Title", json.dumps(asset))

    def test_prepare_writes_asset_referenced_by_and_source_path_for_figure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            asset_dir = root / "assets"
            asset_dir.mkdir()
            (asset_dir / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            source.write_text(
                "# Lesson\n\nIntro paragraph about the chart.\n\n![Chart](assets/chart.png)\n",
                encoding="utf-8",
            )
            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(root / "out"), "force": True, "profile": "standard"},
            )
            self.assertEqual(code, 0)
            run_dir = Path(envelope["data"]["run_dir"])
            assets = json.loads((run_dir / "canonical_ir" / "assets.json").read_text(encoding="utf-8"))
        self.assertEqual(assets["asset_count"], 1)
        asset = assets["assets"][0]
        self.assertIn("source_path", asset)
        self.assertTrue(asset["source_path"])
        self.assertIn("referenced_by", asset)
        referenced_by = asset["referenced_by"]
        self.assertIsInstance(referenced_by, list)
        self.assertTrue(referenced_by)
        self.assertTrue(all(isinstance(n, str) and n.startswith("n_") for n in referenced_by))
        self.assertFalse(any("Intro paragraph" in json.dumps(item) for item in assets["assets"]))

    def test_prepare_writes_table_asset_when_markdown_contains_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            source.write_text(
                "# Lesson\n\nIntro paragraph.\n\n| Col A | Col B |\n| --- | --- |\n| 1 | 2 |\n",
                encoding="utf-8",
            )
            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(root / "out"), "force": True, "profile": "standard"},
            )
            self.assertEqual(code, 0)
            run_dir = Path(envelope["data"]["run_dir"])
            assets = json.loads((run_dir / "canonical_ir" / "assets.json").read_text(encoding="utf-8"))
        asset_types = {item["asset_type"] for item in assets["assets"]}
        self.assertIn("table", asset_types)
        table_assets = [item for item in assets["assets"] if item["asset_type"] == "table"]
        self.assertEqual(table_assets[0]["reference_kind"], "inline_table")


if __name__ == "__main__":
    unittest.main()
