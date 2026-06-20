"""Tests for block-aware splitting, focused on rerun hygiene.

apply_patch re-runs splitting on the same run_dir. Stale chunk files from the
previous iteration must be removed, otherwise glob-based chunk counts pick up
leftover files and diverge from the fresh chunk_manifest.jsonl.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from kbprep_worker import split


def _kept_block(text: str, idx: int = 0) -> dict:
    return {
        "block_id": f"b{idx}",
        "type": "paragraph",
        "status": "keep",
        "text": text,
    }


class SplitRerunCleansStaleChunksTests(unittest.TestCase):
    def test_rerun_removes_stale_chunk_files(self) -> None:
        run_dir = Path(tempfile.mkdtemp(prefix="kbprep-split-rerun-"))
        try:
            big_blocks = [_kept_block(f"section {i} " + ("x" * 1300), i) for i in range(10)]
            first = split.split_into_chunks(big_blocks, str(run_dir), "pdf_like", "hash1", "run1")
            chunks_dir = run_dir / "chunks"
            self.assertEqual(len(list(chunks_dir.glob("*.md"))), first["chunk_count"])
            self.assertGreater(first["chunk_count"], 3)

            # Second split on the SAME run_dir with far fewer blocks.
            small_blocks = [_kept_block("only one chunk " + ("y" * 1300), 0)]
            second = split.split_into_chunks(small_blocks, str(run_dir), "pdf_like", "hash2", "run2")
            second_files = sorted(chunks_dir.glob("*.md"))

            # Stale files from the first run must be gone.
            self.assertEqual(len(second_files), second["chunk_count"])
            self.assertEqual(len(second_files), 1)
            manifest_lines = (run_dir / "chunk_manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(manifest_lines), second["chunk_count"])
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
