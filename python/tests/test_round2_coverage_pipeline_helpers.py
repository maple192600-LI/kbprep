import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.converter_registry import ConversionRoute, ConversionRouteKind
from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.mineru_adapter import MinerUProcessError
from kbprep_worker.stages import pipeline_core, pipeline_helpers


def _capture_fail(fn, *args, **kwargs):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fn(*args, **kwargs)
    except EnvelopeExit as exc:
        return exc.code, json.loads(out.getvalue())
    raise AssertionError("expected envelope exit")


class PipelineHelperRound2CoverageTests(unittest.TestCase):
    def test_markdown_image_assets_copy_rewrite_and_report_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "source"
            source_dir.mkdir()
            (source_dir / "images").mkdir()
            (source_dir / "images" / "a.png").write_bytes(b"a")
            (source_dir / "photo with space.jpg").write_bytes(b"jpg")
            outside = root / "outside.png"
            outside.write_bytes(b"out")
            source = source_dir / "note.md"
            run_dir = root / "run"
            text = "\n".join([
                "![A](images/a.png)",
                "![B](<photo with space.jpg> \"title\")",
                "![[images/a.png|300]]",
                "![Remote](https://example.com/a.png)",
                f"![Outside]({outside})",
                "![Missing](missing.png)",
                "![NotImage](file.txt)",
            ])

            rewritten, artifacts = pipeline_core._copy_local_markdown_image_assets(text, source, run_dir)

            self.assertIn("![A](images/a.png)", rewritten)
            self.assertIn("![B](images/photo with space.jpg)", rewritten)
            self.assertIn("![](images/a.png)", rewritten)
            self.assertTrue((run_dir / "images" / "a.png").exists())
            self.assertTrue((run_dir / "images" / "photo with space.jpg").exists())
            self.assertEqual(artifacts["local_image_assets"]["copied_count"], 2)
            self.assertEqual(artifacts["local_image_assets"]["missing_count"], 1)
            self.assertGreaterEqual(artifacts["local_image_assets"]["skipped_count"], 1)
            self.assertTrue(artifacts["warnings"])
            self.assertEqual(pipeline_core._markdown_image_path_part("<x y.png> \"t\""), "x y.png")
            self.assertTrue(pipeline_core._is_nonlocal_markdown_image("data:image/png;base64,xxx"))
            self.assertFalse(pipeline_core._looks_like_image_reference("readme.txt"))

    def test_mineru_conversion_copies_images_and_pdf_fallback_records_rejected_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "scan.pdf"
            source.write_bytes(b"%PDF-")
            run_dir = root / "run"
            run_dir.mkdir()
            converted = run_dir / "converted.md"
            converted.write_text("���" * 80, encoding="utf-8")

            mineru_md = root / "mineru" / "source.md"
            (mineru_md.parent / "images").mkdir(parents=True)
            (mineru_md.parent / "images" / "page.png").write_bytes(b"png")
            mineru_md.write_text("OCR 正文\n![p](images/page.png)", encoding="utf-8")

            fake_result = {
                "source_md_path": str(mineru_md),
                "assets_dir": str(mineru_md.parent),
                "warnings": ["mineru warning"],
            }
            with patch("kbprep_worker.mineru_adapter.run_mineru", return_value=fake_result):
                result = pipeline_core._run_mineru_conversion(source, converted, run_dir, "zh", "ocr")
            self.assertEqual(result, fake_result)
            self.assertIn("OCR 正文", converted.read_text(encoding="utf-8"))
            self.assertTrue((run_dir / "images" / "page.png").exists())

            converted.write_text("���" * 80, encoding="utf-8")
            with patch("kbprep_worker.stages.pipeline_helpers._run_mineru_conversion", return_value={
                "source_md_path": str(mineru_md),
                "warnings": [],
            }):
                fallback = pipeline_helpers._maybe_fallback_pdf_markdown_to_mineru(
                    input_p=source,
                    converted_path=converted,
                    run_dir=run_dir,
                    language="ch",
                    source_route="pdf_text_layer",
                    source_artifacts={},
                )
            self.assertIsNotNone(fallback)
            assert fallback is not None
            self.assertEqual(fallback["fallback_from"], "pdf_text_layer")
            self.assertTrue(Path(fallback["rejected_text_layer_md"]).exists())
            self.assertTrue(fallback["warnings"])

            self.assertFalse(pipeline_core._pdf_text_layer_output_needs_ocr({"total_chars": 0, "garbled_ratio": 1}))
            with patch("kbprep_worker.mineru_adapter.run_mineru", return_value={"source_md_path": str(root / "missing.md")}):
                with self.assertRaises(pipeline_core.PipelineError) as raised:
                    pipeline_core._run_mineru_conversion(source, run_dir / "missing-converted.md", run_dir, "zh", "auto")
            self.assertEqual(raised.exception.code, "E_CONVERT_OUTPUT_MISSING")

    def test_mineru_conversion_emits_pdf_bbox_native_source_spans_from_content_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "scan.pdf"
            source.write_bytes(b"%PDF-")
            run_dir = root / "run"
            run_dir.mkdir()
            converted = run_dir / "converted.md"
            mineru_md = root / "mineru" / "source.md"
            mineru_md.parent.mkdir(parents=True)
            converted_text = "# Title\n\nFirst paragraph.\n\nSecond paragraph.\n"
            mineru_md.write_text(converted_text, encoding="utf-8")
            content_list_path = mineru_md.parent / "content_list.json"
            content_list_path.write_text(json.dumps([
                {"type": "text", "text": "First paragraph.", "page_idx": 0, "bbox": [10.0, 20.0, 100.0, 40.0]},
                {"type": "text", "text": "Second paragraph.", "page_idx": 1, "bbox": [5.0, 15.0, 90.0, 35.0]},
            ], ensure_ascii=False), encoding="utf-8")
            fake_result = {
                "source_md_path": str(mineru_md),
                "content_list_path": str(content_list_path),
                "assets_dir": str(mineru_md.parent),
                "warnings": [],
            }
            with patch("kbprep_worker.mineru_adapter.run_mineru", return_value=fake_result):
                result = pipeline_core._run_mineru_conversion(source, converted, run_dir, "zh", "ocr")

        native = result.get("native_source_spans")
        self.assertIsNotNone(native)
        assert native is not None
        self.assertEqual(len(native), 2)
        self.assertEqual(native[0]["precision"], "pdf_bbox")
        self.assertEqual(native[0]["location"]["page"], 1)
        self.assertEqual(native[0]["location"]["bbox"], [10.0, 20.0, 100.0, 40.0])
        # 1-based line numbers align with typed_node (canonical_nodes._parse_markdown_blocks uses start_index + 1).
        self.assertEqual(native[0]["converted_line_start"], 3)
        self.assertEqual(native[1]["converted_line_start"], 5)

    def test_conversion_reports_existing_run_scan_and_primary_quality_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            converted = run_dir / "converted.md"
            converted.write_text("正文", encoding="utf-8")
            route = ConversionRoute(
                kind=ConversionRouteKind.PDF_TEXT_LAYER,
                converter="pdf_text_layer",
                conversion_strategy="pdf_text_layer",
                matched_converter="pdf_text_layer",
                match_evidence=("extension:.pdf", "pdf_header"),
            )
            pipeline_core._write_conversion_report(
                run_dir=run_dir,
                input_path=root / "input.pdf",
                output_path=converted,
                converter="mineru_after_pdf_text_layer_fallback",
                route=route,
                source_type="pdf",
                mineru_artifacts={"fallback_from": "pdf_text_layer"},
                runtime={"python": "3"},
                diagnosis={"conversion_strategy": "pdf_text_layer"},
                warnings=["warn"],
            )
            report = json.loads((run_dir / "conversion_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["route_decision"]["fallback_applied"])
            self.assertEqual(report["route_decision"]["fallback_to"], "mineru_ocr")
            self.assertEqual(pipeline_core._actual_route_for_converter("mineru", {"conversion_strategy": "mineru_mixed_text_image"}), "mineru_mixed_text_image")  # noqa: E501

            runs = root / "runs"
            runs.mkdir()
            for idx in range(25):
                candidate = runs / f"{idx:02d}"
                candidate.mkdir()
                (candidate / "quality_report.json").write_text(
                    json.dumps({
                        "source_sha256": "hash",
                        "config_hash": "cfg",
                        "plugin_version": "v",
                        "runtime_cache_key": "rt",
                        "strict_errors": [] if idx == 24 else ["blocked"],
                    }),
                    encoding="utf-8",
                )
            existing = pipeline_core._find_existing_run(root, "hash", "cfg", "v", "rt")
            self.assertEqual(existing["run_id"], "24")
            self.assertIsNone(pipeline_core._find_existing_run(root, "missing", "cfg", "v", "rt"))
            self.assertIsNone(
                pipeline_core._find_existing_run(
                    root,
                    "hash",
                    "cfg",
                    "v",
                    "rt",
                    policy_snapshot_hash="policy-v2",
                ),
            )
            (runs / "24" / "quality_report.json").write_text(
                json.dumps({
                    "source_sha256": "hash",
                    "config_hash": "cfg",
                    "plugin_version": "v",
                    "runtime_cache_key": "rt",
                    "cleaning_policy_snapshot_hash": "policy-v1",
                    "strict_errors": [],
                }),
                encoding="utf-8",
            )
            matched = pipeline_core._find_existing_run(
                root,
                "hash",
                "cfg",
                "v",
                "rt",
                policy_snapshot_hash="policy-v1",
            )
            self.assertEqual(matched["run_id"], "24")
            self.assertIsNone(
                pipeline_core._find_existing_run(
                    root,
                    "hash",
                    "cfg",
                    "v",
                    "rt",
                    policy_snapshot_hash="policy-v2",
                ),
            )

            issue = pipeline_core._primary_quality_issue({"quality_issues": [{"code": "E_IMAGE_FILE_MISSING", "gate": "image"}]})
            self.assertEqual(issue["code"], "E_IMAGE_FILE_MISSING")
            fallback_issue = pipeline_core._primary_quality_issue({"strict_errors": ["E_CONVERTED_TEXT_UNREADABLE: bad"]})
            self.assertEqual(fallback_issue["gate"], "conversion_integrity")

    def test_conversion_report_preserves_selected_mineru_strategy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            converted = run_dir / "converted.md"
            converted.write_text("OCR text", encoding="utf-8")
            route = ConversionRoute(
                kind=ConversionRouteKind.MINERU_OCR,
                converter="mineru",
                conversion_strategy="mineru_auto",
                matched_converter="mineru",
                match_evidence=("extension:.pdf", "pdf_header"),
            )

            pipeline_core._write_conversion_report(
                run_dir=run_dir,
                input_path=root / "input.pdf",
                output_path=converted,
                converter="mineru",
                route=route,
                source_type="pdf",
                mineru_artifacts={},
                runtime={},
                diagnosis={"conversion_strategy": "mineru_auto"},
                warnings=[],
            )

            report = json.loads((run_dir / "conversion_report.json").read_text(encoding="utf-8"))
            decision = report["route_decision"]
            self.assertEqual(decision["selected_route"], "mineru_auto")
            self.assertEqual(decision["actual_route"], "mineru_auto")

    def test_error_handlers_source_identity_and_run_outputs_are_explainable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.md"
            source.write_text("# 标题", encoding="utf-8")
            state = pipeline_core.PipelineState({
                "input_path": str(source),
                "output_root": str(root / "out"),
                "source_identity": {"source_url": "https://www.example.com/a"},
                "source_metadata": {"site_name": "Example"},
            })
            state.run_dir = root / "out" / "runs" / "r1"
            state.run_dir.mkdir(parents=True)
            state.converted_path = state.run_dir / "converted.md"
            state.converted_path.write_text("正文", encoding="utf-8")
            state.latest_file = root / "out" / "latest.json"
            state.file_hash = "hash"
            state.plugin_version = "v"
            state.runtime_cache_key = "rt"

            identity = pipeline_core._source_identity_for_rules(source, state.data)
            self.assertEqual(identity["source_domain"], "example.com")
            self.assertEqual(pipeline_core._identity_scalar(3), "3")
            self.assertEqual(pipeline_core._domain_from_identity_url("https://www.test.com/x"), "test.com")
            self.assertIn("converted_md", pipeline_core._run_outputs(state))

            code, envelope = _capture_fail(
                pipeline_core._handle_pipeline_error,
                state,
                pipeline_core.PipelineError("E_TEST", "message", {"x": 1}),
            )
            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_TEST")

            code, envelope = _capture_fail(pipeline_core._handle_missing_mineru, state, FileNotFoundError("mineru"))
            self.assertEqual(envelope["error"]["code"], "E_MINERU_NOT_FOUND")

            code, envelope = _capture_fail(pipeline_core._handle_timeout, state, TimeoutError("slow"))
            self.assertEqual(envelope["error"]["code"], "E_TIMEOUT")

            code, envelope = _capture_fail(
                pipeline_core._handle_unexpected_error,
                state,
                MinerUProcessError("bad mineru", {"mineru_exit_code": 2}),
            )
            self.assertEqual(envelope["error"]["code"], "E_CONVERT_FAILED")
            self.assertEqual(envelope["error"]["details"]["mineru_exit_code"], 2)

    def test_prepare_success_payload_does_not_duplicate_envelope_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.md"
            source.write_text("# Title", encoding="utf-8")
            state = pipeline_core.PipelineState({
                "input_path": str(source),
                "output_root": str(root / "out"),
            })
            run_dir = root / "out" / "runs" / "r1"
            (run_dir / "chunks").mkdir(parents=True)
            (run_dir / "chunks" / "chunk-001.md").write_text("content", encoding="utf-8")
            state.run_id = "r1"
            state.latest_outputs = {"final_md": str(root / "input.cleaned.md")}

            code, envelope = _capture_fail(pipeline_core._emit_success, state, run_dir, {})

        self.assertEqual(code, 0)
        self.assertNotIn("ok", envelope["data"])
        self.assertEqual(envelope["data"]["run_id"], "r1")


if __name__ == "__main__":
    unittest.main()
