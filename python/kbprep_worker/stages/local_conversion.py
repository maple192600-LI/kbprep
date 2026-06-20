"""Local direct and Office XML conversions used by the prepare pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..atomic_io import atomic_write_text
from ..converters.office_xml import (
    OfficeXmlConversionError,
    office_xml_to_markdown,
    write_pptx_content_list,
)
from ..supported_formats import MARKDOWN_EXTENSIONS
from .pipeline_helpers import _copy_local_markdown_image_assets, _read_direct_source, _validate_convertible_container
from .pipeline_state import PipelineError, PipelineState


def convert_direct_text(
    state: PipelineState,
    converted_path: Path,
    run_dir: Path,
    match_evidence: tuple[str, ...],
    ext: str,
) -> None:
    direct_read_kwargs: dict[str, Any] = {"run_dir": run_dir}
    if "html_signature" in match_evidence:
        direct_read_kwargs["force_html"] = True
    text = _read_direct_source(state.input_p, **direct_read_kwargs)
    if ext in MARKDOWN_EXTENSIONS:
        text, local_image_artifacts = _copy_local_markdown_image_assets(text, state.input_p, run_dir)
        state.mineru_artifacts.update(local_image_artifacts)
        state.warnings.extend(local_image_artifacts.get("warnings", []))
    atomic_write_text(converted_path, text)


def convert_office_xml(state: PipelineState, converted_path: Path, run_dir: Path, ext: str) -> None:
    _validate_convertible_container(state.input_p)
    try:
        text, office_warnings, office_artifacts = office_xml_to_markdown(state.input_p, run_dir)
    except OfficeXmlConversionError as exc:
        raise PipelineError(exc.code, exc.message, exc.details)
    atomic_write_text(converted_path, text)
    state.mineru_artifacts.update(office_artifacts)
    if ext == ".pptx":
        state.mineru_artifacts.update(write_pptx_content_list(text, run_dir))
        state.diagnosis["split_strategy"] = "preserve_slide_or_page_order"
    state.warnings.extend(office_warnings)
