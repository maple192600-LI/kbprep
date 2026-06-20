"""Compatibility surface for the KBPrep prepare pipeline.

The full implementation lives in `pipeline_core` while this module stays small
enough to audit and preserves the historical import paths used by tests and
callers.
"""
from __future__ import annotations

from . import pipeline_core as _core

PipelineError = _core.PipelineError


def run(data: dict) -> None:
    """Run the single-file prepare pipeline."""
    for name in ("_read_direct_source",):
        if name in globals():
            setattr(_core, name, globals()[name])
            from . import local_conversion

            setattr(local_conversion, name, globals()[name])
    return _core.run(data)


def __getattr__(name: str):
    return getattr(_core, name)
