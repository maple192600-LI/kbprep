"""Repository-root import shim for local Python commands.

The installable worker package lives under `python/kbprep_worker`. This shim
lets root-level commands such as `python -m unittest discover -s python/tests`
import it without requiring PYTHONPATH.
"""
from __future__ import annotations

from pathlib import Path

_REAL_PACKAGE = Path(__file__).resolve().parents[1] / "python" / "kbprep_worker"
__path__ = [str(_REAL_PACKAGE)]

_init_file = _REAL_PACKAGE / "__init__.py"
if _init_file.is_file():
    exec(compile(_init_file.read_text(encoding="utf-8"), str(_init_file), "exec"), globals())
