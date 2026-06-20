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


if __name__ == "__main__":
    unittest.main()
