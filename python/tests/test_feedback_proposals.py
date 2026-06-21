import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.feedback import proposals
from kbprep_worker.feedback.support import _matches_pattern
from kbprep_worker.rule_schema import validate_rule_proposal


def _base_proposal() -> dict[str, Any]:
    return {
        "schema": "kbprep.rule_proposal.v1",
        "id": "proposal-old",
        "status": "proposed",
        "action": "discard",
        "scope": "user",
        "match": "literal",
        "pattern": "扫码入群领取资料",
        "examples": ["扫码入群领取资料"],
        "counterexamples": ["正文案例：扫码动作是渠道字段"],
        "reason": "test",
        "risk_note": "May delete legitimate course discussion if the scope is too broad.",
        "owner_confirmation_status": "pending",
        "requires_confirmation": True,
        "created_from_run": "run",
    }


def _capture_envelope(fn: Callable[[dict[str, Any]], None], payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fn(payload)
    except EnvelopeExit as exc:
        return exc.code, json.loads(out.getvalue())
    raise AssertionError("expected JSON envelope")


class FeedbackProposalNarrowingTests(unittest.TestCase):
    def test_broad_literal_proposal_can_narrow_to_anchored_regex(self) -> None:
        proposal = {
            **_base_proposal(),
            "pattern": "扫码入群",
            "examples": ["扫码入群领取资料", "扫码入群领取资料，添加助教"],
            "counterexamples": ["正文案例：扫码入群领取资料是渠道字段"],
        }
        validation = proposals._validate_proposal_acceptance(proposal)

        narrowed = proposals._suggest_narrowed_proposal(proposal, validation)

        self.assertIsNotNone(narrowed)
        assert narrowed is not None
        self.assertEqual(narrowed["match"], "regex")
        self.assertEqual(narrowed["narrowed_from_pattern"], "扫码入群")
        self.assertTrue(_matches_pattern("扫码入群领取资料", narrowed["pattern"], "regex"))
        self.assertFalse(_matches_pattern("正文案例：扫码入群领取资料是渠道字段", narrowed["pattern"], "regex"))

    def test_rule_proposal_schema_requires_evidence_risk_and_confirmation_status(self) -> None:
        for key in ("examples", "counterexamples", "risk_note", "owner_confirmation_status"):
            with self.subTest(key=key):
                proposal = _base_proposal()
                proposal.pop(key)
                with self.assertRaises(ValueError):
                    validate_rule_proposal(proposal, "feedback")

        proposal = {**_base_proposal(), "owner_confirmation_status": "auto_accepted"}
        with self.assertRaises(ValueError):
            validate_rule_proposal(proposal, "feedback")

    def test_accept_proposal_requires_explicit_owner_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp)
            proposed_path = rules_dir / "proposed_rules.jsonl"
            proposed_path.write_text(json.dumps(_base_proposal(), ensure_ascii=False) + "\n", encoding="utf-8")

            code, envelope = _capture_envelope(
                proposals._accept_proposal,
                {"rules_dir": str(rules_dir), "accept_proposal": "latest"},
            )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_CONFIRMATION_REQUIRED")
            self.assertFalse((rules_dir / "accepted_rules.jsonl").exists())

            with patch("kbprep_worker.feedback.proposals._rerun_after_accept", return_value={"status": "skipped"}):
                code, accepted = _capture_envelope(
                    proposals._accept_proposal,
                    {
                        "rules_dir": str(rules_dir),
                        "accept_proposal": "latest",
                        "confirm_rule_acceptance": True,
                    },
                )
            self.assertEqual(code, 0)
            self.assertEqual(accepted["data"]["accepted"]["owner_confirmation_status"], "confirmed")

    def test_accept_proposal_rejects_manual_counterexample_placeholder(self) -> None:
        proposal = {
            **_base_proposal(),
            "counterexamples": ["Manual counterexample required before accepting this proposal."],
        }
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp)
            proposed_path = rules_dir / "proposed_rules.jsonl"
            proposed_path.write_text(json.dumps(proposal, ensure_ascii=False) + "\n", encoding="utf-8")

            code, envelope = _capture_envelope(
                proposals._accept_proposal,
                {
                    "rules_dir": str(rules_dir),
                    "accept_proposal": "latest",
                    "confirm_rule_acceptance": True,
                },
            )

        self.assertEqual(code, 1)
        self.assertEqual(envelope["error"]["code"], "E_RULE_VALIDATION_FAILED")
        self.assertEqual(envelope["error"]["details"]["missing_counterexamples"], proposal["counterexamples"])

    def test_discard_counterexamples_include_review_needed_and_quality_issue_body_matches(self) -> None:
        artifacts = {
            "texts": {
                "cleaned": "",
                "review_needed": "案例：字段值为关注公众号时表示渠道来源，应作为样本值保留。",
                "discarded": "关注公众号领取资料。",
            },
            "quality": {
                "quality_issues": [
                    {"message": "案例：表格字段关注公众号是渠道取值，不是营销 CTA。"},
                ],
            },
        }

        counterexamples = proposals._counterexamples(
            {},
            "关注公众号",
            "literal",
            "discard",
            artifacts,
        )

        self.assertIn("案例：字段值为关注公众号时表示渠道来源，应作为样本值保留。", counterexamples)
        self.assertIn("案例：表格字段关注公众号是渠道取值，不是营销 CTA。", counterexamples)


if __name__ == "__main__":
    unittest.main()
