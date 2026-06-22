import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.canonical_ir import validate_canonical_ir_manifests, write_canonical_ir_manifests


def _write_valid_manifest_pair(
    run_dir: Path,
    converted: Path,
    *,
    document_id: str = "doc_test",
    artifacts: dict[str, str] | None = None,
    coverage: dict[str, bool] | None = None,
) -> None:
    canonical_dir = run_dir / "canonical_ir"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "conversion_report.json").write_text("{}", encoding="utf-8")
    (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")
    artifact_payload = {
        "converted_md": "converted.md",
        "conversion_report": "conversion_report.json",
        "diagnosis_report": "diagnosis_report.json",
    }
    artifact_payload.update(artifacts or {})
    coverage_payload = {
        "typed_nodes_available": False,
        "source_spans_available": False,
        "assets_available": False,
    }
    coverage_payload.update(coverage or {})
    (canonical_dir / "manifest.json").write_text(
        json.dumps({
            "schema": "kbprep.canonical_ir_manifest.v1",
            "document_id": document_id,
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
            "artifacts": artifact_payload,
            "coverage": coverage_payload,
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


def _typed_nodes_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "kbprep.canonical_ir_typed_nodes.v1",
        "document_id": "doc_test",
        "source_artifact": "converted.md",
        "node_count": 1,
        "nodes": [{
            "node_id": "n_000001",
            "ordinal": 1,
            "type": "heading",
            "text": "Title",
            "metadata": {"heading_level": 1},
        }],
    }
    payload.update(overrides)
    return payload


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
            self.assertEqual(canonical_manifest["artifacts"]["typed_nodes"], "canonical_ir/typed_nodes.json")
            self.assertTrue(canonical_manifest["coverage"]["typed_nodes_available"])
            typed_nodes = json.loads((run_dir / "canonical_ir" / "typed_nodes.json").read_text(encoding="utf-8"))
            self.assertEqual(typed_nodes["schema"], "kbprep.canonical_ir_typed_nodes.v1")
            self.assertEqual(typed_nodes["source_artifact"], "converted.md")
            self.assertEqual(typed_nodes["document_id"], canonical_manifest["document_id"])
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

    def test_validator_rejects_invalid_typed_nodes_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(schema="wrong.schema")),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_TYPED_NODES_INVALID" for issue in issues))

    def test_validator_allows_legacy_manifest_without_typed_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(run_dir, converted)

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertEqual(issues, [])

    def test_validator_rejects_typed_nodes_available_without_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(run_dir, converted, coverage={"typed_nodes_available": True})

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_MANIFEST_INVALID" for issue in issues))

    def test_validator_rejects_typed_nodes_artifact_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"typed_nodes": "../typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_MANIFEST_INVALID" for issue in issues))

    def test_validator_rejects_typed_nodes_identity_and_count_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(document_id="doc_other", node_count=99)),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_TYPED_NODES_INVALID" for issue in issues))

    def test_validator_accepts_empty_typed_nodes_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"converted_md": "converted.md", "typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(node_count=0, nodes=[])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertEqual(issues, [])

    def test_validator_rejects_invalid_typed_node_text_and_metadata_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"converted_md": "converted.md", "typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            node = {"node_id": "n_000001", "ordinal": 1, "type": "heading", "text": None, "metadata": []}
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(nodes=[node])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        messages = [issue.message for issue in issues]
        self.assertIn("typed_nodes node text must be non-empty", messages)
        self.assertIn("typed_nodes node metadata must be an object", messages)

    def test_validator_rejects_typed_node_missing_required_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"converted_md": "converted.md", "typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            node = {"node_id": "n_000001", "ordinal": 1, "type": "heading", "text": "Title"}
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(nodes=[node])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.message == "typed_nodes node keys must match C1 schema exactly" for issue in issues))

    def test_validator_accepts_c1b_typed_node_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("---\ntitle: Example\n---\n\n![Alt](image.png)\n\n$$\nx\n$$\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"converted_md": "converted.md", "typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            nodes = [
                {
                    "node_id": "n_000001",
                    "ordinal": 1,
                    "type": "metadata",
                    "text": "title: Example",
                    "metadata": {"format": "yaml_frontmatter"},
                },
                {
                    "node_id": "n_000002",
                    "ordinal": 2,
                    "type": "figure",
                    "text": "![Alt](image.png)",
                    "metadata": {"alt": "Alt", "target": "image.png"},
                },
                {
                    "node_id": "n_000003",
                    "ordinal": 3,
                    "type": "formula",
                    "text": "x",
                    "metadata": {"syntax": "dollar_block"},
                },
            ]
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(node_count=3, nodes=nodes)),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertEqual(issues, [])

    def test_validator_rejects_non_integer_typed_node_count(self):
        invalid_counts = (True, "1", -1)
        for invalid_count in invalid_counts:
            with self.subTest(invalid_count=invalid_count):
                with tempfile.TemporaryDirectory() as tmp:
                    run_dir = Path(tmp)
                    converted = run_dir / "converted.md"
                    converted.write_text("# Safe\n", encoding="utf-8")
                    _write_valid_manifest_pair(
                        run_dir,
                        converted,
                        artifacts={"typed_nodes": "canonical_ir/typed_nodes.json"},
                        coverage={"typed_nodes_available": True},
                    )
                    (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                        json.dumps(_typed_nodes_payload(node_count=invalid_count)),
                        encoding="utf-8",
                    )

                    issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

                self.assertTrue(any(issue.code == "E_CANONICAL_IR_TYPED_NODES_INVALID" for issue in issues))

    def test_validator_rejects_fake_source_span_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            node = {"node_id": "n_000001", "ordinal": 1, "type": "heading", "text": "Title", "metadata": {}, "line_start": 1}
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(nodes=[node])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_TYPED_NODES_INVALID" for issue in issues))

    def test_validator_rejects_typed_nodes_source_artifact_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(source_artifact="../converted.md")),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_TYPED_NODES_INVALID" for issue in issues))

    def test_validator_rejects_typed_nodes_source_artifact_that_is_not_converted_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            alt = run_dir / "alt.md"
            alt.write_text("# Alternate\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"converted_md": "alt.md", "typed_nodes": "canonical_ir/typed_nodes.json"},
                coverage={"typed_nodes_available": True},
            )
            document_manifest = {
                "schema": "kbprep.document_manifest.v1",
                "canonical_ir_manifest": "canonical_ir/manifest.json",
                "converted_md": "alt.md",
                "conversion_report": "conversion_report.json",
                "created_from_run": "run_test",
            }
            (run_dir / "document_manifest.json").write_text(json.dumps(document_manifest), encoding="utf-8")
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(source_artifact="alt.md")),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=alt)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_TYPED_NODES_INVALID" for issue in issues))

    def test_validator_rejects_source_spans_claim_for_c1(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(run_dir, converted, coverage={"source_spans_available": True})

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_MANIFEST_INVALID" for issue in issues))


if __name__ == "__main__":
    unittest.main()
