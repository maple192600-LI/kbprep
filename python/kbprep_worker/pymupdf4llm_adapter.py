"""Tier 1 PDF conversion using PyMuPDF4LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from .atomic_io import atomic_write_json, atomic_write_text


def convert_pymupdf4llm_pdf(input_path: Path, output_path: Path, run_dir: Path) -> dict[str, Any]:
    chunks = _to_markdown_chunks(input_path, run_dir)
    markdown, content_list = _markdown_and_content_list(chunks)
    if not markdown.strip():
        raise RuntimeError(f"{input_path.name} produced empty Markdown with pymupdf4llm")

    atomic_write_text(output_path, markdown.rstrip() + "\n")
    content_list_path = run_dir / "pymupdf4llm_content_list.json"
    atomic_write_json(content_list_path, content_list, indent=2, trailing_newline=False)
    return {
        "source_md_path": str(output_path),
        "content_list_path": str(content_list_path),
        "content_list_v2_path": None,
        "middle_json_path": None,
        "assets_dir": str(run_dir / "images" / "pymupdf4llm"),
        "converter": "pymupdf4llm",
        "warnings": [
            "W_PDF_PYMUPDF4LLM_CONVERTER_USED: used trusted text-layer PDF route with PyMuPDF4LLM.",
        ],
    }


def _to_markdown_chunks(input_path: Path, run_dir: Path) -> list[dict[str, Any]]:
    try:
        import pymupdf4llm
    except ImportError as exc:
        raise RuntimeError("pymupdf4llm is required for Tier 1 PDF conversion") from exc

    image_dir = run_dir / "images" / "pymupdf4llm"
    image_dir.mkdir(parents=True, exist_ok=True)
    chunks = pymupdf4llm.to_markdown(
        str(input_path),
        page_chunks=True,
        write_images=True,
        image_path=str(image_dir),
        image_format="png",
        dpi=150,
    )
    if isinstance(chunks, str):
        return [{"metadata": {"page_number": 1}, "text": chunks}]
    if isinstance(chunks, list):
        return [chunk for chunk in chunks if isinstance(chunk, dict)]
    raise RuntimeError("pymupdf4llm returned an unsupported Markdown payload")


def _markdown_and_content_list(chunks: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    markdown_parts: list[str] = []
    content_list: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        raw_metadata = chunk.get("metadata")
        metadata = cast(dict[str, Any], raw_metadata) if isinstance(raw_metadata, dict) else {}
        page_number = _page_number(metadata, index)
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        markdown_parts.append(f"<!-- page: {page_number} -->\n\n{text}")
        content_list.append({
            "type": "text",
            "page_idx": page_number - 1,
            "text": text,
            "metadata": json.loads(json.dumps(metadata, ensure_ascii=False, default=str)),
        })
    return "\n\n".join(markdown_parts), content_list


def _page_number(metadata: dict[str, Any], fallback_index: int) -> int:
    raw = metadata.get("page_number")
    return raw if isinstance(raw, int) and raw > 0 else fallback_index + 1
