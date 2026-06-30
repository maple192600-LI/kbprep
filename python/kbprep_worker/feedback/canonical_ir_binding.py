"""Run-level Canonical IR binding evidence for feedback rerun plans."""

import json
from pathlib import Path

from ..canonical_nodes import CANONICAL_IR_TYPED_NODES_SCHEMA
from .support import _optional_string, _read_json_file


def canonical_ir_binding(run_dir: Path) -> dict:
    canonical_manifest_path = run_dir / "canonical_ir" / "manifest.json"
    document_manifest_path = run_dir / "document_manifest.json"
    canonical_manifest = _read_json_file(canonical_manifest_path)
    document_manifest = _read_json_file(document_manifest_path)
    document_id = _optional_string(canonical_manifest.get("document_id"))
    if (
        canonical_manifest.get("schema") != "kbprep.canonical_ir_manifest.v1"
        or not document_id
        or not _document_manifest_is_valid(run_dir, document_manifest)
    ):
        return pending_canonical_ir_binding()
    node_ids = _canonical_node_ids(run_dir)
    return {
        "status": "bound",
        "binding_level": "run",
        "canonical_ir_id": document_id,
        "document_id": document_id,
        "canonical_ir_manifest": str(canonical_manifest_path),
        "document_manifest": str(document_manifest_path),
        "artifacts": _canonical_ir_artifact_refs(canonical_manifest),
        "document_manifest_ref": "canonical_ir/manifest.json",
        "created_from_run": str(document_manifest["created_from_run"]),
        "node_identity_available": bool(node_ids),
        "id_level_narrowing": False,
        "canonical_node_ids": node_ids,
        "reason": _binding_reason(node_ids),
    }


def _canonical_node_ids(run_dir: Path) -> list[str]:
    """Return stable canonical_node_ids from typed_nodes.json when available.

    The typed_nodes artifact carries the per-document node identity emitted by
    the Canonical IR builders. When it is present and well-formed, the binding
    can record node-level identity for selective narrowing scope. Missing,
    unreadable, or schema-mismatched artifacts fall back to an empty list
    (run-level only).
    """
    typed_nodes_path = run_dir / "canonical_ir" / "typed_nodes.json"
    try:
        payload = json.loads(typed_nodes_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict) or payload.get("schema") != CANONICAL_IR_TYPED_NODES_SCHEMA:
        return []
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return []
    ids = [str(node.get("node_id") or "").strip() for node in nodes if isinstance(node, dict)]
    return list(dict.fromkeys(node_id for node_id in ids if node_id))


def _binding_reason(node_ids: list[str]) -> str:
    if node_ids:
        return (
            "Canonical IR node-level identity is available (canonical_node_ids recorded "
            "from typed_nodes). Execution-level selective rerun by node-id remains future "
            "work; rerun is still run-level (id_level_narrowing=false)."
        )
    return (
        "Run-level Canonical IR evidence is bound; node-level identity is unavailable "
        "without typed_nodes node_id evidence."
    )


def pending_canonical_ir_binding() -> dict:
    return {
        "status": "pending",
        "canonical_ir_id": None,
        "reason": "Canonical IR id binding is pending until run-level manifest evidence is available.",
    }


def _document_manifest_is_valid(run_dir: Path, manifest: dict) -> bool:
    return (
        manifest.get("schema") == "kbprep.document_manifest.v1"
        and _run_relative_ref_is(manifest.get("canonical_ir_manifest"), "canonical_ir/manifest.json")
        and _run_relative_ref_is(manifest.get("conversion_report"), "conversion_report.json")
        and _safe_run_relative_ref(manifest.get("converted_md"))
        and bool(_optional_string(manifest.get("created_from_run")))
        and (run_dir / "conversion_report.json").exists()
    )


def _run_relative_ref_is(value: object, expected: str) -> bool:
    return isinstance(value, str) and value == expected and _safe_run_relative_ref(value)


def _safe_run_relative_ref(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _canonical_ir_artifact_refs(manifest: dict) -> dict:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return {}
    return {str(key): value for key, value in artifacts.items() if isinstance(key, str) and isinstance(value, str)}
