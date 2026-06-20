import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.feedback import _append_jsonl_locked


class FeedbackTests(unittest.TestCase):
    def test_locked_jsonl_append_writes_complete_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "proposed_rules.jsonl")

            _append_jsonl_locked(path, {"id": "one", "text": "第一条"})
            _append_jsonl_locked(path, {"id": "two", "text": "第二条"})

            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual([json.loads(line)["id"] for line in lines], ["one", "two"])

    def test_locked_jsonl_append_uses_separate_lock_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "accepted_rules.jsonl")

            _append_jsonl_locked(path, {"id": "accepted"})

            self.assertTrue(path.exists())
            self.assertTrue(Path(tmp, "accepted_rules.jsonl.lock").exists())


if __name__ == "__main__":
    unittest.main()
