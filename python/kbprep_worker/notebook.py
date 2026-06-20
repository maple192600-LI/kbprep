"""Jupyter notebook to Markdown conversion helpers."""

from __future__ import annotations

import json
from pathlib import Path


def analyze_notebook(input_path: str | Path) -> dict:
    notebook = _load_notebook(input_path)
    cells = notebook.get("cells", [])
    markdown_cells = sum(1 for cell in cells if cell.get("cell_type") == "markdown")
    code_cells = sum(1 for cell in cells if cell.get("cell_type") == "code")
    markdown = notebook_to_markdown(input_path)
    return {
        "page_count": 1,
        "cell_count": len(cells),
        "markdown_cell_count": markdown_cells,
        "code_cell_count": code_cells,
        "total_text_length": len(markdown),
        "text_layer_health": "good",
        "needs_ocr": False,
        "recommended_pipeline": "direct",
        "conversion_strategy": "notebook_json",
        "warnings": [],
    }


def notebook_to_markdown(input_path: str | Path) -> str:
    notebook = _load_notebook(input_path)
    language = _notebook_language(notebook)
    parts: list[str] = []

    for index, cell in enumerate(notebook.get("cells", []), start=1):
        cell_type = cell.get("cell_type")
        source = _join_source(cell.get("source"))
        if cell_type == "markdown":
            if source.strip():
                parts.append(source.strip())
            continue

        if cell_type == "code":
            if source.strip():
                parts.append(_fenced(source.rstrip(), language))
            output_text = _cell_outputs_to_text(cell.get("outputs", []))
            if output_text.strip():
                parts.append(f"## Cell {index} Output\n\n" + _fenced(output_text.rstrip(), "text"))
            continue

        if source.strip():
            parts.append(f"## Cell {index} ({cell_type or 'unknown'})\n\n{source.strip()}")

    return "\n\n".join(part for part in parts if part.strip()).strip() + "\n"


def _load_notebook(input_path: str | Path) -> dict:
    path = Path(input_path)
    return json.loads(path.read_text(encoding="utf-8"))


def _notebook_language(notebook: dict) -> str:
    kernelspec = notebook.get("metadata", {}).get("kernelspec", {})
    language = kernelspec.get("language") or kernelspec.get("name") or "python"
    return str(language).lower()


def _join_source(source) -> str:
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    if source is None:
        return ""
    return str(source)


def _cell_outputs_to_text(outputs) -> str:
    lines: list[str] = []
    for output in outputs or []:
        output_type = output.get("output_type")
        if output_type == "stream":
            lines.append(_join_source(output.get("text")))
        elif output_type in {"execute_result", "display_data"}:
            data = output.get("data", {})
            if "text/plain" in data:
                lines.append(_join_source(data["text/plain"]))
        elif output_type == "error":
            traceback = output.get("traceback") or []
            if traceback:
                lines.append("\n".join(str(part) for part in traceback))
            else:
                lines.append(f"{output.get('ename', 'Error')}: {output.get('evalue', '')}")
    return "\n".join(line.rstrip("\n") for line in lines if str(line).strip())


def _fenced(text: str, language: str) -> str:
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}{language}\n{text}\n{fence}"
