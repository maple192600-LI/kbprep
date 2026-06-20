import unittest

from kbprep_worker.pdf_route_policy import selected_pdf_strategy


class PDFRoutePolicyTests(unittest.TestCase):
    def test_tier_1_selects_pymupdf4llm(self):
        diagnosis = {
            "conversion_strategy": "pdf_text_layer",
            "pdf_route_diagnostics": {
                "schema": "kbprep.pdf_route_diagnostics.v1",
                "recommended_tier": "tier_1",
                "recommended_route": "pymupdf4llm",
                "reason": "Tier 1 because text is trusted and layout is simple.",
            },
        }

        strategy = selected_pdf_strategy(diagnosis)

        self.assertEqual(strategy, "pymupdf4llm")

    def test_tier_2_selects_mineru_txt_or_auto(self):
        for route in ("mineru_txt", "mineru_auto"):
            with self.subTest(route=route):
                diagnosis = {
                    "conversion_strategy": "mineru_auto",
                    "pdf_route_diagnostics": {
                        "schema": "kbprep.pdf_route_diagnostics.v1",
                        "recommended_tier": "tier_2",
                        "recommended_route": route,
                        "reason": "Tier 2 because trusted text has complex layout.",
                    },
                }

                strategy = selected_pdf_strategy(diagnosis)

                self.assertEqual(strategy, route)

    def test_tier_3_selects_mineru_ocr(self):
        diagnosis = {
            "conversion_strategy": "mineru_ocr",
            "pdf_route_diagnostics": {
                "schema": "kbprep.pdf_route_diagnostics.v1",
                "recommended_tier": "tier_3",
                "recommended_route": "mineru_ocr",
                "reason": "Tier 3 because OCR evidence is present.",
            },
        }

        strategy = selected_pdf_strategy(diagnosis)

        self.assertEqual(strategy, "mineru_ocr")

    def test_missing_diagnostics_preserves_legacy_strategy(self):
        diagnosis = {"conversion_strategy": "pdf_text_layer"}

        strategy = selected_pdf_strategy(diagnosis)

        self.assertEqual(strategy, "pdf_text_layer")

    def test_missing_diagnostics_and_strategy_falls_back_to_ocr(self):
        strategy = selected_pdf_strategy({})

        self.assertEqual(strategy, "mineru_ocr")


if __name__ == "__main__":
    unittest.main()
