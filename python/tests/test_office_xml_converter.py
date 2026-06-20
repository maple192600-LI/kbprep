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


if __name__ == "__main__":
    unittest.main()
