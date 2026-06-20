"""Rule-backed text profile signals for diagnosis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class TextProfileSignals:
    tutorial_terms: tuple[str, ...]
    meeting_terms: tuple[str, ...]
    note_terms: tuple[str, ...]
    ebook_terms: tuple[str, ...]


@lru_cache(maxsize=1)
def load_text_profile_signals() -> TextProfileSignals:
    path = Path(__file__).resolve().parents[2] / "rules" / "base" / "text_profile_signals.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "kbprep.text_profile_signals.v1":
        raise ValueError(f"Invalid text profile signal schema in {path}")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError(f"{path}: profiles must be an object")
    return TextProfileSignals(
        tutorial_terms=_profile_terms(profiles, "tutorial", path),
        meeting_terms=_profile_terms(profiles, "meeting_or_interview", path),
        note_terms=_profile_terms(profiles, "note", path),
        ebook_terms=_profile_terms(profiles, "ebook_or_long_report", path),
    )


def _profile_terms(profiles: dict, profile: str, path: Path) -> tuple[str, ...]:
    terms = profiles.get(profile)
    if not isinstance(terms, list):
        raise ValueError(f"{path}: profile {profile} must be a list")
    values = tuple(term for term in terms if isinstance(term, str) and term.strip())
    if not values:
        raise ValueError(f"{path}: profile {profile} must contain at least one term")
    return values
