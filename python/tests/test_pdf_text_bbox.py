"""PDF text-layer bbox native span extraction (M2 Slice 1.1).

The text-layer route now emits block-level content_list items carrying bbox so
the existing attach_pdf_native_source_spans / extract_pdf_native_source_spans
channel (built for MinerU OCR) also produces pdf_bbox native spans for trusted
PDF text layers. Markdown output stays page-level normalized; only the
content_list gains block-level bbox records.
"""
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from kbprep_worker.blockify import extract_pdf_native_source_spans
from kbprep_worker.pdf_text import _append_block_content_item


class PdfTextBboxTests(unittest.TestCase):
    def test_append_block_content_item_carries_bbox(self) -> None:
        content_list: list[dict[str, Any]] = []
        block = (0.0, 0.0, 100.0, 20.0, "Hello paragraph.", 0, 0)

        _append_block_content_item(content_list, block, page_idx=0)

        self.assertEqual(len(content_list), 1)
        item = content_list[0]
        self.assertEqual(item["page_idx"], 0)
        self.assertEqual(item["bbox"], [0.0, 0.0, 100.0, 20.0])
        self.assertEqual(item["text"], "Hello paragraph.")

    def test_append_block_content_item_skips_image_empty_and_invalid_bbox(self) -> None:
        content_list: list[dict[str, Any]] = []

        # image block (block_type=1) -> skipped
        _append_block_content_item(content_list, (0.0, 0.0, 10.0, 10.0, "alt", 0, 1), page_idx=0)
        # empty text -> skipped
        _append_block_content_item(content_list, (0.0, 0.0, 10.0, 10.0, "   ", 0, 0), page_idx=0)
        # non-numeric bbox element -> skipped
        _append_block_content_item(content_list, (0.0, 0.0, 10.0, "bad", "text", 0, 0), page_idx=0)

        self.assertEqual(content_list, [])

    def test_text_layer_content_list_produces_pdf_bbox_spans(self) -> None:
        content_list = [
            {"type": "text", "page_idx": 0, "text": "First paragraph.", "bbox": [0.0, 0.0, 100.0, 20.0]},
            {"type": "text", "page_idx": 0, "text": "Second paragraph.", "bbox": [0.0, 30.0, 100.0, 50.0]},
        ]
        converted_text = "<!-- page: 1 -->\n\nFirst paragraph.\n\nSecond paragraph."
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(content_list, handle)
            content_list_path = handle.name
        try:
            spans = extract_pdf_native_source_spans(content_list_path, converted_text)
        finally:
            Path(content_list_path).unlink(missing_ok=True)

        self.assertEqual(len(spans), 2)
        for span in spans:
            self.assertEqual(span["precision"], "pdf_bbox")
            self.assertIn("page", span["location"])
            self.assertIn("bbox", span["location"])


if __name__ == "__main__":
    unittest.main()
