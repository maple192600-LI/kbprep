import tempfile
import unittest
from pathlib import Path

from kbprep_worker.feedback import _append_jsonl_locked, run
from kbprep_worker.feedback.promotion_history import _promotion_history_document_summary
from kbprep_worker.feedback.proposals import _validate_proposal_acceptance
from kbprep_worker.feedback.support import _matches_pattern, _read_jsonl


class FeedbackPackageBoundaryTests(unittest.TestCase):
    def test_public_compatibility_exports_still_work(self):
        self.assertTrue(callable(run))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "rules.jsonl")
            _append_jsonl_locked(path, {"id": "one"})
            self.assertEqual(_read_jsonl(path)[0]["id"], "one")

    def test_proposal_pattern_helpers_remain_importable(self):
        validation = _validate_proposal_acceptance({
            "pattern": "关注公众号",
            "match": "literal",
            "examples": ["关注公众号领取资料"],
            "counterexamples": ["正文案例：关注公众号是渠道字段"],
        })

        self.assertTrue(_matches_pattern("请关注公众号领取资料", "关注公众号", "literal"))
        self.assertFalse(validation["ok"])
        self.assertEqual(validation["counterexample_matches"], ["正文案例：关注公众号是渠道字段"])

    def test_scope_and_promotion_history_helpers_remain_importable(self):
        history = _promotion_history_document_summary("course", [
            {
                "schema": "kbprep.dictionary_promotion_history.v1",
                "created_at": "2026-06-01T00:00:00Z",
                "document_type": "course",
                "promoted_count": 1,
                "regression_verification": {
                    "status": "passed",
                    "sample_count": 1,
                    "passed_count": 1,
                    "failed_count": 0,
                    "samples": [{"ok": True}],
                },
            }
        ])

        self.assertEqual(history["latest_status"], "passed")
        self.assertEqual(history["last_failure_reason"], "")


if __name__ == "__main__":
    unittest.main()
