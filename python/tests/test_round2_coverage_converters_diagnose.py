import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.converters import html as html_mod
from kbprep_worker.converters import office_xml
from kbprep_worker.diagnose import pdf_analysis


class HtmlConverterRound2CoverageTests(unittest.TestCase):
    def test_rich_html_preserves_tables_cards_images_and_svg_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "site"
            source_root.mkdir()
            (source_root / "img.png").write_bytes(b"png")
            run_dir = root / "run"
            html = """
            <html><head><title>课程图谱</title><script>bad()</script></head>
            <body><main>
              <h1>标题</h1>
              <p>正文 <strong>重点</strong> <a href="https://example.com">链接</a></p>
              <div class="card"><h3>案例卡</h3><p>卡片正文</p></div>
              <table><tr><th>字段</th><th>值</th></tr><tr><td>a|b</td><td>1</td></tr></table>
              <img src="img.png" alt="图像">
              <svg viewbox="0 0 100 50"><title>流程图</title><rect width="100" height="50"/></svg>
            </main></body></html>
            """
            markdown = html_mod.html_to_markdown(html, run_dir=run_dir, source_stem="course", source_root=source_root)

            self.assertIn("# 标题", markdown)
            self.assertIn("重点", markdown)
            self.assertIn("[链接](https://example.com)", markdown)
            self.assertIn("案例卡", markdown)
            self.assertIn("字段", markdown)
            self.assertIn("a\\|b", markdown)
            self.assertIn("![图像]", markdown)
            self.assertNotIn("bad()", markdown)
            rich_markdown = html_mod.rich_html_to_markdown(
                html,
                run_dir=run_dir,
                source_stem="course",
                source_root=source_root,
            )
            if rich_markdown.strip():
                self.assertIn("**重点**", rich_markdown)
                self.assertIn("#### 案例卡", rich_markdown)
                self.assertIn("| 字段 | 值 |", rich_markdown)
                self.assertIn("a\\|b", rich_markdown)
                self.assertIn("![图像](images/img.png)", rich_markdown)
                self.assertIn("![流程图](images/", rich_markdown)
                self.assertTrue((run_dir / "images" / "img.png").exists())
                self.assertTrue(any(path.suffix == ".svg" for path in (run_dir / "images").iterdir()))

    def test_stdlib_html_parser_fallback_and_svg_helpers(self):
        html = "<h2>Title</h2><p>Body <a href='https://x.test'>X</a></p><ul><li>One</li></ul><script>bad</script>"
        with patch("builtins.__import__", side_effect=ImportError("no bs4")):
            markdown = html_mod.html_to_markdown(html)
        self.assertIn("## Title", markdown)
        self.assertIn("[X](https://x.test)", markdown)
        self.assertIn("- One", markdown)
        self.assertNotIn("bad", markdown)
        malformed_heading = "<h1>Unclosed title<p>Body after heading</p>"
        with patch("builtins.__import__", side_effect=ImportError("no bs4")):
            malformed = html_mod.html_to_markdown(malformed_heading)
        self.assertIn("# Unclosed title", malformed)
        self.assertIn("Body after heading", malformed)
        self.assertEqual(html_mod._parse_svg_view_box("0 0 10 20"), (0.0, 0.0, 10.0, 20.0))
        self.assertIsNone(html_mod._parse_svg_view_box("0 0 -1 20"))
        self.assertEqual(html_mod._format_svg_number(3.0), "3")
        self.assertEqual(html_mod._escape_table_cell("a|b\nc"), "a\\|b c")


class OfficeXmlRound2CoverageTests(unittest.TestCase):
    def _zip(self, path: Path, files: dict[str, str | bytes]) -> None:
        with zipfile.ZipFile(path, "w") as zf:
            for name, content in files.items():
                if isinstance(content, bytes):
                    zf.writestr(name, content)
                else:
                    zf.writestr(name, content.encode("utf-8"))

    def test_docx_pptx_and_xlsx_extract_readable_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            docx = root / "sample.docx"
            self._zip(docx, {
                "word/document.xml": """
                <w:document xmlns:w="w"><w:body>
                  <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>标题</w:t></w:r></w:p>
                  <w:p><w:r><w:t>正文</w:t></w:r></w:p>
                  <w:tbl><w:tr><w:tc><w:p><w:r><w:t>字段</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>值</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
                  <w:p><w:r><w:drawing><a:blip xmlns:a="a" r:embed="rId1" xmlns:r="r"/></w:drawing></w:r></w:p>
                </w:body></w:document>
                """,
                "word/_rels/document.xml.rels": "<Relationships><Relationship Id='rId1' Target='media/image1.png'/></Relationships>",
                "word/media/image1.png": b"png",
            })
            docx_md, warnings, artifacts = office_xml.office_xml_to_markdown(docx, run_dir)
            self.assertIn("# 标题", docx_md)
            self.assertIn("| 字段 | 值 |", docx_md)
            self.assertEqual(artifacts["office_image_assets"]["copied_count"], 1)
            self.assertTrue(warnings)

            pptx = root / "deck.pptx"
            self._zip(pptx, {
                "ppt/slides/slide1.xml": "<p:sld xmlns:p='p' xmlns:a='a' xmlns:r='r'><a:p><a:r><a:t>Slide Title</a:t></a:r></a:p><a:p><a:r><a:t>Body</a:t></a:r></a:p><a:blip r:embed='rId1'/></p:sld>",  # noqa: E501
                "ppt/slides/_rels/slide1.xml.rels": "<Relationships><Relationship Id='rId1' Target='../media/image1.png'/></Relationships>",
                "ppt/media/image1.png": b"png",
                "ppt/notesSlides/notesSlide1.xml": "<p:notes xmlns:p='p' xmlns:a='a'><a:p><a:r><a:t>Speaker note</a:t></a:r></a:p></p:notes>",  # noqa: E501
            })
            pptx_md, _, pptx_artifacts = office_xml.office_xml_to_markdown(pptx, run_dir)
            self.assertIn("# Slide 1: Slide Title", pptx_md)
            self.assertIn("## Slide 1 Notes", pptx_md)
            self.assertEqual(pptx_artifacts["office_image_assets"]["copied_count"], 1)
            content_list = office_xml.write_pptx_content_list(pptx_md, run_dir)
            self.assertTrue(Path(content_list["content_list_path"]).exists())

            xlsx = root / "book.xlsx"
            self._zip(xlsx, {
                "xl/workbook.xml": "<workbook><sheets><sheet name='Data'/></sheets></workbook>",
                "xl/sharedStrings.xml": "<sst><si><t>Name</t></si><si><t>Alice</t></si></sst>",
                "xl/worksheets/sheet1.xml": "<worksheet><sheetData><row><c t='s'><v>0</v></c><c><v>Score</v></c></row><row><c t='s'><v>1</v></c><c><v>9</v></c></row></sheetData></worksheet>",  # noqa: E501
            })
            xlsx_md, _, _ = office_xml.office_xml_to_markdown(xlsx, run_dir)
            self.assertIn("# Data", xlsx_md)
            self.assertIn("| Name | Score |", xlsx_md)

    def test_office_xml_errors_and_cell_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = root / "bad.docx"
            bad.write_text("not zip", encoding="utf-8")
            with self.assertRaises(office_xml.OfficeXmlConversionError) as raised:
                office_xml.office_xml_to_markdown(bad, root)
            self.assertEqual(raised.exception.code, "E_CONVERT_INPUT_INVALID")
            self.assertEqual(office_xml.rows_to_markdown_table([]), "")


class PdfAnalysisRound2CoverageTests(unittest.TestCase):
    class _Rect:
        def __init__(self, width: int, height: int):
            self.width = width
            self.height = height

    class _Page:
        def __init__(self, text: str, images: list[tuple], width: int = 800, height: int = 600):
            self._text = text
            self._images = images
            self.rect = PdfAnalysisRound2CoverageTests._Rect(width, height)

        def get_text(self, kind: str) -> str:
            return self._text

        def get_images(self, full: bool = True) -> list[tuple]:
            return self._images

    class _Doc:
        def __init__(self, pages):
            self.pages = pages
            self.closed = False

        def __len__(self):
            return len(self.pages)

        def __getitem__(self, index):
            return self.pages[index]

        def close(self):
            self.closed = True

    def test_pdf_analysis_classifies_text_image_and_slide_profiles(self):
        pages = [
            self._Page("第一章 内容\n步骤1：设置 threshold=0.8", [(1,)], width=1200, height=700),
            self._Page("", [(1,)], width=1200, height=700),
            self._Page("第二章 内容", [(1,)], width=1200, height=700),
        ]
        fake_doc = self._Doc(pages)
        fake_fitz = types.SimpleNamespace(open=lambda path: fake_doc)
        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            result = pdf_analysis.analyze_pdf("sample.pdf")

        self.assertEqual(result["page_count"], 3)
        self.assertEqual(result["image_pages"], 1)
        self.assertIn(result["layout_profile"], {"slide_deck_or_ppt_export", "landscape_report"})
        self.assertEqual(result["conversion_strategy"], "mineru_auto")
        self.assertTrue(fake_doc.closed)

    def test_pdf_analysis_handles_missing_pymupdf_and_errors(self):
        with patch.dict(sys.modules, {"fitz": None}):
            result = pdf_analysis.analyze_pdf("missing.pdf")
        self.assertEqual(result["text_layer_health"], "unavailable")
        self.assertTrue(result["warnings"])

        fake_fitz = types.SimpleNamespace(open=lambda path: (_ for _ in ()).throw(RuntimeError("boom")))
        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            errored = pdf_analysis.analyze_pdf("bad.pdf")
        self.assertEqual(errored["text_layer_health"], "error")

    def test_pdf_analysis_closes_document_when_page_read_fails(self):
        class FailingPage(self._Page):
            def get_text(self, kind: str) -> str:
                raise RuntimeError("page failed")

        fake_doc = self._Doc([FailingPage("", [])])
        fake_fitz = types.SimpleNamespace(open=lambda path: fake_doc)

        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            errored = pdf_analysis.analyze_pdf("bad-page.pdf")

        self.assertEqual(errored["text_layer_health"], "error")
        self.assertTrue(fake_doc.closed)

    def test_pdf_assessment_helpers_cover_bad_text_and_image_ratios(self):
        result = pdf_analysis._initial_pdf_result()
        result.update({"page_count": 10, "average_text_chars_per_text_page": 100})
        warnings: list[str] = []
        pdf_analysis._apply_text_layer_assessment(
            result,
            {
                "garbled_ratio": 0.0,
                "chinese_ratio": 0.0,
                "alnum_ratio": 0.7,
                "mojibake_ratio": 0.0,
                "unreadable_text_ratio": 0.0,
            },
            image_pages=0,
            text_pages=10,
            language="en",
            warnings=warnings,
        )
        self.assertEqual(result["text_layer_health"], "good")

        pdf_analysis._apply_image_ratio_assessment(result, image_pages=9, text_pages=1, warnings=warnings)
        pdf_analysis._append_ocr_confusion_warning({"ocr_ai_confusion_count": 2}, warnings)
        pdf_analysis._apply_pdf_layout_profile(result, image_pages=9, text_pages=1, image_count=10, landscape_pages=9)
        pdf_analysis._apply_pdf_processing_strategy(result)
        self.assertTrue(result["needs_ocr"])
        self.assertEqual(result["conversion_strategy"], "mineru_ocr")
        self.assertTrue(any("OCR" in item or "ocr" in item for item in result["processing_hints"]))

    def test_pdf_processing_routes_simple_trusted_text_layer_to_lightweight_converter(self):
        result = pdf_analysis._initial_pdf_result()
        result.update({
            "page_count": 8,
            "average_text_chars_per_text_page": 1200,
            "pdf_subtype": "text_layer",
            "text_layer_health": "good",
        })

        pdf_analysis._apply_pdf_layout_profile(result, image_pages=0, text_pages=8, image_count=0, landscape_pages=0)
        pdf_analysis._apply_pdf_processing_strategy(result)

        self.assertEqual(result["layout_complexity"], "simple")
        self.assertEqual(result["conversion_strategy"], "pdf_text_layer")


if __name__ == "__main__":
    unittest.main()
