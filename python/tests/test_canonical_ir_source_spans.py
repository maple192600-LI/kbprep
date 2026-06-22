import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.canonical_nodes import write_typed_nodes_artifact
from kbprep_worker.canonical_spans import (
    CANONICAL_IR_SOURCE_SPANS_SCHEMA,
    validate_source_spans_artifact,
    write_source_spans_artifact,
)


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


if __name__ == "__main__":
    unittest.main()
