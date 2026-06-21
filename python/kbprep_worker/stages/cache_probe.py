"""Cache probe cleanup helpers for the prepare pipeline."""
from __future__ import annotations

from pathlib import Path

from ..fs_safety import safe_rmtree


def discard_cache_probe_run(run_dir: Path | None, runs_dir: Path | None, existing_run_dir: Path) -> None:
    if not isinstance(run_dir, Path) or not isinstance(runs_dir, Path):
        return
    if run_dir.resolve() == existing_run_dir.resolve() or not run_dir.exists():
        return
    try:
        run_dir.resolve().relative_to(runs_dir.resolve())
    except ValueError:
        return
    safe_rmtree(run_dir, root=runs_dir)
