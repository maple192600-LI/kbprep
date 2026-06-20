"""Small file readers for quality checks."""

import json
from pathlib import Path


def _read_json_file(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


read_json_file = _read_json_file
