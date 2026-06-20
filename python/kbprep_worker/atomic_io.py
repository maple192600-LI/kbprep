"""Atomic file writes for KBPrep worker artifacts.

Writes go to a same-directory tempfile, fsync, then ``os.replace`` onto the
target so readers never observe a partial file. Interruption (Ctrl-C, power
loss) leaves either the previous full file or nothing — never a half-written
file that would break downstream reads (latest.json, manifests, reports).

Use these instead of ``Path.write_text`` / ``write_bytes`` for any artifact
whose corruption would break a later read.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_REPLACE_RETRY_ATTEMPTS = 50
_REPLACE_RETRY_DELAY_SECONDS = 0.002


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    fsync_file: bool = True,
    fsync_dir: bool = True,
) -> None:
    """Atomically write ``text`` to ``path`` (UTF-8 by default)."""
    data = text.encode(encoding)
    _atomic_replace_bytes(path, data, fsync_file=fsync_file, fsync_dir=fsync_dir)


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    fsync_file: bool = True,
    fsync_dir: bool = True,
) -> None:
    """Atomically write raw ``data`` to ``path``."""
    _atomic_replace_bytes(path, data, fsync_file=fsync_file, fsync_dir=fsync_dir)


def atomic_write_json(
    path: Path,
    obj: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
    encoding: str = "utf-8",
    trailing_newline: bool = True,
    fsync_file: bool = True,
    fsync_dir: bool = True,
) -> None:
    """Atomically serialize ``obj`` to JSON and write to ``path``.

    Serializes to a string first so a serialization error never leaves a
    partial file on disk.
    """
    text = json.dumps(obj, indent=indent, ensure_ascii=ensure_ascii)
    if trailing_newline:
        text += "\n"
    atomic_write_text(
        path,
        text,
        encoding=encoding,
        fsync_file=fsync_file,
        fsync_dir=fsync_dir,
    )


def _atomic_replace_bytes(
    target: Path,
    data: bytes,
    *,
    fsync_file: bool,
    fsync_dir: bool,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(
        f".{target.name}.tmp.{os.getpid()}.{threading.get_ident()}",
    )
    try:
        with tmp.open("wb") as handle:
            handle.write(data)
            if fsync_file:
                handle.flush()
                os.fsync(handle.fileno())
        _replace_with_retry(tmp, target)
        if fsync_dir:
            _fsync_dir(target.parent)
    except BaseException:
        # Cleanup must not mask the original error; only swallow OSError from
        # the unlink itself (this is not a bare except — we re-raise).
        with _suppress_oserror():
            tmp.unlink(missing_ok=True)
        raise


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of the parent directory so the rename is durable.

    Some platforms (and CI containers) reject fsync on directory fds; that is
    not fatal, so failures are swallowed.
    """
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def _replace_with_retry(tmp: Path, target: Path) -> None:
    for attempt in range(_REPLACE_RETRY_ATTEMPTS):
        try:
            os.replace(tmp, target)
            return
        except PermissionError as exc:
            if not _should_retry_replace(exc, attempt):
                raise
            time.sleep(_REPLACE_RETRY_DELAY_SECONDS)


def _should_retry_replace(exc: PermissionError, attempt: int) -> bool:
    is_last_attempt = attempt >= _REPLACE_RETRY_ATTEMPTS - 1
    if is_last_attempt:
        return False
    return os.name == "nt" and getattr(exc, "winerror", None) == 5


@contextmanager
def _suppress_oserror() -> Iterator[None]:
    try:
        yield
    except OSError:
        pass
