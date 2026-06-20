import tempfile
import unittest
import zipfile
from pathlib import Path

from kbprep_worker.converter_registry import file_identity_for_path
from kbprep_worker.zip_safety import (
    ZipSafetyError,
    ZipSafetyLimits,
    open_safe_zip,
)


class ZipSafetyTests(unittest.TestCase):
    def test_rejects_too_many_entries_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "many.zip")
            _write_zip(path, {"a.txt": b"a", "b.txt": b"b"})

            with self.assertRaisesRegex(ZipSafetyError, "entry count"):
                open_safe_zip(path, _limits(max_entries=1))

    def test_rejects_single_entry_uncompressed_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "large-entry.zip")
            _write_zip(path, {"big.txt": b"x" * 11})

            with self.assertRaisesRegex(ZipSafetyError, "entry big.txt"):
                open_safe_zip(path, _limits(max_entry_uncompressed_bytes=10))

    def test_rejects_total_uncompressed_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "large-total.zip")
            _write_zip(path, {"a.txt": b"x" * 6, "b.txt": b"y" * 6})

            with self.assertRaisesRegex(ZipSafetyError, "total uncompressed"):
                open_safe_zip(path, _limits(max_total_uncompressed_bytes=10))

    def test_reads_entry_through_safe_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "safe.zip")
            _write_zip(path, {"a.txt": b"ok"})

            with open_safe_zip(path, _limits()) as archive:
                self.assertEqual(archive.read_bytes("a.txt"), b"ok")
                self.assertIn("a.txt", archive.namelist())

    def test_office_and_epub_do_not_read_zip_entries_directly(self):
        root = Path(__file__).resolve().parents[1]
        office_source = (root / "kbprep_worker/converters/office_xml.py").read_text(encoding="utf-8")
        epub_source = (root / "kbprep_worker/epub.py").read_text(encoding="utf-8")
        registry_source = (root / "kbprep_worker/converter_registry.py").read_text(encoding="utf-8")

        self.assertNotIn("zf.read(", office_source)
        self.assertNotIn("zf.read(", epub_source)
        self.assertNotIn("archive.read(", registry_source)

    def test_converter_registry_sniff_rejects_unsafe_zip_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "unsafe.epub")
            _write_zip(path, {"../mimetype": b"application/epub+zip"})

            identity = file_identity_for_path(path)

        self.assertEqual(identity.signatures, ())


def _write_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def _limits(
    max_entries: int = 10,
    max_entry_uncompressed_bytes: int = 100,
    max_total_uncompressed_bytes: int = 100,
) -> ZipSafetyLimits:
    return ZipSafetyLimits(
        max_entries=max_entries,
        max_entry_uncompressed_bytes=max_entry_uncompressed_bytes,
        max_total_uncompressed_bytes=max_total_uncompressed_bytes,
    )


if __name__ == "__main__":
    unittest.main()
