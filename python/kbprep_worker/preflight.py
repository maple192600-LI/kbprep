"""
preflight - check KBPrep-local Python, MinerU availability, GPU/CUDA, and workspace permissions.
"""

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text
from .envelope import fail, ok
from .mineru_adapter import find_mineru
from .setup_env import detect_device

logger = logging.getLogger(__name__)


def run(data: dict) -> None:
    workspace_path = str(data.get("workspace_path") or ".")
    profile = str(data.get("profile") or "lite")

    warnings: list[str] = []
    errors: list[str] = []
    versions: dict[str, Any] = {}

    _record_python_versions(versions)
    versions["runtime_isolated"] = True
    _record_pymupdf_versions(versions, warnings)
    _record_mineru_versions(versions, errors)
    _record_torch_versions(versions, warnings)
    _record_mineru_device(versions, warnings)
    _record_model_cache(versions, warnings)
    _record_memory_or_disk(versions, workspace_path)
    _check_workspace_writable(workspace_path, errors)
    _check_disk_space(workspace_path, profile, versions, errors, warnings)

    if errors:
        fail("KBPREP_WORKER_NOT_READY", "; ".join(errors), details={"versions": versions}, warnings=warnings)
    else:
        ok(data={"ok": True, "versions": versions, "warnings": warnings, "errors": errors})


def _record_python_versions(versions: dict[str, Any]) -> None:
    versions["python"] = sys.version.split()[0]
    versions["python_executable"] = sys.executable


def _record_pymupdf_versions(versions: dict[str, Any], warnings: list[str]) -> None:
    try:
        import fitz  # PyMuPDF

        versions["pymupdf"] = getattr(fitz, "__version__", "unknown")
        versions["pdf_text_layer_available"] = True
    except ImportError:
        versions["pymupdf"] = "not installed"
        versions["pdf_text_layer_available"] = False
        warnings.append(
            "PyMuPDF not installed. Trusted text-layer PDFs cannot use the lightweight "
            "pdf_text_layer route in this Python environment."
        )


def _record_mineru_versions(versions: dict[str, Any], errors: list[str]) -> None:
    try:
        mineru_path = find_mineru()
        versions["mineru_path"] = mineru_path
        versions["mineru"] = _mineru_version(mineru_path)
    except FileNotFoundError:
        errors.append(
            "MinerU not found for the selected Python environment. "
            "Run kbprep_preflight again after the KBPrep-local .kbprep/venv setup finishes, "
            "or reinstall KBPrep if the environment is incomplete."
        )


def _mineru_version(mineru_path: str) -> str:
    try:
        result = subprocess.run([mineru_path, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except Exception:
        return "error"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _record_torch_versions(versions: dict[str, Any], warnings: list[str]) -> None:
    try:
        import torch

        torch_version = f"{torch.__version__}"
        versions["torch_cuda_available"] = bool(torch.cuda.is_available())
        versions["torch_cuda_version"] = torch.version.cuda or "none"
        versions["torch_device_count"] = int(torch.cuda.device_count())
        if torch.version.cuda:
            torch_version += f"+cuda{torch.version.cuda}"
            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(0)
                versions["torch"] = torch_version
                versions["gpu_name"] = torch.cuda.get_device_name(0)
                versions["gpu_vram_gb"] = f"{props.total_memory / 1024**3:.1f}"
                versions["gpu_count"] = str(torch.cuda.device_count())
            else:
                versions["torch"] = torch_version
                warnings.append("torch has CUDA support but no GPU is available.")
        else:
            versions["torch"] = f"{torch_version}+cpu"
            nvidia_smi = shutil.which("nvidia-smi")
            if nvidia_smi:
                versions["nvidia_smi_path"] = nvidia_smi
                warnings.append(
                    "NVIDIA GPU detected but torch is CPU-only. "
                    "The KBPrep setup step will try to install CUDA torch inside its own .kbprep/venv only."
                )
    except ImportError:
        versions["torch"] = "not installed"
        versions["torch_cuda_available"] = False
        versions["torch_cuda_version"] = "not installed"
        versions["torch_device_count"] = 0


def _record_mineru_device(versions: dict[str, Any], warnings: list[str]) -> None:
    device = detect_device()
    versions["mineru_device"] = device
    if device == "cpu":
        warnings.append("MinerU will run in CPU mode. GPU acceleration recommended for faster processing.")


def _record_model_cache(versions: dict[str, Any], warnings: list[str]) -> None:
    try:
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        main_model = hf_cache / "models--opendatalab--PDF-Extract-Kit-1.0"
        has_main = main_model.exists() and (main_model / "blobs").exists() and any((main_model / "blobs").iterdir())
        if has_main:
            blob_size = sum(f.stat().st_size for f in (main_model / "blobs").iterdir() if f.is_file())
            versions["mineru_models_cached"] = f"PDF-Extract-Kit-1.0 ({blob_size / 1024**3:.1f} GB)"
        else:
            warnings.append(
                "MinerU model pack (PDF-Extract-Kit-1.0) not cached. "
                "First run will download ~2GB from HuggingFace. "
                "Set HTTP_PROXY/HTTPS_PROXY if behind a firewall."
            )
            versions["mineru_models_cached"] = "none"
    except Exception:
        warnings.append("Could not check MinerU model cache.")


def _record_memory_or_disk(versions: dict[str, Any], workspace_path: str) -> None:
    try:
        import psutil

        mem = psutil.virtual_memory()
        versions["memory_total_gb"] = f"{mem.total / 1024**3:.1f}"
        versions["memory_available_gb"] = f"{mem.available / 1024**3:.1f}"
    except ImportError:
        try:
            usage = shutil.disk_usage(str(Path(workspace_path)))
            versions["disk_free_gb"] = f"{usage.free / 1024**3:.1f}"
        except Exception:
            logger.debug("disk usage probe failed for %s", workspace_path, exc_info=True)


def _check_workspace_writable(workspace_path: str, errors: list[str]) -> None:
    ws = Path(workspace_path)
    try:
        ws.mkdir(parents=True, exist_ok=True)
        test_file = ws / ".kbprep_write_test"
        atomic_write_text(test_file, "ok")
        test_file.unlink()
    except Exception as e:
        errors.append(f"Workspace not writable: {e}")


def _check_disk_space(
    workspace_path: str,
    profile: str,
    versions: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    ws = Path(workspace_path)
    try:
        usage = shutil.disk_usage(str(ws))
        free_gb = usage.free / (1024**3)
        versions["disk_free_gb"] = f"{free_gb:.1f}"
        min_gb = 25 if profile == "standard" else 2
        if free_gb < min_gb:
            errors.append(f"Disk space low: {free_gb:.1f} GB free, need {min_gb} GB")
    except Exception:
        warnings.append("Could not check disk space.")
