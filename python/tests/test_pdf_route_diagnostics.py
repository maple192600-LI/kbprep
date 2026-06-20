import unittest

from kbprep_worker.diagnose.pdf_route_diagnostics import build_pdf_route_diagnostics


class PDFRouteDiagnosticsTests(unittest.TestCase):
    def test_simple_trusted_text_layer_recommends_tier_1(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 2,
            "text_pages": 2,
            "image_pages": 0,
            "image_count": 0,
            "text_layer_health": "good",
            "needs_ocr": False,
            "layout_complexity": "simple",
            "layout_profile": "document_pages",
            "pdf_subtype": "text_layer",
            "text_quality": {
                "garbled_ratio": 0.0,
                "unreadable_text_ratio": 0.0,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.0,
                "control_ratio": 0.0,
            },
        })

        self.assertEqual(diagnostics["schema"], "kbprep.pdf_route_diagnostics.v1")
        self.assertTrue(diagnostics["text_layer"]["trusted"])
        self.assertEqual(diagnostics["image_coverage"]["ratio"], 0.0)
        self.assertEqual(diagnostics["layout_complexity"]["level"], "simple")
        self.assertEqual(diagnostics["recommended_tier"], "tier_1")
        self.assertEqual(diagnostics["recommended_route"], "pymupdf4llm")
        self.assertEqual(diagnostics["ocr_triggers"], [])

    def test_complex_trusted_text_layer_recommends_tier_2(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 4,
            "text_pages": 4,
            "image_pages": 0,
            "image_count": 0,
            "text_layer_health": "good",
            "needs_ocr": False,
            "layout_complexity": "complex",
            "layout_profile": "slide_deck_or_ppt_export",
            "pdf_subtype": "ppt_exported_text_layer",
            "multi_column_pages": 1,
            "table_pages": 0,
            "image_text_interleaved_pages": 0,
            "text_quality": {
                "garbled_ratio": 0.0,
                "unreadable_text_ratio": 0.0,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.0,
                "control_ratio": 0.0,
            },
        })

        self.assertTrue(diagnostics["text_layer"]["trusted"])
        self.assertEqual(diagnostics["layout_complexity"]["level"], "complex")
        self.assertTrue(diagnostics["structure_signals"]["multi_column"])
        self.assertTrue(diagnostics["structure_signals"]["slide_like"])
        self.assertEqual(diagnostics["recommended_tier"], "tier_2")
        self.assertEqual(diagnostics["recommended_route"], "mineru_auto")

    def test_untrusted_text_layer_recommends_tier_3(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 6,
            "text_pages": 6,
            "image_pages": 0,
            "image_count": 0,
            "text_layer_health": "bad",
            "needs_ocr": True,
            "layout_complexity": "simple",
            "layout_profile": "document_pages",
            "pdf_subtype": "garbled_text_layer",
            "text_quality": {
                "garbled_ratio": 0.3,
                "unreadable_text_ratio": 0.3,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.2,
                "control_ratio": 0.0,
            },
        })

        self.assertFalse(diagnostics["text_layer"]["trusted"])
        self.assertTrue(diagnostics["text_risk"]["cid_or_tounicode_risk"])
        self.assertIn("untrusted_text_layer", diagnostics["ocr_triggers"])
        self.assertEqual(diagnostics["recommended_tier"], "tier_3")
        self.assertEqual(diagnostics["recommended_route"], "mineru_ocr")

    def test_scanned_or_image_heavy_pdf_recommends_tier_3(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 10,
            "text_pages": 1,
            "image_pages": 9,
            "image_count": 9,
            "text_layer_health": "no_text_layer",
            "needs_ocr": True,
            "layout_complexity": "complex",
            "layout_profile": "image_heavy_document",
            "pdf_subtype": "image_only_or_scanned",
            "text_quality": {
                "garbled_ratio": 0.0,
                "unreadable_text_ratio": 0.0,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.0,
                "control_ratio": 0.0,
            },
        })

        self.assertEqual(diagnostics["image_coverage"]["ratio"], 0.9)
        self.assertEqual(diagnostics["image_coverage"]["level"], "high")
        self.assertIn("high_image_coverage", diagnostics["ocr_triggers"])
        self.assertEqual(diagnostics["recommended_tier"], "tier_3")

    def test_large_pdf_sampling_metadata_is_preserved(self):
        diagnostics = build_pdf_route_diagnostics({
            "page_count": 120,
            "text_pages": 15,
            "image_pages": 0,
            "image_count": 0,
            "text_layer_health": "good",
            "needs_ocr": False,
            "layout_complexity": "simple",
            "layout_profile": "document_pages",
            "large_pdf_sampling_applied": True,
            "large_pdf_sampled_pages": 21,
            "large_pdf_sample_strategy": "first_5_last_5_stride_10",
            "text_quality": {
                "garbled_ratio": 0.0,
                "unreadable_text_ratio": 0.0,
                "replacement_char_ratio": 0.0,
                "mojibake_ratio": 0.0,
                "control_ratio": 0.0,
            },
        })

        self.assertTrue(diagnostics["large_pdf_sampling"]["applied"])
        self.assertEqual(diagnostics["large_pdf_sampling"]["sampled_pages"], 21)
        self.assertEqual(diagnostics["large_pdf_sampling"]["strategy"], "first_5_last_5_stride_10")


if __name__ == "__main__":
    unittest.main()
