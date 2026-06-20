"""Lightweight document type classification for rule selection."""

from __future__ import annotations

import re
from typing import Any

from .document_type_signals import load_document_type_signals

DOCUMENT_CLASSIFICATION_SCHEMA = "kbprep.document_classification.v1"
SUPPORTED_DOCUMENT_TYPES = {"report", "course", "transcript", "webpage", "ebook", "code", "unknown"}


def classify_document_type(text: str, source_type: str = "", diagnosis: dict | None = None) -> dict:
    diagnosis = diagnosis or {}
    detected_format = str(diagnosis.get("detected_format") or "").lower()
    text_sample = (text or "")[:200_000]
    signals = load_document_type_signals()
    supported = set(signals.supported_document_types) or SUPPORTED_DOCUMENT_TYPES
    scores = {name: 0 for name in supported}
    reasons: dict[str, list[str]] = {name: [] for name in supported}

    def add(name: str, score: int, reason: str) -> None:
        if name not in scores:
            return
        scores[name] += score
        reasons[name].append(reason)

    normalized_source_type = str(source_type or "").lower()
    for hint in signals.source_type_hints:
        if normalized_source_type == hint.value:
            add(hint.document_type, hint.score, hint.reason)
    for hint in signals.format_hints:
        if detected_format == hint.value:
            add(hint.document_type, hint.score, hint.reason)
    for pattern in signals.content_patterns:
        if re.search(pattern.pattern, text_sample, pattern.flags):
            add(pattern.document_type, pattern.score, pattern.reason)

    best = max((name for name in supported if name != "unknown"), key=lambda name: scores.get(name, 0))
    best_score = scores[best]
    if best_score <= 0:
        return {
            "document_type": "unknown",
            "confidence": 0.1,
            "reasons": ["no strong document-type signals detected"],
            "scores": scores,
        }

    confidence = min(0.95, 0.35 + best_score / 12)
    return {
        "document_type": best,
        "confidence": round(confidence, 3),
        "reasons": reasons[best],
        "scores": scores,
    }


def build_document_classification_artifact(
    *,
    text: str,
    source_type: str = "",
    diagnosis: dict | None = None,
    classification: dict | None = None,
) -> dict[str, Any]:
    diagnosis = diagnosis or {}
    classification = classification or classify_document_type(text, source_type=source_type, diagnosis=diagnosis)
    document_type = str(classification.get("document_type") or "unknown")
    confidence = float(classification.get("confidence") or 0)
    usable_for_policy = document_type != "unknown" and confidence >= 0.5 and bool(classification.get("reasons"))
    artifact: dict[str, Any] = {
        "schema": DOCUMENT_CLASSIFICATION_SCHEMA,
        "status": "partial",
        "document_type": document_type,
        "confidence": round(confidence, 3),
        "usable_for_policy": usable_for_policy,
        "candidates": _candidate_rows(classification),
        "reasons": list(classification.get("reasons") or []),
        "evidence": _classification_evidence(text, source_type, diagnosis),
    }
    if not usable_for_policy:
        artifact["insufficient_reason"] = _insufficient_reason(document_type, confidence)
    return artifact


def _candidate_rows(classification: dict) -> list[dict[str, Any]]:
    raw_scores = classification.get("scores")
    scores = raw_scores if isinstance(raw_scores, dict) else {}
    rows = [
        {"document_type": str(name), "score": int(score or 0)}
        for name, score in scores.items()
    ]
    return sorted(rows, key=lambda item: (-item["score"], item["document_type"]))


def _classification_evidence(text: str, source_type: str, diagnosis: dict) -> dict[str, Any]:
    sample = text or ""
    lines = [line for line in sample.splitlines() if line.strip()]
    heading_count = len(re.findall(r"(?m)^#{1,6}\s+\S+", sample))
    signals = load_document_type_signals()
    return {
        "source_type": source_type,
        "detected_format": str(diagnosis.get("detected_format") or ""),
        "signal_source": _display_signal_source(signals.source),
        "total_chars": len(sample),
        "line_count": len(lines),
        "heading_count": heading_count,
        "heading_density": round(heading_count / max(len(lines), 1), 3),
        "link_count": len(re.findall(r"\[[^\]]+\]\([^)]+\)|https?://", sample)),
        "table_row_count": len(re.findall(r"(?m)^\s*\|.+\|\s*$", sample)),
        "code_fence_count": sample.count("```") // 2,
        "timestamp_count": len(re.findall(r"(?m)^\s*\d{1,2}:\d{2}\b", sample)),
    }


def _display_signal_source(source: str) -> str:
    normalized = source.replace("\\", "/")
    return normalized if normalized.startswith("rules/") else f"rules/{normalized}"


def _insufficient_reason(document_type: str, confidence: float) -> str:
    if document_type == "unknown":
        return "no strong document-type signals detected"
    return f"classification confidence {confidence:.3f} is below the policy-use threshold"
