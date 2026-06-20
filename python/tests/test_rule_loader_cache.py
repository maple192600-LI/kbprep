import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.rule_loader import load_cleaning_rules


class RuleLoaderCacheTests(unittest.TestCase):
    def setUp(self):
        load_cleaning_rules.cache_clear()

    def tearDown(self):
        load_cleaning_rules.cache_clear()

    def test_accepted_rules_are_parsed_once_until_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp)
            (rules_dir / "accepted_rules.jsonl").write_text(
                json.dumps(
                    {
                        "schema": "kbprep.rule_proposal.v1",
                        "id": "proposal-1",
                        "accepted_rule_id": "accepted-1",
                        "status": "accepted",
                        "action": "discard",
                        "scope": "global",
                        "match": "literal",
                        "pattern": "subscribe now",
                        "reason": "CTA",
                        "risk_note": "Fixture accepted rule only targets subscription CTA text.",
                        "created_from_run": "run-1",
                        "owner_confirmation_status": "confirmed",
                        "requires_confirmation": True,
                        "examples": ["subscribe now"],
                        "counterexamples": ["body paragraph"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            old_env = os.environ.get("KBPREP_USER_RULES_DIR")
            os.environ["KBPREP_USER_RULES_DIR"] = str(rules_dir)
            try:
                with patch("kbprep_worker.rule_loader.validate_rule_proposal") as validate:
                    from kbprep_worker.rule_schema import validate_rule_proposal as real_validate

                    validate.side_effect = real_validate
                    load_cleaning_rules(source_identity="")
                    load_cleaning_rules(source_identity="")
                    self.assertEqual(validate.call_count, 1)
            finally:
                if old_env is None:
                    os.environ.pop("KBPREP_USER_RULES_DIR", None)
                else:
                    os.environ["KBPREP_USER_RULES_DIR"] = old_env


if __name__ == "__main__":
    unittest.main()
