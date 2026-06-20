"""Error report helpers for the single-file prepare pipeline."""

from __future__ import annotations

from pathlib import Path

from .atomic_io import atomic_write_json


def write_error_report_from_context(
    context: dict,
    code: str,
    message: str,
    warnings: list[str],
    traceback_text: str | None = None,
) -> dict:
    """Persist failure evidence when a run directory already exists."""
    run_dir = context.get("run_dir")
    if not isinstance(run_dir, Path):
        return {}

    input_p = context.get("input_p")
    root_p = context.get("root_p")
    original_file = context.get("original_file")
    report = {
        "schema": "kbprep.error_report.v1",
        "code": code,
        "message": message,
        "input_path": str(input_p) if isinstance(input_p, Path) else None,
        "output_root": str(root_p) if isinstance(root_p, Path) else None,
        "run_dir": str(run_dir),
        "original_file": str(original_file) if isinstance(original_file, Path) and original_file.exists() else None,
        "source_sha256": context.get("file_hash", ""),
        "source_type": context.get("source_type", "unknown"),
        "plugin_version": context.get("plugin_version", "unknown"),
        "mineru_version": context.get("mineru_version", "unknown"),
        "runtime": context.get("runtime", {}),
        "diagnosis": context.get("diagnosis", {}),
        "warnings": warnings,
    }
    if traceback_text:
        report["traceback_tail"] = traceback_text.splitlines()[-40:]

    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        error_report = run_dir / "error_report.json"
        atomic_write_json(error_report, report, indent=2, trailing_newline=False)
        return {
            "run_dir": str(run_dir),
            "original_file": report["original_file"],
            "error_report": str(error_report),
            "runtime": report["runtime"],
            "diagnosis": report["diagnosis"],
        }
    except Exception as report_error:
        return {
            "run_dir": str(run_dir),
            "error_report_error": str(report_error),
        }
