import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import kbprep_worker.converter_registry as registry
from kbprep_worker.converter_registry import (
    ConversionRouteKind,
    ConverterRegistration,
    file_identity_for_path,
    registered_converters,
    select_conversion_route,
)


class ConverterRegistryTests(unittest.TestCase):
    def test_known_extensions_resolve_to_named_routes(self):
        self.assertEqual(select_conversion_route(".md", {}).kind, ConversionRouteKind.DIRECT_TEXT)
        self.assertEqual(select_conversion_route(".docx", {}).kind, ConversionRouteKind.OFFICE_XML)
        self.assertEqual(select_conversion_route(".epub", {}).kind, ConversionRouteKind.EPUB_XHTML)
        self.assertEqual(select_conversion_route(".pdf", {"conversion_strategy": "pdf_text_layer"}).kind, ConversionRouteKind.PDF_TEXT_LAYER)  # noqa: E501
        self.assertEqual(select_conversion_route(".pdf", {"conversion_strategy": "mineru_ocr"}).kind, ConversionRouteKind.MINERU_OCR)
        legacy_mineru = select_conversion_route(".pdf", {"conversion_strategy": "mineru_pipeline"})
        self.assertEqual(legacy_mineru.kind, ConversionRouteKind.MINERU_OCR)
        self.assertEqual(legacy_mineru.conversion_strategy, "mineru_ocr")

    def test_unknown_extensions_are_explicitly_unsupported(self):
        route = select_conversion_route(".rtf", {})

        self.assertEqual(route.kind, ConversionRouteKind.UNSUPPORTED)
        self.assertEqual(route.error_code, "E_UNSUPPORTED_TYPE")
        self.assertEqual(route.conversion_strategy, "unsupported_extension")

    def test_media_and_external_formats_do_not_resolve_to_mineru(self):
        self.assertEqual(select_conversion_route(".png", {}).kind, ConversionRouteKind.IMAGE_TO_PDF_OCR)
        self.assertEqual(select_conversion_route(".doc", {}).kind, ConversionRouteKind.LEGACY_OFFICE_TO_PDF)
        self.assertEqual(select_conversion_route(".mp3", {}).kind, ConversionRouteKind.MEDIA_TRANSCRIPT)
        mobi = select_conversion_route(".mobi", {})
        self.assertEqual(mobi.kind, ConversionRouteKind.UNSUPPORTED)
        self.assertEqual(mobi.conversion_strategy, "unsupported_extension")
        self.assertIn("Convert it to EPUB", mobi.message)

    def test_registry_exposes_converter_metadata(self):
        registrations = registered_converters()

        self.assertTrue(any(item.id == "direct_text" and ".md" in item.extensions for item in registrations))
        self.assertTrue(all(item.priority > 0 for item in registrations))

    def test_route_selection_uses_registration_priority(self):
        low_priority = ConverterRegistration(
            id="later",
            kind=ConversionRouteKind.DIRECT_TEXT,
            priority=20,
            extensions=(".demo",),
            converter="later_converter",
            conversion_strategy="later_strategy",
        )
        high_priority = ConverterRegistration(
            id="earlier",
            kind=ConversionRouteKind.OFFICE_XML,
            priority=10,
            extensions=(".demo",),
            converter="earlier_converter",
            conversion_strategy="earlier_strategy",
        )

        with patch.object(registry, "_REGISTRATIONS", (low_priority, high_priority)):
            route = registry.select_conversion_route(".demo", {})

        self.assertEqual(route.matched_converter, "earlier")
        self.assertEqual(route.converter, "earlier_converter")
        self.assertEqual(route.conversion_strategy, "earlier_strategy")

    def test_content_sniffing_routes_extensionless_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "source")
            path.write_bytes(b"%PDF-1.7\n% fake")
            identity = file_identity_for_path(path)
            route = select_conversion_route(identity.extension, {"conversion_strategy": "mineru_ocr"}, file_identity=identity)

        self.assertEqual(route.kind, ConversionRouteKind.MINERU_OCR)
        self.assertEqual(route.matched_converter, "mineru")
        self.assertIn("pdf_header", route.match_evidence)

    def test_pdf_route_policy_selects_pymupdf4llm_registration(self):
        route = select_conversion_route(".pdf", {
            "conversion_strategy": "pdf_text_layer",
            "pdf_route_diagnostics": {
                "schema": "kbprep.pdf_route_diagnostics.v1",
                "recommended_route": "pymupdf4llm",
            },
        })

        self.assertEqual(route.kind, ConversionRouteKind.PDF_PYMUPDF4LLM)
        self.assertEqual(route.converter, "pymupdf4llm")
        self.assertEqual(route.conversion_strategy, "pymupdf4llm")

    def test_pdf_route_policy_selects_mineru_txt_registration(self):
        route = select_conversion_route(".pdf", {
            "conversion_strategy": "mineru_auto",
            "pdf_route_diagnostics": {
                "schema": "kbprep.pdf_route_diagnostics.v1",
                "recommended_route": "mineru_txt",
            },
        })

        self.assertEqual(route.kind, ConversionRouteKind.MINERU_OCR)
        self.assertEqual(route.converter, "mineru")
        self.assertEqual(route.conversion_strategy, "mineru_txt")

    def test_fake_pdf_extension_is_rejected_when_content_is_not_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "fake.pdf")
            path.write_text("not a pdf", encoding="utf-8")
            identity = file_identity_for_path(path)
            route = select_conversion_route(identity.extension, {}, file_identity=identity)

        self.assertEqual(route.kind, ConversionRouteKind.UNSUPPORTED)
        self.assertEqual(route.error_code, "E_UNSUPPORTED_TYPE")
        self.assertIn("extension_content_mismatch", route.match_evidence)

    def test_content_sniffing_routes_extensionless_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "saved-page")
            path.write_text("<!doctype html><html><body><main>Lesson</main></body></html>", encoding="utf-8")
            identity = file_identity_for_path(path)
            route = select_conversion_route(identity.extension, {}, file_identity=identity)

        self.assertEqual(route.kind, ConversionRouteKind.DIRECT_TEXT)
        self.assertEqual(route.matched_converter, "direct_text")
        self.assertIn("html_signature", route.match_evidence)

    def test_content_sniffing_routes_extensionless_office_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "office-binary")
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types><Override PartName='/word/document.xml'/></Types>")
                archive.writestr("word/document.xml", "<w:document/>")
            identity = file_identity_for_path(path)
            route = select_conversion_route(identity.extension, {}, file_identity=identity)

        self.assertEqual(route.kind, ConversionRouteKind.OFFICE_XML)
        self.assertEqual(route.matched_converter, "office_xml")
        self.assertIn("office_content_types", route.match_evidence)


if __name__ == "__main__":
    unittest.main()
