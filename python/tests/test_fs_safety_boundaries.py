"""Tests for the output_root / input_path boundary guards."""
from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from kbprep_worker.fs_safety import is_safe_input_path, is_safe_output_root


class IsSafeOutputRootTests(TestCase):
    def test_normal_directory_passes(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertTrue(is_safe_output_root(Path(tmp) / "out"))

    def test_filesystem_root_rejected(self) -> None:
        # "/" resolves to the drive root on Windows and the POSIX root
        # elsewhere; both satisfy resolved == resolved.parent.
        self.assertFalse(is_safe_output_root(Path("/")))

    def test_user_home_rejected(self) -> None:
        self.assertFalse(is_safe_output_root(Path.home()))

    def test_protected_os_dir_rejected(self) -> None:
        protected = Path("C:/Windows") if sys.platform == "win32" else Path("/etc")
        self.assertFalse(is_safe_output_root(protected))


class IsSafeInputPathTests(TestCase):
    def test_nonexistent_passes(self) -> None:
        # Existence is reported separately (E_INPUT_NOT_FOUND); the boundary
        # guard stays neutral on missing paths.
        self.assertTrue(is_safe_input_path(Path("/no/such/expected.md")))

    def test_normal_file_passes(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.md"
            path.write_text("hello", encoding="utf-8")
            self.assertTrue(is_safe_input_path(path))

    def test_oversized_file_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.bin"
            path.write_bytes(b"\x00" * 10)
            self.assertFalse(is_safe_input_path(path, max_size_mb=0))
