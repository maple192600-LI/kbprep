"""Generate bounded review packs for human or external AI review."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_json
from ..quality.thresholds import review_pack_low_confidence_threshold
from ..rule_loader import load_cleaning_rules
from ..rule_schema import ClassificationPattern

POLICY_CONTEXT_ITEM_LIMIT = 16
POLICY_CONTEXT_TEXT_LIMIT = 96


def _generate_review_pack(
    blocks: list[dict[str, Any]],
    run_dir: Path,
    source_type: str,
    *,
    source_quality: str = "",
    document_type: str = "",
    profile: str = "standard",
    source_identity: str = "",
) -> None:
    candidates = []
    low_confidence_threshold = review_pack_low_confidence_threshold(
        source_quality=source_quality,
        document_type=document_type,
    )
    for block in blocks:
        if _review_pack_block_needs_review(block, low_confidence_threshold):
            candidates.append(_review_pack_candidate(block))
    pack = {
        "schema": "kbprep.review_pack.v1",
        "source_type": source_type,
        "document_type": document_type,
        "low_confidence_threshold": low_confidence_threshold,
        "context_policy": {
            "block_text": "candidate_blocks_only",
            "neighbor_text": "not_included",
            "policy_context_item_limit": POLICY_CONTEXT_ITEM_LIMIT,
        },
        "policy_context": _policy_context(
            profile=profile,
            document_type=document_type,
            source_identity=source_identity,
        ),
        "instructions": [
            "Classify blocks only; never rewrite text.",
            "Prefer keep or review when a block may contain usable knowledge.",
            "Never discard steps, prompts, code, tables, tool names, numbers, parameters, links, or concrete examples.",
            "For curated Obsidian use, discard pure author bios, usernames, self-introductions, credentials, and identity wrappers when they do not carry reusable knowledge.",  # noqa: E501
            "If removing a block would break continuity, references, setup, or a later method/case, mark it review instead of discard.",
            "Return RFC 6902 JSON Patch operations against /blocks/<block_id>/<field>.",
        ],
        "blocks": candidates,
    }
    atomic_write_json(
        run_dir / "review_pack.json",
        pack,
        indent=2,
        trailing_newline=False,
    )


def _review_pack_block_needs_review(block: dict[str, Any], low_confidence_threshold: float) -> bool:
    status = block.get("status")
    risk_tags = block.get("risk_tags", [])
    confidence = float(block.get("confidence") or 0)
    return status == "review" or bool(risk_tags) or confidence < low_confidence_threshold


def _review_pack_candidate(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "block_id": block.get("block_id"),
        "type": block.get("type"),
        "status": block.get("status"),
        "risk_tags": block.get("risk_tags", []),
        "reason": block.get("reason", ""),
        "confidence": float(block.get("confidence") or 0),
        "protected": bool(block.get("protected")),
        "heading_path": block.get("heading_path", []),
        "page_range": [block.get("page_start"), block.get("page_end")],
        "text": block.get("text", ""),
        "allowed_patch_fields": ["status", "risk_tags", "reason", "confidence"],
    }


def _policy_context(*, profile: str, document_type: str, source_identity: str) -> dict[str, Any]:
    rules = load_cleaning_rules(
        profile=profile,
        document_type=document_type,
        source_identity=source_identity,
    )
    terms = [
        *rules.knowledge_terms,
        *rules.business_method_context_terms,
        *rules.marketing_wrapper_heading_terms,
        *rules.marketing_wrapper_back_matter_terms,
        *rules.cta_keywords,
    ]
    return {
        "document_type": document_type,
        "profile": profile,
        "relevant_terms": _bounded_strings(terms),
        "protected_patterns": _bounded_patterns(rules.protected_patterns),
        "rule_sources": _bounded_strings(rules.sources),
    }


def _bounded_strings(values: tuple[str, ...] | list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        result.append(text[:POLICY_CONTEXT_TEXT_LIMIT])
        seen.add(text)
        if len(result) >= POLICY_CONTEXT_ITEM_LIMIT:
            break
    return result


def _bounded_patterns(values: tuple[ClassificationPattern, ...]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        label = value.label.strip()
        pattern = value.pattern.strip()
        key = (label, pattern)
        if not label or not pattern or key in seen:
            continue
        result.append({
            "label": label[:POLICY_CONTEXT_TEXT_LIMIT],
            "pattern": pattern[:POLICY_CONTEXT_TEXT_LIMIT],
        })
        seen.add(key)
        if len(result) >= POLICY_CONTEXT_ITEM_LIMIT:
            break
    return result
