import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ReviewRegressionGuardTests(unittest.TestCase):
    def test_project_environment_command_can_import_worker_package(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import kbprep_worker; print(kbprep_worker.__name__)",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=15,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "kbprep_worker")

    def test_envelope_does_not_call_sys_exit_directly(self):
        tree = ast.parse((ROOT / "python/kbprep_worker/envelope.py").read_text(encoding="utf-8"))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "sys"
            and node.func.attr == "exit"
        ]

        self.assertEqual(calls, [])

    def test_feedback_and_quality_remain_packages(self):
        self.assertTrue((ROOT / "python/kbprep_worker/feedback/__init__.py").is_file())
        self.assertTrue((ROOT / "python/kbprep_worker/quality/__init__.py").is_file())
        self.assertFalse((ROOT / "python/kbprep_worker/feedback.py").exists())
        self.assertFalse((ROOT / "python/kbprep_worker/quality.py").exists())

    def test_pipeline_keeps_diagnose_direct_and_html_converter_external(self):
        source = (ROOT / "python/kbprep_worker/stages/pipeline.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        subprocess_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ]
        self.assertEqual(subprocess_calls, [])
        self.assertNotIn("class _HTMLToMarkdownParser", source)
        self.assertNotIn("def _rich_html_to_markdown(", source)
        self.assertNotIn("def _standalone_svg_text(", source)

    def test_pipeline_size_budget_stays_reviewable(self):
        source = (ROOT / "python/kbprep_worker/stages/pipeline.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source)
        run_node = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        self.assertLess(len(lines), 1000)
        self.assertLess(run_node.end_lineno - run_node.lineno + 1, 300)

    def test_pipeline_core_run_is_stage_orchestration_only(self):
        source = (ROOT / "python/kbprep_worker/stages/pipeline_core.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        run_node = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        self.assertLess(run_node.end_lineno - run_node.lineno + 1, 100)

    def test_obsidian_and_diagnose_remain_packages(self):
        self.assertTrue((ROOT / "python/kbprep_worker/obsidian_kb/__init__.py").is_file())
        self.assertTrue((ROOT / "python/kbprep_worker/diagnose/__init__.py").is_file())
        self.assertFalse((ROOT / "python/kbprep_worker/obsidian_kb.py").exists())
        self.assertFalse((ROOT / "python/kbprep_worker/diagnose.py").exists())
        for module in ("context.py", "policy.py", "signals.py", "titles.py", "body_notes.py", "frontmatter.py", "links.py"):
            self.assertTrue((ROOT / "python/kbprep_worker/obsidian_kb" / module).is_file())
        for module in ("format_detect.py", "pdf_analysis.py", "runtime.py"):
            self.assertTrue((ROOT / "python/kbprep_worker/diagnose" / module).is_file())

    def test_obsidian_package_has_no_giant_facade_or_empty_submodules(self):
        package_dir = ROOT / "python/kbprep_worker/obsidian_kb"
        init_source = (package_dir / "__init__.py").read_text(encoding="utf-8")
        self.assertLessEqual(len(init_source.splitlines()), 80)
        self.assertNotIn("OBSIDIAN_TEMPLATE =", init_source)
        self.assertNotIn("def _use_obsidian_template", init_source)

        direct_definitions = {
            "body_notes.py": "render_obsidian_vault",
            "policy.py": "apply_curated_obsidian_policy",
            "titles.py": "complete_body_filename",
            "frontmatter.py": "_yaml_safe",
            "links.py": "_safe_filename",
        }
        for filename, function_name in direct_definitions.items():
            source = (package_dir / filename).read_text(encoding="utf-8")
            tree = ast.parse(source)
            self.assertTrue(
                any(isinstance(node, ast.FunctionDef) and node.name == function_name for node in tree.body),
                f"{filename} must directly define {function_name}",
            )
            self.assertNotIn("from . import", source)

        for path in package_dir.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("OBSIDIAN_TEMPLATE =", source)
            self.assertNotIn("def _use_obsidian_template", source)

    def test_ocr_normalization_rules_are_externalized(self):
        rules_path = ROOT / "rules/base/ocr_normalization.json"
        self.assertTrue(rules_path.is_file())
        payload = json.loads(rules_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "kbprep.ocr_normalization.v1")
        self.assertGreaterEqual(len(payload["fix_rules"]), 1)

        normalize_source = (ROOT / "python/kbprep_worker/normalize.py").read_text(encoding="utf-8")
        self.assertNotIn("OCR_FIX_PATTERNS = [", normalize_source)
        self.assertIn("load_ocr_normalization_rules", normalize_source)

    def test_ci_and_build_guards_are_present(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        direct_unittest = "python" + " -m unittest discover -s python/tests"
        direct_worker_help = "python" + " -m kbprep_worker.cli"
        direct_pythonpath = "PYTHONPATH" + ": python"
        direct_system_install = "uv pip install " + "--system"

        self.assertIn("node scripts/python-venv.mjs -m unittest discover -s python/tests", ci)
        self.assertIn("node scripts/python-venv.mjs -m kbprep_worker.cli --help", ci)
        self.assertIn("KBPREP_WORKER_NOT_READY", ci)
        self.assertIn("preflight should report missing MinerU in the lightweight CI worker", ci)
        self.assertNotIn(direct_pythonpath, ci)
        self.assertNotIn(direct_system_install, ci)
        self.assertNotIn(direct_unittest, ci)
        self.assertNotIn(direct_worker_help, ci)
        self.assertIn("node --input-type=module", package["scripts"]["build"])
        self.assertNotIn("require('fs')", package["scripts"]["build"])


if __name__ == "__main__":
    unittest.main()
