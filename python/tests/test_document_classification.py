import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

from kbprep_worker.document_type import build_document_classification_artifact, classify_document_type
from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.stages import pipeline_core


def _capture_envelope(fn: Callable[[dict[str, Any]], None], payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fn(payload)
    except EnvelopeExit as exc:
        return exc.code, json.loads(out.getvalue())
    raise AssertionError("worker command did not write a JSON envelope")


class DocumentClassificationTests(unittest.TestCase):
    def test_classification_artifact_exposes_candidates_and_evidence(self) -> None:
        text = "# 第 1 课\n\n学习目标：掌握配置步骤。\n\n练习：设置 threshold=0.8。\n"
        classification = classify_document_type(text, source_type="markdown_note", diagnosis={})

        artifact = build_document_classification_artifact(
            text=text,
            source_type="markdown_note",
            diagnosis={},
            classification=classification,
        )

        self.assertEqual(artifact["schema"], "kbprep.document_classification.v1")
        self.assertEqual(artifact["status"], "complete")
        self.assertEqual(artifact["document_type"], "course")
        self.assertTrue(artifact["usable_for_policy"])
        self.assertEqual(artifact["candidates"][0]["document_type"], "course")
        self.assertGreater(artifact["evidence"]["heading_count"], 0)
        self.assertIn("rules/base/document_type_signals.json", artifact["evidence"]["signal_source"])

    def test_classification_artifact_marks_unknown_as_not_usable_for_policy(self) -> None:
        text = "只有一段普通文字，没有稳定的类型线索。"
        classification = classify_document_type(text, source_type="markdown_note", diagnosis={})

        artifact = build_document_classification_artifact(
            text=text,
            source_type="markdown_note",
            diagnosis={},
            classification=classification,
        )

        self.assertEqual(artifact["document_type"], "unknown")
        self.assertFalse(artifact["usable_for_policy"])
        self.assertIn("insufficient_reason", artifact)

    def test_classification_artifact_covers_report_webpage_and_code_signals(self) -> None:
        cases = [
            ("# 摘要\n\n本报告说明样本量、趋势和结论。", {}, "report"),
            ("<nav>首页</nav><main>privacy terms cookie</main>", {"detected_format": "html"}, "webpage"),
            ("```python\nimport json\nprint(json.dumps({}))\n```", {"detected_format": "code"}, "code"),
        ]
        for text, diagnosis, expected in cases:
            with self.subTest(expected=expected):
                classification = classify_document_type(text, source_type="markdown_note", diagnosis=diagnosis)
                artifact = build_document_classification_artifact(
                    text=text,
                    source_type="markdown_note",
                    diagnosis=diagnosis,
                    classification=classification,
                )
                self.assertEqual(artifact["document_type"], expected)
                self.assertEqual(artifact["candidates"][0]["document_type"], expected)

    def test_classification_artifact_exposes_content_form_traits_and_version(self) -> None:
        text = "# 第 1 课\n\n学习目标：掌握配置步骤。\n\n练习：设置 threshold=0.8。\n"
        artifact = build_document_classification_artifact(
            text=text,
            source_type="markdown_note",
            diagnosis={},
        )

        self.assertIn(artifact["content_form"], {"prose", "code", "table_heavy", "transcript", "outline", "mixed"})
        self.assertIsInstance(artifact["content_traits"], dict)
        self.assertTrue(
            set(artifact["content_traits"]).issuperset(
                {
                    "has_headings",
                    "has_code_blocks",
                    "has_tables",
                    "has_timestamps",
                    "has_links",
                    "heading_density",
                    "line_count",
                }
            )
        )
        self.assertEqual(artifact["classifier_version"], "1.0")

    def test_classification_content_form_detects_code_heavy(self) -> None:
        text = "```python\nimport os\nprint(os.getcwd())\n```\n\n```js\nconsole.log(1)\n```\n"
        artifact = build_document_classification_artifact(
            text=text,
            source_type="markdown_note",
            diagnosis={},
        )

        self.assertEqual(artifact["content_form"], "code")
        self.assertTrue(artifact["content_traits"]["has_code_blocks"])

    def test_classification_content_form_detects_table_heavy(self) -> None:
        text = "\n".join("| a | b |" for _ in range(8)) + "\n"
        artifact = build_document_classification_artifact(
            text=text,
            source_type="markdown_note",
            diagnosis={},
        )

        self.assertEqual(artifact["content_form"], "table_heavy")
        self.assertTrue(artifact["content_traits"]["has_tables"])

    def test_classification_content_form_detects_transcript(self) -> None:
        text = "00:15 第一句内容\n00:30 第二句内容\n01:00 第三句内容\n"
        artifact = build_document_classification_artifact(
            text=text,
            source_type="markdown_note",
            diagnosis={},
        )

        self.assertEqual(artifact["content_form"], "transcript")
        self.assertTrue(artifact["content_traits"]["has_timestamps"])

    def test_classification_content_form_detects_outline(self) -> None:
        text = "# A\n# B\n# C\nbody one\nbody two\nbody three\nbody four\nbody five\n"
        artifact = build_document_classification_artifact(
            text=text,
            source_type="markdown_note",
            diagnosis={},
        )

        self.assertEqual(artifact["content_form"], "outline")
        self.assertTrue(artifact["content_traits"]["has_headings"])

    def test_classification_content_form_detects_prose(self) -> None:
        text = "这是一段普通文字。\n第二行继续叙述。\n第三行结束。\n"
        artifact = build_document_classification_artifact(
            text=text,
            source_type="markdown_note",
            diagnosis={},
        )

        self.assertEqual(artifact["content_form"], "prose")

    def test_classification_content_form_falls_back_to_mixed_for_short_text(self) -> None:
        text = "短文本\n二行\n"
        artifact = build_document_classification_artifact(
            text=text,
            source_type="markdown_note",
            diagnosis={},
        )

        self.assertEqual(artifact["content_form"], "mixed")

    def test_prepare_writes_document_classification_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            source.write_text("# 第 1 课\n\n学习目标：掌握配置步骤。\n\n练习：设置 threshold=0.8。\n", encoding="utf-8")

            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(root / "out"), "force": True, "profile": "standard"},
            )

            self.assertEqual(code, 0)
            run_dir = Path(envelope["data"]["run_dir"])
            artifact_path = run_dir / "document_classification.json"
            run_metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

            self.assertTrue(artifact_path.exists())
            self.assertEqual(artifact["schema"], "kbprep.document_classification.v1")
            self.assertEqual(artifact["document_type"], "course")
            self.assertEqual(run_metadata["document_classification"], str(artifact_path))
            self.assertEqual(envelope["data"]["outputs"]["document_classification"], str(artifact_path))


if __name__ == "__main__":
    unittest.main()
