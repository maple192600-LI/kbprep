"""Execute selective feedback reruns from planned rerun evidence."""

import os

from .rerun_verification import (
    _acceptance_verification,
    _command_evidence,
    _parse_worker_envelope,
    _rerun_invocation_failure,
    _run_prepare_subprocess,
    _selective_rerun_plan,
)


def _execute_selective_rerun(data: dict) -> dict:
    plan = _selective_rerun_plan(data)
    if plan.get("status") == "blocked":
        return _blocked_selective_execution(plan)
    rerun_plan = _selective_plan_as_prepare_plan(plan)
    env_overrides = _selective_plan_env_overrides(plan)
    completed, error = _run_prepare_subprocess(rerun_plan, _env_with_overrides(env_overrides))
    command_evidence = _execution_command_evidence(plan, env_overrides, actually_executed=completed is not None)
    if error:
        failed = _rerun_invocation_failure(label="selective rerun", rerun_plan=rerun_plan, error=error)
        return _selective_execution_result(plan, failed, command_evidence)
    if completed is None:
        failed = _rerun_invocation_failure(
            label="selective rerun",
            rerun_plan=rerun_plan,
            error="worker process did not start",
        )
        return _selective_execution_result(plan, failed, command_evidence)
    envelope = _parse_worker_envelope(completed.stdout)
    verification = _acceptance_verification(rerun_plan, completed, envelope)
    verification["status"] = "passed" if envelope.get("ok") else "failed"
    return _selective_execution_result(plan, verification, command_evidence)


def _blocked_selective_execution(plan: dict) -> dict:
    return {
        "schema": "kbprep.selective_rerun_verification.v1",
        "ok": False,
        "status": "blocked",
        "reason": plan.get("reason"),
        "missing_evidence": plan.get("missing_evidence", []),
        "run_id": plan.get("run_id"),
        "run_dir": plan.get("run_dir"),
        "document_type": plan.get("document_type"),
        "canonical_ir_binding": plan.get("canonical_ir_binding"),
        "plan": plan,
    }


def _selective_plan_as_prepare_plan(plan: dict) -> dict:
    payload = plan.get("prepare_payload")
    payload = payload if isinstance(payload, dict) else {}
    rerun_plan = dict(payload)
    rerun_plan["ok"] = True
    rerun_plan["mode"] = "rules_only"
    rerun_plan["force"] = True
    return rerun_plan


def _selective_plan_env_overrides(plan: dict) -> dict[str, str]:
    command_evidence = plan.get("command_evidence")
    command_evidence = command_evidence if isinstance(command_evidence, dict) else {}
    raw_env = command_evidence.get("environment")
    raw_env = raw_env if isinstance(raw_env, dict) else {}
    return {str(key): str(value) for key, value in raw_env.items() if value is not None}


def _env_with_overrides(overrides: dict[str, str]) -> dict[str, str]:
    env = dict(os.environ)
    env.update(overrides)
    return env


def _execution_command_evidence(plan: dict, env_overrides: dict[str, str], *, actually_executed: bool) -> dict:
    evidence = _command_evidence(plan["prepare_payload"], env_overrides)
    evidence["actually_executed"] = actually_executed
    return evidence


def _selective_execution_result(plan: dict, verification: dict, command_evidence: dict) -> dict:
    result = {
        "schema": "kbprep.selective_rerun_verification.v1",
        **verification,
        "run_id": plan.get("run_id"),
        "document_type": plan.get("document_type"),
        "policy_snapshot_hash": plan.get("policy_snapshot_hash"),
        "canonical_ir_binding": plan.get("canonical_ir_binding"),
        "plan": plan,
        "command_evidence": command_evidence,
    }
    result["ok"] = bool(verification.get("ok"))
    return result
