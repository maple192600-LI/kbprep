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

    def test_docx_native_source_spans_record_paragraph_and_run_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "doc.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
                    '<w:r><w:t>Heading text</w:t></w:r></w:p>'
                    '<w:p><w:r><w:t>First run</w:t></w:r>'
                    '<w:r><w:t>Second run</w:t></w:r></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _warnings, artifacts = office_xml_to_markdown(path, run_dir)
            native = artifacts.get("native_source_spans", [])

        self.assertIn("# Heading text", markdown)
        self.assertEqual(len(native), 2)
        self.assertEqual([entry["precision"] for entry in native], ["docx_run_range", "docx_run_range"])
        self.assertEqual(native[0]["location"]["paragraph_index"], 0)
        self.assertEqual(native[0]["location"]["run_start"], 0)
        self.assertEqual(native[0]["location"]["run_end"], 0)
        self.assertEqual(native[0]["converted_line_start"], 1)
        self.assertEqual(native[0]["converted_line_end"], 1)
        self.assertEqual(native[1]["location"]["paragraph_index"], 1)
        self.assertEqual(native[1]["location"]["run_start"], 0)
        self.assertEqual(native[1]["location"]["run_end"], 1)
        self.assertEqual(native[1]["converted_line_start"], 3)
        self.assertEqual(native[1]["converted_line_end"], 3)

    def test_xlsx_native_source_spans_record_cell_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "book.xlsx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr(
                    "xl/workbook.xml",
                    '<workbook xmlns="main"><sheets><sheet name="Data" sheetId="1"/></sheets></workbook>',
                )
                zf.writestr(
                    "xl/sharedStrings.xml",
                    '<sst xmlns="main"><si><t>Name</t></si><si><t>Score</t></si><si><t>Alice</t></si></sst>',
                )
                zf.writestr(
                    "xl/worksheets/sheet1.xml",
                    '<worksheet xmlns="main"><sheetData>'
                    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                    '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>9</v></c></row>'
                    '</sheetData></worksheet>',
                )
            markdown, _warnings, artifacts = office_xml_to_markdown(path, run_dir)
            native = artifacts.get("native_source_spans", [])

        self.assertIn("# Data", markdown)
        self.assertIn("| Alice | 9 |", markdown)
        self.assertEqual(len(native), 1)
        self.assertEqual(native[0]["precision"], "xlsx_cell_range")
        self.assertEqual(native[0]["location"]["sheet"], "Data")
        self.assertEqual(native[0]["location"]["start"], "A1")
        self.assertEqual(native[0]["location"]["end"], "B2")
        self.assertEqual(native[0]["converted_line_start"], 3)
        self.assertEqual(native[0]["converted_line_end"], 5)

    def test_docx_paragraph_without_runs_emits_no_native_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "bare.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:p><w:t>Bare text without run wrapper</w:t></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _warnings, artifacts = office_xml_to_markdown(path, run_dir)
            native = artifacts.get("native_source_spans", [])

        self.assertIn("Bare text without run wrapper", markdown)
        self.assertEqual(native, [])

    def test_xlsx_cells_without_refs_emit_no_native_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "noref.xlsx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr(
                    "xl/workbook.xml",
                    '<workbook xmlns="main"><sheets><sheet name="Data" sheetId="1"/></sheets></workbook>',
                )
                zf.writestr(
                    "xl/sharedStrings.xml",
                    '<sst xmlns="main"><si><t>Name</t></si><si><t>Value</t></si></sst>',
                )
                zf.writestr(
                    "xl/worksheets/sheet1.xml",
                    '<worksheet xmlns="main"><sheetData>'
                    '<row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row>'
                    '</sheetData></worksheet>',
                )
            markdown, _warnings, artifacts = office_xml_to_markdown(path, run_dir)
            native = artifacts.get("native_source_spans", [])

        self.assertIn("| Name | Value |", markdown)
        self.assertEqual(native, [])

    # --- DOCX structure deepening (format-strategy priority target) ---

    def test_docx_external_hyperlink_resolves_uri_from_rels(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "link.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/_rels/document.xml.rels", (
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId7" Type="hyperlink" Target="https://example.com/guide" TargetMode="External"/>'
                    '</Relationships>'
                ))
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w" xmlns:r="r"><w:body>'
                    '<w:p><w:hyperlink r:id="rId7"><w:r><w:t>Read the guide</w:t></w:r></w:hyperlink></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("[Read the guide](https://example.com/guide)", markdown)

    def test_docx_anchor_hyperlink_uses_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "anchor.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:p><w:hyperlink w:anchor="section1"><w:r><w:t>jump</w:t></w:r></w:hyperlink></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("[jump](#section1)", markdown)

    def test_docx_hyperlink_without_matching_rel_keeps_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "broken_link.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w" xmlns:r="r"><w:body>'
                    '<w:p><w:hyperlink r:id="rIdMissing"><w:r><w:t>orphan link</w:t></w:r></w:hyperlink></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("orphan link", markdown)
        self.assertNotIn("]()", markdown)

    def test_docx_bold_and_italic_runs_emit_markdown_emphasis(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "styled.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:p>'
                    '<w:r><w:rPr><w:b/></w:rPr><w:t>Bold word</w:t></w:r>'
                    '<w:r><w:t> and </w:t></w:r>'
                    '<w:r><w:rPr><w:i/></w:rPr><w:t>italic word</w:t></w:r>'
                    '</w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("**Bold word**", markdown)
        self.assertIn("*italic word*", markdown)

    def test_docx_bold_with_val_false_is_not_emphasized(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "valfalse.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:p><w:r><w:rPr><w:b w:val="false"/></w:rPr><w:t>plain</w:t></w:r></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("plain", markdown)
        self.assertNotIn("**", markdown)

    def test_docx_strike_run_emits_strikethrough(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "strike.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:p><w:r><w:rPr><w:strike/></w:rPr><w:t>deleted</w:t></w:r></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("~~deleted~~", markdown)

    def test_docx_unordered_list_emits_bullet_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "ulist.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/numbering.xml", (
                    '<w:numbering xmlns:w="w">'
                    '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>'
                    '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
                    '</w:numbering>'
                ))
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
                    '<w:r><w:t>First bullet</w:t></w:r></w:p>'
                    '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
                    '<w:r><w:t>Second bullet</w:t></w:r></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("- First bullet", markdown)
        self.assertIn("- Second bullet", markdown)

    def test_docx_ordered_list_emits_decimal_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "olist.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/numbering.xml", (
                    '<w:numbering xmlns:w="w">'
                    '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum>'
                    '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
                    '</w:numbering>'
                ))
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr>'
                    '<w:r><w:t>First step</w:t></w:r></w:p>'
                    '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr>'
                    '<w:r><w:t>Second step</w:t></w:r></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("1. First step", markdown)
        self.assertIn("2. Second step", markdown)

    def test_docx_list_paragraph_without_numbering_part_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "dangling_list.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="9"/></w:numPr></w:pPr>'
                    '<w:r><w:t>Dangling item</w:t></w:r></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        # No numbering.xml: must not raise, must not fabricate list markers.
        self.assertIn("Dangling item", markdown)
        self.assertNotIn("- Dangling", markdown)
        self.assertNotIn("1. Dangling", markdown)

    def test_docx_gridspan_repeats_value_across_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "gridspan.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:tbl><w:tr>'
                    '<w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>Merged</w:t></w:r></w:p></w:tc>'
                    '</w:tr></w:tbl>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("| Merged | Merged |", markdown)

    def test_docx_vmerge_continue_filled_from_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "vmerge.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:tbl>'
                    '<w:tr>'
                    '<w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>Top</w:t></w:r></w:p></w:tc>'
                    '<w:tc><w:p><w:r><w:t>Right1</w:t></w:r></w:p></w:tc>'
                    '</w:tr>'
                    '<w:tr>'
                    '<w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p><w:r><w:t></w:t></w:r></w:p></w:tc>'
                    '<w:tc><w:p><w:r><w:t>Right2</w:t></w:r></w:p></w:tc>'
                    '</w:tr>'
                    '</w:tbl>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        # vMerge continue cell must be filled with the restart value "Top".
        self.assertIn("| Top | Right2 |", markdown)

    def test_docx_corrupt_numbering_xml_degrades_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "bad_numbering.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/numbering.xml", "<<not valid xml>>")
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w"><w:body>'
                    '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
                    '<w:r><w:t>Still readable</w:t></w:r></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("Still readable", markdown)
        self.assertNotIn("- Still readable", markdown)

    def test_docx_corrupt_rels_degrades_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "bad_rels.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/_rels/document.xml.rels", "<<not valid xml>>")
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w" xmlns:r="r"><w:body>'
                    '<w:p><w:hyperlink r:id="rId7"><w:r><w:t>Link text</w:t></w:r></w:hyperlink></w:p>'
                    '<w:p><w:r><w:t>Body text</w:t></w:r></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("Link text", markdown)
        self.assertIn("Body text", markdown)

    def test_docx_bold_run_inside_hyperlink_keeps_style_and_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "bold_link.docx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/_rels/document.xml.rels", (
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Type="hyperlink" Target="https://example.com" TargetMode="External"/>'
                    '</Relationships>'
                ))
                zf.writestr("word/document.xml", (
                    '<w:document xmlns:w="w" xmlns:r="r"><w:body>'
                    '<w:p><w:hyperlink r:id="rId1">'
                    '<w:r><w:rPr><w:b/></w:rPr><w:t>BoldLink</w:t></w:r>'
                    '</w:hyperlink></w:p>'
                    '</w:body></w:document>'
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("[**BoldLink**](https://example.com)", markdown)

    # --- PPTX/XLSX lightweight coverage (format-strategy ④/⑤) ---

    def test_pptx_notes_slide_appended_to_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "deck.pptx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("ppt/slides/slide1.xml", (
                    "<p:sld xmlns:p='p' xmlns:a='a'>"
                    "<p:cSld><p:spTree>"
                    "<p:sp><p:nvSpPr><p:cNvPr id='2' name='Title 1'/></p:nvSpPr>"
                    "<p:txBody><a:p><a:r><a:t>Visible Title</a:t></a:r></a:p></p:txBody></p:sp>"
                    "</p:spTree></p:cSld></p:sld>"
                ))
                zf.writestr("ppt/notesSlides/notesSlide1.xml", (
                    "<p:notes xmlns:p='p' xmlns:a='a'>"
                    "<p:cSld><p:spTree>"
                    "<p:sp><p:txBody><a:p><a:r><a:t>Speaker note detail</a:t></a:r></a:p></p:txBody></p:sp>"
                    "</p:spTree></p:cSld></p:notes>"
                ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("# Slide 1: Visible Title", markdown)
        self.assertIn("## Slide 1 Notes", markdown)
        self.assertIn("Speaker note detail", markdown)

    def test_pptx_multiple_slides_preserve_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "multi.pptx")
            with zipfile.ZipFile(path, "w") as zf:
                for idx, title in [(1, "Alpha"), (2, "Beta")]:
                    zf.writestr(f"ppt/slides/slide{idx}.xml", (
                        f"<p:sld xmlns:p='p' xmlns:a='a'>"
                        f"<p:cSld><p:spTree>"
                        f"<p:sp><p:nvSpPr><p:cNvPr id='{idx}' name='T{idx}'/></p:nvSpPr>"
                        f"<p:txBody><a:p><a:r><a:t>{title}</a:t></a:r></a:p></p:txBody></p:sp>"
                        f"</p:spTree></p:cSld></p:sld>"
                    ))
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("# Slide 1: Alpha", markdown)
        self.assertIn("# Slide 2: Beta", markdown)
        self.assertLess(markdown.index("# Slide 1: Alpha"), markdown.index("# Slide 2: Beta"))

    def test_xlsx_multiple_sheets_each_with_title_and_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "multi.xlsx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("[Content_Types].xml", "<Types/>")
                zf.writestr(
                    "xl/workbook.xml",
                    '<workbook xmlns="main"><sheets>'
                    '<sheet name="First" sheetId="1"/><sheet name="Second" sheetId="2"/>'
                    '</sheets></workbook>',
                )
                zf.writestr(
                    "xl/sharedStrings.xml",
                    '<sst xmlns="main"><si><t>A</t></si><si><t>B</t></si><si><t>C</t></si><si><t>D</t></si></sst>',
                )
                zf.writestr(
                    "xl/worksheets/sheet1.xml",
                    '<worksheet xmlns="main"><sheetData>'
                    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                    '</sheetData></worksheet>',
                )
                zf.writestr(
                    "xl/worksheets/sheet2.xml",
                    '<worksheet xmlns="main"><sheetData>'
                    '<row r="1"><c r="A1" t="s"><v>2</v></c><c r="B1" t="s"><v>3</v></c></row>'
                    '</sheetData></worksheet>',
                )
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("# First", markdown)
        self.assertIn("# Second", markdown)
        self.assertIn("| A | B |", markdown)
        self.assertIn("| C | D |", markdown)
        self.assertLess(markdown.index("# First"), markdown.index("# Second"))

    def test_xlsx_empty_sheet_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "sparse.xlsx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("[Content_Types].xml", "<Types/>")
                zf.writestr(
                    "xl/workbook.xml",
                    '<workbook xmlns="main"><sheets>'
                    '<sheet name="Empty" sheetId="1"/><sheet name="Filled" sheetId="2"/>'
                    '</sheets></workbook>',
                )
                zf.writestr(
                    "xl/sharedStrings.xml",
                    '<sst xmlns="main"><si><t>Key</t></si><si><t>Val</t></si></sst>',
                )
                zf.writestr(
                    "xl/worksheets/sheet1.xml",
                    '<worksheet xmlns="main"><sheetData>'
                    '<row r="1"><c r="A1"/><c r="B1"/></row>'
                    '</sheetData></worksheet>',
                )
                zf.writestr(
                    "xl/worksheets/sheet2.xml",
                    '<worksheet xmlns="main"><sheetData>'
                    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                    '</sheetData></worksheet>',
                )
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertNotIn("# Empty", markdown)
        self.assertIn("# Filled", markdown)
        self.assertIn("| Key | Val |", markdown)

    def test_xlsx_inline_string_cell_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = Path(tmp, "inline.xlsx")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("[Content_Types].xml", "<Types/>")
                zf.writestr(
                    "xl/workbook.xml",
                    '<workbook xmlns="main"><sheets><sheet name="Inline" sheetId="1"/></sheets></workbook>',
                )
                zf.writestr(
                    "xl/worksheets/sheet1.xml",
                    '<worksheet xmlns="main"><sheetData>'
                    '<row r="1">'
                    '<c r="A1" t="inlineStr"><is><t>Inline value</t></is></c>'
                    '<c r="B1"><v>42</v></c>'
                    '</row>'
                    '</sheetData></worksheet>',
                )
            markdown, _w, _a = office_xml_to_markdown(path, run_dir)

        self.assertIn("Inline value", markdown)
        self.assertIn("42", markdown)


if __name__ == "__main__":
    unittest.main()
