import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

from kbprep_worker import prepare_batch
from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.stages import pipeline_core


def _capture_envelope(fn: Callable[[dict[str, Any]], None], payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fn(payload)
    except EnvelopeExit as exc:
        return exc.code, json.loads(out.getvalue())
    raise AssertionError("worker command did not write a JSON envelope")


def _successful_child(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
    out = Path(output_root)
    out.mkdir(parents=True, exist_ok=True)
    final = out / f"{file_path.stem}.cleaned.md"
    final.write_text(f"# {file_path.stem}", encoding="utf-8")
    return {
        "ok": True,
        "data": {
            "run_id": file_path.stem,
            "strict_errors": [],
            "latest_outputs": {
                "final_artifact_type": "markdown",
                "final_md": str(final),
            },
        },
    }


def _write_policy_affected_run_evidence(
    run_dir: Path,
    *,
    document_id: str,
    policy_snapshot_hash: str,
    source_identity: dict[str, Any],
    document_type: str = "course",
) -> None:
    """Write run_metadata + canonical_ir binding artifacts under run_dir.

    Mirrors feedback/_write_canonical_ir_binding_artifacts (test_feedback.py) so
    canonical_ir_binding(run_dir) returns status="bound" with the given document_id.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "schema": "kbprep.run_metadata.v1",
                "run_id": run_dir.name,
                "source_identity": source_identity,
                "document_type": document_type,
                "cleaning_policy_snapshot_hash": policy_snapshot_hash,
                "prepare_payload": {"input_path": "", "output_root": "", "profile": "standard"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "quality_report.json").write_text(
        json.dumps({"profile": "standard", "document_type": document_type}),
        encoding="utf-8",
    )
    (run_dir / "converted.md").write_text("# Converted\n", encoding="utf-8")
    (run_dir / "conversion_report.json").write_text(
        json.dumps({"converted_md": "converted.md"}),
        encoding="utf-8",
    )
    canonical_dir = run_dir / "canonical_ir"
    canonical_dir.mkdir(exist_ok=True)
    (canonical_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "kbprep.canonical_ir_manifest.v1",
                "document_id": document_id,
                "status": "partial",
                "artifacts": {
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "document_manifest.json").write_text(
        json.dumps(
            {
                "schema": "kbprep.document_manifest.v1",
                "canonical_ir_manifest": "canonical_ir/manifest.json",
                "conversion_report": "conversion_report.json",
                "converted_md": "converted.md",
                "created_from_run": str(run_dir),
            }
        ),
        encoding="utf-8",
    )


def _build_policy_affected_fixture(root: Path) -> tuple[Path, Path, dict[str, dict[str, Any]]]:
    """Build a batch manifest + child run evidence for policy_affected rerun tests.

    alpha/beta are succeeded children (manifest records run_id); gamma is a failed child
    (manifest records no run_id, so its evidence is reached only by scanning runs/);
    delta is pending (no output_root). Returns (manifest_path, input_dir, children) where
    children maps relative_path -> {document_id, policy_snapshot_hash, source_identity}.
    """
    input_dir = root / "sources"
    output_root = root / "batch"
    input_dir.mkdir()
    for name in ("alpha.md", "beta.md", "gamma.md"):
        (input_dir / name).write_text(f"# {name.removesuffix('.md')}", encoding="utf-8")

    identities = {
        "alpha.md": ("doc-alpha", "hash-alpha", {"source_name": "alpha.md", "source_domain": "example.com"}, "succeeded", "run_alpha"),
        "beta.md": ("doc-beta", "hash-beta", {"source_name": "beta.md", "source_domain": "example.com"}, "succeeded", "run_beta"),
        "gamma.md": ("doc-gamma", "hash-gamma", {"source_name": "gamma.md", "source_domain": "gamma.example.com"}, "failed", None),
    }
    items: list[dict[str, Any]] = []
    children: dict[str, dict[str, Any]] = {}
    for name, (doc_id, policy_hash, source_identity, status, run_id) in identities.items():
        child_out = output_root / "files" / name.removesuffix(".md")
        _write_policy_affected_run_evidence(
            child_out / "runs" / (run_id or "run_gamma_001"),
            document_id=doc_id,
            policy_snapshot_hash=policy_hash,
            source_identity=source_identity,
        )
        item: dict[str, Any] = {"relative_path": name, "file": name, "status": status, "rerunnable": True, "output_root": str(child_out)}
        if run_id:
            item["run_id"] = run_id
        items.append(item)
        children[name] = {"document_id": doc_id, "policy_snapshot_hash": policy_hash, "source_identity": source_identity}
    items.append({"relative_path": "delta.md", "file": "delta.md", "status": "pending", "rerunnable": True})
    manifest_path = output_root / "batch_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "kbprep.batch_manifest.v1",
                "input_dir": str(input_dir),
                "output_root": str(output_root),
                "items": items,
                "rerun": {"recommended_scope": "none"},
            }
        ),
        encoding="utf-8",
    )
    return manifest_path, input_dir, children


class BatchStatusManifestTests(unittest.TestCase):
    def test_all_successful_children_write_completed_parent_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "beta.txt").write_text("Beta", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", side_effect=_successful_child):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )

            self.assertEqual(code, 0)
            manifest_path = Path(envelope["data"]["batch_manifest_json"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["summary"]["succeeded"], 2)
            self.assertEqual(manifest["summary"]["failed"], 0)
            self.assertEqual(manifest["summary"]["skipped_unsupported"], 0)
            self.assertEqual(manifest["rerun"]["recommended_scope"], "none")

    def test_batch_writes_status_manifest_with_skips_and_empty_rerun_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "beta.txt").write_text("Beta", encoding="utf-8")
            (input_dir / "archive.bin").write_text("skip", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", side_effect=_successful_child):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )

            self.assertEqual(code, 0)
            manifest_path = Path(envelope["data"]["batch_manifest_json"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["schema"], "kbprep.batch_manifest.v1")
            self.assertEqual(manifest["status"], "completed_with_warnings")
            self.assertEqual(manifest["summary"]["succeeded"], 2)
            self.assertEqual(manifest["summary"]["skipped_unsupported"], 1)
            self.assertEqual(manifest["rerun"]["failed_only"], [])
            self.assertEqual(manifest["rerun"]["recommended_scope"], "none")
            statuses = {item["relative_path"]: item["status"] for item in manifest["items"]}
            self.assertEqual(statuses["alpha.md"], "succeeded")
            self.assertEqual(statuses["beta.txt"], "succeeded")
            self.assertEqual(statuses["archive.bin"], "skipped_unsupported")
            alpha = next(item for item in manifest["items"] if item["relative_path"] == "alpha.md")
            self.assertEqual(len(alpha["source_sha256"]), 64)

    def test_playlist_batch_expands_to_youtube_child_jobs_with_parent_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_root = root / "playlist-batch"
            playlist_url = "https://www.youtube.com/playlist?list=ExamplePlaylist01"

            def expand_playlist(source_url: str, output_root_arg: Path, **_kwargs: Any) -> Any:
                source_dir = output_root_arg / ".kbprep-inputs" / "youtube-playlist" / "ExamplePlaylist01"
                source_dir.mkdir(parents=True, exist_ok=True)
                descriptors = []
                for index, video_id in enumerate(("ExampleVideo01", "ExampleVideo02"), start=1):
                    descriptor = source_dir / f"{index:03d}-{video_id}.url"
                    descriptor.write_text(
                        f"[InternetShortcut]\nURL=https://www.youtube.com/watch?v={video_id}\n",
                        encoding="utf-8",
                    )
                    descriptors.append(descriptor)
                manifest = output_root_arg / "playlist_manifest.json"
                manifest.write_text(
                    json.dumps(
                        {
                            "schema": "kbprep.youtube_playlist_manifest.v1",
                            "playlist_url": source_url,
                            "playlist_id": "ExamplePlaylist01",
                            "descriptors": [str(path) for path in descriptors],
                        }
                    ),
                    encoding="utf-8",
                )
                return type(
                    "PlaylistExpansion",
                    (),
                    {
                        "ok": True,
                        "source_dir": source_dir,
                        "descriptor_paths": descriptors,
                        "report": {
                            "playlist_url": source_url,
                            "playlist_id": "ExamplePlaylist01",
                            "playlist_manifest_json": str(manifest),
                            "summary": {"selected": 2, "available": 2},
                        },
                    },
                )()

            processed_urls: list[str] = []

            def child(file_path: Path, output_root_arg: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                descriptor = file_path.read_text(encoding="utf-8")
                processed_urls.append(descriptor.split("URL=", 1)[1].strip())
                return _successful_child(file_path, output_root_arg)

            with (
                patch.object(prepare_batch, "expand_youtube_playlist_to_descriptors", side_effect=expand_playlist),
                patch.object(prepare_batch, "_process_one_file", side_effect=child),
            ):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "playlist_url": playlist_url,
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )

            self.assertEqual(code, 0)
            self.assertEqual(
                processed_urls,
                [
                    "https://www.youtube.com/watch?v=ExampleVideo01",
                    "https://www.youtube.com/watch?v=ExampleVideo02",
                ],
            )
            manifest = json.loads(Path(envelope["data"]["batch_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_collection"]["kind"], "youtube_playlist")
            self.assertEqual(manifest["source_collection"]["playlist_url"], playlist_url)
            self.assertEqual(manifest["source_collection"]["playlist_id"], "ExamplePlaylist01")
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["summary"]["succeeded"], 2)
            self.assertEqual([item["source_url"] for item in manifest["items"]], processed_urls)

    def test_failed_sample_writes_manifest_with_failed_and_pending_rerun_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "beta.md").write_text("# Beta", encoding="utf-8")

            def fail_first(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                if file_path.name == "alpha.md":
                    return {
                        "ok": False,
                        "error": {
                            "code": "E_TEST_STRICT",
                            "message": "forced sample failure",
                            "details": {"stage": "quality_check"},
                        },
                    }
                return _successful_child(file_path, output_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=fail_first):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )

            manifest_path = Path(envelope["error"]["details"]["batch_manifest_json"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(code, 1)
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["summary"]["processed"], 1)
            self.assertEqual(manifest["summary"]["failed"], 1)
            self.assertEqual(manifest["summary"]["pending"], 1)
            self.assertEqual(manifest["rerun"]["recommended_scope"], "failed_and_pending")
            self.assertEqual(manifest["rerun"]["failed_only"], ["alpha.md"])
            self.assertEqual(manifest["rerun"]["pending"], ["beta.md"])
            items = {item["relative_path"]: item for item in manifest["items"]}
            self.assertEqual(items["alpha.md"]["failure_stage"], "quality_check")
            self.assertEqual(items["beta.md"]["status"], "pending")

    def test_batch_rerun_executes_failed_and_pending_manifest_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "beta.md").write_text("# Beta", encoding="utf-8")
            (input_dir / "gamma.md").write_text("# Gamma", encoding="utf-8")

            def fail_first(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                if file_path.name == "alpha.md":
                    return {"ok": False, "error": {"code": "E_TEST_STRICT", "details": {"stage": "quality_check"}}}
                return _successful_child(file_path, output_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=fail_first):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])
            rerun_calls: list[str] = []

            def rerun_child(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                rerun_calls.append(file_path.relative_to(input_dir).as_posix())
                return _successful_child(file_path, output_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=rerun_child):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "rerun": True,
                        "batch_manifest_path": str(manifest_path),
                        "min_free_memory_gb": 0,
                    },
                )

            self.assertEqual(code, 0)
            self.assertEqual(rerun_calls, ["alpha.md", "beta.md", "gamma.md"])
            rerun_manifest = json.loads(Path(envelope["data"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(rerun_manifest["schema"], "kbprep.batch_rerun_manifest.v1")
            self.assertEqual(rerun_manifest["status"], "completed")
            self.assertEqual(rerun_manifest["source_batch_manifest"], str(manifest_path))
            self.assertEqual(rerun_manifest["scope"], "failed_and_pending")
            self.assertEqual(rerun_manifest["summary"]["selected"], 3)
            self.assertEqual(rerun_manifest["summary"]["succeeded"], 3)

    def test_batch_rerun_skips_unrelated_successful_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "beta.md").write_text("# Beta", encoding="utf-8")
            (input_dir / "gamma.md").write_text("# Gamma", encoding="utf-8")

            def mixed_result(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                if file_path.name == "beta.md":
                    return {"ok": False, "error": {"code": "E_TEST_STRICT", "details": {"stage": "quality_check"}}}
                return _successful_child(file_path, output_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=mixed_result):
                code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["data"]["batch_manifest_json"])
            rerun_calls: list[str] = []

            def rerun_child(file_path: Path, output_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                rerun_calls.append(file_path.relative_to(input_dir).as_posix())
                return _successful_child(file_path, output_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=rerun_child):
                rerun_code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
                )

            rerun_manifest = json.loads(Path(envelope["data"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertEqual(rerun_code, 0)
            self.assertEqual(rerun_calls, ["beta.md"])
            self.assertEqual(rerun_manifest["selected"], ["beta.md"])
            self.assertEqual(rerun_manifest["scope"], "failed_only")

    def test_batch_manifest_records_rerun_command_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", side_effect=_successful_child):
                _code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "profile": "obsidian_kb",
                        "mode": "rules_plus_review_pack",
                        "language": "en",
                        "force": True,
                        "artifact_policy": "keep_all",
                        "max_quality_iterations": 7,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )

            manifest = json.loads(Path(envelope["data"]["batch_manifest_json"]).read_text(encoding="utf-8"))
            defaults = manifest["rerun"]["command_defaults"]
            self.assertEqual(defaults["profile"], "obsidian_kb")
            self.assertEqual(defaults["mode"], "rules_plus_review_pack")
            self.assertEqual(defaults["language"], "en")
            self.assertEqual(defaults["artifact_policy"], "keep_all")
            self.assertEqual(defaults["max_quality_iterations"], 7)

    def test_batch_manifest_preserves_youtube_fallback_rerun_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_root = root / "batch"
            playlist_url = "https://www.youtube.com/playlist?list=ExamplePlaylist01"

            def expand_playlist(source_url: str, output_root_arg: Path, **_kwargs: Any) -> Any:
                source_dir = output_root_arg / ".kbprep-inputs" / "youtube-playlist" / "ExamplePlaylist01"
                source_dir.mkdir(parents=True, exist_ok=True)
                descriptor = source_dir / "001-ExampleVideo01.url"
                descriptor.write_text(
                    "[InternetShortcut]\nURL=https://www.youtube.com/watch?v=ExampleVideo01\n",
                    encoding="utf-8",
                )
                return type(
                    "PlaylistExpansion",
                    (),
                    {
                        "ok": True,
                        "source_dir": source_dir,
                        "descriptor_paths": [descriptor],
                        "report": {
                            "playlist_url": source_url,
                            "playlist_id": "ExamplePlaylist01",
                            "summary": {"selected": 1, "available": 1},
                        },
                    },
                )()

            with (
                patch.object(prepare_batch, "expand_youtube_playlist_to_descriptors", side_effect=expand_playlist),
                patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}),
            ):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "playlist_url": playlist_url,
                        "output_root": str(output_root),
                        "force": True,
                        "allow_youtube_media_fallback": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])

            fallback_values: list[bool] = []

            def rerun_child(_file_path: Path, _output_root: str, *_args: Any, **kwargs: Any) -> dict[str, Any]:
                fallback_values.append(kwargs.get("allow_youtube_media_fallback") is True)
                return _successful_child(_file_path, _output_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=rerun_child):
                code, _envelope = _capture_envelope(
                    prepare_batch.run,
                    {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
                )

            self.assertEqual(code, 0)
            self.assertEqual(fallback_values, [True])

    def test_playlist_batch_rerun_preserves_playlist_source_collection_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_root = root / "batch"
            playlist_url = "https://www.youtube.com/playlist?list=ExamplePlaylist01"

            def expand_playlist(source_url: str, output_root_arg: Path, **_kwargs: Any) -> Any:
                source_dir = output_root_arg / ".kbprep-inputs" / "youtube-playlist" / "ExamplePlaylist01"
                source_dir.mkdir(parents=True, exist_ok=True)
                descriptor = source_dir / "001-ExampleVideo01.url"
                descriptor.write_text(
                    "[InternetShortcut]\nURL=https://www.youtube.com/watch?v=ExampleVideo01\n",
                    encoding="utf-8",
                )
                return type(
                    "PlaylistExpansion",
                    (),
                    {
                        "ok": True,
                        "source_dir": source_dir,
                        "descriptor_paths": [descriptor],
                        "report": {
                            "playlist_url": source_url,
                            "playlist_id": "ExamplePlaylist01",
                            "summary": {"selected": 1, "available": 1},
                        },
                    },
                )()

            with (
                patch.object(prepare_batch, "expand_youtube_playlist_to_descriptors", side_effect=expand_playlist),
                patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}),
            ):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "playlist_url": playlist_url,
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
            )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_collection"]["private_source_text"] = "SECRET_SOURCE_TEXT"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", side_effect=_successful_child):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
                )

            rerun_manifest = json.loads(Path(envelope["data"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertEqual(rerun_manifest["source_collection"]["kind"], "youtube_playlist")
            self.assertEqual(rerun_manifest["source_collection"]["playlist_url"], playlist_url)
            self.assertEqual(rerun_manifest["source_collection"]["playlist_id"], "ExamplePlaylist01")
            self.assertNotIn("private_source_text", rerun_manifest["source_collection"])
            self.assertEqual(rerun_manifest["results"][0]["source_url"], "https://www.youtube.com/watch?v=ExampleVideo01")
            self.assertEqual(rerun_manifest["results"][0]["source_sha256"], manifest["items"][0]["source_sha256"])

    def test_batch_rerun_reports_missing_sources_without_success_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            missing = input_dir / "missing.md"
            missing.write_text("# Missing", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])
            missing.unlink()

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
            )

            rerun_manifest = json.loads(Path(envelope["error"]["details"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(code, 1)
            self.assertEqual(envelope["status"], "failed")
            self.assertEqual(rerun_manifest["status"], "failed")
            self.assertEqual(rerun_manifest["failures"][0]["error"]["code"], "E_INPUT_NOT_FOUND")

    def test_batch_rerun_rejects_changed_source_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            source = input_dir / "alpha.md"
            source.write_text("# Alpha", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])
            source.write_text("# Alpha changed", encoding="utf-8")

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
            )

            rerun_manifest = json.loads(Path(envelope["error"]["details"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(code, 1)
            self.assertEqual(envelope["status"], "failed")
            self.assertEqual(rerun_manifest["failures"][0]["error"]["code"], "E_SOURCE_CHANGED")

    def test_batch_rerun_rejects_unsafe_manifest_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            source = input_dir / "alpha.md"
            source.write_text("# Alpha", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["output_root"] = str(Path.home())
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
            )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_INVALID_OUTPUT_ROOT")

    def test_batch_rerun_rejects_manifest_paths_outside_cli_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boundary = root / "boundary"
            outside = root / "outside"
            input_dir = boundary / "sources"
            output_root = outside / "batch"
            boundary.mkdir()
            outside.mkdir()
            input_dir.mkdir()
            source = input_dir / "alpha.md"
            source.write_text("# Alpha", encoding="utf-8")
            manifest_path = boundary / "batch_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema": "kbprep.batch_manifest.v1",
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "items": [
                            {
                                "relative_path": "alpha.md",
                                "status": "failed",
                                "rerunnable": True,
                                "source_sha256": "not-used",
                            },
                        ],
                        "rerun": {"recommended_scope": "failed_only", "failed_only": ["alpha.md"]},
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"KBPREP_CLI_BOUNDARY_DIR": str(boundary)}):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
                )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_INVALID_OUTPUT_ROOT")

    def test_batch_rerun_rejects_forged_url_descriptor_without_playlist_source_collection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            source = input_dir / "lesson.url"
            source.write_text("[InternetShortcut]\nURL=https://www.youtube.com/watch?v=ExampleVideo01\n", encoding="utf-8")
            manifest_path = output_root / "batch_manifest.json"
            output_root.mkdir()
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema": "kbprep.batch_manifest.v1",
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "items": [
                            {
                                "relative_path": "lesson.url",
                                "status": "failed",
                                "rerunnable": True,
                                "source_sha256": prepare_batch._file_sha256(source),
                            },
                        ],
                        "rerun": {"recommended_scope": "failed_only", "failed_only": ["lesson.url"]},
                    }
                ),
                encoding="utf-8",
            )

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
            )

            rerun_manifest = json.loads(Path(envelope["error"]["details"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(code, 1)
            self.assertEqual(envelope["status"], "failed")
            self.assertEqual(rerun_manifest["failures"][0]["error"]["code"], "E_INVALID_INPUT")

    def test_batch_rerun_preserves_skipped_unsupported_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "archive.bin").write_text("skip", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])

            with patch.object(prepare_batch, "_process_one_file", side_effect=_successful_child):
                _code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
                )

            rerun_manifest = json.loads(Path(envelope["data"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(rerun_manifest["skipped_unsupported"], ["archive.bin"])

    def test_batch_rerun_with_no_selected_items_fails_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", side_effect=_successful_child):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["data"]["batch_manifest_json"])

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {"rerun": True, "batch_manifest_path": str(manifest_path), "min_free_memory_gb": 0},
            )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_BATCH_RERUN_EMPTY")

    def test_batch_rerun_rejects_bare_affected_scope_to_avoid_manifest_field_collision(self) -> None:
        # The bare scope name "affected" stays rejected on purpose: manifest already has a
        # rerun.affected field (failed+pending union). Policy-identity targeting uses the
        # distinct scope name "policy_affected" so the two cannot be confused.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {"rerun": True, "batch_manifest_path": str(manifest_path), "rerun_scope": "affected", "min_free_memory_gb": 0},
            )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_INVALID_INPUT")

    def test_batch_rerun_policy_affected_scope_rejects_without_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")

            with patch.object(prepare_batch, "_process_one_file", return_value={"ok": False, "error": {"code": "E_TEST"}}):
                _code, first = _capture_envelope(
                    prepare_batch.run,
                    {
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "force": True,
                        "min_free_memory_gb": 0,
                        "convert_jobs": 1,
                    },
                )
            manifest_path = Path(first["error"]["details"]["batch_manifest_json"])

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {
                    "rerun": True,
                    "batch_manifest_path": str(manifest_path),
                    "rerun_scope": "policy_affected",
                    "min_free_memory_gb": 0,
                },
            )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_INVALID_INPUT")
            self.assertIn("identity", envelope["error"]["message"].lower())

    def test_batch_rerun_policy_affected_scope_selects_matching_children_by_policy_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path, input_dir, _children = _build_policy_affected_fixture(Path(tmp))
            rerun_calls: list[str] = []

            def rerun_child(file_path: Path, out_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                rerun_calls.append(file_path.relative_to(input_dir).as_posix())
                return _successful_child(file_path, out_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=rerun_child):
                code, envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "rerun": True,
                        "batch_manifest_path": str(manifest_path),
                        "rerun_scope": "policy_affected",
                        "affected_policy_snapshot_hash": "hash-alpha",
                        "min_free_memory_gb": 0,
                    },
                )

            self.assertEqual(code, 0)
            self.assertEqual(rerun_calls, ["alpha.md"])
            rerun_manifest = json.loads(Path(envelope["data"]["batch_rerun_manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(rerun_manifest["scope"], "policy_affected")
            self.assertEqual(rerun_manifest["selected"], ["alpha.md"])

    def test_batch_rerun_policy_affected_scope_matches_by_document_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path, input_dir, children = _build_policy_affected_fixture(Path(tmp))
            rerun_calls: list[str] = []

            def rerun_child(file_path: Path, out_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                rerun_calls.append(file_path.relative_to(input_dir).as_posix())
                return _successful_child(file_path, out_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=rerun_child):
                code, _envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "rerun": True,
                        "batch_manifest_path": str(manifest_path),
                        "rerun_scope": "policy_affected",
                        "affected_document_id": children["beta.md"]["document_id"],
                        "min_free_memory_gb": 0,
                    },
                )

            self.assertEqual(code, 0)
            self.assertEqual(rerun_calls, ["beta.md"])

    def test_batch_rerun_policy_affected_scope_matches_failed_child_via_runs_scan_by_source_identity(self) -> None:
        # gamma is a failed child with no manifest run_id; its evidence is reached only by
        # scanning <output_root>/runs/*/. Match it via a stable source_identity field to prove
        # both the runs/ scan fallback and the source_identity matching dimension work.
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path, input_dir, _children = _build_policy_affected_fixture(Path(tmp))
            rerun_calls: list[str] = []

            def rerun_child(file_path: Path, out_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                rerun_calls.append(file_path.relative_to(input_dir).as_posix())
                return _successful_child(file_path, out_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=rerun_child):
                code, _envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "rerun": True,
                        "batch_manifest_path": str(manifest_path),
                        "rerun_scope": "policy_affected",
                        "affected_source_identity": {"source_domain": "gamma.example.com"},
                        "min_free_memory_gb": 0,
                    },
                )

            self.assertEqual(code, 0)
            self.assertEqual(rerun_calls, ["gamma.md"])

    def test_batch_rerun_policy_affected_scope_skips_child_without_run_evidence(self) -> None:
        # A failed child whose runs/ dir does not exist (early-stage failure) must be skipped
        # without crashing; children whose evidence is reachable and matches are still selected.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "sources"
            output_root = root / "batch"
            input_dir.mkdir()
            (input_dir / "alpha.md").write_text("# Alpha", encoding="utf-8")
            (input_dir / "gamma.md").write_text("# Gamma", encoding="utf-8")

            child_out_alpha = output_root / "files" / "alpha"
            _write_policy_affected_run_evidence(
                child_out_alpha / "runs" / "run_alpha",
                document_id="doc-alpha",
                policy_snapshot_hash="hash-alpha",
                source_identity={"source_name": "alpha.md"},
            )
            # gamma is a failed child whose output_root has no runs/ dir at all.
            child_out_gamma = output_root / "files" / "gamma"

            manifest_path = output_root / "batch_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema": "kbprep.batch_manifest.v1",
                        "input_dir": str(input_dir),
                        "output_root": str(output_root),
                        "items": [
                            {
                                "relative_path": "alpha.md",
                                "file": "alpha.md",
                                "status": "succeeded",
                                "run_id": "run_alpha",
                                "output_root": str(child_out_alpha),
                                "rerunnable": True,
                            },
                            {
                                "relative_path": "gamma.md",
                                "file": "gamma.md",
                                "status": "failed",
                                "output_root": str(child_out_gamma),
                                "rerunnable": True,
                            },
                        ],
                        "rerun": {"recommended_scope": "none"},
                    }
                ),
                encoding="utf-8",
            )

            rerun_calls: list[str] = []

            def rerun_child(file_path: Path, out_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                rerun_calls.append(file_path.relative_to(input_dir).as_posix())
                return _successful_child(file_path, out_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=rerun_child):
                code, _envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "rerun": True,
                        "batch_manifest_path": str(manifest_path),
                        "rerun_scope": "policy_affected",
                        "affected_policy_snapshot_hash": "hash-alpha",
                        "min_free_memory_gb": 0,
                    },
                )

            self.assertEqual(code, 0)
            self.assertEqual(rerun_calls, ["alpha.md"])

    def test_batch_rerun_policy_affected_scope_rejects_unstable_source_identity_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path, _input_dir, _children = _build_policy_affected_fixture(Path(tmp))

            code, envelope = _capture_envelope(
                prepare_batch.run,
                {
                    "rerun": True,
                    "batch_manifest_path": str(manifest_path),
                    "rerun_scope": "policy_affected",
                    "affected_source_identity": {"source_path": "/x/y.md"},
                    "min_free_memory_gb": 0,
                },
            )

            self.assertEqual(code, 1)
            self.assertEqual(envelope["error"]["code"], "E_INVALID_INPUT")
            self.assertIn("non-stable key", envelope["error"]["message"])

    def test_batch_rerun_policy_affected_scope_matches_by_multi_key_source_identity_subset(self) -> None:
        # Subset semantics: every supplied white-listed key must match. alpha matches both
        # source_name and source_domain; beta shares source_domain but differs in source_name,
        # so it must not be selected.
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path, input_dir, _children = _build_policy_affected_fixture(Path(tmp))
            rerun_calls: list[str] = []

            def rerun_child(file_path: Path, out_root: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                rerun_calls.append(file_path.relative_to(input_dir).as_posix())
                return _successful_child(file_path, out_root)

            with patch.object(prepare_batch, "_process_one_file", side_effect=rerun_child):
                code, _envelope = _capture_envelope(
                    prepare_batch.run,
                    {
                        "rerun": True,
                        "batch_manifest_path": str(manifest_path),
                        "rerun_scope": "policy_affected",
                        "affected_source_identity": {"source_name": "alpha.md", "source_domain": "example.com"},
                        "min_free_memory_gb": 0,
                    },
                )

            self.assertEqual(code, 0)
            self.assertEqual(rerun_calls, ["alpha.md"])

    def test_single_file_prepare_does_not_create_batch_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "guide.txt"
            output_root = root / "out"
            source.write_text("# Guide\n\nKeep SINGLE_PREP_MARKER.", encoding="utf-8")

            code, envelope = _capture_envelope(
                pipeline_core.run,
                {"input_path": str(source), "output_root": str(output_root), "force": True, "profile": "standard"},
            )

            self.assertEqual(code, 0)
            self.assertNotIn("batch_manifest_json", envelope["data"])
            self.assertFalse((output_root / "batch_manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
