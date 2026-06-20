import unittest
from pathlib import Path

from kbprep_worker.diagnose.text_quality import analyze_text_quality, detect_text_profile
from kbprep_worker.quality.conversion_integrity import _source_text_layer_status
from kbprep_worker.text_profile_rules import load_text_profile_signals

ROOT = Path(__file__).resolve().parents[2]


class DiagnoseTextQualityBehaviorTests(unittest.TestCase):
    def test_normal_text_has_low_unreadable_ratio_and_detects_tutorial_profile(self):
        text = "\n".join(
            [
                "步骤1：打开 ExampleTool 后台，设置 threshold=0.8。",
                "步骤2：记录 retry_count=3 和 failure_reason=timeout。",
                "步骤3：复盘失败原因并保存配置。",
            ]
        )

        quality = analyze_text_quality(text)
        profile = detect_text_profile(text)

        self.assertLess(quality["unreadable_text_ratio"], 0.1)
        self.assertEqual(profile["text_profile"], "tutorial")

    def test_text_profile_terms_are_loaded_from_rules(self):
        signals = load_text_profile_signals()

        self.assertIn("tutorial", signals.tutorial_terms)
        self.assertEqual(detect_text_profile("Host: welcome\nGuest: hello")["text_profile"], "meeting_or_interview")

    def test_mojibake_text_has_high_unreadable_ratio(self):
        text = "ExampleTool姗欑毊涔︿粠鍏ラ棬鍒扮簿閫氾紝娑电洊鏋舵瀯鍘熺悊" * 8

        quality = analyze_text_quality(text)

        self.assertGreaterEqual(quality["unreadable_text_ratio"], 0.25)
        self.assertGreater(quality["mojibake_chars"], 0)

    def test_english_question_marks_are_not_replacement_garbling(self):
        text = "What is retrieval? How does ranking work? This paragraph is readable."

        quality = analyze_text_quality(text)

        self.assertEqual(quality["replacement_char_ratio"], 0.0)
        self.assertLess(quality["unreadable_text_ratio"], 0.05)

    def test_accented_english_text_is_readable_not_garbled(self):
        text = "café naïve résumé coöperate touché déjà vu " * 6

        quality = analyze_text_quality(text)

        self.assertEqual(quality["garbled_chars"], 0)
        self.assertLess(quality["unreadable_text_ratio"], 0.05)

    def test_common_symbols_are_not_character_garbling(self):
        text = "Status ★ passed; cost ≈ $12; value ≥ 90%; use arrows → for flow. " * 4

        quality = analyze_text_quality(text)

        self.assertEqual(quality["garbled_chars"], 0)
        self.assertLess(quality["unreadable_text_ratio"], 0.05)

    def test_abnormal_unicode_long_runs_are_garbled(self):
        text = "Ჭ䌦圳➉ᵜⰭ䕇✮⦽ " * 30

        quality = analyze_text_quality(text)

        self.assertGreater(quality["garbled_ratio"], 0.08)
        self.assertGreater(quality["unreadable_text_ratio"], 0.08)

    def test_mojibake_tokens_are_loaded_from_rules_not_worker_source(self):
        source = (ROOT / "python/kbprep_worker/diagnose/text_quality.py").read_text(encoding="utf-8")

        for token in ["姗欑毊", "鍏ラ棬", "MOJIBAKE_TOKEN_RE"]:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_rejected_pdf_text_layer_is_superseded_by_successful_ocr_conversion(self):
        layer = _source_text_layer_status(
            {
                "needs_ocr": True,
                "pdf_subtype": "garbled_text_layer",
                "text_quality": {"unreadable_text_ratio": 0.5},
            },
            {"converter": "mineru", "converted_bytes": 2048},
        )

        self.assertTrue(layer["superseded_by_conversion"])
        self.assertEqual(layer["converter"], "mineru")

    def test_unreadable_pdf_text_layer_without_ocr_remains_final_quality_failure(self):
        layer = _source_text_layer_status(
            {
                "needs_ocr": True,
                "pdf_subtype": "garbled_text_layer",
                "text_quality": {"unreadable_text_ratio": 0.5},
            },
            {"converter": "pdf_text_layer", "converted_bytes": 128},
        )

        self.assertFalse(layer["superseded_by_conversion"])
        self.assertEqual(layer["converter"], "pdf_text_layer")


if __name__ == "__main__":
    unittest.main()
