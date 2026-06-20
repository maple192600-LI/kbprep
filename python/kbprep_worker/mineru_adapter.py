"""
mineru_adapter — wrapper around MinerU CLI for document conversion.
Handles device detection and resource control.
"""
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .atomic_io import atomic_write_text
from .detect import normalize_language_hint
from .setup_env import detect_device

logger = logging.getLogger(__name__)
DEFAULT_MINERU_TIMEOUT_SECONDS = 1140
LOCAL_PROXY_BYPASS_HOSTS = ("localhost", "127.0.0.1")


class MinerUProcessError(RuntimeError):
    def __init__(self, message: str, details: dict):
        self.details = details
        super().__init__(message)

MINERU_LANGUAGE_ALIASES = {
    "zh": "ch",
    "zh-cn": "ch",
    "zh_cn": "ch",
    "cn": "ch",
    "chinese": "ch",
    "simplified_chinese": "ch",
    "zh-hans": "ch",
    "zh_hans": "ch",
    "zh-tw": "chinese_cht",
    "zh_tw": "chinese_cht",
    "zh-hk": "chinese_cht",
    "zh_hk": "chinese_cht",
    "traditional_chinese": "chinese_cht",
}


@dataclass(frozen=True)
class MinerUOutputs:
    md_path: Path | None
    content_list: Path | None
    content_list_v2: Path | None
    middle_json: Path | None


def find_mineru() -> str:
    """Find the MinerU executable installed beside the selected Python runtime.

    Deliberately does NOT fall back to a system MinerU on PATH: KBPrep only
    trusts the MinerU pinned inside the selected Python environment so that
    conversion behaviour stays reproducible. This constraint is guarded by
    src/test/scenarios/worker-core-runtime-part1.test.ts.
    """
    import sys
    python_dir = Path(sys.executable).parent
    for name in ["mineru", "mineru.exe"]:
        candidate = python_dir / name
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(f"mineru not found in selected Python environment: {python_dir}")


def normalize_mineru_language(language: str | None) -> str:
    """Map common user-facing language hints to MinerU CLI language codes."""
    alias = MINERU_LANGUAGE_ALIASES.get(language.strip().lower(), language) if language else None
    return normalize_language_hint(alias)


def mineru_timeout_seconds() -> int:
    raw = os.environ.get("KBPREP_MINERU_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_MINERU_TIMEOUT_SECONDS
    try:
        value = int(float(raw))
    except ValueError:
        return DEFAULT_MINERU_TIMEOUT_SECONDS
    return max(30, value)


def run_mineru(
    input_path: str,
    output_dir: str,
    language: str = "en",
    mode: str = "auto",
    keep_debug_files: bool = False,
) -> dict:
    """
    Run MinerU on a single file.

    Returns dict with:
        source_md_path, content_list_path, content_list_v2_path,
        middle_json_path, assets_dir, warnings
    """
    mineru = find_mineru()
    input_p = Path(input_path)
    output_p = Path(output_dir)
    output_p.mkdir(parents=True, exist_ok=True)

    stem = input_p.stem
    assets_dir = output_p / "mineru_raw"
    assets_dir.mkdir(parents=True, exist_ok=True)

    timeout_seconds = mineru_timeout_seconds()
    cmd = _mineru_command(mineru, input_p, assets_dir, mode, language)

    logger.info("Running MinerU: %s", " ".join(cmd))
    result = _run_mineru_command(cmd, input_p, timeout_seconds)
    _raise_for_mineru_failure(result, timeout_seconds, cmd)

    outputs = _locate_mineru_outputs(assets_dir, stem, input_p)
    if outputs.md_path is None:
        raise RuntimeError(f"MinerU did not produce a .md file for {input_p.name}")
    final_md = _copy_mineru_markdown(outputs.md_path, output_p)
    if not keep_debug_files:
        _cleanup_mineru_debug_files(assets_dir)
    return _mineru_result_payload(final_md, outputs, assets_dir, timeout_seconds, cmd)


def _mineru_command(mineru: str, input_p: Path, assets_dir: Path, mode: str, language: str) -> list[str]:
    mineru_language = normalize_mineru_language(language)
    return [
        mineru,
        "-p", str(input_p),
        "-o", str(assets_dir),
        "-b", "pipeline",
        "-m", mode,
        "-l", mineru_language,
    ]


def _mineru_environment() -> dict[str, str]:
    env = os.environ.copy()
    _append_local_proxy_bypass(env)
    _apply_optional_mineru_tools_source(env)
    device = detect_device()
    env["MINERU_DEVICE_MODE"] = device
    if device == "cpu":
        env["TORCH_NUM_THREADS"] = os.environ.get("TORCH_NUM_THREADS", "4")
        env["OMP_NUM_THREADS"] = os.environ.get("OMP_NUM_THREADS", "4")
        logger.warning("Running MinerU in CPU mode. Install CUDA torch for GPU acceleration.")
    else:
        logger.info("Running MinerU on device: %s", device)
    return env


def _append_local_proxy_bypass(env: dict[str, str]) -> None:
    hosts = _merged_proxy_bypass_hosts(env.get("NO_PROXY") or env.get("no_proxy", ""))
    joined = ",".join(hosts)
    env["NO_PROXY"] = joined
    env["no_proxy"] = joined


def _merged_proxy_bypass_hosts(existing: str) -> tuple[str, ...]:
    values = [item.strip() for item in existing.split(",") if item.strip()]
    for host in LOCAL_PROXY_BYPASS_HOSTS:
        if host not in values:
            values.append(host)
    return tuple(values)


def _apply_optional_mineru_tools_source(env: dict[str, str]) -> None:
    override = os.environ.get("KBPREP_MINERU_TOOLS_SOURCE", "").strip()
    if override:
        env["MINERU_TOOLS_SOURCE"] = override


def _mineru_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "IDLE_PRIORITY_CLASS", 0)}


def _run_mineru_command(cmd: list[str], input_p: Path, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(input_p.parent),
            env=_mineru_environment(),
            **_mineru_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"MinerU timed out after {timeout_seconds}s processing {input_p.name}"
        ) from exc


def _raise_for_mineru_failure(
    result: subprocess.CompletedProcess[str],
    timeout_seconds: int,
    cmd: list[str],
) -> None:
    if result.returncode == 0:
        return
    stderr_tail = result.stderr.strip().split("\n")[-20:] if result.stderr else []
    raise MinerUProcessError(
        f"MinerU exited with code {result.returncode}: {'; '.join(stderr_tail)}",
        details={
            "mineru_exit_code": result.returncode,
            "mineru_stderr_tail": stderr_tail,
            "mineru_stdout_tail": result.stdout.strip().split("\n")[-20:] if result.stdout else [],
            "mineru_timeout_seconds": timeout_seconds,
            "mineru_command": _command_for_report(cmd),
        },
    )


def _locate_mineru_outputs(assets_dir: Path, stem: str, input_p: Path) -> MinerUOutputs:
    possible_roots = [
        assets_dir / stem,
        assets_dir / stem / "auto",
        assets_dir / stem / "ocr",
        assets_dir / "auto" / stem,
        assets_dir / "ocr" / stem,
    ]

    md_path = None
    content_list = None
    content_list_v2 = None
    middle_json = None

    for root in possible_roots:
        root_outputs = _mineru_outputs_from_root(root, stem)
        md_path = root_outputs.md_path or md_path
        content_list = root_outputs.content_list or content_list
        content_list_v2 = root_outputs.content_list_v2 or content_list_v2
        middle_json = root_outputs.middle_json or middle_json

    if md_path is None:
        for f in assets_dir.rglob(f"{stem}.md"):
            md_path = f
            break

    if md_path is None:
        raise RuntimeError(f"MinerU did not produce a .md file for {input_p.name}")
    return MinerUOutputs(md_path, content_list, content_list_v2, middle_json)


def _mineru_outputs_from_root(root: Path, stem: str) -> MinerUOutputs:
    if not root.exists():
        return MinerUOutputs(None, None, None, None)
    md_path = root / f"{stem}.md" if (root / f"{stem}.md").exists() else None
    content_list = None
    content_list_v2 = None
    middle_json = None
    for file_path in root.iterdir():
        name = file_path.name
        if name.endswith("_content_list_v2.json"):
            content_list_v2 = file_path
        elif name.endswith("_content_list.json"):
            content_list = file_path
        elif name.endswith("_middle.json"):
            middle_json = file_path
    return MinerUOutputs(md_path, content_list, content_list_v2, middle_json)


def _copy_mineru_markdown(md_path: Path, output_p: Path) -> Path:
    final_md = output_p / "source.md"
    atomic_write_text(final_md, md_path.read_text(encoding="utf-8"))
    return final_md


def _cleanup_mineru_debug_files(assets_dir: Path) -> None:
    for pdf_file in assets_dir.rglob("*.pdf"):
        if pdf_file.name.endswith("_layout.pdf") or pdf_file.name.endswith("_span.pdf"):
            pdf_file.unlink(missing_ok=True)


def _mineru_result_payload(
    final_md: Path,
    outputs: MinerUOutputs,
    assets_dir: Path,
    timeout_seconds: int,
    cmd: list[str],
) -> dict:
    warnings: list[str] = []
    if outputs.content_list is None and outputs.content_list_v2 is None:
        warnings.append("MinerU did not produce content_list files. Page-level hints unavailable for splitting.")
    return {
        "source_md_path": str(final_md),
        "content_list_path": str(outputs.content_list) if outputs.content_list else None,
        "content_list_v2_path": str(outputs.content_list_v2) if outputs.content_list_v2 else None,
        "middle_json_path": str(outputs.middle_json) if outputs.middle_json else None,
        "assets_dir": str(assets_dir),
        "warnings": warnings,
        "mineru_timeout_seconds": timeout_seconds,
        "mineru_command": _command_for_report(cmd),
    }


def _command_for_report(cmd: list[str]) -> list[str]:
    return [str(part) for part in cmd]
