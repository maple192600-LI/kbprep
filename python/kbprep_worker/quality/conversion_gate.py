"""Pre-clean conversion quality gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_json
from ..canonical_ir import validate_canonical_ir_manifests
from ..diagnose import analyze_text_quality
from .conversion_integrity import converted_text_quality as report_converted_text_quality
from .thresholds import CONVERSION_THRESHOLDS


def run_pre_clean_conversion_gate(run_dir: Path, diagnosis: dict[str, Any]) -> dict[str, Any]:
    run_p = Path(run_dir)
    conversion_report_path, diagnosis_report_path, conversion_report, strict_errors, quality_issues = _read_gate_evidence(run_p)
    converted_path = Path(str(conversion_report.get("converted_md") or run_p / "converted.md"))
    quality = _converted_quality(conversion_report, converted_path)
    text_errors, text_issues = _quality_failures(quality, converted_path)
    strict_errors.extend(text_errors)
    quality_issues.extend(text_issues)
    manifest_evidence = _canonical_ir_manifest_evidence(run_p, converted_path)
    _append_manifest_issues(strict_errors, quality_issues, manifest_evidence)
    status = "fail" if strict_errors else "pass"
    report = {
        "schema": "kbprep.conversion_quality_report.v1",
        "gate": "pre_clean_conversion",
        "status": status,
        "blocked_stage": "cleanup" if strict_errors else None,
        "conversion_report": str(conversion_report_path),
        "diagnosis_report": str(diagnosis_report_path),
        "converted_md": str(converted_path),
        "canonical_ir_manifest": manifest_evidence["canonical_ir_manifest"],
        "document_manifest": manifest_evidence["document_manifest"],
        "canonical_ir_status": manifest_evidence["status"],
        "converter": conversion_report.get("converter"),
        "diagnosed_strategy": conversion_report.get("diagnosed_strategy"),
        "route_evidence": _route_evidence(conversion_report),
        "conversion_warnings": _list_or_empty(conversion_report.get("warnings")),
        "evidence": _evidence_summary(conversion_report_path, diagnosis_report_path, converted_path),
        "diagnosis_text_quality": diagnosis.get("text_quality", {}) if isinstance(diagnosis, dict) else {},
        "converted_text_quality": quality,
        "strict_errors": strict_errors,
        "quality_issues": quality_issues,
        "failure_actions": _failure_actions(quality_issues),
        "thresholds": {
            "garbage_ratio_strict": CONVERSION_THRESHOLDS["garbage_ratio_strict"],
        },
    }
    atomic_write_json(
        run_p / "conversion_quality_report.json",
        report,
        indent=2,
        trailing_newline=False,
    )
    return report


def _read_gate_evidence(run_p: Path) -> tuple[Path, Path, dict[str, Any], list[str], list[dict[str, Any]]]:
    conversion_report_path = run_p / "conversion_report.json"
    diagnosis_report_path = run_p / "diagnosis_report.json"
    strict_errors: list[str] = []
    quality_issues: list[dict[str, Any]] = []
    conversion_report = _read_required_json_report(
        conversion_report_path,
        missing_code="E_CONVERSION_REPORT_MISSING",
        invalid_code="E_CONVERSION_REPORT_INVALID",
        label="conversion_report.json",
        strict_errors=strict_errors,
        quality_issues=quality_issues,
    )
    _read_required_json_report(
        diagnosis_report_path,
        missing_code="E_DIAGNOSIS_REPORT_MISSING",
        invalid_code="E_DIAGNOSIS_REPORT_INVALID",
        label="diagnosis_report.json",
        strict_errors=strict_errors,
        quality_issues=quality_issues,
    )
    if _conversion_report_declares_failure(conversion_report):
        code = str(conversion_report.get("error_code") or "E_CONVERT_FAILED")
        _append_issue(strict_errors, quality_issues, "E_CONVERT_FAILED", f"conversion report declares failure: {code}")
    return conversion_report_path, diagnosis_report_path, conversion_report, strict_errors, quality_issues


def _read_required_json_report(
    path: Path,
    *,
    missing_code: str,
    invalid_code: str,
    label: str,
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    if not path.exists():
        _append_issue(
            strict_errors,
            quality_issues,
            missing_code,
            f"{label} is missing; conversion evidence is incomplete",
            evidence={label: str(path)},
        )
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _append_issue(
            strict_errors,
            quality_issues,
            invalid_code,
            f"{label} is not readable JSON",
            evidence={label: str(path), "error": str(exc)},
        )
        return {}
    if isinstance(data, dict):
        return data
    _append_issue(
        strict_errors,
        quality_issues,
        invalid_code,
        f"{label} must be a JSON object",
        evidence={label: str(path), "actual_type": type(data).__name__},
    )
    return {}


def _canonical_ir_manifest_evidence(run_p: Path, converted_path: Path) -> dict[str, Any]:
    canonical_manifest_path = run_p / "canonical_ir" / "manifest.json"
    document_manifest_path = run_p / "document_manifest.json"
    issues = validate_canonical_ir_manifests(run_p, converted_path=converted_path)
    return {
        "canonical_ir_manifest": str(canonical_manifest_path),
        "document_manifest": str(document_manifest_path),
        "status": "missing_or_invalid" if issues else "partial",
        "issues": [_validation_issue_dict(issue) for issue in issues],
    }


def _route_evidence(conversion_report: dict[str, Any]) -> dict[str, Any]:
    route = _dict_or_empty(conversion_report.get("route_decision"))
    return {
        "converter": conversion_report.get("converter"),
        "actual_route": route.get("actual_route"),
        "selected_route": route.get("selected_route"),
        "declared_route": route.get("declared_route"),
        "diagnosed_strategy": conversion_report.get("diagnosed_strategy"),
        "fallback_applied": route.get("fallback_applied"),
    }


def _evidence_summary(
    conversion_report_path: Path,
    diagnosis_report_path: Path,
    converted_path: Path,
) -> dict[str, Any]:
    return {
        "conversion_report_exists": conversion_report_path.exists(),
        "diagnosis_report_exists": diagnosis_report_path.exists(),
        "converted_md_exists": converted_path.exists(),
    }


def _conversion_report_declares_failure(conversion_report: dict[str, Any]) -> bool:
    status = str(conversion_report.get("status") or "").lower()
    return status in {"fail", "failed", "error"} or conversion_report.get("ok") is False


def _failure_actions(quality_issues: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    for issue in quality_issues:
        code = str(issue.get("code") or "")
        if code in seen_codes:
            continue
        seen_codes.add(code)
        actions.append(_failure_action(code))
    return actions


def _failure_action(code: str) -> dict[str, str]:
    if code == "E_CONVERSION_REPORT_MISSING":
        return _action(code, "rerun_conversion", "Run conversion again before cleanup.")
    if code == "E_CONVERSION_REPORT_INVALID":
        return _action(code, "rerun_conversion", "Regenerate conversion evidence before cleanup.")
    if code == "E_DIAGNOSIS_REPORT_MISSING":
        return _action(code, "rerun_diagnosis", "Run source diagnosis again before cleanup.")
    if code == "E_DIAGNOSIS_REPORT_INVALID":
        return _action(code, "rerun_diagnosis", "Regenerate source diagnosis evidence before cleanup.")
    if code == "E_CONVERT_FAILED":
        return _action(code, "fix_conversion_failure", "Fix the failed converter or choose another route.")
    if code in {"E_CANONICAL_IR_MANIFEST_MISSING", "E_DOCUMENT_MANIFEST_MISSING"}:
        return _action(code, "regenerate_canonical_ir", "Regenerate Canonical IR evidence before cleanup.")
    if code == "E_CANONICAL_IR_TYPED_NODES_INVALID":
        return _action(code, "regenerate_canonical_ir", "Regenerate Canonical IR typed-node evidence before cleanup.")
    if code == "E_CANONICAL_IR_SOURCE_SPANS_INVALID":
        return _action(code, "regenerate_canonical_ir", "Regenerate Canonical IR source-span evidence before cleanup.")
    if code == "E_CANONICAL_IR_TRANSFORMATION_LEDGER_INVALID":
        return _action(code, "regenerate_canonical_ir", "Regenerate Canonical IR transformation ledger evidence before cleanup.")
    if code in {"E_CANONICAL_IR_MANIFEST_INVALID", "E_DOCUMENT_MANIFEST_INVALID"}:
        return _action(code, "repair_manifest", "Repair manifest schema and artifact references before cleanup.")
    if code in {"E_CONVERT_OUTPUT_MISSING", "E_CONVERT_OUTPUT_EMPTY"}:
        return _action(code, "rerun_conversion", "Rerun conversion or choose another conversion route.")
    if code.startswith("E_CONVERTED_TEXT_"):
        return _action(code, "use_alternate_route", "Inspect source evidence and rerun with OCR or another route.")
    return _action(code, "inspect_quality_issue", "Inspect the quality issue before cleanup.")


def _action(code: str, action: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "action": action,
        "blocked_stage": "cleanup",
        "message": message,
    }


def _validation_issue_dict(issue: Any) -> dict[str, Any]:
    return {
        "code": issue.code,
        "message": issue.message,
        "evidence": issue.evidence,
    }


def _append_manifest_issues(
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
    manifest_evidence: dict[str, Any],
) -> None:
    for issue in manifest_evidence["issues"]:
        _append_issue(
            strict_errors,
            quality_issues,
            str(issue["code"]),
            str(issue["message"]),
            evidence=_dict_or_none(issue.get("evidence")),
        )


def _converted_quality(conversion_report: dict[str, Any], converted_path: Path) -> dict[str, Any]:
    from_report = report_converted_text_quality(conversion_report)
    if from_report:
        return from_report
    if not converted_path.exists():
        return {"total_chars": 0, "missing": True}
    text = converted_path.read_text(encoding="utf-8", errors="replace")
    return analyze_text_quality(text)


def _quality_failures(quality: dict[str, Any], converted_path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    strict_errors: list[str] = []
    quality_issues: list[dict[str, Any]] = []
    if quality.get("missing"):
        _append_issue(strict_errors, quality_issues, "E_CONVERT_OUTPUT_MISSING", "converted.md is missing")
        return strict_errors, quality_issues
    if int(quality.get("total_chars") or 0) <= 0:
        _append_issue(strict_errors, quality_issues, "E_CONVERT_OUTPUT_EMPTY", "converted.md is empty")
        return strict_errors, quality_issues

    checks = (
        ("garbled_ratio", "E_CONVERTED_TEXT_GARBLED", "converted text garbled ratio"),
        ("unreadable_text_ratio", "E_CONVERTED_TEXT_UNREADABLE", "converted text unreadable ratio"),
        ("mojibake_ratio", "E_CONVERTED_TEXT_MOJIBAKE", "converted text mojibake ratio"),
    )
    threshold = CONVERSION_THRESHOLDS["garbage_ratio_strict"]
    for key, code, label in checks:
        value = float(quality.get(key, 0) or 0)
        if value > threshold:
            _append_issue(
                strict_errors,
                quality_issues,
                code,
                f"{label} {value:.2%} exceeds strict threshold before cleanup",
                evidence={"converted_md": str(converted_path), key: round(value, 4), "threshold": threshold},
            )
    return strict_errors, quality_issues


def _append_issue(
    strict_errors: list[str],
    quality_issues: list[dict[str, Any]],
    code: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    strict_errors.append(f"{code}: {message}")
    issue: dict[str, Any] = {
        "code": code,
        "gate": "pre_clean_conversion",
        "message": message,
    }
    if evidence:
        issue["evidence"] = evidence
    quality_issues.append(issue)


def _dict_or_none(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_or_empty(value: object) -> list[Any]:
    return value if isinstance(value, list) else []
