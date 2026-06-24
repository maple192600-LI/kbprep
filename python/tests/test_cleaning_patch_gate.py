import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.cleaning_patch_gate import apply_patch_quality_gate, validate_cleaning_patch_gate_artifact
from kbprep_worker.cleaning_patches import build_cleaning_patches


def _policy(*rule_ids: str) -> dict:
    return {"active_rule_ids": list(rule_ids)}


class CleaningPatchGateTests(unittest.TestCase):
    def test_rejects_missing_target_block(self) -> None:
        patches = [{
            "schema": "kbprep.cleaning_patch.v1",
            "patch_id": "p1",
            "change_type": "status_update",
            "block_id": "missing",
            "policy_snapshot_hash": "policy-1",
            "rule_id": "rule.cta",
            "before": {"status": "keep"},
            "after": {"status": "discard", "cleaning_rule_id": "rule.cta"},
            "text_changed": False,
            "location": {"line_start": 1},
        }]

        result = apply_patch_quality_gate([], [], patches, _policy("rule.cta"))

        self.assertEqual(len(result.accepted_patches), 0)
        self.assertEqual(result.rejected_patches[0]["reason_code"], "missing_target_node")

    def test_rejects_rule_not_in_policy_snapshot(self) -> None:
        before = [{"block_id": "b1", "status": "keep", "type": "paragraph", "text": "扫码入群"}]
        after = [{
            "block_id": "b1",
            "status": "discard",
            "type": "marketing_cta",
            "text": "扫码入群",
            "cleaning_rule_id": "rule.unknown",
        }]
        patches = build_cleaning_patches(before, after, "policy-1")

        result = apply_patch_quality_gate(before, after, patches, _policy("rule.cta"))

        self.assertEqual(result.gated_blocks[0]["status"], "keep")
        self.assertEqual(result.rejected_patches[0]["reason_code"], "rule_not_in_policy_snapshot")

    def test_rejects_protected_content_change_and_restores_original_block(self) -> None:
        before = [{
            "block_id": "code1",
            "status": "keep",
            "type": "code",
            "protected": True,
            "text": "print('threshold=0.8')",
        }]
        after = [{
            "block_id": "code1",
            "status": "discard",
            "type": "marketing_cta",
            "protected": True,
            "text": "print('threshold=0.8')",
            "cleaning_rule_id": "rule.cta",
        }]
        patches = build_cleaning_patches(before, after, "policy-1")

        result = apply_patch_quality_gate(before, after, patches, _policy("rule.cta"))

        self.assertEqual(result.gated_blocks[0]["status"], "keep")
        self.assertEqual(result.gated_blocks[0]["type"], "code")
        self.assertEqual(result.rejected_patches[0]["reason_code"], "protected_structure_change")

    def test_rejects_derived_patch_from_protected_parent(self) -> None:
        before = [{
            "block_id": "code1",
            "status": "keep",
            "type": "code",
            "protected": True,
            "text": "threshold=0.8\n扫码入群",
        }]
        after = [
            {
                "block_id": "code1",
                "status": "keep",
                "type": "code",
                "protected": True,
                "text": "threshold=0.8",
                "risk_tags": ["promo_line_removed"],
            },
            {
                "block_id": "code1_promo_001",
                "status": "discard",
                "type": "marketing_cta",
                "text": "扫码入群",
                "cleaning_rule_id": "rule.cta",
            },
        ]
        patches = build_cleaning_patches(before, after, "policy-1")

        result = apply_patch_quality_gate(before, after, patches, _policy("rule.cta"))

        self.assertEqual([block["block_id"] for block in result.gated_blocks], ["code1"])
        self.assertEqual(result.gated_blocks[0]["text"], "threshold=0.8\n扫码入群")
        self.assertEqual(result.summary["accepted_patch_count"], 0)
        self.assertEqual(result.summary["rejected_reason_counts"]["protected_structure_change"], 2)

    def test_rejects_ruleless_review_status_on_protected_block(self) -> None:
        before = [{
            "block_id": "code1",
            "status": "keep",
            "type": "code",
            "protected": True,
            "text": "threshold=0.8",
        }]
        after = [{
            "block_id": "code1",
            "status": "review",
            "type": "code",
            "protected": True,
            "text": "threshold=0.8",
            "risk_tags": ["possible_cta"],
        }]
        patches = build_cleaning_patches(before, after, "policy-1")

        result = apply_patch_quality_gate(before, after, patches, _policy())

        self.assertEqual(result.gated_blocks[0]["status"], "keep")
        self.assertEqual(result.rejected_patches[0]["reason_code"], "protected_structure_change")

    def test_rejects_keep_status_type_change_on_protected_block(self) -> None:
        before = [{
            "block_id": "code1",
            "status": "keep",
            "type": "code",
            "protected": True,
            "text": "threshold=0.8",
        }]
        after = [{
            "block_id": "code1",
            "status": "keep",
            "type": "marketing_cta",
            "protected": True,
            "text": "threshold=0.8",
            "cleaning_rule_id": "rule.cta",
        }]
        patches = build_cleaning_patches(before, after, "policy-1")

        result = apply_patch_quality_gate(before, after, patches, _policy("rule.cta"))

        self.assertEqual(result.gated_blocks[0]["type"], "code")
        self.assertEqual(result.rejected_patches[0]["reason_code"], "protected_structure_change")

    def test_rejects_keep_status_protected_flag_removal(self) -> None:
        before = [{
            "block_id": "code1",
            "status": "keep",
            "type": "code",
            "protected": True,
            "text": "threshold=0.8",
        }]
        after = [{
            "block_id": "code1",
            "status": "keep",
            "type": "code",
            "protected": False,
            "text": "threshold=0.8",
            "cleaning_rule_id": "rule.cta",
        }]
        patches = build_cleaning_patches(before, after, "policy-1")

        result = apply_patch_quality_gate(before, after, patches, _policy("rule.cta"))

        self.assertTrue(result.gated_blocks[0]["protected"])
        self.assertEqual(result.rejected_patches[0]["reason_code"], "protected_structure_change")

    def test_rejects_whole_section_heading_deletion(self) -> None:
        before = [{"block_id": "h1", "status": "keep", "type": "section_heading", "text": "课程大纲"}]
        after = [{
            "block_id": "h1",
            "status": "discard",
            "type": "marketing_cta",
            "text": "课程大纲",
            "cleaning_rule_id": "rule.cta",
        }]
        patches = build_cleaning_patches(before, after, "policy-1")

        result = apply_patch_quality_gate(before, after, patches, _policy("rule.cta"))

        self.assertEqual(result.gated_blocks[0]["status"], "keep")
        self.assertEqual(result.rejected_patches[0]["reason_code"], "whole_section_deletion")

    def test_accepts_safe_rule_backed_cta_discard(self) -> None:
        before = [{"block_id": "b1", "status": "keep", "type": "paragraph", "text": "扫码入群"}]
        after = [{
            "block_id": "b1",
            "status": "discard",
            "type": "marketing_cta",
            "text": "扫码入群",
            "cleaning_rule_id": "rule.cta",
        }]
        patches = build_cleaning_patches(before, after, "policy-1")

        result = apply_patch_quality_gate(before, after, patches, _policy("rule.cta"))

        self.assertEqual(len(result.rejected_patches), 0)
        self.assertEqual(result.gated_blocks[0]["status"], "discard")
        self.assertEqual(result.summary["accepted_patch_count"], 1)

    def test_accepts_parent_content_update_when_rule_backed_derived_block_exists(self) -> None:
        before = [{"block_id": "b1", "status": "keep", "type": "paragraph", "text": "正文\n扫码入群"}]
        after = [
            {"block_id": "b1", "status": "keep", "type": "paragraph", "text": "正文", "risk_tags": ["promo_line_removed"]},
            {
                "block_id": "b1_promo_001",
                "status": "discard",
                "type": "marketing_cta",
                "text": "扫码入群",
                "cleaning_rule_id": "rule.cta",
            },
        ]
        patches = build_cleaning_patches(before, after, "policy-1")

        result = apply_patch_quality_gate(before, after, patches, _policy("rule.cta"))

        self.assertEqual(len(result.rejected_patches), 0)
        self.assertEqual([block["block_id"] for block in result.gated_blocks], ["b1", "b1_promo_001"])

    def test_rejected_patch_metadata_does_not_copy_source_text(self) -> None:
        before = [{"block_id": "b1", "status": "keep", "type": "paragraph", "text": "DO_NOT_LEAK"}]
        after = [{"block_id": "b1", "status": "discard", "type": "marketing_cta", "text": "DO_NOT_LEAK"}]
        patches = build_cleaning_patches(before, after, "policy-1")

        result = apply_patch_quality_gate(before, after, patches, _policy("rule.cta"))

        self.assertNotIn("DO_NOT_LEAK", json.dumps(result.rejected_patches, ensure_ascii=False))

    def test_validate_cleaning_patch_gate_artifact_rejects_old_or_invalid_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cleaning_patch_gate.json"
            path.write_text(json.dumps({"schema": "old"}), encoding="utf-8")

            self.assertFalse(validate_cleaning_patch_gate_artifact(path))

            path.write_text(
                json.dumps({
                    "schema": "kbprep.cleaning_patch_gate.v1",
                    "accepted_patch_count": 1,
                    "rejected_patch_count": 0,
                    "rejected_reason_counts": {},
                    "source_text": "DO_NOT_LEAK",
                }),
                encoding="utf-8",
            )

            self.assertFalse(validate_cleaning_patch_gate_artifact(path))

            path.write_text(
                json.dumps({
                    "schema": "kbprep.cleaning_patch_gate.v1",
                    "accepted_patch_count": 1,
                    "rejected_patch_count": 0,
                    "rejected_reason_counts": {},
                }),
                encoding="utf-8",
            )

            self.assertTrue(validate_cleaning_patch_gate_artifact(path))


if __name__ == "__main__":
    unittest.main()
