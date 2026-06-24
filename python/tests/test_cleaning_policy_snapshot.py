import contextlib
import hashlib
import json
import os
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path

from kbprep_worker.cleaning_policy_snapshot import (
    compile_cleaning_policy_snapshot,
    write_cleaning_policy_snapshot,
)


@contextlib.contextmanager
def _env(name: str, value: str) -> Iterator[None]:
    previous = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


@contextlib.contextmanager
def _cwd(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_lines(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line, ensure_ascii=False) for line in lines), encoding="utf-8")


def _accepted_rule(rule_id: str, document_type: str, pattern: str) -> dict:
    return {
        "schema": "kbprep.rule_proposal.v1",
        "id": rule_id,
        "status": "accepted",
        "accepted_rule_id": f"accepted-{rule_id}",
        "action": "discard",
        "scope": "document_type",
        "document_type": document_type,
        "match": "literal",
        "pattern": pattern,
        "reason": "sample-backed cleanup",
        "risk_note": "sample verified",
        "created_from_run": "run-1",
        "requires_confirmation": True,
        "owner_confirmation_status": "confirmed",
        "examples": [pattern],
        "counterexamples": ["正文内容"],
    }


def _accepted_source_rule(rule_id: str, source_pattern: str, pattern: str) -> dict:
    rule = _accepted_rule(rule_id, "course", pattern)
    rule["scope"] = "source_pattern"
    rule.pop("document_type")
    rule["source_pattern"] = source_pattern
    return rule


def _section_hash_fixture(rule_pattern: str, dictionary_value: str, protection_pattern: str) -> dict:
    return {
        "schema": "kbprep.cleaning_rules.v1",
        "rules": [{
            "type": "promotional_line",
            "id": "base.discard.cta",
            "action": "discard",
            "match": "literal",
            "pattern": rule_pattern,
            "reason": "generic",
            "risk_tag": "marketing",
        }],
        "keyword_sets": {
            "cta_keywords": [dictionary_value],
            "protected_patterns": [{"label": "formula", "pattern": protection_pattern}],
        },
    }


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _route_by_kind(snapshot: dict, kind: str) -> dict:
    for route in snapshot["policy_inputs"]["rule_routes"]:
        if route["kind"] == kind:
            return route
    raise AssertionError(f"missing route kind: {kind}")


def _route_by_source(snapshot: dict, source: str) -> dict:
    for route in snapshot["policy_inputs"]["rule_routes"]:
        if route["source"] == source:
            return route
    raise AssertionError(f"missing route source: {source}")


class CleaningPolicySnapshotTests(unittest.TestCase):
    def test_compiles_schema_inputs_thresholds_and_rule_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_root = root / "rules"
            base_path = rules_root / "base" / "obvious_noise.json"
            course_path = rules_root / "document_types" / "course.json"
            _write_json(base_path, {"schema": "test.rules", "marker": "base-v1"})
            _write_json(course_path, {"schema": "test.rules", "marker": "course-v1"})

            with _env("KBPREP_RULES_ROOT", str(rules_root)), _cwd(root):
                result = compile_cleaning_policy_snapshot(
                    profile="standard",
                    document_type="course",
                    source_identity={"source_name": "lesson.md", "source_domain": "example.com"},
                    source_quality="good",
                )
            expected_base_sha = _file_sha256(base_path)

        snapshot = result.snapshot
        base_route = _route_by_kind(snapshot, "base")
        self.assertEqual(snapshot["schema"], "kbprep.cleaning_policy_snapshot.v1")
        self.assertEqual(snapshot["policy_inputs"]["profile"], "standard")
        self.assertEqual(snapshot["policy_inputs"]["document_type"], "course")
        self.assertEqual(snapshot["thresholds"]["cleaning"]["discard_ratio_strict"], 0.45)
        self.assertEqual(snapshot["thresholds"]["review"]["review_pack_low_confidence"], 0.76)
        self.assertEqual(snapshot["thresholds"]["review_pack_low_confidence_threshold"], 0.76)
        self.assertEqual(base_route["sha256"], expected_base_sha)
        self.assertEqual(len(snapshot["policy_inputs"]["source_identity"]["sha256"]), 64)
        self.assertEqual(len(result.snapshot_hash), 64)

    def test_private_template_override_records_resolved_path_without_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_root = root / "rules"
            private_path = root / ".kbprep" / "rules" / "templates" / "self_media_course.json"
            _write_json(rules_root / "base" / "obvious_noise.json", {"schema": "test.rules"})
            _write_json(rules_root / "templates" / "self_media_course.json", {"marker": "public"})
            _write_json(private_path, {"marker": "DO_NOT_LEAK_PRIVATE_RULE_BODY"})

            with _env("KBPREP_RULES_ROOT", str(rules_root)), _cwd(root):
                result = compile_cleaning_policy_snapshot(
                    profile="curated_obsidian_kb",
                    document_type="course",
                    source_identity={},
                )
            expected_private_sha = _file_sha256(private_path)

        template_route = _route_by_kind(result.snapshot, "profile_template")
        serialized = json.dumps(result.snapshot, ensure_ascii=False)
        self.assertEqual(Path(template_route["path"]), private_path)
        self.assertEqual(template_route["source"], ".kbprep/rules/templates/self_media_course.json")
        self.assertEqual(template_route["sha256"], expected_private_sha)
        self.assertNotIn("DO_NOT_LEAK_PRIVATE_RULE_BODY", serialized)

    def test_explicit_cwd_controls_project_private_template_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "project"
            other_root = root / "other"
            rules_root = root / "rules"
            private_path = project_root / ".kbprep" / "rules" / "templates" / "self_media_course.json"
            wrong_private_path = other_root / ".kbprep" / "rules" / "templates" / "self_media_course.json"
            _write_json(rules_root / "base" / "obvious_noise.json", {"schema": "test.rules"})
            _write_json(rules_root / "templates" / "self_media_course.json", {"marker": "public"})
            _write_json(private_path, {"marker": "expected-private"})
            _write_json(wrong_private_path, {"marker": "wrong-private"})

            with _env("KBPREP_RULES_ROOT", str(rules_root)), _cwd(other_root):
                result = compile_cleaning_policy_snapshot(
                    profile="curated_obsidian_kb",
                    document_type="course",
                    source_identity={},
                    cwd=project_root,
                )
            expected_private_sha = _file_sha256(private_path)
            expected_private_path = private_path

        template_route = _route_by_kind(result.snapshot, "profile_template")
        self.assertEqual(Path(template_route["path"]), expected_private_path)
        self.assertEqual(template_route["sha256"], expected_private_sha)

    def test_private_document_type_dictionary_records_path_without_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_root = root / "rules"
            private_path = root / ".kbprep" / "rules" / "document_types" / "report.json"
            _write_json(rules_root / "base" / "obvious_noise.json", {"schema": "test.rules"})
            _write_json(rules_root / "document_types" / "report.json", {"marker": "public"})
            _write_json(private_path, {"marker": "DO_NOT_LEAK_PRIVATE_DOCUMENT_TYPE_RULE"})

            with _env("KBPREP_RULES_ROOT", str(rules_root)), _cwd(root):
                result = compile_cleaning_policy_snapshot(
                    profile="standard",
                    document_type="report",
                    source_identity={},
                )
            expected_private_sha = _file_sha256(private_path)

        private_route = _route_by_source(result.snapshot, ".kbprep/rules/document_types/report.json")
        serialized = json.dumps(result.snapshot, ensure_ascii=False)
        self.assertEqual(Path(private_route["path"]), private_path)
        self.assertEqual(private_route["kind"], "document_type")
        self.assertEqual(private_route["sha256"], expected_private_sha)
        self.assertNotIn("DO_NOT_LEAK_PRIVATE_DOCUMENT_TYPE_RULE", serialized)

    def test_accepted_rule_hash_uses_active_rules_for_current_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_root = root / "rules"
            user_rules = root / "user-rules"
            accepted_path = user_rules / "accepted_rules.jsonl"
            _write_json(rules_root / "base" / "obvious_noise.json", {"schema": "test.rules"})
            _write_lines(accepted_path, [_accepted_rule("interview-1", "interview", "访谈广告")])

            with (
                _env("KBPREP_RULES_ROOT", str(rules_root)),
                _env("KBPREP_USER_RULES_DIR", str(user_rules)),
                _cwd(root),
            ):
                first = compile_cleaning_policy_snapshot(
                    profile="standard",
                    document_type="course",
                    source_identity={},
                )
                _write_lines(accepted_path, [_accepted_rule("interview-2", "interview", "另一个访谈广告")])
                second = compile_cleaning_policy_snapshot(
                    profile="standard",
                    document_type="course",
                    source_identity={},
                )
                _write_lines(accepted_path, [_accepted_rule("course-1", "course", "课程广告")])
                third = compile_cleaning_policy_snapshot(
                    profile="standard",
                    document_type="course",
                    source_identity={},
                )

        self.assertEqual(first.snapshot_hash, second.snapshot_hash)
        self.assertNotEqual(second.snapshot_hash, third.snapshot_hash)
        accepted_route = _route_by_kind(third.snapshot, "accepted_user")
        self.assertEqual(accepted_route["hash_scope"], "active_accepted_rules")
        self.assertEqual(accepted_route["active_rule_count"], 1)

    def test_accepted_rule_hash_filters_source_pattern_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_root = root / "rules"
            user_rules = root / "user-rules"
            accepted_path = user_rules / "accepted_rules.jsonl"
            _write_json(rules_root / "base" / "obvious_noise.json", {"schema": "test.rules"})
            _write_lines(accepted_path, [_accepted_source_rule("other-1", "source_domain:other.example", "其他广告")])

            with (
                _env("KBPREP_RULES_ROOT", str(rules_root)),
                _env("KBPREP_USER_RULES_DIR", str(user_rules)),
                _cwd(root),
            ):
                source_identity = {"source_domain": "course.example", "source_name": "lesson.md"}
                first = compile_cleaning_policy_snapshot(
                    profile="standard",
                    document_type="course",
                    source_identity=source_identity,
                )
                _write_lines(accepted_path, [_accepted_source_rule("other-2", "source_domain:other.example", "更多广告")])
                second = compile_cleaning_policy_snapshot(
                    profile="standard",
                    document_type="course",
                    source_identity=source_identity,
                )
                _write_lines(accepted_path, [_accepted_source_rule("course-source", "source_domain:course.example", "课程广告")])
                third = compile_cleaning_policy_snapshot(
                    profile="standard",
                    document_type="course",
                    source_identity=source_identity,
                )

        self.assertEqual(first.snapshot_hash, second.snapshot_hash)
        self.assertNotEqual(second.snapshot_hash, third.snapshot_hash)
        accepted_route = _route_by_kind(third.snapshot, "accepted_user")
        self.assertEqual(accepted_route["active_rule_count"], 1)

    def test_compiled_policy_records_ids_hashes_and_preferences_without_private_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_root = root / "rules"
            user_rules = root / "user-rules"
            private_path = root / ".kbprep" / "rules" / "document_types" / "course.json"
            accepted_path = user_rules / "accepted_rules.jsonl"
            _write_json(rules_root / "base" / "obvious_noise.json", {
                "schema": "kbprep.cleaning_rules.v1",
                "rules": [{
                    "type": "promotional_line",
                    "id": "base.discard.cta",
                    "action": "discard",
                    "match": "literal",
                    "pattern": "generic cta",
                    "reason": "generic",
                    "risk_tag": "marketing",
                }],
                "keyword_sets": {
                    "cta_keywords": ["cta"],
                    "protected_patterns": [{"label": "formula", "pattern": "E=mc2"}],
                },
            })
            _write_json(rules_root / "document_types" / "course.json", {
                "schema": "kbprep.cleaning_rules.v1",
                "rules": [],
                "keyword_sets": {"knowledge_terms": ["lesson"]},
            })
            _write_json(private_path, {
                "schema": "kbprep.cleaning_rules.v1",
                "rules": [],
                "keyword_sets": {"marketing_wrapper_line_patterns": ["DO_NOT_LEAK_PRIVATE_PATTERN"]},
            })
            _write_lines(accepted_path, [_accepted_rule("course-accepted", "course", "private accepted pattern")])

            with (
                _env("KBPREP_RULES_ROOT", str(rules_root)),
                _env("KBPREP_USER_RULES_DIR", str(user_rules)),
                _cwd(root),
            ):
                result = compile_cleaning_policy_snapshot(
                    profile="standard",
                    document_type="course",
                    source_identity={"source_name": "lesson.md"},
                )

        policy = result.snapshot["compiled_policy"]
        self.assertEqual(policy["schema"], "kbprep.compiled_cleaning_policy.v1")
        self.assertIn("base.discard.cta", policy["active_rule_ids"])
        self.assertIn("accepted-course-accepted", policy["active_rule_ids"])
        self.assertIn("cta_keywords", policy["active_dictionary_ids"])
        self.assertIn("protected_patterns:formula", policy["active_protection_ids"])
        self.assertEqual(policy["disabled_rule_ids"], [])
        self.assertEqual(policy["conflict_resolutions"], [])
        self.assertEqual(policy["preferences"]["profile"], "standard")
        self.assertEqual(policy["preferences"]["document_type"], "course")
        self.assertEqual(len(policy["rule_set_hash"]), 64)
        self.assertEqual(len(policy["dictionary_hash"]), 64)
        self.assertEqual(len(policy["protection_hash"]), 64)
        serialized = json.dumps(result.snapshot, ensure_ascii=False)
        self.assertNotIn("DO_NOT_LEAK_PRIVATE_PATTERN", serialized)
        self.assertNotIn("private accepted pattern", serialized)

    def test_compiled_policy_section_hashes_change_only_for_their_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_root = root / "rules"
            base_path = rules_root / "base" / "obvious_noise.json"
            first_payload = _section_hash_fixture("rule-v1", "dictionary-v1", "protection-v1")
            _write_json(base_path, first_payload)

            with _env("KBPREP_RULES_ROOT", str(rules_root)), _cwd(root):
                first = compile_cleaning_policy_snapshot(profile="standard", document_type="", source_identity={})
                _write_json(base_path, _section_hash_fixture("rule-v2", "dictionary-v1", "protection-v1"))
                rule_changed = compile_cleaning_policy_snapshot(profile="standard", document_type="", source_identity={})
                _write_json(base_path, _section_hash_fixture("rule-v2", "dictionary-v2", "protection-v1"))
                dictionary_changed = compile_cleaning_policy_snapshot(profile="standard", document_type="", source_identity={})
                _write_json(base_path, _section_hash_fixture("rule-v2", "dictionary-v2", "protection-v2"))
                protection_changed = compile_cleaning_policy_snapshot(profile="standard", document_type="", source_identity={})

        first_policy = first.snapshot["compiled_policy"]
        rule_policy = rule_changed.snapshot["compiled_policy"]
        dictionary_policy = dictionary_changed.snapshot["compiled_policy"]
        protection_policy = protection_changed.snapshot["compiled_policy"]
        self.assertNotEqual(first_policy["rule_set_hash"], rule_policy["rule_set_hash"])
        self.assertEqual(first_policy["dictionary_hash"], rule_policy["dictionary_hash"])
        self.assertEqual(first_policy["protection_hash"], rule_policy["protection_hash"])
        self.assertNotEqual(rule_policy["dictionary_hash"], dictionary_policy["dictionary_hash"])
        self.assertEqual(rule_policy["protection_hash"], dictionary_policy["protection_hash"])
        self.assertNotEqual(dictionary_policy["protection_hash"], protection_policy["protection_hash"])

    def test_compiled_policy_records_disabled_rules_and_conflict_resolutions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_root = root / "rules"
            _write_json(rules_root / "base" / "obvious_noise.json", {
                "schema": "kbprep.cleaning_rules.v1",
                "rules": [
                    {
                        "type": "promotional_line",
                        "id": "base.discard.enabled",
                        "action": "discard",
                        "match": "literal",
                        "pattern": "enabled",
                        "reason": "enabled",
                        "risk_tag": "marketing",
                    },
                    {
                        "type": "promotional_line",
                        "id": "base.discard.disabled",
                        "action": "discard",
                        "match": "literal",
                        "pattern": "disabled",
                        "reason": "disabled",
                        "risk_tag": "marketing",
                        "enabled": False,
                    },
                ],
                "keyword_sets": {},
                "conflict_resolutions": [{
                    "winner_rule_id": "base.protect.body",
                    "loser_rule_id": "base.discard.enabled",
                    "resolution": "protection_wins",
                    "pattern": "DO_NOT_LEAK_CONFLICT_PATTERN",
                }],
            })

            with _env("KBPREP_RULES_ROOT", str(rules_root)), _cwd(root):
                result = compile_cleaning_policy_snapshot(profile="standard", document_type="", source_identity={})

        policy = result.snapshot["compiled_policy"]
        self.assertIn("base.discard.disabled", policy["disabled_rule_ids"])
        self.assertEqual(policy["conflict_resolutions"], [{
            "loser_rule_id": "base.discard.enabled",
            "resolution": "protection_wins",
            "winner_rule_id": "base.protect.body",
        }])
        self.assertNotIn("base.discard.disabled", policy["active_rule_ids"])
        self.assertNotIn("DO_NOT_LEAK_CONFLICT_PATTERN", json.dumps(result.snapshot, ensure_ascii=False))

    def test_rule_content_change_changes_snapshot_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_root = root / "rules"
            base_path = rules_root / "base" / "obvious_noise.json"
            _write_json(base_path, {"schema": "test.rules", "marker": "v1"})
            with _env("KBPREP_RULES_ROOT", str(rules_root)), _cwd(root):
                first = compile_cleaning_policy_snapshot(profile="standard", document_type="", source_identity={})
                _write_json(base_path, {"schema": "test.rules", "marker": "v2"})
                second = compile_cleaning_policy_snapshot(profile="standard", document_type="", source_identity={})

        self.assertNotEqual(first.snapshot_hash, second.snapshot_hash)

    def test_write_snapshot_writes_run_artifact_and_returns_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_root = root / "rules"
            run_dir = root / "run"
            _write_json(rules_root / "base" / "obvious_noise.json", {"schema": "test.rules", "marker": "v1"})
            with _env("KBPREP_RULES_ROOT", str(rules_root)), _cwd(root):
                result = write_cleaning_policy_snapshot(
                    run_dir,
                    profile="standard",
                    document_type="",
                    source_identity={"source_name": "note.md"},
                    source_quality="",
                )
                artifact = json.loads(result.path.read_text(encoding="utf-8"))

        self.assertEqual(result.path, run_dir / "cleaning_policy_snapshot.json")
        self.assertEqual(artifact["snapshot_hash"], result.snapshot_hash)
        self.assertEqual(artifact["policy_inputs"]["source_identity"]["source_name"], "note.md")


if __name__ == "__main__":
    unittest.main()
