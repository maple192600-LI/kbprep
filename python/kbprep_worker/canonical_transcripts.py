"""Shared transcript cue parsing for Canonical IR artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_TRANSCRIPT_ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "gb2312")
_TIMING_RE = re.compile(r"^\s*(?P<start>\S+)\s+-->\s+(?P<end>\S+)(?:\s+(?P<settings>.+?))?\s*$")
_WEBVTT_DIRECTIVES = ("WEBVTT", "NOTE", "STYLE", "REGION")
_CUE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


@dataclass(frozen=True)
class TranscriptCue:
    cue_id: str
    start_time: str
    end_time: str
    text: str
    settings: str = ""


def read_transcript_cues(input_path: Path) -> list[TranscriptCue]:
    """Read SRT/WebVTT-style timed cues from a source transcript file."""
    try:
        raw = input_path.read_bytes()
    except OSError:
        return []
    for encoding in _TRANSCRIPT_ENCODINGS:
        try:
            return parse_transcript_cues(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    return []


def parse_transcript_cues(text: str) -> list[TranscriptCue]:
    """Parse timed cue blocks without inventing cue data."""
    cues: list[TranscriptCue] = []
    for block in _transcript_blocks(text):
        cue = _parse_transcript_block(block, len(cues) + 1)
        if cue is not None:
            cues.append(cue)
    return cues


def _transcript_blocks(text: str) -> list[list[str]]:
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[list[str]] = []
    for raw_block in re.split(r"\n\s*\n", normalized):
        lines = [line.strip() for line in raw_block.split("\n") if line.strip()]
        if lines:
            blocks.append(lines)
    return blocks


def _parse_transcript_block(lines: list[str], fallback_index: int) -> TranscriptCue | None:
    for index, line in enumerate(lines):
        timing = _TIMING_RE.match(line)
        if timing is None:
            continue
        return TranscriptCue(
            cue_id=_cue_identifier(lines, index, fallback_index),
            start_time=timing.group("start"),
            end_time=timing.group("end"),
            text=" ".join(lines[index + 1 :]).strip(),
            settings=(timing.group("settings") or "").strip(),
        )
    return None


def _cue_identifier(lines: list[str], timing_index: int, fallback_index: int) -> str:
    if timing_index > 0:
        candidate = lines[timing_index - 1].strip()
        if _is_valid_cue_identifier(candidate):
            return candidate
    return str(fallback_index)


def _is_valid_cue_identifier(candidate: str) -> bool:
    if not candidate or "-->" in candidate or len(candidate) > 120:
        return False
    upper = candidate.upper()
    first_token = upper.split(maxsplit=1)[0]
    return first_token not in _WEBVTT_DIRECTIVES and _CUE_IDENTIFIER_RE.match(candidate) is not None
