from __future__ import annotations

import csv
import html
import io
import json
import re
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path

from ..supported_formats import CODE_EXTENSIONS, CODE_LANGUAGE_BY_EXTENSION, NOTEBOOK_EXTENSIONS

HtmlConverter = Callable[[str, Path | None, str, Path], str]


class _InlineHTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def read_with_fallback(path: Path) -> str:
    for enc in ["utf-8", "utf-8-sig", "gbk", "gb2312", "latin-1"]:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError(f"Cannot decode {path.name}")


def read_direct_source(
    path: Path,
    run_dir: Path | None = None,
    html_converter: HtmlConverter | None = None,
) -> str:
    text = read_with_fallback(path)
    ext = path.suffix.lower()
    if ext in {".vtt", ".srt", ".ass", ".lrc"}:
        return normalize_subtitle_transcript(text)
    if ext in {".html", ".htm"}:
        if not html_converter:
            raise ValueError("html_converter is required for HTML inputs")
        return html_converter(text, run_dir, path.stem, path.parent)
    if ext == ".json":
        return json_to_markdown(text)
    if ext in NOTEBOOK_EXTENSIONS:
        from ..notebook import notebook_to_markdown
        return notebook_to_markdown(path)
    if ext in {".csv", ".tsv"}:
        return delimited_to_markdown(text, delimiter="\t" if ext == ".tsv" else ",")
    if ext in CODE_EXTENSIONS:
        return code_to_markdown(text, ext)
    return text


def code_to_markdown(text: str, ext: str) -> str:
    lang = CODE_LANGUAGE_BY_EXTENSION.get(ext, "")
    body = text.rstrip()
    fence = "```"
    while fence in body:
        fence += "`"
    return f"{fence}{lang}\n{body}\n{fence}\n"


def json_to_markdown(text: str) -> str:
    try:
        parsed = json.loads(text)
        pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        pretty = text.strip()
    return "```json\n" + pretty + "\n```\n"


def delimited_to_markdown(text: str, delimiter: str) -> str:
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    rows = [[cell.strip() for cell in row] for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        return ""
    max_cols = max(len(row) for row in rows)
    rows = [row + [""] * (max_cols - len(row)) for row in rows]
    header = rows[0]
    body = rows[1:]
    lines = [
        "| " + " | ".join(escape_table_cell(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(escape_table_cell(cell) for cell in row) + " |")
    return "\n".join(lines) + "\n"


def escape_table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def normalize_subtitle_transcript(text: str) -> str:
    """Convert subtitle timing files into readable transcript markdown."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if line.upper() == "WEBVTT":
            continue
        if line.isdigit():
            continue
        if "-->" in line:
            continue
        if line.startswith(("NOTE", "STYLE", "REGION")):
            continue
        if line.lower().startswith(("kind:", "language:")):
            continue
        line = _strip_inline_html(line)
        line = re.sub(r"<\d{1,2}:\d{2}:\d{2}\.\d+>", "", line)
        line = html.unescape(line)
        line = line.replace(">>", "")
        line = re.sub(r"^\[[^\]]{1,30}\]\s*", "", line)
        line = line.strip()
        if line:
            lines.append(line)

    deduped: list[str] = []
    for line in lines:
        if not line:
            continue
        previous = deduped[-1] if deduped else ""
        if previous == line:
            continue
        if previous and line.startswith(previous):
            deduped[-1] = line
            continue
        if previous and previous.startswith(line):
            continue
        deduped.append(line)
    lines = deduped

    paragraphs: list[str] = []
    current = ""
    for line in lines:
        if not line:
            if current:
                paragraphs.append(current.strip())
                current = ""
            continue
        candidate = f"{current} {line}".strip() if current else line
        if len(candidate) > 500:
            if current:
                paragraphs.append(current.strip())
            current = line
        else:
            current = candidate
    if current:
        paragraphs.append(current.strip())

    return "# Transcript\n\n" + "\n\n".join(paragraphs) + "\n"


def _strip_inline_html(text: str) -> str:
    if "<" not in text or ">" not in text:
        return text
    parser = _InlineHTMLTextParser()
    parser.feed(text)
    parser.close()
    return parser.text()
