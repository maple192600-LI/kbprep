import tempfile
import unittest
from pathlib import Path

from kbprep_worker.converters.html import rich_html_to_markdown
from kbprep_worker.stages.pipeline import _copy_local_markdown_image_assets


class ImagePathSafetyTests(unittest.TestCase):
    def test_markdown_image_copy_skips_encoded_parent_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "source"
            source_dir.mkdir()
            run_dir = root / "run"
            outside = root / "secret.png"
            outside.write_bytes(b"secret")
            note = source_dir / "note.md"
            note.write_text("![x](..%2fsecret.png)", encoding="utf-8")

            text, artifacts = _copy_local_markdown_image_assets(note.read_text(encoding="utf-8"), note, run_dir)

        self.assertIn("..%2fsecret.png", text)
        self.assertEqual(artifacts["local_image_assets"]["copied_count"], 0)
        self.assertEqual(artifacts["local_image_assets"]["skipped_count"], 1)

    def test_html_image_copy_skips_parent_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "source"
            source_dir.mkdir()
            run_dir = root / "run"
            (root / "secret.png").write_bytes(b"secret")

            markdown = rich_html_to_markdown(
                '<html><body><img src="../secret.png" alt="secret"/></body></html>',
                run_dir=run_dir,
                source_stem="page",
                source_root=source_dir,
            )

        self.assertNotIn("images/secret.png", markdown)
        self.assertFalse((run_dir / "images" / "secret.png").exists())


if __name__ == "__main__":
    unittest.main()
