"""Canonical IR TypedNode artifact builder."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .atomic_io import atomic_write_json
from .canonical_transcripts import read_transcript_cues

CANONICAL_IR_TYPED_NODES_SCHEMA = "kbprep.canonical_ir_typed_nodes.v1"
SUPPORTED_NODE_TYPES = frozenset({
    "heading",
    "paragraph",
    "list",
    "table",
    "code",
    "quote",
    "formula",
    "figure",
    "metadata",
    "transcript_cue",
})
TYPED_NODE_KEYS = frozenset({"node_id", "ordinal", "type", "text", "metadata"})

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
_UNORDERED_LIST_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
_TABLE_SEPARATOR_CELL_RE = re.compile(r"^\s*:?-{3,}:?\s*$")
_FIGURE_RE = re.compile(r'^\s*!\[([^\]]*)\]\((\S+?)(?:\s+"([^"]*)")?\)\s*$')
_INLINE_FORMULA_RE = re.compile(r"^\$(?!\$)(.+?)(?<!\\)\$$")
_SPEAKER_RE = re.compile(r"^\s*([^:\n：]{1,40})\s*[:：]\s+\S+")
_SPEAKER_LABEL_RE = re.compile(
    r"^(?:"
    r"Speaker\s*[A-Za-z0-9]+|S\d+|[A-Z]|"
    r"Host|Guest|Interviewer|Interviewee|Moderator|Narrator|Teacher|Student|"
    r"主持人|嘉宾|讲者|旁白|访谈者|受访者|采访者|讲师|老师|学生|说话人|发言人|问|答"
    r")$",
    re.IGNORECASE,
)
_SPEAKER_NAME_LABEL_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}$")
_NON_SPEAKER_LABELS = frozenset({"Note", "Notice", "Warning", "Important", "Tip"})


@dataclass(frozen=True)
class TypedNode:
    node_id: str
    ordinal: int
    node_type: str
    text: str
    metadata: Mapping[str, object]
    line_start: int
    line_end: int


@dataclass(frozen=True)
class _ParsedBlock:
    node_type: str
    text: str
    metadata: dict[str, object]
    line_start: int
    line_end: int


def build_typed_nodes_from_markdown(
    markdown: str,
    *,
    source_type: str = "",
    conversion_route: str = "",
    transcript_cue_texts: Sequence[str] | None = None,
) -> list[TypedNode]:
    """Build deterministic C1 typed nodes from Markdown blocks."""
    blocks = _parse_markdown_blocks(markdown.splitlines())
    nodes: list[TypedNode] = []
    cue_index = 0
    transcript_context = _is_transcript_context(source_type, conversion_route)
    cue_texts = _normalized_transcript_cue_texts(transcript_cue_texts)
    remaining_candidates = _transcript_candidate_counts(blocks)
    next_cue_index = 1
    for block in blocks:
        node_type = block.node_type
        metadata = dict(block.metadata)
        if block.text.strip():
            if transcript_context and block.node_type == "paragraph":
                _remove_transcript_candidates(remaining_candidates, block.text)
                matched_cue_index = _matched_next_transcript_cue_index(
                    block.text,
                    cue_texts,
                    next_cue_index,
                    remaining_candidates=remaining_candidates,
                )
                if matched_cue_index is not None:
                    next_cue_index = matched_cue_index + 1
                    node_type = "transcript_cue"
                    metadata = _transcript_metadata(block.text, matched_cue_index, raw_cue_confirmed=True)
                elif not cue_texts and _speaker_name(
                    block.text,
                    allow_name_label=_allows_name_speaker_labels(conversion_route),
                ) is not None:
                    cue_index += 1
                    node_type = "transcript_cue"
                    metadata = _transcript_metadata(
                        block.text,
                        cue_index,
                        allow_name_label=_allows_name_speaker_labels(conversion_route),
                    )
            nodes.append(_typed_node(len(nodes) + 1, node_type, block.text, metadata, block.line_start, block.line_end))
    return nodes


def _parse_markdown_blocks(lines: list[str]) -> list[_ParsedBlock]:
    blocks: list[_ParsedBlock] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        start_index = index
        node_type, text, metadata, index = _consume_block(lines, index)
        blocks.append(_ParsedBlock(node_type, text, metadata, start_index + 1, index))
    return blocks


def write_typed_nodes_artifact(
    *,
    run_dir: Path,
    document_id: str,
    converted_path: Path,
    source_type: str = "",
    conversion_route: str = "",
    input_path: Path | None = None,
    transcript_cue_texts: Sequence[str] | None = None,
) -> Path:
    """Write ``canonical_ir/typed_nodes.json`` for the converted Markdown."""
    artifact_path = run_dir / "canonical_ir" / "typed_nodes.json"
    markdown = converted_path.read_text(encoding="utf-8")
    cue_texts = _artifact_transcript_cue_texts(
        input_path,
        source_type,
        conversion_route,
        transcript_cue_texts,
    )
    nodes = build_typed_nodes_from_markdown(
        markdown,
        source_type=source_type,
        conversion_route=conversion_route,
        transcript_cue_texts=cue_texts,
    )
    payload = {
        "schema": CANONICAL_IR_TYPED_NODES_SCHEMA,
        "document_id": document_id,
        "source_artifact": converted_path.resolve().relative_to(run_dir.resolve()).as_posix(),
        "node_count": len(nodes),
        "nodes": [_typed_node_to_dict(node) for node in nodes],
    }
    atomic_write_json(artifact_path, payload, indent=2, trailing_newline=False)
    return artifact_path


def _consume_block(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    line = lines[index]
    if _parse_fence(line) is not None:
        return _consume_code(lines, index)
    if _is_yaml_frontmatter_start(lines, index):
        return _consume_metadata(lines, index)
    if _is_formula_start(line):
        return _consume_formula(lines, index)
    heading = _HEADING_RE.match(line)
    if heading:
        return "heading", heading.group(2).strip(), {"heading_level": len(heading.group(1))}, index + 1
    if _list_item_text(line) is not None:
        return _consume_list(lines, index)
    if _starts_table(lines, index):
        return _consume_table(lines, index)
    if line.lstrip().startswith(">"):
        return _consume_quote(lines, index)
    if _figure_metadata(line) is not None:
        return _consume_figure(lines, index)
    return _consume_paragraph(lines, index)


def _consume_code(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    fence = _parse_fence(lines[index])
    if fence is None:
        return _consume_paragraph(lines, index)
    fence_char, fence_len, language = fence
    block: list[str] = []
    index += 1
    while index < len(lines):
        if _is_closing_fence(lines[index], fence_char, fence_len):
            return "code", "\n".join(block), {"language": language} if language else {}, index + 1
        block.append(lines[index])
        index += 1
    return "code", "\n".join(block), {"language": language} if language else {}, index


def _consume_list(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    items: list[str] = []
    while index < len(lines):
        item = _list_item_text(lines[index])
        if item is None:
            break
        items.append(item.strip())
        index += 1
    return "list", "\n".join(items), {"items": len(items)}, index


def _consume_table(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    rows: list[str] = []
    while index < len(lines) and _has_pipe_cells(lines[index]):
        rows.append(lines[index].strip())
        index += 1
    return "table", "\n".join(rows), {"rows": len(rows)}, index


def _consume_quote(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    quoted: list[str] = []
    while index < len(lines) and lines[index].lstrip().startswith(">"):
        quoted.append(lines[index].lstrip()[1:].strip())
        index += 1
    return "quote", "\n".join(quoted), {"lines": len(quoted)}, index


def _consume_metadata(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    metadata_lines: list[str] = []
    index += 1
    while index < len(lines):
        if lines[index].strip() == "---":
            return "metadata", "\n".join(metadata_lines), {"format": "yaml_frontmatter", "lines": len(metadata_lines)}, index + 1
        metadata_lines.append(lines[index])
        index += 1
    return "paragraph", "---\n" + "\n".join(metadata_lines), {}, index


def _consume_figure(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    line = lines[index].strip()
    metadata = _figure_metadata(line)
    if metadata is None:
        return _consume_paragraph(lines, index)
    return "figure", line, metadata, index + 1


def _consume_formula(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    stripped = lines[index].strip()
    if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
        return "formula", stripped[2:-2].strip(), {"syntax": "dollar_block"}, index + 1
    if stripped == "$$":
        return _consume_formula_block(lines, index)
    inline = _INLINE_FORMULA_RE.match(stripped)
    if inline:
        return "formula", inline.group(1).strip(), {"syntax": "dollar_inline"}, index + 1
    return _consume_paragraph(lines, index)


def _consume_formula_block(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    formula_lines: list[str] = []
    index += 1
    while index < len(lines):
        if lines[index].strip() == "$$":
            return "formula", "\n".join(formula_lines).strip(), {"syntax": "dollar_block"}, index + 1
        formula_lines.append(lines[index])
        index += 1
    return "formula", "\n".join(formula_lines).strip(), {"syntax": "dollar_block"}, index


def _consume_paragraph(lines: list[str], index: int) -> tuple[str, str, dict[str, object], int]:
    paragraph: list[str] = []
    while index < len(lines) and lines[index].strip():
        if paragraph and _is_special_block_start(lines, index):
            break
        paragraph.append(lines[index].strip())
        index += 1
    return "paragraph", "\n".join(paragraph), {}, index


def _is_special_block_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    return (
        _parse_fence(line) is not None
        or _is_yaml_frontmatter_start(lines, index)
        or _is_formula_start(line)
        or _HEADING_RE.match(line) is not None
        or _list_item_text(line) is not None
        or _starts_table(lines, index)
        or line.lstrip().startswith(">")
        or _figure_metadata(line) is not None
    )


def _starts_table(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and _has_pipe_cells(lines[index])
        and _is_table_separator_row(lines[index + 1])
    )


def _has_pipe_cells(line: str) -> bool:
    return len(_table_cells(line)) >= 2


def _is_table_separator_row(line: str) -> bool:
    cells = _table_cells(line)
    return len(cells) >= 2 and all(_TABLE_SEPARATOR_CELL_RE.match(cell) for cell in cells)


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if "|" not in stripped:
        return []
    parts = stripped.split("|")
    if stripped.startswith("|"):
        parts = parts[1:]
    if stripped.endswith("|") and len(parts) > 2:
        parts = parts[:-1]
    return [cell.strip() for cell in parts]


def _parse_fence(line: str) -> tuple[str, int, str] | None:
    leading_spaces = len(line) - len(line.lstrip(" "))
    if leading_spaces > 3:
        return None
    stripped = line.strip()
    if not stripped or stripped[0] not in {"`", "~"}:
        return None
    fence_char = stripped[0]
    fence_len = len(stripped) - len(stripped.lstrip(fence_char))
    if fence_len < 3:
        return None
    return fence_char, fence_len, stripped[fence_len:].strip()


def _is_yaml_frontmatter_start(lines: list[str], index: int) -> bool:
    return index == 0 and lines[index].strip() == "---" and any(line.strip() == "---" for line in lines[index + 1 :])


def _figure_metadata(line: str) -> dict[str, object] | None:
    match = _FIGURE_RE.match(line)
    if match is None:
        return None
    metadata: dict[str, object] = {"alt": match.group(1), "target": match.group(2)}
    title = match.group(3)
    if title:
        metadata["title"] = title
    return metadata


def _is_formula_start(line: str) -> bool:
    stripped = line.strip()
    if stripped == "$$":
        return True
    if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
        return True
    return _INLINE_FORMULA_RE.match(stripped) is not None


def _is_transcript_context(source_type: str, conversion_route: str) -> bool:
    return source_type == "subtitle_transcript" or conversion_route in {"media_to_transcript", "media_transcript"}


def _transcript_metadata(
    text: str,
    cue_index: int,
    *,
    raw_cue_confirmed: bool = False,
    allow_name_label: bool = False,
) -> dict[str, object]:
    metadata: dict[str, object] = {"cue_index": cue_index}
    speaker = _speaker_name(text, require_likely=not raw_cue_confirmed, allow_name_label=allow_name_label)
    if speaker:
        metadata["speaker"] = speaker
    return metadata


def _artifact_transcript_cue_texts(
    input_path: Path | None,
    source_type: str,
    conversion_route: str,
    transcript_cue_texts: Sequence[str] | None,
) -> Sequence[str] | None:
    if transcript_cue_texts is not None:
        return transcript_cue_texts
    if input_path is None or not _is_transcript_context(source_type, conversion_route):
        return None
    return [cue.text for cue in read_transcript_cues(input_path)]


def _normalized_transcript_cue_texts(cue_texts: Sequence[str] | None) -> tuple[str, ...]:
    if cue_texts is None:
        return ()
    return tuple(_normalize_transcript_text(text) for text in cue_texts if _normalize_transcript_text(text))


def _transcript_candidate_counts(blocks: Sequence[_ParsedBlock]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for block in blocks:
        if block.node_type == "paragraph":
            for candidate in _transcript_match_candidates(block.text):
                counts[candidate] = counts.get(candidate, 0) + 1
    return counts


def _remove_transcript_candidates(counts: dict[str, int], text: str) -> None:
    for candidate in _transcript_match_candidates(text):
        remaining = counts.get(candidate, 0) - 1
        if remaining > 0:
            counts[candidate] = remaining
        else:
            counts.pop(candidate, None)


def _matched_next_transcript_cue_index(
    text: str,
    cue_texts: tuple[str, ...],
    next_index: int,
    *,
    remaining_candidates: Mapping[str, int],
) -> int | None:
    if not cue_texts or next_index < 1 or next_index > len(cue_texts):
        return None
    candidates = _transcript_match_candidates(text)
    if cue_texts[next_index - 1] in candidates:
        return next_index
    for index in range(next_index + 1, len(cue_texts) + 1):
        if cue_texts[index - 1] in candidates:
            skipped_cues = cue_texts[next_index - 1 : index - 1]
            if any(remaining_candidates.get(cue_text, 0) > 0 for cue_text in skipped_cues):
                return None
            return index
    return None


def _transcript_match_candidates(text: str) -> frozenset[str]:
    candidates = {
        _normalize_transcript_text(text),
        _normalize_transcript_text(_strip_speaker_prefix(text, require_likely=False)),
    }
    return frozenset(candidate for candidate in candidates if candidate)


def _normalize_transcript_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _strip_speaker_prefix(text: str, *, require_likely: bool = True) -> str:
    match = _SPEAKER_RE.match(text)
    if match is None:
        return text
    if require_likely and not _is_likely_speaker_label(match.group(1).strip()):
        return text
    return text[match.end() :].strip()


def _speaker_name(text: str, *, require_likely: bool = True, allow_name_label: bool = False) -> str | None:
    match = _SPEAKER_RE.match(text)
    if match is None:
        return None
    speaker = match.group(1).strip()
    if require_likely and not _is_likely_speaker_label(speaker, allow_name_label=allow_name_label):
        return None
    return speaker


def _is_likely_speaker_label(label: str, *, allow_name_label: bool = False) -> bool:
    stripped = label.strip()
    if _SPEAKER_LABEL_RE.match(stripped):
        return True
    if not allow_name_label:
        return False
    return stripped not in _NON_SPEAKER_LABELS and bool(_SPEAKER_NAME_LABEL_RE.match(stripped))


def _allows_name_speaker_labels(conversion_route: str) -> bool:
    return conversion_route in {"media_to_transcript", "media_transcript"}


def _is_closing_fence(line: str, fence_char: str, fence_len: int) -> bool:
    leading_spaces = len(line) - len(line.lstrip(" "))
    if leading_spaces > 3:
        return False
    stripped = line.strip()
    if not stripped.startswith(fence_char * fence_len):
        return False
    closing_len = len(stripped) - len(stripped.lstrip(fence_char))
    return stripped[closing_len:].strip() == ""


def _list_item_text(line: str) -> str | None:
    ordered = _ORDERED_LIST_RE.match(line)
    if ordered:
        return ordered.group(1)
    unordered = _UNORDERED_LIST_RE.match(line)
    if unordered:
        return unordered.group(1)
    return None


def _typed_node(
    ordinal: int,
    node_type: str,
    text: str,
    metadata: dict[str, object],
    line_start: int,
    line_end: int,
) -> TypedNode:
    return TypedNode(
        node_id=f"n_{ordinal:06d}",
        ordinal=ordinal,
        node_type=node_type,
        text=text,
        metadata=metadata,
        line_start=line_start,
        line_end=line_end,
    )


def _typed_node_to_dict(node: TypedNode) -> dict[str, object]:
    return {
        "node_id": node.node_id,
        "ordinal": node.ordinal,
        "type": node.node_type,
        "text": node.text,
        "metadata": dict(node.metadata),
    }
