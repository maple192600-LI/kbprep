"""Auditable PDF route diagnostic evidence."""

from __future__ import annotations

from typing import Any

PDF_ROUTE_DIAGNOSTICS_SCHEMA = "kbprep.pdf_route_diagnostics.v1"


def build_pdf_route_diagnostics(diagnosis: dict[str, Any]) -> dict[str, Any]:
    text_layer = _text_layer_summary(diagnosis)
    image_coverage = _image_coverage_summary(diagnosis)
    structure = _structure_signals(diagnosis)
    text_risk = _text_risk_signals(diagnosis)
    ocr_triggers = _ocr_triggers(diagnosis, text_layer, image_coverage, text_risk)
    layout = _layout_complexity_summary(diagnosis, structure)
    recommended_tier = _recommended_tier(text_layer, layout, image_coverage, ocr_triggers)
    return {
        "schema": PDF_ROUTE_DIAGNOSTICS_SCHEMA,
        "text_layer": text_layer,
        "layout_complexity": layout,
        "image_coverage": image_coverage,
        "structure_signals": structure,
        "text_risk": text_risk,
        "large_pdf_sampling": _large_pdf_sampling(diagnosis),
        "ocr_triggers": ocr_triggers,
        "recommended_tier": recommended_tier,
        "recommended_route": _recommended_route(recommended_tier),
        "reason": _reason(recommended_tier, text_layer, layout, image_coverage, ocr_triggers),
    }


def _text_layer_summary(diagnosis: dict[str, Any]) -> dict[str, Any]:
    health = str(diagnosis.get("text_layer_health") or "unknown")
    trusted = health == "good" and not bool(diagnosis.get("needs_ocr"))
    return {
        "health": health,
        "trusted": trusted,
        "pdf_subtype": diagnosis.get("pdf_subtype") or "unknown",
    }


def _image_coverage_summary(diagnosis: dict[str, Any]) -> dict[str, Any]:
    page_count = _int_value(diagnosis.get("page_count"))
    image_pages = _int_value(diagnosis.get("image_pages"))
    text_pages = _int_value(diagnosis.get("text_pages"))
    sampled_page_count = _int_value(diagnosis.get("sampled_page_count"))
    denominator = _coverage_denominator(diagnosis, page_count, sampled_page_count)
    ratio = round(image_pages / denominator, 4) if denominator else 0.0
    if ratio >= 0.5:
        level = "high"
    elif ratio > 0:
        level = "low"
    else:
        level = "none"
    return {
        "page_count": page_count,
        "sampled_page_count": sampled_page_count,
        "image_pages": image_pages,
        "text_pages": text_pages,
        "ratio": ratio,
        "ratio_basis": "sampled_pages" if denominator == sampled_page_count and denominator else "page_count",
        "level": level,
    }


def _coverage_denominator(diagnosis: dict[str, Any], page_count: int, sampled_page_count: int) -> int:
    if bool(diagnosis.get("large_pdf_sampling_applied")) and sampled_page_count > 0:
        return sampled_page_count
    return page_count


def _structure_signals(diagnosis: dict[str, Any]) -> dict[str, bool]:
    layout_profile = str(diagnosis.get("layout_profile") or "")
    return {
        "multi_column": _int_value(diagnosis.get("multi_column_pages")) > 0,
        "table_heavy": _int_value(diagnosis.get("table_pages")) > 0,
        "image_text_interleaving": _int_value(diagnosis.get("image_text_interleaved_pages")) > 0,
        "slide_like": layout_profile == "slide_deck_or_ppt_export",
    }


def _text_risk_signals(diagnosis: dict[str, Any]) -> dict[str, bool]:
    quality = diagnosis.get("text_quality")
    text_quality = quality if isinstance(quality, dict) else {}
    unreadable = _float_value(text_quality.get("unreadable_text_ratio"))
    mojibake = _float_value(text_quality.get("mojibake_ratio"))
    replacement = _float_value(text_quality.get("replacement_char_ratio"))
    control = _float_value(text_quality.get("control_ratio"))
    untrusted = str(diagnosis.get("text_layer_health") or "") in {"bad", "degraded", "untrusted"}
    return {
        "cid_or_tounicode_risk": untrusted and (unreadable > 0 or mojibake > 0),
        "replacement_character_risk": replacement > 0,
        "control_character_risk": control > 0,
    }


def _ocr_triggers(
    diagnosis: dict[str, Any],
    text_layer: dict[str, Any],
    image_coverage: dict[str, Any],
    text_risk: dict[str, bool],
) -> list[str]:
    triggers: list[str] = []
    if bool(diagnosis.get("needs_ocr")):
        triggers.append("diagnosis_needs_ocr")
    if not text_layer["trusted"]:
        triggers.append("untrusted_text_layer")
    if image_coverage["level"] == "high":
        triggers.append("high_image_coverage")
    for key, enabled in text_risk.items():
        if enabled:
            triggers.append(key)
    return _dedupe(triggers)


def _layout_complexity_summary(diagnosis: dict[str, Any], structure: dict[str, bool]) -> dict[str, Any]:
    level = str(diagnosis.get("layout_complexity") or "unknown")
    if level == "unknown" and any(structure.values()):
        level = "complex"
    return {
        "level": level,
        "profile": diagnosis.get("layout_profile") or "unknown",
        "signals": [key for key, enabled in structure.items() if enabled],
    }


def _recommended_tier(
    text_layer: dict[str, Any],
    layout: dict[str, Any],
    image_coverage: dict[str, Any],
    ocr_triggers: list[str],
) -> str:
    if ocr_triggers or image_coverage["level"] == "high" or not text_layer["trusted"]:
        return "tier_3"
    if layout["level"] == "complex":
        return "tier_2"
    return "tier_1"


def _recommended_route(tier: str) -> str:
    routes = {
        "tier_1": "pymupdf4llm",
        "tier_2": "mineru_auto",
        "tier_3": "mineru_ocr",
    }
    return routes[tier]


def _reason(
    tier: str,
    text_layer: dict[str, Any],
    layout: dict[str, Any],
    image_coverage: dict[str, Any],
    ocr_triggers: list[str],
) -> str:
    if tier == "tier_3":
        trigger_text = ", ".join(ocr_triggers) if ocr_triggers else "high image coverage"
        return f"Tier 3 because OCR evidence is present: {trigger_text}."
    if tier == "tier_2":
        return f"Tier 2 because text is trusted but layout is {layout['level']}."
    return f"Tier 1 because text is trusted and layout is {layout['level']} with image coverage {image_coverage['ratio']}."  # noqa: E501


def _large_pdf_sampling(diagnosis: dict[str, Any]) -> dict[str, Any]:
    return {
        "applied": bool(diagnosis.get("large_pdf_sampling_applied")),
        "sampled_pages": _int_value(diagnosis.get("large_pdf_sampled_pages")),
        "page_count": _int_value(diagnosis.get("page_count")),
        "strategy": diagnosis.get("large_pdf_sample_strategy") or "full_scan",
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def _float_value(value: object) -> float:
    return value if isinstance(value, float | int) else 0.0
