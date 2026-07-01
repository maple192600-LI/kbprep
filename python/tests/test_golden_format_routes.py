import json
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
        self.assertEqual(by_capability["image_ocr"]["expected_status"], "verified")
        self.assertEqual(by_capability["legacy_office_pdf_bridge"]["expected_status"], "unsupported")
        self.assertEqual(by_capability["media_local_transcript"]["expected_status"], "verified")
        self.assertEqual(by_capability["youtube_url_routes"]["expected_status"], "partial")
        self.assertEqual(by_capability["mobi_unsupported"]["expected_status"], "unsupported")

        for sample in samples:
            capability = get_capability_for_extension(sample["extension"])
            self.assertEqual(capability["id"], sample["capability_id"])
            self.assertEqual(capability["status"], sample["expected_status"])
            self.assertEqual(capability["route"], sample["expected_route"])
            # promote_to_verified / promotion_blocker 必须与 expected_status 一致：
            # verified 的 sample 已走完 promotion（promote=true、blocker 空）；
            # 非 verified 的 sample 不得声称已 promote（promote=false）。
            if sample["expected_status"] == "verified":
                self.assertTrue(
                    sample["promote_to_verified"],
                    f"{sample['capability_id']}: verified sample must mark promote_to_verified=true",
                )
                self.assertEqual(
                    sample["promotion_blocker"], "",
                    f"{sample['capability_id']}: verified sample must clear promotion_blocker",
                )
            else:
                self.assertFalse(
                    sample["promote_to_verified"],
                    f"{sample['capability_id']}: non-verified sample must not claim promote_to_verified",
                )

    def test_verified_promotion_requires_real_tool_evidence(self):
        """verified promotion 门禁：按类型结构化声明工具 + 真实 fixture + 验收记录。

        required_tools 分 PATH 工具（``shutil.which`` 可查的二进制名）与 Python 库
        （``importlib.util.find_spec`` 可查的模块名）。这两类的运行时存在性由各
        converter 内部的 ``_missing_dependency`` 守（见 converters/asr.py、
        external_tools.py），不在本测试范围——GPU ASR 模型（qwen3-asr）不可能出现在
        每台 CI 机器上，verified 的承诺靠 fixture + content-hash 锁定兑现
        （见 test_media_asr_fixture.py）。

        本测试守声明层：verified 的 capability 必须如实按类型声明工具依赖（不能用
        描述性文字混充工具名），并配有真实固化 fixture 与人工验收记录。
        """
        manifest = _load_manifest()
        for sample in manifest["samples"]:
            if sample["expected_status"] != "verified":
                continue
            tools = sample["required_tools"]
            self.assertIsInstance(
                tools, dict,
                f"{sample['capability_id']}: required_tools must be structured as {{path, python}}",
            )
            self.assertIn("path", tools, f"{sample['capability_id']}: required_tools missing 'path'")
            self.assertIn("python", tools, f"{sample['capability_id']}: required_tools missing 'python'")
            # PATH 工具名必须是可被 shutil.which 查到的二进制名，不能是描述性文字
            for tool in tools["path"]:
                self.assertRegex(
                    tool, r"^[a-z][a-z0-9._-]*$",
                    f"{sample['capability_id']}: path tool must be a binary name, got {tool!r}",
                )
            # Python 模块名必须是可 import 形态（下划线），不能是连字符或描述文字
            for module in tools["python"]:
                self.assertRegex(
                    module, r"^[a-z_][a-z0-9_]*$",
                    f"{sample['capability_id']}: python entry must be an importable module name, got {module!r}",
                )
            self.assertTrue(
                sample["real_fixture"],
                f"{sample['capability_id']}: verified needs real_fixture",
            )
            self.assertTrue(
                sample["manual_acceptance_evidence"],
                f"{sample['capability_id']}: verified needs manual_acceptance_evidence",
            )


def _load_manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


if __name__ == "__main__":
    unittest.main()
