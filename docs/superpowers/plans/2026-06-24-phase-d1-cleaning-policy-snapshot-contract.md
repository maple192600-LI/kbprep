# Phase D1 Cleaning Policy Snapshot Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete `CleaningPolicySnapshot` so every cleaning run records the active rule, dictionary, protection, disabled-rule, conflict, preference, and hash contract required before patch-based cleaning can be built.

**Architecture:** Keep the existing `policy_inputs.rule_routes` artifact for backward compatibility and add a `compiled_policy` section that is safe to publish in run artifacts. The compiled policy records ids and hashes only; it must not copy private rule bodies, private patterns, or source content into the snapshot.

**Tech Stack:** Python stdlib, existing KBPrep rule registry, existing rule loader/schema, `unittest`, existing npm script wrappers.

---

### Task 1: Contract Test

**Files:**
- Modify: `python/tests/test_cleaning_policy_snapshot.py`

- [x] **Step 1: Add failing coverage for the compiled policy contract**

Add a test that builds a base rule file, document-type rule file, private override, and accepted user rule, then asserts that `compiled_policy` exists and includes stable ids plus hashes without leaking private content.

```python
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
```

- [x] **Step 2: Run the focused test and confirm it fails for the expected reason**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_cleaning_policy_snapshot.CleaningPolicySnapshotTests.test_compiled_policy_records_ids_hashes_and_preferences_without_private_content -v
```

Expected: fail with missing `compiled_policy`.

### Task 2: Compiler Implementation

**Files:**
- Modify: `python/kbprep_worker/cleaning_policy_snapshot.py`

- [x] **Step 1: Add safe compiled-policy helpers**

Add helpers that summarize existing route snapshots and active accepted rules into ids and hashes. Use ids and source names only. Do not serialize private patterns, private keyword values, or source text.

- [x] **Step 2: Add `compiled_policy` to the snapshot payload**

`_snapshot_payload()` should compute `rule_routes` once, then include:

```python
"compiled_policy": _compiled_policy_summary(
    rule_routes=rule_routes,
    profile=profile,
    document_type=document_type,
    rule_templates=rule_templates,
),
```

- [x] **Step 3: Run the focused test and the existing snapshot tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_cleaning_policy_snapshot -v
```

Expected: all snapshot tests pass.

### Task 3: Planning And Status Alignment

**Files:**
- Modify: `docs/development/06-cleaning-policy-library.md`
- Modify: `docs/development/development-roadmap.md`
- Modify: `docs/development/kbprep-implementation-status.json`

- [x] **Step 1: Update D1 status text only after tests pass**

Mark `CleaningPolicySnapshot` as complete for the id/hash/preference contract while keeping later patch-gate work in D2-D6 unchanged.

- [x] **Step 2: Run development document checks**

Run:

```powershell
npm run check:development-docs
npm run check:flowchart
```

Expected: both pass.

### Task 4: Verification, Review, And Integration

**Files:**
- Verify all touched files.

- [x] **Step 1: Run quality checks**

Run:

```powershell
npm run python:ruff
npm run python:typecheck
npm run dev:check
```

Expected: all pass.

- [x] **Step 2: Request subagent review**

Ask a review subagent to check contract completeness, private-content leakage risk, compatibility with D2-D6, and test strength.

- [x] **Step 3: Fix review findings and rerun affected checks**

Every accepted review finding must have a targeted fix and a rerun of the focused test plus any affected check.

- [x] **Step 4: Commit, push, and integrate only after checks pass**

Create a focused commit on `codex/phase-d1-cleaning-policy-snapshot-contract`, push it, and merge only when local checks and remote CI are green.
