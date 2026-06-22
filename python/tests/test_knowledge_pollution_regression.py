import json
import os
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from kbprep_worker.classify_blocks import classify_blocks
from kbprep_worker.clean_rules import apply_clean_rules
from kbprep_worker.obsidian_kb import apply_curated_obsidian_policy, complete_body_filename
from kbprep_worker.obsidian_template import load_obsidian_template
from kbprep_worker.rule_loader import load_cleaning_rules


class KnowledgePollutionRegressionTests(unittest.TestCase):
    def tearDown(self) -> None:
        load_cleaning_rules.cache_clear()
        load_obsidian_template.cache_clear()

    def test_cta_phrase_inside_method_instruction_is_kept(self):
        blocks = [{
            "block_id": "b_method",
            "type": "paragraph",
            "text": "步骤1：在文章结尾加入“扫码入群领取体验卡”作为测试文案，并记录转化率和失败原因。",
            "heading_path": ["用户运营", "私域转化方法"],
        }]

        classified = classify_blocks(blocks, profile="curated_obsidian_kb")

        self.assertEqual(classified[0]["status"], "keep")
        self.assertTrue(classified[0].get("protected"))
        self.assertIn(classified[0]["type"], {"case_step", "operation_step"})

    def test_report_wrapper_noise_is_removed_without_losing_business_methods(self) -> None:
        blocks = [
            {
                "block_id": "wrapper_offer",
                "type": "paragraph",
                "status": "keep",
                "text": "ExampleCommunityPrep：和 30000+ 实战派同行一起学习",
                "heading_path": ["封面"],
            },
            {
                "block_id": "author_heading",
                "type": "section_heading",
                "status": "keep",
                "text": "## @ExampleAuthor：",
                "heading_path": ["案例"],
            },
            {
                "block_id": "author_intro",
                "type": "paragraph",
                "status": "keep",
                "text": "大家好，我是ExampleAuthor，ExampleTool 创始人，今天分享我的经历。",
                "heading_path": ["案例"],
            },
            {
                "block_id": "business_method",
                "type": "paragraph",
                "status": "keep",
                "text": "创始人亲自跑一遍业务流程，记录所有节点和操作。",
                "heading_path": ["方法"],
            },
            {
                "block_id": "community_method",
                "type": "paragraph",
                "status": "keep",
                "text": "案例复盘：社群不是目标，用户留存指标才是判断标准。",
                "heading_path": ["案例复盘"],
            },
            {
                "block_id": "prompt_method",
                "type": "paragraph",
                "status": "keep",
                "text": "步骤1：用 AI 拆解作者介绍，识别哪些是营销包装。",
                "heading_path": ["操作步骤"],
            },
        ]

        cleaned = apply_clean_rules(blocks, profile="standard", document_type="report")
        statuses = {block["block_id"]: block["status"] for block in cleaned}

        self.assertEqual(statuses["wrapper_offer"], "discard")
        self.assertEqual(statuses["author_heading"], "discard")
        self.assertEqual(statuses["author_intro"], "discard")
        self.assertEqual(statuses["business_method"], "keep")
        self.assertEqual(statuses["community_method"], "keep")
        self.assertEqual(statuses["prompt_method"], "keep")

    def test_public_rules_do_not_ship_private_packaging_titles(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _project_root_env(Path(tmp)):
                load_cleaning_rules.cache_clear()
                rules = load_cleaning_rules(profile="curated_obsidian_kb")

        self.assertNotIn("ExampleCourse", rules.marketing_wrapper_passthrough_titles)

    def test_private_packaging_title_passthrough_is_loaded_from_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_private_cleaning_template(root)
            with _project_root_env(root):
                load_cleaning_rules.cache_clear()
                rules = load_cleaning_rules(profile="curated_obsidian_kb")

        self.assertIn("ExampleCourse", rules.marketing_wrapper_passthrough_titles)

        blocks = [{
            "block_id": "title",
            "type": "paragraph",
            "text": "# ExampleCourse",
            "heading_path": ["ExampleCourse"],
        }]
        with _project_root_env(root):
            load_cleaning_rules.cache_clear()
            classified = classify_blocks(blocks, profile="curated_obsidian_kb")

        self.assertEqual(classified[0]["status"], "keep")

    def test_obsidian_templates_do_not_leak_between_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_private_obsidian_template(root)
            course_blocks = [{
                "block_id": "course_heading",
                "type": "section_heading",
                "status": "keep",
                "text": "# ExampleCommunityPrep如何用AI赋能ExampleMember",
            }]
            generic_blocks = [{
                "block_id": "generic_heading",
                "type": "section_heading",
                "status": "keep",
                "text": "# ExampleCommunityPrep如何用AI赋能ExampleMember",
            }]

            with _project_root_env(root):
                load_obsidian_template.cache_clear()
                course_result = apply_curated_obsidian_policy(course_blocks, template_name="obsidian_course_kb")
                generic_result = apply_curated_obsidian_policy(generic_blocks, template_name="obsidian_generic")
                course_filename = complete_body_filename("认知", template_name="obsidian_course_kb")
                generic_filename = complete_body_filename("认知", template_name="obsidian_generic")

        self.assertEqual(course_result[0].get("curated_text"), "# 如何用AI赋能")
        self.assertIsNone(generic_result[0].get("curated_text"))
        self.assertEqual(course_filename, "认知-完整正文.md")
        self.assertEqual(generic_filename, "认知.md")


@contextmanager
def _project_root_env(root: Path) -> Iterator[None]:
    old_project_root = os.environ.get("KBPREP_PROJECT_ROOT")
    old_user_rules_dir = os.environ.get("KBPREP_USER_RULES_DIR")
    os.environ["KBPREP_PROJECT_ROOT"] = str(root)
    os.environ.pop("KBPREP_USER_RULES_DIR", None)
    try:
        yield
    finally:
        if old_project_root is None:
            os.environ.pop("KBPREP_PROJECT_ROOT", None)
        else:
            os.environ["KBPREP_PROJECT_ROOT"] = old_project_root
        if old_user_rules_dir is None:
            os.environ.pop("KBPREP_USER_RULES_DIR", None)
        else:
            os.environ["KBPREP_USER_RULES_DIR"] = old_user_rules_dir


def _write_private_cleaning_template(root: Path) -> None:
    template_dir = root / ".kbprep" / "rules" / "templates"
    template_dir.mkdir(parents=True)
    (template_dir / "self_media_course.json").write_text(
        json.dumps(_private_cleaning_template(), ensure_ascii=False),
        encoding="utf-8",
    )


def _write_private_obsidian_template(root: Path) -> None:
    template_dir = root / ".kbprep" / "rules" / "templates"
    template_dir.mkdir(parents=True)
    (template_dir / "obsidian_course_kb.json").write_text(
        json.dumps(_private_obsidian_template(), ensure_ascii=False),
        encoding="utf-8",
    )


def _private_cleaning_template() -> dict[str, object]:
    return {
        "schema": "kbprep.cleaning_rules.v1",
        "description": "test private course cleanup template",
        "rules": [],
        "keyword_sets": {
            "marketing_wrapper_passthrough_titles": ["ExampleCourse", "《ExampleCourse》"],
        },
    }


def _private_obsidian_template() -> dict[str, object]:
    return {
        "schema": "kbprep.obsidian_template.v1",
        "description": "test private course obsidian template",
        "categories": ["认知", "方法", "案例"],
        "default_category": "认知",
        "method_category": "方法",
        "cognition_category": "认知",
        "case_category": "案例",
        "social_profile_labels": [],
        "social_profile_platforms": [],
        "provenance_terms": [],
        "author_bio_terms": [],
        "bio_role_terms": [],
        "author_credential_terms": [],
        "knowledge_terms": [],
        "case_terms": [],
        "method_terms": [],
        "cognition_terms": [],
        "packaging_heading_terms": [],
        "packaging_heading_regexes": [],
        "brand_heading_replacements": [["ExampleCommunityPrep", ""], ["ExampleMember", ""]],
        "layout_table_terms": [],
        "brand_program_packaging_terms": [],
        "translator_back_matter_terms": [],
    }


if __name__ == "__main__":
    unittest.main()
