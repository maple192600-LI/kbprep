import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.canonical_ir import validate_canonical_ir_manifests
from kbprep_worker.canonical_ledger import (
    CANONICAL_IR_TRANSFORMATION_LEDGER_SCHEMA,
    validate_transformation_ledger_artifact,
    validate_transformation_ledger_reference,
    write_transformation_ledger_artifact,
)


def _typed_nodes_payload() -> dict[str, object]:
    return {
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


def _source_spans_payload() -> dict[str, object]:
    return {
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


def _write_manifest_pair(
    run_dir: Path,
    converted: Path,
    *,
    artifacts: dict[str, str] | None = None,
    coverage: dict[str, bool] | None = None,
) -> None:
    canonical_dir = run_dir / "canonical_ir"
    canonical_dir.mkdir(parents=True, exist_ok=True)
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
    (run_dir / "conversion_report.json").write_text("{}", encoding="utf-8")
    (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")
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
            "converted_md": converted.name,
            "conversion_report": "conversion_report.json",
            "created_from_run": "run_test",
        }),
        encoding="utf-8",
    )


def _write_valid_ledger_fixture(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    run_dir = root
    canonical_dir = run_dir / "canonical_ir"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    converted = run_dir / "converted.md"
    typed_nodes = canonical_dir / "typed_nodes.json"
    source_spans = canonical_dir / "source_spans.json"
    converted.write_text("# Note\n", encoding="utf-8")
    typed_nodes.write_text(json.dumps(_typed_nodes_payload()), encoding="utf-8")
    source_spans.write_text(json.dumps(_source_spans_payload()), encoding="utf-8")
    ledger = write_transformation_ledger_artifact(
        run_dir=run_dir,
        document_id="doc_test",
        run_id="run_test",
        converted_path=converted,
        typed_nodes_path=typed_nodes,
        typed_nodes_available=True,
        source_spans_path=source_spans,
        source_spans_available=True,
        conversion={
            "converter": "direct_text",
            "actual_route": "direct_text",
            "route_decision_hash": "abc123",
        },
    )
    return run_dir, ledger, converted, typed_nodes, source_spans


class CanonicalIrTransformationLedgerTests(unittest.TestCase):
    def test_writer_records_conversion_and_ir_artifact_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger_path, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))

            payload = json.loads(ledger_path.read_text(encoding="utf-8"))
            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger_path,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertEqual(payload["schema"], CANONICAL_IR_TRANSFORMATION_LEDGER_SCHEMA)
        self.assertEqual(payload["document_id"], "doc_test")
        self.assertEqual(payload["canonical_ir_manifest"], "canonical_ir/manifest.json")
        self.assertEqual(payload["converted_artifact"], "converted.md")
        self.assertEqual(payload["typed_nodes_artifact"], "canonical_ir/typed_nodes.json")
        self.assertEqual(payload["source_spans_artifact"], "canonical_ir/source_spans.json")
        self.assertEqual(payload["created_from_run"], "run_test")
        self.assertEqual(payload["entry_count"], 6)
        self.assertEqual([entry["ordinal"] for entry in payload["entries"]], [1, 2, 3, 4, 5, 6])
        self.assertEqual(
            [entry["entry_id"] for entry in payload["entries"]],
            ["e_000001", "e_000002", "e_000003", "e_000004", "e_000005", "e_000006"],
        )
        self.assertEqual(
            [entry["operation"] for entry in payload["entries"]],
            [
                "route_decision_recorded",
                "converted_markdown_written",
                "typed_nodes_artifact_written",
                "typed_nodes_artifact_validated",
                "source_spans_artifact_written",
                "source_spans_artifact_validated",
            ],
        )
        self.assertEqual(issues, [])

    def test_validator_rejects_entry_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["entry_count"] = 99
            ledger.write_text(json.dumps(payload), encoding="utf-8")

            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertTrue(any("entry_count must equal len(entries)" in issue.message for issue in issues))

    def test_validator_rejects_reordered_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["entries"][0], payload["entries"][1] = payload["entries"][1], payload["entries"][0]
            ledger.write_text(json.dumps(payload), encoding="utf-8")

            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertTrue(any("ordinal must match entry position" in issue.message for issue in issues))

    def test_validator_rejects_evidence_ref_that_escapes_run_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["entries"][0]["evidence_refs"] = ["../conversion_report.json"]
            ledger.write_text(json.dumps(payload), encoding="utf-8")

            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertTrue(any("evidence_refs must stay inside the run directory" in issue.message for issue in issues))

    def test_validator_rejects_details_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["entries"][0]["details"]["actual_route"] = "tampered"
            ledger.write_text(json.dumps(payload), encoding="utf-8")

            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertTrue(any("details_hash must match details" in issue.message for issue in issues))

    def test_validator_rejects_header_schema_and_document_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["schema"] = "wrong.schema"
            payload["document_id"] = "doc_other"
            ledger.write_text(json.dumps(payload), encoding="utf-8")

            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        messages = [issue.message for issue in issues]
        self.assertIn("transformation_ledger schema is invalid", messages)
        self.assertIn("transformation_ledger.document_id must match canonical manifest", messages)

    def test_validator_rejects_header_artifact_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["converted_artifact"] = "../converted.md"
            ledger.write_text(json.dumps(payload), encoding="utf-8")

            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertTrue(any("converted_artifact must stay inside the run directory" in issue.message for issue in issues))

    def test_validator_rejects_header_wrong_artifact_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ledger, converted, typed_nodes, source_spans = _write_valid_ledger_fixture(Path(tmp))
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["typed_nodes_artifact"] = "canonical_ir/other_typed_nodes.json"
            ledger.write_text(json.dumps(payload), encoding="utf-8")

            issues = validate_transformation_ledger_artifact(
                run_dir=run_dir,
                ledger_path=ledger,
                document_id="doc_test",
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_spans_path=source_spans,
            )

        self.assertTrue(any("typed_nodes_artifact must reference expected artifact" in issue.message for issue in issues))

    def test_reference_validator_accepts_valid_manifest_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ledger, converted, _typed_nodes, _source_spans = _write_valid_ledger_fixture(Path(tmp))

            issues = validate_transformation_ledger_reference(
                run_dir=run_dir,
                artifacts={
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                    "transformation_ledger": "canonical_ir/transformation_ledger.json",
                },
                coverage={"transformation_ledger_available": True},
                document_id="doc_test",
                converted_path=converted,
            )

        self.assertEqual(issues, [])

    def test_manifest_validator_accepts_valid_ledger_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ledger, converted, _typed_nodes, _source_spans = _write_valid_ledger_fixture(Path(tmp))
            _write_manifest_pair(
                run_dir,
                converted,
                artifacts={
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                    "transformation_ledger": "canonical_ir/transformation_ledger.json",
                },
                coverage={
                    "typed_nodes_available": True,
                    "source_spans_available": True,
                    "transformation_ledger_available": True,
                },
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertEqual(issues, [])

    def test_reference_validator_rejects_claim_without_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Note\n", encoding="utf-8")

            issues = validate_transformation_ledger_reference(
                run_dir=run_dir,
                artifacts={},
                coverage={"transformation_ledger_available": True},
                document_id="doc_test",
                converted_path=converted,
            )

        self.assertTrue(any("requires artifacts.transformation_ledger" in issue.message for issue in issues))

    def test_manifest_validator_rejects_claim_without_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Note\n", encoding="utf-8")
            _write_manifest_pair(run_dir, converted, coverage={"transformation_ledger_available": True})

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(
            "coverage.transformation_ledger_available requires artifacts.transformation_ledger" in issue.message
            for issue in issues
        ))

    def test_reference_validator_rejects_artifact_without_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ledger, converted, _typed_nodes, _source_spans = _write_valid_ledger_fixture(Path(tmp))

            issues = validate_transformation_ledger_reference(
                run_dir=run_dir,
                artifacts={
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                    "transformation_ledger": "canonical_ir/transformation_ledger.json",
                },
                coverage={"transformation_ledger_available": False},
                document_id="doc_test",
                converted_path=converted,
            )

        self.assertTrue(any("must be true when artifacts.transformation_ledger exists" in issue.message for issue in issues))

    def test_manifest_validator_rejects_artifact_without_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ledger, converted, _typed_nodes, _source_spans = _write_valid_ledger_fixture(Path(tmp))
            _write_manifest_pair(
                run_dir,
                converted,
                artifacts={
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                    "transformation_ledger": "canonical_ir/transformation_ledger.json",
                },
                coverage={
                    "typed_nodes_available": True,
                    "source_spans_available": True,
                    "transformation_ledger_available": False,
                },
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertFalse([issue for issue in issues if issue.code == "E_CANONICAL_IR_SOURCE_SPANS_INVALID"], issues)
        self.assertTrue(any(
            "coverage.transformation_ledger_available must be true when artifacts.transformation_ledger exists"
            in issue.message
            for issue in issues
        ))

    def test_reference_validator_continues_after_artifact_without_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ledger, converted, _typed_nodes, _source_spans = _write_valid_ledger_fixture(Path(tmp))

            issues = validate_transformation_ledger_reference(
                run_dir=run_dir,
                artifacts={
                    "typed_nodes": "../typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                    "transformation_ledger": "../transformation_ledger.json",
                },
                coverage={"transformation_ledger_available": False},
                document_id="doc_test",
                converted_path=converted,
            )

        messages = [issue.message for issue in issues]
        self.assertIn("coverage.transformation_ledger_available must be true when artifacts.transformation_ledger exists", messages)
        self.assertTrue(any("transformation_ledger must stay inside the run directory" in message for message in messages))
        self.assertTrue(any("typed_nodes must stay inside the run directory" in message for message in messages))

    def test_reference_validator_rejects_missing_sibling_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ledger, converted, _typed_nodes, _source_spans = _write_valid_ledger_fixture(Path(tmp))

            issues = validate_transformation_ledger_reference(
                run_dir=run_dir,
                artifacts={"transformation_ledger": "canonical_ir/transformation_ledger.json"},
                coverage={"transformation_ledger_available": True},
                document_id="doc_test",
                converted_path=converted,
            )

        messages = [issue.message for issue in issues]
        self.assertTrue(any("typed_nodes must be a relative path string" in message for message in messages))
        self.assertTrue(any("source_spans must be a relative path string" in message for message in messages))

    def test_reference_validator_rejects_wrong_ledger_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ledger, converted, _typed_nodes, _source_spans = _write_valid_ledger_fixture(Path(tmp))

            issues = validate_transformation_ledger_reference(
                run_dir=run_dir,
                artifacts={
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                    "transformation_ledger": "canonical_ir/other_ledger.json",
                },
                coverage={"transformation_ledger_available": True},
                document_id="doc_test",
                converted_path=converted,
            )

        self.assertTrue(any("must reference canonical_ir/transformation_ledger.json" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
