import unittest

from kbprep_worker.epub import html_to_markdown


class EpubConverterTests(unittest.TestCase):
    def test_html_to_markdown_handles_malformed_epub_html_with_links_and_lists(self):
        html = """
        <html><body>
          <h1>第一章
          <p>步骤：打开 <a href="https://example.com">工具</a>
          <ul><li>保留要点</li></ul>
          <script>noise()</script>
        </body></html>
        """

        markdown = html_to_markdown(html)

        self.assertIn("# 第一章", markdown)
        self.assertIn("[工具](https://example.com)", markdown)
        self.assertIn("- 保留要点", markdown)
        self.assertNotIn("noise", markdown)

    def test_html_to_markdown_preserves_epub_block_structures(self):
        html = """
        <html><body>
          <h2>Method</h2>
          <p>Line one<br/>Line two</p>
          <blockquote>Risk note</blockquote>
          <pre><code>if failure_reason == "timeout":
              retry_count = 3</code></pre>
          <table>
            <tr><th>Field</th><th>Value</th></tr>
            <tr><td>a|b</td><td>1</td></tr>
          </table>
          <ol><li>First step<ul><li>Nested detail</li></ul></li></ol>
        </body></html>
        """

        markdown = html_to_markdown(html)

        self.assertIn("## Method", markdown)
        self.assertIn("Line one", markdown)
        self.assertIn("Line two", markdown)
        self.assertIn("> Risk note", markdown)
        self.assertIn("failure_reason", markdown)
        self.assertIn("retry_count", markdown)
        self.assertIn("| Field | Value |", markdown)
        self.assertIn("a\\|b", markdown)
        self.assertIn("1. First step", markdown)
        self.assertIn("Nested detail", markdown)

    def test_anchor_footnotes_render_as_markdown_footnotes(self):
        html = """
        <html><body>
          <h1>Chapter</h1>
          <p>Some claim<a href="#fn1" id="ref1">[1]</a> here.</p>
          <p>Another point<a href="#fn2">[2]</a> follows.</p>
          <div class="footnotes">
            <p id="fn1">First footnote detail.</p>
            <p id="fn2">Second note text.</p>
          </div>
        </body></html>
        """
        markdown = html_to_markdown(html)

        self.assertIn("[^1]", markdown)
        self.assertIn("[^2]", markdown)
        self.assertIn("[^1]: First footnote detail.", markdown)
        self.assertIn("[^2]: Second note text.", markdown)
        body_before_notes = markdown.split("[^1]:")[0]
        self.assertNotIn("First footnote detail.", body_before_notes)

    def test_complex_table_expands_colspan_and_rowspan(self):
        html = """
        <html><body>
          <table>
            <tr><th>A</th><th>B</th><th>C</th></tr>
            <tr><td colspan="2">merged-ab</td><td>c2</td></tr>
            <tr><td>a3</td><td rowspan="2">merged-b</td><td>c3</td></tr>
            <tr><td>a4</td><td>c4</td></tr>
          </table>
        </body></html>
        """
        markdown = html_to_markdown(html)

        lines = [ln for ln in markdown.splitlines() if ln.strip().startswith("|")]
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], "| A | B | C |")
        self.assertEqual(lines[2], "| merged-ab | merged-ab | c2 |")
        self.assertEqual(lines[3], "| a3 | merged-b | c3 |")
        self.assertEqual(lines[4], "| a4 | merged-b | c4 |")

    def test_epub_type_noteref_and_footnote_render_as_markdown_footnotes(self):
        html = """
        <html><body>
          <h1>Chapter</h1>
          <p>Some claim<a href="#fn1" epub:type="noteref">1</a> here.</p>
          <aside epub:type="footnote" id="fn1"><p>First EPUB3 footnote detail.</p></aside>
        </body></html>
        """
        markdown = html_to_markdown(html)

        self.assertIn("[^1]", markdown)
        self.assertIn("[^1]: First EPUB3 footnote detail.", markdown)
        body_before_notes = markdown.split("[^1]:")[0]
        self.assertNotIn("First EPUB3 footnote detail.", body_before_notes)


if __name__ == "__main__":
    unittest.main()
