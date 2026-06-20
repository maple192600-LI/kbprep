import re
import unittest
from pathlib import Path

from kbprep_worker.error_codes import KBPREP_ERROR_CODES, KBPREP_RUNTIME_ERROR_CODES, KBPREP_WARNING_CODES

ROOT = Path(__file__).resolve().parents[2]


class ErrorCodeContractTests(unittest.TestCase):
    def test_typescript_and_python_error_code_lists_match(self):
        ts_source = (ROOT / "src/errorCodes.ts").read_text(encoding="utf-8")
        ts_errors = _typescript_const_values(ts_source, "KBPREP_ERROR_CODES")
        ts_runtime_errors = _typescript_const_values(ts_source, "KBPREP_RUNTIME_ERROR_CODES")
        ts_warnings = _typescript_const_values(ts_source, "KBPREP_WARNING_CODES")

        self.assertEqual(ts_errors, KBPREP_ERROR_CODES)
        self.assertEqual(ts_runtime_errors, KBPREP_RUNTIME_ERROR_CODES)
        self.assertEqual(ts_warnings, KBPREP_WARNING_CODES)

    def test_source_does_not_introduce_unregistered_codes(self):
        registered = KBPREP_ERROR_CODES | KBPREP_WARNING_CODES
        offenders: list[str] = []
        for folder in [ROOT / "src", ROOT / "python/kbprep_worker"]:
            for path in folder.rglob("*"):
                if path.suffix not in {".ts", ".py"} or "__pycache__" in path.parts or path.name.endswith(".test.ts"):
                    continue
                text = path.read_text(encoding="utf-8")
                for code in re.findall(r'"([EW]_[A-Z0-9_]+)"|\'([EW]_[A-Z0-9_]+)\'', text):
                    value = code[0] or code[1]
                    if value.endswith("_"):
                        continue
                    if value not in registered:
                        offenders.append(f"{path.relative_to(ROOT)}:{value}")

        self.assertEqual(offenders, [])

    def test_runtime_error_codes_are_registered(self):
        registered = KBPREP_RUNTIME_ERROR_CODES
        offenders: list[str] = []

        for path in (ROOT / "src").rglob("*.ts"):
            if path.name == "errorCodes.ts" or path.name.endswith(".test.ts"):
                continue
            text = path.read_text(encoding="utf-8")
            for code in re.findall(r'code:\s*"(KBPREP_[A-Z0-9_]+)"', text):
                if code not in registered:
                    offenders.append(f"{path.relative_to(ROOT)}:{code}")
        for path in (ROOT / "python/kbprep_worker").rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for code in re.findall(r'fail\(\s*"([A-Z0-9_]+)"', text):
                if code.startswith("KBPREP_") and code not in registered:
                    offenders.append(f"{path.relative_to(ROOT)}:{code}")

        self.assertEqual(offenders, [])


def _typescript_const_values(source: str, const_name: str) -> set[str]:
    match = re.search(rf"export const {const_name} = \[(.*?)\] as const;", source, re.DOTALL)
    if not match:
        return set()
    return set(re.findall(r'"([A-Z0-9_]+)"', match.group(1)))


if __name__ == "__main__":
    unittest.main()
