"""Rerun representative sources to verify accepted feedback rules."""

import json
import os
import subprocess
import sys
from pathlib import Path

from .support import _matches_pattern, _optional_string, _read_json_file, _string_list

RERUN_TIMEOUT_SECONDS = 120


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
    return {
        "input_path": rerun_plan["input_path"],
        "output_root": rerun_plan["output_root"],
        "profile": rerun_plan.get("profile") or "standard",
        "mode": "rules_only",
        "language": "auto",
        "source_type": "auto",
        "splitter": "auto",
        "force": True,
    }


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
