import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kbprep_worker.feedback import dictionary_suggestions, promotion_history, rerun_verification
from kbprep_worker.obsidian_kb import body_notes, policy, signals


class ObsidianRound2CoverageTests(unittest.TestCase):
    def test_policy_and_renderer_keep_traceable_vault_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "images").mkdir()
            (run_dir / "images" / "flow.svg").write_text("<svg viewBox='0 0 10 10'></svg>", encoding="utf-8")
            for name in ["quality_report.json", "conversion_report.json", "audit.md"]:
                (run_dir / name).write_text(json.dumps({"name": name}, ensure_ascii=False), encoding="utf-8")
            (run_dir / "quality_gates").mkdir()
            (run_dir / "quality_gates" / "retention.json").write_text("{}", encoding="utf-8")

            blocks = [
                {"block_id": "h1", "type": "section_heading", "status": "keep", "text": "# 方法流程"},
                {"block_id": "b1", "type": "paragraph", "status": "keep", "text": "步骤1：设置参数，并记录证据。"},
                {
                    "block_id": "svg",
                    "type": "image_evidence",
                    "status": "keep",
                    "text": "![流程图](images/flow.svg)",
                    "images": [{"src": "images/flow.svg"}],
                    "heading_path": ["方法流程"],
                },
                {"block_id": "page", "type": "paragraph", "status": "keep", "text": "<!-- page: 3 -->"},
                {"block_id": "ad", "type": "section_heading", "status": "keep", "text": "## 写在最后"},
                {"block_id": "review", "type": "paragraph", "status": "review", "text": "疑似边界内容"},
                {"block_id": "discard", "type": "cta", "status": "discard", "text": "扫码关注"},
            ]

            curated = policy.apply_curated_obsidian_policy(blocks, template_name="obsidian_generic")
            self.assertEqual(curated[2]["type"], "diagram")
            self.assertEqual(curated[3]["status"], "discard")
            self.assertEqual(curated[4]["type"], "marketing_wrapper")

            body_notes.render_obsidian_vault(
                curated,
                str(run_dir),
                source_title="课程 A",
                source_hash="abc123",
                run_id="run-1",
                profile="curated_obsidian_kb",
                template_name="obsidian_generic",
            )

            vault = run_dir / "obsidian"
            complete_files = list((vault / "Notes").glob("*.md"))
            self.assertTrue(complete_files)
            complete_text = (vault / "课程 A.md").read_text(encoding="utf-8")
            self.assertIn("步骤1", complete_text)
            self.assertNotIn("<!-- page: 3 -->", complete_text)
            index_text = (vault / "00-索引.md").read_text(encoding="utf-8")
            self.assertIn("[[_audit/cleaning-report|清洗报告]]", index_text)
            self.assertTrue((vault / "images" / "flow.svg").exists())
            self.assertTrue((vault / "_audit" / "quality_report.json").exists())
            self.assertTrue((vault / "_audit" / "quality_gates" / "retention.json").exists())
            source_map_lines = (vault / "_audit" / "source-map.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertTrue(any('"block_id": "b1"' in line for line in source_map_lines))

    def test_english_obsidian_output_uses_english_interface_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            blocks = [
                {"block_id": "h1", "type": "section_heading", "status": "keep", "text": "# Operating Model"},
                {"block_id": "b1", "type": "paragraph", "status": "keep", "text": "Set the threshold and review evidence."},
                {"block_id": "discard", "type": "cta", "status": "discard", "text": "Subscribe now"},
            ]

            body_notes.render_obsidian_vault(
                blocks,
                str(run_dir),
                source_title="Operations Manual",
                source_hash="abc123",
                run_id="run-1",
                profile="curated_obsidian_kb",
                template_name="obsidian_generic",
            )

            vault = run_dir / "obsidian"
            index_text = (vault / "00-索引.md").read_text(encoding="utf-8")
            report_text = (vault / "_audit" / "cleaning-report.md").read_text(encoding="utf-8")

            self.assertIn("[[_audit/cleaning-report|Cleaning report]]", index_text)
            self.assertIn("## Output principles", report_text)
            self.assertIn("- Kept blocks: 2", report_text)
            self.assertNotIn("清洗报告", index_text)
            self.assertNotIn("输出原则", report_text)

    def test_english_obsidian_duplicate_title_suffix_is_english(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            blocks = [
                {"block_id": "b1", "type": "paragraph", "status": "keep", "text": "Evidence stays traceable."},
            ]

            body_notes.render_obsidian_vault(
                blocks,
                str(run_dir),
                source_title="Notes",
                source_hash="abc123",
                run_id="run-1",
                profile="curated_obsidian_kb",
                template_name="obsidian_generic",
            )

            vault = run_dir / "obsidian"
            self.assertTrue((vault / "Notes-Complete body.md").exists())
            self.assertFalse((vault / "Notes-完整正文.md").exists())

    def test_signal_helpers_cover_marketing_toc_and_slide_cases(self):
        ctx = signals.ObsidianContext(
            template_name="test",
            template=type(
                "Template",
                (),
                {
                    "categories": ("Notes",),
                    "default_category": "Notes",
                    "method_category": "Notes",
                    "cognition_category": "Notes",
                    "case_category": "Notes",
                    "social_profile_labels": ("小红书", "公众号"),
                    "social_profile_platforms": ("微信",),
                    "provenance_terms": ("来源",),
                    "author_bio_terms": ("作者简介",),
                    "bio_role_terms": ("讲师", "创始人"),
                    "author_credential_terms": ("博士",),
                    "knowledge_terms": ("步骤", "参数", "案例"),
                    "case_terms": ("案例",),
                    "method_terms": ("方法",),
                    "cognition_terms": ("认知",),
                    "packaging_heading_terms": ("写在最后",),
                    "packaging_heading_regexes": (r"^版权.*$",),
                    "brand_heading_replacements": (),
                    "layout_table_terms": ("目录",),
                    "brand_program_packaging_terms": ("训练营报名",),
                    "translator_back_matter_terms": ("译后记", "本译本仅供", "交流群"),
                },
            )(),
        )

        self.assertEqual(signals._slide_chapter_divider_title("Chapter 2\n增长方法\n12"), "增长方法")
        self.assertIn("## 增长方法", signals._curated_slide_chapter_body("Chapter 2\n增长方法\n正文\n12", "增长方法"))
        self.assertTrue(signals._is_visual_chapter_separator("=== 第三章 ==="))
        self.assertTrue(signals._is_packaging_heading("## 写在最后", ctx))
        self.assertTrue(signals._is_noise_heading("## 一", ctx))
        self.assertTrue(signals._is_author_intro("作者简介：讲师，创始人", ctx))
        self.assertFalse(signals._is_author_intro("讲师，创始人：步骤和参数说明", ctx))
        self.assertTrue(signals._is_author_card_line("@teacher_01", ctx))
        self.assertTrue(signals._is_layout_table_artifact("| 目录 |||\n| 09:30 |||", ctx))
        self.assertTrue(signals._is_brand_program_packaging("训练营报名入口", ctx))
        self.assertTrue(signals._is_toc_like("第一章: 方法  1\n第二章: 案例  2"))
        block = {"status": "keep", "type": "paragraph", "text": "x"}
        signals._discard(block, "noise", "drop_reason", 0.9)
        self.assertEqual(block["status"], "discard")
        signals._append_tag(block, "drop_reason")
        self.assertEqual(block["risk_tags"].count("drop_reason"), 1)


class FeedbackRound2CoverageTests(unittest.TestCase):
    def _jsonl(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    def test_dictionary_suggestion_and_validation_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp) / "user"
            rows = [
                {"id": "a", "document_type": "course", "action": "discard", "match": "literal", "pattern": "扫码", "reason": "CTA", "examples": ["扫码"]},  # noqa: E501
                {"id": "b", "document_type": "course", "action": "discard", "match": "literal", "pattern": "扫码", "reason": "duplicate"},
                {"id": "c", "artifact_context": {"document_type": "course"}, "action": "discard", "match": "regex", "pattern": "关注.+公众号"},  # noqa: E501
                {"id": "d", "document_type": "course", "action": "protect", "match": "literal", "pattern": "参数"},
            ]
            self._jsonl(rules_dir / "accepted_rules.jsonl", rows)
            self._jsonl(rules_dir / "rejected_rules.jsonl", [
                {"document_type": "course", "action": "discard", "match": "literal", "pattern": "已拒绝"},
            ])
            captured: dict = {}
            with patch("kbprep_worker.feedback.dictionary_suggestions.ok", side_effect=lambda data=None: captured.update(data or {})):
                dictionary_suggestions._suggest_dictionary_updates({"rules_dir": str(rules_dir), "min_feedback_count": 2})
            report = captured["suggestions"]
            self.assertEqual(report["suggestion_count"], 1)
            suggestion = report["suggestions"][0]
            self.assertEqual(suggestion["feedback_count"], 2)
            validation = dictionary_suggestions._validate_dictionary_suggestion(suggestion, "memory")
            self.assertEqual(len(validation["proposed_rules"]), 2)
            self.assertIn("learned-course", dictionary_suggestions._promoted_cleaning_rule("course", validation["proposed_rules"][0])["id"])
            self.assertIsNone(dictionary_suggestions._feedback_cluster_key({"action": "discard"}))
            self.assertEqual(dictionary_suggestions._rule_id("A B/中文"), "a-b-中文")

    def test_promotion_history_and_rerun_effect_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_rules_dir = root / "rules"
            history_path = target_rules_dir / "promotion_history.jsonl"
            self._jsonl(history_path, [
                {
                    "schema": "kbprep.dictionary_promotion_history.v1",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "document_type": "course",
                    "regression_verification": {
                        "status": "failed",
                        "reason": "strict errors",
                        "samples": [{"ok": False, "worker_error": {"code": "E_QA_PROTECTED_CONTENT_LOST"}}],
                    },
                },
                {
                    "schema": "kbprep.dictionary_promotion_resolution.v1",
                    "created_at": "2026-01-02T00:00:00+00:00",
                    "document_type": "course",
                    "resolved_failed_promotions": 1,
                    "regression_verification": {"status": "passed"},
                },
            ])
            risk = promotion_history._promotion_history_risk(target_rules_dir=target_rules_dir, document_type="course")
            self.assertEqual(risk["status"], "clear")
            summary = promotion_history._promotion_history_document_summary(
                "course",
                promotion_history._read_jsonl(history_path),
            )
            self.assertEqual(summary["latest_status"], "resolved")
            self.assertEqual(promotion_history._positive_int_or_zero("-1"), 0)

            cleaned = root / "cleaned.md"
            cleaned.write_text("保留参数，扫码已经移除", encoding="utf-8")
            sample = {"cleaned_md": str(cleaned)}
            effects = rerun_verification._verify_promoted_rules_after_rerun(
                [
                    {"id": "discard", "action": "discard", "match": "literal", "pattern": "关注公众号"},
                    {"id": "protect", "action": "protect", "match": "literal", "pattern": "参数"},
                    {"id": "review", "action": "review", "match": "literal", "pattern": "扫码"},
                ],
                sample,
            )
            self.assertTrue(effects["ok"])
            accepted_effect = rerun_verification._verify_rule_effect_after_rerun(
                {"action": "discard", "match": "literal", "pattern": "关注公众号"},
                sample,
            )
            self.assertTrue(accepted_effect["ok"])

    def test_rerun_plans_parse_existing_metadata_and_worker_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_root = root / "out"
            run_dir = output_root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            source = root / "source.md"
            source.write_text("正文", encoding="utf-8")
            (run_dir / "run_metadata.json").write_text(
                json.dumps({"prepare_payload": {"input_path": str(source), "output_root": str(output_root), "profile": "standard"}}),
                encoding="utf-8",
            )
            (run_dir / "quality_report.json").write_text(json.dumps({"profile": "obsidian_kb"}), encoding="utf-8")

            plan = rerun_verification._rerun_plan_from_run_dir(run_dir)
            self.assertTrue(plan["ok"])
            self.assertEqual(plan["profile"], "standard")
            self.assertEqual(
                rerun_verification._parse_worker_envelope("noise\n{\"ok\": true, \"data\": {}}\n")["ok"],
                True,
            )
            self.assertFalse(rerun_verification._parse_worker_envelope("not json")["ok"])
            suggestion = {"proposed_rules": [{"created_from_run": str(run_dir)}, {"created_from_run": str(run_dir)}]}
            self.assertEqual(len(rerun_verification._representative_run_dirs(suggestion, {})), 1)


if __name__ == "__main__":
    unittest.main()
