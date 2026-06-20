"""Runtime metadata helpers for the single-file prepare pipeline."""

import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys


def check_env(profile: str) -> list[str]:
    warnings: list[str] = []
    return warnings


def get_mineru_version() -> str:
    metadata_version = _mineru_package_version()
    if metadata_version:
        return metadata_version
    try:
        from .mineru_adapter import find_mineru
        mineru = find_mineru()
        result = subprocess.run([mineru, "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip().split()[-1]
    except Exception:
        pass
    return "unknown"


def _mineru_package_version() -> str | None:
    try:
        return importlib.metadata.version("mineru")
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None


def runtime_snapshot(mineru_version: str) -> dict:
    runtime = {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_executable": sys.executable,
        "mineru_version": mineru_version,
        "mineru_path": None,
        "torch": "not installed",
        "torch_cuda_available": False,
        "torch_cuda_version": "not installed",
        "torch_device_count": 0,
        "mineru_device": "unknown",
    }
    try:
        from .mineru_adapter import find_mineru
        runtime["mineru_path"] = find_mineru()
    except Exception:
        pass
    try:
        import torch
        runtime["torch"] = str(torch.__version__)
        runtime["torch_cuda_available"] = bool(torch.cuda.is_available())
        runtime["torch_cuda_version"] = torch.version.cuda or "none"
        runtime["torch_device_count"] = int(torch.cuda.device_count())
        if torch.cuda.is_available():
            runtime["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    try:
        from .setup_env import detect_device
        runtime["mineru_device"] = detect_device()
    except Exception:
        pass
    return runtime


def runtime_cache_key(runtime: dict) -> str:
    """Build a stable cache key for outputs that can change with runtime selection."""
    identity = {
        "python_executable": runtime.get("python_executable"),
        "mineru_path": runtime.get("mineru_path"),
        "mineru_version": runtime.get("mineru_version"),
        "torch": runtime.get("torch"),
        "torch_cuda_available": runtime.get("torch_cuda_available"),
        "torch_cuda_version": runtime.get("torch_cuda_version"),
        "mineru_device": runtime.get("mineru_device"),
    }
    payload = json.dumps(identity, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def mineru_timeout_seconds_from_env() -> int | None:
    raw = os.environ.get("KBPREP_MINERU_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None
