import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.cleaning_patches import (
    build_cleaning_patches,
    validate_cleaning_patches_artifact,
    write_cleaning_patches,
)


class CleaningPatchTests(unittest.TestCase):
    def test_builds_safe_status_update_patch_without_text_content(self) -> None:
        patches = build_cleaning_patches(
            before_blocks=[{
                "block_id": "b1",
                "status": "keep",
                "type": "paragraph",
                "text": "DO_NOT_LEAK_SOURCE_TEXT",
                "line_start": 2,
                "line_end": 3,
            }],
            after_blocks=[{
                "block_id": "b1",
                "status": "discard",
                "type": "marketing_cta",
                "text": "DO_NOT_LEAK_SOURCE_TEXT",
                "line_start": 2,
                "line_end": 3,
                "cleaning_rule_id": "rule.cta",
                "cleaning_rule_source": "rules/base/obvious_noise.json",
                "risk_tags": ["marketing"],
                "reason": "DO_NOT_LEAK_RULE_REASON",
            }],
            policy_snapshot_hash="policy-1",
        )

        self.assertEqual(len(patches), 1)
        patch = patches[0]
        self.assertEqual(patch["schema"], "kbprep.cleaning_patch.v1")
        self.assertEqual(patch["change_type"], "status_update")
        self.assertEqual(patch["block_id"], "b1")
        self.assertEqual(patch["before"]["status"], "keep")
        self.assertEqual(patch["after"]["status"], "discard")
        self.assertEqual(patch["rule_id"], "rule.cta")
        self.assertEqual(patch["policy_snapshot_hash"], "policy-1")
        self.assertEqual(patch["location"], {"line_start": 2, "line_end": 3, "page_start": None, "page_end": None})
        serialized = json.dumps(patches, ensure_ascii=False)
        self.assertNotIn("DO_NOT_LEAK_SOURCE_TEXT", serialized)
        self.assertNotIn("DO_NOT_LEAK_RULE_REASON", serialized)
        self.assertNotIn("before_text_sha256", patch)
        self.assertNotIn("after_text_sha256", patch)

    def test_sanitizes_private_rule_source_paths(self) -> None:
        patches = build_cleaning_patches(
            before_blocks=[{"block_id": "b1", "status": "keep", "text": "body"}],
            after_blocks=[{
                "block_id": "b1",
                "status": "discard",
                "text": "body",
                "cleaning_rule_id": "rule.private",
                "cleaning_rule_source": r"C:\Users\Example\.kbprep\rules\accepted.jsonl",
            }],
            policy_snapshot_hash="policy-1",
        )

        patch = patches[0]
        self.assertEqual(patch["rule_source"], "private_rules")
        self.assertEqual(patch["after"]["cleaning_rule_source"], "private_rules")
        serialized = json.dumps(patch, ensure_ascii=False)
        self.assertNotIn("C:", serialized)
        self.assertNotIn("Users", serialized)
        self.assertNotIn("accepted.jsonl", serialized)

    def test_builds_derived_block_patch_for_split_promotional_lines(self) -> None:
        patches = build_cleaning_patches(
            before_blocks=[{
                "block_id": "b1",
                "status": "keep",
                "type": "paragraph",
                "text": "正文\n扫码入群",
            }],
            after_blocks=[
                {
                    "block_id": "b1",
                    "status": "keep",
                    "type": "paragraph",
                    "text": "正文",
                    "risk_tags": ["promo_line_removed"],
                },
                {
                    "block_id": "b1_promo_001",
                    "status": "discard",
                    "type": "marketing_cta",
                    "text": "扫码入群",
                    "cleaning_rule_id": "rule.cta",
                    "cleaning_rule_source": "rules/base/obvious_noise.json",
                },
            ],
            policy_snapshot_hash="policy-1",
        )

        change_types = [patch["change_type"] for patch in patches]
        self.assertIn("content_update", change_types)
        self.assertIn("derived_block", change_types)
        derived = next(patch for patch in patches if patch["change_type"] == "derived_block")
        self.assertEqual(derived["block_id"], "b1_promo_001")
        self.assertEqual(derived["parent_block_id"], "b1")
        self.assertEqual(derived["after"]["status"], "discard")

    def test_write_cleaning_patches_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cleaning_patches.jsonl"
            patches = build_cleaning_patches(
                before_blocks=[{"block_id": "b1", "status": "keep", "text": "before"}],
                after_blocks=[{"block_id": "b1", "status": "review", "text": "before"}],
                policy_snapshot_hash="policy-1",
            )
            write_cleaning_patches(path, patches)

            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["block_id"], "b1")

    def test_validate_cleaning_patches_artifact_rejects_old_or_leaky_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cleaning_patches.jsonl"
            path.write_text(
                json.dumps({
                    "schema": "old",
                    "rule_source": "C:/Users/Example/.kbprep/rules/accepted.jsonl",
                    "before_text_sha256": "x",
                }),
                encoding="utf-8",
            )

            self.assertFalse(validate_cleaning_patches_artifact(path))

            patches = build_cleaning_patches(
                before_blocks=[{"block_id": "b1", "status": "keep", "text": "before"}],
                after_blocks=[{"block_id": "b1", "status": "review", "text": "before"}],
                policy_snapshot_hash="policy-1",
            )
            write_cleaning_patches(path, patches)

            self.assertTrue(validate_cleaning_patches_artifact(path))


if __name__ == "__main__":
    unittest.main()
