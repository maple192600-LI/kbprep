"""State containers and errors for the single-file pipeline."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..detect import detect_language, normalize_language_hint


class PipelineError(Exception):
    """Raised when a pipeline stage fails."""
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


@dataclass(frozen=True)
class PipelineInputConfig:
    input_path: str
    output_root: str
    profile: str
    mode: str
    force: bool
    language: str
    source_type: str
    splitter: str
    artifact_policy: str


@dataclass(frozen=True)
class PipelineRunFacts:
    file_hash: str = ""
    file_size: int = 0
    run_id: str = ""
    source_type: str = "unknown"
    document_type: str = "unknown"


@dataclass(frozen=True)
class PipelineRuntimeFacts:
    plugin_version: str = "unknown"
    mineru_version: str = "unknown"
    python_version: str = "unknown"
    runtime_cache_key: str = ""


@dataclass(frozen=True)
class PipelineArtifactPaths:
    run_dir: Path | None = None
    converted_path: Path | None = None
    normalized_path: Path | None = None
    blocks_path: Path | None = None
    latest_file: Path | None = None


def _pipeline_language(raw_language: object, input_path: str) -> str:
    if isinstance(raw_language, str) and raw_language.strip() and raw_language.strip().lower() != "auto":
        return normalize_language_hint(raw_language)
    return detect_language(input_path)


def _stderr_log(level: str, stage: str, message: str, code: str = "") -> None:
    """Write a JSONL log entry to stderr."""
    entry = {"level": level, "stage": stage, "message": message}
    if code:
        entry["code"] = code
    sys.stderr.write(json.dumps(entry, ensure_ascii=False) + "\n")
    sys.stderr.flush()



@dataclass
class PipelineState:
    data: dict[str, Any]
    input_path: str = field(init=False)
    output_root: str = field(init=False)
    profile: str = field(init=False)
    mode: str = field(init=False)
    force: bool = field(init=False)
    language: str = field(init=False)
    override_source_type: str = field(init=False)
    override_splitter: str = field(init=False)
    artifact_policy: str = field(init=False)
    max_quality_iterations: int = field(init=False)
    warnings: list[str] = field(default_factory=list)
    strict_errors: list[str] = field(default_factory=list)
    diagnosis: dict[str, Any] = field(default_factory=dict)
    mineru_artifacts: dict[str, Any] = field(default_factory=dict)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    quality_report: dict[str, Any] = field(default_factory=dict)
    latest_outputs: dict[str, Any] = field(default_factory=dict)
    document_type: str = "unknown"
    document_type_detection: dict[str, Any] = field(default_factory=dict)
    cleaning_policy_snapshot_hash: str = ""
    cleaning_policy_snapshot: dict[str, Any] = field(default_factory=dict)
    file_hash: str = ""
    file_size: int = 0
    plugin_version: str = "unknown"
    mineru_version: str = "unknown"
    python_version: str = "unknown"
    runtime: dict[str, Any] = field(default_factory=dict)
    runtime_cache_key: str = ""
    source_type: str = "unknown"
    source_identity: dict[str, Any] = field(default_factory=dict)
    config_hash: str = ""
    run_id: str = ""
    input_p: Path = field(init=False)
    root_p: Path = field(init=False)
    original_dir: Path | None = None
    runs_dir: Path | None = None
    run_dir: Path | None = None
    latest_file: Path | None = None
    original_file: Path | None = None
    converted_path: Path | None = None
    normalized_path: Path | None = None
    blocks_path: Path | None = None
    cleaning_policy_snapshot_path: Path | None = None
    input_config: PipelineInputConfig = field(init=False)
    run_facts: PipelineRunFacts = field(default_factory=PipelineRunFacts)
    runtime_facts: PipelineRuntimeFacts = field(default_factory=PipelineRuntimeFacts)
    artifact_paths: PipelineArtifactPaths = field(default_factory=PipelineArtifactPaths)

    def __post_init__(self) -> None:
        if not isinstance(self.data, dict):
            raise PipelineError("E_INVALID_INPUT", "prepare payload must be a JSON object")
        input_path = self.data.get("input_path")
        if not isinstance(input_path, str) or not input_path.strip():
            raise PipelineError("E_INVALID_INPUT", "input_path is required and must be a non-empty string")
        self.input_path = self.data["input_path"]
        output_root = self.data.get("output_root", ".")
        if not isinstance(output_root, str) or not output_root.strip():
            raise PipelineError("E_INVALID_INPUT", "output_root must be a non-empty string when provided")
        self.output_root = output_root
        self.profile = self.data.get("profile", "standard")
        self.mode = self.data.get("mode", "rules_only")
        self.force = self.data.get("force", False)
        self.language = _pipeline_language(self.data.get("language"), self.input_path)
        self.override_source_type = self.data.get("source_type", "auto")
        self.override_splitter = self.data.get("splitter", "auto")
        self.artifact_policy = self.data.get("artifact_policy", "keep_latest")
        self.max_quality_iterations = self.data.get("max_quality_iterations", 3)
        self.input_p = Path(self.input_path)
        self.root_p = Path(self.output_root)
        self.input_config = PipelineInputConfig(
            input_path=self.input_path,
            output_root=self.output_root,
            profile=self.profile,
            mode=self.mode,
            force=self.force,
            language=self.language,
            source_type=self.override_source_type,
            splitter=self.override_splitter,
            artifact_policy=self.artifact_policy,
        )

    def error_context(self) -> dict[str, Any]:
        return {
            "run_dir": self.run_dir,
            "input_p": self.input_p,
            "root_p": self.root_p,
            "original_file": self.original_file,
            "file_hash": self.file_hash,
            "source_type": self.source_type,
            "plugin_version": self.plugin_version,
            "mineru_version": self.mineru_version,
            "runtime": self.runtime,
            "diagnosis": self.diagnosis,
        }

    def require_stage_fields(self, stage: str, *fields: str) -> None:
        missing = [field for field in fields if getattr(self, field) is None]
        if missing:
            raise PipelineError(
                "E_PIPELINE_STAGE_ORDER",
                f"{stage} stage requires initialized state fields: {', '.join(missing)}",
                {"stage": stage, "missing_fields": missing},
            )

    def require_path(self, stage: str, field: str) -> Path:
        value = getattr(self, field)
        if not isinstance(value, Path):
            raise PipelineError(
                "E_PIPELINE_STAGE_ORDER",
                f"{stage} stage requires initialized path field: {field}",
                {"stage": stage, "missing_fields": [field]},
            )
        return value
