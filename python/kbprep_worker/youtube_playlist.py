"""YouTube playlist expansion into local descriptor inputs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .converters.external_tools import DEFAULT_COMMAND_TIMEOUT_SECONDS, ExternalCommandResult
from .youtube_source import is_youtube_playlist_url, is_youtube_url, youtube_playlist_id, youtube_video_id

DEFAULT_PLAYLIST_LIMIT = 50
MAX_PLAYLIST_LIMIT = 500

CommandRunner = Callable[[tuple[str, ...], Path | None, int], ExternalCommandResult]
ToolLocator = Callable[[str], str | None]


@dataclass(frozen=True)
class YoutubePlaylistExpansion:
    ok: bool
    source_dir: Path
    descriptor_paths: tuple[Path, ...]
    report: dict[str, Any]


def expand_youtube_playlist_to_descriptors(
    source_url: str,
    output_root: Path,
    *,
    limit: int | None = None,
    env: Mapping[str, str] | None = None,
    which: ToolLocator = shutil.which,
    runner: CommandRunner | None = None,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> YoutubePlaylistExpansion:
    playlist_id = youtube_playlist_id(source_url)
    source_dir = _source_dir(output_root, playlist_id)
    if not is_youtube_playlist_url(source_url):
        return _failure(source_url, source_dir, _unsupported_failure())
    if _network_disabled(env):
        return _failure(source_url, source_dir, _network_disabled_failure())
    ytdlp = which("yt-dlp")
    if not ytdlp:
        return _failure(source_url, source_dir, _missing_dependency("yt-dlp"))
    command = _playlist_command(ytdlp, source_url)
    sanitized = _sanitize_command(command, source_url)
    result = _safe_run(command, source_dir, runner or _default_runner, timeout_seconds)
    if result.returncode != 0:
        return _failure(source_url, source_dir, _command_failure(result), [sanitized])
    return _write_playlist_descriptors(source_url, source_dir, result.stdout, _bounded_limit(limit), [sanitized])


def _write_playlist_descriptors(
    source_url: str,
    source_dir: Path,
    stdout: str,
    limit: int,
    sanitized_commands: list[list[str]],
) -> YoutubePlaylistExpansion:
    source_dir.mkdir(parents=True, exist_ok=True)
    entries = _playlist_entries(stdout)
    selected = entries[:limit]
    descriptor_paths = tuple(_write_descriptor(source_dir, index, entry) for index, entry in enumerate(selected, start=1))
    failure = None if descriptor_paths else _empty_playlist_failure()
    report = _report(
        source_url,
        source_dir,
        descriptor_paths,
        sanitized_commands,
        available=len(entries),
        selected=len(descriptor_paths),
        failure=failure,
    )
    _write_manifest(source_dir, report)
    return YoutubePlaylistExpansion(ok=bool(descriptor_paths), source_dir=source_dir, descriptor_paths=descriptor_paths, report=report)


def _playlist_entries(stdout: str) -> list[dict[str, str]]:
    payload = _json_payload(stdout)
    raw_entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(raw_entries, list):
        return []
    entries: list[dict[str, str]] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        video_url = _entry_video_url(raw)
        video_id = youtube_video_id(video_url)
        if video_url and video_id:
            entries.append({"video_id": video_id, "source_url": video_url})
    return entries


def _entry_video_url(raw: dict[str, Any]) -> str:
    webpage_url = raw.get("webpage_url")
    if isinstance(webpage_url, str) and is_youtube_url(webpage_url):
        return webpage_url.strip()
    url = raw.get("url")
    if isinstance(url, str) and is_youtube_url(url):
        return url.strip()
    raw_id = url if isinstance(url, str) else raw.get("id")
    if isinstance(raw_id, str):
        video_id = _safe_video_id(raw_id)
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
    return ""


def _write_descriptor(source_dir: Path, index: int, entry: dict[str, str]) -> Path:
    path = source_dir / f"{index:03d}-{entry['video_id']}.url"
    path.write_text(f"[InternetShortcut]\nURL={entry['source_url']}\n", encoding="utf-8")
    return path


def _write_manifest(source_dir: Path, report: dict[str, Any]) -> Path:
    path = source_dir.parent / "playlist_manifest.json"
    payload = {"schema": "kbprep.youtube_playlist_manifest.v1", **report}
    atomic_write_json(path, payload, indent=2, trailing_newline=False)
    report["playlist_manifest_json"] = str(path)
    return path


def _report(
    source_url: str,
    source_dir: Path,
    descriptor_paths: tuple[Path, ...],
    sanitized_commands: list[list[str]],
    *,
    available: int,
    selected: int,
    failure: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "playlist_url": source_url,
        "playlist_id": youtube_playlist_id(source_url),
        "source_dir": str(source_dir),
        "descriptor_paths": [str(path) for path in descriptor_paths],
        "sanitized_commands": sanitized_commands,
        "summary": {"available": available, "selected": selected, "skipped": max(available - selected, 0)},
        "failure_reason": failure,
    }


def _failure(
    source_url: str,
    source_dir: Path,
    failure: dict[str, Any],
    sanitized_commands: list[list[str]] | None = None,
) -> YoutubePlaylistExpansion:
    report = _report(source_url, source_dir, tuple(), sanitized_commands or [], available=0, selected=0, failure=failure)
    return YoutubePlaylistExpansion(ok=False, source_dir=source_dir, descriptor_paths=tuple(), report=report)


def _source_dir(output_root: Path, playlist_id: str) -> Path:
    safe_id = playlist_id or "playlist"
    return Path(output_root) / ".kbprep-inputs" / "youtube-playlist" / safe_id


def _playlist_command(ytdlp: str, source_url: str) -> tuple[str, ...]:
    return (ytdlp, "--flat-playlist", "--dump-single-json", source_url)


def _safe_run(command: tuple[str, ...], cwd: Path, runner: CommandRunner, timeout_seconds: int) -> ExternalCommandResult:
    try:
        cwd.mkdir(parents=True, exist_ok=True)
        return runner(command, cwd, timeout_seconds)
    except subprocess.TimeoutExpired as error:
        return ExternalCommandResult(124, _command_output_text(error.stdout), f"command timed out after {timeout_seconds}s")
    except OSError as error:
        return ExternalCommandResult(1, "", str(error))


def _default_runner(command: tuple[str, ...], cwd: Path | None, timeout_seconds: int) -> ExternalCommandResult:
    completed = subprocess.run(command, cwd=str(cwd) if cwd else None, check=False, capture_output=True, text=True, timeout=timeout_seconds)
    return ExternalCommandResult(completed.returncode, _command_output_text(completed.stdout), _command_output_text(completed.stderr))


def _json_payload(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sanitize_command(command: tuple[str, ...], source_url: str) -> list[str]:
    return ["yt-dlp" if index == 0 else "{playlist_url}" if item == source_url else item for index, item in enumerate(command)]


def _bounded_limit(value: int | None) -> int:
    if value is None:
        return DEFAULT_PLAYLIST_LIMIT
    return max(1, min(int(value), MAX_PLAYLIST_LIMIT))


def _network_disabled(env: Mapping[str, str] | None) -> bool:
    value = (env if env is not None else os.environ).get("KBPREP_DISABLE_NETWORK", "")
    return value.strip().lower() in {"1", "true", "yes"}


def _safe_video_id(value: str) -> str:
    return "".join(char for char in value if char.isalnum() or char in {"_", "-"})[:64]


def _unsupported_failure() -> dict[str, Any]:
    return {"code": "E_UNSUPPORTED_TYPE", "message": "Only explicit YouTube playlist URLs are supported for playlist batches."}


def _empty_playlist_failure() -> dict[str, Any]:
    return {"code": "E_INVALID_INPUT", "message": "YouTube playlist did not contain supported video entries."}


def _network_disabled_failure() -> dict[str, Any]:
    return {"code": "E_NETWORK_DISABLED", "message": "Network access is disabled for YouTube playlist expansion."}


def _missing_dependency(dependency: str) -> dict[str, Any]:
    return {"code": "E_ENV_MISSING", "dependency": dependency, "message": f"Required external dependency is not available: {dependency}."}


def _command_failure(result: ExternalCommandResult) -> dict[str, Any]:
    message = (result.stderr or result.stdout or "external command failed").strip()
    if result.returncode == 124 or "timed out" in message.lower():
        return {"code": "E_TIMEOUT", "returncode": result.returncode, "message": message}
    return {"code": "E_CONVERT_FAILED", "returncode": result.returncode, "message": message}


def _command_output_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""
