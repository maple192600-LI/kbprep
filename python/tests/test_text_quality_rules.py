import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.text_quality_rules import load_text_quality_signals


class TextQualityRulesTests(unittest.TestCase):
    def tearDown(self) -> None:
        load_text_quality_signals.cache_clear()

    def test_builtin_text_quality_signals_load_and_match_mojibake(self):
        signals = load_text_quality_signals()

        self.assertIsNotNone(signals.mojibake_sequence_re.search("鐩綍绔"))
        self.assertIsNotNone(signals.mojibake_token_re.search("姗欑毊"))
        self.assertIsNotNone(signals.ocr_ai_confusion_re.search("All in Al"))

    def test_bad_regex_in_text_quality_rules_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules_root = Path(tmp)
            base = rules_root / "base"
            base.mkdir()
            (base / "text_quality_signals.json").write_text(
                json.dumps(
                    {
                        "schema": "kbprep.text_quality_signals.v1",
                        "abnormal_unicode_sequence_pattern": "[\\u10A0-\\u10FF]{2,}",
                        "mojibake_sequence_pattern": "[",
                        "mojibake_character_pattern": "�",
                        "mojibake_tokens": ["姗欑毊"],
                        "ocr_ai_confusion_patterns": ["All in Al"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"KBPREP_RULES_ROOT": str(rules_root)}):
                load_text_quality_signals.cache_clear()
                with self.assertRaises(ValueError):
                    load_text_quality_signals()

    def test_rules_root_override_without_text_quality_file_falls_back_to_builtin(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"KBPREP_RULES_ROOT": tmp}):
                load_text_quality_signals.cache_clear()
                signals = load_text_quality_signals()

        self.assertIsNotNone(signals.mojibake_token_re.search("姗欑毊"))


if __name__ == "__main__":
    unittest.main()
