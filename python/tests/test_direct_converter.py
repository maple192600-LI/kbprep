import tempfile
import unittest
from pathlib import Path

from kbprep_worker.converters.direct import (
    code_to_markdown,
    delimited_to_markdown,
    json_to_markdown,
    normalize_subtitle_transcript,
    read_direct_source,
)


class DirectConverterTests(unittest.TestCase):
    def test_json_to_markdown_pretty_prints_valid_json(self):
        markdown = json_to_markdown('{"name":"KBPrep","value":1}')

        self.assertIn('  "name": "KBPrep"', markdown)
        self.assertTrue(markdown.startswith("```json\n"))

    def test_delimited_to_markdown_escapes_table_pipes(self):
        markdown = delimited_to_markdown("name,value\nA,one|two\n", ",")

        self.assertIn("| A | one\\|two |", markdown)

    def test_subtitle_transcript_removes_timing_lines(self):
        markdown = normalize_subtitle_transcript("WEBVTT\n\n1\n00:00:01 --> 00:00:02\nHello\n")

        self.assertIn("# Transcript", markdown)
        self.assertIn("Hello", markdown)
        self.assertNotIn("-->", markdown)

    def test_code_to_markdown_expands_fence_when_body_contains_backticks(self):
        markdown = code_to_markdown("print('x')\n```\n", ".py")

        self.assertTrue(markdown.startswith("````python\n"))
        self.assertTrue(markdown.endswith("\n````\n"))

    def test_read_direct_source_uses_injected_html_converter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "page.html")
            path.write_text("<h1>Hello</h1>", encoding="utf-8")

            text = read_direct_source(
                path,
                run_dir=Path(tmp, "run"),
                html_converter=lambda html, run_dir, source_stem, source_root: f"{source_stem}:{html}",
            )

        self.assertEqual(text, "page:<h1>Hello</h1>")


if __name__ == "__main__":
    unittest.main()
