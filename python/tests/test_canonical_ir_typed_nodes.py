import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker.canonical_nodes import (
    CANONICAL_IR_TYPED_NODES_SCHEMA,
    build_typed_nodes_from_markdown,
    write_typed_nodes_artifact,
)


class CanonicalIrTypedNodeTests(unittest.TestCase):
    def test_builds_core_markdown_typed_nodes_in_source_order(self) -> None:
        markdown = """# Title

Intro line
continued line

- First
- Second

| Key | Value |
| --- | --- |
| A | 1 |

```python
# not a heading
- not a list
```

> Quote one
> Quote two
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["heading", "paragraph", "list", "table", "code", "quote"])
        self.assertEqual([node.node_id for node in nodes], [f"n_{index:06d}" for index in range(1, 7)])
        self.assertEqual([node.ordinal for node in nodes], list(range(1, 7)))
        self.assertEqual(nodes[0].metadata, {"heading_level": 1})
        self.assertEqual(nodes[2].text, "First\nSecond")
        self.assertEqual(nodes[3].metadata, {"rows": 3})
        self.assertEqual(nodes[4].metadata, {"language": "python"})
        self.assertIn("# not a heading", nodes[4].text)
        self.assertEqual(nodes[5].text, "Quote one\nQuote two")

    def test_parser_builds_c1b_metadata_figure_and_formula_nodes(self) -> None:
        markdown = """---
title: Example Note
tags:
  - canonical-ir
---

![Architecture diagram](assets/diagram.png "Architecture")

$$
E = mc^2
$$

$a + b = c$
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["metadata", "figure", "formula", "formula"])
        self.assertEqual(nodes[0].metadata, {"format": "yaml_frontmatter", "lines": 3})
        self.assertIn("title: Example Note", nodes[0].text)
        self.assertEqual(
            nodes[1].metadata,
            {"alt": "Architecture diagram", "target": "assets/diagram.png", "title": "Architecture"},
        )
        self.assertEqual(nodes[2].text, "E = mc^2")
        self.assertEqual(nodes[2].metadata, {"syntax": "dollar_block"})
        self.assertEqual(nodes[3].text, "a + b = c")
        self.assertEqual(nodes[3].metadata, {"syntax": "dollar_inline"})

    def test_parser_keeps_c1b_syntax_inside_code_fence_as_code(self) -> None:
        markdown = """```markdown
---
title: Not metadata
---
![not a figure](image.png)
$$
not_formula()
$$
```
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["code"])
        self.assertIn("![not a figure](image.png)", nodes[0].text)
        self.assertIn("not_formula()", nodes[0].text)

    def test_parser_builds_transcript_cue_nodes_in_transcript_context(self) -> None:
        markdown = """# Transcript

Host: Welcome to the lesson.

Guest: Set threshold to 0.8 and record the failure reason.
"""

        nodes = build_typed_nodes_from_markdown(markdown, source_type="subtitle_transcript")

        self.assertEqual([node.node_type for node in nodes], ["heading", "transcript_cue", "transcript_cue"])
        self.assertEqual(nodes[1].metadata, {"cue_index": 1, "speaker": "Host"})
        self.assertEqual(nodes[2].metadata, {"cue_index": 2, "speaker": "Guest"})

    def test_parser_keeps_transcript_intro_without_matching_cue_evidence(self) -> None:
        markdown = """# Transcript

This note was added by the converter before timed cues.

Host: Welcome to the lesson.
"""

        nodes = build_typed_nodes_from_markdown(
            markdown,
            source_type="subtitle_transcript",
            transcript_cue_texts=["Host: Welcome to the lesson."],
        )

        self.assertEqual([node.node_type for node in nodes], ["heading", "paragraph", "transcript_cue"])
        self.assertEqual(nodes[2].metadata, {"cue_index": 1, "speaker": "Host"})

    def test_parser_does_not_treat_generic_colon_notice_as_speaker_cue(self) -> None:
        markdown = "注意: 这是说明\n\nHost: Welcome\n"

        nodes = build_typed_nodes_from_markdown(markdown, source_type="subtitle_transcript")

        self.assertEqual([node.node_type for node in nodes], ["paragraph", "transcript_cue"])
        self.assertEqual(nodes[0].metadata, {})
        self.assertEqual(nodes[1].metadata, {"cue_index": 1, "speaker": "Host"})

    def test_parser_allows_common_asr_speaker_labels_without_raw_cues(self) -> None:
        markdown = "Speaker 1: Welcome\n\n主持人: 欢迎\n\n讲者: 继续\n\n问: 问题\n\n答: 回答\n"

        nodes = build_typed_nodes_from_markdown(markdown, source_type="subtitle_transcript")

        self.assertEqual(
            [node.node_type for node in nodes],
            ["transcript_cue", "transcript_cue", "transcript_cue", "transcript_cue", "transcript_cue"],
        )
        self.assertEqual(nodes[0].metadata, {"cue_index": 1, "speaker": "Speaker 1"})
        self.assertEqual(nodes[1].metadata, {"cue_index": 2, "speaker": "主持人"})
        self.assertEqual(nodes[2].metadata, {"cue_index": 3, "speaker": "讲者"})
        self.assertEqual(nodes[3].metadata, {"cue_index": 4, "speaker": "问"})
        self.assertEqual(nodes[4].metadata, {"cue_index": 5, "speaker": "答"})

    def test_parser_preserves_raw_cue_confirmed_name_speaker_metadata(self) -> None:
        nodes = build_typed_nodes_from_markdown(
            "Alice: Hello\n",
            source_type="subtitle_transcript",
            transcript_cue_texts=["Alice: Hello"],
        )

        self.assertEqual([node.node_type for node in nodes], ["transcript_cue"])
        self.assertEqual(nodes[0].metadata, {"cue_index": 1, "speaker": "Alice"})

    def test_parser_allows_name_speakers_for_media_transcript_without_raw_cues(self) -> None:
        nodes = build_typed_nodes_from_markdown(
            "Alice: Hello there\n\nBob: Hi",
            source_type="subtitle_transcript",
            conversion_route="media_to_transcript",
        )

        self.assertEqual([node.node_type for node in nodes], ["transcript_cue", "transcript_cue"])
        self.assertEqual(nodes[0].metadata, {"cue_index": 1, "speaker": "Alice"})
        self.assertEqual(nodes[1].metadata, {"cue_index": 2, "speaker": "Bob"})

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

    def test_parser_does_not_skip_later_raw_cue_that_appears_after_reordered_text(self) -> None:
        markdown = "Host: First cue\n\nHost: Third cue\n\nGuest: Second cue\n"

        nodes = build_typed_nodes_from_markdown(
            markdown,
            source_type="subtitle_transcript",
            transcript_cue_texts=["Host: First cue", "Guest: Second cue", "Host: Third cue"],
        )

        self.assertEqual([node.node_type for node in nodes], ["transcript_cue", "paragraph", "transcript_cue"])
        self.assertEqual(nodes[0].metadata, {"cue_index": 1, "speaker": "Host"})
        self.assertEqual(nodes[1].metadata, {})
        self.assertEqual(nodes[2].metadata, {"cue_index": 2, "speaker": "Guest"})

    def test_writes_typed_nodes_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            converted = run_dir / "converted.md"
            converted.write_text("# Note\n\nA useful note.\n", encoding="utf-8")

            artifact = write_typed_nodes_artifact(run_dir=run_dir, document_id="doc_test", converted_path=converted)

            payload = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], CANONICAL_IR_TYPED_NODES_SCHEMA)
        self.assertEqual(payload["document_id"], "doc_test")
        self.assertEqual(payload["source_artifact"], "converted.md")
        self.assertEqual(payload["node_count"], 2)
        self.assertEqual([node["type"] for node in payload["nodes"]], ["heading", "paragraph"])
        self.assertEqual(set(payload["nodes"][0]), {"node_id", "ordinal", "type", "text", "metadata"})

    def test_parser_keeps_code_fence_content_as_one_code_node(self) -> None:
        markdown = """```markdown
# Not a heading
- not a list item
> not a quote
| not | a table |
```
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["code"])
        self.assertIn("# Not a heading", nodes[0].text)
        self.assertEqual(nodes[0].metadata, {"language": "markdown"})

    def test_parser_supports_tilde_code_fences(self) -> None:
        markdown = """~~~python
# Not a heading
- not a list item
~~~
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["code"])
        self.assertIn("- not a list item", nodes[0].text)
        self.assertEqual(nodes[0].metadata, {"language": "python"})

    def test_parser_keeps_shorter_backticks_inside_longer_fence(self) -> None:
        markdown = """````
```
content
````
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["code"])
        self.assertEqual(nodes[0].text, "```\ncontent")

    def test_parser_does_not_treat_pipe_sentence_as_table(self) -> None:
        nodes = build_typed_nodes_from_markdown("The standard A | B appears inside prose.\n")

        self.assertEqual([node.node_type for node in nodes], ["paragraph"])

    def test_parser_recognizes_pipe_table_without_outer_pipes(self) -> None:
        nodes = build_typed_nodes_from_markdown("A | B\n--- | ---\n1 | 2\n")

        self.assertEqual([node.node_type for node in nodes], ["table"])
        self.assertEqual(nodes[0].metadata, {"rows": 3})

    def test_parser_keeps_table_with_empty_cell_as_one_table(self) -> None:
        nodes = build_typed_nodes_from_markdown("A | B\n--- | ---\n1 | \n")

        self.assertEqual([node.node_type for node in nodes], ["table"])
        self.assertEqual(nodes[0].metadata, {"rows": 3})

    def test_parser_merges_ordered_list_and_multiline_paragraph(self) -> None:
        markdown = """First paragraph line
Second paragraph line

1. Collect source evidence
2. Record acceptance criteria
"""

        nodes = build_typed_nodes_from_markdown(markdown)

        self.assertEqual([node.node_type for node in nodes], ["paragraph", "list"])
        self.assertEqual(nodes[0].text, "First paragraph line\nSecond paragraph line")
        self.assertEqual(nodes[1].text, "Collect source evidence\nRecord acceptance criteria")


if __name__ == "__main__":
    unittest.main()
