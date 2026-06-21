"""PDF route policy derived from auditable diagnosis evidence."""

from __future__ import annotations

from typing import Any

PDF_ROUTE_DIAGNOSTICS_SCHEMA = "kbprep.pdf_route_diagnostics.v1"
PDF_PHASE_B_STRATEGIES = {"pymupdf4llm", "mineru_txt", "mineru_auto", "mineru_ocr"}
LEGACY_PDF_STRATEGIES = {
    "pdf_text_layer",
    "mineru_pipeline",
    "mineru_pipeline_ocr",
    "mineru_auto",
    "mineru_ocr",
    "mineru_mixed_text_image",
}


def selected_pdf_strategy(diagnosis: dict[str, Any]) -> str:
    """Return the executable PDF conversion strategy for a diagnosis result.

    If no auditable PDF diagnostics or legacy strategy exists, choose OCR as the
    conservative fallback so unknown PDF evidence does not bypass safer handling.
    """
    diagnostics = diagnosis.get("pdf_route_diagnostics")
    if isinstance(diagnostics, dict) and diagnostics.get("schema") == PDF_ROUTE_DIAGNOSTICS_SCHEMA:
        route = str(diagnostics.get("recommended_route") or "")
        if route in PDF_PHASE_B_STRATEGIES:
            return route

    legacy = str(diagnosis.get("conversion_strategy") or "")
    if legacy in LEGACY_PDF_STRATEGIES:
        return legacy
    return "mineru_ocr"
