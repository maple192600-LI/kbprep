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
    coverage: dict[str, object] | None = None,
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


def _coverage_report(
    *,
    typed_available: bool = True,
    source_spans_available: bool = False,
    transformation_ledger_available: bool = False,
    node_count: int = 1,
    span_count: int = 0,
    covered_count: int = 0,
    node_types: dict[str, int] | None = None,
    source_kinds: dict[str, int] | None = None,
    precisions: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "schema": "kbprep.canonical_ir_coverage_report.v1",
        "typed_nodes": {
            "artifact": "canonical_ir/typed_nodes.json",
            "available": typed_available,
            "status": "validated" if typed_available else "not_available",
            "node_count": node_count,
            "node_types": node_types if node_types is not None else ({"heading": node_count} if node_count else {}),
        },
        "source_spans": {
            "artifact": "canonical_ir/source_spans.json",
            "available": source_spans_available,
            "status": "validated" if source_spans_available else "not_available",
            "span_count": span_count,
            "typed_node_count": node_count,
            "covered_typed_node_count": covered_count,
            "typed_node_coverage_ratio": 1.0 if node_count == 0 else round(covered_count / node_count, 4),
            "source_kinds": source_kinds if source_kinds is not None else {},
            "precisions": precisions if precisions is not None else {},
        },
        "transformation_ledger": {
            "artifact": "canonical_ir/transformation_ledger.json",
            "available": transformation_ledger_available,
            "status": "validated" if transformation_ledger_available else "not_available",
            "entry_count": 6 if transformation_ledger_available else 0,
        },
        "gaps": {
            "route_native_precision": {"status": "target_work"},
            "relationships": {"status": "target_work"},
            "assets": {"status": "target_work"},
            "annotations": {"status": "target_work"},
            "ir_markdown_regeneration": {"status": "target_work"},
        },
    }


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


def _source_spans_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "kbprep.canonical_ir_source_spans.v1",
        "document_id": "doc_test",
        "source_artifact": "converted.md",
        "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
        "span_count": 1,
        "spans": [{
            "span_id": "s_000001",
            "node_id": "n_000001",
            "source_kind": "markdown_text",
            "location": {"converted_line_start": 1, "converted_line_end": 1},
            "evidence": {
                "source_type": "markdown_note",
                "converter": "direct_text",
                "conversion_route": "direct_text",
                "source_kind": "markdown_text",
                "precision": "converted_line_range",
            },
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
            self.assertEqual(canonical_manifest["artifacts"]["source_spans"], "canonical_ir/source_spans.json")
            self.assertTrue(canonical_manifest["coverage"]["typed_nodes_available"])
            self.assertTrue(canonical_manifest["coverage"]["source_spans_available"])
            typed_nodes = json.loads((run_dir / "canonical_ir" / "typed_nodes.json").read_text(encoding="utf-8"))
            self.assertEqual(typed_nodes["schema"], "kbprep.canonical_ir_typed_nodes.v1")
            self.assertEqual(typed_nodes["source_artifact"], "converted.md")
            self.assertEqual(typed_nodes["document_id"], canonical_manifest["document_id"])
            source_spans = json.loads((run_dir / "canonical_ir" / "source_spans.json").read_text(encoding="utf-8"))
            self.assertEqual(source_spans["schema"], "kbprep.canonical_ir_source_spans.v1")
            self.assertEqual(source_spans["typed_nodes_artifact"], "canonical_ir/typed_nodes.json")
            self.assertEqual(document_manifest["canonical_ir_manifest"], "canonical_ir/manifest.json")
            self.assertEqual(document_manifest["converted_md"], "converted.md")
            self.assertEqual(validate_canonical_ir_manifests(run_dir, converted_path=converted), [])

    def test_writer_uses_actual_route_for_source_span_conversion_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "source.pdf"
            converted = run_dir / "converted.md"
            source.write_text("pdf source placeholder", encoding="utf-8")
            converted.write_text("# Extracted\n", encoding="utf-8")
            (run_dir / "conversion_report.json").write_text(
                json.dumps({
                    "converter": "mineru",
                    "converted_md": str(converted),
                    "route_decision": {
                        "actual_converter": "mineru",
                        "actual_route": "mineru_ocr",
                    },
                }),
                encoding="utf-8",
            )
            (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")

            write_canonical_ir_manifests(
                run_dir=run_dir,
                input_path=source,
                source_type="pdf_like",
                file_hash="a" * 64,
                file_size=source.stat().st_size,
                run_id="run_test",
            )

            source_spans = json.loads((run_dir / "canonical_ir" / "source_spans.json").read_text(encoding="utf-8"))

        self.assertEqual(source_spans["spans"][0]["evidence"]["converter"], "mineru")
        self.assertEqual(source_spans["spans"][0]["evidence"]["conversion_route"], "mineru_ocr")

    def test_writer_falls_back_to_actual_converter_before_report_converter_when_route_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "source.txt"
            converted = run_dir / "converted.md"
            source.write_text("source text", encoding="utf-8")
            converted.write_text("source text\n", encoding="utf-8")
            (run_dir / "conversion_report.json").write_text(
                json.dumps({
                    "converter": "legacy_name",
                    "converted_md": str(converted),
                    "route_decision": {
                        "actual_converter": "direct_text",
                    },
                }),
                encoding="utf-8",
            )
            (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")

            write_canonical_ir_manifests(
                run_dir=run_dir,
                input_path=source,
                source_type="markdown_note",
                file_hash="b" * 64,
                file_size=source.stat().st_size,
                run_id="run_test",
            )

            source_spans = json.loads((run_dir / "canonical_ir" / "source_spans.json").read_text(encoding="utf-8"))
            manifest = json.loads((run_dir / "canonical_ir" / "manifest.json").read_text(encoding="utf-8"))
            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertEqual(source_spans["spans"][0]["evidence"]["converter"], "direct_text")
        self.assertEqual(source_spans["spans"][0]["evidence"]["conversion_route"], "direct_text")
        self.assertEqual(manifest["conversion"]["actual_route"], "direct_text")
        self.assertEqual(issues, [])

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

    def test_validator_rejects_assets_available_without_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            report = _coverage_report()
            report["assets"] = {
                "artifact": "canonical_ir/assets.json",
                "available": True,
                "status": "validated",
                "record_count": 1,
            }
            _write_valid_manifest_pair(
                run_dir,
                converted,
                coverage={"assets_available": True, "report": report},
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any("coverage.assets_available requires artifacts.assets" in issue.message for issue in issues))

    def test_validator_rejects_invalid_asset_artifact_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            report = _coverage_report()
            report["assets"] = {
                "artifact": "canonical_ir/assets.json",
                "available": True,
                "status": "validated",
                "record_count": 1,
            }
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"assets": "canonical_ir/assets.json"},
                coverage={"assets_available": True, "report": report},
            )
            (run_dir / "canonical_ir" / "assets.json").write_text(
                json.dumps({
                    "schema": "wrong.schema",
                    "document_id": "doc_test",
                    "asset_count": 1,
                    "assets": [{
                        "asset_id": "a_000001",
                        "asset_type": "image",
                        "source_node_id": "n_000001",
                        "reference": "images/chart.png",
                        "reference_kind": "markdown_image",
                        "copied_text": "Sensitive source sentence",
                    }],
                }),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any("assets schema is invalid" in issue.message for issue in issues))
        self.assertTrue(any("assets record keys must match schema exactly" in issue.message for issue in issues))

    def test_validator_rejects_record_artifact_top_level_source_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            report = _coverage_report()
            report["assets"] = {
                "artifact": "canonical_ir/assets.json",
                "available": True,
                "status": "validated",
                "record_count": 1,
            }
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"assets": "canonical_ir/assets.json"},
                coverage={"assets_available": True, "report": report},
            )
            (run_dir / "canonical_ir" / "assets.json").write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_assets.v1",
                    "document_id": "doc_test",
                    "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
                    "asset_count": 1,
                    "assets": [{
                        "asset_id": "a_000001",
                        "asset_type": "image",
                        "source_node_id": "n_000001",
                        "reference": "images/chart.png",
                        "reference_kind": "markdown_image",
                    }],
                    "copied_text": "Sensitive source sentence",
                }),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any("assets top-level keys must match schema exactly" in issue.message for issue in issues))

    def test_validator_rejects_record_artifact_evidence_source_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            report = _coverage_report()
            report["relationships"] = {
                "artifact": "canonical_ir/relationships.json",
                "available": True,
                "status": "validated",
                "record_count": 1,
            }
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"relationships": "canonical_ir/relationships.json"},
                coverage={"relationships_available": True, "report": report},
            )
            (run_dir / "canonical_ir" / "relationships.json").write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_relationships.v1",
                    "document_id": "doc_test",
                    "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
                    "relationship_count": 1,
                    "relationships": [{
                        "relationship_id": "r_000001",
                        "type": "next_sibling",
                        "source_node_id": "n_000001",
                        "target_node_id": "n_000002",
                        "evidence": {
                            "basis": "typed_node_order",
                            "copied_text": "Sensitive source sentence",
                        },
                    }],
                }),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any("relationships record evidence keys must match schema exactly" in issue.message for issue in issues))

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
                coverage={
                    "typed_nodes_available": True,
                    "report": _coverage_report(node_count=0),
                },
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
                coverage={
                    "typed_nodes_available": True,
                    "report": _coverage_report(
                        node_count=3,
                        node_types={"metadata": 1, "figure": 1, "formula": 1},
                    ),
                },
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
                coverage={
                    "typed_nodes_available": True,
                    "report": _coverage_report(
                        node_count=3,
                        node_types={"metadata": 1, "figure": 1, "formula": 1},
                    ),
                },
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
                coverage={
                    "typed_nodes_available": True,
                    "report": _coverage_report(
                        node_count=3,
                        node_types={"metadata": 1, "figure": 1, "formula": 1},
                    ),
                },
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

    def test_validator_accepts_source_spans_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={
                    "converted_md": "converted.md",
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                },
                coverage={
                    "typed_nodes_available": True,
                    "source_spans_available": True,
                    "report": _coverage_report(
                        source_spans_available=True,
                        span_count=1,
                        covered_count=1,
                        source_kinds={"markdown_text": 1},
                        precisions={"converted_line_range": 1},
                    ),
                },
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload()),
                encoding="utf-8",
            )
            (run_dir / "canonical_ir" / "source_spans.json").write_text(
                json.dumps(_source_spans_payload()),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertEqual(issues, [])

    def test_validator_rejects_source_spans_available_without_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(run_dir, converted, coverage={"source_spans_available": True})

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_MANIFEST_INVALID" for issue in issues))
        self.assertTrue(any("coverage.source_spans_available requires artifacts.source_spans" in issue.message for issue in issues))

    def test_validator_rejects_source_spans_artifact_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={"source_spans": "../source_spans.json"},
                coverage={"source_spans_available": True},
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_MANIFEST_INVALID" for issue in issues))

    def test_validator_rejects_invalid_source_spans_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={
                    "converted_md": "converted.md",
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                },
                coverage={"typed_nodes_available": True, "source_spans_available": True},
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload()),
                encoding="utf-8",
            )
            (run_dir / "canonical_ir" / "source_spans.json").write_text(
                json.dumps(_source_spans_payload(schema="wrong.schema")),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_SOURCE_SPANS_INVALID" for issue in issues))

    def test_validator_rejects_source_span_with_malformed_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={
                    "converted_md": "converted.md",
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                },
                coverage={"typed_nodes_available": True, "source_spans_available": True},
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload()),
                encoding="utf-8",
            )
            bad_span = {
                "span_id": "s_000001",
                "node_id": "n_000001",
                "source_kind": "markdown_text",
                "location": {"converted_line_start": 1, "converted_line_end": 1},
                "evidence": {"foo": "bar"},
            }
            (run_dir / "canonical_ir" / "source_spans.json").write_text(
                json.dumps(_source_spans_payload(spans=[bad_span])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_SOURCE_SPANS_INVALID" for issue in issues))
        self.assertTrue(any("source span evidence" in issue.message for issue in issues))

    def test_validator_rejects_source_line_precision_with_transcript_timing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("Host: Welcome\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={
                    "converted_md": "converted.md",
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                },
                coverage={"typed_nodes_available": True, "source_spans_available": True},
            )
            typed_payload = _typed_nodes_payload(
                nodes=[{
                    "node_id": "n_000001",
                    "ordinal": 1,
                    "type": "transcript_cue",
                    "text": "Host: Welcome",
                    "metadata": {"cue_index": 1, "speaker": "Host"},
                }],
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(json.dumps(typed_payload), encoding="utf-8")
            (run_dir / "canonical_ir" / "source_spans.json").write_text(
                json.dumps(_source_spans_payload(spans=[_transcript_span_with_conflicting_precision()])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertEqual(
            [issue.message for issue in issues if issue.code == "E_CANONICAL_IR_SOURCE_SPANS_INVALID"],
            ["source_line_range precision cannot include transcript cue fields"],
        )

    def test_validator_rejects_transcript_timing_precision_with_source_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("Host: Welcome\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={
                    "converted_md": "converted.md",
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                },
                coverage={"typed_nodes_available": True, "source_spans_available": True},
            )
            typed_payload = _typed_nodes_payload(
                nodes=[{
                    "node_id": "n_000001",
                    "ordinal": 1,
                    "type": "transcript_cue",
                    "text": "Host: Welcome",
                    "metadata": {"cue_index": 1, "speaker": "Host"},
                }],
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(json.dumps(typed_payload), encoding="utf-8")
            bad_span = {
                "span_id": "s_000001",
                "node_id": "n_000001",
                "source_kind": "transcript",
                "location": {
                    "converted_line_start": 1,
                    "converted_line_end": 1,
                    "source_line_start": 1,
                    "source_line_end": 1,
                    "cue_index": 1,
                    "cue_id": "1",
                    "start_time": "00:00:01,000",
                    "end_time": "00:00:03,000",
                },
                "evidence": {
                    "source_type": "subtitle_transcript",
                    "converter": "direct_text",
                    "conversion_route": "direct_text",
                    "source_kind": "transcript",
                    "precision": "transcript_cue_timing",
                },
            }
            (run_dir / "canonical_ir" / "source_spans.json").write_text(
                json.dumps(_source_spans_payload(spans=[bad_span])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertEqual(
            [issue.message for issue in issues if issue.code == "E_CANONICAL_IR_SOURCE_SPANS_INVALID"],
            ["transcript_cue_timing precision cannot include source line range"],
        )

    def test_validator_rejects_converted_line_precision_with_native_locations(self):
        cases = [
            (
                "source line range requires source_line_range precision",
                {
                    "span_id": "s_000001",
                    "node_id": "n_000001",
                    "source_kind": "markdown_text",
                    "location": {
                        "converted_line_start": 1,
                        "converted_line_end": 1,
                        "source_line_start": 1,
                        "source_line_end": 1,
                    },
                    "evidence": {
                        "source_type": "markdown_note",
                        "converter": "direct_text",
                        "conversion_route": "direct_text",
                        "source_kind": "markdown_text",
                        "precision": "converted_line_range",
                    },
                },
            ),
            (
                "transcript timing requires transcript_cue_timing precision",
                {
                    "span_id": "s_000001",
                    "node_id": "n_000001",
                    "source_kind": "transcript",
                    "location": {
                        "converted_line_start": 1,
                        "converted_line_end": 1,
                        "cue_index": 1,
                        "cue_id": "1",
                    },
                    "evidence": {
                        "source_type": "subtitle_transcript",
                        "converter": "direct_text",
                        "conversion_route": "direct_text",
                        "source_kind": "transcript",
                        "precision": "converted_line_range",
                    },
                },
            ),
            (
                "transcript timing requires transcript_cue_timing precision",
                {
                    "span_id": "s_000001",
                    "node_id": "n_000001",
                    "source_kind": "transcript",
                    "location": {
                        "converted_line_start": 1,
                        "converted_line_end": 1,
                        "cue_index": 1,
                        "start_time": "00:00:01,000",
                        "end_time": "00:00:03,000",
                    },
                    "evidence": {
                        "source_type": "subtitle_transcript",
                        "converter": "direct_text",
                        "conversion_route": "direct_text",
                        "source_kind": "transcript",
                        "precision": "converted_line_range",
                    },
                },
            ),
            (
                "transcript timing requires transcript_cue_timing precision",
                {
                    "span_id": "s_000001",
                    "node_id": "n_000001",
                    "source_kind": "transcript",
                    "location": {
                        "converted_line_start": 1,
                        "converted_line_end": 1,
                        "cue_index": 1,
                        "cue_settings": "align:start",
                    },
                    "evidence": {
                        "source_type": "subtitle_transcript",
                        "converter": "direct_text",
                        "conversion_route": "direct_text",
                        "source_kind": "transcript",
                        "precision": "converted_line_range",
                    },
                },
            ),
        ]
        for expected_message, bad_span in cases:
            with self.subTest(expected_message=expected_message):
                with tempfile.TemporaryDirectory() as tmp:
                    run_dir = Path(tmp)
                    converted = run_dir / "converted.md"
                    converted.write_text("Host: Welcome\n", encoding="utf-8")
                    _write_valid_manifest_pair(
                        run_dir,
                        converted,
                        artifacts={
                            "converted_md": "converted.md",
                            "typed_nodes": "canonical_ir/typed_nodes.json",
                            "source_spans": "canonical_ir/source_spans.json",
                        },
                        coverage={"typed_nodes_available": True, "source_spans_available": True},
                    )
                    (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                        json.dumps(_typed_nodes_payload()),
                        encoding="utf-8",
                    )
                    (run_dir / "canonical_ir" / "source_spans.json").write_text(
                        json.dumps(_source_spans_payload(spans=[bad_span])),
                        encoding="utf-8",
                    )

                    issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

                self.assertEqual(
                    [issue.message for issue in issues if issue.code == "E_CANONICAL_IR_SOURCE_SPANS_INVALID"],
                    [expected_message],
                )

    def test_validator_rejects_source_spans_artifact_when_coverage_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={
                    "converted_md": "converted.md",
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                },
                coverage={"typed_nodes_available": True, "source_spans_available": False},
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload()),
                encoding="utf-8",
            )
            (run_dir / "canonical_ir" / "source_spans.json").write_text(
                json.dumps(_source_spans_payload()),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_MANIFEST_INVALID" for issue in issues))
        self.assertTrue(
            any("coverage.source_spans_available must be true when artifacts.source_spans exists" in issue.message for issue in issues)
        )

    def test_validator_rejects_source_span_node_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={
                    "converted_md": "converted.md",
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                },
                coverage={"typed_nodes_available": True, "source_spans_available": True},
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload()),
                encoding="utf-8",
            )
            bad_span = {
                "span_id": "s_000001",
                "node_id": "n_999999",
                "source_kind": "markdown_text",
                "location": {"converted_line_start": 1, "converted_line_end": 1},
                "evidence": {
                    "source_type": "markdown_note",
                    "converter": "direct_text",
                    "conversion_route": "direct_text",
                    "source_kind": "markdown_text",
                    "precision": "converted_line_range",
                },
            }
            (run_dir / "canonical_ir" / "source_spans.json").write_text(
                json.dumps(_source_spans_payload(spans=[bad_span])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_SOURCE_SPANS_INVALID" for issue in issues))

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


def _transcript_span_with_conflicting_precision() -> dict[str, object]:
    return {
        "span_id": "s_000001",
        "node_id": "n_000001",
        "source_kind": "markdown_text",
        "location": {
            "converted_line_start": 1,
            "converted_line_end": 1,
            "cue_index": 1,
            "cue_id": "1",
            "source_line_start": 1,
            "source_line_end": 1,
            "start_time": "00:00:01,000",
            "end_time": "00:00:02,000",
        },
        "evidence": {
            "source_type": "subtitle_transcript",
            "converter": "direct_text",
            "conversion_route": "direct_text",
            "source_kind": "markdown_text",
            "precision": "source_line_range",
        },
    }


if __name__ == "__main__":
    unittest.main()
