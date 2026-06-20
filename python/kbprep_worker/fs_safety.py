"""Safe filesystem deletion helpers for cleanup and publishing paths."""

from __future__ import annotations

import os
import shutil
import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


def safe_rmtree(
    path: Path,
    *,
    root: Path,
    dry_run: bool = False,
    retries: int = 2,
    retry_delay: float = 0.05,
) -> bool:
    """Remove a directory after proving it stays inside root.

    Returns True when the path exists and would be removed. Raises RuntimeError
    with a diagnostic message when removal fails after retries.
    """
    target = _resolve_inside_root(path, root)
    if not target.exists():
        return False
    if not target.is_dir():
        raise RuntimeError(f"Refusing to remove non-directory with safe_rmtree: {target}")
    if dry_run:
        return True

    attempts = max(1, retries)
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            shutil.rmtree(target, onerror=_make_writable)
            return True
        except Exception as exc:  # pragma: no cover - exercised by mocked failure.
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(max(0.0, retry_delay))
    raise RuntimeError(f"Failed to remove directory {target}: {last_error}") from last_error


def safe_unlink(path: Path, *, root: Path, dry_run: bool = False) -> bool:
    """Remove a file after proving it stays inside root."""
    target = _resolve_inside_root(path, root)
    if not target.exists():
        return False
    if target.is_dir():
        raise RuntimeError(f"Refusing to unlink directory with safe_unlink: {target}")
    if dry_run:
        return True
    try:
        target.unlink()
        return True
    except Exception as exc:
        raise RuntimeError(f"Failed to remove file {target}: {exc}") from exc


def _resolve_inside_root(path: Path, root: Path) -> Path:
    root_resolved = root.resolve()
    target = path.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise RuntimeError(f"Refusing to delete outside root: {target}")
    return target


_PROTECTED_DIRS: frozenset[str] = frozenset({
    "/etc", "/usr", "/var", "/bin", "/sbin", "/lib", "/boot", "/sys", "/proc", "/root",
    "C:/Windows", "C:/Program Files", "C:/Program Files (x86)", "C:/ProgramData",
})


def is_safe_output_root(output_root: Path) -> bool:
    """Return True unless output_root is a system root, user home, or protected OS dir.

    Conservative guard for the open-source CLI: rejects only obviously unsafe
    destinations so legitimate user-specified working directories always pass.
    """
    try:
        resolved = output_root.resolve()
    except (OSError, RuntimeError):
        return False
    if resolved == resolved.parent:
        return False
    try:
        if resolved == Path.home():
            return False
    except (OSError, RuntimeError):
        pass
    try:
        protected = {Path(item).resolve() for item in _PROTECTED_DIRS}
    except (OSError, RuntimeError):
        protected = set()
    return resolved not in protected


def is_safe_input_path(input_path: Path, *, max_size_mb: int = 1024) -> bool:
    """Return True unless input_path is a device file or implausibly large.

    Non-existence is not rejection here (the pipeline reports E_INPUT_NOT_FOUND
    separately).
    """
    try:
        resolved = input_path.resolve()
    except (OSError, RuntimeError):
        return False
    if not resolved.exists():
        return True
    if resolved.is_char_device() or resolved.is_block_device():
        return False
    try:
        if resolved.is_file() and resolved.stat().st_size > max_size_mb * 1024 * 1024:
            return False
    except OSError:
        return False
    return True


def _make_writable(function: Callable[..., object], path: str, excinfo: Any) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        function(path)
    except Exception:
        raise excinfo[1]
