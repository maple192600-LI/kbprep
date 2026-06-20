import tempfile
import unittest
from pathlib import Path

from kbprep_worker.quality.runner import _count_chunks_with_unclosed_code_fences


class MarkdownFenceTests(unittest.TestCase):
    def test_inline_backticks_do_not_count_as_fences(self):
        with tempfile.TemporaryDirectory() as tmp:
            chunks = Path(tmp)
            (chunks / "part.md").write_text("Use inline ``` text in a sentence.", encoding="utf-8")

            self.assertEqual(_count_chunks_with_unclosed_code_fences(chunks), 0)

    def test_longer_fence_can_contain_shorter_backticks(self):
        with tempfile.TemporaryDirectory() as tmp:
            chunks = Path(tmp)
            (chunks / "part.md").write_text("````\nexample ``` inside\n````\n", encoding="utf-8")

            self.assertEqual(_count_chunks_with_unclosed_code_fences(chunks), 0)

    def test_unclosed_backtick_fence_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            chunks = Path(tmp)
            (chunks / "part.md").write_text("```python\nprint('x')\n", encoding="utf-8")

            self.assertEqual(_count_chunks_with_unclosed_code_fences(chunks), 1)

    def test_unclosed_tilde_fence_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            chunks = Path(tmp)
            (chunks / "part.md").write_text("~~~\ncode\n", encoding="utf-8")

            self.assertEqual(_count_chunks_with_unclosed_code_fences(chunks), 1)


if __name__ == "__main__":
    unittest.main()
