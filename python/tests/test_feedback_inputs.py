import unittest

from kbprep_worker.feedback.support import _matches_feedback_intent


class FeedbackInputBehaviorTests(unittest.TestCase):
    def test_feedback_intent_terms_are_literal_not_regex(self):
        terms = ("删[掉]", "protect+keep?", "remove(this)")

        self.assertFalse(_matches_feedback_intent("请删除这段污染", terms))
        self.assertFalse(_matches_feedback_intent("protect keep this body paragraph", terms))
        self.assertFalse(_matches_feedback_intent("remove this paragraph", terms))
        self.assertTrue(_matches_feedback_intent("请删[掉]这个字面标记", terms))
        self.assertTrue(_matches_feedback_intent("protect+keep? appears literally", terms))
        self.assertTrue(_matches_feedback_intent("remove(this) appears literally", terms))


if __name__ == "__main__":
    unittest.main()
