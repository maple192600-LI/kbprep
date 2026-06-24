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


def status_from_findings(strict_errors: list[str], warnings: list[str]) -> str:
    """Map quality findings to a job status per core design §17.

    - strict_errors present -> ``failed`` (a hard gate failed)
    - no strict_errors + warnings present -> ``completed_with_warnings``
    - otherwise -> ``completed``
    """
    if strict_errors:
        return "failed"
    if warnings:
        return "completed_with_warnings"
    return "completed"


def ok(
    data: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    status: str = "completed",
) -> dict:
    """Write a success envelope to stdout.

    status defaults to ``completed``; prepare's success path overrides it to
    ``completed_with_warnings`` when non-blocking warnings exist (Phase E).
    """
    envelope: dict[str, Any] = {
        "ok": True,
        "status": status,
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
    status: str = "failed",
) -> dict:
    """Write a failure envelope to stdout."""
    envelope: dict[str, Any] = {
        "ok": False,
        "status": status,
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
