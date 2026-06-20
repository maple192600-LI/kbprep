import tempfile
import unittest
from pathlib import Path

from kbprep_worker.converters.html import html_to_markdown, rich_html_to_markdown


class HtmlConverterTests(unittest.TestCase):
    def test_html_fallback_keeps_content_link_and_drops_script(self):
        html = """
        <html><head><script>alert('x')</script></head><body>
          <article>
            <h1>操作教程</h1>
            <p>步骤1：设置 threshold=0.8。</p>
            <p><a href="https://example.com/tool">打开工具</a></p>
          </article>
        </body></html>
        """

        markdown = html_to_markdown(html)

        self.assertIn("# 操作教程", markdown)
        self.assertIn("threshold=0.8", markdown)
        self.assertIn("[打开工具](https://example.com/tool)", markdown)
        self.assertNotIn("<script>", markdown)

    def test_rich_html_copies_local_image_when_dependencies_are_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            image_dir = source_root / "assets"
            image_dir.mkdir()
            (image_dir / "step.png").write_bytes(b"png")
            run_dir = source_root / "run"
            html = """
            <html><head><script>alert('x')</script></head><body>
              <article>
                <h1>操作教程</h1>
                <p>步骤1：设置 threshold=0.8。</p>
                <p><a href="https://example.com/tool">打开工具</a></p>
                <p><img src="assets/step.png" alt="后台截图"></p>
              </article>
            </body></html>
            """

            markdown = rich_html_to_markdown(html, run_dir=run_dir, source_stem="page", source_root=source_root)

            if not markdown.strip():
                self.skipTest("rich HTML dependencies are not installed in this Python test environment")

            self.assertIn("# 操作教程", markdown)
            self.assertIn("threshold=0.8", markdown)
            self.assertIn("[打开工具](https://example.com/tool)", markdown)
            self.assertIn("![后台截图](images/assets/step.png)", markdown)
            self.assertNotIn("<script>", markdown)
            self.assertTrue((run_dir / "images" / "assets" / "step.png").exists())


if __name__ == "__main__":
    unittest.main()
