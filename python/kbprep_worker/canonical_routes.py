"""Canonical conversion route helpers shared by Canonical IR writers."""

from __future__ import annotations

from typing import Any


def dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def canonical_converter(conversion_report: dict[str, Any], route_decision: dict[str, Any]) -> str:
    return str(route_decision.get("actual_converter") or conversion_report.get("converter") or "")


def canonical_conversion_route(conversion_report: dict[str, Any], route_decision: dict[str, Any]) -> str:
    return str(
        route_decision.get("actual_route")
        or route_decision.get("actual_converter")
        or conversion_report.get("converter")
        or ""
    )
