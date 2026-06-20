"""
JSON envelope helpers for stdout communication with TypeScript layer.

Node adapters run the worker as short-lived CLI subprocesses.
Each command writes one JSON envelope to stdout and exits.
"""
import json
import sys
from typing import Any


class EnvelopeExit(SystemExit):
    """Controlled process exit after writing a worker JSON envelope."""


def ok(data: dict[str, Any] | None = None, metrics: dict[str, Any] | None = None, warnings: list[str] | None = None) -> dict:
    """Write a success envelope to stdout."""
    envelope: dict[str, Any] = {
        "ok": True,
        "data": data or {},
        "metrics": metrics or {},
        "warnings": warnings or [],
    }
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False))
    sys.stdout.flush()
    raise EnvelopeExit(0)


def fail(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    recoverable: bool = True,
    suggested_action: str = "Check input and retry.",
) -> dict:
    """Write a failure envelope to stdout."""
    envelope: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "recoverable": recoverable,
            "suggested_action": suggested_action,
            "details": details or {},
        },
        "warnings": warnings or [],
    }
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False))
    sys.stdout.flush()
    raise EnvelopeExit(1)
