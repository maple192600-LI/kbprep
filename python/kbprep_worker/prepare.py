"""Thin entrypoint for the single-file KBPrep prepare pipeline.

The implementation lives in ``kbprep_worker.stages.pipeline`` so this public
module stays small while preserving compatibility for existing imports.
"""

from .prepare_artifacts import apply_artifact_policy as _apply_artifact_policy
from .stages.pipeline import (
    PipelineError,
    _find_existing_run,
    _run_mineru_conversion,
    run,
)
from .supported_formats import (
    DIRECT_EXTENSIONS,
    EPUB_EXTENSIONS,
    MEDIA_EXTENSIONS,
    OFFICE_XML_EXTENSIONS,
)

__all__ = [
    "DIRECT_EXTENSIONS",
    "EPUB_EXTENSIONS",
    "MEDIA_EXTENSIONS",
    "OFFICE_XML_EXTENSIONS",
    "PipelineError",
    "_apply_artifact_policy",
    "_find_existing_run",
    "_run_mineru_conversion",
    "run",
]
