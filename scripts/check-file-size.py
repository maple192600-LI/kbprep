from __future__ import annotations

import ast
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

MAX_FILE_LINES = 800
MAX_FUNCTION_LINES = 50
SCAN_ROOTS = (Path("python/kbprep_worker"), Path("src"))
SKIP_PARTS = frozenset({"__pycache__", ".venv", "node_modules", "dist", ".git", "build"})
ALLOWLIST_PATH = Path("scripts/checks/file-size-allowlist.json")


@dataclass(frozen=True)
class Allowance:
    allowed_lines: int
    reason: str
    expires: date


@dataclass(frozen=True)
class Allowlist:
    entries: Mapping[str, Allowance]


@dataclass(frozen=True)
class Violation:
    key: str
    message: str


def collect_violations(
    repo_root: Path,
    scan_roots: Sequence[Path],
    allowlist: Allowlist,
    current_date: date,
) -> list[Violation]:
    violations: list[Violation] = []
    allowance_observations: dict[str, int] = {}
    for path in _iter_checked_files(repo_root, scan_roots):
        line_count = _count_lines(path)
        relative = _relative(path, repo_root)
        key = f"file:{relative}"
        _record_allowance_observation(allowance_observations, allowlist, key, line_count)
        if line_count > MAX_FILE_LINES:
            _append_violation(
                violations,
                key=key,
                message=f"{relative}: 文件 {line_count} 行 > {MAX_FILE_LINES}",
                actual_lines=line_count,
                allowlist=allowlist,
                current_date=current_date,
            )
        if path.suffix == ".py":
            violations.extend(_python_function_violations(path, repo_root, allowlist, current_date, allowance_observations))
    violations.extend(_allowlist_cleanup_violations(allowlist, allowance_observations))
    return violations


def load_allowlist(path: Path) -> Allowlist:
    if not path.exists():
        return Allowlist(entries={})
    payload = json.loads(path.read_text(encoding="utf-8"))
    reason = _required_text(payload, "reason")
    expires = _parse_date(_required_text(payload, "expires"))
    raw_entries = payload.get("entries", {})
    if not isinstance(raw_entries, dict):
        raise ValueError("file-size allowlist entries must be an object")
    entries = {
        key: Allowance(
            allowed_lines=_required_int(value, "allowed_lines", key),
            reason=reason,
            expires=expires,
        )
        for key, value in raw_entries.items()
    }
    return Allowlist(entries=entries)


def _iter_checked_files(repo_root: Path, scan_roots: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    for root in scan_roots:
        absolute_root = root if root.is_absolute() else repo_root / root
        if not absolute_root.exists():
            continue
        for path in absolute_root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts"} and not _is_skipped(path, repo_root):
                files.append(path)
    return sorted(files)


def _python_function_violations(
    path: Path,
    repo_root: Path,
    allowlist: Allowlist,
    current_date: date,
    allowance_observations: dict[str, int],
) -> list[Violation]:
    source = path.read_text(encoding="utf-8")
    relative = _relative(path, repo_root)
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        return [Violation(key=f"parse:{relative}", message=f"{relative}: Python 解析失败 {error}")]
    visitor = _FunctionLengthVisitor(relative, allowlist, current_date, allowance_observations)
    visitor.visit(tree)
    return visitor.violations


def _append_violation(
    violations: list[Violation],
    key: str,
    message: str,
    actual_lines: int,
    allowlist: Allowlist,
    current_date: date,
) -> None:
    allowance = allowlist.entries.get(key)
    if allowance is None:
        violations.append(Violation(key=key, message=message))
        return
    if current_date > allowance.expires:
        violations.append(Violation(key=key, message=f"{message}；临时豁免已于 {allowance.expires.isoformat()} 过期"))
        return
    if actual_lines > allowance.allowed_lines:
        violations.append(Violation(key=key, message=f"{message}；超过临时豁免上限 {allowance.allowed_lines} 行"))


class _FunctionLengthVisitor(ast.NodeVisitor):
    def __init__(
        self,
        relative_path: str,
        allowlist: Allowlist,
        current_date: date,
        allowance_observations: dict[str, int],
    ) -> None:
        self.relative_path = relative_path
        self.allowlist = allowlist
        self.current_date = current_date
        self.allowance_observations = allowance_observations
        self.stack: list[str] = []
        self.violations: list[Violation] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        actual_lines = (node.end_lineno or node.lineno) - node.lineno + 1
        function_name = ".".join((*self.stack, node.name))
        key = f"function:{self.relative_path}:{function_name}"
        _record_allowance_observation(self.allowance_observations, self.allowlist, key, actual_lines)
        if actual_lines > MAX_FUNCTION_LINES:
            _append_violation(
                self.violations,
                key=key,
                message=f"{self.relative_path}:{node.lineno} 函数 {function_name} {actual_lines} 行 > {MAX_FUNCTION_LINES}",
                actual_lines=actual_lines,
                allowlist=self.allowlist,
                current_date=self.current_date,
            )
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()


def _record_allowance_observation(observations: dict[str, int], allowlist: Allowlist, key: str, actual_lines: int) -> None:
    if key in allowlist.entries:
        observations[key] = actual_lines


def _allowlist_cleanup_violations(allowlist: Allowlist, observations: Mapping[str, int]) -> list[Violation]:
    violations: list[Violation] = []
    for key in sorted(allowlist.entries):
        actual_lines = observations.get(key)
        if actual_lines is None:
            violations.append(Violation(key=key, message=f"{ALLOWLIST_PATH}: {key} 临时豁免目标不存在或不在扫描范围"))
            continue
        limit = _limit_for_allowance_key(key)
        if actual_lines <= limit:
            violations.append(Violation(key=key, message=f"{ALLOWLIST_PATH}: {key} 临时豁免已不需要；当前 {actual_lines} 行 <= {limit} 行"))
    return violations


def _limit_for_allowance_key(key: str) -> int:
    if key.startswith("file:"):
        return MAX_FILE_LINES
    return MAX_FUNCTION_LINES


def _is_skipped(path: Path, repo_root: Path) -> bool:
    return any(part in SKIP_PARTS for part in _relative_path_parts(path, repo_root))


def _relative(path: Path, repo_root: Path) -> str:
    return Path(*_relative_path_parts(path, repo_root)).as_posix()


def _relative_path_parts(path: Path, repo_root: Path) -> tuple[str, ...]:
    try:
        return path.relative_to(repo_root).parts
    except ValueError:
        return path.parts


def _count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _required_text(payload: object, field: str) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get(field), str) or not payload[field].strip():
        raise ValueError(f"file-size allowlist must define non-empty {field}")
    return payload[field]


def _required_int(payload: object, field: str, key: str) -> int:
    if not isinstance(payload, dict) or not isinstance(payload.get(field), int):
        raise ValueError(f"file-size allowlist entry {key} must define integer {field}")
    return payload[field]


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"file-size allowlist expires must be YYYY-MM-DD: {value}") from error


def main() -> int:
    repo_root = Path.cwd()
    try:
        allowlist = load_allowlist(repo_root / ALLOWLIST_PATH)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        sys.stderr.write(f"行数检查配置无效: {error}\n")
        return 1
    violations = collect_violations(repo_root, SCAN_ROOTS, allowlist, date.today())
    if violations:
        sys.stderr.write("\n".join(violation.message for violation in violations))
        sys.stderr.write("\n")
        return 1
    sys.stdout.write(
        f"OK: 文件<={MAX_FILE_LINES} 行，函数<={MAX_FUNCTION_LINES} 行；"
        f"{len(allowlist.entries)} 个既有超限项受临时豁免约束\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
