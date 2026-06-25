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
from kbprep_worker.feedback import promotion_history, proposals
from kbprep_worker.rule_loader import load_active_accepted_rules
from kbprep_worker.rule_schema import ALLOWED_RULE_LIFECYCLE_STATUSES, validate_rule_proposal


def _base_proposal() -> dict[str, Any]:
    return {
        "schema": "kbprep.rule_proposal.v1",
        "id": "proposal-lifecycle",
        "status": "proposed",
        "lifecycle_status": "proposed",
        "lifecycle_history": ["proposed"],
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


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class FeedbackPromotionLifecycleTests(unittest.TestCase):
    def test_rule_proposal_schema_accepts_compatible_lifecycle_states(self) -> None:
        self.assertEqual(
            ALLOWED_RULE_LIFECYCLE_STATUSES,
            {
                "proposed",
                "accepted",
                "rejected",
                "rerun_pending",
                "rerun_passed",
                "rerun_failed",
                "promotion_blocked",
            },
        )
        valid = [
            ("proposed", "pending", "proposed"),
            ("accepted", "confirmed", "accepted"),
            ("accepted", "confirmed", "rerun_pending"),
            ("accepted", "confirmed", "rerun_passed"),
            ("accepted", "confirmed", "rerun_failed"),
            ("rejected", "rejected", "rejected"),
        ]
        for status, owner_status, lifecycle_status in valid:
            with self.subTest(status=status, lifecycle_status=lifecycle_status):
                proposal = {
                    **_base_proposal(),
                    "status": status,
                    "owner_confirmation_status": owner_status,
                    "lifecycle_status": lifecycle_status,
                    "lifecycle_history": [lifecycle_status],
                }
                validate_rule_proposal(proposal, "lifecycle")

        with self.assertRaises(ValueError):
            validate_rule_proposal({**_base_proposal(), "lifecycle_status": "auto_promoted"}, "lifecycle")
        with self.assertRaises(ValueError):
            validate_rule_proposal(
                {
                    **_base_proposal(),
                    "status": "accepted",
                    "owner_confirmation_status": "confirmed",
                    "lifecycle_status": "rejected",
                    "lifecycle_history": ["rejected"],
                },
                "lifecycle",
            )
        with self.assertRaises(ValueError):
            validate_rule_proposal(
                {
                    **_base_proposal(),
                    "status": "accepted",
                    "owner_confirmation_status": "confirmed",
                    "lifecycle_status": "rerun_passed",
                    "lifecycle_history": ["accepted", "rerun_pending"],
                },
                "lifecycle",
            )

    def test_accept_proposal_records_rerun_passed_without_breaking_active_rule_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp)
            proposed_path = rules_dir / "proposed_rules.jsonl"
            proposed_path.write_text(json.dumps(_base_proposal(), ensure_ascii=False) + "\n", encoding="utf-8")

            with patch("kbprep_worker.feedback.proposals._rerun_after_accept", return_value={"ok": True, "status": "passed"}):
                code, envelope = _capture_envelope(
                    proposals._accept_proposal,
                    {
                        "rules_dir": str(rules_dir),
                        "accept_proposal": "latest",
                        "confirm_rule_acceptance": True,
                        "rerun_after_accept": True,
                    },
                )

            accepted = envelope["data"]["accepted"]
            accepted_path = rules_dir / "accepted_rules.jsonl"
            rows = _jsonl(accepted_path)
            self.assertEqual(code, 0)
            self.assertEqual(accepted["status"], "accepted")
            self.assertEqual(accepted["lifecycle_status"], "rerun_passed")
            self.assertEqual(rows[0]["lifecycle_history"], ["accepted", "rerun_pending", "rerun_passed"])
            self.assertEqual(len(load_active_accepted_rules(accepted_path, document_type="", source_identity="")), 1)

    def test_accept_proposal_records_rerun_failed_without_changing_status_contract(self) -> None:
        proposal = {**_base_proposal(), "id": "proposal-rerun-failed"}
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp)
            proposed_path = rules_dir / "proposed_rules.jsonl"
            proposed_path.write_text(json.dumps(proposal, ensure_ascii=False) + "\n", encoding="utf-8")

            with patch("kbprep_worker.feedback.proposals._rerun_after_accept", return_value={"ok": False, "status": "failed"}):
                code, envelope = _capture_envelope(
                    proposals._accept_proposal,
                    {
                        "rules_dir": str(rules_dir),
                        "accept_proposal": "latest",
                        "confirm_rule_acceptance": True,
                        "rerun_after_accept": True,
                    },
                )

            accepted = envelope["data"]["accepted"]
            rows = _jsonl(rules_dir / "accepted_rules.jsonl")
            self.assertEqual(code, 0)
            self.assertEqual(accepted["status"], "accepted")
            self.assertEqual(accepted["lifecycle_status"], "rerun_failed")
            self.assertEqual(rows[0]["lifecycle_status"], "rerun_failed")

    def test_accept_proposal_keeps_unavailable_rerun_pending(self) -> None:
        proposal = {**_base_proposal(), "id": "proposal-rerun-unavailable"}
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp)
            proposed_path = rules_dir / "proposed_rules.jsonl"
            proposed_path.write_text(json.dumps(proposal, ensure_ascii=False) + "\n", encoding="utf-8")

            with patch(
                "kbprep_worker.feedback.proposals._rerun_after_accept",
                return_value={"status": "unavailable", "reason": "missing metadata"},
            ):
                code, envelope = _capture_envelope(
                    proposals._accept_proposal,
                    {
                        "rules_dir": str(rules_dir),
                        "accept_proposal": "latest",
                        "confirm_rule_acceptance": True,
                        "rerun_after_accept": True,
                    },
                )

            accepted = envelope["data"]["accepted"]
            rows = _jsonl(rules_dir / "accepted_rules.jsonl")
            self.assertEqual(code, 0)
            self.assertEqual(accepted["lifecycle_status"], "rerun_pending")
            self.assertEqual(rows[0]["lifecycle_history"], ["accepted", "rerun_pending"])

    def test_reject_proposal_records_rejected_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp)
            proposed_path = rules_dir / "proposed_rules.jsonl"
            proposed_path.write_text(json.dumps(_base_proposal(), ensure_ascii=False) + "\n", encoding="utf-8")

            code, envelope = _capture_envelope(
                proposals._reject_proposal,
                {"rules_dir": str(rules_dir), "reject_proposal": "latest", "reject_reason": "too broad"},
            )

            rejected = envelope["data"]["rejected"]
            self.assertEqual(code, 0)
            self.assertEqual(rejected["status"], "rejected")
            self.assertEqual(rejected["lifecycle_status"], "rejected")
            self.assertEqual(_jsonl(rules_dir / "rejected_rules.jsonl")[0]["lifecycle_history"], ["rejected"])

    def test_failed_promotion_history_reports_promotion_blocked_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target_rules_dir = Path(tmp)
            history_path = target_rules_dir / "promotion_history.jsonl"
            history_path.write_text(
                json.dumps({
                    "schema": "kbprep.dictionary_promotion_history.v1",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "document_type": "course",
                    "regression_verification": {"status": "failed", "reason": "strict errors"},
                }, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )

            risk = promotion_history._promotion_history_risk(target_rules_dir=target_rules_dir, document_type="course")

            self.assertEqual(risk["status"], "blocked")
            self.assertEqual(risk["lifecycle_status"], "promotion_blocked")


if __name__ == "__main__":
    unittest.main()
