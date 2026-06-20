"""Shared support helpers for the feedback command."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from ..envelope import fail
from ..rule_loader import load_cleaning_rules, rules_root


class _JsonlFileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle: Any | None = None

    def __enter__(self) -> _JsonlFileLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        handle = self.handle
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if not self.handle:
            return
        handle = self.handle
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        handle.close()


def _append_jsonl_locked(path: Path, payload: dict) -> None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    with _JsonlFileLock(lock_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                fail("E_INVALID_INPUT", f"Invalid JSON in {path}:{line_no}: {exc}")
            if not isinstance(value, dict):
                fail("E_INVALID_INPUT", f"Rule proposal in {path}:{line_no} must be an object")
            rows.append(value)
    return rows


def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        fail("E_INVALID_INPUT", "examples and counterexamples must be lists")
        return []
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str) or not item.strip():
            fail("E_INVALID_INPUT", "examples and counterexamples must contain non-empty strings")
            continue
        result.append(item.strip())
    return result


def _matching_snippets(text: str, pattern: str, match: str, limit: int = 8) -> list[str]:
    snippets = []
    for line in text.splitlines():
        cleaned = _clean_snippet_line(line)
        if not cleaned:
            continue
        if _matches_pattern(cleaned, pattern, match):
            snippets.append(cleaned[:240])
            if len(snippets) >= limit:
                break
    return snippets


def _matches_pattern(text: str, pattern: str, match: str) -> bool:
    if match == "regex":
        try:
            return re.search(pattern, text, re.IGNORECASE) is not None
        except re.error:
            return False
    return pattern.lower() in text.lower()


def _clean_snippet_line(line: str) -> str:
    line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
    line = re.sub(r"^\s*[-*+]\s+", "", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line


def _looks_like_body_counterexample(line: str, pattern: str) -> bool:
    if line.strip() == pattern.strip():
        return False
    terms = _body_counterexample_terms()
    line_lower = line.lower()
    return any(term in line or term.lower() in line_lower for term in terms)


def _body_counterexample_terms() -> tuple[str, ...]:
    rules = load_cleaning_rules()
    return (
        rules.knowledge_terms
        + rules.tutorial_indicators
        + rules.feedback_protect_intent_terms
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _target_rules_dir(data: dict) -> Path:
    value = _optional_string(data.get("target_rules_dir"))
    if value:
        return Path(value).expanduser().resolve()
    return rules_root()


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value) if isinstance(value, (str, int, float)) and not isinstance(value, bool) else default
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)


def _required_path(data: dict, key: str) -> Path:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        fail("E_INPUT_NOT_FOUND", f"{key} is required")
        return Path.cwd()
    path = Path(value).expanduser().resolve()
    if key == "run_dir" and not path.exists():
        fail("E_INPUT_NOT_FOUND", f"run_dir does not exist: {path}")
    return path


def _feedback_text(data: dict) -> str:
    inline = _optional_string(data.get("feedback_text"))
    if inline:
        return inline
    feedback_file = _optional_string(data.get("feedback_file"))
    if feedback_file:
        path = Path(feedback_file).expanduser().resolve()
        if not path.exists():
            fail("E_INPUT_NOT_FOUND", f"feedback_file does not exist: {path}")
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    fail("E_INPUT_NOT_FOUND", "feedback_text or feedback_file is required")
    return ""


def _rules_dir(data: dict) -> Path:
    value = _optional_string(data.get("rules_dir"))
    if value:
        return Path(value).expanduser().resolve()
    return Path.cwd() / ".kbprep" / "rules" / "user"


def _action(data: dict, text: str) -> str:
    explicit = _optional_string(data.get("action"))
    if explicit:
        if explicit not in {"discard", "review", "protect"}:
            fail("E_INVALID_INPUT", "action must be discard, review, or protect")
        return explicit
    rules = load_cleaning_rules()
    if _matches_feedback_intent(text, rules.feedback_protect_intent_terms):
        return "protect"
    if _matches_feedback_intent(text, rules.feedback_discard_intent_terms):
        return "discard"
    return "review"


def _matches_feedback_intent(text: str, terms: tuple[str, ...]) -> bool:
    text_norm = text.casefold()
    return any(term.casefold() in text_norm for term in terms if term)


def _scope(data: dict) -> str:
    scope = _optional_string(data.get("scope")) or "user"
    if scope not in {"global", "user", "project", "document_type", "source_pattern"}:
        fail("E_INVALID_INPUT", "scope must be global, user, project, document_type, or source_pattern")
    return scope


def _match_type(data: dict) -> str:
    match = _optional_string(data.get("match")) or "literal"
    if match not in {"literal", "regex"}:
        fail("E_INVALID_INPUT", "match must be literal or regex")
    return match


def _pattern(data: dict, feedback_text: str) -> str:
    explicit = _optional_string(data.get("pattern"))
    if explicit:
        return explicit
    quoted = re.findall(r"[「“\"']([^」”\"']{2,120})[」”\"']", feedback_text)
    if quoted:
        return quoted[0].strip()
    examples = _string_list(data.get("examples"))
    if examples:
        return examples[0].strip()[:120]
    cleaned = re.sub(r"\s+", " ", feedback_text).strip()
    return cleaned[:120] if cleaned else "manual feedback"


def _run_artifacts(run_dir: Path) -> dict:
    quality = _read_json_file(run_dir / "quality_report.json")
    metadata = _read_json_file(run_dir / "run_metadata.json")
    raw_prepare_payload = metadata.get("prepare_payload")
    prepare_payload: dict[str, Any] = raw_prepare_payload if isinstance(raw_prepare_payload, dict) else {}
    raw_input_path = prepare_payload.get("input_path")
    input_path = raw_input_path if isinstance(raw_input_path, str) else ""
    source_identity = _metadata_source_identity(metadata, input_path)
    texts = {
        "discarded": _read_text_sample(run_dir / "discarded.md"),
        "cleaned": _read_text_sample(run_dir / "cleaned.md"),
        "review_needed": _read_text_sample(run_dir / "review_needed.md"),
    }
    failed_gates = []
    gates = quality.get("quality_gates", [])
    if isinstance(gates, list):
        for gate in gates:
            if isinstance(gate, dict) and gate.get("status") == "fail" and isinstance(gate.get("name"), str):
                failed_gates.append(gate["name"])
    strict_errors = quality.get("strict_errors", [])
    context = {
        "source_type": quality.get("source_type") if isinstance(quality.get("source_type"), str) else "",
        "profile": quality.get("profile") if isinstance(quality.get("profile"), str) else "",
        "document_type": quality.get("document_type") if isinstance(quality.get("document_type"), str) else "",
        "failed_gates": failed_gates,
        "strict_error_count": len(strict_errors) if isinstance(strict_errors, list) else 0,
        "input_path": input_path,
        "source_name": _optional_string(source_identity.get("source_name")) or (Path(input_path).name if input_path else ""),
        "source_identity": source_identity,
        "files_seen": [
            name for name in ("quality_report.json", "discarded.md", "cleaned.md", "review_needed.md")
            if (run_dir / name).exists()
        ],
    }
    return {"context": context, "texts": texts}


def _metadata_source_identity(metadata: dict, input_path: str) -> dict:
    raw = metadata.get("source_identity")
    if isinstance(raw, dict):
        identity = dict(raw)
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {}
        identity = parsed if isinstance(parsed, dict) else {"source_identity": raw.strip()}
    else:
        identity = {}
    if input_path:
        identity.setdefault("input_path", input_path)
        identity.setdefault("source_path", input_path)
        identity.setdefault("source_name", Path(input_path).name)
    return identity


def _read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _read_text_sample(path: Path, max_chars: int = 100_000) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""


def _source_pattern_payload(data: dict, artifacts: dict) -> dict:
    if _scope(data) != "source_pattern":
        return {}
    explicit = _optional_string(data.get("source_pattern"))
    if explicit:
        return {"source_pattern": explicit}
    context = artifacts["context"]
    domain = _source_domain_from_context(context)
    if domain:
        return {"source_pattern": f"source_domain:{domain}"}
    inferred = _optional_string(context.get("source_name"))
    if inferred:
        return {"source_pattern": inferred}
    fail("E_INVALID_INPUT", "source_pattern is required when scope is source_pattern and it cannot be inferred from run metadata")
    return {}


def _proposal_scope_payload(data: dict, artifacts: dict, rules_dir: Path, action: str, match: str, pattern: str) -> dict:
    del rules_dir, action, match, pattern
    if _optional_string(data.get("scope")):
        return {"scope": _scope(data), **_source_pattern_payload(data, artifacts)}
    return {"scope": _scope(data)}


def _source_domain_from_context(context: dict) -> str:
    explicit = _source_identity_value(context, "source_domain")
    if explicit:
        return explicit.lower().removeprefix("www.")
    for key in ("source_url", "origin_url"):
        value = _source_identity_value(context, key)
        if not value:
            continue
        parsed = urlparse(value)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain:
            return domain
    return ""


def _source_identity_value(context: dict, key: str) -> str:
    identity = _source_identity_from_context(context)
    value = identity.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    nested = identity.get("source_metadata")
    if isinstance(nested, dict):
        nested_value = nested.get(key)
        if isinstance(nested_value, str) and nested_value.strip():
            return nested_value.strip()
    value = context.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _source_identity_from_context(context: dict) -> dict:
    value = context.get("source_identity")
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {"source_identity": value.strip()}
        if isinstance(parsed, dict):
            return parsed
        return {"source_identity": value.strip()}
    return {}
