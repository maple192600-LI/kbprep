"""Body-note rendering for Obsidian knowledge-base output."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..atomic_io import atomic_write_text
from ..detect import detect_language_from_text
from ..fs_safety import safe_rmtree
from ..render_outputs import _block_meta_comment
from .context import ObsidianContext, context_for_template
from .frontmatter import _yaml_safe
from .links import _safe_filename
from .signals import IMAGE_TYPES, _is_internal_page_marker, _is_knowledge_diagram
from .titles import _heading_title, complete_body_filename


@dataclass(frozen=True)
class ObsidianLabels:
    entry_heading: str
    complete_body: str
    cleaning_report: str
    review_needed: str
    stats_heading: str
    kept_blocks: str
    discarded_blocks: str
    review_blocks: str
    topic_notes: str
    deletion_types: str
    output_principles: str
    report_heading: str
    ungrouped_knowledge: str
    empty_value: str
    principles: tuple[str, ...]


ZH_LABELS = ObsidianLabels(
    entry_heading="入口",
    complete_body="完整正文",
    cleaning_report="清洗报告",
    review_needed="待复核内容",
    stats_heading="统计",
    kept_blocks="保留块",
    discarded_blocks="删除块",
    review_blocks="待复核块",
    topic_notes="主题笔记",
    deletion_types="删除类型",
    output_principles="输出原则",
    report_heading="{source_title} 清洗报告",
    ungrouped_knowledge="未分组知识",
    empty_value="无",
    principles=(
        "正文段落不改写、不总结、不合并。",
        "作者简介、身份包装、广告和图片类内容从正文剥离。",
        "被删除或待复核内容保留在 `_audit` 中，可追溯恢复。",
    ),
)

EN_LABELS = ObsidianLabels(
    entry_heading="Entry",
    complete_body="Complete body",
    cleaning_report="Cleaning report",
    review_needed="Review needed",
    stats_heading="Stats",
    kept_blocks="Kept blocks",
    discarded_blocks="Discarded blocks",
    review_blocks="Review blocks",
    topic_notes="Topic notes",
    deletion_types="Discarded types",
    output_principles="Output principles",
    report_heading="{source_title} Cleaning Report",
    ungrouped_knowledge="Ungrouped knowledge",
    empty_value="None",
    principles=(
        "Body paragraphs are not rewritten, summarized, or merged.",
        "Author bios, identity packaging, ads, and image-only material are separated from the main body.",
        "Discarded or review-needed content remains in `_audit` and can be restored.",
    ),
)


def render_obsidian_vault(
    blocks: list[dict],
    run_dir: str,
    source_title: str,
    source_hash: str,
    run_id: str,
    profile: str = "obsidian_kb",
    template_name: str = "obsidian_generic",
) -> None:
    """Render a text-first Obsidian wiki folder under run_dir/obsidian."""
    ctx = context_for_template(template_name)
    run_p = Path(run_dir)
    vault_dir, audit_dir = _prepare_obsidian_vault(run_p, ctx)
    _copy_vault_images(run_p, vault_dir)
    kept_blocks, review_blocks, discarded_blocks = _partition_obsidian_blocks(blocks)
    labels = _labels_for_obsidian_output(source_title, kept_blocks)
    complete_filename = complete_body_filename(source_title, ctx=ctx, duplicate_suffix=labels.complete_body)
    _write_complete_body(vault_dir, complete_filename, source_title, source_hash, run_id, profile, kept_blocks)

    note_entries, source_map = _render_topic_notes(kept_blocks, vault_dir, profile, ctx, labels)
    _render_index(
        vault_dir,
        source_title,
        complete_filename,
        note_entries,
        kept_blocks,
        discarded_blocks,
        review_blocks,
        profile,
        ctx,
        labels,
    )
    _render_audit_file(audit_dir / "discarded.md", discarded_blocks)
    _render_audit_file(audit_dir / "review_needed.md", review_blocks)
    _render_cleaning_report(
        audit_dir / "cleaning-report.md",
        source_title,
        kept_blocks,
        discarded_blocks,
        review_blocks,
        note_entries,
        labels,
    )
    _write_source_map(audit_dir / "source-map.jsonl", source_map)
    _copy_run_evidence_to_obsidian_audit(run_p, audit_dir)


def _prepare_obsidian_vault(run_dir: Path, ctx: ObsidianContext) -> tuple[Path, Path]:
    vault_dir = run_dir / "obsidian"
    if vault_dir.exists():
        safe_rmtree(vault_dir, root=run_dir)
    for subdir in [*ctx.categories, "_audit", "images"]:
        (vault_dir / subdir).mkdir(parents=True, exist_ok=True)
    return vault_dir, vault_dir / "_audit"


def _copy_vault_images(run_dir: Path, vault_dir: Path) -> None:
    source_images = run_dir / "images"
    vault_images = vault_dir / "images"
    if not source_images.exists():
        return
    safe_rmtree(vault_images, root=vault_dir)
    shutil.copytree(source_images, vault_images)


def _partition_obsidian_blocks(blocks: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    return (
        [block for block in blocks if block.get("status") == "keep" and _renderable_text(block)],
        [block for block in blocks if block.get("status") == "review"],
        [block for block in blocks if block.get("status") == "discard"],
    )


def _write_complete_body(
    vault_dir: Path,
    complete_filename: str,
    source_title: str,
    source_hash: str,
    run_id: str,
    profile: str,
    kept_blocks: list[dict],
) -> None:
    atomic_write_text(
        vault_dir / complete_filename,
        "\n".join([
            "---",
            f'title: "{_yaml_safe(source_title)}"',
            f"kbprep_profile: {profile}",
            f'source_sha256: "{source_hash}"',
            f'run_id: "{run_id}"',
            "---",
            "",
            _join_blocks(kept_blocks),
            "",
        ]),
        encoding="utf-8",
    )


def _write_source_map(path: Path, source_map: list[dict]) -> None:
    atomic_write_text(
        path,
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in source_map),
        encoding="utf-8",
    )


def _renderable_text(block: dict) -> str:
    text = (block.get("curated_text") or block.get("text") or "").strip()
    if not text:
        return ""
    if _is_internal_page_marker(text):
        return ""
    if block.get("type") in IMAGE_TYPES and not _is_knowledge_diagram(block):
        return ""
    return text


def _join_blocks(blocks: list[dict]) -> str:
    return "\n\n".join(_renderable_text(block) for block in blocks if _renderable_text(block))


def _copy_run_evidence_to_obsidian_audit(run_dir: Path, audit_dir: Path) -> None:
    for name in [
        "quality_report.json",
        "conversion_report.json",
        "diagnosis_report.json",
        "run_metadata.json",
        "source_conversion_integrity.json",
        "audit.md",
    ]:
        source = run_dir / name
        if source.exists():
            shutil.copy2(source, audit_dir / name)
    source_gate_dir = run_dir / "quality_gates"
    target_gate_dir = audit_dir / "quality_gates"
    if source_gate_dir.exists():
        if target_gate_dir.exists():
            safe_rmtree(target_gate_dir, root=audit_dir)
        shutil.copytree(source_gate_dir, target_gate_dir)


def _render_topic_notes(
    kept_blocks: list[dict],
    vault_dir: Path,
    profile: str,
    ctx: ObsidianContext,
    labels: ObsidianLabels,
) -> tuple[list[dict], list[dict]]:
    sections = _topic_sections(kept_blocks, ctx, labels)
    note_entries: list[dict] = []
    source_map: list[dict] = []
    counters = {category: 0 for category in ctx.categories}
    for section in sections:
        title = section["title"]
        category = _category_for_title(title, ctx)
        counters[category] += 1
        filename = f"{counters[category]:03d}-{_safe_filename(title)}.md"
        note_path = vault_dir / category / filename
        rel_note = f"{category}/{filename}"
        _write_topic_note(note_path, title, category, profile, section["blocks"])
        note_entries.append({"title": title, "category": category, "path": rel_note})
        source_map.extend(_topic_source_map(section["blocks"], rel_note, title))
    return note_entries, source_map


def _topic_sections(kept_blocks: list[dict], ctx: ObsidianContext, labels: ObsidianLabels) -> list[dict]:
    sections: list[dict] = []
    current: dict | None = None
    for block in kept_blocks:
        text = _renderable_text(block)
        if not text:
            continue
        if block.get("type") == "section_heading":
            if current and current["blocks"]:
                sections.append(current)
            current = {"title": _heading_title(text, ctx), "blocks": [block]}
            continue
        if current is None:
            current = {"title": labels.ungrouped_knowledge, "blocks": []}
        current["blocks"].append(block)
    if current and current["blocks"]:
        sections.append(current)
    return sections


def _write_topic_note(note_path: Path, title: str, category: str, profile: str, blocks: list[dict]) -> None:
    content = "\n".join([
        "---",
        f'title: "{_yaml_safe(title)}"',
        f'category: "{category}"',
        f"kbprep_profile: {profile}",
        "---",
        "",
        _join_blocks(blocks),
        "",
    ])
    atomic_write_text(note_path, content)


def _topic_source_map(blocks: list[dict], rel_note: str, title: str) -> list[dict]:
    return [
        {
            "block_id": block.get("block_id"),
            "type": block.get("type"),
            "status": block.get("status"),
            "note": rel_note,
            "heading": title,
        }
        for block in blocks
    ]


def _render_index(
    vault_dir: Path,
    source_title: str,
    complete_filename: str,
    note_entries: list[dict],
    kept_blocks: list[dict],
    discarded_blocks: list[dict],
    review_blocks: list[dict],
    profile: str,
    ctx: ObsidianContext,
    labels: ObsidianLabels,
) -> None:
    complete_link = complete_filename.removesuffix(".md")
    lines = [
        "---",
        f'title: "{_yaml_safe(source_title)}"',
        f"kbprep_profile: {profile}",
        "---",
        "",
        f"# {source_title}",
        "",
        f"## {labels.entry_heading}",
        "",
        f"- [[{complete_link}|{labels.complete_body}]]",
        f"- [[_audit/cleaning-report|{labels.cleaning_report}]]",
        f"- [[_audit/review_needed|{labels.review_needed}]]",
        "",
        f"## {labels.stats_heading}",
        "",
        f"- {labels.kept_blocks}: {len(kept_blocks)}",
        f"- {labels.discarded_blocks}: {len(discarded_blocks)}",
        f"- {labels.review_blocks}: {len(review_blocks)}",
        "",
    ]
    for category in ctx.categories:
        entries = [entry for entry in note_entries if entry["category"] == category]
        if not entries:
            continue
        lines.extend([f"## {category}", ""])
        for entry in entries:
            link = entry["path"].removesuffix(".md")
            lines.append(f"- [[{link}|{entry['title']}]]")
        lines.append("")
    atomic_write_text(vault_dir / "00-索引.md", "\n".join(lines))


def _render_audit_file(path: Path, blocks: list[dict]) -> None:
    lines: list[str] = []
    for block in blocks:
        lines.append(_block_meta_comment(block, include_reason=True))
        text = (block.get("text") or "").strip()
        if text:
            lines.append(text)
        lines.append("")
    atomic_write_text(path, "\n".join(lines))


def _render_cleaning_report(
    path: Path,
    source_title: str,
    kept_blocks: list[dict],
    discarded_blocks: list[dict],
    review_blocks: list[dict],
    note_entries: list[dict],
    labels: ObsidianLabels,
) -> None:
    type_counts: dict[str, int] = {}
    for block in discarded_blocks:
        block_type = str(block.get("type") or "unknown")
        type_counts[block_type] = type_counts.get(block_type, 0) + 1
    lines = [
        f"# {labels.report_heading.format(source_title=source_title)}",
        "",
        f"## {labels.output_principles}",
        "",
        *(f"- {principle}" for principle in labels.principles),
        "",
        f"## {labels.stats_heading}",
        "",
        f"- {labels.kept_blocks}: {len(kept_blocks)}",
        f"- {labels.discarded_blocks}: {len(discarded_blocks)}",
        f"- {labels.review_blocks}: {len(review_blocks)}",
        f"- {labels.topic_notes}: {len(note_entries)}",
        "",
        f"## {labels.deletion_types}",
        "",
    ]
    if type_counts:
        for block_type, count in sorted(type_counts.items()):
            lines.append(f"- {block_type}: {count}")
    else:
        lines.append(f"- {labels.empty_value}")
    lines.append("")
    atomic_write_text(path, "\n".join(lines))


def _category_for_title(title: str, ctx: ObsidianContext) -> str:
    if any(term in title for term in ctx.method_terms):
        return ctx.method_category
    if any(term in title for term in ctx.cognition_terms):
        return ctx.cognition_category
    if any(term in title for term in ctx.case_terms):
        return ctx.case_category
    return ctx.default_category


def _labels_for_obsidian_output(source_title: str, kept_blocks: list[dict]) -> ObsidianLabels:
    sample = "\n".join([source_title, *(_renderable_text(block) for block in kept_blocks[:20])])
    return ZH_LABELS if detect_language_from_text(sample) == "ch" else EN_LABELS
