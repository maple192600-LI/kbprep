import tempfile
import unittest
import zipfile
from pathlib import Path

from kbprep_worker.converters.office_xml import (
    OfficeXmlConversionError,
    office_xml_to_markdown,
    write_pptx_content_list,
)


class OfficeXmlConverterTests(unittest.TestCase):
    def test_xlsx_to_markdown_extracts_shared_strings_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "params.xlsx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("[Content_Types].xml", "<Types/>")
                zf.writestr(
                    "xl/workbook.xml",
                    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    '<sheets><sheet name="Params" sheetId="1"/></sheets></workbook>',
                )
                zf.writestr(
                    "xl/sharedStrings.xml",
                    '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    "<si><t>Name</t></si><si><t>Value</t></si><si><t>threshold</t></si><si><t>0.8</t></si></sst>",
                )
                zf.writestr(
                    "xl/worksheets/sheet1.xml",
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                    '<row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row>'
                    '<row><c t="s"><v>2</v></c><c t="s"><v>3</v></c></row>'
                    "</sheetData></worksheet>",
                )

            markdown, warnings, artifacts = office_xml_to_markdown(path, Path(tmp, "run"))

        self.assertIn("# Params", markdown)
        self.assertIn("| threshold | 0.8 |", markdown)
        self.assertTrue(warnings)
        self.assertEqual(artifacts["office_image_assets"]["copied_count"], 0)

    def test_invalid_office_zip_raises_structured_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "broken.docx")
            path.write_text("not a zip", encoding="utf-8")

            with self.assertRaises(OfficeXmlConversionError) as raised:
                office_xml_to_markdown(path, Path(tmp, "run"))

        self.assertEqual(raised.exception.code, "E_CONVERT_INPUT_INVALID")

    def test_write_pptx_content_list_records_slide_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            result = write_pptx_content_list("# Slide 1: Intro\n\nA\n\n# Slide 2: Case\n\nB\n", run_dir)

            content = Path(result["content_list_path"]).read_text(encoding="utf-8")

        self.assertIn('"page_idx": 0', content)
        self.assertIn('"page_idx": 1', content)

    def test_pptx_native_source_spans_record_shape_id_and_line_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "deck.pptx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("ppt/slides/slide1.xml", (
                    "<p:sld xmlns:p='p' xmlns:a='a' xmlns:r='r'>"
                    "<p:cSld><p:spTree>"
                    "<p:sp>"
                    "<p:nvSpPr><p:cNvPr id='2' name='Title 1'/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
                    "<p:spPr/>"
                    "<p:txBody><a:p><a:r><a:t>Slide Title</a:t></a:r></a:p></p:txBody>"
                    "</p:sp>"
                    "<p:sp>"
                    "<p:nvSpPr><p:cNvPr id='3' name='Content 2'/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
                    "<p:spPr/>"
                    "<p:txBody><a:p><a:r><a:t>Body content</a:t></a:r></a:p></p:txBody>"
                    "</p:sp>"
                    "</p:spTree></p:cSld>"
                    "</p:sld>"
                ))
            markdown, _warnings, artifacts = office_xml_to_markdown(path, run_dir)
            native = artifacts.get("native_source_spans", [])

        self.assertIn("# Slide 1: Slide Title", markdown)
        self.assertIn("Body content", markdown)
        self.assertEqual(len(native), 2)
        self.assertEqual([entry["precision"] for entry in native], ["pptx_shape", "pptx_shape"])
        self.assertEqual(native[0]["location"]["slide"], 1)
        self.assertEqual(native[0]["location"]["shape_id"], "2")
        self.assertEqual(native[0]["converted_line_start"], 1)
        self.assertEqual(native[0]["converted_line_end"], 1)
        self.assertEqual(native[1]["location"]["shape_id"], "3")
        self.assertEqual(native[1]["converted_line_start"], 3)
        self.assertEqual(native[1]["converted_line_end"], 3)

    def test_pptx_without_shape_wrappers_falls_back_to_paragraph_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "flat.pptx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("ppt/slides/slide1.xml", (
                    "<p:sld xmlns:p='p' xmlns:a='a' xmlns:r='r'>"
                    "<a:p><a:r><a:t>Flat Title</a:t></a:r></a:p>"
                    "<a:p><a:r><a:t>Flat Body</a:t></a:r></a:p>"
                    "</p:sld>"
                ))
            markdown, _warnings, artifacts = office_xml_to_markdown(path, run_dir)
            native = artifacts.get("native_source_spans", [])

        self.assertIn("# Slide 1: Flat Title", markdown)
        self.assertIn("Flat Body", markdown)
        self.assertEqual(native, [])


if __name__ == "__main__":
    unittest.main()
