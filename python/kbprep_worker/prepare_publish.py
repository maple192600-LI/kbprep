"""Source-side final output publishing helpers for prepare."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .atomic_io import atomic_write_text
from .supported_formats import MARKDOWN_EXTENSIONS


def publish_direct_final_to_source(run_dir: Path, input_p: Path) -> None:
    cleaned_src = run_dir / "cleaned.md"
    if not cleaned_src.exists():
        return

    final_md = source_final_markdown_path(input_p)
    final_md.parent.mkdir(parents=True, exist_ok=True)
    text = cleaned_src.read_text(encoding="utf-8")

    images_src = run_dir / "images"
    if images_src.exists() and any(p.is_file() for p in images_src.rglob("*")):
        assets_dir = source_final_assets_dir(input_p)
        assets_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(images_src, assets_dir, dirs_exist_ok=True)
        try:
            asset_rel = assets_dir.relative_to(final_md.parent).as_posix()
        except ValueError:
            asset_rel = os.path.relpath(assets_dir, final_md.parent).replace("\\", "/")
        text = rewrite_markdown_image_refs(text, asset_rel)

    atomic_write_text(final_md, text)


def source_final_markdown_path(input_p: Path | None) -> Path:
    if input_p is None:
        return Path("cleaned.md")
    stem = safe_source_stem(input_p)
    if input_p.suffix.lower() in MARKDOWN_EXTENSIONS:
        return input_p.with_name(f"{stem}.cleaned.md")
    return input_p.with_name(f"{stem}.md")


def source_final_assets_dir(input_p: Path | None) -> Path:
    if input_p is None:
        return Path("cleaned.assets")
    return input_p.with_name(f"{safe_source_stem(input_p)}.assets")


def safe_source_stem(input_p: Path) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", input_p.stem).strip(" ._")
    if not stem:
        stem = "cleaned"
    return stem


def rewrite_markdown_image_refs(text: str, asset_rel: str) -> str:
    return re.sub(
        r"(!\[[^\]]*\]\()images[/\\]([^)]+)(\))",
        lambda m: f"{m.group(1)}{asset_rel}/{m.group(2).replace(chr(92), '/')}{m.group(3)}",
        text,
    )
