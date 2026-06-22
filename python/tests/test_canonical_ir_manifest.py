import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.quality.conversion_gate import run_pre_clean_conversion_gate
from kbprep_worker.stages import pipeline_core


def _capture_envelope(fn, payload):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fn(payload)
    except EnvelopeExit as exc:
        return exc.code, json.loads(out.getvalue())
    raise AssertionError("worker command did not write a JSON envelope")


class CanonicalIrManifestTests(unittest.TestCase):
    def test_prepare_writes_canonical_ir_and_document_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            source.write_text("# 操作教程\n\n步骤1：设置 threshold=0.8 并记录结果。\n", encoding="utf-8")

            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(root / "out"), "force": True, "profile": "standard"},
            )

            self.assertEqual(code, 0)
            run_dir = Path(envelope["data"]["run_dir"])
            canonical_manifest_path = run_dir / "canonical_ir" / "manifest.json"
            document_manifest_path = run_dir / "document_manifest.json"
            quality_report_path = run_dir / "conversion_quality_report.json"

            self.assertTrue(canonical_manifest_path.exists())
            self.assertTrue(document_manifest_path.exists())

            canonical_manifest = json.loads(canonical_manifest_path.read_text(encoding="utf-8"))
            typed_nodes_path = run_dir / "canonical_ir" / "typed_nodes.json"
            self.assertEqual(canonical_manifest["schema"], "kbprep.canonical_ir_manifest.v1")
            self.assertEqual(canonical_manifest["status"], "partial")
            self.assertEqual(canonical_manifest["source_snapshot"]["input_name"], source.name)
            self.assertEqual(canonical_manifest["source_snapshot"]["input_size"], source.stat().st_size)
            self.assertEqual(canonical_manifest["conversion"]["actual_route"], "direct_text")
            self.assertTrue(canonical_manifest["coverage"]["typed_nodes_available"])
            self.assertTrue(canonical_manifest["coverage"]["source_spans_available"])
            self.assertEqual(canonical_manifest["artifacts"]["typed_nodes"], "canonical_ir/typed_nodes.json")
            self.assertEqual(canonical_manifest["artifacts"]["source_spans"], "canonical_ir/source_spans.json")
            self.assertTrue(typed_nodes_path.exists())
            self.assertTrue((run_dir / "canonical_ir" / "source_spans.json").exists())
            typed_nodes = json.loads(typed_nodes_path.read_text(encoding="utf-8"))
            self.assertEqual(typed_nodes["schema"], "kbprep.canonical_ir_typed_nodes.v1")
            self.assertEqual(typed_nodes["source_artifact"], "converted.md")
            self.assertEqual(typed_nodes["document_id"], canonical_manifest["document_id"])

            document_manifest = json.loads(document_manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(document_manifest["schema"], "kbprep.document_manifest.v1")
            self.assertEqual(document_manifest["canonical_ir_manifest"], "canonical_ir/manifest.json")
            self.assertEqual(document_manifest["converted_md"], "converted.md")

            conversion_quality_report = json.loads(quality_report_path.read_text(encoding="utf-8"))
            self.assertEqual(conversion_quality_report["status"], "pass")
            self.assertEqual(conversion_quality_report["canonical_ir_manifest"], str(canonical_manifest_path))
            self.assertEqual(conversion_quality_report["document_manifest"], str(document_manifest_path))

    def test_conversion_gate_fails_when_canonical_ir_manifest_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# 教程\n\n步骤1：记录 threshold=0.8。\n", encoding="utf-8")
            (run_dir / "conversion_report.json").write_text(
                json.dumps({
                    "converter": "direct_text",
                    "converted_md": str(converted),
                    "converted_bytes": converted.stat().st_size,
                }),
                encoding="utf-8",
            )

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertTrue(
            any(error.startswith("E_CANONICAL_IR_MANIFEST_MISSING") for error in report["strict_errors"]),
        )
        self.assertTrue(
            any(issue["code"] == "E_CANONICAL_IR_MANIFEST_MISSING" for issue in report["quality_issues"]),
        )

    def test_conversion_gate_fails_when_canonical_ir_manifest_schema_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# 教程\n\n步骤1：记录 threshold=0.8。\n", encoding="utf-8")
            conversion_report = run_dir / "conversion_report.json"
            conversion_report.write_text(
                json.dumps({
                    "converter": "direct_text",
                    "converted_md": str(converted),
                    "converted_bytes": converted.stat().st_size,
                }),
                encoding="utf-8",
            )
            canonical_manifest = run_dir / "canonical_ir" / "manifest.json"
            canonical_manifest.parent.mkdir(parents=True)
            canonical_manifest.write_text(
                json.dumps({"schema": "wrong.schema", "status": "partial"}),
                encoding="utf-8",
            )
            (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")
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

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertTrue(
            any(error.startswith("E_CANONICAL_IR_MANIFEST_INVALID") for error in report["strict_errors"]),
        )

    def test_conversion_gate_fails_when_document_manifest_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# 教程\n\n步骤1：记录 threshold=0.8。\n", encoding="utf-8")
            (run_dir / "conversion_report.json").write_text(
                json.dumps({
                    "converter": "direct_text",
                    "converted_md": str(converted),
                    "converted_bytes": converted.stat().st_size,
                }),
                encoding="utf-8",
            )
            (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")
            canonical_manifest = run_dir / "canonical_ir" / "manifest.json"
            canonical_manifest.parent.mkdir(parents=True)
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

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocked_stage"], "cleanup")
        self.assertEqual(report["canonical_ir_status"], "missing_or_invalid")
        self.assertTrue(any(error.startswith("E_DOCUMENT_MANIFEST_MISSING") for error in report["strict_errors"]))

    def test_conversion_gate_fails_when_document_manifest_reference_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# 教程\n\n步骤1：记录 threshold=0.8。\n", encoding="utf-8")
            (run_dir / "conversion_report.json").write_text(
                json.dumps({
                    "converter": "direct_text",
                    "converted_md": str(converted),
                    "converted_bytes": converted.stat().st_size,
                }),
                encoding="utf-8",
            )
            (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")
            canonical_manifest = run_dir / "canonical_ir" / "manifest.json"
            canonical_manifest.parent.mkdir(parents=True)
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
                    "conversion_report": "../conversion_report.json",
                    "converted_md": "converted.md",
                    "created_from_run": "run_test",
                }),
                encoding="utf-8",
            )

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["canonical_ir_status"], "missing_or_invalid")
        self.assertTrue(any(error.startswith("E_DOCUMENT_MANIFEST_INVALID") for error in report["strict_errors"]))


if __name__ == "__main__":
    unittest.main()
