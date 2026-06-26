"""ASR providers + 路由（从 external_tools 拆出，避免 external_tools 单文件超 800 行）。

双链路：中文 → Qwen3-ASR（transformers 后端，Python import，GPU），英文 → Whisper（CLI，GPU）。
按 ``KBPREP_ASR_LANGUAGE`` 路由（默认 zh）。配置参考 MediaCrawler 验证过的
cuda:0/bfloat16/长 max_new_tokens。torch/qwen_asr 懒加载（asr extra 缺失给明确错误）。
"""
from __future__ import annotations

import os
import re
import shutil
from collections.abc import Mapping
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from .external_tools import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    MEDIA_SOURCE_EXTENSIONS,
    CommandRunner,
    ExternalConversionResult,
    ToolLocator,
    _artifact_path,
    _command_failure,
    _convert_failure,
    _default_runner,
    _empty_output_failure,
    _failure_result,
    _missing_dependency,
    _missing_output_failure,
    _safe_run,
    _sanitize_command,
    _success_result,
    _unsupported_result,
)

DEFAULT_WHISPER_MODEL = "large-v3"
DEFAULT_QWEN3_ASR_MODEL = "Qwen/Qwen3-ASR-1.7B"
DEFAULT_ASR_LANGUAGE = "zh"
DEFAULT_QWEN3_ASR_MAX_NEW_TOKENS = 8192


def transcribe_media(
    source_path: Path,
    run_dir: Path,
    env: Mapping[str, str] | None = None,
    which: ToolLocator = shutil.which,
    runner: CommandRunner | None = None,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> ExternalConversionResult:
    """双链路 ASR 统一入口：按 ``KBPREP_ASR_LANGUAGE`` 路由——中文走 Qwen3-ASR，英文走 Whisper。

    subtitle-first 不变（YouTube 有字幕直接用字幕）；本函数只负责无字幕 media fallback 转写。
    """
    if _asr_provider(env) == "qwen3-asr":
        return transcribe_media_with_qwen3_asr(source_path, run_dir, env, which, runner, timeout_seconds)
    return transcribe_media_with_whisper(source_path, run_dir, env, which, runner, timeout_seconds)


def _asr_provider(env: Mapping[str, str] | None) -> str:
    """语言路由：``KBPREP_ASR_LANGUAGE=zh`` → qwen3-asr；``en`` → whisper。默认 zh。"""
    active_env = env if env is not None else os.environ
    language = (active_env.get("KBPREP_ASR_LANGUAGE") or DEFAULT_ASR_LANGUAGE).strip().lower()
    return "qwen3-asr" if language.startswith("zh") else "whisper"


# ---------- Whisper 链路（英文）----------


def _unsupported_media_result(source: Path, run_dir: Path) -> ExternalConversionResult:
    """媒体类型不在 ASR scope 时，仍给可审计的 ffmpeg+whisper sanitized 命令报告。"""
    audio_path = _artifact_path(run_dir, "media_audio", source, ".wav")
    transcript_path = _artifact_path(run_dir, "media_transcript", source, ".txt")
    commands = _media_commands("ffmpeg", "whisper", source, audio_path, transcript_path.parent, DEFAULT_WHISPER_MODEL)
    sanitized = [_sanitize_command(command, source, audio_path, transcript_path) for command in commands]
    return _unsupported_result(source, "media_to_transcript", "direct_text", sanitized)


def transcribe_media_with_whisper(
    source_path: Path,
    run_dir: Path,
    env: Mapping[str, str] | None = None,
    which: ToolLocator = shutil.which,
    runner: CommandRunner | None = None,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> ExternalConversionResult:
    """英文链路：Whisper CLI 转写（GPU 自动）。"""
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


def _whisper_model(env: Mapping[str, str] | None) -> str:
    model_env = env if env is not None else os.environ
    return (model_env.get("KBPREP_WHISPER_MODEL") or DEFAULT_WHISPER_MODEL).strip() or DEFAULT_WHISPER_MODEL


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


def _media_commands(
    ffmpeg: str,
    whisper: str,
    source: Path,
    audio_path: Path,
    transcript_dir: Path,
    model: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ffmpeg_command = _audio_extract_command(ffmpeg, source, audio_path)
    whisper_command = (whisper, str(audio_path), "--model", model, "--output_format", "txt", "--output_dir", str(transcript_dir))
    return ffmpeg_command, whisper_command


def _audio_extract_command(ffmpeg: str, source: Path, audio_path: Path) -> tuple[str, ...]:
    """ffmpeg 抽 16kHz 单声道 wav（Whisper 与 Qwen3-ASR 两链路共用，DRY）。"""
    return (ffmpeg, "-y", "-i", str(source), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(audio_path))


# ---------- Qwen3-ASR 链路（中文）----------


def transcribe_media_with_qwen3_asr(
    source_path: Path,
    run_dir: Path,
    env: Mapping[str, str] | None = None,
    which: ToolLocator = shutil.which,
    runner: CommandRunner | None = None,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> ExternalConversionResult:
    """中文链路：Qwen3-ASR GPU 转写。torch/qwen_asr 懒加载（仅 asr extra 可用）。"""
    source = Path(source_path)
    if source.suffix.lower() not in MEDIA_SOURCE_EXTENSIONS:
        return _unsupported_media_result(source, run_dir)
    active_env = env if env is not None else os.environ
    audio_path = _artifact_path(run_dir, "media_audio", source, ".wav")
    transcript_path = _artifact_path(run_dir, "media_transcript", source, ".txt")
    audio_command = _audio_extract_command(which("ffmpeg") or "ffmpeg", source, audio_path)
    extra = _qwen3_report_extra(active_env)
    dependency_failure = _qwen3_asr_dependency_failure()
    if dependency_failure:
        return _qwen3_failure(source, audio_command, audio_path, transcript_path, dependency_failure, extra)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_result = _safe_run(audio_command, audio_path.parent, runner or _default_runner, timeout_seconds)
    if ffmpeg_result.returncode != 0:
        return _qwen3_failure(source, audio_command, audio_path, transcript_path, _command_failure(ffmpeg_result), extra)
    return _qwen3_transcribe(source, audio_command, audio_path, transcript_path, active_env, extra)


def _qwen3_transcribe(
    source: Path,
    audio_command: tuple[str, ...],
    audio_path: Path,
    transcript_path: Path,
    env: Mapping[str, str],
    extra: dict[str, Any],
) -> ExternalConversionResult:
    """跑 Qwen3-ASR 推理并写逐字稿；空结果/异常不落盘（e18cf9a B1 教训）。"""
    try:
        text = _run_qwen3_asr_inference(audio_path, env, _qwen3_asr_model(env), _qwen3_asr_language(env))
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        return _qwen3_failure(source, audio_command, audio_path, transcript_path, _convert_failure(error), extra)
    if not text.strip():
        return _qwen3_failure(source, audio_command, audio_path, transcript_path, _empty_output_failure(transcript_path), extra)
    transcript_path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return _success_result(
        source,
        "media_to_transcript",
        "direct_text",
        _qwen3_sanitized(audio_command, source, audio_path, transcript_path),
        transcript_path,
        extra,
    )


def _qwen3_failure(
    source: Path,
    audio_command: tuple[str, ...],
    audio_path: Path,
    transcript_path: Path,
    failure: dict[str, Any],
    extra: dict[str, Any],
) -> ExternalConversionResult:
    return _failure_result(
        source,
        "media_to_transcript",
        "direct_text",
        _qwen3_sanitized(audio_command, source, audio_path, transcript_path),
        None,
        failure,
        extra,
    )


def _qwen3_sanitized(
    audio_command: tuple[str, ...], source: Path, audio_path: Path, transcript_path: Path
) -> list[list[str]]:
    return [_sanitize_command(audio_command, source, audio_path, transcript_path), ["<qwen3-asr local inference>"]]


def _qwen3_report_extra(env: Mapping[str, str]) -> dict[str, Any]:
    return {
        "asr_provider": "qwen3_asr",
        "qwen3_asr_model": _qwen3_asr_model(env),
        "qwen3_asr_language": _qwen3_asr_language(env),
    }


def _qwen3_asr_model(env: Mapping[str, str]) -> str:
    return (env.get("KBPREP_QWEN3_ASR_MODEL") or DEFAULT_QWEN3_ASR_MODEL).strip() or DEFAULT_QWEN3_ASR_MODEL


def _qwen3_asr_language(env: Mapping[str, str]) -> str:
    """``qwen_asr.transcribe`` 接受 'Chinese'/'English'（官方示例写法）。"""
    raw = (env.get("KBPREP_ASR_LANGUAGE") or DEFAULT_ASR_LANGUAGE).strip().lower()
    return {"zh": "Chinese", "zh-cn": "Chinese", "zh-tw": "Chinese", "en": "English"}.get(raw, "Chinese")


def _qwen3_asr_max_new_tokens(env: Mapping[str, str]) -> int:
    raw = (env.get("KBPREP_QWEN3_ASR_MAX_NEW_TOKENS") or str(DEFAULT_QWEN3_ASR_MAX_NEW_TOKENS)).strip()
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_QWEN3_ASR_MAX_NEW_TOKENS


def _qwen3_asr_dependency_failure() -> dict[str, Any] | None:
    """asr extra 未装时给明确错误，而非裸 ImportError（e18cf9a C4 教训）。"""
    if find_spec("qwen_asr") is None:
        failure = _missing_dependency("qwen-asr")
        failure["message"] = "Qwen3-ASR 中文链路需要 asr extra：pip install -e '.[asr]'"
        return failure
    return None


def _run_qwen3_asr_inference(audio_path: Path, env: Mapping[str, str], model_name: str, language: str) -> str:
    """参考 MediaCrawler 验证过的配置：dtype bfloat16 + device_map cuda:0 + 长 max_new_tokens。

    官方示例：https://github.com/QwenLM/Qwen3-ASR/blob/main/examples/example_qwen3_asr_transformers.py
    """
    import torch
    from qwen_asr import Qwen3ASRModel

    model = Qwen3ASRModel.from_pretrained(
        model_name,
        dtype=torch.bfloat16,
        device_map="cuda:0",
        max_new_tokens=_qwen3_asr_max_new_tokens(env),
    )
    transcribe_kwargs: dict[str, Any] = {"language": language}
    context = (env.get("KBPREP_ASR_CONTEXT") or "").strip()
    if context:
        transcribe_kwargs["context"] = context
    results = model.transcribe(audio=str(audio_path), **transcribe_kwargs)
    if not results:
        return ""
    first = results[0] if isinstance(results, (list, tuple)) else results
    text = getattr(first, "text", None) or ""
    return re.sub(r"<\|[^|]+\|>", "", text).strip()
