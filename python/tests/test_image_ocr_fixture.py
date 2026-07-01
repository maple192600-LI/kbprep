"""Lock the real MinerU image-OCR fixture as version-controlled evidence."""

import hashlib
import unittest
from pathlib import Path

FIXTURE_IMAGE = Path(__file__).parent / "golden" / "formats" / "image" / "ocr_sample_en.png"
FIXTURE_IMAGE_SHA256 = "0152893135c44241d0dabca319f694e6cfcb6bec54a2fb4358ae8cf0e7b55043"
FIXTURE_TEXT = Path(__file__).parent / "golden" / "formats" / "image" / "ocr_sample_en.txt"
FIXTURE_TEXT_SHA256 = "ec3db1bebf0b1d3ec9ad2f930a0e3fa51ca1c8ddc585709c4c18bbcd6fb1d5e6"


class ImageOcrFixtureTests(unittest.TestCase):
    def test_real_mineru_image_ocr_fixture_is_version_controlled(self) -> None:
        """Lock a real image OCR run as version-controlled evidence.

        The fixture pair is an English Hermes Agent tutorial screenshot
        (owner-provided) plus the Markdown extracted by running it through the
        project image-OCR chain: PyMuPDF wraps the PNG as a PDF, then MinerU
        OCR (project venv, auto mode, en) extracts the text. It is an evidence
        snapshot: OCR output can vary across MinerU versions, so CI does not
        re-run OCR. Instead the content hashes below lock the current snapshot;
        any silent drift in the source image or the extracted text fails this
        test until the fixture is regenerated deliberately.
        """
        self.assertTrue(FIXTURE_IMAGE.exists(), f"image OCR source fixture missing: {FIXTURE_IMAGE}")
        self.assertTrue(FIXTURE_TEXT.exists(), f"image OCR text fixture missing: {FIXTURE_TEXT}")
        text = FIXTURE_TEXT.read_text(encoding="utf-8").strip()
        self.assertGreater(len(text), 200)
        self.assertLess(len(text), 8000)
        self.assertIn("Hermes Agent", text)
        self.assertIn("interview", text)

    def test_real_mineru_image_ocr_fixture_hashes_are_locked(self) -> None:
        """Content-hash locks that catch silent fixture drift in CI."""
        self.assertTrue(FIXTURE_IMAGE.exists(), f"image OCR source fixture missing: {FIXTURE_IMAGE}")
        image_hash = hashlib.sha256(FIXTURE_IMAGE.read_bytes()).hexdigest()
        self.assertEqual(
            image_hash,
            FIXTURE_IMAGE_SHA256,
            "image OCR source image drifted from the locked snapshot; regenerate "
            "it deliberately and update FIXTURE_IMAGE_SHA256",
        )
        text_hash = hashlib.sha256(FIXTURE_TEXT.read_bytes()).hexdigest()
        self.assertEqual(
            text_hash,
            FIXTURE_TEXT_SHA256,
            "image OCR extracted text drifted from the locked snapshot; regenerate "
            "it deliberately (re-run MinerU OCR) and update FIXTURE_TEXT_SHA256",
        )


if __name__ == "__main__":
    unittest.main()
