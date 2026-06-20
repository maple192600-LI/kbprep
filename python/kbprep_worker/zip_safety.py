"""Shared ZIP safety checks for local archive-based converters."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import TracebackType

_ZIP_MIB = 1024 * 1024
_ZIP_READ_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ZipSafetyLimits:
    max_entries: int
    max_entry_uncompressed_bytes: int
    max_total_uncompressed_bytes: int


DEFAULT_ZIP_SAFETY_LIMITS = ZipSafetyLimits(
    max_entries=5000,
    max_entry_uncompressed_bytes=64 * _ZIP_MIB,
    max_total_uncompressed_bytes=512 * _ZIP_MIB,
)


class ZipSafetyError(ValueError):
    """Raised when a ZIP container exceeds local safety limits."""


class SafeZipReader:
    def __init__(
        self,
        archive: zipfile.ZipFile,
        limits: ZipSafetyLimits = DEFAULT_ZIP_SAFETY_LIMITS,
    ) -> None:
        _validate_limits(limits)
        self._archive = archive
        self._limits = limits
        self._infos = _validated_infos(archive.infolist(), limits)

    def __enter__(self) -> SafeZipReader:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._archive.close()

    def namelist(self) -> tuple[str, ...]:
        return tuple(self._infos)

    def has_entry(self, name: str) -> bool:
        return name in self._infos

    def read_bytes(self, name: str) -> bytes:
        info = self._info_for(name)
        return _read_limited(self._archive, info, self._limits.max_entry_uncompressed_bytes)

    def read_text(self, name: str, encoding: str = "utf-8", errors: str = "replace") -> str:
        return self.read_bytes(name).decode(encoding, errors=errors)

    def _info_for(self, name: str) -> zipfile.ZipInfo:
        try:
            return self._infos[name]
        except KeyError as error:
            raise KeyError(name) from error


def open_safe_zip(
    path: Path,
    limits: ZipSafetyLimits = DEFAULT_ZIP_SAFETY_LIMITS,
) -> SafeZipReader:
    archive = zipfile.ZipFile(path)
    try:
        return SafeZipReader(archive, limits)
    except Exception:
        archive.close()
        raise


def _validate_limits(limits: ZipSafetyLimits) -> None:
    values = (
        limits.max_entries,
        limits.max_entry_uncompressed_bytes,
        limits.max_total_uncompressed_bytes,
    )
    if any(value <= 0 for value in values):
        raise ValueError("ZIP safety limits must be positive integers.")


def _validated_infos(
    infos: list[zipfile.ZipInfo],
    limits: ZipSafetyLimits,
) -> dict[str, zipfile.ZipInfo]:
    if len(infos) > limits.max_entries:
        raise ZipSafetyError(f"ZIP entry count {len(infos)} exceeds limit {limits.max_entries}.")
    checked: dict[str, zipfile.ZipInfo] = {}
    total_size = 0
    for info in infos:
        _validate_entry_name(info.filename)
        if info.filename in checked:
            raise ZipSafetyError(f"ZIP duplicate entry is not allowed: {info.filename}")
        checked[info.filename] = info
        if info.is_dir():
            continue
        _validate_entry_size(info, limits.max_entry_uncompressed_bytes)
        total_size += info.file_size
    if total_size > limits.max_total_uncompressed_bytes:
        raise ZipSafetyError(
            f"ZIP total uncompressed size {total_size} exceeds limit {limits.max_total_uncompressed_bytes}.",
        )
    return checked


def _validate_entry_name(name: str) -> None:
    if not name or "\\" in name or name.startswith("/"):
        raise ZipSafetyError(f"ZIP entry has unsafe path: {name}")
    if any(part == ".." for part in PurePosixPath(name).parts):
        raise ZipSafetyError(f"ZIP entry has unsafe path: {name}")


def _validate_entry_size(info: zipfile.ZipInfo, max_bytes: int) -> None:
    if info.file_size > max_bytes:
        raise ZipSafetyError(f"ZIP entry {info.filename} size {info.file_size} exceeds limit {max_bytes}.")


def _read_limited(archive: zipfile.ZipFile, info: zipfile.ZipInfo, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total_size = 0
    with archive.open(info) as source:
        while True:
            chunk = source.read(min(_ZIP_READ_CHUNK_BYTES, max_bytes - total_size + 1))
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
            total_size += len(chunk)
            if total_size > max_bytes:
                raise ZipSafetyError(f"ZIP entry {info.filename} expanded beyond limit {max_bytes}.")
