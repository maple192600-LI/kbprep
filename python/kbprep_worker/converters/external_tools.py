from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..converters.direct import normalize_subtitle_transcript
from ..supported_formats import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, LEGACY_OFFICE_EXTENSIONS, VIDEO_EXTENSIONS
from ..youtube_source import is_youtube_url, safe_youtube_stem

DEFAULT_COMMAND_TIMEOUT_SECONDS = 900
DEFAULT_WHISPER_MODEL = "base"

IMAGE_SOURCE_EXTENSIONS = frozenset(IMAGE_EXTENSIONS)
LEGACY_OFFICE_SOURCE_EXTENSIONS = frozenset(LEGACY_OFFICE_EXTENSIONS)
MEDIA_SOURCE_EXTENSIONS = frozenset(AUDIO_EXTENSIONS | VIDEO_EXTENSIONS)
YOUTUBE_MEDIA_SUFFIX = ".mp4"

CommandRunner = Callable[[tuple[str, ...], Path | None, int], "ExternalCommandResult"]
ToolLocator = Callable[[str], str | None]
ImagePdfRenderer = Callable[[Path, Path], None]


@dataclass(frozen=True)
class ExternalCommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ExternalConversionResult:
    ok: bool
    artifact_path: Path | None
    report: dict[str, Any]


def wrap_image_as_pdf(
    source_path: Path,
    run_dir: Path,
    renderer: ImagePdfRenderer | None = None,
) -> ExternalConversionResult:
    source = Path(source_path)
    artifact = _artifact_path(run_dir, "image_pdf", source, ".external.pdf")
    command = _pymupdf_sanitized_command()
    if source.suffix.lower() not in IMAGE_SOURCE_EXTENSIONS:
        return _unsupported_result(source, "image_to_pdf", "mineru_ocr", [command])
    try:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        active_renderer = renderer or _render_image_with_pymupdf
        active_renderer(source, artifact)
    except ImportError as error:
        return _failure_result(source, "image_to_pdf", "mineru_ocr", [command], None, _dependency_failure("pymupdf", error))
    except (OSError, RuntimeError, ValueError) as error:
        return _failure_result(source, "image_to_pdf", "mineru_ocr", [command], None, _convert_failure(error))
    if not artifact.is_file():
        return _failure_result(source, "image_to_pdf", "mineru_ocr", [command], None, _missing_output_failure(artifact))
    return _success_result(source, "image_to_pdf", "mineru_ocr", [command], artifact)


def convert_legacy_office_to_pdf(
    source_path: Path,
    run_dir: Path,
    which: ToolLocator = shutil.which,
    runner: CommandRunner | None = None,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> ExternalConversionResult:
    source = Path(source_path)
    artifact = _artifact_path(run_dir, "legacy_office_pdf", source, ".pdf")
    command_template = _libreoffice_command("soffice", source, artifact.parent)
    if source.suffix.lower() not in LEGACY_OFFICE_SOURCE_EXTENSIONS:
        return _unsupported_result(source, "legacy_office_to_pdf", "pdf_route", [_sanitize_command(command_template, source, artifact)])
    executable = _find_command(("soffice", "libreoffice"), which)
    if not executable:
        return _failure_result(
            source,
            "legacy_office_to_pdf",
            "pdf_route",
            [_sanitize_command(command_template, source, artifact)],
            None,
            _missing_dependency("libreoffice"),
        )
    artifact.parent.mkdir(parents=True, exist_ok=True)
    command = _libreoffice_command(executable, source, artifact.parent)
    sanitized = _sanitize_command(command, source, artifact)
    return _command_pdf_result(source, command, sanitized, artifact, runner or _default_runner, timeout_seconds)


def transcribe_media_with_whisper(
    source_path: Path,
    run_dir: Path,
    env: Mapping[str, str] | None = None,
    which: ToolLocator = shutil.which,
    runner: CommandRunner | None = None,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> ExternalConversionResult:
    source = Path(source_path)
    if source.suffix.lower() not in MEDIA_SOURCE_EXTENSIONS:
        return _unsupported_media_result(source, run_dir)
    ffmpeg = which("ffmpeg")
    whisper = which("whisper")
    audio_path = _artifact_path(run_dir, "media_audio", source, ".wav")
    transcript_path = _artifact_path(run_dir, "media_transcript", source, ".txt")
    model = _whisper_model(env)
    commands = _media_commands(ffmpeg or "ffmpeg", whisper or "whisper", source, audio_path, transcript_path.parent, model)
    sanitized = [_sanitize_command(command, source, audio_path, transcript_path) for command in commands]
    extra = {"whisper_model": model}
    if not ffmpeg:
        return _failure_result(
            source, "media_to_transcript", "direct_text", sanitized, None, _missing_dependency("ffmpeg"), extra
        )
    if not whisper:
        return _failure_result(
            source, "media_to_transcript", "direct_text", sanitized, None, _missing_dependency("whisper"), extra
        )
    return _run_media_commands(
        source, commands, sanitized, audio_path, transcript_path, runner or _default_runner, timeout_seconds, model
    )


def extract_youtube_transcript(
    source_url: str,
    run_dir: Path,
    env: Mapping[str, str] | None = None,
    which: ToolLocator = shutil.which,
    runner: CommandRunner | None = None,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    allow_media_fallback: bool = False,
) -> ExternalConversionResult:
    if not is_youtube_url(source_url):
        return _youtube_failure(source_url, "youtube_subtitle", _unsupported_youtube_failure())
    if _network_disabled(env):
        return _youtube_failure(source_url, "youtube_subtitle", _network_disabled_failure())
    ytdlp = which("yt-dlp")
    if not ytdlp:
        return _youtube_failure(source_url, "youtube_subtitle", _missing_dependency("yt-dlp"))
    active_runner = runner or _default_runner
    subtitle = _try_youtube_subtitle(source_url, run_dir, ytdlp, active_runner, timeout_seconds)
    if subtitle.ok:
        return subtitle
    if not _can_fallback_from_subtitle_failure(subtitle.report):
        return subtitle
    if not allow_media_fallback:
        return _youtube_failure(
            source_url,
            "youtube_subtitle",
            _fallback_not_enabled_failure(),
            _youtube_attempt_commands(subtitle.report),
        )
    return _youtube_media_fallback(source_url, run_dir, env, which, active_runner, timeout_seconds, subtitle.report)


def _try_youtube_subtitle(
    source_url: str,
    run_dir: Path,
    ytdlp: str,
    runner: CommandRunner,
    timeout_seconds: int,
) -> ExternalConversionResult:
    subtitle_dir = Path(run_dir) / "external" / "youtube_subtitle"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    inventory = _youtube_subtitle_inventory(source_url, subtitle_dir, ytdlp, runner, timeout_seconds)
    if inventory is not None:
        return inventory
    output_template = subtitle_dir / safe_youtube_stem(source_url)
    command = _youtube_subtitle_command(ytdlp, source_url, output_template)
    sanitized = _sanitize_youtube_command(command, source_url, output_template)
    result = _safe_run(command, subtitle_dir, runner, timeout_seconds)
    subtitle = _find_subtitle_artifact(subtitle_dir, output_template.name)
    if result.returncode != 0 or subtitle is None:
        failure = _command_failure(result) if result.returncode != 0 else _missing_output_failure(output_template)
        return _youtube_failure(source_url, "youtube_subtitle", failure, [sanitized])
    transcript = output_template.with_suffix(".txt")
    text = normalize_subtitle_transcript(subtitle.read_text(encoding="utf-8", errors="replace"))
    transcript.write_text(text.rstrip() + "\n", encoding="utf-8")
    report = _youtube_report(source_url, "youtube_subtitle", "success", [sanitized], transcript)
    report["subtitle_path"] = str(subtitle)
    return ExternalConversionResult(ok=True, artifact_path=transcript, report=report)


def _youtube_subtitle_inventory(
    source_url: str,
    subtitle_dir: Path,
    ytdlp: str,
    runner: CommandRunner,
    timeout_seconds: int,
) -> ExternalConversionResult | None:
    command = _youtube_inventory_command(ytdlp, source_url)
    sanitized = _sanitize_youtube_command(command, source_url, subtitle_dir / "inventory.json")
    result = _safe_run(command, subtitle_dir, runner, timeout_seconds)
    if result.returncode != 0:
        return _youtube_failure(source_url, "youtube_subtitle", _command_failure(result), [sanitized])
    payload = _parse_youtube_inventory(result.stdout)
    if payload is None:
        return None
    if _has_preferred_subtitle(payload):
        return None
    return _youtube_failure(source_url, "youtube_subtitle", _subtitle_unavailable_failure(), [sanitized])


def _youtube_media_fallback(
    source_url: str,
    run_dir: Path,
    env: Mapping[str, str] | None,
    which: ToolLocator,
    runner: CommandRunner,
    timeout_seconds: int,
    subtitle_report: dict[str, Any],
) -> ExternalConversionResult:
    ytdlp = which("yt-dlp")
    ffmpeg = which("ffmpeg")
    whisper = which("whisper")
    if not ytdlp:
        return _youtube_failure(source_url, "youtube_media_transcript", _missing_dependency("yt-dlp"))
    if not ffmpeg:
        return _youtube_failure(source_url, "youtube_media_transcript", _missing_dependency("ffmpeg"))
    if not whisper:
        return _youtube_failure(source_url, "youtube_media_transcript", _missing_dependency("whisper"))
    media = Path(run_dir) / "external" / "youtube_media" / f"{safe_youtube_stem(source_url)}{YOUTUBE_MEDIA_SUFFIX}"
    media.parent.mkdir(parents=True, exist_ok=True)
    command = _youtube_media_command(ytdlp, source_url, media)
    sanitized = _sanitize_youtube_command(command, source_url, media)
    result = _safe_run(command, media.parent, runner, timeout_seconds)
    if result.returncode != 0 or not media.is_file():
        failure = _command_failure(result) if result.returncode != 0 else _missing_output_failure(media)
        return _youtube_failure(source_url, "youtube_media_transcript", failure, [sanitized])
    media_result = transcribe_media_with_whisper(media, run_dir, env, which, runner, timeout_seconds)
    return _youtube_fallback_result(source_url, media_result, sanitized, subtitle_report)


def _render_image_with_pymupdf(source_path: Path, target_path: Path) -> None:
    import fitz

    image_doc = fitz.open(str(source_path))
    try:
        pdf_bytes = image_doc.convert_to_pdf()
    finally:
        image_doc.close()
    pdf_doc = fitz.open("pdf", pdf_bytes)
    try:
        pdf_doc.save(str(target_path))
    finally:
        pdf_doc.close()


def _default_runner(command: tuple[str, ...], cwd: Path | None, timeout_seconds: int) -> ExternalCommandResult:
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return ExternalCommandResult(
        completed.returncode,
        _command_output_text(completed.stdout),
        _command_output_text(completed.stderr),
    )


def _command_pdf_result(
    source: Path,
    command: tuple[str, ...],
    sanitized: list[str],
    artifact: Path,
    runner: CommandRunner,
    timeout_seconds: int,
) -> ExternalConversionResult:
    result = _safe_run(command, artifact.parent, runner, timeout_seconds)
    if result.returncode != 0:
        return _failure_result(
            source, "legacy_office_to_pdf", "pdf_route", [sanitized], None, _command_failure(result)
        )
    if not artifact.is_file():
        return _failure_result(
            source, "legacy_office_to_pdf", "pdf_route", [sanitized], None, _missing_output_failure(artifact)
        )
    return _success_result(source, "legacy_office_to_pdf", "pdf_route", [sanitized], artifact)


def _run_media_commands(
    source: Path,
    commands: tuple[tuple[str, ...], tuple[str, ...]],
    sanitized: list[list[str]],
    audio_path: Path,
    transcript_path: Path,
    runner: CommandRunner,
    timeout_seconds: int,
    model: str,
) -> ExternalConversionResult:
    extra = {"whisper_model": model}
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_result = _safe_run(commands[0], audio_path.parent, runner, timeout_seconds)
    if ffmpeg_result.returncode != 0:
        return _failure_result(
            source, "media_to_transcript", "direct_text", sanitized, None, _command_failure(ffmpeg_result), extra
        )
    whisper_result = _safe_run(commands[1], transcript_path.parent, runner, timeout_seconds)
    if whisper_result.returncode != 0:
        return _failure_result(
            source, "media_to_transcript", "direct_text", sanitized, None, _command_failure(whisper_result), extra
        )
    if not transcript_path.is_file():
        return _failure_result(
            source, "media_to_transcript", "direct_text", sanitized, None, _missing_output_failure(transcript_path), extra
        )
    if not transcript_path.read_text(encoding="utf-8").strip():
        return _failure_result(
            source, "media_to_transcript", "direct_text", sanitized, None, _empty_output_failure(transcript_path), extra
        )
    return _success_result(source, "media_to_transcript", "direct_text", sanitized, transcript_path, extra)


def _safe_run(command: tuple[str, ...], cwd: Path, runner: CommandRunner, timeout_seconds: int) -> ExternalCommandResult:
    try:
        return runner(command, cwd, timeout_seconds)
    except subprocess.TimeoutExpired as error:
        return ExternalCommandResult(
            returncode=124,
            stdout=_command_output_text(error.stdout),
            stderr=f"command timed out after {timeout_seconds}s",
        )
    except OSError as error:
        return ExternalCommandResult(returncode=1, stdout="", stderr=str(error))


def _success_result(
    source: Path,
    external_route: str,
    next_route: str,
    sanitized_commands: list[list[str]],
    artifact: Path,
    extra: dict[str, Any] | None = None,
) -> ExternalConversionResult:
    report = _report(source, external_route, next_route, "success", sanitized_commands, artifact, None)
    if extra:
        report.update(extra)
    return ExternalConversionResult(ok=True, artifact_path=artifact, report=report)


def _failure_result(
    source: Path,
    external_route: str,
    next_route: str,
    sanitized_commands: list[list[str]],
    artifact: Path | None,
    failure: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> ExternalConversionResult:
    report = _report(source, external_route, next_route, "failed", sanitized_commands, artifact, failure)
    if extra:
        report.update(extra)
    return ExternalConversionResult(ok=False, artifact_path=artifact, report=report)


def _unsupported_result(
    source: Path,
    external_route: str,
    next_route: str,
    sanitized_commands: list[list[str]],
) -> ExternalConversionResult:
    failure = {
        "code": "E_UNSUPPORTED_TYPE",
        "message": f"{source.suffix.lower() or '<none>'} is outside this external conversion helper's scope.",
    }
    return _failure_result(source, external_route, next_route, sanitized_commands, None, failure)


def _unsupported_media_result(source: Path, run_dir: Path) -> ExternalConversionResult:
    audio_path = _artifact_path(run_dir, "media_audio", source, ".wav")
    transcript_path = _artifact_path(run_dir, "media_transcript", source, ".txt")
    commands = _media_commands("ffmpeg", "whisper", source, audio_path, transcript_path.parent, DEFAULT_WHISPER_MODEL)
    sanitized = [_sanitize_command(command, source, audio_path, transcript_path) for command in commands]
    return _unsupported_result(source, "media_to_transcript", "direct_text", sanitized)


def _report(
    source: Path,
    external_route: str,
    next_route: str,
    status: str,
    sanitized_commands: list[list[str]],
    artifact: Path | None,
    failure: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "route_decision": _route_decision(source, external_route, next_route, status),
        "sanitized_commands": sanitized_commands,
        "artifact_path": str(artifact) if artifact else None,
        "failure_reason": failure,
    }


def _route_decision(source: Path, external_route: str, next_route: str, status: str) -> dict[str, str]:
    return {
        "declared_route": "external_conversion_required",
        "source_extension": source.suffix.lower(),
        "external_route": external_route,
        "next_route": next_route,
        "status": status,
    }


def _artifact_path(run_dir: Path, folder: str, source: Path, suffix: str) -> Path:
    stem = source.stem or "source"
    return Path(run_dir) / "external" / folder / f"{stem}{suffix}"


def _find_command(names: tuple[str, ...], which: ToolLocator) -> str | None:
    for name in names:
        found = which(name)
        if found:
            return found
    return None


def _libreoffice_command(executable: str, source: Path, output_dir: Path) -> tuple[str, ...]:
    return (executable, "--headless", "--convert-to", "pdf", "--outdir", str(output_dir), str(source))


def _media_commands(
    ffmpeg: str,
    whisper: str,
    source: Path,
    audio_path: Path,
    transcript_dir: Path,
    model: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ffmpeg_command = (ffmpeg, "-y", "-i", str(source), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(audio_path))
    whisper_command = (whisper, str(audio_path), "--model", model, "--output_format", "txt", "--output_dir", str(transcript_dir))
    return ffmpeg_command, whisper_command


def _youtube_subtitle_command(ytdlp: str, source_url: str, output_template: Path) -> tuple[str, ...]:
    return (
        ytdlp,
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        "zh-Hans,zh,en",
        "--sub-format",
        "vtt/srt",
        "--output",
        str(output_template),
        source_url,
    )


def _youtube_inventory_command(ytdlp: str, source_url: str) -> tuple[str, ...]:
    return (ytdlp, "--dump-single-json", "--skip-download", source_url)


def _youtube_media_command(ytdlp: str, source_url: str, media_path: Path) -> tuple[str, ...]:
    return (ytdlp, "--format", "ba/bestaudio/best", "--output", str(media_path), source_url)


def _find_subtitle_artifact(subtitle_dir: Path, stem: str) -> Path | None:
    candidates: list[Path] = []
    for suffix in ("*.vtt", "*.srt"):
        candidates.extend(subtitle_dir.glob(f"{stem}*{suffix[1:]}"))
    files = sorted(path for path in candidates if path.is_file())
    return _preferred_subtitle(files)


def _preferred_subtitle(files: list[Path]) -> Path | None:
    if not files:
        return None
    language_order = ("zh-Hans", "zh", "en")
    by_name = {path.name.lower(): path for path in files}
    for language in language_order:
        marker = f".{language.lower()}."
        for name, path in by_name.items():
            if marker in name:
                return path
    return files[0]


def _youtube_report(
    source_url: str,
    external_route: str,
    status: str,
    sanitized_commands: list[list[str]],
    artifact: Path | None,
    failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "route_decision": {
            "declared_route": "external_conversion_required",
            "source_extension": ".url",
            "external_route": external_route,
            "next_route": "direct_text",
            "status": status,
            "fallback_applied": "false",
        },
        "source_url": source_url,
        "sanitized_commands": sanitized_commands,
        "artifact_path": str(artifact) if artifact else None,
        "failure_reason": failure,
    }


def _youtube_failure(
    source_url: str,
    external_route: str,
    failure: dict[str, Any],
    sanitized_commands: list[list[str]] | None = None,
) -> ExternalConversionResult:
    report = _youtube_report(source_url, external_route, "failed", sanitized_commands or [], None, failure)
    return ExternalConversionResult(ok=False, artifact_path=None, report=report)


def _youtube_fallback_result(
    source_url: str,
    media_result: ExternalConversionResult,
    download_command: list[str],
    subtitle_report: dict[str, Any],
) -> ExternalConversionResult:
    if not media_result.ok:
        return media_result
    report = _youtube_report(source_url, "youtube_media_transcript", "success", [download_command], media_result.artifact_path)
    report["route_decision"]["fallback_applied"] = "true"
    report["route_decision"]["fallback_from"] = "youtube_subtitle"
    report["subtitle_attempt"] = subtitle_report
    report["media_transcript"] = media_result.report
    return ExternalConversionResult(ok=True, artifact_path=media_result.artifact_path, report=report)


def _sanitize_youtube_command(command: tuple[str, ...], source_url: str, artifact: Path) -> list[str]:
    replacements = {source_url: "{source_url}", str(artifact): "{artifact_path}", artifact.as_posix(): "{artifact_path}"}
    return [_command_basename(item) if index == 0 else replacements.get(item, item) for index, item in enumerate(command)]


def _unsupported_youtube_failure() -> dict[str, Any]:
    return {"code": "E_UNSUPPORTED_TYPE", "message": "Only YouTube URLs are supported by this optional route."}


def _fallback_not_enabled_failure() -> dict[str, Any]:
    return {
        "code": "E_YOUTUBE_SUBTITLE_UNAVAILABLE",
        "message": "YouTube subtitles were unavailable. Enable media fallback explicitly to download audio and transcribe it.",
    }


def _subtitle_unavailable_failure() -> dict[str, Any]:
    return {
        "code": "E_YOUTUBE_SUBTITLE_UNAVAILABLE",
        "message": "YouTube subtitles were unavailable. Enable media fallback explicitly to download audio and transcribe it.",
    }


def _network_disabled_failure() -> dict[str, Any]:
    return {
        "code": "E_NETWORK_DISABLED",
        "message": "Network access is disabled for YouTube extraction.",
    }


def _network_disabled(env: Mapping[str, str] | None) -> bool:
    value = (env if env is not None else os.environ).get("KBPREP_DISABLE_NETWORK", "")
    return value.strip().lower() in {"1", "true", "yes"}


def _youtube_attempt_commands(report: dict[str, Any]) -> list[list[str]]:
    commands = report.get("sanitized_commands")
    return commands if isinstance(commands, list) else []


def _can_fallback_from_subtitle_failure(report: dict[str, Any]) -> bool:
    failure = report.get("failure_reason")
    if not isinstance(failure, dict):
        return False
    return str(failure.get("code") or "") == "E_YOUTUBE_SUBTITLE_UNAVAILABLE"


def _parse_youtube_inventory(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _has_preferred_subtitle(payload: dict[str, Any]) -> bool:
    languages: set[str] = set()
    for field in ("subtitles", "automatic_captions"):
        value = payload.get(field)
        if isinstance(value, dict):
            languages.update(str(key) for key in value)
    return any(language in languages for language in ("zh-Hans", "zh", "en"))


def _whisper_model(env: Mapping[str, str] | None) -> str:
    model_env = env if env is not None else os.environ
    return (model_env.get("KBPREP_WHISPER_MODEL") or DEFAULT_WHISPER_MODEL).strip() or DEFAULT_WHISPER_MODEL


def _command_output_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _sanitize_command(command: tuple[str, ...], *paths: Path) -> list[str]:
    replacements = _path_replacements(paths)
    sanitized: list[str] = []
    for index, argument in enumerate(command):
        value = replacements.get(argument, argument)
        sanitized.append(_command_basename(value) if index == 0 and value == argument else value)
    return sanitized


def _path_replacements(paths: tuple[Path, ...]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    labels = ("{input_file}", "{audio_path}", "{artifact_path}", "{output_dir}")
    for path, label in zip(paths, labels, strict=False):
        replacements[str(path)] = label
        replacements[path.as_posix()] = label
        replacements[str(path.parent)] = "{output_dir}"
        replacements[path.parent.as_posix()] = "{output_dir}"
    return replacements


def _command_basename(value: str) -> str:
    normalized = value.replace("\\", "/")
    return normalized.rsplit("/", 1)[-1] or value


def _pymupdf_sanitized_command() -> list[str]:
    return ["pymupdf", "open", "{input_file}", "convert_to_pdf", "{artifact_path}"]


def _missing_dependency(dependency: str) -> dict[str, Any]:
    return {
        "code": "E_ENV_MISSING",
        "dependency": dependency,
        "message": f"Required external dependency is not available: {dependency}.",
    }


def _dependency_failure(dependency: str, error: ImportError) -> dict[str, Any]:
    failure = _missing_dependency(dependency)
    failure["message"] = str(error) or failure["message"]
    return failure


def _convert_failure(error: BaseException) -> dict[str, Any]:
    return {"code": "E_CONVERT_FAILED", "message": str(error)}


def _command_failure(result: ExternalCommandResult) -> dict[str, Any]:
    message = (result.stderr or result.stdout or "external command failed").strip()
    if result.returncode == 124 or "timed out" in message.lower():
        return {"code": "E_TIMEOUT", "returncode": result.returncode, "message": message}
    return {"code": "E_CONVERT_FAILED", "returncode": result.returncode, "message": message}


def _missing_output_failure(path: Path) -> dict[str, Any]:
    return {"code": "E_CONVERT_OUTPUT_MISSING", "message": f"Expected conversion artifact was not created: {path.name}."}


def _empty_output_failure(path: Path) -> dict[str, Any]:
    return {"code": "E_CONVERT_OUTPUT_EMPTY", "message": f"Expected conversion artifact was empty: {path.name}."}
