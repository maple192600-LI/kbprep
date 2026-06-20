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


def setup_gpu(venv_python: str | None = None, device_override: str | None = None) -> dict:
    """Detect hardware and install CUDA torch into the KBPrep venv when appropriate."""
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
        return result

    if result["nvidia_driver"] and not result["torch_cuda"]:
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

    return result
