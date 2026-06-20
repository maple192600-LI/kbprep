"""
normalize - OCR fix and formatting normalization.
Only fixes formatting and OCR errors, never deletes knowledge.

Input: converted.md + MinerU JSON artifacts + images/
Output: normalized.md + normalization_report.json + ocr_fixes.jsonl
"""
import json
import logging
import re
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

OcrRule = tuple[re.Pattern[str], str, str, float, str]


@lru_cache(maxsize=1)
def load_ocr_normalization_rules() -> tuple[list[OcrRule], list[OcrRule]]:
    """Load OCR normalization rules from the packaged rule dictionary."""
    root = Path(__file__).resolve().parents[2]
    rules_path = root / "rules" / "base" / "ocr_normalization.json"
    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "kbprep.ocr_normalization.v1":
        raise ValueError(f"Invalid OCR normalization schema in {rules_path}")
    return (
        _compile_ocr_rules(payload.get("fix_rules", []), rules_path),
        _compile_ocr_rules(payload.get("review_rules", []), rules_path),
    )


def _compile_ocr_rules(items: object, source: Path) -> list[OcrRule]:
    if not isinstance(items, list):
        raise ValueError(f"{source}: OCR rule groups must be lists")
    compiled: list[OcrRule] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{source}: OCR rule {idx} must be an object")
        pattern = item.get("pattern")
        replacement = item.get("replacement")
        rule = item.get("rule")
        confidence = item.get("confidence")
        warning_code = item.get("warning_code", "")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"{source}: OCR rule {idx}.pattern is required")
        if not isinstance(replacement, str):
            raise ValueError(f"{source}: OCR rule {idx}.replacement must be a string")
        if not isinstance(rule, str) or not rule:
            raise ValueError(f"{source}: OCR rule {idx}.rule is required")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            raise ValueError(f"{source}: OCR rule {idx}.confidence must be between 0 and 1")
        if not isinstance(warning_code, str):
            raise ValueError(f"{source}: OCR rule {idx}.warning_code must be a string")
        try:
            compiled.append((re.compile(pattern), replacement, rule, float(confidence), warning_code))
        except re.error as exc:
            raise ValueError(f"{source}: OCR rule {idx}.pattern is invalid: {exc}") from exc
    return compiled


def normalize(converted_text: str, run_dir: str, mineru_artifacts: dict | None = None) -> dict:
    """
    Normalize converted markdown: fix OCR errors, fix formatting.
    Returns dict with normalized_text, fix_count, warnings.
    """
    fixes = []
    text = converted_text

    # ── Step 1: Fix HTML tables → Markdown tables ─────────────────
    text, table_fixes = _convert_html_tables(text)
    fixes.extend(table_fixes)

    # ── Step 2: Fix OCR confusions ────────────────────────────────
    text, ocr_fixes, warnings = _apply_ocr_fix_rules(text)
    fixes.extend(ocr_fixes)

    # ── Step 3: Fix heading levels ────────────────────────────────
    text, heading_fixes = _fix_heading_levels(text)
    fixes.extend(heading_fixes)

    # ── Step 4: Fix broken code blocks ────────────────────────────
    text, code_fixes = _fix_code_blocks(text)
    fixes.extend(code_fixes)

    # ── Step 5: Fix image references ──────────────────────────────
    text, img_fixes = _fix_image_references(text, run_dir)
    fixes.extend(img_fixes)

    # ── Write reports ─────────────────────────────────────────────
    _write_normalization_reports(Path(run_dir), fixes)

    return {
        "normalized_text": text,
        "fix_count": len(fixes),
        "warnings": warnings,
    }


def _apply_ocr_fix_rules(text: str) -> tuple[str, list[dict], list[str]]:
    fixes = []
    ocr_fix_patterns, _ocr_review_patterns = load_ocr_normalization_rules()
    for pattern, replacement, rule, confidence, warning_code in ocr_fix_patterns:
        matches = list(pattern.finditer(text))
        for match in reversed(matches):
            fixes.append({
                "fix_source": "ocr_normalization",
                "line_id": f"l_{match.start()}",
                "before": match.group(0),
                "after": replacement,
                "rule": rule,
                "confidence": confidence,
                "warning_code": warning_code,
            })
            text = text[:match.start()] + replacement + text[match.end():]
    warnings = _ocr_fix_warnings(fixes)
    return text, fixes, warnings


def _ocr_fix_warnings(fixes: list[dict]) -> list[str]:
    ai_fix_count = sum(1 for fix in fixes if fix.get("warning_code") == "W_OCR_AI_CONFUSION")
    if ai_fix_count <= 0:
        return []
    return [f"W_OCR_AI_CONFUSION: {ai_fix_count} AI/Al confusion patterns fixed"]


def _write_normalization_reports(run_dir: Path, fixes: list[dict]) -> None:
    ocr_fixes = [fix for fix in fixes if fix.get("fix_source") == "ocr_normalization"]
    table_fixes = [fix for fix in fixes if "table" in fix.get("rule", "")]
    _write_fix_jsonl(run_dir / "ocr_fixes.jsonl", ocr_fixes)
    _write_fix_jsonl(run_dir / "table_fixes.jsonl", table_fixes)
    atomic_write_json(
        run_dir / "normalization_report.json",
        _normalization_report(fixes, ocr_fixes, table_fixes),
        indent=2,
        trailing_newline=False,
    )


def _write_fix_jsonl(path: Path, fixes: list[dict]) -> None:
    if not fixes:
        return
    with path.open("w", encoding="utf-8") as fh:
        for fix in fixes:
            fh.write(json.dumps(fix, ensure_ascii=False) + "\n")


def _normalization_report(fixes: list[dict], ocr_fixes: list[dict], table_fixes: list[dict]) -> dict:
    return {
        "total_fixes": len(fixes),
        "ocr_fixes": len(ocr_fixes),
        "table_fixes": len(table_fixes),
        "heading_fixes": sum(1 for fix in fixes if "heading" in fix.get("rule", "")),
        "code_fixes": sum(1 for fix in fixes if "code" in fix.get("rule", "")),
        "image_fixes": sum(1 for fix in fixes if "image" in fix.get("rule", "")),
    }


def _convert_html_tables(text: str) -> tuple[str, list[dict]]:
    """Convert HTML tables to Markdown tables."""
    fixes: list[dict] = []
    if "<table" not in text.lower():
        return text, fixes

    try:
        from bs4 import BeautifulSoup, NavigableString
    except ImportError:
        return _convert_html_tables_with_parser(text)

    soup = BeautifulSoup(text, "html.parser")
    tables = list(soup.find_all("table"))
    if not tables:
        return text, fixes

    for table in tables:
        html = str(table)
        md_table = _html_table_to_markdown(table)
        if not md_table:
            continue
        fixes.append({
            "rule": "html_table_to_markdown",
            "before": html[:100] + "..." if len(html) > 100 else html,
            "after": md_table[:100] + "..." if len(md_table) > 100 else md_table,
            "confidence": 0.85,
        })
        table.replace_with(NavigableString("\n" + md_table + "\n"))

    return str(soup), fixes


def _html_table_to_markdown(table: Any) -> str | None:
    """Convert a simple HTML table to Markdown table format."""
    if isinstance(table, str):
        parser = _HTMLTableReplacementParser(table)
        parser.feed(table)
        parser.close()
        if not parser.tables:
            return None
        return _rows_to_markdown(parser.tables[0]["rows"])

    rows: list[list[str]] = []
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if cells:
            rows.append([_html_cell_text(cell) for cell in cells])
    return _rows_to_markdown(rows)


def _html_cell_text(cell: Any) -> str:
    return " ".join(cell.get_text(" ", strip=True).split()).replace("|", "\\|")


class _HTMLTableReplacementParser(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.line_offsets = _line_offsets(source)
        self.tables: list[dict[str, Any]] = []
        self.current_table: dict[str, Any] | None = None
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name == "table" and self.current_table is None:
            self.current_table = {"start": self._position(), "rows": []}
        elif self.current_table is not None and name == "tr":
            self.current_row = []
        elif self.current_row is not None and name in {"td", "th"}:
            self.current_cell = []

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if self.current_cell is not None and name in {"td", "th"}:
            if self.current_row is not None:
                self.current_row.append(_html_parser_cell_text(self.current_cell))
            self.current_cell = None
        elif self.current_table is not None and name == "tr":
            if self.current_row:
                self.current_table["rows"].append(self.current_row)
            self.current_row = None
        elif self.current_table is not None and name == "table":
            self.current_table["end"] = self._tag_end_position()
            self.tables.append(self.current_table)
            self.current_table = None

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(data)

    def _position(self) -> int:
        line, column = self.getpos()
        return self.line_offsets[line - 1] + column

    def _tag_end_position(self) -> int:
        start = self._position()
        end = self.source.find(">", start)
        return len(self.source) if end == -1 else end + 1


def _convert_html_tables_with_parser(text: str) -> tuple[str, list[dict]]:
    parser = _HTMLTableReplacementParser(text)
    parser.feed(text)
    parser.close()
    if not parser.tables:
        return text, []

    fixes: list[dict] = []
    output = text
    for table in reversed(parser.tables):
        md_table = _rows_to_markdown(table["rows"])
        if not md_table:
            continue
        before = text[table["start"]:table["end"]]
        fixes.append({
            "rule": "html_table_to_markdown",
            "before": before[:100] + "..." if len(before) > 100 else before,
            "after": md_table[:100] + "..." if len(md_table) > 100 else md_table,
            "confidence": 0.85,
        })
        output = output[:table["start"]] + "\n" + md_table + "\n" + output[table["end"]:]
    return output, list(reversed(fixes))


def _rows_to_markdown(rows: list[list[str]]) -> str | None:
    if not rows:
        return None
    width = max(len(row) for row in rows)
    padded_rows = [row + [""] * (width - len(row)) for row in rows]
    lines = [
        "| " + " | ".join(padded_rows[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in padded_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _html_parser_cell_text(parts: list[str]) -> str:
    return " ".join(" ".join(parts).split()).replace("|", "\\|")


def _line_offsets(source: str) -> list[int]:
    offsets = [0]
    for index, char in enumerate(source):
        if char == "\n":
            offsets.append(index + 1)
    return offsets


def _fix_heading_levels(text: str) -> tuple[str, list[dict]]:
    """Do not guess heading-level repairs.

    Earlier automatic heading rewrites could damage intentional heading jumps.
    Keep source heading levels unless a future explicit rule has source evidence.
    """
    return text, []


def _fix_code_blocks(text: str) -> tuple[str, list[dict]]:
    """Fix broken code blocks (unclosed fences)."""
    fixes = []
    lines = text.split("\n")
    in_code = False
    code_start = -1

    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                code_start = i
            else:
                in_code = False

    # If code block is unclosed, close it
    if in_code and code_start >= 0:
        lines.append("```")
        fixes.append({
            "rule": "code_block_close",
            "before": "(unclosed code block)",
            "after": "```",
            "confidence": 0.90,
        })

    return "\n".join(lines), fixes


def _fix_image_references(text: str, run_dir: str) -> tuple[str, list[dict]]:
    """Fix image references to point to correct paths."""
    fixes = []
    # Fix common MinerU image path patterns
    img_re = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

    def fix_img(match: re.Match[str]) -> str:
        alt = match.group(1)
        src = match.group(2)
        # Normalize path separators
        if "\\" in src:
            new_src = src.replace("\\", "/")
            fixes.append({
                "rule": "image_path_separator",
                "before": src,
                "after": new_src,
                "confidence": 0.95,
            })
            return f"![{alt}]({new_src})"
        return match.group(0)

    text = img_re.sub(fix_img, text)
    return text, fixes
