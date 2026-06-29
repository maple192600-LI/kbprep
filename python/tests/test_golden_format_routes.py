import json
import shutil
import unittest
from pathlib import Path

from kbprep_worker.converter_capabilities import get_capability_for_extension

MANIFEST_PATH = Path(__file__).parent / "golden" / "formats" / "manifest.json"


class GoldenFormatRouteTests(unittest.TestCase):
    def test_golden_format_manifest_records_truthful_statuses(self):
        manifest = _load_manifest()
        samples = manifest["samples"]

        self.assertGreaterEqual(len(samples), 4)
        by_capability = {sample["capability_id"]: sample for sample in samples}
        self.assertEqual(by_capability["image_ocr"]["expected_status"], "experimental")
        self.assertEqual(by_capability["legacy_office_pdf_bridge"]["expected_status"], "unsupported")
        self.assertEqual(by_capability["media_local_transcript"]["expected_status"], "partial")
        self.assertEqual(by_capability["youtube_url_routes"]["expected_status"], "partial")
        self.assertEqual(by_capability["mobi_unsupported"]["expected_status"], "unsupported")

        for sample in samples:
            capability = get_capability_for_extension(sample["extension"])
            self.assertEqual(capability["id"], sample["capability_id"])
            self.assertEqual(capability["status"], sample["expected_status"])
            self.assertEqual(capability["route"], sample["expected_route"])
            self.assertFalse(sample["promote_to_verified"])

    def test_verified_promotion_requires_real_tool_evidence(self):
        manifest = _load_manifest()
        for sample in manifest["samples"]:
            if sample["expected_status"] != "verified":
                continue
            missing = [tool for tool in sample["required_tools"] if shutil.which(tool) is None]
            self.assertEqual(missing, [], f"{sample['capability_id']} verified without tools: {missing}")
            self.assertTrue(sample["real_fixture"])
            self.assertTrue(sample["manual_acceptance_evidence"])


def _load_manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


if __name__ == "__main__":
    unittest.main()
