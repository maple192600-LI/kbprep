"""Markdown and text signal extraction used by quality gates."""

import re


def _detect_language_from_blocks(blocks: list[dict]) -> str:
    text = "\n".join(str(block.get("text", "")) for block in blocks)
    if not text.strip():
        return "other"
    letters = sum(1 for char in text if char.isalpha())
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    if letters == 0:
        return "other"
    ratio = cjk / letters
    if ratio >= 0.2:
        return "zh"
    if ratio <= 0.05:
        return "en"
    return "mixed"

def _markdown_headings(text: str) -> list[str]:
    headings = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        heading = _normalize_heading_text(match.group(1))
        if heading:
            headings.append(heading)
    return headings

def _strip_fenced_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text or "", flags=re.DOTALL)

def _normalize_heading_text(text: str) -> str:
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text or "")
    text = re.sub(r"\s*#*\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text

def _contains_normalized(values: list[str], target: str) -> bool:
    return any(value == target for value in values)

def _markdown_table_count(text: str) -> int:
    lines = text.splitlines()
    count = 0
    index = 0
    while index < len(lines) - 1:
        if _looks_like_table_row(lines[index]) and _looks_like_table_separator(lines[index + 1]):
            count += 1
            index += 2
            while index < len(lines) and _looks_like_table_row(lines[index]):
                index += 1
            continue
        index += 1
    return count

def _looks_like_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2

def _looks_like_table_separator(line: str) -> bool:
    stripped = line.strip()
    if not _looks_like_table_row(stripped):
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)

def _extract_image_sources(text: str) -> list[str]:
    return [match.strip() for match in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text or "") if match.strip()]


detect_language_from_blocks = _detect_language_from_blocks
