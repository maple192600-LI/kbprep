import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.quality.conversion_gate import run_pre_clean_conversion_gate


def _write_conversion_report(run_dir: Path, converted: Path, **overrides) -> None:
    payload = {
        "converter": "direct_text",
        "converted_md": str(converted),
        "converted_bytes": converted.stat().st_size if converted.exists() else 0,
        "route_decision": {
            "actual_route": "direct_text",
            "selected_route": "direct_text",
        },
    }
    payload.update(overrides)
    (run_dir / "conversion_report.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_valid_manifests(run_dir: Path, converted: Path) -> None:
    canonical_dir = run_dir / "canonical_ir"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")
    canonical_manifest = canonical_dir / "manifest.json"
    canonical_manifest.write_text(
        json.dumps({
            "schema": "kbprep.canonical_ir_manifest.v1",
            "document_id": "doc_test",
            "source_snapshot": {
                "input_path": "input.md",
                "input_name": "input.md",
                "input_sha256": "hash",
                "input_size": 1,
                "source_type": "markdown_note",
            },
            "conversion": {
                "converter": "direct_text",
                "actual_route": "direct_text",
                "route_decision": {},
                "route_decision_hash": "hash",
            },
            "artifacts": {
                "converted_md": "converted.md",
                "conversion_report": "conversion_report.json",
                "diagnosis_report": "diagnosis_report.json",
            },
            "coverage": {
                "typed_nodes_available": False,
                "source_spans_available": False,
                "assets_available": False,
            },
            "status": "partial",
        }),
        encoding="utf-8",
    )
    (run_dir / "document_manifest.json").write_text(
        json.dumps({
            "schema": "kbprep.document_manifest.v1",
            "canonical_ir_manifest": "canonical_ir/manifest.json",
            "conversion_report": "conversion_report.json",
            "converted_md": "converted.md",
            "created_from_run": "run_test",
        }),
        encoding="utf-8",
    )


class ConversionGateTests(unittest.TestCase):
    def test_pre_clean_conversion_gate_fails_garbled_converted_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("鐩綍 閮ㄧ讲 鏂规 " * 80, encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["schema"], "kbprep.conversion_quality_report.v1")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocked_stage"], "cleanup")
        self.assertEqual(report["route_evidence"]["actual_route"], "direct_text")
        self.assertTrue(any(action["code"].startswith("E_CONVERTED_TEXT_") for action in report["failure_actions"]))
        self.assertTrue(any(error.startswith("E_CONVERTED_TEXT_") for error in report["strict_errors"]))
        self.assertTrue(all(issue["gate"] == "pre_clean_conversion" for issue in report["quality_issues"]))

    def test_pre_clean_conversion_gate_passes_readable_converted_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# 教程\n\n步骤1：设置 threshold=0.8 并记录失败原因。\n", encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "pass")
        self.assertIsNone(report["blocked_stage"])
        self.assertEqual(report["failure_actions"], [])
        self.assertEqual(report["strict_errors"], [])

    def test_pre_clean_conversion_gate_fails_when_conversion_report_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# 教程\n\n步骤1：记录 threshold=0.8。\n", encoding="utf-8")
            _write_valid_manifests(run_dir, converted)
            (run_dir / "conversion_report.json").unlink(missing_ok=True)

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocked_stage"], "cleanup")
        self.assertTrue(any(error.startswith("E_CONVERSION_REPORT_MISSING") for error in report["strict_errors"]))
        self.assertTrue(any(action["action"] == "rerun_conversion" for action in report["failure_actions"]))

    def test_pre_clean_conversion_gate_fails_when_conversion_report_is_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# 教程\n\n步骤1：记录 threshold=0.8。\n", encoding="utf-8")
            _write_valid_manifests(run_dir, converted)
            (run_dir / "conversion_report.json").write_text("{bad json", encoding="utf-8")

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocked_stage"], "cleanup")
        self.assertTrue(any(error.startswith("E_CONVERSION_REPORT_INVALID") for error in report["strict_errors"]))
        self.assertTrue(any(issue["code"] == "E_CONVERSION_REPORT_INVALID" for issue in report["quality_issues"]))
        self.assertTrue(any(action["action"] == "rerun_conversion" for action in report["failure_actions"]))

    def test_pre_clean_conversion_gate_fails_when_diagnosis_report_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# 教程\n\n步骤1：记录 threshold=0.8。\n", encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            (run_dir / "diagnosis_report.json").unlink()

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertTrue(any(error.startswith("E_DIAGNOSIS_REPORT_MISSING") for error in report["strict_errors"]))
        self.assertTrue(any(action["action"] == "rerun_diagnosis" for action in report["failure_actions"]))

    def test_pre_clean_conversion_gate_fails_when_diagnosis_report_is_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# 教程\n\n步骤1：记录 threshold=0.8。\n", encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            (run_dir / "diagnosis_report.json").write_text("{bad json", encoding="utf-8")

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertTrue(any(error.startswith("E_DIAGNOSIS_REPORT_INVALID") for error in report["strict_errors"]))
        self.assertTrue(any(issue["code"] == "E_DIAGNOSIS_REPORT_INVALID" for issue in report["quality_issues"]))
        self.assertTrue(any(action["action"] == "rerun_diagnosis" for action in report["failure_actions"]))

    def test_pre_clean_conversion_gate_fails_when_conversion_report_declares_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# 教程\n\n步骤1：记录 threshold=0.8。\n", encoding="utf-8")
            _write_conversion_report(run_dir, converted, status="failed", error_code="E_MINERU_NOT_FOUND")
            _write_valid_manifests(run_dir, converted)

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertTrue(any(error.startswith("E_CONVERT_FAILED") for error in report["strict_errors"]))
        self.assertTrue(any(action["action"] == "fix_conversion_failure" for action in report["failure_actions"]))

    def test_pre_clean_conversion_gate_fails_when_typed_nodes_are_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Tutorial\n\nRecord acceptance criteria.\n", encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            manifest_path = run_dir / "canonical_ir" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"]["typed_nodes"] = "canonical_ir/typed_nodes.json"
            manifest["coverage"]["typed_nodes_available"] = True
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps({"schema": "wrong.schema"}),
                encoding="utf-8",
            )

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocked_stage"], "cleanup")
        self.assertTrue(any(error.startswith("E_CANONICAL_IR_TYPED_NODES_INVALID") for error in report["strict_errors"]))
        self.assertTrue(any(action["action"] == "regenerate_canonical_ir" for action in report["failure_actions"]))


if __name__ == "__main__":
    unittest.main()
