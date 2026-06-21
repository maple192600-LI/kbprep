import contextlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from kbprep_worker import prepare_batch
from kbprep_worker.blockify import blockify
from kbprep_worker.classify_blocks import classify_blocks
from kbprep_worker.clean_rules import apply_clean_rules
from kbprep_worker.document_type import classify_document_type
from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.epub import analyze_epub, convert_epub
from kbprep_worker.images import classify_images
from kbprep_worker.notebook import analyze_notebook, notebook_to_markdown
from kbprep_worker.pdf_text import _normalize_page_text
from kbprep_worker.render_outputs import render
from kbprep_worker.rule_loader import load_cleaning_rules
from kbprep_worker.split import split_into_chunks
from kbprep_worker.stages import pipeline_core


def _base_rules(marker: str = "v1") -> dict:
    return {
        "schema": "kbprep.cleaning_rules.v1",
        "keyword_sets": {
            "cta_keywords": [f"cta-{marker}"],
        },
        "rules": [],
    }


def _capture_envelope(fn, payload):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fn(payload)
    except EnvelopeExit as exc:
        return exc.code, json.loads(out.getvalue())
    raise AssertionError("worker command did not write a JSON envelope")


class CoreProcessingPathTests(unittest.TestCase):
    def test_markdown_prepare_pipeline_publishes_quality_checked_final_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            assets = root / "images"
            assets.mkdir()
            (assets / "step.png").write_bytes(b"png")
            source.write_text(
                "\n".join([
                    "# 操作教程",
                    "",
                    "步骤1：设置 threshold=0.8。",
                    "",
                    "```python",
                    "print('ok')",
                    "```",
                    "",
                    "| 字段 | 值 |",
                    "| --- | --- |",
                    "| retry_count | 3 |",
                    "",
                    "![后台截图](images/step.png)",
                    "",
                ]),
                encoding="utf-8",
            )

            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(root / "out"), "force": True, "profile": "standard"},
            )

            self.assertEqual(code, 0)
            data = envelope["data"]
            self.assertEqual(data["strict_errors"], [])
            final_md = Path(data["latest_outputs"]["final_md"])
            self.assertTrue(final_md.exists())
            self.assertIn("threshold=0.8", final_md.read_text(encoding="utf-8"))
            conversion_report = json.loads(Path(data["latest_outputs"]["conversion_report"]).read_text(encoding="utf-8"))
            self.assertEqual(conversion_report["route_decision"]["actual_route"], "direct_text")
            quality_report = json.loads(Path(data["latest_outputs"]["quality_report"]).read_text(encoding="utf-8"))
            self.assertIn("quality_issues", quality_report)
            self.assertIn("conversion_quality_gate", quality_report)
            snapshot_path = Path(data["outputs"]["cleaning_policy_snapshot"])
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            metadata = json.loads((Path(data["run_dir"]) / "run_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(quality_report["cleaning_policy_snapshot_hash"], snapshot["snapshot_hash"])
            self.assertEqual(metadata["cleaning_policy_snapshot_hash"], snapshot["snapshot_hash"])
            self.assertEqual(
                quality_report["cleaning_policy_snapshot"]["path"],
                str(snapshot_path),
            )

    def test_prepare_cache_reuse_requires_matching_policy_snapshot_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            source.write_text("# 操作教程\n\n步骤1：保留这个方法内容。\n", encoding="utf-8")
            output_root = root / "out"

            first_code, first_envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(output_root), "force": True, "profile": "standard"},
            )
            second_code, second_envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(output_root), "profile": "standard"},
            )

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertTrue(second_envelope["data"]["skipped"])
            self.assertEqual(second_envelope["data"]["run_id"], first_envelope["data"]["run_id"])
            self.assertEqual(len([path for path in (output_root / "runs").iterdir() if path.is_dir()]), 1)

    def test_prepare_cache_hit_does_not_rewrite_existing_run_artifacts_in_same_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            source.write_text("# 操作教程\n\n步骤1：保留这个方法内容。\n", encoding="utf-8")
            output_root = root / "out"

            with patch("kbprep_worker.stages.pipeline_core.time.time", return_value=1000.0):
                first_code, first_envelope = _capture_envelope(
                    pipeline_core.run,
                    {"input_path": str(source), "output_root": str(output_root), "force": True, "profile": "standard"},
                )
                first_run_dir = Path(first_envelope["data"]["run_dir"])
                tracked_files = {
                    name: (first_run_dir / name).read_bytes()
                    for name in (
                        "run_metadata.json",
                        "diagnosis_report.json",
                        "converted.md",
                        "normalized.md",
                        "blocks.jsonl",
                        "document_classification.json",
                        "cleaning_policy_snapshot.json",
                    )
                }
                second_code, second_envelope = _capture_envelope(
                    pipeline_core.run,
                    {"input_path": str(source), "output_root": str(output_root), "profile": "standard"},
                )

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertTrue(second_envelope["data"]["skipped"])
            self.assertEqual(second_envelope["data"]["run_id"], first_envelope["data"]["run_id"])
            self.assertEqual(
                tracked_files,
                {name: (first_run_dir / name).read_bytes() for name in tracked_files},
            )
            self.assertEqual(len([path for path in (output_root / "runs").iterdir() if path.is_dir()]), 1)

    def test_prepare_cache_hit_discards_distinct_probe_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            source.write_text("# 操作教程\n\n步骤1：保留这个方法内容。\n", encoding="utf-8")
            output_root = root / "out"

            first_code, first_envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(output_root), "force": True, "profile": "standard"},
            )
            second_code, second_envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(output_root), "profile": "standard"},
            )

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertTrue(second_envelope["data"]["skipped"])
            self.assertEqual(second_envelope["data"]["run_id"], first_envelope["data"]["run_id"])
            self.assertEqual(
                [path.name for path in (output_root / "runs").iterdir() if path.is_dir()],
                [first_envelope["data"]["run_id"]],
            )

    def test_prepare_does_not_reuse_legacy_run_without_policy_snapshot_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "lesson.md"
            source.write_text("# 操作教程\n\n步骤1：保留这个方法内容。\n", encoding="utf-8")
            output_root = root / "out"

            first_code, first_envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(output_root), "force": True, "profile": "standard"},
            )
            quality_path = Path(first_envelope["data"]["run_dir"]) / "quality_report.json"
            quality_report = json.loads(quality_path.read_text(encoding="utf-8"))
            quality_report.pop("cleaning_policy_snapshot_hash")
            quality_path.write_text(json.dumps(quality_report, ensure_ascii=False), encoding="utf-8")

            second_code, second_envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(output_root), "profile": "standard"},
            )

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertFalse(second_envelope["data"].get("skipped", False))
            refreshed_quality = json.loads(Path(second_envelope["data"]["latest_outputs"]["quality_report"]).read_text(encoding="utf-8"))
            self.assertIn("cleaning_policy_snapshot_hash", refreshed_quality)

    def test_prepare_reruns_when_rule_file_changes_policy_snapshot_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_root = root / "rules"
            base_rules_path = rules_root / "base" / "obvious_noise.json"
            base_rules_path.parent.mkdir(parents=True)
            base_rules_path.write_text(json.dumps(_base_rules("v1"), ensure_ascii=False), encoding="utf-8")
            source = root / "lesson.md"
            source.write_text("# 操作教程\n\n步骤1：保留这个方法内容。\n", encoding="utf-8")
            output_root = root / "out"

            with patch.dict(os.environ, {"KBPREP_RULES_ROOT": str(rules_root)}):
                load_cleaning_rules.cache_clear()
                first_code, first_envelope = _capture_envelope(
                    pipeline_core.run,
                    {"input_path": str(source), "output_root": str(output_root), "force": True, "profile": "standard"},
                )
                first_quality = json.loads(Path(first_envelope["data"]["latest_outputs"]["quality_report"]).read_text(encoding="utf-8"))
                base_rules_path.write_text(json.dumps(_base_rules("v2"), ensure_ascii=False), encoding="utf-8")
                load_cleaning_rules.cache_clear()
                second_code, second_envelope = _capture_envelope(
                    pipeline_core.run,
                    {"input_path": str(source), "output_root": str(output_root), "profile": "standard"},
                )
                second_quality = json.loads(Path(second_envelope["data"]["latest_outputs"]["quality_report"]).read_text(encoding="utf-8"))

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertFalse(second_envelope["data"].get("skipped", False))
            self.assertNotEqual(
                first_quality["cleaning_policy_snapshot_hash"],
                second_quality["cleaning_policy_snapshot_hash"],
            )

    def test_prepare_stops_before_cleanup_when_pre_clean_conversion_gate_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "garbled.txt"
            source.write_text("鐩綍 閮ㄧ讲 鏂规 " * 80, encoding="utf-8")

            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(root / "out"), "force": True, "profile": "standard"},
            )

            self.assertEqual(code, 1)
            self.assertTrue(envelope["error"]["code"].startswith("E_CONVERTED_TEXT_"))
            gate_path = Path(envelope["error"]["details"]["conversion_quality_report"])
            self.assertTrue(gate_path.exists())
            self.assertFalse((gate_path.parent / "normalized.md").exists())
            self.assertFalse((gate_path.parent / "blocks.jsonl").exists())

    def test_batch_run_samples_first_and_keeps_unsupported_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            input_dir.mkdir()
            (input_dir / "a.md").write_text("# A\n\ncontent", encoding="utf-8")
            (input_dir / "b.pdf").write_bytes(b"%PDF")
            (input_dir / "c.txt").write_text("plain text", encoding="utf-8")
            (input_dir / "clip.mp3").write_bytes(b"mp3")
            (input_dir / "old.doc").write_bytes(b"doc")
            ignored = input_dir / "node_modules"
            ignored.mkdir()
            (ignored / "ignored.md").write_text("ignored", encoding="utf-8")
            output_root = root / "batch"

            def fake_process(file_path, output_root, *_args, **_kwargs):
                out = Path(output_root)
                out.mkdir(parents=True, exist_ok=True)
                final = out / f"{file_path.stem}.cleaned.md"
                final.write_text(f"# {file_path.stem}", encoding="utf-8")
                return {
                    "ok": True,
                    "data": {
                        "run_id": file_path.stem,
                        "strict_errors": [],
                        "latest_outputs": {
                            "final_artifact_type": "markdown",
                            "final_md": str(final),
                        },
                    },
                }

            with patch.object(prepare_batch, "_process_one_file", side_effect=fake_process):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 2,
                    },
                )

            self.assertEqual(code, 0)
            data = envelope["data"]
            self.assertEqual(data["total"], 4)
            self.assertEqual(data["skipped_unsupported"], 1)
            inventory = json.loads(Path(data["batch_inventory_json"]).read_text(encoding="utf-8"))
            reasons = {entry["file"]: entry.get("reason") for entry in inventory["files"]}
            self.assertEqual(reasons["clip.mp3"], "media_binary_not_transcribed_in_v1")
            self.assertIsNone(reasons["old.doc"])
            self.assertNotIn("ignored.md", [entry["file"] for entry in inventory["files"]])

    def test_block_clean_image_split_and_render_outputs_preserve_protected_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = "\n".join([
                "# 教程",
                "",
                "步骤1：点击设置，记录 failure_reason。",
                "",
                "扫码进群领取福利",
                "",
                "```python",
                "threshold = 0.8",
                "```",
                "",
                "| 字段 | 值 |",
                "| --- | --- |",
                "| retry_count | 3 |",
                "",
                "这是一个真实案例，收入截图如下：",
                "![收入截图](images/proof.png)",
                "",
            ])
            (run_dir / "converted.md").write_text(converted, encoding="utf-8")

            blocks = blockify(converted, "abcdef1234567890", run_dir=str(run_dir))
            classify_blocks(blocks, profile="standard")
            apply_clean_rules(blocks, profile="standard")
            classify_images(blocks, str(run_dir), profile="standard")

            statuses = {block["text"]: block["status"] for block in blocks}
            self.assertEqual(statuses["扫码进群领取福利"], "discard")
            self.assertTrue(any(block["type"] == "code" and block["protected"] for block in blocks))
            self.assertTrue(any(block.get("image_type") in {"proof_screenshot", "operation_screenshot"} for block in blocks if block.get("images")))  # noqa: E501

            render(blocks, str(run_dir), "abcdef1234567890", "run123", profile="standard")
            split_result = split_into_chunks(blocks, str(run_dir), "generic_block", "abcdef1234567890", "run123")

            self.assertGreaterEqual(split_result["chunk_count"], 1)
            self.assertIn("threshold = 0.8", (run_dir / "cleaned.md").read_text(encoding="utf-8"))
            self.assertIn("扫码进群", (run_dir / "discarded.md").read_text(encoding="utf-8"))

    def test_document_type_rule_dictionaries_protect_cta_examples(self):
        for document_type in ("course", "transcript", "webpage", "interview"):
            rules = load_cleaning_rules(document_type=document_type)
            self.assertIn(f"rules/document_types/{document_type}.json", rules.sources)

        blocks = [
            {
                "block_id": "course_goal",
                "type": "paragraph",
                "status": "unclassified",
                "text": "学习目标：解释扫码海报在课程中作为反例的使用。",
                "heading_path": ["课程导入"],
            },
            {
                "block_id": "platform_rule",
                "type": "paragraph",
                "status": "unclassified",
                "text": "平台规则：不得诱导关注公众号，这类文案要作为违规案例记录。",
                "heading_path": ["平台规则"],
            },
            {
                "block_id": "case_review",
                "type": "paragraph",
                "status": "unclassified",
                "text": "案例复盘：文末引导写扫码加群会导致审核失败。",
                "heading_path": ["案例复盘"],
            },
            {
                "block_id": "pure_cta",
                "type": "paragraph",
                "status": "unclassified",
                "text": "扫码加入社群领取体验卡。",
                "heading_path": [],
            },
            {
                "block_id": "conditional_ad_cta",
                "type": "paragraph",
                "status": "unclassified",
                "text": "如果想领取体验卡，扫码进群即可。",
                "heading_path": [],
            },
            {
                "block_id": "conditional_policy_example",
                "type": "paragraph",
                "status": "unclassified",
                "text": "如果文案出现扫码入群，应该记录为违规案例和判断标准。",
                "heading_path": ["平台规则"],
            },
        ]

        classified = {block["block_id"]: block for block in classify_blocks(blocks, document_type="course")}

        self.assertEqual(classified["course_goal"]["status"], "keep")
        self.assertEqual(classified["platform_rule"]["status"], "keep")
        self.assertEqual(classified["case_review"]["status"], "keep")
        self.assertEqual(classified["pure_cta"]["status"], "discard")
        self.assertEqual(classified["pure_cta"]["type"], "marketing_cta")
        self.assertEqual(classified["conditional_ad_cta"]["status"], "discard")
        self.assertEqual(classified["conditional_ad_cta"]["type"], "marketing_cta")
        self.assertEqual(classified["conditional_policy_example"]["status"], "keep")

    def test_webpage_login_and_registration_steps_are_kept_as_body_content(self):
        blocks = [
            {
                "block_id": "login_step",
                "type": "paragraph",
                "status": "unclassified",
                "text": "输入邮箱和密码完成登录。",
                "heading_path": ["登录"],
            },
            {
                "block_id": "registration_step",
                "type": "paragraph",
                "status": "unclassified",
                "text": "填写邮箱并提交验证码完成注册。",
                "heading_path": ["注册"],
            },
        ]

        classified = {block["block_id"]: block for block in classify_blocks(blocks, document_type="webpage")}

        self.assertEqual(classified["login_step"]["status"], "keep")
        self.assertEqual(classified["registration_step"]["status"], "keep")

    def test_large_render_outputs_write_parts_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            blocks = []
            for idx in range(10):
                blocks.append({
                    "block_id": f"h{idx}",
                    "type": "section_heading",
                    "text": f"# Chapter {idx}",
                    "status": "keep",
                    "heading_path": [f"Chapter {idx}"],
                })
                blocks.append({
                    "block_id": f"p{idx}",
                    "type": "paragraph",
                    "text": ("正文内容 " * 900).strip(),
                    "status": "keep",
                    "heading_path": [f"Chapter {idx}"],
                })

            render(blocks, str(run_dir), "abcdef1234567890", "run123", profile="standard")

            manifest = json.loads((run_dir / "parts" / "parts_manifest.json").read_text(encoding="utf-8"))
            self.assertGreater(len(manifest), 1)
            self.assertTrue((run_dir / "parts" / "part_001.md").exists())

    def test_epub_notebook_pdf_and_document_type_helpers_preserve_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epub_path = root / "book.epub"
            with zipfile.ZipFile(epub_path, "w") as zf:
                zf.writestr(
                    "META-INF/container.xml",
                    """<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>""",
                )
                zf.writestr(
                    "OEBPS/content.opf",
                    """<package><manifest><item id="c1" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/></spine></package>""",  # noqa: E501
                )
                zf.writestr(
                    "OEBPS/chapter.xhtml",
                    """<html><body><h1>第一章</h1><p>步骤：保留链接 <a href="https://example.com">工具</a></p><ul><li>要点</li></ul><img src="images/step.png" alt="截图"/></body></html>""",  # noqa: E501
                )
                zf.writestr("OEBPS/images/step.png", b"png")
            output_md = root / "book.md"
            artifacts, warnings = convert_epub(epub_path, output_md, root / "run")

            self.assertEqual(warnings, [])
            self.assertIn("# 第一章", output_md.read_text(encoding="utf-8"))
            self.assertEqual(artifacts["epub_image_assets"]["copied_count"], 1)
            self.assertEqual(analyze_epub(str(epub_path))["conversion_strategy"], "epub_xhtml")

            notebook_path = root / "analysis.ipynb"
            notebook_path.write_text(
                json.dumps({
                    "metadata": {"kernelspec": {"language": "python"}},
                    "cells": [
                        {"cell_type": "markdown", "source": ["# 分析\n"]},
                        {
                            "cell_type": "code",
                            "source": ["print('ok')"],
                            "outputs": [{"output_type": "stream", "text": ["ok\n"]}],
                        },
                    ],
                }),
                encoding="utf-8",
            )
            notebook_md = notebook_to_markdown(notebook_path)
            self.assertIn("```python", notebook_md)
            self.assertEqual(analyze_notebook(notebook_path)["code_cell_count"], 1)

            self.assertEqual(
                _normalize_page_text("这是一个超过二十个字的长段落用于测试硬换行合并\n继续说明参数\n\n1. 保留步骤"),
                "这是一个超过二十个字的长段落用于测试硬换行合并继续说明参数\n\n1. 保留步骤",
            )
            classified = classify_document_type("课程教程\n步骤1：打开工具\n案例复盘", source_type="markdown_note")
            self.assertIn(classified["document_type"], {"course", "code", "unknown"})


if __name__ == "__main__":
    unittest.main()
