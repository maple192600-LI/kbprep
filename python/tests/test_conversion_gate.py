import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.canonical_ledger import write_transformation_ledger_artifact
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


def _enable_canonical_artifacts(run_dir: Path) -> None:
    manifest_path = run_dir / "canonical_ir" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["typed_nodes"] = "canonical_ir/typed_nodes.json"
    manifest["artifacts"]["source_spans"] = "canonical_ir/source_spans.json"
    manifest["coverage"]["typed_nodes_available"] = True
    manifest["coverage"]["source_spans_available"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _write_single_transcript_typed_node(run_dir: Path) -> None:
    (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
        json.dumps({
            "schema": "kbprep.canonical_ir_typed_nodes.v1",
            "document_id": "doc_test",
            "source_artifact": "converted.md",
            "node_count": 1,
            "nodes": [{
                "node_id": "n_000001",
                "ordinal": 1,
                "type": "transcript_cue",
                "text": "Host: Welcome",
                "metadata": {"cue_index": 1, "speaker": "Host"},
            }],
        }),
        encoding="utf-8",
    )


def _write_single_heading_canonical_artifacts(run_dir: Path) -> None:
    _write_heading_canonical_artifacts_at(run_dir, "canonical_ir", "Tutorial")


def _write_heading_canonical_artifacts_at(run_dir: Path, artifact_dir: str, heading_text: str) -> None:
    target_dir = run_dir / artifact_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "typed_nodes.json").write_text(
        json.dumps({
            "schema": "kbprep.canonical_ir_typed_nodes.v1",
            "document_id": "doc_test",
            "source_artifact": "converted.md",
            "node_count": 1,
            "nodes": [{
                "node_id": "n_000001",
                "ordinal": 1,
                "type": "heading",
                "text": heading_text,
                "metadata": {"heading_level": 1},
            }],
        }),
        encoding="utf-8",
    )
    (target_dir / "source_spans.json").write_text(
        json.dumps({
            "schema": "kbprep.canonical_ir_source_spans.v1",
            "document_id": "doc_test",
            "source_artifact": "converted.md",
            "typed_nodes_artifact": f"{artifact_dir}/typed_nodes.json",
            "span_count": 1,
            "spans": [_heading_source_span()],
        }),
        encoding="utf-8",
    )


def _heading_source_span() -> dict[str, object]:
    return {
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
    }


def _add_coverage_report(run_dir: Path, source_ratio: float = 1.0) -> None:
    manifest_path = run_dir / "canonical_ir" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["coverage"]["report"] = _coverage_report(source_ratio)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _point_coverage_report_to_artifacts(run_dir: Path, artifact_dir: str) -> None:
    manifest_path = run_dir / "canonical_ir" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = manifest["coverage"]["report"]
    report["typed_nodes"]["artifact"] = f"{artifact_dir}/typed_nodes.json"
    report["source_spans"]["artifact"] = f"{artifact_dir}/source_spans.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _enable_transformation_ledger(run_dir: Path, converted: Path) -> None:
    typed_nodes_path = run_dir / "canonical_ir" / "typed_nodes.json"
    source_spans_path = run_dir / "canonical_ir" / "source_spans.json"
    ledger_path = write_transformation_ledger_artifact(
        run_dir=run_dir,
        document_id="doc_test",
        run_id="run_test",
        converted_path=converted,
        typed_nodes_path=typed_nodes_path,
        typed_nodes_available=True,
        source_spans_path=source_spans_path,
        source_spans_available=True,
        conversion={
            "converter": "direct_text",
            "actual_route": "direct_text",
            "route_decision_hash": "hash",
        },
    )
    manifest_path = run_dir / "canonical_ir" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["transformation_ledger"] = ledger_path.relative_to(run_dir).as_posix()
    manifest["coverage"]["transformation_ledger_available"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _coverage_report(source_ratio: float) -> dict[str, object]:
    return {
        "schema": "kbprep.canonical_ir_coverage_report.v1",
        "typed_nodes": {
            "artifact": "canonical_ir/typed_nodes.json",
            "available": True,
            "status": "validated",
            "node_count": 1,
            "node_types": {"heading": 1},
        },
        "source_spans": {
            "artifact": "canonical_ir/source_spans.json",
            "available": True,
            "status": "validated",
            "span_count": 1,
            "typed_node_count": 1,
            "covered_typed_node_count": 1 if source_ratio == 1.0 else 0,
            "typed_node_coverage_ratio": source_ratio,
            "source_kinds": {"markdown_text": 1},
            "precisions": {"converted_line_range": 1},
        },
        "transformation_ledger": {
            "artifact": "canonical_ir/transformation_ledger.json",
            "available": False,
            "status": "not_available",
            "entry_count": 0,
        },
        "gaps": {
            "route_native_precision": {"status": "target_work"},
            "relationships": {"status": "target_work"},
            "assets": {"status": "target_work"},
            "annotations": {"status": "target_work"},
            "ir_markdown_regeneration": {"status": "target_work"},
        },
    }


def _write_conflicting_precision_source_span(run_dir: Path) -> None:
    (run_dir / "canonical_ir" / "source_spans.json").write_text(
        json.dumps({
            "schema": "kbprep.canonical_ir_source_spans.v1",
            "document_id": "doc_test",
            "source_artifact": "converted.md",
            "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
            "span_count": 1,
            "spans": [_conflicting_precision_source_span()],
        }),
        encoding="utf-8",
    )


def _conflicting_precision_source_span() -> dict[str, object]:
    return {
        "span_id": "s_000001",
        "node_id": "n_000001",
        "source_kind": "transcript",
        "location": _conflicting_precision_location(),
        "evidence": {
            "source_type": "subtitle_transcript",
            "converter": "direct_text",
            "conversion_route": "direct_text",
            "source_kind": "transcript",
            "precision": "source_line_range",
        },
    }


def _conflicting_precision_location() -> dict[str, object]:
    return {
        "converted_line_start": 1,
        "converted_line_end": 1,
        "cue_index": 1,
        "source_line_start": 1,
        "source_line_end": 1,
        "start_time": "00:00:01,000",
        "end_time": "00:00:02,000",
    }


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

    def test_pre_clean_conversion_gate_uses_complete_canonical_ir_text_quality_before_rendered_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("鐩綍 閮ㄧ讲 鏂规 " * 80, encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            _enable_canonical_artifacts(run_dir)
            _write_single_heading_canonical_artifacts(run_dir)
            _add_coverage_report(run_dir)

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["text_quality_source"], "canonical_ir")
        self.assertTrue(report["canonical_ir_gate_evidence"]["complete"])
        self.assertEqual(report["strict_errors"], [])

    def test_pre_clean_conversion_gate_prefers_complete_canonical_ir_over_report_text_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("鐩綍 閮ㄧ讲 鏂规 " * 80, encoding="utf-8")
            _write_conversion_report(
                run_dir,
                converted,
                mineru_artifacts={
                    "post_convert_text_quality": {
                        "total_chars": 100,
                        "garbled_ratio": 0.8,
                        "unreadable_text_ratio": 0.8,
                        "mojibake_ratio": 0.0,
                    },
                },
            )
            _write_valid_manifests(run_dir, converted)
            _enable_canonical_artifacts(run_dir)
            _write_single_heading_canonical_artifacts(run_dir)
            _add_coverage_report(run_dir)

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["text_quality_source"], "canonical_ir")
        self.assertTrue(report["canonical_ir_gate_evidence"]["complete"])
        self.assertEqual(report["strict_errors"], [])

    def test_pre_clean_conversion_gate_falls_back_to_rendered_markdown_when_ir_coverage_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("鐩綍 閮ㄧ讲 鏂规 " * 80, encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            _enable_canonical_artifacts(run_dir)
            _write_single_heading_canonical_artifacts(run_dir)
            _add_coverage_report(run_dir, source_ratio=0.0)

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertNotEqual(report["text_quality_source"], "canonical_ir")
        self.assertFalse(report["canonical_ir_gate_evidence"]["complete"])
        self.assertTrue(
            any(error.startswith("E_CANONICAL_IR_COVERAGE_REPORT_INVALID") for error in report["strict_errors"])
        )

    def test_pre_clean_conversion_gate_rejects_coverage_report_artifact_spoofing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("鐩綍 閮ㄧ讲 鏂规 " * 80, encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            _enable_canonical_artifacts(run_dir)
            _write_heading_canonical_artifacts_at(run_dir, "canonical_ir", "鐩綍 閮ㄧ讲 鏂规")
            _write_heading_canonical_artifacts_at(run_dir, "spoof", "Tutorial")
            _add_coverage_report(run_dir)
            _point_coverage_report_to_artifacts(run_dir, "spoof")

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertNotEqual(report["text_quality_source"], "canonical_ir")
        self.assertFalse(report["canonical_ir_gate_evidence"]["complete"])
        self.assertTrue(any(
            error.startswith("E_CANONICAL_IR_COVERAGE_REPORT_INVALID")
            for error in report["strict_errors"]
        ))

    def test_pre_clean_conversion_gate_does_not_mark_noncanonical_manifest_artifacts_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("鐩綍 閮ㄧ讲 鏂规 " * 80, encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            manifest_path = run_dir / "canonical_ir" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"]["typed_nodes"] = "spoof/typed_nodes.json"
            manifest["artifacts"]["source_spans"] = "spoof/source_spans.json"
            manifest["coverage"]["typed_nodes_available"] = True
            manifest["coverage"]["source_spans_available"] = True
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            _write_heading_canonical_artifacts_at(run_dir, "spoof", "Tutorial")
            _add_coverage_report(run_dir)
            _point_coverage_report_to_artifacts(run_dir, "spoof")

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertNotEqual(report["text_quality_source"], "canonical_ir")
        self.assertFalse(report["canonical_ir_gate_evidence"]["complete"])
        self.assertTrue(any(error.startswith("E_CANONICAL_IR_MANIFEST_INVALID") for error in report["strict_errors"]))

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

    def test_pre_clean_conversion_gate_fails_when_source_spans_are_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Tutorial\n\nRecord acceptance criteria.\n", encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            manifest_path = run_dir / "canonical_ir" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"]["typed_nodes"] = "canonical_ir/typed_nodes.json"
            manifest["artifacts"]["source_spans"] = "canonical_ir/source_spans.json"
            manifest["coverage"]["typed_nodes_available"] = True
            manifest["coverage"]["source_spans_available"] = True
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_typed_nodes.v1",
                    "document_id": "doc_test",
                    "source_artifact": "converted.md",
                    "node_count": 1,
                    "nodes": [{
                        "node_id": "n_000001",
                        "ordinal": 1,
                        "type": "heading",
                        "text": "Tutorial",
                        "metadata": {"heading_level": 1},
                    }],
                }),
                encoding="utf-8",
            )
            (run_dir / "canonical_ir" / "source_spans.json").write_text(
                json.dumps({"schema": "wrong.schema"}),
                encoding="utf-8",
            )

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocked_stage"], "cleanup")
        self.assertTrue(any(error.startswith("E_CANONICAL_IR_SOURCE_SPANS_INVALID") for error in report["strict_errors"]))
        self.assertTrue(any(action["action"] == "regenerate_canonical_ir" for action in report["failure_actions"]))

    def test_pre_clean_conversion_gate_fails_when_typed_nodes_available_lacks_coverage_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Tutorial\n\nRecord acceptance criteria.\n", encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            _enable_canonical_artifacts(run_dir)
            _write_single_heading_canonical_artifacts(run_dir)

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocked_stage"], "cleanup")
        self.assertTrue(any(error.startswith("E_CANONICAL_IR_COVERAGE_REPORT_INVALID") for error in report["strict_errors"]))
        self.assertTrue(any(action["action"] == "regenerate_canonical_ir" for action in report["failure_actions"]))

    def test_pre_clean_conversion_gate_fails_when_source_span_coverage_report_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Tutorial\n\nRecord acceptance criteria.\n", encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            _enable_canonical_artifacts(run_dir)
            _write_single_heading_canonical_artifacts(run_dir)
            _add_coverage_report(run_dir, source_ratio=0.0)

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocked_stage"], "cleanup")
        self.assertTrue(any(error.startswith("E_CANONICAL_IR_COVERAGE_REPORT_INVALID") for error in report["strict_errors"]))
        self.assertTrue(any(action["action"] == "regenerate_canonical_ir" for action in report["failure_actions"]))

    def test_pre_clean_conversion_gate_fails_when_ledger_coverage_report_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Tutorial\n\nRecord acceptance criteria.\n", encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            _enable_canonical_artifacts(run_dir)
            _write_single_heading_canonical_artifacts(run_dir)
            _enable_transformation_ledger(run_dir, converted)
            _add_coverage_report(run_dir)

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocked_stage"], "cleanup")
        self.assertTrue(any(error.startswith("E_CANONICAL_IR_COVERAGE_REPORT_INVALID") for error in report["strict_errors"]))
        self.assertTrue(any(action["action"] == "regenerate_canonical_ir" for action in report["failure_actions"]))

    def test_pre_clean_conversion_gate_fails_when_source_span_precision_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("Host: Welcome\n", encoding="utf-8")
            _write_conversion_report(run_dir, converted)
            _write_valid_manifests(run_dir, converted)
            _enable_canonical_artifacts(run_dir)
            _write_single_transcript_typed_node(run_dir)
            _write_conflicting_precision_source_span(run_dir)

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["blocked_stage"], "cleanup")
        self.assertTrue(any(error.startswith("E_CANONICAL_IR_SOURCE_SPANS_INVALID") for error in report["strict_errors"]))
        self.assertTrue(any(action["action"] == "regenerate_canonical_ir" for action in report["failure_actions"]))

    def test_pre_clean_conversion_gate_deduplicates_typed_node_failure_actions(self):
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
            bad_node = {"node_id": "bad", "ordinal": 2, "type": "unknown", "text": "", "metadata": []}
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_typed_nodes.v1",
                    "document_id": "doc_test",
                    "source_artifact": "converted.md",
                    "node_count": 1,
                    "nodes": [bad_node],
                }),
                encoding="utf-8",
            )

            report = run_pre_clean_conversion_gate(run_dir, diagnosis={})

        typed_node_actions = [
            action for action in report["failure_actions"] if action["code"] == "E_CANONICAL_IR_TYPED_NODES_INVALID"
        ]
        typed_node_errors = [
            error for error in report["strict_errors"] if error.startswith("E_CANONICAL_IR_TYPED_NODES_INVALID")
        ]
        self.assertEqual(report["status"], "fail")
        self.assertGreaterEqual(len(typed_node_errors), 2)
        self.assertEqual(len(typed_node_actions), 1)
        self.assertEqual(typed_node_actions[0]["action"], "regenerate_canonical_ir")


if __name__ == "__main__":
    unittest.main()
