import tempfile
import unittest
from pathlib import Path

from kbprep_worker.normalize import _fix_heading_levels, normalize


class NormalizeTests(unittest.TestCase):
    def test_heading_level_normalization_does_not_rewrite_legal_exported_jumps(self):
        text = "# Slide Deck\n\n#### Slide 1\n\nBody\n\n## Appendix\n"

        normalized, fixes = _fix_heading_levels(text)

        self.assertEqual(normalized, text)
        self.assertEqual(fixes, [])

    def test_normalize_keeps_jump_headings_without_reporting_heading_fixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = normalize("# Lesson\n\n#### Deep Export Heading\n\nBody", tmp)
            report = Path(tmp, "normalization_report.json").read_text(encoding="utf-8")

        self.assertIn("#### Deep Export Heading", result["normalized_text"])
        self.assertIn('"heading_fixes": 0', report)


if __name__ == "__main__":
    unittest.main()
