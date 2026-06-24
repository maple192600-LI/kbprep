"""Directory batch processing with sample-first safety."""
import gc
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .atomic_io import atomic_write_json
from .batch_manifest import batch_parent_status, write_batch_manifest
from .envelope import fail, ok
from .supported_formats import (
    BATCH_SUPPORTED_EXTENSIONS,
    FORMAT_BY_EXTENSION,
    IMAGE_EXTENSIONS,
    LEGACY_OFFICE_EXTENSIONS,
    MEDIA_EXTENSIONS,
    MINERU_EXTENSIONS,
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = BATCH_SUPPORTED_EXTENSIONS
HEAVY_CONVERSION_EXTENSIONS = MINERU_EXTENSIONS | IMAGE_EXTENSIONS | LEGACY_OFFICE_EXTENSIONS

DEFAULT_MIN_FREE_GB = 4.0
DEFAULT_MAX_QUALITY_ITERATIONS = 3

IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".nuxt",
}


@dataclass(frozen=True)
class BatchConfig:
    input_dir: str
    output_root: str
    profile: str
    language: str
    mode: str
    force: bool
    artifact_policy: str
    max_quality_iterations: int | str | None
    min_free_gb: float
    convert_jobs: int


def _available_memory_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / (1024**3)
    except ImportError:
        return 999.0


def _process_one_file(file_path: Path, output_root: str, profile: str,
                      language: str, mode: str, force: bool, artifact_policy: str = "keep_latest",
                      max_quality_iterations: int | str | None = DEFAULT_MAX_QUALITY_ITERATIONS) -> dict:
    payload = {
        "input_path": str(file_path),
        "output_root": output_root,
        "profile": profile,
        "mode": mode,
        "language": language,
        "source_type": "auto",
        "splitter": "auto",
        "force": force,
        "artifact_policy": artifact_policy,
        "max_quality_iterations": max_quality_iterations,
    }
    proc = subprocess.run(
        [sys.executable, "-m", "kbprep_worker.cli", "prepare", "--json-stdin"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        env=_child_env(),
        timeout=5400,
    )
    stdout = proc.stdout.strip()
    if not stdout:
        return {
            "ok": False,
            "error": {
                "code": "E_WORKER_BAD_JSON",
                "message": "No stdout from prepare subprocess",
                "stderr_tail": proc.stderr.splitlines()[-20:],
            },
        }
    try:
        return json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "error": {
                "code": "E_WORKER_BAD_JSON",
                "message": str(exc),
                "stdout_preview": stdout[:500],
                "stderr_tail": proc.stderr.splitlines()[-20:],
            },
        }


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("KBPREP_PROJECT_ROOT", str(Path.cwd()))
    return env


def _safe_output_dir_name(file_path: Path) -> str:
    stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", file_path.stem).strip("._-")
    if not stem:
        stem = "source"
    digest = hashlib.sha256(str(file_path.resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{stem}_{digest}"


def _output_root_for_file(batch_output_root: Path, file_path: Path) -> Path:
    return batch_output_root / "files" / _safe_output_dir_name(file_path)


def _batch_final_fields_from_result(data: dict) -> dict:
    latest_outputs = data.get("latest_outputs", {})
    if not isinstance(latest_outputs, dict):
        return {}
    artifact_type = latest_outputs.get("final_artifact_type")
    final_md = latest_outputs.get("final_md")
    if artifact_type == "markdown" or final_md:
        if final_md and Path(final_md).exists():
            return {
                "final_artifact_type": "markdown",
                "batch_final_md": final_md,
            }
        return {}

    obsidian_dir = latest_outputs.get("obsidian_dir")
    obsidian_index = latest_outputs.get("obsidian_index")
    obsidian_complete = latest_outputs.get("obsidian_complete")
    if artifact_type == "obsidian_dir" or obsidian_dir or obsidian_index:
        if obsidian_dir and obsidian_index and Path(obsidian_dir).is_dir() and Path(obsidian_index).is_file():
            fields = {
                "final_artifact_type": "obsidian_dir",
                "batch_obsidian_dir": obsidian_dir,
                "batch_obsidian_index": obsidian_index,
            }
            if obsidian_complete and Path(obsidian_complete).is_file():
                fields["batch_obsidian_complete"] = obsidian_complete
            return fields
    return {}


def _write_progress(output_root: Path, payload: dict) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        output_root / "progress.json",
        payload,
        indent=2,
        trailing_newline=False,
    )


def _write_failures(output_root: Path, failures: list[dict]) -> None:
    atomic_write_json(
        output_root / "failures.json",
        failures,
        indent=2,
        trailing_newline=False,
    )


def _scan_input_files(input_p: Path) -> tuple[list[Path], dict]:
    files: list[Path] = []
    entries: list[dict] = []
    skipped_unsupported = 0

    for file_path in _iter_source_files(input_p):
        ext = file_path.suffix.lower()
        detected_format = FORMAT_BY_EXTENSION.get(ext, "unknown")
        relative_path = file_path.relative_to(input_p).as_posix()
        entry = {
            "file": file_path.name,
            "relative_path": relative_path,
            "extension": ext,
            "detected_format": detected_format,
            "size_bytes": file_path.stat().st_size,
            "conversion_weight": "heavy" if _is_heavy_conversion_file(file_path) else "light",
        }
        if ext in SUPPORTED_EXTENSIONS:
            entry["action"] = "process"
            files.append(file_path)
        else:
            entry["action"] = "skip"
            skipped_unsupported += 1
            if ext in MEDIA_EXTENSIONS:
                entry["reason"] = "media_binary_not_transcribed_in_v1"
            else:
                entry["reason"] = f"unsupported_extension:{ext or '<none>'}"
        entries.append(entry)

    inventory = {
        "input_dir": str(input_p),
        "discovered_total": len(entries),
        "processable_total": len(files),
        "skipped_unsupported": skipped_unsupported,
        "files": entries,
    }
    return files, inventory


def _iter_source_files(root: Path) -> Iterator[Path]:
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if child.is_symlink():
            continue
        if child.is_dir():
            if child.name.lower() in IGNORED_DIRECTORY_NAMES:
                continue
            yield from _iter_source_files(child)
        elif child.is_file():
            yield child


def _write_batch_inventory(output_root: Path, inventory: dict) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "batch_inventory.json"
    atomic_write_json(path, inventory, indent=2, trailing_newline=False)
    return path


def _is_heavy_conversion_file(file_path: Path) -> bool:
    return file_path.suffix.lower() in HEAVY_CONVERSION_EXTENSIONS


def run(data: dict) -> None:
    config = _batch_config(data)
    input_p, output_p = _batch_paths_or_fail(config)
    files, inventory = _scan_input_files(input_p)
    inventory_path = _write_batch_inventory(output_p, inventory)
    _ensure_batch_files_or_fail(files, inventory, inventory_path, config.input_dir)
    _ensure_batch_memory(config.min_free_gb)
    started_at = time.time()
    results: list[dict] = []
    failures: list[dict] = []
    relative_paths = {file_path: file_path.relative_to(input_p).as_posix() for file_path in files}

    sample_result = _process_batch_sample(
        config, input_p, files, output_p, inventory, relative_paths, started_at, results, failures,
    )
    remaining = files[1:]
    counters = {
        "succeeded": 1,
        "skipped": 1 if sample_result.get("data", {}).get("skipped") else 0,
        "failed": 0,
    }
    heavy_files = [file_path for file_path in files if _is_heavy_conversion_file(file_path)]
    heavy_remaining = [file_path for file_path in remaining if _is_heavy_conversion_file(file_path)]
    light_remaining = [file_path for file_path in remaining if not _is_heavy_conversion_file(file_path)]

    _process_heavy_batch_files(config, heavy_remaining, output_p, _record_context(
        files, inventory, relative_paths, heavy_files, light_remaining, started_at, results, failures, counters,
    ))
    max_workers = _process_light_batch_files(config, light_remaining, output_p, _record_context(
        files, inventory, relative_paths, heavy_files, light_remaining, started_at, results, failures, counters,
    ))
    manifest_path = _write_batch_complete(output_p, input_p, files, inventory, started_at, results, failures, counters)
    _emit_batch_result(
        output_p, files, inventory, inventory_path, manifest_path, results, failures, counters, heavy_files, max_workers,
    )


def _batch_config(data: dict) -> BatchConfig:
    return BatchConfig(
        input_dir=str(data["input_dir"]),
        output_root=str(data["output_root"]),
        profile=str(data.get("profile", "standard")),
        language=str(data.get("language", "auto")),
        mode=str(data.get("mode", "rules_only")),
        force=bool(data.get("force", False)),
        artifact_policy=str(data.get("artifact_policy", "keep_latest")),
        max_quality_iterations=data.get("max_quality_iterations", DEFAULT_MAX_QUALITY_ITERATIONS),
        min_free_gb=float(data.get("min_free_memory_gb", DEFAULT_MIN_FREE_GB)),
        convert_jobs=int(data.get("convert_jobs", 1)),
    )


def _batch_paths_or_fail(config: BatchConfig) -> tuple[Path, Path]:
    input_p = Path(config.input_dir)
    output_p = Path(config.output_root)
    if not input_p.exists() or not input_p.is_dir():
        fail("E_INVALID_INPUT", f"input_dir does not exist or is not a directory: {config.input_dir}")
    return input_p, output_p


def _ensure_batch_files_or_fail(files: list[Path], inventory: dict, inventory_path: Path, input_dir: str) -> None:
    if files:
        return
    fail(
        "E_INVALID_INPUT",
        f"No supported files found in {input_dir}",
        details={
            "batch_inventory_json": str(inventory_path),
            "discovered_total": inventory["discovered_total"],
            "skipped_unsupported": inventory["skipped_unsupported"],
        },
    )


def _ensure_batch_memory(min_free_gb: float) -> None:
    available = _available_memory_gb()
    if available >= min_free_gb:
        return
    gc.collect()
    available = _available_memory_gb()
    if available < min_free_gb / 2:
        fail(
            "KBPREP_OOM_RISK",
            f"Insufficient memory ({available:.1f} GB free, need {min_free_gb:.1f} GB).",
            details={"available_gb": round(available, 1)},
        )


def _process_batch_sample(
    config: BatchConfig,
    input_p: Path,
    files: list[Path],
    output_p: Path,
    inventory: dict,
    relative_paths: dict[Path, str],
    started_at: float,
    results: list[dict],
    failures: list[dict],
) -> dict:
    sample = files[0]
    _write_sample_progress(output_p, files, inventory, relative_paths[sample], started_at)
    sample_output_root = _output_root_for_file(output_p, sample)
    sample_result = _process_configured_file(config, sample, sample_output_root)
    sample_data = sample_result.get("data", {})
    sample_entry = _result_entry(sample, relative_paths[sample], sample_output_root, sample_result)
    if sample_result.get("ok") and not sample_data.get("strict_errors"):
        sample_entry.update(_batch_final_fields_from_result(sample_data))
    results.append(sample_entry)
    if not sample_result.get("ok") or sample_result.get("data", {}).get("strict_errors"):
        _stop_after_failed_sample(
            output_p,
            input_p,
            files,
            inventory,
            sample,
            relative_paths[sample],
            sample_output_root,
            sample_result,
            failures,
            started_at,
        )
    return sample_result


def _write_sample_progress(
    output_p: Path,
    files: list[Path],
    inventory: dict,
    sample_relative_path: str,
    started_at: float,
) -> None:
    _write_progress(output_p, {
        "stage": "sample",
        "total": len(files),
        "discovered_total": inventory["discovered_total"],
        "skipped_unsupported": inventory["skipped_unsupported"],
        "processed": 0,
        "sample_file": sample_relative_path,
        "started_at": started_at,
    })


def _stop_after_failed_sample(
    output_p: Path,
    input_p: Path,
    files: list[Path],
    inventory: dict,
    sample: Path,
    sample_relative_path: str,
    sample_output_root: Path,
    sample_result: dict,
    failures: list[dict],
    started_at: float,
) -> None:
    failures.append(_failure_entry(sample, sample_relative_path, sample_output_root, sample_result))
    _write_failures(output_p, failures)
    _write_progress(output_p, {
        "stage": "stopped_after_sample",
        "total": len(files),
        "discovered_total": inventory["discovered_total"],
        "skipped_unsupported": inventory["skipped_unsupported"],
        "processed": 1,
        "failed": 1,
        "started_at": started_at,
        "finished_at": time.time(),
    })
    manifest_path = write_batch_manifest(
        output_root=output_p,
        input_dir=input_p,
        inventory=inventory,
        results=[_result_entry(sample, sample_relative_path, sample_output_root, sample_result)],
        failures=failures,
        counters={"succeeded": 0, "skipped": 0, "failed": 1},
        started_at=started_at,
        stage="stopped_after_sample",
        finished_at=time.time(),
    )
    fail(
        "E_QA_FAILED",
        "Sample file failed. Batch stopped before processing remaining files.",
        details={"sample": sample.name, "result": sample_result, "batch_manifest_json": str(manifest_path)},
        warnings=sample_result.get("warnings", []),
    )


def _process_configured_file(config: BatchConfig, file_path: Path, output_root: Path) -> dict:
    return _process_one_file(
        file_path,
        str(output_root),
        config.profile,
        config.language,
        config.mode,
        config.force,
        config.artifact_policy,
        config.max_quality_iterations,
    )


def _record_context(
    files: list[Path],
    inventory: dict,
    relative_paths: dict[Path, str],
    heavy_files: list[Path],
    light_remaining: list[Path],
    started_at: float,
    results: list[dict],
    failures: list[dict],
    counters: dict[str, int],
) -> dict:
    return {
        "files": files,
        "inventory": inventory,
        "relative_paths": relative_paths,
        "heavy_files": heavy_files,
        "light_remaining": light_remaining,
        "started_at": started_at,
        "results": results,
        "failures": failures,
        "counters": counters,
    }


def _process_heavy_batch_files(config: BatchConfig, files: list[Path], output_p: Path, context: dict) -> None:
    for file_path in files:
        try:
            out = _process_configured_file(config, file_path, _output_root_for_file(output_p, file_path))
        except Exception as exc:
            out = {"ok": False, "error": {"message": str(exc)}}
        _record_batch_result(file_path, out, config, output_p, context)


def _process_light_batch_files(config: BatchConfig, files: list[Path], output_p: Path, context: dict) -> int:
    max_workers = max(1, min(config.convert_jobs, len(files) or 1))
    if not files:
        return max_workers
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(_process_configured_file, config, file_path, _output_root_for_file(output_p, file_path)): file_path
            for file_path in files
        }
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            try:
                out = future.result()
            except Exception as exc:
                out = {"ok": False, "error": {"message": str(exc)}}
            _record_batch_result(file_path, out, config, output_p, context)
    return max_workers


def _record_batch_result(file_path: Path, out: dict, config: BatchConfig, output_p: Path, context: dict) -> None:
    counters = context["counters"]
    relative_paths = context["relative_paths"]
    file_output_root = _output_root_for_file(output_p, file_path)
    if out.get("ok") and not out.get("data", {}).get("strict_errors"):
        counters["succeeded"] += 1
        if out.get("data", {}).get("skipped"):
            counters["skipped"] += 1
        entry = _result_entry(file_path, relative_paths[file_path], file_output_root, out)
        entry.update(_batch_final_fields_from_result(out.get("data", {})))
        context["results"].append(entry)
    else:
        counters["failed"] += 1
        failure = _failure_entry(file_path, relative_paths[file_path], file_output_root, out)
        context["failures"].append(failure)
        context["results"].append({"file": file_path.name, "ok": False, **failure})
    _write_batch_progress(output_p, config, context)
    _write_failures(output_p, context["failures"])


def _result_entry(file_path: Path, relative_path: str, output_root: Path, result: dict) -> dict:
    return {
        "file": file_path.name,
        "relative_path": relative_path,
        "output_root": str(output_root),
        **result.get("data", {}),
        "ok": result.get("ok", False),
    }


def _failure_entry(file_path: Path, relative_path: str, output_root: Path, result: dict) -> dict:
    return {
        "file": file_path.name,
        "relative_path": relative_path,
        "output_root": str(output_root),
        "error": result.get("error", {}),
        "data": result.get("data", {}),
    }


def _write_batch_progress(output_p: Path, config: BatchConfig, context: dict) -> None:
    counters = context["counters"]
    _write_progress(output_p, {
        "stage": "batch",
        "total": len(context["files"]),
        "discovered_total": context["inventory"]["discovered_total"],
        "skipped_unsupported": context["inventory"]["skipped_unsupported"],
        "processed": len(context["results"]),
        "succeeded": counters["succeeded"],
        "skipped": counters["skipped"],
        "failed": counters["failed"],
        "heavy_conversion_files": len(context["heavy_files"]),
        "heavy_conversion_concurrency": 1,
        "light_conversion_concurrency": max(1, min(config.convert_jobs, len(context["light_remaining"]) or 1)),
        "started_at": context["started_at"],
        "updated_at": time.time(),
    })


def _write_batch_complete(
    output_p: Path,
    input_p: Path,
    files: list[Path],
    inventory: dict,
    started_at: float,
    results: list[dict],
    failures: list[dict],
    counters: dict[str, int],
) -> Path:
    finished_at = time.time()
    _write_progress(output_p, {
        "stage": "complete",
        "total": len(files),
        "discovered_total": inventory["discovered_total"],
        "skipped_unsupported": inventory["skipped_unsupported"],
        "processed": len(results),
        "succeeded": counters["succeeded"],
        "skipped": counters["skipped"],
        "failed": counters["failed"],
        "started_at": started_at,
        "finished_at": finished_at,
    })
    _write_failures(output_p, failures)
    atomic_write_json(output_p / "results.json", results, indent=2, trailing_newline=False)
    return write_batch_manifest(
        output_root=output_p,
        input_dir=input_p,
        inventory=inventory,
        results=results,
        failures=failures,
        counters=counters,
        started_at=started_at,
        stage="complete",
        finished_at=finished_at,
    )


def _emit_batch_result(
    output_p: Path,
    files: list[Path],
    inventory: dict,
    inventory_path: Path,
    manifest_path: Path,
    results: list[dict],
    failures: list[dict],
    counters: dict[str, int],
    heavy_files: list[Path],
    max_workers: int,
) -> None:
    ok(data={
        "total": len(files),
        "discovered_total": inventory["discovered_total"],
        "succeeded": counters["succeeded"],
        "skipped": counters["skipped"],
        "skipped_unsupported": inventory["skipped_unsupported"],
        "failed": counters["failed"],
        "heavy_conversion_files": len(heavy_files),
        "heavy_conversion_concurrency": 1,
        "light_conversion_concurrency": max_workers,
        "results": results,
        "batch_inventory_json": str(inventory_path),
        "failures_json": str(output_p / "failures.json"),
        "progress_json": str(output_p / "progress.json"),
        "results_json": str(output_p / "results.json"),
        "batch_manifest_json": str(manifest_path),
        "files_dir": str(output_p / "files"),
    }, status=batch_parent_status(inventory, results, failures))
