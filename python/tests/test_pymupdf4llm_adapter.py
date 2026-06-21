import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from kbprep_worker.pymupdf4llm_adapter import convert_pymupdf4llm_pdf


class PyMuPDF4LLMAdapterTests(unittest.TestCase):
    def test_converts_page_chunks_to_markdown_and_content_list(self):
        fake = types.SimpleNamespace()
        calls = []

        def to_markdown(doc, *, page_chunks=False, write_images=False, image_path=None, image_format=None, dpi=None):
            calls.append({
                "doc": doc,
                "page_chunks": page_chunks,
                "write_images": write_images,
                "image_path": image_path,
                "image_format": image_format,
                "dpi": dpi,
            })
            self.assertTrue(page_chunks)
            return [
                {"metadata": {"page_number": 1, "title": "First"}, "text": "Step 1: keep threshold=0.8."},
                {"metadata": {"page_number": 2, "title": "Second"}, "text": "Step 2: keep retry_count=3."},
            ]

        fake.to_markdown = to_markdown
        old_module = sys.modules.get("pymupdf4llm")
        sys.modules["pymupdf4llm"] = fake
        try:
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                input_path = root / "simple.pdf"
                output_path = root / "converted.md"
                input_path.write_bytes(b"%PDF-1.7\n")

                result = convert_pymupdf4llm_pdf(input_path, output_path, root)

                markdown = output_path.read_text(encoding="utf-8")
                self.assertIn("<!-- page: 1 -->", markdown)
                self.assertIn("threshold=0.8", markdown)
                self.assertIn("retry_count=3", markdown)
                self.assertEqual(result["converter"], "pymupdf4llm")
                self.assertTrue(Path(str(result["content_list_path"])).exists())
                self.assertEqual(calls[0]["image_format"], "png")
                self.assertEqual(calls[0]["dpi"], 150)
        finally:
            if old_module is None:
                sys.modules.pop("pymupdf4llm", None)
            else:
                sys.modules["pymupdf4llm"] = old_module

    def test_rejects_empty_markdown(self):
        fake = types.SimpleNamespace(to_markdown=lambda *args, **kwargs: [{"metadata": {"page_number": 1}, "text": ""}])
        old_module = sys.modules.get("pymupdf4llm")
        sys.modules["pymupdf4llm"] = fake
        try:
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                input_path = root / "empty.pdf"
                output_path = root / "converted.md"
                input_path.write_bytes(b"%PDF-1.7\n")

                with self.assertRaises(RuntimeError):
                    convert_pymupdf4llm_pdf(input_path, output_path, root)
        finally:
            if old_module is None:
                sys.modules.pop("pymupdf4llm", None)
            else:
                sys.modules["pymupdf4llm"] = old_module


if __name__ == "__main__":
    unittest.main()
