import unittest

from kbprep_worker.quality.thresholds import (
    CLASSIFICATION_CONFIDENCE,
    DIAGNOSIS_THRESHOLDS,
    OBSIDIAN_CONFIDENCE,
)


class ThresholdContractTests(unittest.TestCase):
    def test_classification_confidence_names_business_decisions(self):
        self.assertEqual(CLASSIFICATION_CONFIDENCE["marketing_wrapper_discard"], 0.96)
        self.assertEqual(CLASSIFICATION_CONFIDENCE["default_keep"], 0.70)

    def test_diagnosis_threshold_names_pdf_quality_decisions(self):
        self.assertEqual(DIAGNOSIS_THRESHOLDS["pdf_unreadable_text_layer"], 0.25)
        self.assertEqual(DIAGNOSIS_THRESHOLDS["pdf_slide_like_score"], 0.65)

    def test_obsidian_confidence_names_curation_decisions(self):
        self.assertEqual(OBSIDIAN_CONFIDENCE["drop_internal_page_marker"], 0.99)
        self.assertEqual(OBSIDIAN_CONFIDENCE["author_intro_review"], 0.60)


if __name__ == "__main__":
    unittest.main()
