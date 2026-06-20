"""Post-install hardware detection and KBPrep-local runtime tuning."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)

CUDA_TORCH_INDEX_URL = "https://download.pytorch.org/whl/cu126"
CUDA_TORCH_PACKAGES = ["torch>=2.8,<3", "torchvision>=0.23,<1"]
CUDA_TORCH_INSTALL_TIMEOUT_SECONDS = int(os.environ.get("KBPREP_CUDA_TORCH_INSTALL_TIMEOUT_SECONDS", "1500"))
MINERU_INSTALL_PACKAGES = ["mineru[all]>=3.2.1,<4"]
MINERU_INSTALL_TIMEOUT_SECONDS = int(os.environ.get("KBPREP_MINERU_INSTALL_TIMEOUT_SECONDS", "1800"))

# MinerU 运行时后端元数据（来源：MinerU 官方 README 硬件要求表，2026-06 no_cache 核查）。
# 安装统一用 mineru[all]（含所有核心）；这里描述的是运行时推理后端的选择维度。
MINERU_BACKENDS: tuple[dict[str, object], ...] = (
    {
        "key": "hybrid-engine",
        "label": "Hybrid 引擎（高精度 + 低幻觉）",
        "min_vram_gb": 8,
        "needs_gpu": True,
        "cpu_ok": False,
        "accuracy": "OmniDocBench v1.6 约 95.30",
        "best_for": "文本 PDF 原生抽取 + VLM 兜底，低幻觉；需要 NVIDIA 显存 ≥8GB",
    },
    {
        "key": "vlm-engine",
        "label": "VLM 引擎（高精度）",
        "min_vram_gb": 8,
        "needs_gpu": True,
        "cpu_ok": False,
        "accuracy": "OmniDocBench v1.6 约 95.39（high）/ 95.26（medium）",
        "best_for": "复杂版面、公式、表格的高精度解析；需要 NVIDIA 显存 ≥8GB",
    },
    {
        "key": "pipeline",
        "label": "Pipeline（兼容、可纯 CPU）",
        "min_vram_gb": 4,
        "needs_gpu": False,
        "cpu_ok": True,
        "accuracy": "OmniDocBench v1.6 约 86.47",
        "best_for": "兼容性最好、批量稳定；纯 CPU 也能跑；显存 ≥4GB 或无独显",
    },
    {
        "key": "http-client",
        "label": "HTTP 客户端（连远程服务）",
        "min_vram_gb": 2,
        "needs_gpu": False,
        "cpu_ok": True,
        "accuracy": "取决于远端服务",
        "best_for": "本地硬件不足时连远程 OpenAI 兼容服务；显存 ≥2GB",
    },
)


def check_nvidia_driver() -> bool:
    """Check if nvidia-smi is available."""
    return shutil.which("nvidia-smi") is not None


def _torch_probe_code() -> str:
    return """
import json
try:
    import torch
    payload = {
        "installed": True,
        "version": getattr(torch, "__version__", "unknown"),
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_version": torch.version.cuda or "none",
        "device_count": int(torch.cuda.device_count()),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
    }
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        payload["device_name"] = torch.cuda.get_device_name(0)
        payload["vram_gb"] = round(props.total_memory / 1024**3, 1)
except Exception as exc:
    payload = {"installed": False, "device": "cpu", "error": str(exc)}
print(json.dumps(payload, ensure_ascii=False))
""".strip()


def probe_torch(python: str | None = None) -> dict:
    """Probe torch in a fresh process so post-install checks are not stale."""
    interpreter = python or sys.executable
    try:
        proc = subprocess.run(
            [interpreter, "-c", _torch_probe_code()],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).splitlines()[-5:]
            return {"installed": False, "device": "cpu", "error": "\n".join(tail)}
        return json.loads(proc.stdout.strip() or "{}")
    except Exception as exc:
        return {"installed": False, "device": "cpu", "error": str(exc)}


def check_torch_cuda(python: str | None = None) -> bool:
    """Check if torch CUDA is available in the selected Python."""
    return bool(probe_torch(python).get("cuda_available"))


def get_gpu_info(python: str | None = None) -> dict:
    """Get GPU info from the selected Python environment."""
    probe = probe_torch(python)
    if probe.get("cuda_available"):
        return {
            "available": True,
            "device_name": probe.get("device_name", "unknown"),
            "vram_gb": probe.get("vram_gb"),
            "cuda_version": probe.get("cuda_version", "unknown"),
            "torch_version": probe.get("version", "unknown"),
        }
    return {"available": False}


def detect_device(python: str | None = None) -> str:
    """Detect best available compute device in the selected Python."""
    return str(probe_torch(python).get("device") or "cpu")


def mineru_backend_options() -> list[dict[str, object]]:
    """Return user-facing descriptions of every MinerU runtime backend."""
    return [
        {
            "key": b["key"],
            "label": b["label"],
            "min_vram_gb": b["min_vram_gb"],
            "needs_gpu": b["needs_gpu"],
            "cpu_ok": b["cpu_ok"],
            "accuracy": b["accuracy"],
            "best_for": b["best_for"],
        }
        for b in MINERU_BACKENDS
    ]


def suggest_mineru_backend(gpu_info: dict, prefer_high_accuracy: bool = True) -> tuple[str, str]:
    """Suggest a MinerU runtime backend from the GPU probe. Returns (backend_key, reason)."""
    if not gpu_info.get("available"):
        return "pipeline", "未检测到可用 GPU，建议 pipeline 后端（纯 CPU 也能跑，兼容性最好）。"
    vram = float(gpu_info.get("vram_gb") or 0)
    name = gpu_info.get("device_name") or "未知型号"
    if prefer_high_accuracy and vram >= 8:
        return (
            "hybrid-engine",
            f"检测到 NVIDIA GPU（{name}，{vram:.0f}GB 显存），建议 hybrid-engine（高精度 + 低幻觉，需 ≥8GB 显存）。",
        )
    if vram >= 4:
        return (
            "pipeline",
            f"检测到 NVIDIA GPU（{name}，{vram:.0f}GB 显存），显存 4-8GB 建议 pipeline 后端（GPU 加速、兼容稳定）。",
        )
    return "pipeline", f"检测到 GPU 但显存不足 4GB（{name}，{vram:.0f}GB），建议 pipeline 后端（纯 CPU 兼容）。"


def choose_mineru_backend(gpu_info: dict, backend_override: str | None) -> tuple[dict, list[str]]:
    """Pick the MinerU backend from hardware + optional override. Returns (payload, extra_actions)."""
    suggested, suggested_reason = suggest_mineru_backend(gpu_info)
    valid_keys = {str(b["key"]) for b in MINERU_BACKENDS}
    actions: list[str] = []
    if backend_override and backend_override in valid_keys:
        chosen, chosen_reason = backend_override, f"用户指定 backend_override={backend_override}"
    elif backend_override:
        chosen, chosen_reason = suggested, (
            f"backend_override={backend_override} 无效（可选：{', '.join(sorted(valid_keys))}），"
            f"回退到建议值 {suggested}"
        )
        actions.append(f"invalid_backend_override:{backend_override}")
    else:
        chosen, chosen_reason = suggested, suggested_reason
    return {
        "options": mineru_backend_options(),
        "suggested": suggested,
        "suggested_reason": suggested_reason,
        "chosen": chosen,
        "chosen_reason": chosen_reason,
    }, actions


def _install_cuda_torch(python: str, result: dict, actions_taken: list[str]) -> None:
    """Install CUDA torch into the venv when NVIDIA is present but torch lacks CUDA."""
    if not (result["nvidia_driver"] and not result["torch_cuda"]):
        return
    logger.info("NVIDIA GPU detected but torch lacks CUDA support. Installing CUDA torch...")
    try:
        subprocess.run(
            [
                python, "-m", "pip", "install",
                "--upgrade", "--force-reinstall",
                *CUDA_TORCH_PACKAGES,
                "--index-url", CUDA_TORCH_INDEX_URL,
            ],
            check=True,
            timeout=CUDA_TORCH_INSTALL_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )
        torch_probe = probe_torch(python)
        result["torch"] = torch_probe
        result["torch_cuda"] = bool(torch_probe.get("cuda_available"))
        result["gpu"] = get_gpu_info(python)
        result["device"] = str(torch_probe.get("device") or "cpu")
        actions_taken.append("installed_cuda_torch")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        actions_taken.append(f"cuda_install_failed: {exc}")


def install_mineru_all(python: str, actions_taken: list[str]) -> None:
    """Install mineru[all] into the venv. Call AFTER CUDA torch so pip keeps the CUDA build
    (otherwise a bare `pip install mineru[all]` pulls the Windows CPU torch from PyPI)."""
    try:
        subprocess.run(
            [python, "-m", "pip", "install", "--upgrade", *MINERU_INSTALL_PACKAGES],
            check=True,
            timeout=MINERU_INSTALL_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )
        actions_taken.append("installed_mineru_all")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        actions_taken.append(f"mineru_install_failed: {exc}")


def setup_gpu(
    venv_python: str | None = None,
    device_override: str | None = None,
    backend_override: str | None = None,
    install_mineru: bool = False,
) -> dict:
    """Detect hardware, install CUDA torch (and optionally mineru[all]), recommend a backend."""
    python = venv_python or sys.executable
    torch_probe = probe_torch(python)
    result: dict[str, object] = {
        "nvidia_driver": check_nvidia_driver(),
        "torch": torch_probe,
        "torch_cuda": bool(torch_probe.get("cuda_available")),
        "gpu": get_gpu_info(python),
        "device": str(torch_probe.get("device") or "cpu"),
        "device_override": device_override,
        "cuda_torch_index_url": CUDA_TORCH_INDEX_URL,
        "cuda_torch_packages": CUDA_TORCH_PACKAGES,
        "actions_taken": [],
    }

    actions_taken: list[str] = []
    result["actions_taken"] = actions_taken

    if device_override == "cpu":
        actions_taken.append("cuda_install_skipped_device_override_cpu")
        gpu_probe = result["gpu"] if isinstance(result["gpu"], dict) else {}
        result["mineru_backend"], backend_actions = choose_mineru_backend(gpu_probe, backend_override)
        actions_taken.extend(backend_actions)
        return result

    _install_cuda_torch(python, result, actions_taken)
    if install_mineru:
        install_mineru_all(python, actions_taken)
    gpu_probe = result["gpu"] if isinstance(result["gpu"], dict) else {}
    result["mineru_backend"], backend_actions = choose_mineru_backend(gpu_probe, backend_override)
    actions_taken.extend(backend_actions)
    return result
