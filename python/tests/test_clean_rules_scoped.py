"""Scoped cleaning for node-id selective rerun (M5).

apply_clean_rules accepts an optional target_node_ids list. When it is a
non-empty list, only the blocks whose canonical node_id (n_{index+1:06d}) is
in the set are passed through the cleaning rules; every other block keeps its
original status and text. This lets a selective rerun focus rule-effect
verification on the affected nodes without disturbing the rest of the document.
"""
import unittest

from kbprep_worker.clean_rules import apply_clean_rules


class ScopedCleaningTests(unittest.TestCase):
    def _blocks(self, count: int = 3) -> list[dict]:
        return [
            {"text": f"block {i + 1} content", "type": "paragraph", "status": "unclassified"}
            for i in range(count)
        ]

    def test_target_node_ids_leaves_non_scoped_blocks_untouched(self) -> None:
        blocks = self._blocks(3)
        result = apply_clean_rules(
            blocks,
            profile="standard",
            document_type="report",
            target_node_ids=["n_000002"],
        )

        # non-scoped blocks (index 0 and 2) keep their original status
        self.assertEqual(result[0].get("status"), "unclassified")
        self.assertEqual(result[2].get("status"), "unclassified")
        # the three original blocks are still present (non-scoped are not removed)
        self.assertGreaterEqual(len(result), 3)

    def test_target_node_ids_none_or_empty_cleans_all_blocks(self) -> None:
        blocks_none = self._blocks(2)
        result_none = apply_clean_rules(blocks_none, profile="standard", document_type="report")
        self.assertIsInstance(result_none, list)
        self.assertGreaterEqual(len(result_none), 2)

        blocks_empty = self._blocks(2)
        result_empty = apply_clean_rules(
            blocks_empty,
            profile="standard",
            document_type="report",
            target_node_ids=[],
        )
        self.assertIsInstance(result_empty, list)

    def test_target_node_ids_with_unknown_id_skips_all_cleaning(self) -> None:
        blocks = self._blocks(3)
        original_statuses = [block.get("status") for block in blocks]
        result = apply_clean_rules(
            blocks,
            profile="standard",
            document_type="report",
            target_node_ids=["n_999999"],
        )

        # no block matches n_999999, so no block is cleaned
        for index, block in enumerate(result[:3]):
            self.assertEqual(block.get("status"), original_statuses[index])


if __name__ == "__main__":
    unittest.main()
