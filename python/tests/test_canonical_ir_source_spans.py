import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from kbprep_worker.canonical_ir import write_canonical_ir_manifests
from kbprep_worker.canonical_nodes import write_typed_nodes_artifact
from kbprep_worker.canonical_spans import (
    CANONICAL_IR_SOURCE_SPANS_SCHEMA,
    validate_source_spans_artifact,
    write_source_spans_artifact,
)
from kbprep_worker.converters.office_xml import office_xml_to_markdown


class CanonicalIrSourceSpanTests(unittest.TestCase):
    def test_writes_source_spans_for_markdown_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "source.md"
            converted = run_dir / "converted.md"
            converted.write_text("# Title\n\nParagraph one\ncontinued line\n\n- Item\n", encoding="utf-8")
            source.write_text(converted.read_text(encoding="utf-8"), encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="markdown_note",
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="markdown_note",
                converter="direct_text",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], CANONICAL_IR_SOURCE_SPANS_SCHEMA)
        self.assertEqual(payload["document_id"], "doc_test")
        self.assertEqual(payload["source_artifact"], "converted.md")
        self.assertEqual(payload["typed_nodes_artifact"], "canonical_ir/typed_nodes.json")
        self.assertEqual(payload["span_count"], 3)
        self.assertEqual([span["span_id"] for span in payload["spans"]], ["s_000001", "s_000002", "s_000003"])
        self.assertEqual([span["node_id"] for span in payload["spans"]], ["n_000001", "n_000002", "n_000003"])
        self.assertEqual(payload["spans"][0]["location"]["converted_line_start"], 1)
        self.assertEqual(payload["spans"][1]["location"]["converted_line_start"], 3)
        self.assertEqual(payload["spans"][1]["location"]["converted_line_end"], 4)
        self.assertEqual(payload["spans"][1]["source_kind"], "markdown_text")
        self.assertEqual(payload["spans"][1]["evidence"]["precision"], "source_line_range")

    def test_writes_transcript_source_spans_with_timing_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "lesson.srt"
            converted = run_dir / "converted.md"
            source.write_text(
                "\n".join([
                    "1",
                    "00:00:01,000 --> 00:00:04,000",
                    "Host: Welcome to the lesson.",
                    "",
                    "2",
                    "00:00:05,000 --> 00:00:08,000",
                    "Guest: Set threshold to 0.8.",
                ]),
                encoding="utf-8",
            )
            converted.write_text(
                "# Transcript\n\nHost: Welcome to the lesson.\n\nGuest: Set threshold to 0.8.\n",
                encoding="utf-8",
            )
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="subtitle_transcript",
                converter="direct_text",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))
            issues = validate_source_spans_artifact(
                run_dir=run_dir,
                source_spans_path=artifact,
                typed_nodes_path=typed_nodes,
                document_id="doc_test",
                converted_path=converted,
            )

        cue_span = payload["spans"][1]
        self.assertEqual(cue_span["source_kind"], "transcript")
        self.assertEqual(cue_span["location"]["cue_index"], 1)
        self.assertEqual(cue_span["location"]["start_time"], "00:00:01,000")
        self.assertEqual(cue_span["location"]["end_time"], "00:00:04,000")
        self.assertEqual(cue_span["evidence"]["precision"], "transcript_cue_timing")
        self.assertEqual(issues, [])

    def test_transcript_intro_does_not_shift_raw_cue_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "lesson.srt"
            converted = run_dir / "converted.md"
            source.write_text(
                "\n".join([
                    "1",
                    "00:00:01,000 --> 00:00:04,000",
                    "Host: Welcome to the lesson.",
                ]),
                encoding="utf-8",
            )
            converted.write_text(
                "# Transcript\n\nThis note was added before cues.\n\nHost: Welcome to the lesson.\n",
                encoding="utf-8",
            )
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="subtitle_transcript",
                converter="direct_text",
                conversion_route="direct_text",
            )

            typed_payload = json.loads(typed_nodes.read_text(encoding="utf-8"))
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            issues = validate_source_spans_artifact(
                run_dir=run_dir,
                source_spans_path=artifact,
                typed_nodes_path=typed_nodes,
                document_id="doc_test",
                converted_path=converted,
            )

        self.assertEqual([node["type"] for node in typed_payload["nodes"]], ["heading", "paragraph", "transcript_cue"])
        self.assertEqual(payload["spans"][1]["source_kind"], "converted_markdown")
        self.assertNotIn("cue_index", payload["spans"][1]["location"])
        self.assertEqual(payload["spans"][2]["source_kind"], "transcript")
        self.assertEqual(payload["spans"][2]["location"]["cue_index"], 1)
        self.assertEqual(payload["spans"][2]["location"]["start_time"], "00:00:01,000")
        self.assertEqual(issues, [])

    def test_csv_source_spans_use_structured_data_source_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "source.csv"
            converted = run_dir / "converted.md"
            source.write_text("key,value\nalpha,1\n", encoding="utf-8")
            converted.write_text("| key | value |\n| --- | --- |\n| alpha | 1 |\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="structured_data",
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="structured_data",
                converter="direct_text",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["source_kind"], "structured_data")
        self.assertEqual(payload["spans"][0]["evidence"]["source_kind"], "structured_data")
        self.assertEqual(payload["spans"][0]["evidence"]["precision"], "converted_line_range")

    def test_gbk_srt_source_spans_keep_transcript_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "lesson.srt"
            converted = run_dir / "converted.md"
            source.write_bytes(
                "\n".join([
                    "1",
                    "00:00:01,000 --> 00:00:03,000",
                    "主持人: 欢迎开始",
                ]).encode("gbk")
            )
            converted.write_text("主持人: 欢迎开始\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="subtitle_transcript",
                converter="direct_text",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["source_kind"], "transcript")
        self.assertEqual(payload["spans"][0]["location"]["start_time"], "00:00:01,000")
        self.assertEqual(payload["spans"][0]["evidence"]["precision"], "transcript_cue_timing")

    def test_webvtt_source_spans_include_cue_settings_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "lesson.vtt"
            converted = run_dir / "converted.md"
            source.write_text(
                "\n".join([
                    "WEBVTT",
                    "",
                    "intro",
                    "00:00:01.000 --> 00:00:03.000 align:start position:0%",
                    "Host: Welcome",
                ]),
                encoding="utf-8",
            )
            converted.write_text("Host: Welcome\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="subtitle_transcript",
                converter="direct_text",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["location"]["cue_id"], "intro")
        self.assertEqual(payload["spans"][0]["location"]["cue_settings"], "align:start position:0%")

    def test_ipynb_source_spans_use_notebook_source_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "analysis.ipynb"
            converted = run_dir / "converted.md"
            source.write_text('{"cells":[]}', encoding="utf-8")
            converted.write_text("# Notebook\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="structured_data",
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="structured_data",
                converter="notebook_json",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["source_kind"], "notebook")
        self.assertEqual(payload["spans"][0]["evidence"]["source_kind"], "notebook")

    def test_reordered_transcript_text_does_not_attach_later_cue_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "lesson.srt"
            converted = run_dir / "converted.md"
            source.write_text(
                "\n".join([
                    "1",
                    "00:00:01,000 --> 00:00:03,000",
                    "Host: First cue",
                    "",
                    "2",
                    "00:00:04,000 --> 00:00:06,000",
                    "Guest: Second cue",
                ]),
                encoding="utf-8",
            )
            converted.write_text("Guest: Second cue\n\nHost: First cue\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="subtitle_transcript",
                converter="direct_text",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["source_kind"], "converted_markdown")
        self.assertNotIn("start_time", payload["spans"][0]["location"])
        self.assertEqual(payload["spans"][1]["source_kind"], "transcript")
        self.assertEqual(payload["spans"][1]["location"]["cue_id"], "1")

    def test_transcript_matching_preserves_timing_after_missing_middle_cue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "lesson.srt"
            converted = run_dir / "converted.md"
            source.write_text(
                "\n".join([
                    "1",
                    "00:00:01,000 --> 00:00:03,000",
                    "Host: First cue",
                    "",
                    "2",
                    "00:00:04,000 --> 00:00:06,000",
                    "Guest: Removed cue",
                    "",
                    "3",
                    "00:00:07,000 --> 00:00:09,000",
                    "Host: Third cue",
                ]),
                encoding="utf-8",
            )
            converted.write_text("Host: First cue\n\nHost: Third cue\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="subtitle_transcript",
                converter="direct_text",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["location"]["cue_id"], "1")
        self.assertEqual(payload["spans"][1]["location"]["cue_id"], "3")
        self.assertEqual(payload["spans"][1]["location"]["start_time"], "00:00:07,000")

    def test_reordered_transcript_text_after_prior_match_does_not_steal_later_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "lesson.srt"
            converted = run_dir / "converted.md"
            source.write_text(
                "\n".join([
                    "1",
                    "00:00:01,000 --> 00:00:03,000",
                    "Host: First cue",
                    "",
                    "2",
                    "00:00:04,000 --> 00:00:06,000",
                    "Guest: Second cue",
                    "",
                    "3",
                    "00:00:07,000 --> 00:00:09,000",
                    "Host: Third cue",
                ]),
                encoding="utf-8",
            )
            converted.write_text("Host: First cue\n\nHost: Third cue\n\nGuest: Second cue\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="subtitle_transcript",
                converter="direct_text",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["location"]["cue_id"], "1")
        self.assertEqual(payload["spans"][1]["source_kind"], "converted_markdown")
        self.assertNotIn("start_time", payload["spans"][1]["location"])
        self.assertEqual(payload["spans"][2]["location"]["cue_id"], "2")
        self.assertEqual(payload["spans"][2]["location"]["start_time"], "00:00:04,000")

    def test_media_transcript_name_speakers_without_raw_cues_remain_transcript_spans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "lesson.mp3"
            converted = run_dir / "converted.md"
            source.write_bytes(b"fake media placeholder")
            converted.write_text("Alice: Hello there\n\nBob: Hi\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
                conversion_route="media_to_transcript",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="subtitle_transcript",
                converter="media_transcript",
                conversion_route="media_to_transcript",
            )

            typed_payload = json.loads(typed_nodes.read_text(encoding="utf-8"))
            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual([node["type"] for node in typed_payload["nodes"]], ["transcript_cue", "transcript_cue"])
        self.assertEqual(typed_payload["nodes"][0]["metadata"], {"cue_index": 1, "speaker": "Alice"})
        self.assertEqual(payload["spans"][0]["source_kind"], "transcript")
        self.assertEqual(payload["spans"][0]["location"]["cue_index"], 1)
        self.assertEqual(payload["spans"][0]["evidence"]["precision"], "converted_line_range")

    def test_validator_rejects_converted_line_precision_with_cue_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("Host: Welcome\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
            )
            source_spans = run_dir / "canonical_ir" / "source_spans.json"
            source_spans.write_text(
                json.dumps({
                    "schema": CANONICAL_IR_SOURCE_SPANS_SCHEMA,
                    "document_id": "doc_test",
                    "source_artifact": "converted.md",
                    "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
                    "span_count": 1,
                    "spans": [{
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
                    }],
                }),
                encoding="utf-8",
            )

            issues = validate_source_spans_artifact(
                run_dir=run_dir,
                source_spans_path=source_spans,
                typed_nodes_path=typed_nodes,
                document_id="doc_test",
                converted_path=converted,
            )

        self.assertTrue(any("transcript timing requires transcript_cue_timing precision" in issue.message for issue in issues))

    def test_validator_accepts_route_native_precision_locations(self) -> None:
        cases = [
            (
                "pdf",
                {
                    "converted_line_start": 1,
                    "converted_line_end": 1,
                    "page": 1,
                    "bbox": [0.0, 0.0, 100.0, 20.0],
                },
                "pdf_bbox",
            ),
            (
                "docx",
                {
                    "converted_line_start": 1,
                    "converted_line_end": 1,
                    "paragraph_index": 0,
                    "run_start": 0,
                    "run_end": 2,
                },
                "docx_run_range",
            ),
            (
                "pptx",
                {
                    "converted_line_start": 1,
                    "converted_line_end": 1,
                    "slide": 1,
                    "shape_id": "title-1",
                },
                "pptx_shape",
            ),
            (
                "xlsx",
                {
                    "converted_line_start": 1,
                    "converted_line_end": 1,
                    "sheet": "Sheet1",
                    "start": "A1",
                    "end": "C3",
                },
                "xlsx_cell_range",
            ),
            (
                "transcript",
                {
                    "converted_line_start": 1,
                    "converted_line_end": 1,
                    "cue_index": 1,
                    "cue_id": "cue-1",
                },
                "transcript_cue_id",
            ),
            (
                "youtube",
                {
                    "converted_line_start": 1,
                    "converted_line_end": 1,
                    "cue_id": "yt-cue-1",
                },
                "youtube_cue_id",
            ),
        ]
        for source_kind, location, precision in cases:
            with self.subTest(precision=precision):
                with tempfile.TemporaryDirectory() as tmp:
                    run_dir = Path(tmp)
                    converted = run_dir / "converted.md"
                    converted.write_text("# Native Evidence\n", encoding="utf-8")
                    typed_nodes = write_typed_nodes_artifact(
                        run_dir=run_dir,
                        document_id="doc_test",
                        converted_path=converted,
                        source_type="generic_block",
                    )
                    source_spans = run_dir / "canonical_ir" / "source_spans.json"
                    source_spans.write_text(
                        json.dumps({
                            "schema": CANONICAL_IR_SOURCE_SPANS_SCHEMA,
                            "document_id": "doc_test",
                            "source_artifact": "converted.md",
                            "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
                            "span_count": 1,
                            "spans": [{
                                "span_id": "s_000001",
                                "node_id": "n_000001",
                                "source_kind": source_kind,
                                "location": location,
                                "evidence": {
                                    "source_type": "generic_block",
                                    "converter": "test_converter",
                                    "conversion_route": "test_route",
                                    "source_kind": source_kind,
                                    "precision": precision,
                                },
                            }],
                        }),
                        encoding="utf-8",
                    )

                    issues = validate_source_spans_artifact(
                        run_dir=run_dir,
                        source_spans_path=source_spans,
                        typed_nodes_path=typed_nodes,
                        document_id="doc_test",
                        converted_path=converted,
                    )

                self.assertEqual(issues, [])

    def test_route_native_precision_rejects_mixed_location_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Native Evidence\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="pdf_like",
            )
            source_spans = run_dir / "canonical_ir" / "source_spans.json"
            source_spans.write_text(
                json.dumps({
                    "schema": CANONICAL_IR_SOURCE_SPANS_SCHEMA,
                    "document_id": "doc_test",
                    "source_artifact": "converted.md",
                    "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
                    "span_count": 1,
                    "spans": [{
                        "span_id": "s_000001",
                        "node_id": "n_000001",
                        "source_kind": "pdf",
                        "location": {
                            "converted_line_start": 1,
                            "converted_line_end": 1,
                            "page": 1,
                            "bbox": [0.0, 0.0, 100.0, 20.0],
                            "source_line_start": 1,
                            "source_line_end": 1,
                        },
                        "evidence": {
                            "source_type": "pdf_like",
                            "converter": "test_converter",
                            "conversion_route": "test_route",
                            "source_kind": "pdf",
                            "precision": "pdf_bbox",
                        },
                    }],
                }),
                encoding="utf-8",
            )

            issues = validate_source_spans_artifact(
                run_dir=run_dir,
                source_spans_path=source_spans,
                typed_nodes_path=typed_nodes,
                document_id="doc_test",
                converted_path=converted,
            )

        self.assertTrue(any("pdf_bbox precision cannot include other route location fields" in issue.message for issue in issues))

    def test_youtube_cue_id_precision_requires_youtube_source_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# YouTube Cue\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="youtube_transcript",
            )
            source_spans = run_dir / "canonical_ir" / "source_spans.json"
            source_spans.write_text(
                json.dumps({
                    "schema": CANONICAL_IR_SOURCE_SPANS_SCHEMA,
                    "document_id": "doc_test",
                    "source_artifact": "converted.md",
                    "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
                    "span_count": 1,
                    "spans": [{
                        "span_id": "s_000001",
                        "node_id": "n_000001",
                        "source_kind": "transcript",
                        "location": {
                            "converted_line_start": 1,
                            "converted_line_end": 1,
                            "cue_id": "yt-cue-1",
                        },
                        "evidence": {
                            "source_type": "youtube_transcript",
                            "converter": "test_converter",
                            "conversion_route": "youtube",
                            "source_kind": "transcript",
                            "precision": "youtube_cue_id",
                        },
                    }],
                }),
                encoding="utf-8",
            )

            issues = validate_source_spans_artifact(
                run_dir=run_dir,
                source_spans_path=source_spans,
                typed_nodes_path=typed_nodes,
                document_id="doc_test",
                converted_path=converted,
            )

        self.assertTrue(any("youtube_cue_id precision requires youtube source_kind" in issue.message for issue in issues))

    def test_pdf_bbox_precision_requires_native_pdf_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Native Evidence\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="pdf_like",
            )
            source_spans = run_dir / "canonical_ir" / "source_spans.json"
            source_spans.write_text(
                json.dumps({
                    "schema": CANONICAL_IR_SOURCE_SPANS_SCHEMA,
                    "document_id": "doc_test",
                    "source_artifact": "converted.md",
                    "typed_nodes_artifact": "canonical_ir/typed_nodes.json",
                    "span_count": 1,
                    "spans": [{
                        "span_id": "s_000001",
                        "node_id": "n_000001",
                        "source_kind": "pdf",
                        "location": {
                            "converted_line_start": 1,
                            "converted_line_end": 1,
                            "page": 1,
                        },
                        "evidence": {
                            "source_type": "pdf_like",
                            "converter": "test_converter",
                            "conversion_route": "test_route",
                            "source_kind": "pdf",
                            "precision": "pdf_bbox",
                        },
                    }],
                }),
                encoding="utf-8",
            )

            issues = validate_source_spans_artifact(
                run_dir=run_dir,
                source_spans_path=source_spans,
                typed_nodes_path=typed_nodes,
                document_id="doc_test",
                converted_path=converted,
            )

        self.assertTrue(any("pdf_bbox precision requires page and bbox" in issue.message for issue in issues))

    def test_writer_does_not_invent_pdf_bbox_without_native_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "source.pdf"
            converted = run_dir / "converted.md"
            source.write_bytes(b"%PDF placeholder")
            converted.write_text("# Extracted\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="pdf_like",
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="pdf_like",
                converter="pdf_text_layer",
                conversion_route="pdf_text_layer",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["source_kind"], "pdf")
        self.assertEqual(payload["spans"][0]["evidence"]["precision"], "converted_line_range")
        self.assertNotIn("bbox", payload["spans"][0]["location"])

    def test_writer_emits_pptx_shape_precision_from_native_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "deck.pptx"
            converted = run_dir / "converted.md"
            converted.write_text("# Slide 1: Title\n\nBody paragraph\n", encoding="utf-8")
            source.write_bytes(b"PK fake pptx placeholder")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="office_xml",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="office_xml",
                converter="office_xml",
                conversion_route="office_xml",
                native_source_spans=[
                    {
                        "converted_line_start": 1,
                        "converted_line_end": 1,
                        "precision": "pptx_shape",
                        "location": {"slide": 1, "shape_id": "title-1"},
                    },
                    {
                        "converted_line_start": 3,
                        "converted_line_end": 3,
                        "precision": "pptx_shape",
                        "location": {"slide": 1, "shape_id": "body-2"},
                    },
                ],
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))
            issues = validate_source_spans_artifact(
                run_dir=run_dir,
                source_spans_path=artifact,
                typed_nodes_path=typed_nodes,
                document_id="doc_test",
                converted_path=converted,
            )

        self.assertEqual(payload["spans"][0]["source_kind"], "pptx")
        self.assertEqual(payload["spans"][0]["evidence"]["precision"], "pptx_shape")
        self.assertEqual(payload["spans"][0]["location"]["slide"], 1)
        self.assertEqual(payload["spans"][0]["location"]["shape_id"], "title-1")
        self.assertEqual(payload["spans"][1]["evidence"]["precision"], "pptx_shape")
        self.assertEqual(payload["spans"][1]["location"]["slide"], 1)
        self.assertEqual(payload["spans"][1]["location"]["shape_id"], "body-2")
        self.assertEqual(issues, [])

    def test_canonical_ir_manifest_threads_native_source_spans_to_writer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "deck.pptx"
            converted = run_dir / "converted.md"
            converted.write_text("# Slide 1: Title\n\nBody paragraph\n", encoding="utf-8")
            source.write_bytes(b"PK fake pptx placeholder")
            (run_dir / "conversion_report.json").write_text(json.dumps({
                "converter": "office_xml",
                "converted_md": str(converted),
                "converted_bytes": converted.stat().st_size,
                "mineru_artifacts": {
                    "native_source_spans": [
                        {
                            "converted_line_start": 1,
                            "converted_line_end": 1,
                            "precision": "pptx_shape",
                            "location": {"slide": 1, "shape_id": "title-1"},
                        },
                        {
                            "converted_line_start": 3,
                            "converted_line_end": 3,
                            "precision": "pptx_shape",
                            "location": {"slide": 1, "shape_id": "body-2"},
                        },
                    ],
                },
            }), encoding="utf-8")

            write_canonical_ir_manifests(
                run_dir=run_dir,
                input_path=source,
                source_type="office_xml",
                file_hash="abc123def456",
                file_size=source.stat().st_size,
                run_id="run_test",
            )

            spans_path = run_dir / "canonical_ir" / "source_spans.json"
            typed_path = run_dir / "canonical_ir" / "typed_nodes.json"
            payload = json.loads(spans_path.read_text(encoding="utf-8"))
            issues = validate_source_spans_artifact(
                run_dir=run_dir,
                source_spans_path=spans_path,
                typed_nodes_path=typed_path,
                document_id="doc_abc123def456",
                converted_path=converted,
            )

        self.assertEqual(payload["spans"][0]["evidence"]["precision"], "pptx_shape")
        self.assertEqual(payload["spans"][0]["location"]["shape_id"], "title-1")
        self.assertEqual(payload["spans"][1]["evidence"]["precision"], "pptx_shape")
        self.assertEqual(payload["spans"][1]["location"]["shape_id"], "body-2")
        self.assertEqual(issues, [])

    def test_writer_ignores_native_evidence_when_precision_mismatches_source_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "doc.pdf"
            converted = run_dir / "converted.md"
            converted.write_text("# Title\n\nBody paragraph\n", encoding="utf-8")
            source.write_bytes(b"%PDF placeholder")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="pdf_like",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="pdf_like",
                converter="pdf_text_layer",
                conversion_route="pdf_text_layer",
                native_source_spans=[
                    {
                        "converted_line_start": 1,
                        "converted_line_end": 1,
                        "precision": "pptx_shape",
                        "location": {"slide": 1, "shape_id": "wrong-route"},
                    },
                ],
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))
            issues = validate_source_spans_artifact(
                run_dir=run_dir,
                source_spans_path=artifact,
                typed_nodes_path=typed_nodes,
                document_id="doc_test",
                converted_path=converted,
            )

        self.assertEqual(payload["spans"][0]["source_kind"], "pdf")
        self.assertEqual(payload["spans"][0]["evidence"]["precision"], "converted_line_range")
        self.assertNotIn("shape_id", payload["spans"][0]["location"])
        self.assertEqual(issues, [])

    def test_writer_keeps_converted_line_range_when_native_evidence_does_not_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "deck.pptx"
            converted = run_dir / "converted.md"
            converted.write_text("# Slide 1: Title\n", encoding="utf-8")
            source.write_bytes(b"PK placeholder")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="office_xml",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="office_xml",
                converter="office_xml",
                conversion_route="office_xml",
                native_source_spans=[
                    {
                        "converted_line_start": 99,
                        "converted_line_end": 99,
                        "precision": "pptx_shape",
                        "location": {"slide": 1, "shape_id": "no-overlap"},
                    },
                ],
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["evidence"]["precision"], "converted_line_range")
        self.assertNotIn("shape_id", payload["spans"][0]["location"])

    def test_pptx_converter_native_spans_align_with_typed_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "deck.pptx"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("ppt/slides/slide1.xml", (
                    "<p:sld xmlns:p='p' xmlns:a='a' xmlns:r='r'>"
                    "<p:cSld><p:spTree>"
                    "<p:sp><p:nvSpPr><p:cNvPr id='2' name='Title'/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
                    "<p:spPr/><p:txBody><a:p><a:r><a:t>Slide Title</a:t></a:r></a:p></p:txBody></p:sp>"
                    "<p:sp><p:nvSpPr><p:cNvPr id='3' name='Body'/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
                    "<p:spPr/><p:txBody><a:p><a:r><a:t>Body content</a:t></a:r></a:p></p:txBody></p:sp>"
                    "</p:spTree></p:cSld></p:sld>"
                ))
            markdown, _office_warnings, office_artifacts = office_xml_to_markdown(source, run_dir)
            native = office_artifacts["native_source_spans"]

            converted = run_dir / "converted.md"
            converted.write_text(markdown, encoding="utf-8")
            (run_dir / "conversion_report.json").write_text(json.dumps({
                "converter": "office_xml",
                "converted_md": str(converted),
                "converted_bytes": converted.stat().st_size,
                "mineru_artifacts": {"native_source_spans": native},
            }), encoding="utf-8")

            write_canonical_ir_manifests(
                run_dir=run_dir,
                input_path=source,
                source_type="office_xml",
                file_hash="pptxhash1234567",
                file_size=source.stat().st_size,
                run_id="run_test",
            )

            spans_path = run_dir / "canonical_ir" / "source_spans.json"
            typed_path = run_dir / "canonical_ir" / "typed_nodes.json"
            spans_payload = json.loads(spans_path.read_text(encoding="utf-8"))
            issues = validate_source_spans_artifact(
                run_dir=run_dir,
                source_spans_path=spans_path,
                typed_nodes_path=typed_path,
                document_id="doc_pptxhash1234567",
                converted_path=converted,
            )

        precisions = [span["evidence"]["precision"] for span in spans_payload["spans"]]
        shape_ids = [span["location"].get("shape_id") for span in spans_payload["spans"]]
        self.assertEqual(precisions.count("pptx_shape"), 2)
        self.assertIn("2", shape_ids)
        self.assertIn("3", shape_ids)
        self.assertEqual(issues, [])

    def test_pdf_text_layer_route_records_pdf_bbox_as_missing_native_kind(self):
        # The PDF text-layer route has no coordinates, so it emits no
        # native_source_spans. Spans stay on converted-line precision and the
        # coverage report must list pdf_bbox as a missing native kind rather
        # than letting a writer fabricate a bounding box.
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "text.pdf"
            converted = run_dir / "converted.md"
            converted.write_text(
                "<!-- page: 1 -->\n\nPDF paragraph one\n\nSecond paragraph\n",
                encoding="utf-8",
            )
            source.write_bytes(b"%PDF-")
            (run_dir / "conversion_report.json").write_text(json.dumps({
                "converter": "pdf_text_layer",
                "converted_md": str(converted),
                "converted_bytes": converted.stat().st_size,
            }), encoding="utf-8")

            write_canonical_ir_manifests(
                run_dir=run_dir,
                input_path=source,
                source_type="pdf_like",
                file_hash="pdftexthash12345",
                file_size=source.stat().st_size,
                run_id="run_test",
            )

            manifest = json.loads((run_dir / "canonical_ir" / "manifest.json").read_text(encoding="utf-8"))
            spans_payload = json.loads((run_dir / "canonical_ir" / "source_spans.json").read_text(encoding="utf-8"))

        precisions = [span["evidence"]["precision"] for span in spans_payload["spans"]]
        gap = manifest["coverage"]["report"]["gaps"]["route_native_precision"]
        self.assertTrue(all(precision == "converted_line_range" for precision in precisions))
        self.assertIn("pdf_bbox", gap["missing"])


if __name__ == "__main__":
    unittest.main()
