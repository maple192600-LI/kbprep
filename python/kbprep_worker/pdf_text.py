"""Lightweight text-layer PDF conversion.

This converter is intentionally narrow: it only uses an existing, trusted PDF
text layer. OCR, image-heavy, and garbled PDFs stay on the MinerU route.
"""

import re
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json, atomic_write_text


def convert_text_layer_pdf(input_path: Path, output_path: Path, run_dir: Path) -> dict:
    """Extract readable Markdown from a trusted PDF text layer.

    Returns a MinerU-shaped artifact dict so downstream page mapping, block
    ranges, and conversion reports can keep working without special cases.
    """
    markdown_parts, content_list = _extract_pdf_text_pages(input_path)
    markdown = "\n\n".join(markdown_parts).strip()
    if not markdown:
        raise RuntimeError(f"{input_path.name} has no extractable trusted text layer")

    atomic_write_text(output_path, markdown + "\n")
    content_list_path = _write_pdf_text_content_list(run_dir, content_list)
    return _pdf_text_artifacts(output_path, content_list_path)


def _extract_pdf_text_pages(input_path: Path) -> tuple[list[str], list[dict]]:
    doc = _open_pymupdf_document(input_path)
    content_list: list[dict] = []
    markdown_parts: list[str] = []
    try:
        for page_idx, page in enumerate(doc):
            normalized = _normalize_page_text(page.get_text("text").strip())
            if not normalized:
                continue
            markdown_parts.append(f"<!-- page: {page_idx + 1} -->\n\n{normalized}")
            content_list.append({"type": "text", "page_idx": page_idx, "text": normalized})
    finally:
        doc.close()
    return markdown_parts, content_list


def _open_pymupdf_document(input_path: Path) -> Any:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError("PyMuPDF is required for pdf_text_layer conversion") from e
    return fitz.open(str(input_path))


def _write_pdf_text_content_list(run_dir: Path, content_list: list[dict]) -> Path:
    content_list_path = run_dir / "pdf_text_content_list.json"
    atomic_write_json(content_list_path, content_list, indent=2, trailing_newline=False)
    return content_list_path


def _pdf_text_artifacts(output_path: Path, content_list_path: Path) -> dict:
    return {
        "source_md_path": str(output_path),
        "content_list_path": str(content_list_path),
        "content_list_v2_path": None,
        "middle_json_path": None,
        "assets_dir": None,
        "converter": "pdf_text_layer",
        "warnings": [
            "W_PDF_TEXT_LAYER_CONVERTER_USED: used existing PDF text layer; OCR/image layout extraction was skipped."
        ],
    }


def _normalize_page_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned: list[str] = []
    blank_pending = False

    for line in lines:
        if not line:
            blank_pending = bool(cleaned)
            continue
        if blank_pending and cleaned[-1] != "":
            cleaned.append("")
        elif cleaned and _should_merge_hard_wrap(cleaned[-1], line):
            cleaned[-1] = _merge_wrapped_lines(cleaned[-1], line)
            blank_pending = False
            continue
        cleaned.append(line)
        blank_pending = False

    return "\n".join(cleaned).strip()


_STRUCTURAL_LINE_RE = re.compile(
    r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)、]\s+|>\s*|```|<!--|---\s*$|\|.*\|)"
)
_SENTENCE_END_RE = re.compile(r"[。！？!?；;：:]\s*$")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_WORD_EDGE_RE = re.compile(r"[A-Za-z0-9,)]$")


def _should_merge_hard_wrap(previous: str, current: str) -> bool:
    """Join PDF text-layer hard wraps inside paragraphs while preserving structure."""
    prev = previous.strip()
    cur = current.strip()
    if not prev or not cur:
        return False
    if _STRUCTURAL_LINE_RE.match(prev) or _STRUCTURAL_LINE_RE.match(cur):
        return False
    if _SENTENCE_END_RE.search(prev):
        return False
    if len(prev) <= 20 and len(cur) <= 20 and not _SENTENCE_END_RE.search(cur):
        return False
    if _CJK_RE.search(prev[-1]) or _CJK_RE.search(cur[0]):
        return True
    return bool(_LATIN_WORD_EDGE_RE.search(prev) and re.match(r"^[a-zA-Z0-9(]", cur))


def _merge_wrapped_lines(previous: str, current: str) -> str:
    if _CJK_RE.search(previous[-1]) or _CJK_RE.search(current[0]):
        return previous.rstrip() + current.lstrip()
    return previous.rstrip() + " " + current.lstrip()
