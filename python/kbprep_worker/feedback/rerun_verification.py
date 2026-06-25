"""Rerun representative sources to verify accepted feedback rules."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .canonical_ir_binding import canonical_ir_binding, pending_canonical_ir_binding
from .support import (
    _append_jsonl_locked,
    _matches_pattern,
    _optional_string,
    _promotion_history_rules_dir,
    _read_json_file,
    _read_jsonl,
    _rules_dir,
    _string_list,
    _target_rules_dir,
)

RERUN_TIMEOUT_SECONDS = 120


def _selective_rerun_plan(data: dict) -> dict:
    if _optional_string(data.get("accepted_proposal")):
        plan = _selective_plan_from_accepted_proposal(data)
    elif _optional_string(data.get("run_dir")):
        plan = _selective_plan_from_run_dir(Path(str(data["run_dir"])).expanduser().resolve(), "run_metadata")
    elif not _optional_string(data.get("document_type")):
        plan = _blocked_plan(
            plan_source="selector",
            reason="plan_rerun requires run_dir, accepted_proposal, or document_type.",
            missing_evidence=["rerun_selector"],
        )
    else:
        plan = _selective_plan_from_promotion_history(data)
    if plan.get("status") == "blocked":
        _append_blocked_rerun_history(data, plan)
    return plan


def _selective_plan_from_accepted_proposal(data: dict) -> dict:
    rules_dir = _rules_dir(data)
    accepted_path = rules_dir / "accepted_rules.jsonl"
    proposal = _selected_accepted_proposal(accepted_path, str(data.get("accepted_proposal") or ""))
    if not proposal:
        return _blocked_plan(
            plan_source="accepted_proposal",
            reason=f"accepted proposal not found in {accepted_path}",
            missing_evidence=["accepted_proposal"],
        )
    run_dir = _optional_string(proposal.get("created_from_run")) or ""
    if not run_dir:
        return _blocked_plan(
            plan_source="accepted_proposal",
            reason="accepted proposal does not include created_from_run evidence",
            accepted_proposal_id=_optional_string(proposal.get("id")) or "",
            missing_evidence=["created_from_run"],
        )
    plan = _selective_plan_from_run_dir(Path(run_dir).expanduser().resolve(), "accepted_proposal")
    plan["accepted_proposal_id"] = _optional_string(proposal.get("id")) or ""
    if plan.get("status") == "planned":
        plan["command_evidence"] = _command_evidence(plan["prepare_payload"], {"KBPREP_USER_RULES_DIR": str(rules_dir)})
    return plan


def _selected_accepted_proposal(path: Path, wanted: str) -> dict | None:
    if not path.exists():
        return None
    proposals = _read_jsonl(path)
    if wanted == "latest" and proposals:
        return proposals[-1]
    return next((item for item in proposals if item.get("id") == wanted), None)


def _selective_plan_from_promotion_history(data: dict) -> dict:
    history_path = _promotion_history_path(data)
    document_type = _optional_string(data.get("document_type"))
    if not history_path.exists():
        return _blocked_plan(
            plan_source="promotion_history",
            reason=f"promotion_history.jsonl does not exist: {history_path}",
            missing_evidence=["promotion_history"],
        )
    entries = _promotion_history_entries(history_path, document_type)
    if not entries:
        return _blocked_plan(
            plan_source="promotion_history",
            reason="No promotion history entries matched the requested document_type.",
            missing_evidence=["promotion_history_entry"],
        )
    return _plan_from_latest_promotion_entry(entries[-1], history_path.parent)


def _promotion_history_path(data: dict) -> Path:
    explicit = _optional_string(data.get("promotion_history_file"))
    if explicit:
        return Path(explicit).expanduser().resolve()
    history_rules_dir = _promotion_history_rules_dir(_target_rules_dir(data))
    return history_rules_dir / "promotion_history.jsonl"


def _promotion_history_entries(path: Path, document_type: str | None) -> list[dict]:
    entries = [
        item for item in _read_jsonl(path)
        if item.get("schema") in {"kbprep.dictionary_promotion_history.v1", "kbprep.dictionary_promotion_resolution.v1"}
    ]
    if not document_type:
        return entries
    return [item for item in entries if item.get("document_type") == document_type]


def _plan_from_latest_promotion_entry(entry: dict, rules_root: Path) -> dict:
    verification = entry.get("regression_verification")
    verification = verification if isinstance(verification, dict) else {}
    status = _optional_string(verification.get("status")) or "unknown"
    samples = _promotion_samples(verification)
    if status == "failed":
        sample = next((item for item in samples if item.get("ok") is False), samples[0] if samples else {})
        run_dir = _optional_string(sample.get("run_dir")) or ""
        return _blocked_plan(
            plan_source="promotion_history",
            reason=_promotion_sample_reason(sample) or "Failed promotion history blocks selective rerun planning.",
            run_dir=run_dir,
            document_type=_optional_string(entry.get("document_type")) or "",
            promotion_history_status=status,
            missing_evidence=["passing_promotion_history"],
            canonical_ir_binding=canonical_ir_binding(Path(run_dir).expanduser().resolve()) if run_dir else None,
        )
    if not samples:
        return _blocked_plan(
            plan_source="promotion_history",
            reason="Promotion history did not record representative run samples.",
            document_type=_optional_string(entry.get("document_type")) or "",
            promotion_history_status=status,
            missing_evidence=["representative_run_dir"],
        )
    run_dir = _optional_string(samples[0].get("run_dir")) or ""
    plan = _selective_plan_from_run_dir(Path(run_dir).expanduser().resolve(), "promotion_history")
    plan["promotion_history_status"] = status
    if plan.get("status") == "planned":
        plan["command_evidence"] = _command_evidence(plan["prepare_payload"], {"KBPREP_RULES_ROOT": str(rules_root)})
    return plan


def _promotion_samples(verification: dict) -> list[dict]:
    samples = verification.get("samples")
    if not isinstance(samples, list):
        return []
    return [item for item in samples if isinstance(item, dict)]


def _rerun_after_dictionary_promotion(
    *,
    suggestion: dict,
    target_rules_dir: Path,
    promoted_rules: list[dict],
    data: dict,
) -> dict:
    if data.get("rerun_after_promotion") is not True:
        return {
            "status": "not_requested",
            "reason": "Set rerun_after_promotion=true to rerun representative sources after promoting a dictionary.",
        }

    run_dirs = _representative_run_dirs(suggestion, data)
    if not run_dirs:
        return {
            "status": "unavailable",
            "ok": False,
            "sample_count": 0,
            "reason": "No representative run directories were found in the suggestion or representative_run_dirs input.",
        }

    samples = []
    for run_dir in run_dirs:
        sample = _rerun_representative_source(
            run_dir=run_dir,
            target_rules_dir=target_rules_dir,
            promoted_rules=promoted_rules,
        )
        samples.append(sample)

    ok_samples = [sample for sample in samples if sample.get("ok")]
    return {
        "status": "passed" if len(ok_samples) == len(samples) else "failed",
        "ok": len(ok_samples) == len(samples),
        "sample_count": len(samples),
        "passed_count": len(ok_samples),
        "failed_count": len(samples) - len(ok_samples),
        "samples": samples,
    }

def _representative_run_dirs(suggestion: dict, data: dict) -> list[Path]:
    explicit = [
        Path(value).expanduser().resolve()
        for value in _string_list(data.get("representative_run_dirs"))
    ]
    if explicit:
        return _dedupe_paths_local(explicit)

    proposed_rules = suggestion.get("proposed_rules")
    result = []
    if isinstance(proposed_rules, list):
        for item in proposed_rules:
            if not isinstance(item, dict):
                continue
            raw = _optional_string(item.get("created_from_run")) or _optional_string(item.get("source_run_dir"))
            if raw:
                result.append(Path(raw).expanduser().resolve())
    return _dedupe_paths_local(result)

def _dedupe_paths_local(paths: list[Path]) -> list[Path]:
    seen = set()
    result = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result

def _rerun_representative_source(
    *,
    run_dir: Path,
    target_rules_dir: Path,
    promoted_rules: list[dict],
) -> dict:
    rerun_plan = _rerun_plan_from_run_dir(run_dir)
    if not rerun_plan.get("ok"):
        return {
            "ok": False,
            "status": "unavailable",
            "run_dir": str(run_dir),
            **rerun_plan,
        }

    completed, error = _run_prepare_subprocess(rerun_plan, _rules_root_env(target_rules_dir))
    if error:
        return _rerun_invocation_failure(
            label="representative rerun",
            rerun_plan=rerun_plan,
            error=error,
            run_dir=run_dir,
        )
    if completed is None:
        return _rerun_invocation_failure(
            label="representative rerun",
            rerun_plan=rerun_plan,
            error="worker process did not start",
            run_dir=run_dir,
        )

    envelope = _parse_worker_envelope(completed.stdout)
    sample = _representative_sample(run_dir, rerun_plan, completed, envelope)
    if not envelope.get("ok"):
        return sample

    effect = _verify_promoted_rules_after_rerun(promoted_rules, sample)
    sample.update(effect)
    sample["ok"] = bool(effect.get("ok"))
    sample["status"] = "passed" if sample["ok"] else "failed"
    return sample

def _rerun_plan_from_run_dir(run_dir: Path) -> dict:
    proposal_like = {"created_from_run": str(run_dir)}
    return _rerun_plan_from_proposal(proposal_like)


def _selective_plan_from_run_dir(run_dir: Path, plan_source: str) -> dict:
    if not run_dir.exists():
        return _blocked_plan(
            plan_source=plan_source,
            reason=f"run_dir does not exist: {run_dir}",
            run_dir=str(run_dir),
            missing_evidence=["run_dir"],
        )
    metadata = _read_json_file(run_dir / "run_metadata.json")
    quality = _read_json_file(run_dir / "quality_report.json")
    evidence = _run_evidence_from_metadata(run_dir, metadata, quality)
    missing = _missing_rerun_evidence(evidence)
    if missing:
        return _blocked_plan(
            plan_source=plan_source,
            reason=f"Run metadata is missing required rerun evidence: {', '.join(missing)}.",
            run_dir=str(run_dir),
            run_id=evidence.get("run_id", ""),
            document_type=evidence.get("document_type", ""),
            missing_evidence=missing,
            canonical_ir_binding=canonical_ir_binding(run_dir),
        )
    return _planned_selective_rerun(plan_source, run_dir, evidence)


def _run_evidence_from_metadata(run_dir: Path, metadata: dict, quality: dict) -> dict:
    payload = metadata.get("prepare_payload")
    payload = payload if isinstance(payload, dict) else {}
    source_identity = metadata.get("source_identity")
    source_identity = source_identity if isinstance(source_identity, dict) else {}
    input_path = _optional_string(payload.get("input_path")) or ""
    return {
        "run_id": _optional_string(metadata.get("run_id")) or run_dir.name,
        "input_path": input_path,
        "output_root": _optional_string(payload.get("output_root")) or _default_output_root(run_dir),
        "profile": _optional_string(payload.get("profile")) or _optional_string(quality.get("profile")) or "standard",
        "source_identity": _source_identity_for_plan(source_identity, input_path),
        "document_type": _optional_string(metadata.get("document_type")) or _optional_string(quality.get("document_type")) or "unknown",
        "policy_snapshot_hash": (
            _optional_string(metadata.get("cleaning_policy_snapshot_hash"))
            or _optional_string(quality.get("cleaning_policy_snapshot_hash"))
            or ""
        ),
        "prepare_payload": payload,
    }


def _default_output_root(run_dir: Path) -> str:
    if run_dir.parent.name == "runs":
        return str(run_dir.parent.parent)
    return str(run_dir.parent)


def _source_identity_for_plan(source_identity: dict, input_path: str) -> dict:
    identity = dict(source_identity)
    if input_path:
        identity.setdefault("input_path", input_path)
        identity.setdefault("source_path", input_path)
        identity.setdefault("source_name", Path(input_path).name)
    return identity


def _missing_rerun_evidence(evidence: dict) -> list[str]:
    missing = []
    input_path = _optional_string(evidence.get("input_path")) or ""
    output_root = _optional_string(evidence.get("output_root")) or ""
    if not input_path:
        missing.append("input_path")
    elif not Path(input_path).exists():
        missing.append("input_path_exists")
    if not output_root:
        missing.append("output_root")
    return missing


def _planned_selective_rerun(plan_source: str, run_dir: Path, evidence: dict) -> dict:
    payload = _selective_prepare_payload(evidence)
    return {
        "schema": "kbprep.selective_rerun_plan.v1",
        "ok": True,
        "status": "planned",
        "plan_source": plan_source,
        "run_id": evidence["run_id"],
        "run_dir": str(run_dir),
        "source_identity": evidence["source_identity"],
        "source_path": evidence["input_path"],
        "document_type": evidence["document_type"],
        "policy_snapshot_hash": evidence["policy_snapshot_hash"],
        "canonical_ir_binding": canonical_ir_binding(run_dir),
        "prepare_payload": payload,
        "command_evidence": _command_evidence(payload, {}),
    }


def _selective_prepare_payload(evidence: dict) -> dict:
    raw_payload = evidence.get("prepare_payload")
    original = raw_payload if isinstance(raw_payload, dict) else {}
    payload = _safe_prepare_payload(original)
    payload["input_path"] = evidence["input_path"]
    payload["output_root"] = evidence["output_root"]
    payload["profile"] = evidence["profile"]
    payload["mode"] = "rules_only"
    payload["force"] = True
    payload.setdefault("language", "auto")
    payload.setdefault("source_type", "auto")
    payload.setdefault("splitter", "auto")
    return payload


def _safe_prepare_payload(payload: dict) -> dict:
    allowed_keys = {
        "artifact_policy",
        "language",
        "source_type",
        "source_url",
        "source_domain",
        "site_name",
        "allow_youtube_media_fallback",
        "splitter",
        "max_quality_iterations",
    }
    return {
        str(key): value
        for key, value in payload.items()
        if key in allowed_keys and value is not None
    }


def _command_evidence(payload: dict, env: dict[str, str]) -> dict:
    return {
        "would_execute": False,
        "standalone_command": [
            "kbprep-prepare",
            "--input",
            payload["input_path"],
            "--output",
            payload["output_root"],
            "--profile",
            payload["profile"],
            "--mode",
            "rules_only",
            "--force",
        ],
        "worker_command": ["python", "-m", "kbprep_worker.cli", "prepare", "--json-stdin"],
        "environment": env,
        "payload": payload,
    }


def _blocked_plan(
    *,
    plan_source: str,
    reason: str,
    missing_evidence: list[str],
    run_dir: str = "",
    run_id: str = "",
    document_type: str = "",
    accepted_proposal_id: str = "",
    promotion_history_status: str = "",
    canonical_ir_binding: dict | None = None,
) -> dict:
    plan = {
        "schema": "kbprep.selective_rerun_plan.v1",
        "ok": False,
        "status": "blocked",
        "plan_source": plan_source,
        "reason": reason,
        "missing_evidence": missing_evidence,
        "run_dir": run_dir,
        "run_id": run_id or (Path(run_dir).name if run_dir else ""),
        "document_type": document_type,
        "canonical_ir_binding": canonical_ir_binding or pending_canonical_ir_binding(),
    }
    _add_optional_blocked_fields(plan, accepted_proposal_id, promotion_history_status)
    return plan


def _add_optional_blocked_fields(plan: dict, accepted_proposal_id: str, promotion_history_status: str) -> None:
    if accepted_proposal_id:
        plan["accepted_proposal_id"] = accepted_proposal_id
    if promotion_history_status:
        plan["promotion_history_status"] = promotion_history_status


def _append_blocked_rerun_history(data: dict, plan: dict) -> None:
    history_path = _rules_dir(data) / "rerun_history.jsonl"
    entry = {
        "schema": "kbprep.selective_rerun_history.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "blocked",
        "plan_source": plan.get("plan_source"),
        "run_id": plan.get("run_id"),
        "run_dir": plan.get("run_dir"),
        "document_type": plan.get("document_type"),
        "reason": plan.get("reason"),
        "missing_evidence": plan.get("missing_evidence", []),
        "promotion_history_status": plan.get("promotion_history_status"),
    }
    _append_jsonl_locked(history_path, entry)


def _promotion_sample_reason(sample: dict) -> str:
    worker_error = sample.get("worker_error")
    worker_error = worker_error if isinstance(worker_error, dict) else {}
    return (
        _optional_string(sample.get("reason"))
        or _optional_string(sample.get("error"))
        or _optional_string(worker_error.get("code"))
        or ""
    )

def _verify_promoted_rules_after_rerun(promoted_rules: list[dict], sample: dict) -> dict:
    cleaned_path = sample.get("cleaned_md")
    if not isinstance(cleaned_path, str) or not Path(cleaned_path).exists():
        return {
            "ok": False,
            "rule_effects": [],
            "reason": "cleaned output is missing after representative rerun",
        }
    cleaned_text = Path(cleaned_path).read_text(encoding="utf-8", errors="replace")
    effects = []
    for rule in promoted_rules:
        action = rule.get("action")
        pattern = str(rule.get("pattern", ""))
        match = str(rule.get("match", "literal"))
        matched = _matches_pattern(cleaned_text, pattern, match)
        if action == "discard":
            ok_rule = not matched
            effect = "discard_pattern_absent_from_cleaned" if ok_rule else "discard_pattern_still_in_cleaned"
        elif action == "protect":
            ok_rule = matched
            effect = "protect_pattern_present_in_cleaned" if ok_rule else "protect_pattern_missing_from_cleaned"
        else:
            ok_rule = True
            effect = "review_rule_not_checked_against_cleaned_text"
        effects.append({
            "ok": ok_rule,
            "rule_id": rule.get("id"),
            "action": action,
            "pattern": pattern,
            "effect": effect,
        })
    return {
        "ok": all(effect["ok"] for effect in effects),
        "rule_effects": effects,
    }

def _rerun_after_accept(accepted: dict, rules_dir: Path, data: dict) -> dict:
    if data.get("rerun_after_accept") is not True:
        return {
            "status": "not_requested",
            "reason": "Set rerun_after_accept=true to rerun the affected source after accepting a rule.",
        }

    rerun_plan = _rerun_plan_from_proposal(accepted)
    if not rerun_plan.get("ok"):
        return {
            "status": "unavailable",
            **rerun_plan,
        }

    completed, error = _run_prepare_subprocess(rerun_plan, _user_rules_env(rules_dir))
    if error:
        return _rerun_invocation_failure(label="rerun", rerun_plan=rerun_plan, error=error)
    if completed is None:
        return _rerun_invocation_failure(
            label="rerun",
            rerun_plan=rerun_plan,
            error="worker process did not start",
        )

    envelope = _parse_worker_envelope(completed.stdout)
    verification = _acceptance_verification(rerun_plan, completed, envelope)
    if not envelope.get("ok"):
        return verification

    effect = _verify_rule_effect_after_rerun(accepted, verification)
    verification.update(effect)
    verification["status"] = "passed" if effect.get("ok") else "failed"
    verification["ok"] = bool(effect.get("ok"))
    return verification


def _rules_only_payload(rerun_plan: dict) -> dict:
    payload = _safe_prepare_payload(rerun_plan)
    payload["input_path"] = rerun_plan["input_path"]
    payload["output_root"] = rerun_plan["output_root"]
    payload["profile"] = rerun_plan.get("profile") or "standard"
    payload["mode"] = "rules_only"
    payload["force"] = True
    payload.setdefault("language", "auto")
    payload.setdefault("source_type", "auto")
    payload.setdefault("splitter", "auto")
    return payload


def _rules_root_env(target_rules_dir: Path) -> dict:
    env = dict(os.environ)
    env["KBPREP_RULES_ROOT"] = str(target_rules_dir)
    return env


def _user_rules_env(rules_dir: Path) -> dict:
    env = dict(os.environ)
    existing_rules_dir = env.get("KBPREP_USER_RULES_DIR", "").strip()
    env["KBPREP_USER_RULES_DIR"] = (
        f"{rules_dir}{os.pathsep}{existing_rules_dir}" if existing_rules_dir else str(rules_dir)
    )
    return env


def _run_prepare_subprocess(
    rerun_plan: dict,
    env: dict,
) -> tuple[subprocess.CompletedProcess[str] | None, str]:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "kbprep_worker.cli", "prepare", "--json-stdin"],
            input=json.dumps(_rules_only_payload(rerun_plan), ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            cwd=str(Path(rerun_plan["input_path"]).parent),
            timeout=RERUN_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:
        return None, str(exc)
    return completed, ""


def _rerun_invocation_failure(
    *,
    label: str,
    rerun_plan: dict,
    error: str,
    run_dir: Path | None = None,
) -> dict:
    result = {
        "ok": False,
        "status": "failed",
        "reason": f"{label} invocation failed: {error}",
        "input_path": rerun_plan.get("input_path"),
        "output_root": rerun_plan.get("output_root"),
    }
    if run_dir is not None:
        result["run_dir"] = str(run_dir)
    return result


def _representative_sample(
    run_dir: Path,
    rerun_plan: dict,
    completed: subprocess.CompletedProcess[str],
    envelope: dict,
) -> dict:
    sample = {
        "ok": bool(envelope.get("ok")),
        "status": "passed" if envelope.get("ok") else "failed",
        "exit_code": completed.returncode,
        "run_dir": str(run_dir),
        "input_path": rerun_plan.get("input_path"),
        "output_root": rerun_plan.get("output_root"),
        "stderr_tail": completed.stderr[-2000:],
    }
    _add_prepare_outputs(sample, envelope, run_dir_field="new_run_dir")
    if not envelope.get("ok"):
        sample["worker_error"] = envelope.get("error", {})
    return sample


def _acceptance_verification(
    rerun_plan: dict,
    completed: subprocess.CompletedProcess[str],
    envelope: dict,
) -> dict:
    verification = {
        "status": "failed",
        "ok": bool(envelope.get("ok")),
        "exit_code": completed.returncode,
        "input_path": rerun_plan.get("input_path"),
        "output_root": rerun_plan.get("output_root"),
        "stderr_tail": completed.stderr[-2000:],
    }
    _add_prepare_outputs(verification, envelope, run_dir_field="run_dir")
    if not envelope.get("ok"):
        verification["worker_error"] = envelope.get("error", {})
    return verification


def _add_prepare_outputs(target: dict, envelope: dict, *, run_dir_field: str) -> None:
    raw_data_out = envelope.get("data")
    data_out = raw_data_out if isinstance(raw_data_out, dict) else {}
    if not data_out:
        return
    raw_latest_outputs = data_out.get("latest_outputs")
    latest_outputs = raw_latest_outputs if isinstance(raw_latest_outputs, dict) else {}
    target[run_dir_field] = data_out.get("run_dir")
    target["cleaned_md"] = latest_outputs.get("cleaned_md")
    target["quality_report"] = latest_outputs.get("quality_report")
    target["strict_errors"] = data_out.get("strict_errors", [])


def _rerun_plan_from_proposal(proposal: dict) -> dict:
    run_dir = Path(str(proposal.get("created_from_run", ""))).expanduser()
    if not run_dir.exists():
        return {"ok": False, "reason": f"created_from_run does not exist: {run_dir}"}
    output_root = run_dir.parent.parent if run_dir.parent.name == "runs" else run_dir.parent
    latest_path = output_root / "latest.json"
    metadata_path = run_dir / "run_metadata.json"
    input_path = ""
    profile = ""
    if latest_path.exists():
        latest = _read_json_file(latest_path)
        raw_input_path = latest.get("input_path")
        input_path = raw_input_path if isinstance(raw_input_path, str) else ""
    if not input_path and metadata_path.exists():
        metadata = _read_json_file(metadata_path)
        raw_payload = metadata.get("prepare_payload")
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        raw_input_path = payload.get("input_path")
        raw_output_root = payload.get("output_root")
        raw_profile = payload.get("profile")
        input_path = raw_input_path if isinstance(raw_input_path, str) else ""
        output_root = Path(raw_output_root) if isinstance(raw_output_root, str) and raw_output_root else output_root
        profile = raw_profile if isinstance(raw_profile, str) else ""
    if not input_path:
        return {"ok": False, "reason": f"latest.json or run_metadata.json did not contain input_path for run: {run_dir}"}
    if not Path(input_path).exists():
        return {"ok": False, "reason": f"input_path from run metadata does not exist: {input_path}"}
    quality = _read_json_file(run_dir / "quality_report.json")
    if not profile and isinstance(quality.get("profile"), str):
        profile = quality["profile"]
    return {
        "ok": True,
        "input_path": input_path,
        "output_root": str(output_root),
        "profile": profile or "standard",
    }

def _parse_worker_envelope(stdout: str) -> dict:
    for line in reversed([line.strip() for line in stdout.splitlines() if line.strip()]):
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            return value
    return {"ok": False, "error": {"code": "E_RERUN_OUTPUT_INVALID", "message": "rerun did not emit a JSON envelope"}}

def _verify_rule_effect_after_rerun(accepted: dict, verification: dict) -> dict:
    cleaned_path = verification.get("cleaned_md")
    if not isinstance(cleaned_path, str) or not Path(cleaned_path).exists():
        return {
            "ok": False,
            "rule_effect": "cleaned_output_missing",
        }
    cleaned_text = Path(cleaned_path).read_text(encoding="utf-8", errors="replace")
    action = accepted.get("action")
    pattern = str(accepted.get("pattern", ""))
    match = str(accepted.get("match", "literal"))
    matched = _matches_pattern(cleaned_text, pattern, match)
    if action == "discard":
        return {
            "ok": not matched,
            "rule_effect": "discard_pattern_absent_from_cleaned" if not matched else "discard_pattern_still_in_cleaned",
        }
    if action == "protect":
        return {
            "ok": matched,
            "rule_effect": "protect_pattern_present_in_cleaned" if matched else "protect_pattern_missing_from_cleaned",
        }
    return {
        "ok": True,
        "rule_effect": "review_rule_not_checked_against_cleaned_text",
    }
