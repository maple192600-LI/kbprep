from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import ModuleType


def load_check_file_size() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "check-file-size.py"
    spec = importlib.util.spec_from_file_location("check_file_size", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_python_function(path: Path, body_lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"    value_{index} = {index}" for index in range(body_lines))
    path.write_text(f"def too_long() -> None:\n{body}\n", encoding="utf-8")


class CheckFileSizeScriptTests(unittest.TestCase):
    def test_detects_python_function_over_limit(self) -> None:
        module = load_check_file_size()
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source_path = repo_root / "python" / "kbprep_worker" / "sample.py"
            write_python_function(source_path, body_lines=51)

            violations = module.collect_violations(
                repo_root=repo_root,
                scan_roots=(repo_root / "python" / "kbprep_worker",),
                allowlist=module.Allowlist(entries={}),
                current_date=date(2026, 6, 16),
            )

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].key, "function:python/kbprep_worker/sample.py:too_long")
        self.assertIn("52 行 > 50", violations[0].message)

    def test_allowlist_permits_known_debt_but_blocks_growth(self) -> None:
        module = load_check_file_size()
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source_path = repo_root / "python" / "kbprep_worker" / "sample.py"
            write_python_function(source_path, body_lines=51)
            allowance = module.Allowance(
                allowed_lines=52,
                reason="existing oversized function scheduled for refactor",
                expires=date(2026, 6, 30),
            )
            allowlist = module.Allowlist(
                entries={"function:python/kbprep_worker/sample.py:too_long": allowance},
            )

            self.assertEqual(
                module.collect_violations(
                    repo_root=repo_root,
                    scan_roots=(repo_root / "python" / "kbprep_worker",),
                    allowlist=allowlist,
                    current_date=date(2026, 6, 16),
                ),
                [],
            )

            write_python_function(source_path, body_lines=52)
            violations = module.collect_violations(
                repo_root=repo_root,
                scan_roots=(repo_root / "python" / "kbprep_worker",),
                allowlist=allowlist,
                current_date=date(2026, 6, 16),
            )

        self.assertEqual(len(violations), 1)
        self.assertIn("超过临时豁免上限 52 行", violations[0].message)

    def test_allowlist_flags_resolved_debt_for_removal(self) -> None:
        module = load_check_file_size()
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source_path = repo_root / "python" / "kbprep_worker" / "sample.py"
            write_python_function(source_path, body_lines=10)
            allowance = module.Allowance(
                allowed_lines=52,
                reason="existing oversized function scheduled for refactor",
                expires=date(2026, 6, 30),
            )
            allowlist = module.Allowlist(
                entries={"function:python/kbprep_worker/sample.py:too_long": allowance},
            )

            violations = module.collect_violations(
                repo_root=repo_root,
                scan_roots=(repo_root / "python" / "kbprep_worker",),
                allowlist=allowlist,
                current_date=date(2026, 6, 16),
            )

        self.assertEqual(len(violations), 1)
        self.assertIn("临时豁免已不需要", violations[0].message)


if __name__ == "__main__":
    unittest.main()
