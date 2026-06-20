import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.canonical_ir import validate_canonical_ir_manifests, write_canonical_ir_manifests


class CanonicalIrSchemaTests(unittest.TestCase):
    def test_writer_outputs_manifest_that_passes_shared_validator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("# Note\n\nA useful note.\n", encoding="utf-8")
            run_dir = root / "run"
            run_dir.mkdir()
            converted = run_dir / "converted.md"
            converted.write_text("# Note\n\nA useful note.\n", encoding="utf-8")
            (run_dir / "conversion_report.json").write_text(
                json.dumps({
                    "converter": "direct_text",
                    "converted_md": str(converted),
                    "route_decision": {"actual_route": "direct_text"},
                }),
                encoding="utf-8",
            )
            (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")

            paths = write_canonical_ir_manifests(
                run_dir=run_dir,
                input_path=source,
                source_type="markdown_note",
                file_hash="a" * 64,
                file_size=source.stat().st_size,
                run_id="run_test",
            )

            canonical_manifest = json.loads(paths["canonical_ir_manifest"].read_text(encoding="utf-8"))
            document_manifest = json.loads(paths["document_manifest"].read_text(encoding="utf-8"))
            self.assertEqual(canonical_manifest["artifacts"]["converted_md"], "converted.md")
            self.assertEqual(canonical_manifest["artifacts"]["conversion_report"], "conversion_report.json")
            self.assertEqual(canonical_manifest["artifacts"]["diagnosis_report"], "diagnosis_report.json")
            self.assertEqual(document_manifest["canonical_ir_manifest"], "canonical_ir/manifest.json")
            self.assertEqual(document_manifest["converted_md"], "converted.md")
            self.assertEqual(validate_canonical_ir_manifests(run_dir, converted_path=converted), [])

    def test_validator_reports_missing_required_canonical_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            canonical_dir = run_dir / "canonical_ir"
            canonical_dir.mkdir()
            (canonical_dir / "manifest.json").write_text(
                json.dumps({"schema": "kbprep.canonical_ir_manifest.v1", "status": "partial"}),
                encoding="utf-8",
            )
            (run_dir / "document_manifest.json").write_text(
                json.dumps({
                    "schema": "kbprep.document_manifest.v1",
                    "canonical_ir_manifest": "canonical_ir/manifest.json",
                    "converted_md": "converted.md",
                    "conversion_report": "conversion_report.json",
                    "created_from_run": "run_test",
                }),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=run_dir / "converted.md")

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_MANIFEST_INVALID" for issue in issues))
        self.assertTrue(any("source_snapshot" in issue.message for issue in issues))

    def test_validator_reports_missing_document_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            (run_dir / "conversion_report.json").write_text("{}", encoding="utf-8")
            (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")
            canonical_dir = run_dir / "canonical_ir"
            canonical_dir.mkdir()
            (canonical_dir / "manifest.json").write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_manifest.v1",
                    "document_id": "doc_test",
                    "source_snapshot": {
                        "input_path": "source.md",
                        "input_name": "source.md",
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

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_DOCUMENT_MANIFEST_MISSING" for issue in issues))
        self.assertTrue(any("document_manifest.json" in issue.message for issue in issues))

    def test_validator_rejects_artifact_paths_that_escape_run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            (run_dir / "conversion_report.json").write_text("{}", encoding="utf-8")
            (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")
            canonical_dir = run_dir / "canonical_ir"
            canonical_dir.mkdir()
            (canonical_dir / "manifest.json").write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_manifest.v1",
                    "document_id": "doc_test",
                    "source_snapshot": {
                        "input_path": "source.md",
                        "input_name": "source.md",
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
                        "converted_md": "../outside.md",
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
                    "converted_md": "converted.md",
                    "conversion_report": "conversion_report.json",
                    "created_from_run": "run_test",
                }),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_MANIFEST_INVALID" for issue in issues))
        self.assertTrue(any("converted_md" in issue.message for issue in issues))

    def test_validator_rejects_document_manifest_paths_that_escape_run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            (run_dir / "conversion_report.json").write_text("{}", encoding="utf-8")
            (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")
            canonical_dir = run_dir / "canonical_ir"
            canonical_dir.mkdir()
            (canonical_dir / "manifest.json").write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_manifest.v1",
                    "document_id": "doc_test",
                    "source_snapshot": {
                        "input_path": "source.md",
                        "input_name": "source.md",
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
                    "canonical_ir_manifest": "../manifest.json",
                    "conversion_report": "conversion_report.json",
                    "converted_md": "converted.md",
                    "created_from_run": "run_test",
                }),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_DOCUMENT_MANIFEST_INVALID" for issue in issues))
        self.assertTrue(any("canonical_ir_manifest" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
