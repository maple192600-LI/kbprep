"""Named quality gates, next actions, and handoff tasks."""

from pathlib import Path

from ..atomic_io import atomic_write_json

ERROR_CODE_TO_GATE = {
    "E_TEXT_LAYER_TOO_SHORT": "conversion_integrity",
    "E_TEXT_LAYER_UNREADABLE": "conversion_integrity",
    "E_CONVERTED_TEXT_TOO_SHORT": "conversion_integrity",
    "E_CONVERTED_TEXT_UNREADABLE": "conversion_integrity",
    "E_SOURCE_CONVERSION_LOSS": "conversion_integrity",
    "E_CONVERSION_STRUCTURE_LOSS": "conversion_integrity",
    "E_IMAGE_FILE_MISSING": "conversion_integrity",
    "E_SVG_INVALID": "conversion_integrity",
    "E_PROTECTED_BLOCK_LOSS": "cleanup_safety",
    "E_OPERATION_STEP_LOSS": "cleanup_safety",
    "E_CODE_BLOCK_LOSS": "cleanup_safety",
    "E_TABLE_BLOCK_LOSS": "cleanup_safety",
    "E_CTA_RESIDUE": "cleanup_safety",
    "E_QR_RESIDUE": "cleanup_safety",
    "E_DISCARD_RATIO_EXCEEDED": "cleanup_safety",
    "E_TEXT_COVERAGE_LOW": "cleanup_safety",
    "E_DETAIL_BLOCK_DISCARDED": "cleanup_safety",
    "E_BROKEN_CODE_BLOCK": "splitting_integrity",
    "E_OUTPUT_RETENTION_MISSING": "export_readiness",
    "E_QA_FAILED": "cleanup_safety",
    "W_QA": "cleanup_safety",
}

def _build_quality_gates(strict_errors: list[str], warnings: list[str], report: dict) -> tuple[list[dict], list[dict]]:
    gate_order = [
        "conversion_integrity",
        "cleanup_safety",
        "splitting_integrity",
        "review_safety",
        "export_readiness",
    ]
    descriptions = {
        "conversion_integrity": "Converted Markdown preserves source structure, readable text, and source-linked assets.",
        "cleanup_safety": "Cleaning removes pollution without deleting protected knowledge.",
        "splitting_integrity": "Chunks keep Markdown structure intact for review and Obsidian.",
        "review_safety": "AI or human review patches are validated before publication.",
        "export_readiness": "Final Obsidian/Markdown output may be published.",
    }
    grouped_errors: dict[str, list[str]] = {name: [] for name in gate_order}
    grouped_warnings: dict[str, list[str]] = {name: [] for name in gate_order}

    for error in strict_errors:
        gate = _quality_gate_for_message(error, report=report)
        grouped_errors[gate].append(error)
        if gate != "export_readiness":
            grouped_errors["export_readiness"].append(error)

    for warning in warnings:
        grouped_warnings[_quality_gate_for_message(warning, is_warning=True, report=report)].append(warning)

    gates = []
    for name in gate_order:
        checked = name != "review_safety" or bool(report.get("review_applied_at"))
        errors = grouped_errors[name]
        gate_warnings = grouped_warnings[name]
        if errors:
            status = "fail"
        elif gate_warnings:
            status = "warn"
        elif checked:
            status = "pass"
        else:
            status = "not_checked"
        gates.append({
            "name": name,
            "status": status,
            "checked": checked,
            "description": descriptions[name],
            "strict_errors": errors,
            "warnings": gate_warnings,
        })

    return gates, _next_actions_from_gates(gates)

def _quality_gate_for_message(message: str, is_warning: bool = False, report: dict | None = None) -> str:
    text = message or ""
    issue_gate = _quality_issue_gate_for_message(text, report or {})
    if issue_gate:
        return issue_gate
    code = text.split(":", 1)[0].strip()
    if code in ERROR_CODE_TO_GATE:
        return ERROR_CODE_TO_GATE[code]
    lowered = text.lower()
    if (
        text.startswith("E_TEXT_LAYER_")
        or text.startswith("E_CONVERTED_TEXT_")
        or text.startswith("E_SOURCE_CONVERSION_LOSS")
        or text.startswith("E_CONVERSION_STRUCTURE_LOSS")
        or text.startswith("W_SOURCE_TEXT_LAYER")
        or text.startswith("W_PDF_TEXT_LAYER")
        or "referenced image files are missing" in text
        or "SVG diagram files" in text
    ):
        return "conversion_integrity"
    if is_warning and ("chunk" in lowered or "split" in lowered):
        return "splitting_integrity"
    return "export_readiness"

def _quality_issue_gate_for_message(message: str, report: dict) -> str | None:
    issues = report.get("quality_issues") or []
    if not isinstance(issues, list):
        return None
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "")
        gate = str(issue.get("gate") or "")
        if code and gate and message.startswith(f"{code}:"):
            return gate
    return None

def _next_actions_from_gates(gates: list[dict]) -> list[dict]:
    action_by_gate = {
        "conversion_integrity": {
            "action": "inspect_or_rerun_conversion",
            "target": "converted_md_and_source_evidence",
            "reason": "Converted Markdown lost structure, unreadable text, or source-linked assets.",
        },
        "cleanup_safety": {
            "action": "update_cleaning_rules_or_review_pack",
            "target": "cleaning_rules",
            "reason": "Cleaning left pollution behind or removed content that should be protected.",
        },
        "splitting_integrity": {
            "action": "adjust_splitter_or_chunking",
            "target": "splitter",
            "reason": "Chunking broke Markdown structures needed by AI review and Obsidian.",
        },
        "review_safety": {
            "action": "validate_review_patch",
            "target": "review_patch",
            "reason": "Review changes must be checked before publication.",
        },
        "export_readiness": {
            "action": "block_export",
            "target": "latest_outputs",
            "reason": "Strict quality errors remain, so final Obsidian/Markdown output must not be published.",
        },
    }
    actions = []
    seen: set[tuple[str, str, str]] = set()
    for gate in gates:
        if gate.get("status") != "fail":
            continue
        name = str(gate.get("name"))
        base = action_by_gate.get(name)
        if not base:
            continue
        key = (name, base["action"], base["target"])
        if key in seen:
            continue
        seen.add(key)
        actions.append({
            "gate": name,
            **base,
            "strict_error_count": len(gate.get("strict_errors") or []),
        })
    return actions

def _write_quality_gate_artifacts(report: dict, gates: list[dict], run_p: Path) -> dict:
    gate_dir = run_p / "quality_gates"
    gate_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for index, gate in enumerate(gates, start=1):
        name = str(gate.get("name") or f"gate_{index}")
        artifact = {
            "schema": "kbprep.quality_gate.v1",
            "execution_order": index,
            "gate": gate,
            "input_artifacts": _quality_gate_input_artifacts(name, run_p),
            "blocks_publication": name == "export_readiness" and gate.get("status") == "fail",
            "quality_loop": report.get("quality_loop", {}),
            "source_type": report.get("source_type"),
            "profile": report.get("profile"),
            "document_type": report.get("document_type"),
            "generated_from": str(run_p / "quality_report.json"),
        }
        target = gate_dir / f"{name}.json"
        atomic_write_json(target, artifact, indent=2, trailing_newline=False)
        paths[name] = str(target)
    return paths

def _quality_gate_input_artifacts(gate: str, run_p: Path) -> list[str]:
    common = [
        run_p / "quality_report.json",
        run_p / "blocks.jsonl",
    ]
    by_gate = {
        "conversion_integrity": [
            run_p / "conversion_report.json",
            run_p / "converted.md",
            run_p / "source_conversion_integrity.json",
        ],
        "cleanup_safety": [
            run_p / "cleaned.md",
            run_p / "discarded.md",
            run_p / "review_needed.md",
        ],
        "splitting_integrity": [
            run_p / "chunks",
            run_p / "parts",
        ],
        "review_safety": [
            run_p / "review_pack.json",
        ],
        "export_readiness": [
            run_p / "cleaned.md",
            run_p / "obsidian",
            run_p / "audit.md",
        ],
    }
    paths = [*common, *by_gate.get(gate, [])]
    return [str(path) for path in paths]

def _quality_tasks_from_actions(report: dict, actions: list[dict], run_p: Path) -> dict:
    tasks = []
    gates_by_name = {
        str(gate.get("name")): gate
        for gate in report.get("quality_gates", [])
        if isinstance(gate, dict)
    }
    for index, action in enumerate(actions, start=1):
        gate = str(action.get("gate") or "export_readiness")
        task_gate = "quality_loop" if action.get("action") == "stop_iteration" else gate
        tasks.append(_quality_task_for_action(report, action, run_p, index, task_gate, gates_by_name.get(gate, {})))
    return {
        "schema": "kbprep.quality_tasks.v1",
        "run_dir": str(run_p),
        "source_type": report.get("source_type"),
        "profile": report.get("profile"),
        "document_type": report.get("document_type"),
        "quality_loop": report.get("quality_loop", {}),
        "tasks": tasks,
    }

def _quality_task_for_action(report: dict, action: dict, run_p: Path, index: int, gate: str, gate_report: dict) -> dict:
    evidence_paths = _quality_gate_input_artifacts(gate, run_p)
    if gate == "cleanup_safety":
        evidence_paths.extend([
            "rules/base/obvious_noise.json",
            "rules/document_types/",
            "rules/templates/",
            ".kbprep/rules/user/accepted_rules.jsonl",
        ])
    return {
        "id": f"quality-task-{index:02d}-{gate.replace('_', '-')}",
        "gate": gate,
        "action": action.get("action"),
        "reason": action.get("reason") or gate_report.get("description") or "Quality gate failed.",
        "evidence_paths": _dedupe_paths(evidence_paths),
        "commands": _quality_task_commands(gate, action, run_p),
        "acceptance_checks": [
            "quality_report.json has no strict_errors for this gate.",
            "quality_report.json quality_gates marks this gate as pass or non-failing.",
            "latest.json is updated only after export_readiness passes.",
        ],
        "evidence": {
            "strict_error_count": action.get("strict_error_count", 0),
            "strict_errors": gate_report.get("strict_errors", []),
            "warnings": gate_report.get("warnings", []),
            "quality_loop": report.get("quality_loop", {}),
        },
    }


def _quality_task_commands(gate: str, action: dict, run_p: Path) -> list[str]:
    if action.get("action") == "stop_iteration":
        return [
            f"Inspect {_q(run_p / 'quality_report.json')}, {_q(run_p / 'discarded.md')}, and {_q(run_p / 'review_needed.md')} before changing rules.",  # noqa: E501
            f"Use {_q(run_p / 'run_metadata.json')} to rerun only the affected source after the repair.",
        ]
    by_gate = {
        "conversion_integrity": [
            f"Inspect {_q(run_p / 'conversion_report.json')} and {_q(run_p / 'source_conversion_integrity.json')}.",  # noqa: E501
            f"Compare conversion evidence with {_q(run_p / 'converted.md')} before cleanup continues.",
            f"Rerun the original prepare input recorded in {_q(run_p / 'run_metadata.json')} after fixing the conversion route or source file.",  # noqa: E501
        ],
        "cleanup_safety": [
            f"Inspect {_q(run_p / 'discarded.md')} and {_q(run_p / 'review_needed.md')} against {_q(run_p / 'cleaned.md')}.",  # noqa: E501
            f"Submit a scoped rule proposal: kbprep-feedback --run-dir {_q(run_p)} --feedback-text \"<discard or protect this run evidence>\".",  # noqa: E501
            "After review, rerun the affected source with: kbprep-feedback --accept-proposal <id|latest> --rerun-after-accept.",  # noqa: E501
        ],
        "splitting_integrity": [
            f"Inspect {_q(run_p / 'chunks')} and {_q(run_p / 'parts')} for broken tables, code fences, lists, or block traces.",  # noqa: E501
            f"Use {_q(run_p / 'run_metadata.json')} to rerun only the affected split after the splitter repair.",
        ],
        "review_safety": [
            f"Inspect {_q(run_p / 'review_pack.json')} and validate any patch before publication.",
            f"Apply guarded review only through: kbprep-apply-review --run-dir {_q(run_p)} --patch-file <patch.json>.",  # noqa: E501
        ],
        "export_readiness": [
            f"Inspect {_q(run_p / 'quality_report.json')} and {_q(run_p / 'quality_gates')}.",
            "Do not publish latest outputs until every failing upstream gate has been repaired and rerun.",
        ],
    }
    return by_gate.get(gate, [f"Inspect {_q(run_p / 'quality_report.json')} and rerun only the affected path."])


def _q(path: Path) -> str:
    return f'"{path}"'


def _dedupe_paths(paths: list[str]) -> list[str]:
    result: list[str] = []
    seen = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


build_quality_gates = _build_quality_gates
quality_tasks_from_actions = _quality_tasks_from_actions
write_quality_gate_artifacts = _write_quality_gate_artifacts
