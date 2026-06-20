"""Tests for the atomic file write helpers."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from kbprep_worker.atomic_io import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
)


class AtomicWriteTextTests(TestCase):
    def test_replaces_full_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.txt"
            atomic_write_text(path, "hello")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello")
            atomic_write_text(path, "world")
            self.assertEqual(path.read_text(encoding="utf-8"), "world")

    def test_creates_parent_dirs(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "dir" / "f.txt"
            atomic_write_text(path, "x")
            self.assertEqual(path.read_text(encoding="utf-8"), "x")


class AtomicWriteFailureTests(TestCase):
    def test_partial_failure_leaves_previous_file_and_no_tmp(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.txt"
            atomic_write_text(path, "original")
            with patch(
                "kbprep_worker.atomic_io.os.fsync",
                side_effect=OSError("simulated"),
            ):
                with self.assertRaises(OSError):
                    atomic_write_text(path, "new", fsync_dir=False)
            # Previous content survives.
            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            # No leftover tempfile.
            leftovers = [p for p in Path(tmp).iterdir() if ".tmp." in p.name]
            self.assertEqual(leftovers, [])


class AtomicWriteJsonTests(TestCase):
    def test_indent_and_trailing_newline(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.json"
            atomic_write_json(path, {"b": 2, "a": 1}, indent=2)
            expected = json.dumps({"b": 2, "a": 1}, indent=2) + "\n"
            self.assertEqual(path.read_text(encoding="utf-8"), expected)

    def test_no_trailing_newline_option(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.json"
            atomic_write_json(path, [1, 2], indent=None, trailing_newline=False)
            self.assertEqual(path.read_text(encoding="utf-8"), "[1, 2]")

    def test_ensure_ascii(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.json"
            atomic_write_json(path, {"k": "中文"}, ensure_ascii=True)
            self.assertIn("\\u", path.read_text(encoding="utf-8"))


class AtomicWriteBytesTests(TestCase):
    def test_writes_raw_bytes(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.bin"
            atomic_write_bytes(path, b"\x00\x01\x02")
            self.assertEqual(path.read_bytes(), b"\x00\x01\x02")


class ConcurrentWritersTests(TestCase):
    def test_final_read_is_one_full_version(self) -> None:
        # Many threads write distinct full payloads; whatever we read at the
        # end must be exactly one of those payloads, never a splice of two.
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.txt"
            payloads = [f"payload-{i:04d}-" + "x" * 200 for i in range(50)]

            def writer(payload: str) -> None:
                atomic_write_text(path, payload, fsync_dir=False)

            threads = [threading.Thread(target=writer, args=(p,)) for p in payloads]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            final = path.read_text(encoding="utf-8")
            self.assertIn(final, payloads)
