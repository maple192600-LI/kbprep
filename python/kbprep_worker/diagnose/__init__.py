"""diagnose - file quality diagnosis for kbprep.

Read-only: does not modify any files. Public imports remain compatible with the
old ``kbprep_worker.diagnose`` module while implementation lives in focused
submodules.
"""

from __future__ import annotations

from .format_detect import analyze_audio_video, analyze_ebook, analyze_markdown, analyze_office
from .pdf_analysis import analyze_pdf
from .runtime import EXTENSION_MAP, SOURCE_TYPE_MAP, DiagnoseError, diagnose_file, run
from .text_quality import analyze_text_quality, detect_text_profile

__all__ = [
    "DiagnoseError",
    "EXTENSION_MAP",
    "SOURCE_TYPE_MAP",
    "analyze_audio_video",
    "analyze_ebook",
    "analyze_markdown",
    "analyze_office",
    "analyze_pdf",
    "analyze_text_quality",
    "detect_text_profile",
    "diagnose_file",
    "run",
]
