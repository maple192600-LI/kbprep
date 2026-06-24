"""YouTube source identity helpers for optional URL routes."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

YOUTUBE_DESCRIPTOR_EXTENSIONS = {".url"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def source_url_from_descriptor(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("url="):
            return stripped.split("=", 1)[1].strip()
    return text.strip()


def youtube_url_from_source(path: Path, data: dict | None = None) -> str:
    raw = data.get("source_url") if isinstance(data, dict) else None
    if isinstance(raw, str) and is_youtube_url(raw):
        return raw.strip()
    if path.suffix.lower() in YOUTUBE_DESCRIPTOR_EXTENSIONS:
        candidate = source_url_from_descriptor(path)
        if is_youtube_url(candidate):
            return candidate
    return ""


def is_youtube_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    host = parsed.netloc.lower()
    return parsed.scheme in {"http", "https"} and host in YOUTUBE_HOSTS and bool(youtube_video_id(value))


def youtube_video_id(value: str) -> str:
    parsed = urlparse(value.strip())
    host = parsed.netloc.lower()
    if host == "youtu.be":
        return _safe_video_id(parsed.path.strip("/").split("/", 1)[0])
    query_id = parse_qs(parsed.query).get("v", [""])[0]
    if query_id:
        return _safe_video_id(query_id)
    match = re.search(r"/(?:shorts|embed)/([^/?#]+)", parsed.path)
    return _safe_video_id(match.group(1) if match else "")


def safe_youtube_stem(value: str) -> str:
    return youtube_video_id(value) or "youtube"


def _safe_video_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", value)[:64]
