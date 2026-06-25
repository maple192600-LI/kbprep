import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.canonical_coverage import build_canonical_ir_coverage_report


class CanonicalIrCoverageReportTests(unittest.TestCase):
    def test_route_native_precision_gap_lists_only_missing_native_precisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            canonical_dir = run_dir / "canonical_ir"
            canonical_dir.mkdir()
            typed_nodes = canonical_dir / "typed_nodes.json"
            source_spans = canonical_dir / "source_spans.json"
            ledger = canonical_dir / "transformation_ledger.json"
            typed_nodes.write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_typed_nodes.v1",
                    "document_id": "doc_test",
                    "source_artifact": "converted.md",
                    "node_count": 2,
                    "nodes": [
                        {"node_id": "n_000001", "ordinal": 1, "type": "heading", "text": "Title", "metadata": {}},
                        {"node_id": "n_000002", "ordinal": 2, "type": "paragraph", "text": "Body", "metadata": {}},
                    ],
                }),
                encoding="utf-8",
            )
            source_spans.write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_source_spans.v1",
                    "document_id": "doc_test",
                    "source_artifact": "converted.md",
                    "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
                    "span_count": 2,
                    "spans": [
                        {
                            "span_id": "s_000001",
                            "node_id": "n_000001",
                            "source_kind": "pdf",
                            "location": {
                                "converted_line_start": 1,
                                "converted_line_end": 1,
                                "page": 1,
                                "bbox": [0.0, 0.0, 100.0, 20.0],
                            },
                            "evidence": {
                                "source_type": "pdf_like",
                                "converter": "test_converter",
                                "conversion_route": "test_route",
                                "source_kind": "pdf",
                                "precision": "pdf_bbox",
                            },
                        },
                        {
                            "span_id": "s_000002",
                            "node_id": "n_000002",
                            "source_kind": "markdown_text",
                            "location": {"converted_line_start": 3, "converted_line_end": 3},
                            "evidence": {
                                "source_type": "markdown_note",
                                "converter": "direct_text",
                                "conversion_route": "direct_text",
                                "source_kind": "markdown_text",
                                "precision": "converted_line_range",
                            },
                        },
                    ],
                }),
                encoding="utf-8",
            )
            ledger.write_text(json.dumps({"entries": []}), encoding="utf-8")

            report = build_canonical_ir_coverage_report(
                run_dir=run_dir,
                typed_nodes_path=typed_nodes,
                typed_nodes_available=True,
                source_spans_path=source_spans,
                source_spans_available=True,
                transformation_ledger_path=ledger,
                transformation_ledger_available=False,
            )

        gap = report["gaps"]["route_native_precision"]
        self.assertEqual(gap["status"], "partial")
        self.assertIn("pdf_bbox", gap["current_precisions"])
        self.assertNotIn("pdf_bbox", gap["missing"])
        self.assertIn("docx_run_range", gap["missing"])
        self.assertIn("transcript_cue_id", gap["missing"])

    def test_route_native_precision_does_not_claim_complete_before_converter_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            canonical_dir = run_dir / "canonical_ir"
            canonical_dir.mkdir()
            typed_nodes = canonical_dir / "typed_nodes.json"
            source_spans = canonical_dir / "source_spans.json"
            ledger = canonical_dir / "transformation_ledger.json"
            native_cases = [
                ("pdf", {"converted_line_start": 1, "converted_line_end": 1, "page": 1, "bbox": [0.0, 0.0, 10.0, 10.0]}, "pdf_bbox"),
                (
                    "docx",
                    {"converted_line_start": 2, "converted_line_end": 2, "paragraph_index": 0, "run_start": 0, "run_end": 1},
                    "docx_run_range",
                ),
                ("pptx", {"converted_line_start": 3, "converted_line_end": 3, "slide": 1, "shape_id": "shape-1"}, "pptx_shape"),
                (
                    "xlsx",
                    {"converted_line_start": 4, "converted_line_end": 4, "sheet": "Sheet1", "start": "A1", "end": "B2"},
                    "xlsx_cell_range",
                ),
                (
                    "transcript",
                    {"converted_line_start": 5, "converted_line_end": 5, "cue_index": 1, "cue_id": "cue-1"},
                    "transcript_cue_id",
                ),
                ("youtube", {"converted_line_start": 6, "converted_line_end": 6, "cue_id": "yt-cue-1"}, "youtube_cue_id"),
            ]
            typed_nodes.write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_typed_nodes.v1",
                    "document_id": "doc_test",
                    "source_artifact": "converted.md",
                    "node_count": len(native_cases),
                    "nodes": [
                        {"node_id": f"n_{index:06d}", "ordinal": index, "type": "paragraph", "text": f"Node {index}", "metadata": {}}
                        for index in range(1, len(native_cases) + 1)
                    ],
                }),
                encoding="utf-8",
            )
            source_spans.write_text(
                json.dumps({
                    "schema": "kbprep.canonical_ir_source_spans.v1",
                    "document_id": "doc_test",
                    "source_artifact": "converted.md",
                    "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
                    "span_count": len(native_cases),
                    "spans": [
                        {
                            "span_id": f"s_{index:06d}",
                            "node_id": f"n_{index:06d}",
                            "source_kind": source_kind,
                            "location": location,
                            "evidence": {
                                "source_type": "test",
                                "converter": "test_converter",
                                "conversion_route": "test_route",
                                "source_kind": source_kind,
                                "precision": precision,
                            },
                        }
                        for index, (source_kind, location, precision) in enumerate(native_cases, start=1)
                    ],
                }),
                encoding="utf-8",
            )
            ledger.write_text(json.dumps({"entries": []}), encoding="utf-8")

            report = build_canonical_ir_coverage_report(
                run_dir=run_dir,
                typed_nodes_path=typed_nodes,
                typed_nodes_available=True,
                source_spans_path=source_spans,
                source_spans_available=True,
                transformation_ledger_path=ledger,
                transformation_ledger_available=False,
            )

        gap = report["gaps"]["route_native_precision"]
        self.assertEqual(gap["missing"], [])
        self.assertEqual(gap["status"], "partial")


if __name__ == "__main__":
    unittest.main()
