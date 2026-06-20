"""Format-route acceptance checks for KBPrep local converters."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "python"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

TEST_NAMES = [
    "python.tests.test_converter_registry",
    "python.tests.test_external_tools",
    "python.tests.test_external_route_integration",
    "python.tests.test_epub_converter",
    "python.tests.test_zip_safety",
    "python.tests.test_frontmatter_safety",
    "python.tests.test_golden_format_routes",
    "python.tests.test_diagnose_text_quality",
    "python.tests.test_round2_coverage_converters_diagnose",
]


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromNames(TEST_NAMES)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    summary = {
        "schema": "kbprep.acceptance.formats.v1",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "successful": result.wasSuccessful(),
        "covered_routes": [
            "language_detection_ch_en",
            "pdf_text_layer_or_mineru_auto_or_ocr",
            "image_to_pdf_then_mineru_ocr",
            "legacy_office_to_pdf_route",
            "media_to_transcript",
            "epub_xhtml_safe_zip",
            "frontmatter_yaml_escape",
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
