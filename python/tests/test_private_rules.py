import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from kbprep_worker.cleanup import _delete_standard_artifacts
from kbprep_worker.obsidian_template import load_obsidian_template
from kbprep_worker.rule_loader import load_cleaning_rules


@contextmanager
def _cwd(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


@contextmanager
def _env_var(name: str, value: str):
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


class PrivateRuleTests(unittest.TestCase):
    def tearDown(self):
        load_cleaning_rules.cache_clear()
        load_obsidian_template.cache_clear()

    def test_project_private_obsidian_template_overrides_public_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template_dir = root / ".kbprep" / "rules" / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "obsidian_course_kb.json").write_text(
                json.dumps(_minimal_obsidian_template(["Local"], "Local"), ensure_ascii=False),
                encoding="utf-8",
            )
            with _cwd(root):
                load_obsidian_template.cache_clear()
                template = load_obsidian_template("obsidian_course_kb")

        self.assertEqual(template.categories, ("Local",))
        self.assertEqual(template.source, ".kbprep/rules/templates/obsidian_course_kb.json")

    def test_project_root_env_keeps_batch_children_on_private_rules_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child_cwd = root / "python"
            child_cwd.mkdir()
            template_dir = root / ".kbprep" / "rules" / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "obsidian_course_kb.json").write_text(
                json.dumps(_minimal_obsidian_template(["Batch"], "Batch"), ensure_ascii=False),
                encoding="utf-8",
            )

            with _cwd(child_cwd), _env_var("KBPREP_PROJECT_ROOT", str(root)):
                load_obsidian_template.cache_clear()
                template = load_obsidian_template("obsidian_course_kb")

        self.assertEqual(template.categories, ("Batch",))
        self.assertEqual(template.source, ".kbprep/rules/templates/obsidian_course_kb.json")

    def test_missing_curated_obsidian_template_explains_private_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                load_obsidian_template.cache_clear()
                with self.assertRaises(FileNotFoundError) as raised:
                    load_obsidian_template("obsidian_course_kb")

        message = str(raised.exception)
        self.assertIn(".kbprep/rules/templates/obsidian_course_kb.json", message)
        self.assertIn("obsidian_kb", message)

    def test_missing_curated_template_uses_project_root_env_in_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child_cwd = root / "python"
            child_cwd.mkdir()
            with _cwd(child_cwd), _env_var("KBPREP_PROJECT_ROOT", str(root)):
                load_obsidian_template.cache_clear()
                with self.assertRaises(FileNotFoundError) as raised:
                    load_obsidian_template("obsidian_course_kb")

        message = str(raised.exception)
        self.assertIn(str(root / ".kbprep" / "rules" / "templates" / "obsidian_course_kb.json"), message)
        self.assertNotIn(str(child_cwd / ".kbprep"), message)

    def test_project_private_cleaning_template_is_loaded_before_public_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template_dir = root / ".kbprep" / "rules" / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "self_media_course.json").write_text(
                json.dumps(_minimal_cleaning_template(), ensure_ascii=False),
                encoding="utf-8",
            )
            with _cwd(root):
                load_cleaning_rules.cache_clear()
                rules = load_cleaning_rules(templates=("self_media_course",))

        self.assertIn(".kbprep/rules/templates/self_media_course.json", rules.sources)
        self.assertIn("PRIVATE_TEMPLATE_MARKER", rules.cta_keywords)

    def test_project_private_accepted_rules_are_loaded_from_default_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user_dir = root / ".kbprep" / "rules" / "user"
            user_dir.mkdir(parents=True)
            (user_dir / "accepted_rules.jsonl").write_text(
                json.dumps(_accepted_rule("LOCAL_PRIVATE_ACCEPTED_MARKER"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with _cwd(root):
                load_cleaning_rules.cache_clear()
                rules = load_cleaning_rules(source_identity="local-private-smoke")

        self.assertIn(".kbprep/rules/user/accepted_rules.jsonl", rules.sources)
        self.assertTrue(any(rule.pattern == "LOCAL_PRIVATE_ACCEPTED_MARKER" for rule in rules.promotional_line_rules))

    def test_cleanup_all_preserves_local_private_rules_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_rules = root / ".kbprep" / "rules" / "user"
            private_rules.mkdir(parents=True)
            (private_rules / "accepted_rules.jsonl").write_text("{}", encoding="utf-8")
            (root / "runs").mkdir()
            (root / "converted.md").write_text("# converted", encoding="utf-8")

            deleted = _delete_standard_artifacts(root, dry_run=False)

            self.assertFalse((root / "runs").exists())
            self.assertFalse((root / "converted.md").exists())
            self.assertTrue((private_rules / "accepted_rules.jsonl").exists())
            self.assertFalse(any(".kbprep" in path for path in deleted))


def _minimal_cleaning_template() -> dict:
    return {
        "schema": "kbprep.cleaning_rules.v1",
        "description": "test private cleanup template",
        "rules": [],
        "keyword_sets": {
            "cta_keywords": ["PRIVATE_TEMPLATE_MARKER"],
        },
    }


def _minimal_obsidian_template(categories: list[str], default: str) -> dict:
    return {
        "schema": "kbprep.obsidian_template.v1",
        "description": "test private obsidian template",
        "categories": categories,
        "default_category": default,
        "method_category": default,
        "cognition_category": default,
        "case_category": default,
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
        "brand_heading_replacements": [],
        "layout_table_terms": [],
        "brand_program_packaging_terms": [],
        "translator_back_matter_terms": [],
    }


def _accepted_rule(pattern: str) -> dict:
    return {
        "schema": "kbprep.rule_proposal.v1",
        "id": "proposal-1",
        "accepted_rule_id": "accepted-1",
        "status": "accepted",
        "action": "discard",
        "scope": "global",
        "match": "literal",
        "pattern": pattern,
        "reason": "private accepted rule smoke test",
        "risk_note": "Private accepted rule smoke test is scoped to this test fixture.",
        "created_from_run": "run-1",
        "owner_confirmation_status": "confirmed",
        "requires_confirmation": True,
        "examples": [pattern],
        "counterexamples": ["legitimate course body"],
    }


if __name__ == "__main__":
    unittest.main()
