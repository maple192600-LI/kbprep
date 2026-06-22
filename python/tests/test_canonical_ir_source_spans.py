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


if __name__ == "__main__":
    unittest.main()
