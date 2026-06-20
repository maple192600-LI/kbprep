from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuditContext:
    input_name: str
    file_hash: str
    plugin_version: str
    mineru_version: str
    python_version: str
    runtime: dict[str, Any]
    diagnosis: dict[str, Any]
    blocks: list[dict[str, Any]]
    quality_report: dict[str, Any]
    warnings: list[str]
    strict_errors: list[str]


def generate_audit_md(context: AuditContext) -> str:
    return _generate_audit_md(
        input_name=context.input_name,
        file_hash=context.file_hash,
        plugin_version=context.plugin_version,
        mineru_version=context.mineru_version,
        python_version=context.python_version,
        runtime=context.runtime,
        diagnosis=context.diagnosis,
        blocks=context.blocks,
        quality_report=context.quality_report,
        warnings=context.warnings,
        strict_errors=context.strict_errors,
    )


def _generate_audit_md(
    input_name: str,
    file_hash: str,
    plugin_version: str,
    mineru_version: str,
    python_version: str,
    runtime: dict,
    diagnosis: dict,
    blocks: list[dict],
    quality_report: dict,
    warnings: list[str],
    strict_errors: list[str],
) -> str:
    lines = _input_section(input_name, file_hash, plugin_version, mineru_version, python_version, runtime)
    lines.extend(_diagnosis_section(diagnosis))
    lines.extend(_block_statistics_section(blocks))
    lines.extend(_deleted_content_section(blocks))
    lines.extend(_evidence_section(blocks))
    lines.extend(_risk_section(blocks))
    lines.extend(_review_section(blocks))
    lines.extend(_message_section("Warnings", warnings))
    lines.extend(_message_section("Strict Errors", strict_errors))
    return "\n".join(lines)


def _input_section(
    input_name: str,
    file_hash: str,
    plugin_version: str,
    mineru_version: str,
    python_version: str,
    runtime: dict,
) -> list[str]:
    return [
        "# kbprep audit",
        "",
        "## Input",
        f"Filename: {input_name}",
        f"SHA256: {file_hash}",
        f"Plugin version: {plugin_version}",
        f"MinerU version: {mineru_version}",
        f"Python version: {python_version}",
        f"Python executable: {runtime.get('python_executable', 'unknown')}",
        f"MinerU path: {runtime.get('mineru_path', 'unknown')}",
        f"Torch: {runtime.get('torch', 'unknown')}",
        f"CUDA available: {runtime.get('torch_cuda_available', 'unknown')}",
        f"CUDA version: {runtime.get('torch_cuda_version', 'unknown')}",
        f"MinerU device: {runtime.get('mineru_device', 'unknown')}",
        "",
    ]


def _diagnosis_section(diagnosis: dict) -> list[str]:
    return [
        "## Diagnosis",
        f"Format: {diagnosis.get('detected_format', 'unknown')}",
        f"Text layer health: {diagnosis.get('text_layer_health', 'unknown')}",
        f"Garbled ratio: {diagnosis.get('text_quality', {}).get('garbled_ratio', 'N/A')}",
        f"Needs OCR: {diagnosis.get('needs_ocr', 'unknown')}",
        "",
    ]


def _block_statistics_section(blocks: list[dict]) -> list[str]:
    status_counts: dict[str, int] = {}
    for block in blocks:
        status = str(block.get("status", "unclassified"))
        status_counts[status] = status_counts.get(status, 0) + 1
    lines = ["## Block Statistics"]
    lines.extend(f"- {status}: {count}" for status, count in sorted(status_counts.items()))
    return [*lines, ""]


def _deleted_content_section(blocks: list[dict]) -> list[str]:
    discard_blocks = [block for block in blocks if block.get("status") == "discard"]
    if not discard_blocks:
        return []
    lines = ["## Deleted Content"]
    for block in discard_blocks[:50]:
        lines.append(f"- {block.get('block_id', '?')}: {block.get('type', 'unknown')}, reason: {block.get('reason', '')}")
    if len(discard_blocks) > 50:
        lines.append(f"- ... and {len(discard_blocks) - 50} more")
    return [*lines, ""]


def _evidence_section(blocks: list[dict]) -> list[str]:
    evidence_blocks = [block for block in blocks if block.get("status") == "evidence"]
    if not evidence_blocks:
        return []
    lines = ["## Evidence"]
    lines.extend(f"- {block.get('block_id', '?')}: {block.get('type', 'unknown')}" for block in evidence_blocks[:30])
    return [*lines, ""]


def _risk_section(blocks: list[dict]) -> list[str]:
    risk_blocks = [block for block in blocks if block.get("status") == "keep" and block.get("risk_tags")]
    if not risk_blocks:
        return []
    lines = ["## High-Risk Kept Content"]
    for block in risk_blocks[:30]:
        tags = ", ".join(block.get("risk_tags", []))
        lines.append(f"- {block.get('block_id', '?')}: {tags}, reason: {block.get('reason', '')}")
    return [*lines, ""]


def _review_section(blocks: list[dict]) -> list[str]:
    review_blocks = [block for block in blocks if block.get("status") == "review"]
    if not review_blocks:
        return []
    lines = ["## Needs Review"]
    for block in review_blocks[:30]:
        lines.append(f"- {block.get('block_id', '?')}: {block.get('type', 'unknown')}, reason: {block.get('reason', '')}")
    return [*lines, ""]


def _message_section(title: str, messages: list[str]) -> list[str]:
    if not messages:
        return []
    return [f"## {title}", *(f"- {message}" for message in messages), ""]
