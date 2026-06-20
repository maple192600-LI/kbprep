"""Conversion integrity checks for quality reports."""

from pathlib import Path

from .io import _read_json_file
from .markdown_signals import (
    _contains_normalized,
    _extract_image_sources,
    _markdown_headings,
    _markdown_table_count,
    _normalize_heading_text,
    _strip_fenced_code,
)

TEXT_SOURCE_INTEGRITY_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".adoc"}

def _source_text_layer_status(diagnosis: dict, conversion_report: dict) -> dict:
    text_quality = diagnosis.get("text_quality", {})
    converter = str(conversion_report.get("converter") or "")
    superseded = _conversion_supersedes_source_text_layer(diagnosis, conversion_report)
    return {
        "text_layer_health": diagnosis.get("text_layer_health"),
        "pdf_subtype": diagnosis.get("pdf_subtype"),
        "needs_ocr": bool(diagnosis.get("needs_ocr")),
        "converter": converter,
        "superseded_by_conversion": superseded,
        "garbled_ratio": text_quality.get("garbled_ratio", 0),
        "unreadable_text_ratio": text_quality.get("unreadable_text_ratio", 0),
        "mojibake_ratio": text_quality.get("mojibake_ratio", 0),
    }

def _conversion_supersedes_source_text_layer(diagnosis: dict, conversion_report: dict) -> bool:
    converter = str(conversion_report.get("converter") or "")
    converted_bytes = int(conversion_report.get("converted_bytes") or 0)
    if converter not in {"mineru", "mineru_after_pdf_text_layer_fallback"}:
        return False
    if converted_bytes <= 0:
        return False
    return bool(
        diagnosis.get("needs_ocr")
        or diagnosis.get("pdf_subtype") == "garbled_text_layer"
        or diagnosis.get("text_layer_health") in {"bad", "untrusted"}
    )

def _converted_text_quality(conversion_report: dict) -> dict:
    artifacts = conversion_report.get("mineru_artifacts")
    if not isinstance(artifacts, dict):
        return {}
    quality = artifacts.get("post_convert_text_quality")
    return quality if isinstance(quality, dict) else {}

def _source_conversion_integrity(run_p: Path, conversion_report: dict) -> dict:
    metadata = _read_json_file(run_p / "run_metadata.json")
    input_path = Path(str(metadata.get("input_path") or ""))
    converted_path = Path(str(conversion_report.get("converted_md") or run_p / "converted.md"))
    input_extension = str(conversion_report.get("input_extension") or input_path.suffix).lower()
    converter = str(conversion_report.get("converter") or "")
    if input_extension not in TEXT_SOURCE_INTEGRITY_EXTENSIONS:
        return _empty_source_conversion_integrity(
            checked=False,
            reason=f"source extension {input_extension or '<none>'} is not a direct text integrity target",
            input_path=str(input_path) if str(input_path) else "",
            converter=converter,
        )
    if not input_path.exists():
        return _empty_source_conversion_integrity(
            checked=False,
            reason="source file not found",
            input_path=str(input_path),
            converter=converter,
        )
    if not converted_path.exists():
        return _empty_source_conversion_integrity(
            checked=False,
            reason="converted.md not found",
            input_path=str(input_path),
            converter=converter,
        )

    source_counts = _markdown_structure_counts(input_path.read_text(encoding="utf-8", errors="replace"))
    converted_counts = _markdown_structure_counts(converted_path.read_text(encoding="utf-8", errors="replace"))
    missing_headings = _missing_headings(source_counts["headings"], converted_counts["headings"])
    return {
        "checked": True,
        "input_path": str(input_path),
        "input_extension": input_extension,
        "converter": converter,
        "source_headings": len(source_counts["headings"]),
        "converted_headings": len(converted_counts["headings"]),
        "missing_heading_count": len(missing_headings),
        "missing_headings": missing_headings[:50],
        "source_tables": source_counts["tables"],
        "converted_tables": converted_counts["tables"],
        "missing_table_count": max(0, source_counts["tables"] - converted_counts["tables"]),
        "source_code_blocks": source_counts["code_blocks"],
        "converted_code_blocks": converted_counts["code_blocks"],
        "missing_code_block_count": max(0, source_counts["code_blocks"] - converted_counts["code_blocks"]),
        "source_image_refs": source_counts["image_refs"],
        "converted_image_refs": converted_counts["image_refs"],
        "missing_image_ref_count": max(0, source_counts["image_refs"] - converted_counts["image_refs"]),
    }

def _empty_source_conversion_integrity(checked: bool, reason: str, input_path: str, converter: str) -> dict:
    return {
        "checked": checked,
        "reason": reason,
        "input_path": input_path,
        "converter": converter,
        "source_headings": 0,
        "converted_headings": 0,
        "missing_heading_count": 0,
        "missing_headings": [],
        "source_tables": 0,
        "converted_tables": 0,
        "missing_table_count": 0,
        "source_code_blocks": 0,
        "converted_code_blocks": 0,
        "missing_code_block_count": 0,
        "source_image_refs": 0,
        "converted_image_refs": 0,
        "missing_image_ref_count": 0,
    }

def _conversion_structure_integrity(blocks: list[dict], run_p: Path) -> dict:
    converted_path = run_p / "converted.md"
    if not converted_path.exists():
        return _empty_conversion_structure_integrity()

    converted_text = converted_path.read_text(encoding="utf-8", errors="replace")
    converted_counts = _markdown_structure_counts(converted_text)
    block_text = "\n\n".join(str(block.get("text", "")) for block in blocks)
    block_counts = _block_structure_counts(blocks, block_text)
    missing_headings = _missing_headings(converted_counts["headings"], block_counts["headings"])

    return {
        "checked": True,
        "converted_headings": len(converted_counts["headings"]),
        "block_headings": len([heading for heading in block_counts["headings"] if heading]),
        "missing_heading_count": len(missing_headings),
        "missing_headings": missing_headings[:50],
        "converted_tables": converted_counts["tables"],
        "block_tables": block_counts["tables"],
        "missing_table_count": max(0, converted_counts["tables"] - block_counts["tables"]),
        "converted_code_blocks": converted_counts["code_blocks"],
        "block_code_blocks": block_counts["code_blocks"],
        "missing_code_block_count": max(0, converted_counts["code_blocks"] - block_counts["code_blocks"]),
        "converted_image_refs": converted_counts["image_refs"],
        "block_image_refs": block_counts["image_refs"],
        "missing_image_ref_count": max(0, converted_counts["image_refs"] - block_counts["image_refs"]),
    }


def _markdown_structure_counts(text: str) -> dict:
    non_code_text = _strip_fenced_code(text)
    return {
        "headings": _markdown_headings(non_code_text),
        "tables": _markdown_table_count(non_code_text),
        "code_blocks": text.count("```") // 2,
        "image_refs": len(_extract_image_sources(non_code_text)),
    }


def _block_structure_counts(blocks: list[dict], block_text: str) -> dict:
    non_code_text = _strip_fenced_code(block_text)
    headings = [
        _normalize_heading_text(str(block.get("text", "")))
        for block in blocks
        if block.get("type") == "section_heading"
    ]
    headings.extend(_markdown_headings(non_code_text))
    return {
        "headings": headings,
        "tables": max(sum(1 for block in blocks if block.get("type") == "table"), _markdown_table_count(non_code_text)),
        "code_blocks": max(sum(1 for block in blocks if block.get("type") == "code"), block_text.count("```") // 2),
        "image_refs": len(_extract_image_sources(non_code_text)),
    }


def _missing_headings(source_headings: list[str], target_headings: list[str]) -> list[str]:
    return [
        heading for heading in source_headings
        if heading and not _contains_normalized(target_headings, heading)
    ]


def _empty_conversion_structure_integrity() -> dict:
    return {
        "checked": False,
        "reason": "converted.md not found",
        "converted_headings": 0,
        "block_headings": 0,
        "missing_heading_count": 0,
        "missing_headings": [],
        "converted_tables": 0,
        "block_tables": 0,
        "missing_table_count": 0,
        "converted_code_blocks": 0,
        "block_code_blocks": 0,
        "missing_code_block_count": 0,
        "converted_image_refs": 0,
        "block_image_refs": 0,
        "missing_image_ref_count": 0,
    }


converted_text_quality = _converted_text_quality
conversion_structure_integrity = _conversion_structure_integrity
source_conversion_integrity = _source_conversion_integrity
source_text_layer_status = _source_text_layer_status
