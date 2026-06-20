import contextlib
import io
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from kbprep_worker import classify_blocks, clean_rules, converter_capabilities, detect, setup_env, split
from kbprep_worker.blockify import (
    BLOCK_TYPES,
    _build_page_map,
    _find_page_range,
    _infer_block_type,
    _line_start_offsets,
    _make_block,
    _offset_to_line,
    blockify,
)
from kbprep_worker.diagnose import format_detect
from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.feedback import command as feedback_command
from kbprep_worker.rule_loader import (
    ClassificationRuleGroup,
    CleaningRuleGroup,
    FeedbackRuleGroup,
    ImageRuleGroup,
    LoadedCleaningRules,
)
from kbprep_worker.rule_schema import ClassificationPattern, CleaningRule


def _fake_rules() -> LoadedCleaningRules:
    return LoadedCleaningRules(
        cleaning=CleaningRuleGroup(
            promotional_line_rules=(
                CleaningRule("protect-params", "protect", "literal", "参数说明", "keep params", "protect_params", "test"),
                CleaningRule("user-ad", "discard", "literal", "用户广告", "user feedback discard", "user_feedback_ad", "test"),
                CleaningRule("ad", "discard", "literal", "扫码关注", "discard cta", "cta", "test"),
                CleaningRule("review", "review", "regex", r"可能营销", "review cta", "maybe_cta", "test"),
            ),
            cta_keywords=("扫码", "入群"),
            qr_image_markers=("二维码",),
        ),
        image=ImageRuleGroup((), (), (), (), ()),
        classification=ClassificationRuleGroup(
            tutorial_indicators=("教程", "步骤"),
            knowledge_terms=("参数", "案例", "方法"),
            refund_patterns=(r"退款",),
            footer_patterns=(r"版权所有",),
            evidence_patterns=(ClassificationPattern("revenue_claim", r"收入截图"),),
            marketing_wrapper_heading_terms=("福利",),
            marketing_wrapper_passthrough_titles=(),
            marketing_wrapper_back_matter_terms=("加入",),
            marketing_wrapper_line_patterns=(r"限时领取",),
            business_method_context_terms=("增长方法",),
            transcript_filler_patterns=(r"谢谢大家",),
            protected_patterns=(ClassificationPattern("operation_step", r"^步骤\d"),),
        ),
        feedback=FeedbackRuleGroup(("保留",), ("删除",)),
        sources=("test",),
    )


class CoreHelperRound2CoverageTests(unittest.TestCase):
    def test_detect_and_capability_matrix_cover_declared_families(self):
        self.assertEqual(detect.detect_source_type("x.md"), "markdown_note")
        families = {
            "a.pdf": "pdf",
            "a.doc": "word",
            "a.pptx": "presentation",
            "a.xlsx": "spreadsheet",
            "a.epub": "ebook",
            "a.png": "image",
            "a.mp3": "audio",
            "a.mp4": "video",
            "a.srt": "subtitle_transcript",
            "a.ipynb": "notebook",
            "a.py": "code",
            "a.html": "text",
            "a.odt": "word",
            "a.unknown": "unknown",
        }
        for filename, family in families.items():
            with self.subTest(filename=filename):
                self.assertEqual(detect.detect_source_family(filename), family)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            english = root / "english.txt"
            chinese = root / "中文.txt"
            english.write_text("This is a reliable English text sample with several words.", encoding="utf-8")
            chinese.write_text("这是一个可靠的中文文本样本。", encoding="utf-8")
            self.assertEqual(detect.detect_language(str(english)), "en")
            self.assertEqual(detect.detect_language(str(chinese)), "ch")
        self.assertEqual(detect.detect_language("missing.pdf"), "en")

        rows = converter_capabilities.capability_matrix_rows()
        self.assertTrue(any(row["id"] == "pdf_diagnosis_selected" for row in rows))
        gap_report = converter_capabilities.capability_gap_report()
        self.assertGreater(gap_report["summary"]["partial"], 0)
        self.assertEqual(converter_capabilities.get_capability_for_extension(".nope")["id"], "unsupported_extension")
        self.assertEqual(converter_capabilities._default_promotion_blocker({"status": "partial"}).split()[0], "Needs")
        self.assertTrue(converter_capabilities._default_required_evidence({"status": "unsupported"}))

    def test_format_detect_text_office_media_and_ebook_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md = root / "note.md"
            md.write_text("# 标题\n\n```python\nprint(1)\n```\n\n| A | B |\n|---|---|\n�", encoding="utf-8")
            analysis = format_detect.analyze_markdown(str(md))
            self.assertEqual(analysis["heading_count"], 1)
            self.assertEqual(analysis["code_block_count"], 1)
            self.assertGreaterEqual(analysis["table_row_count"], 2)

            html = root / "page.html"
            html.write_text("<script>bad()</script><h1>标题</h1><p>正文</p>", encoding="utf-8")
            html_analysis = format_detect.analyze_markdown(str(html), detected_format="html")
            self.assertNotIn("bad", str(html_analysis["text_quality"]))

            nb = root / "bad.ipynb"
            nb.write_text("{bad", encoding="utf-8")
            self.assertEqual(format_detect.analyze_markdown(str(nb), detected_format="notebook")["text_layer_health"], "error")

            docx = root / "ok.docx"
            with zipfile.ZipFile(docx, "w") as zf:
                zf.writestr("[Content_Types].xml", "<Types/>")
            self.assertEqual(format_detect.analyze_office(str(docx), "docx")["conversion_strategy"], "office_xml")
            bad_docx = root / "bad.docx"
            bad_docx.write_text("not zip", encoding="utf-8")
            self.assertEqual(format_detect.analyze_office(str(bad_docx), "docx")["text_layer_health"], "invalid_container")
            self.assertEqual(format_detect.analyze_office(str(root / "old.doc"), "doc")["recommended_pipeline"], "legacy_office_to_pdf")  # noqa: E501
            self.assertEqual(format_detect.analyze_audio_video("a.mp3", "audio")["recommended_pipeline"], "media_transcript")
            mobi_analysis = format_detect.analyze_ebook("book.mobi", ".mobi")
            self.assertEqual(mobi_analysis["text_layer_health"], "unsupported")
            self.assertEqual(mobi_analysis["recommended_pipeline"], "unsupported")
            with patch("kbprep_worker.epub.analyze_epub", side_effect=RuntimeError("bad epub")):
                self.assertEqual(format_detect.analyze_ebook("book.epub", ".epub")["text_layer_health"], "invalid_container")

    def test_blockify_page_map_and_inference_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content_list = root / "content.json"
            text = "# 标题\n\n第一页正文\n\n第二页正文\n\n![图](a.png)\n"
            content_list.write_text(json.dumps([
                {"page_idx": 0, "text": "第一页正文"},
                {"page": 1, "text": "第二页正文"},
            ], ensure_ascii=False), encoding="utf-8")
            page_map = _build_page_map(text, {"content_list_path": str(content_list)})
            self.assertEqual(page_map[0]["page"], 0)
            self.assertEqual(_find_page_range(2, 4, page_map), (0, 1))
            offsets = _line_start_offsets(text)
            self.assertEqual(_offset_to_line(text.find("第二页"), offsets), 4)
            self.assertIsNone(_make_block(1, "   ", 0, 0, [], "hash", []))
            block = _make_block(2, "![图](a.png)", 0, 0, [], "abcdef1234567890", [], override_type=None)
            self.assertEqual(block["images"][0]["src"], "a.png")

            self.assertEqual(_infer_block_type("```python\nx\n```"), "code")
            self.assertEqual(_infer_block_type("| A | B |"), "table")
            self.assertEqual(_infer_block_type("> [!note]\n> body"), "quote")
            self.assertEqual(_infer_block_type("Step 1: do it"), "operation_step")
            self.assertEqual(set(BLOCK_TYPES), {"code", "image_evidence", "operation_step", "paragraph", "quote", "section_heading", "table"})  # noqa: E501
            blocks = blockify(text, "abcdef1234567890", {"content_list_path": str(content_list)}, str(root))
            self.assertTrue(any(item["type"] == "image_evidence" for item in blocks))

    def test_classification_cleaning_and_split_paths_with_fake_rules(self):
        rules = _fake_rules()
        blocks = [
            {"block_id": "empty", "text": "", "type": "paragraph", "status": "unclassified"},
            {"block_id": "code", "text": "```python\nx\n```", "type": "code", "status": "unclassified"},
            {"block_id": "img", "text": "![图](a.png)", "type": "image_evidence", "status": "unclassified"},
            {"block_id": "step", "text": "步骤1：配置参数", "type": "paragraph", "status": "unclassified", "heading_path": []},
            {"block_id": "ctx", "text": "案例：如果出现扫码文案，需要判断参数是否保留", "type": "paragraph", "status": "unclassified", "heading_path": []},  # noqa: E501
            {"block_id": "ad", "text": "扫码关注", "type": "paragraph", "status": "unclassified"},
            {"block_id": "evi", "text": "收入截图如下", "type": "paragraph", "status": "unclassified"},
            {"block_id": "accented_latin", "text": "café naïve résumé coöperate touché " * 3, "type": "paragraph", "status": "unclassified"},  # noqa: E501
            {"block_id": "garbled", "text": "�P�D�F� text layer " * 4, "type": "paragraph", "status": "unclassified"},
        ]
        with patch("kbprep_worker.classify_blocks.load_cleaning_rules", return_value=rules):
            classified = classify_blocks.classify_blocks(blocks)
        by_id = {block["block_id"]: block for block in classified}
        self.assertEqual(by_id["empty"]["type"], "empty")
        self.assertTrue(by_id["code"]["protected"])
        self.assertEqual(by_id["img"]["status"], "unclassified")
        self.assertEqual(by_id["step"]["type"], "operation_step")
        self.assertEqual(by_id["ctx"]["status"], "keep")
        self.assertEqual(by_id["ad"]["status"], "discard")
        self.assertEqual(by_id["evi"]["status"], "evidence")
        self.assertEqual(by_id["accented_latin"]["status"], "keep")
        self.assertEqual(by_id["accented_latin"]["type"], "paragraph")
        self.assertEqual(by_id["garbled"]["type"], "garbled_text")
        self.assertTrue(classify_blocks._matches_any_pattern("退款政策", (r"退款",)))

        clean_blocks = [
            {"block_id": "mix", "text": "正文参数说明\n扫码关注", "type": "paragraph", "status": "keep", "source_sha256": "hash"},
            {"block_id": "protect", "text": "参数说明", "type": "paragraph", "status": "keep"},
            {"block_id": "user", "text": "用户广告", "type": "paragraph", "status": "keep"},
            {"block_id": "maybe", "text": "可能营销", "type": "paragraph", "status": "keep"},
            {"block_id": "dup", "text": "重复", "type": "duplicate", "status": "keep"},
        ]
        with patch("kbprep_worker.clean_rules.load_cleaning_rules", return_value=rules):
            cleaned = clean_rules.apply_clean_rules(clean_blocks)
        clean_by_id = {block["block_id"]: block for block in cleaned}
        self.assertEqual(clean_by_id["protect"]["status"], "keep")
        self.assertTrue(clean_by_id["protect"]["protected"])
        self.assertEqual(clean_by_id["user"]["status"], "discard")
        self.assertEqual(clean_by_id["maybe"]["status"], "review")
        self.assertEqual(clean_by_id["dup"]["status"], "discard")
        self.assertTrue(any(block["block_id"].startswith("mix_promo") for block in cleaned))
        self.assertTrue(clean_rules._is_tutorial_context("1. 扫码参数说明", {"heading_path": []}, rules))
        self.assertTrue(clean_rules._has_cta_keywords("请扫码", rules))

        kept = [
            {"block_id": "h", "status": "keep", "type": "section_heading", "text": "# H", "heading_path": ["H"], "page_start": 1, "page_end": 1},  # noqa: E501
            {"block_id": "p1", "status": "keep", "type": "paragraph", "text": "A" * 1300, "heading_path": ["H"], "page_start": 1, "page_end": 1},  # noqa: E501
            {"block_id": "p2", "status": "keep", "type": "paragraph", "text": "B" * 1300, "heading_path": ["H"], "page_start": 2, "page_end": 2},  # noqa: E501
            {"block_id": "skip", "status": "discard", "type": "paragraph", "text": "drop"},
        ]
        self.assertGreaterEqual(len(split._split_pdf_like(kept)), 1)
        self.assertEqual(len(split._split_by_page_order(kept)), 2)
        markdown_chunks = split._split_markdown_note([
            {"block_id": "fm", "status": "keep", "type": "paragraph", "text": "---\ntitle: Demo\n---"},
            *kept,
        ])
        self.assertTrue(markdown_chunks[0]["text"].startswith("---\ntitle: Demo\n---"))
        self.assertGreaterEqual(len(markdown_chunks), 2)

        transcript_blocks = [
            {"block_id": "t1", "status": "keep", "type": "paragraph", "text": "[00:00] " + "A" * 1300},
            {"block_id": "t2", "status": "keep", "type": "paragraph", "text": "Speaker: " + "B" * 1300},
        ]
        transcript_chunks = split._split_transcript(transcript_blocks)
        self.assertEqual(len(transcript_chunks), 2)
        self.assertTrue(transcript_chunks[1]["text"].startswith("Speaker:"))
        self.assertEqual(split._new_chunk()["block_ids"], [])
        with tempfile.TemporaryDirectory() as tmp:
            result = split.split_into_chunks(kept, tmp, "subtitle_transcript", "abcdef", "run")
            self.assertGreater(result["chunk_count"], 0)

    def test_setup_env_and_feedback_command_paths(self):
        with patch("shutil.which", return_value="nvidia-smi"):
            self.assertTrue(setup_env.check_nvidia_driver())
        self.assertIn("import torch", setup_env._torch_probe_code())
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(["py"], 0, stdout='{"cuda_available": true, "device": "cuda", "device_name": "GPU", "vram_gb": 8, "cuda_version": "12", "version": "2"}')):  # noqa: E501
            self.assertTrue(setup_env.check_torch_cuda("py"))
            self.assertEqual(setup_env.get_gpu_info("py")["device_name"], "GPU")
            self.assertEqual(setup_env.detect_device("py"), "cuda")
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(["py"], 1, stdout="", stderr="bad\nerr")):
            self.assertFalse(setup_env.probe_torch("py")["installed"])
        with patch("kbprep_worker.setup_env.probe_torch", return_value={"cuda_available": False, "device": "cpu"}), \
            patch("kbprep_worker.setup_env.check_nvidia_driver", return_value=True):
            self.assertIn("cuda_install_skipped_device_override_cpu", setup_env.setup_gpu("py", device_override="cpu")["actions_taken"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            source = root / "source.md"
            source.write_text("正文", encoding="utf-8")
            (run_dir / "quality_report.json").write_text(json.dumps({"document_type": "course", "quality_gates": [], "strict_errors": []}), encoding="utf-8")  # noqa: E501
            (run_dir / "run_metadata.json").write_text(json.dumps({"prepare_payload": {"input_path": str(source)}}), encoding="utf-8")
            (run_dir / "discarded.md").write_text("扫码关注", encoding="utf-8")
            (run_dir / "cleaned.md").write_text("参数说明", encoding="utf-8")
            (run_dir / "review_needed.md").write_text("", encoding="utf-8")
            out = io.StringIO()
            with patch("kbprep_worker.feedback.support.load_cleaning_rules", return_value=_fake_rules()):
                with contextlib.redirect_stdout(out):
                    with self.assertRaises(EnvelopeExit):
                        feedback_command.run({
                            "run_dir": str(run_dir),
                            "feedback_text": "请删除「扫码关注」",
                            "rules_dir": str(root / "rules"),
                            "action": "discard",
                            "scope": "source_pattern",
                            "source_pattern": "source.md",
                        })
            envelope = json.loads(out.getvalue())
            self.assertTrue(envelope["ok"])
            self.assertEqual(envelope["data"]["proposal"]["scope"], "source_pattern")


if __name__ == "__main__":
    unittest.main()
