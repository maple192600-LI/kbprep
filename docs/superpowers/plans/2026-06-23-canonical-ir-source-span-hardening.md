# Canonical IR SourceSpan Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every discovered Canonical IR TypedNode and SourceSpan issue: precision regression coverage, transcript cue encoding/timing integrity, speaker-prefix false positives, notebook source kind, WebVTT cue settings, cue reorder safety, source-span manifest consistency, conversion-route consistency, cue identifier safety, and stale historical plan drift.

**Architecture:** Keep the Canonical IR artifact model conservative: never invent source evidence, never attach native cue timing when raw evidence is ambiguous, and keep manifest coverage aligned with artifact reality. The changes stay inside the Canonical IR builder/parser/validator layer plus tests and non-protected planning docs.

**Tech Stack:** Python 3 project environment via `node scripts/python-venv.mjs`, `unittest`, KBPrep worker modules under `python/kbprep_worker`, npm project checks.

---

## Non-Deferral Rule For This Plan

Priority in this plan means repair order only. Every issue listed below must be fixed before the branch is complete. No item may be downgraded to "document only", "later", "known issue", or "follow-up" unless a real boundary appears: explicit owner authorization, external access missing, real cost, production/real-data risk, or unverifiable behavior outside this repository.

Every development stage below ends with an independent review subagent. The implementer must not self-review as the only review.

## Verified Current Evidence

- `python/kbprep_worker/canonical_transcripts.py` reads cue files as UTF-8 only and returns `[]` on `UnicodeDecodeError`, so GBK SRT timing can be silently lost.
- `python/kbprep_worker/converters/direct.py` already has fallback source reading for direct conversion, so the converted Markdown may exist while Canonical IR cue timing disappears.
- `python/kbprep_worker/canonical_nodes.py` speaker detection is broad enough to treat non-speaker colon prose such as `注意: 这是说明` as `transcript_cue` when no raw cue list is available.
- `python/kbprep_worker/canonical_nodes.py` matches raw cue texts by searching unused cues globally, so reordered converted cue text can receive later cue timing.
- `python/kbprep_worker/canonical_spans.py` has the three precision validators, but tests only lock one negative direction.
- `python/kbprep_worker/canonical_spans.py` maps `.ipynb` through `structured_data`; this makes notebook source kind semantically ambiguous.
- `python/kbprep_worker/canonical_transcripts.py` parses only start and end timestamps from WebVTT/SRT timing lines and drops WebVTT cue settings.
- `python/kbprep_worker/canonical_transcripts.py` treats the line before a timing line as a cue identifier without filtering WebVTT headers/directives.
- `python/kbprep_worker/canonical_spans.py` validates `artifacts.source_spans` vs `coverage.source_spans_available`, but the reverse artifact-present/coverage-false path needs a direct regression test.
- `python/kbprep_worker/canonical_ir.py` currently derives SourceSpan `conversion_route` from `route_decision.actual_route` with a fallback to `conversion_report.converter`; this needs a named helper and tests so route semantics stay consistent.
- `docs/superpowers/plans/2026-06-22-canonical-ir-typed-nodes.md` still contains historical statements that `source_spans_available` remains false; that is stale after the SourceSpan artifact slice.

## File Structure

- Modify: `python/kbprep_worker/canonical_transcripts.py`
  - Own SRT/WebVTT cue parsing, encoding fallback, cue identifier filtering, and WebVTT cue settings capture.
- Modify: `python/kbprep_worker/canonical_nodes.py`
  - Own TypedNode building, sequence-aware raw cue matching, and stricter speaker-prefix classification.
- Modify: `python/kbprep_worker/canonical_spans.py`
  - Own SourceSpan source kind mapping, WebVTT cue settings propagation, precision schema support, and validation.
- Modify: `python/kbprep_worker/canonical_ir.py`
  - Own canonical conversion route/converter extraction for manifest and SourceSpan writing.
- Create: `python/tests/test_canonical_transcripts.py`
  - Focused cue parsing and encoding fallback regression coverage.
- Modify: `python/tests/test_canonical_ir_typed_nodes.py`
  - TypedNode speaker-prefix and cue-order regression coverage.
- Modify: `python/tests/test_canonical_ir_source_spans.py`
  - SourceSpan notebook kind, GBK timing, WebVTT settings, and reorder behavior coverage.
- Modify: `python/tests/test_canonical_ir_schema.py`
  - Manifest consistency and precision/location mutual-exclusion regression coverage.
- Modify: `docs/superpowers/plans/2026-06-22-canonical-ir-typed-nodes.md`
  - Mark the old C1 plan as superseded for SourceSpan coverage statements so historical notes no longer contradict shipped behavior.

## Task 1: Transcript Cue Parser Encoding, Cue Settings, And Safe IDs

**Files:**
- Modify: `python/kbprep_worker/canonical_transcripts.py`
- Create: `python/tests/test_canonical_transcripts.py`

- [ ] **Step 1: Write failing tests for encoding fallback, WebVTT settings, and cue id filtering**

Create `python/tests/test_canonical_transcripts.py`:

```python
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.canonical_transcripts import parse_transcript_cues, read_transcript_cues


class CanonicalTranscriptTests(unittest.TestCase):
    def test_reads_gbk_srt_without_losing_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "lesson.srt"
            source.write_bytes(
                "\n".join([
                    "1",
                    "00:00:01,000 --> 00:00:03,000",
                    "主持人: 欢迎开始",
                ]).encode("gbk")
            )

            cues = read_transcript_cues(source)

        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].cue_id, "1")
        self.assertEqual(cues[0].start_time, "00:00:01,000")
        self.assertEqual(cues[0].end_time, "00:00:03,000")
        self.assertEqual(cues[0].text, "主持人: 欢迎开始")

    def test_preserves_webvtt_cue_settings(self) -> None:
        cues = parse_transcript_cues(
            "\n".join([
                "WEBVTT",
                "",
                "intro",
                "00:00:01.000 --> 00:00:03.000 align:start position:0%",
                "Host: Welcome",
            ])
        )

        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].cue_id, "intro")
        self.assertEqual(cues[0].settings, "align:start position:0%")

    def test_does_not_use_webvtt_header_as_cue_identifier(self) -> None:
        cues = parse_transcript_cues(
            "\n".join([
                "WEBVTT",
                "00:00:01.000 --> 00:00:03.000",
                "Host: Welcome",
            ])
        )

        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].cue_id, "1")

    def test_does_not_use_webvtt_directive_as_cue_identifier(self) -> None:
        cues = parse_transcript_cues(
            "\n".join([
                "NOTE generated by tool",
                "00:00:01.000 --> 00:00:03.000",
                "Host: Welcome",
            ])
        )

        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].cue_id, "1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the target test and verify it fails before implementation**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_transcripts -v
```

Expected before implementation: failures because GBK reads return no cues, `TranscriptCue` has no `settings`, and `WEBVTT` can be used as a cue id.

- [ ] **Step 3: Implement encoding fallback, settings, and id filtering**

In `python/kbprep_worker/canonical_transcripts.py`, replace the current timing regex/dataclass/read helper/cue-id helper with this shape:

```python
_TRANSCRIPT_ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "gb2312")
_TIMING_RE = re.compile(
    r"^\s*(?P<start>\S+)\s+-->\s+(?P<end>\S+)(?:\s+(?P<settings>.+?))?\s*$"
)
_WEBVTT_DIRECTIVES = ("WEBVTT", "NOTE", "STYLE", "REGION")
_CUE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


@dataclass(frozen=True)
class TranscriptCue:
    cue_id: str
    start_time: str
    end_time: str
    text: str
    settings: str = ""


def read_transcript_cues(input_path: Path) -> list[TranscriptCue]:
    """Read SRT/WebVTT-style timed cues from a source transcript file."""
    try:
        raw = input_path.read_bytes()
    except OSError:
        return []
    for encoding in _TRANSCRIPT_ENCODINGS:
        try:
            return parse_transcript_cues(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    return []
```

Update `_parse_transcript_block`:

```python
def _parse_transcript_block(lines: list[str], fallback_index: int) -> TranscriptCue | None:
    for index, line in enumerate(lines):
        timing = _TIMING_RE.match(line)
        if timing is None:
            continue
        return TranscriptCue(
            cue_id=_cue_identifier(lines, index, fallback_index),
            start_time=timing.group("start"),
            end_time=timing.group("end"),
            text=" ".join(lines[index + 1 :]).strip(),
            settings=(timing.group("settings") or "").strip(),
        )
    return None
```

Update `_cue_identifier` and add `_is_valid_cue_identifier`:

```python
def _cue_identifier(lines: list[str], timing_index: int, fallback_index: int) -> str:
    if timing_index > 0:
        candidate = lines[timing_index - 1].strip()
        if _is_valid_cue_identifier(candidate):
            return candidate
    return str(fallback_index)


def _is_valid_cue_identifier(candidate: str) -> bool:
    if not candidate or "-->" in candidate or len(candidate) > 120:
        return False
    upper = candidate.upper()
    first_token = upper.split(maxsplit=1)[0]
    return first_token not in _WEBVTT_DIRECTIVES and _CUE_IDENTIFIER_RE.match(candidate) is not None
```

Cue identifiers are intentionally restricted to short ASCII identifier tokens such as `1`, `intro`, or `cue-01`.
Plain dialogue/prose lines like `Host: Welcome to the lesson.` must fall back to the deterministic cue index instead of becoming `cue_id`.

- [ ] **Step 4: Run parser tests until they pass**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_transcripts -v
```

Expected after implementation: `OK`.

- [ ] **Step 5: Run independent subagent review for Task 1**

Dispatch a fresh review subagent with this exact brief:

```text
Review Task 1 only. Check python/kbprep_worker/canonical_transcripts.py and python/tests/test_canonical_transcripts.py. Verify that non-UTF-8 SRT cue timing is preserved, WebVTT settings are captured without inventing data, invalid WebVTT headers/directives are not used as cue identifiers, and the parser still returns [] only for unreadable files. Report concrete file/line issues only.
```

Task 1 is not complete until the review is clean or every review finding is fixed and re-reviewed.

## Task 2: TypedNode Transcript Classification Safety

**Files:**
- Modify: `python/kbprep_worker/canonical_nodes.py`
- Modify: `python/tests/test_canonical_ir_typed_nodes.py`

- [ ] **Step 1: Add failing tests for false speaker prefixes and reordered raw cues**

Append these tests to `CanonicalIrTypedNodeTests`:

```python
    def test_parser_does_not_treat_generic_colon_notice_as_speaker_cue(self) -> None:
        markdown = "注意: 这是说明\n\nHost: Welcome\n"

        nodes = build_typed_nodes_from_markdown(markdown, source_type="subtitle_transcript")

        self.assertEqual([node.node_type for node in nodes], ["paragraph", "transcript_cue"])
        self.assertEqual(nodes[0].metadata, {})
        self.assertEqual(nodes[1].metadata, {"cue_index": 1, "speaker": "Host"})

    def test_parser_allows_common_asr_speaker_labels_without_raw_cues(self) -> None:
        markdown = "Speaker 1: Welcome\n\n主持人: 欢迎\n"

        nodes = build_typed_nodes_from_markdown(markdown, source_type="subtitle_transcript")

        self.assertEqual([node.node_type for node in nodes], ["transcript_cue", "transcript_cue"])
        self.assertEqual(nodes[0].metadata, {"cue_index": 1, "speaker": "Speaker 1"})
        self.assertEqual(nodes[1].metadata, {"cue_index": 2, "speaker": "主持人"})

    def test_parser_does_not_match_later_raw_cue_when_converted_text_is_reordered(self) -> None:
        markdown = "Guest: Second cue\n\nHost: First cue\n"

        nodes = build_typed_nodes_from_markdown(
            markdown,
            source_type="subtitle_transcript",
            transcript_cue_texts=["Host: First cue", "Guest: Second cue"],
        )

        self.assertEqual([node.node_type for node in nodes], ["paragraph", "transcript_cue"])
        self.assertEqual(nodes[0].metadata, {})
        self.assertEqual(nodes[1].metadata, {"cue_index": 1, "speaker": "Host"})
```

- [ ] **Step 2: Run the target test and verify it fails before implementation**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes -v
```

Expected before implementation: the generic notice is misclassified or the reordered cue is matched to cue 2.

- [ ] **Step 3: Implement stricter speaker labels and sequence-aware raw cue matching**

In `python/kbprep_worker/canonical_nodes.py`, add label allowlisting near `_SPEAKER_RE`:

```python
_SPEAKER_LABEL_RE = re.compile(
    r"^(?:"
    r"Speaker\s*[A-Za-z0-9]+|S\d+|[A-Z]|"
    r"Host|Guest|Interviewer|Interviewee|Moderator|Narrator|Teacher|Student|"
    r"主持人|嘉宾|访谈者|受访者|采访者|讲师|老师|学生|旁白|说话人|发言人"
    r")$",
    re.IGNORECASE,
)
```

In `build_typed_nodes_from_markdown`, replace the unordered `used_cue_indices` logic with a monotonic next-cue pointer:

```python
    next_cue_index = 1
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        start_index = index
        node_type, text, metadata, index = _consume_block(lines, index)
        if text.strip():
            if transcript_context and node_type == "paragraph":
                matched_cue_index = _matched_next_transcript_cue_index(text, cue_texts, next_cue_index)
                if matched_cue_index is not None:
                    next_cue_index = matched_cue_index + 1
                    node_type = "transcript_cue"
                    metadata = _transcript_metadata(text, matched_cue_index)
                elif not cue_texts and _speaker_name(text) is not None:
                    cue_index += 1
                    node_type = "transcript_cue"
                    metadata = _transcript_metadata(text, cue_index)
            nodes.append(_typed_node(len(nodes) + 1, node_type, text, metadata, start_index + 1, index))
```

Replace `_matched_transcript_cue_index` with sequence-aware matching:

```python
def _matched_next_transcript_cue_index(
    text: str,
    cue_texts: tuple[str, ...],
    next_index: int,
    *,
    remaining_candidates: Mapping[str, int],
) -> int | None:
    if not cue_texts or next_index < 1 or next_index > len(cue_texts):
        return None
    candidates = _transcript_match_candidates(text)
    if cue_texts[next_index - 1] in candidates:
        return next_index
    for index in range(next_index + 1, len(cue_texts) + 1):
        if cue_texts[index - 1] in candidates:
            skipped_cues = cue_texts[next_index - 1 : index - 1]
            if any(remaining_candidates.get(cue_text, 0) > 0 for cue_text in skipped_cues):
                return None
            return index
    return None
```

This allows deleted raw cues to be skipped only when the skipped cue text does not appear later in the converted transcript.
If a skipped raw cue appears later, the current cue is treated as reordered text and stays without transcript timing.

Update `_strip_speaker_prefix` and `_speaker_name` to only accept likely speaker labels:

```python
def _strip_speaker_prefix(text: str) -> str:
    match = _SPEAKER_RE.match(text)
    if match is None or not _is_likely_speaker_label(match.group(1).strip()):
        return text
    return text[match.end() :].strip()


def _speaker_name(text: str) -> str | None:
    match = _SPEAKER_RE.match(text)
    if match is None:
        return None
    speaker = match.group(1).strip()
    return speaker if _is_likely_speaker_label(speaker) else None


def _is_likely_speaker_label(label: str) -> bool:
    return bool(_SPEAKER_LABEL_RE.match(label.strip()))
```

- [ ] **Step 4: Run typed-node tests until they pass**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_typed_nodes -v
```

Expected after implementation: `OK`.

- [ ] **Step 5: Run independent subagent review for Task 2**

Dispatch a fresh review subagent with this brief:

```text
Review Task 2 only. Check transcript classification in python/kbprep_worker/canonical_nodes.py and tests in python/tests/test_canonical_ir_typed_nodes.py. Verify raw cue matching is sequence-aware and cannot attach timing to later cues when converted text is reordered. Verify stricter speaker prefix logic avoids generic colon prose while preserving common ASR labels. Report concrete file/line issues only.
```

Task 2 is not complete until the review is clean or every review finding is fixed and re-reviewed.

## Task 3: SourceSpan Evidence Schema And Builder Hardening

**Files:**
- Modify: `python/kbprep_worker/canonical_spans.py`
- Modify: `python/tests/test_canonical_ir_source_spans.py`

- [ ] **Step 1: Add failing tests for GBK timing, WebVTT settings propagation, notebook kind, and reorder safety**

Append these tests to `CanonicalIrSourceSpanTests`:

```python
    def test_gbk_srt_source_spans_keep_transcript_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "lesson.srt"
            converted = run_dir / "converted.md"
            source.write_bytes(
                "\n".join([
                    "1",
                    "00:00:01,000 --> 00:00:03,000",
                    "主持人: 欢迎开始",
                ]).encode("gbk")
            )
            converted.write_text("主持人: 欢迎开始\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="subtitle_transcript",
                converter="direct_text",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["source_kind"], "transcript")
        self.assertEqual(payload["spans"][0]["location"]["start_time"], "00:00:01,000")
        self.assertEqual(payload["spans"][0]["evidence"]["precision"], "transcript_cue_timing")

    def test_webvtt_source_spans_include_cue_settings_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "lesson.vtt"
            converted = run_dir / "converted.md"
            source.write_text(
                "\n".join([
                    "WEBVTT",
                    "",
                    "intro",
                    "00:00:01.000 --> 00:00:03.000 align:start position:0%",
                    "Host: Welcome",
                ]),
                encoding="utf-8",
            )
            converted.write_text("Host: Welcome\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="subtitle_transcript",
                converter="direct_text",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["location"]["cue_id"], "intro")
        self.assertEqual(payload["spans"][0]["location"]["cue_settings"], "align:start position:0%")

    def test_ipynb_source_spans_use_notebook_source_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "analysis.ipynb"
            converted = run_dir / "converted.md"
            source.write_text('{"cells":[]}', encoding="utf-8")
            converted.write_text("# Notebook\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="structured_data",
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="structured_data",
                converter="notebook_json",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["source_kind"], "notebook")
        self.assertEqual(payload["spans"][0]["evidence"]["source_kind"], "notebook")

    def test_reordered_transcript_text_does_not_attach_later_cue_timing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "lesson.srt"
            converted = run_dir / "converted.md"
            source.write_text(
                "\n".join([
                    "1",
                    "00:00:01,000 --> 00:00:03,000",
                    "Host: First cue",
                    "",
                    "2",
                    "00:00:04,000 --> 00:00:06,000",
                    "Guest: Second cue",
                ]),
                encoding="utf-8",
            )
            converted.write_text("Guest: Second cue\n\nHost: First cue\n", encoding="utf-8")
            typed_nodes = write_typed_nodes_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                converted_path=converted,
                source_type="subtitle_transcript",
                input_path=source,
            )

            artifact = write_source_spans_artifact(
                run_dir=run_dir,
                document_id="doc_test",
                input_path=source,
                converted_path=converted,
                typed_nodes_path=typed_nodes,
                source_type="subtitle_transcript",
                converter="direct_text",
                conversion_route="direct_text",
            )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["spans"][0]["source_kind"], "converted_markdown")
        self.assertNotIn("start_time", payload["spans"][0]["location"])
        self.assertEqual(payload["spans"][1]["source_kind"], "transcript")
        self.assertEqual(payload["spans"][1]["location"]["cue_id"], "1")
```

- [ ] **Step 2: Run the target test and verify it fails before implementation**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_source_spans -v
```

Expected before implementation: failures for GBK timing, WebVTT `cue_settings`, notebook source kind, or reordered cue behavior.

- [ ] **Step 3: Implement notebook source kind and cue settings propagation**

In `python/kbprep_worker/canonical_spans.py`, add `notebook`:

```python
SUPPORTED_SOURCE_KINDS = frozenset({
    "converted_markdown",
    "markdown_text",
    "transcript",
    "pdf",
    "docx",
    "pptx",
    "xlsx",
    "html",
    "epub",
    "structured_data",
    "notebook",
    "code",
    "youtube",
    "unknown",
})
```

Update `_source_kind` so notebooks are not folded into generic structured data:

```python
def _source_kind(input_path: Path, source_type: str, converter: str, conversion_route: str) -> str:
    ext = input_path.suffix.lower()
    if ext in SUBTITLE_EXTENSIONS or _is_transcript_context(source_type, conversion_route):
        return "transcript"
    if ext in NOTEBOOK_EXTENSIONS:
        return "notebook"
    if ext in TABLE_TEXT_EXTENSIONS or ext in JSON_EXTENSIONS:
        return "structured_data"
    if ext in MARKDOWN_EXTENSIONS | PLAIN_TEXT_EXTENSIONS:
        return "markdown_text"
    if ext in HTML_EXTENSIONS:
        return "html"
    if ext in EPUB_EXTENSIONS:
        return "epub"
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in OFFICE_XML_EXTENSIONS:
        return ext.removeprefix(".")
    if source_type == "pdf_like":
        return "pdf"
    if converter == "media_transcript" or conversion_route == "media_to_transcript":
        return "transcript"
    return "unknown"
```

In `_add_transcript_location`, add settings only when present:

```python
        if cue.settings:
            location["cue_settings"] = cue.settings
```

- [ ] **Step 4: Extend transcript location schema to allow cue settings**

In `python/kbprep_worker/canonical_spans.py`, update transcript location key constants:

```python
TRANSCRIPT_TIMING_LOCATION_KEYS = frozenset({"cue_id", "start_time", "end_time", "cue_settings"})
TRANSCRIPT_CUE_LOCATION_KEYS = TRANSCRIPT_TIMING_LOCATION_KEYS | {"cue_index", "cue_settings"}
```

Keep `cue_settings` in `TRANSCRIPT_TIMING_LOCATION_KEYS` because WebVTT settings are part of timed cue evidence.
`converted_line_range` must reject `cue_settings` just as it rejects `cue_id`, `start_time`, and `end_time`; `source_line_range` rejects all cue fields through `TRANSCRIPT_CUE_LOCATION_KEYS`.

- [ ] **Step 5: Run source-span tests until they pass**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_source_spans -v
```

Expected after implementation: `OK`.

- [ ] **Step 6: Run independent subagent review for Task 3**

Dispatch a fresh review subagent with this brief:

```text
Review Task 3 only. Check python/kbprep_worker/canonical_spans.py and python/tests/test_canonical_ir_source_spans.py. Verify notebook source kind is distinct from structured_data, GBK SRT timing is preserved through SourceSpan output, WebVTT cue settings are included only when present, and reordered converted cues cannot receive later raw cue timing. Report concrete file/line issues only.
```

Task 3 is not complete until the review is clean or every review finding is fixed and re-reviewed.

## Task 4: Manifest And Precision Regression Closure

**Files:**
- Modify: `python/tests/test_canonical_ir_schema.py`

- [ ] **Step 1: Add missing precision/location mutual-exclusion tests**

Append these tests to the manifest/schema test class:

```python
    def test_validator_rejects_transcript_timing_precision_with_source_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("Host: Welcome\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={
                    "converted_md": "converted.md",
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                },
                coverage={"typed_nodes_available": True, "source_spans_available": True},
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload(nodes=[{
                    "node_id": "n_000001",
                    "ordinal": 1,
                    "type": "transcript_cue",
                    "text": "Host: Welcome",
                    "metadata": {"cue_index": 1, "speaker": "Host"},
                }])),
                encoding="utf-8",
            )
            bad_span = {
                "span_id": "s_000001",
                "node_id": "n_000001",
                "source_kind": "transcript",
                "location": {
                    "converted_line_start": 1,
                    "converted_line_end": 1,
                    "source_line_start": 1,
                    "source_line_end": 1,
                    "cue_index": 1,
                    "cue_id": "1",
                    "start_time": "00:00:01,000",
                    "end_time": "00:00:03,000",
                },
                "evidence": {
                    "source_type": "subtitle_transcript",
                    "converter": "direct_text",
                    "conversion_route": "direct_text",
                    "source_kind": "transcript",
                    "precision": "transcript_cue_timing",
                },
            }
            (run_dir / "canonical_ir" / "source_spans.json").write_text(
                json.dumps(_source_spans_payload(spans=[bad_span])),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any("transcript_cue_timing precision cannot include source line range" in issue.message for issue in issues))

    def test_validator_rejects_converted_line_precision_with_native_locations(self):
        cases = [
            (
                "source line range requires source_line_range precision",
                {
                    "span_id": "s_000001",
                    "node_id": "n_000001",
                    "source_kind": "markdown_text",
                    "location": {
                        "converted_line_start": 1,
                        "converted_line_end": 1,
                        "source_line_start": 1,
                        "source_line_end": 1,
                    },
                    "evidence": {
                        "source_type": "markdown_note",
                        "converter": "direct_text",
                        "conversion_route": "direct_text",
                        "source_kind": "markdown_text",
                        "precision": "converted_line_range",
                    },
                },
            ),
            (
                "transcript timing requires transcript_cue_timing precision",
                {
                    "span_id": "s_000001",
                    "node_id": "n_000001",
                    "source_kind": "transcript",
                    "location": {
                        "converted_line_start": 1,
                        "converted_line_end": 1,
                        "cue_index": 1,
                        "cue_id": "1",
                        "start_time": "00:00:01,000",
                        "end_time": "00:00:03,000",
                    },
                    "evidence": {
                        "source_type": "subtitle_transcript",
                        "converter": "direct_text",
                        "conversion_route": "direct_text",
                        "source_kind": "transcript",
                        "precision": "converted_line_range",
                    },
                },
            ),
        ]
        for expected_message, bad_span in cases:
            with self.subTest(expected_message=expected_message):
                with tempfile.TemporaryDirectory() as tmp:
                    run_dir = Path(tmp)
                    converted = run_dir / "converted.md"
                    converted.write_text("Host: Welcome\n", encoding="utf-8")
                    _write_valid_manifest_pair(
                        run_dir,
                        converted,
                        artifacts={
                            "converted_md": "converted.md",
                            "typed_nodes": "canonical_ir/typed_nodes.json",
                            "source_spans": "canonical_ir/source_spans.json",
                        },
                        coverage={"typed_nodes_available": True, "source_spans_available": True},
                    )
                    (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                        json.dumps(_typed_nodes_payload()),
                        encoding="utf-8",
                    )
                    (run_dir / "canonical_ir" / "source_spans.json").write_text(
                        json.dumps(_source_spans_payload(spans=[bad_span])),
                        encoding="utf-8",
                    )

                    issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

                self.assertTrue(any(expected_message in issue.message for issue in issues))
```

- [ ] **Step 2: Add reverse manifest consistency regression**

Append:

```python
    def test_validator_rejects_source_spans_artifact_when_coverage_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Safe\n", encoding="utf-8")
            _write_valid_manifest_pair(
                run_dir,
                converted,
                artifacts={
                    "converted_md": "converted.md",
                    "typed_nodes": "canonical_ir/typed_nodes.json",
                    "source_spans": "canonical_ir/source_spans.json",
                },
                coverage={"typed_nodes_available": True, "source_spans_available": False},
            )
            (run_dir / "canonical_ir" / "typed_nodes.json").write_text(
                json.dumps(_typed_nodes_payload()),
                encoding="utf-8",
            )
            (run_dir / "canonical_ir" / "source_spans.json").write_text(
                json.dumps(_source_spans_payload()),
                encoding="utf-8",
            )

            issues = validate_canonical_ir_manifests(run_dir, converted_path=converted)

        self.assertTrue(any(issue.code == "E_CANONICAL_IR_MANIFEST_INVALID" for issue in issues))
        self.assertTrue(any("coverage.source_spans_available must be true when artifacts.source_spans exists" in issue.message for issue in issues))
```

- [ ] **Step 3: Run schema tests**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_schema -v
```

Expected after tests are added: `OK`; the implementation already has the required validators. If this fails, fix the validator instead of weakening the tests.

- [ ] **Step 4: Run independent subagent review for Task 4**

Dispatch a fresh review subagent with this brief:

```text
Review Task 4 only. Check python/tests/test_canonical_ir_schema.py and the current validator behavior in python/kbprep_worker/canonical_spans.py. Verify all three precision/location directions are locked: source_line_range rejects transcript cue fields, transcript_cue_timing rejects source line fields, and converted_line_range rejects both native source lines and transcript timing. Also verify manifest source_spans artifact and coverage flag are mutually consistent in both directions. Report concrete file/line issues only.
```

Task 4 is not complete until the review is clean or every review finding is fixed and re-reviewed.

## Task 5: Canonical Conversion Route Consistency

**Files:**
- Modify: `python/kbprep_worker/canonical_ir.py`
- Modify: `python/tests/test_canonical_ir_schema.py`

- [ ] **Step 1: Add failing tests for route/converter separation**

Append:

```python
    def test_writer_uses_actual_route_for_source_span_conversion_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "source.pdf"
            converted = run_dir / "converted.md"
            source.write_text("pdf source placeholder", encoding="utf-8")
            converted.write_text("# Extracted\n", encoding="utf-8")
            (run_dir / "conversion_report.json").write_text(
                json.dumps({
                    "converter": "mineru",
                    "converted_md": str(converted),
                    "route_decision": {
                        "actual_converter": "mineru",
                        "actual_route": "mineru_ocr",
                    },
                }),
                encoding="utf-8",
            )
            (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")

            write_canonical_ir_manifests(
                run_dir=run_dir,
                input_path=source,
                source_type="pdf_like",
                file_hash="a" * 64,
                file_size=source.stat().st_size,
                run_id="run_test",
            )

            source_spans = json.loads((run_dir / "canonical_ir" / "source_spans.json").read_text(encoding="utf-8"))

        self.assertEqual(source_spans["spans"][0]["evidence"]["converter"], "mineru")
        self.assertEqual(source_spans["spans"][0]["evidence"]["conversion_route"], "mineru_ocr")

    def test_writer_falls_back_to_actual_converter_before_report_converter_when_route_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "source.txt"
            converted = run_dir / "converted.md"
            source.write_text("source text", encoding="utf-8")
            converted.write_text("source text\n", encoding="utf-8")
            (run_dir / "conversion_report.json").write_text(
                json.dumps({
                    "converter": "legacy_name",
                    "converted_md": str(converted),
                    "route_decision": {
                        "actual_converter": "direct_text",
                    },
                }),
                encoding="utf-8",
            )
            (run_dir / "diagnosis_report.json").write_text("{}", encoding="utf-8")

            write_canonical_ir_manifests(
                run_dir=run_dir,
                input_path=source,
                source_type="markdown_note",
                file_hash="b" * 64,
                file_size=source.stat().st_size,
                run_id="run_test",
            )

            source_spans = json.loads((run_dir / "canonical_ir" / "source_spans.json").read_text(encoding="utf-8"))

        self.assertEqual(source_spans["spans"][0]["evidence"]["converter"], "direct_text")
        self.assertEqual(source_spans["spans"][0]["evidence"]["conversion_route"], "direct_text")
```

- [ ] **Step 2: Run route tests and verify they fail before implementation**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_schema -v
```

Expected before implementation: the second route test should expose fallback mixing.

- [ ] **Step 3: Add named helpers for canonical converter and route**

In `python/kbprep_worker/canonical_ir.py`, add:

```python
def _canonical_converter(conversion_report: dict[str, Any], route_decision: dict[str, Any]) -> str:
    return str(route_decision.get("actual_converter") or conversion_report.get("converter") or "")


def _canonical_conversion_route(conversion_report: dict[str, Any], route_decision: dict[str, Any]) -> str:
    return str(
        route_decision.get("actual_route")
        or route_decision.get("actual_converter")
        or conversion_report.get("converter")
        or ""
    )
```

Update `_write_canonical_artifacts`:

```python
    converter = _canonical_converter(conversion_report, route_decision)
    conversion_route = _canonical_conversion_route(conversion_report, route_decision)
```

Pass `converter` and `conversion_route` into typed-node and source-span writers.

- [ ] **Step 4: Run schema tests until they pass**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_ir_schema -v
```

Expected after implementation: `OK`.

- [ ] **Step 5: Run independent subagent review for Task 5**

Dispatch a fresh review subagent with this brief:

```text
Review Task 5 only. Check python/kbprep_worker/canonical_ir.py and route tests in python/tests/test_canonical_ir_schema.py. Verify SourceSpan evidence.converter represents the actual converter, evidence.conversion_route represents the actual route, and fallbacks are named and deterministic instead of ad hoc converter mixing. Report concrete file/line issues only.
```

Task 5 is not complete until the review is clean or every review finding is fixed and re-reviewed.

## Task 6: Stale Historical Plan Drift

**Files:**
- Modify: `docs/superpowers/plans/2026-06-22-canonical-ir-typed-nodes.md`

- [ ] **Step 1: Mark the old C1 typed-node plan as superseded for SourceSpan coverage**

Add this note immediately under the title in `docs/superpowers/plans/2026-06-22-canonical-ir-typed-nodes.md`:

```markdown
> Supersession note, 2026-06-23: this C1 plan described the pre-SourceSpan slice where `coverage.source_spans_available` stayed false. The later C1b2/C2 SourceSpan work supersedes that statement: current Canonical IR may write `canonical_ir/source_spans.json`, and `coverage.source_spans_available` is true when the artifact validates successfully. Treat the old false-coverage steps below as historical context, not current implementation guidance.
```

- [ ] **Step 2: Search for stale false-coverage claims in active docs**

Run:

```powershell
rg -n "source_spans_available.*false|source_spans_available.*remains false|reject `coverage.source_spans_available = true`|pre-SourceSpan" docs README.md
```

Expected: only the superseded historical plan may contain old false-coverage context, and it must have the supersession note.

- [ ] **Step 3: Run development doc check if active docs changed**

If only the historical plan note changed, run:

```powershell
npm run dev:check
```

Expected: `dev:check` exits 0.

If active development docs, flowchart JSON, README, or protected docs are changed by discoveries during this task, run:

```powershell
$env:KBPREP_ALLOW_CORE_DOC_EDIT='1'; npm run dev:check
npm run check:flowchart
npm run check:development-docs
```

Expected: all commands exit 0.

- [ ] **Step 4: Run independent subagent review for Task 6**

Dispatch a fresh review subagent with this brief:

```text
Review Task 6 only. Check docs/superpowers/plans/2026-06-22-canonical-ir-typed-nodes.md and the rg stale-claim output. Verify old source_spans_available=false statements cannot be mistaken for current implementation guidance. Report concrete file/line issues only.
```

Task 6 is not complete until the review is clean or every review finding is fixed and re-reviewed.

## Task 7: Integrated Verification And Final Review

**Files:**
- Review only: all files changed by Tasks 1-6.

- [ ] **Step 1: Run the focused Canonical IR regression suite**

Run:

```powershell
node scripts/python-venv.mjs -m unittest python.tests.test_canonical_transcripts python.tests.test_canonical_ir_typed_nodes python.tests.test_canonical_ir_source_spans python.tests.test_canonical_ir_schema -v
```

Expected: `OK`.

- [ ] **Step 2: Run full Python tests and quality gates**

Run:

```powershell
npm run python:test
npm run python:ruff
npm run python:typecheck
```

Expected: all commands exit 0.

- [ ] **Step 3: Run release-risk project check because converter/Canonical IR behavior changed**

Run:

```powershell
npm run dev:full-check
```

Expected: command exits 0.

- [ ] **Step 4: Run final whitespace/diff check**

Run:

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` exits 0. `git status --short` shows only task-related files.

- [ ] **Step 5: Run independent final review subagent**

Dispatch a fresh review subagent with this brief:

```text
Final review for the Canonical IR SourceSpan hardening plan. Review all changed files in the working tree. Verify every issue from the plan is fixed: precision/location mutual-exclusion coverage, GBK SRT timing, speaker prefix false positives, notebook source kind, WebVTT settings, cue reorder safety, source_spans_available consistency, conversion_route consistency, cue identifier filtering, and stale plan drift. Also verify the reported verification commands match the changed risk surface. Report concrete file/line issues only.
```

No final commit is allowed until the final review is clean or every final-review finding is fixed and re-reviewed.

- [ ] **Step 6: Commit after all tests and reviews are clean**

Run:

```powershell
git add python/kbprep_worker/canonical_transcripts.py python/kbprep_worker/canonical_nodes.py python/kbprep_worker/canonical_spans.py python/kbprep_worker/canonical_ir.py python/tests/test_canonical_transcripts.py python/tests/test_canonical_ir_typed_nodes.py python/tests/test_canonical_ir_source_spans.py python/tests/test_canonical_ir_schema.py docs/superpowers/plans/2026-06-22-canonical-ir-typed-nodes.md docs/superpowers/plans/2026-06-23-canonical-ir-source-span-hardening.md
git commit -m "fix: harden canonical IR source span evidence"
```

Expected: commit succeeds only after focused tests, full Python checks, `dev:full-check`, `git diff --check`, and independent final review are clean.

## Completion Criteria

- GBK SRT no longer loses transcript timing silently in Canonical IR.
- WebVTT settings are preserved in SourceSpan location when present.
- WebVTT headers/directives are not used as cue identifiers.
- Generic colon prose is not misclassified as transcript speaker text in raw-cue-free transcript context.
- Raw cue matching is sequence-aware and does not attach timing to later raw cues when converted text is reordered.
- Notebook sources produce `source_kind: "notebook"`.
- All three precision/location conflict directions are covered by regression tests.
- `artifacts.source_spans` and `coverage.source_spans_available` are tested in both consistency directions.
- SourceSpan evidence separates actual converter from actual route with deterministic fallbacks.
- Stale historical plan text is clearly marked as superseded.
- Every development stage has an independent review subagent result.
- Focused Canonical IR tests, full Python tests, Python ruff/typecheck, `npm run dev:full-check`, and `git diff --check` pass.
