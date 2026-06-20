"""Local private rule locations that stay outside the public package."""

from __future__ import annotations

import os
from pathlib import Path


def project_private_rules_root(cwd: Path | None = None) -> Path:
    return project_root(cwd) / ".kbprep" / "rules"


def project_root(cwd: Path | None = None) -> Path:
    value = os.environ.get("KBPREP_PROJECT_ROOT", "").strip()
    if value:
        return Path(value).expanduser().resolve()
    return cwd or Path.cwd()


def env_private_rule_roots() -> tuple[Path, ...]:
    value = os.environ.get("KBPREP_USER_RULES_DIR", "").strip()
    if not value:
        return ()
    roots = []
    for raw in value.split(os.pathsep):
        if raw.strip():
            roots.append(Path(raw).expanduser().resolve())
    return tuple(_dedupe_paths(roots))


def accepted_rule_dirs_from_env() -> tuple[Path, ...]:
    candidates = []
    for root in env_private_rule_roots():
        candidates.append(root)
        if root.name != "user":
            candidates.append(root / "user")
    return tuple(_dedupe_paths(candidates))


def template_candidates(name: str, public_templates_root: Path, cwd: Path | None = None) -> tuple[Path, ...]:
    filename = f"{name}.json"
    candidates = []
    for root in env_private_rule_roots():
        if root.name == "templates":
            candidates.append(root / filename)
        else:
            candidates.append(root / "templates" / filename)
    candidates.append(project_private_rules_root(cwd) / "templates" / filename)
    candidates.append(public_templates_root / filename)
    return tuple(_dedupe_paths(candidates))


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    result = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result
