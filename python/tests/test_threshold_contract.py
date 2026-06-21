import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.quality.thresholds import (
    CLASSIFICATION_CONFIDENCE,
    DIAGNOSIS_THRESHOLDS,
    OBSIDIAN_CONFIDENCE,
    review_pack_low_confidence_threshold,
)
from kbprep_worker.stages.review_pack import _generate_review_pack


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

    def test_review_pack_low_confidence_threshold_defaults_to_existing_policy(self):
        self.assertEqual(review_pack_low_confidence_threshold(), 0.76)
        self.assertEqual(
            review_pack_low_confidence_threshold(source_quality="high", document_type="report"),
            0.76,
        )
        self.assertEqual(
            review_pack_low_confidence_threshold(source_quality="high", document_type="course"),
            0.76,
        )

    def test_low_quality_transcript_review_pack_uses_more_conservative_threshold(self):
        default = review_pack_low_confidence_threshold()
        transcript = review_pack_low_confidence_threshold(source_quality="low", document_type="transcript")
        unavailable = review_pack_low_confidence_threshold(source_quality="unavailable", document_type="transcript")
        self.assertGreaterEqual(transcript, default)
        self.assertGreater(transcript, default)
        self.assertGreaterEqual(unavailable, default)
        self.assertGreater(unavailable, default)

    def test_review_pack_uses_source_quality_and_document_type_threshold(self):
        blocks = [{
            "block_id": "low_conf_transcript",
            "type": "paragraph",
            "status": "keep",
            "risk_tags": [],
            "reason": "",
            "confidence": 0.78,
            "protected": False,
            "heading_path": [],
            "page_start": 1,
            "page_end": 1,
            "text": "字幕转写段落，置信度略高于默认阈值但仍需人工复核。",
        }]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _generate_review_pack(
                blocks,
                run_dir,
                "subtitle_transcript",
                source_quality="unavailable",
                document_type="transcript",
            )
            pack = (run_dir / "review_pack.json").read_text(encoding="utf-8")

        self.assertIn("low_conf_transcript", pack)

    def test_review_pack_includes_bounded_policy_context(self):
        blocks = [{
            "block_id": "review_course_intro",
            "type": "paragraph",
            "status": "review",
            "risk_tags": ["marketing_wrapper"],
            "reason": "possible wrapper before reusable lesson content",
            "confidence": 0.52,
            "protected": False,
            "heading_path": ["课程", "第一讲"],
            "page_start": 2,
            "page_end": 3,
            "text": "这段需要结合规则上下文判断是否只是包装话术。",
        }]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _generate_review_pack(
                blocks,
                run_dir,
                "markdown_note",
                source_quality="high",
                document_type="course",
                profile="curated_obsidian_kb",
                source_identity='{"source_domain":"example.com"}',
            )
            pack = json.loads((run_dir / "review_pack.json").read_text(encoding="utf-8"))

        policy = pack["policy_context"]
        self.assertEqual(policy["document_type"], "course")
        self.assertEqual(policy["profile"], "curated_obsidian_kb")
        self.assertLessEqual(len(policy["relevant_terms"]), 16)
        self.assertLessEqual(len(policy["protected_patterns"]), 16)
        self.assertTrue(policy["rule_sources"])
        self.assertTrue(any(item["label"] and item["pattern"] for item in policy["protected_patterns"]))
        self.assertEqual(pack["context_policy"]["neighbor_text"], "not_included")
        self.assertEqual(pack["blocks"][0]["heading_path"], ["课程", "第一讲"])
        self.assertEqual(pack["blocks"][0]["risk_tags"], ["marketing_wrapper"])
        self.assertEqual(pack["blocks"][0]["reason"], "possible wrapper before reusable lesson content")


if __name__ == "__main__":
    unittest.main()
