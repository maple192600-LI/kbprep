import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  makeEpubFixture,
  makeGarbledTextLayerPdf,
  makeImageOnlyPdf,
  makeLandscapeImagePdf,
  makeLandscapeTextPdf,
  makeOfficeFixtures,
  makeTextLayerPdf,
  normalizeMarkdownText,
  parseEnvelope,
  repoRoot,
  runPython,
  runPythonJson,
  runWorker,
  runWorkerRawInput,
} from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - quality gates part 2", () => {
  it("reports concrete detail retention and fails when detail-bearing blocks are discarded", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落' * 120, encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'step1', 'status': 'keep', 'type': 'operation_step', 'text': '步骤1：打开平台后台，设置 threshold=0.82。', 'protected': True},",
        "  {'block_id': 'link1', 'status': 'keep', 'type': 'tool_instruction', 'text': '工具地址：https://example.com/docs，账号角色选择 editor。', 'protected': True},",
        "  {'block_id': 'prompt1', 'status': 'keep', 'type': 'prompt', 'text': 'Prompt：请逐段保留操作步骤，不要总结。', 'protected': True},",
        "  {'block_id': 'code1', 'status': 'keep', 'type': 'code', 'text': '```python\\nprint(42)\\n```', 'protected': True},",
        "  {'block_id': 'table1', 'status': 'keep', 'type': 'table', 'text': '| 字段 | 值 |\\n| --- | --- |\\n| retry_count | 3 |', 'protected': True},",
        "  {'block_id': 'bad1', 'status': 'discard', 'type': 'paragraph', 'text': '失败经验：当 retry_count=3 仍失败时，记录 failure_reason 并人工复查。'},",
        "  {'block_id': 'cta1', 'status': 'discard', 'type': 'marketing_cta', 'text': '扫码入群领取体验卡'},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'detail-test'})",
        "detail = report['detail_retention']",
        "assert detail['operation_step']['total_blocks'] == 1, detail",
        "assert detail['tool_or_platform']['total_blocks'] == 2, detail",
        "assert detail['parameter']['total_blocks'] == 3, detail",
        "assert detail['link']['total_blocks'] == 1, detail",
        "assert detail['prompt']['discarded_blocks'] == 0, detail",
        "assert detail['code']['discarded_blocks'] == 0, detail",
        "assert detail['table']['discarded_blocks'] == 0, detail",
        "assert detail['parameter']['discarded_blocks'] == 1, detail",
        "assert detail['discarded_detail_block_ids'] == [], detail",
        "assert not any('detail-bearing blocks were discarded' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("fails quality when cleaned markdown drops signals from kept detail blocks", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落' * 120, encoding='utf-8')",
        "(run_dir / 'cleaned.md').write_text('# 操作流程\\n\\n步骤1：打开后台。\\n', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'step1', 'status': 'keep', 'type': 'operation_step', 'text': '步骤1：打开后台，设置 threshold=0.82，并访问 https://example.com/config。', 'protected': True},",
        "  {'block_id': 'code1', 'status': 'keep', 'type': 'code', 'text': '```python\\nretry_count = 3\\nfailure_reason = \"timeout\"\\n```', 'protected': True},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'output-retention-test'})",
        "retention = report['output_retention']",
        "assert retention['link']['missing'] == ['https://example.com/config'], retention",
        "assert 'threshold=0.82' in retention['parameter']['missing'], retention",
        "assert retention['code']['missing_count'] == 1, retention",
        "assert any('kept detail signals missing from final knowledge output' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("checks curated Obsidian complete正文 as the primary final output", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'obsidian').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('Method body. ' * 120, encoding='utf-8')",
        "(run_dir / 'cleaned.md').write_text('Step 1: configure threshold=0.82 and visit https://example.com/config.\\n```python\\nretry_count = 3\\n```\\n', encoding='utf-8')",
        "(run_dir / 'obsidian' / 'source-title.md').write_text('Step 1: configure the dashboard.\\n', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'step1', 'status': 'keep', 'type': 'operation_step', 'text': 'Step 1: configure threshold=0.82 and visit https://example.com/config.', 'protected': True},",
        "  {'block_id': 'code1', 'status': 'keep', 'type': 'code', 'text': '```python\\nretry_count = 3\\n```', 'protected': True},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'obsidian-primary-test'})",
        "retention = report['output_retention']",
        "assert retention['primary_output']['path'].endswith('source-title.md'), retention",
        "assert retention['primary_output']['missing_total'] > 0, retention",
        "assert any('final knowledge output' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("checks review and evidence detail signals against their own output files", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落' * 120, encoding='utf-8')",
        "(run_dir / 'evidence').mkdir()",
        "(run_dir / 'cleaned.md').write_text('# 正文\\n\\n步骤1：设置 threshold=0.82。\\n', encoding='utf-8')",
        "(run_dir / 'review_needed.md').write_text('需要复查：https://example.com/review retry_count=3\\n', encoding='utf-8')",
        "(run_dir / 'evidence' / 'marketing_pages.md').write_text('证据链接：https://example.com/evidence\\n', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'keep1', 'status': 'keep', 'type': 'operation_step', 'text': '步骤1：设置 threshold=0.82。', 'protected': True},",
        "  {'block_id': 'review1', 'status': 'review', 'type': 'paragraph', 'text': '需要复查：https://example.com/review retry_count=3', 'protected': False},",
        "  {'block_id': 'evidence1', 'status': 'evidence', 'type': 'community_benefit', 'text': '证据链接：https://example.com/evidence', 'protected': False},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'destination-retention-test'})",
        "retention = report['output_retention']",
        "assert retention['cleaned_md']['missing_total'] == 0, retention",
        "assert retention['review_needed_md']['missing_total'] == 0, retention",
        "assert retention['evidence_md']['missing_total'] == 0, retention",
        "assert retention['missing_total'] == 0, retention",
        "assert not any('kept detail signals missing from final knowledge output' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("keeps internal PDF page markers out of readable markdown outputs", () => {
    runPython(
      [
        "from pathlib import Path",
        "from tempfile import TemporaryDirectory",
        "from kbprep_worker.render_outputs import render",
        "with TemporaryDirectory() as tmp:",
        "    run_dir = Path(tmp)",
        "    blocks = [",
        "        {'block_id': 'p1', 'status': 'keep', 'type': 'paragraph', 'text': '<!-- page: 1 -->', 'heading_path': [], 'page_start': 0, 'page_end': 0},",
        "        {'block_id': 'b1', 'status': 'keep', 'type': 'paragraph', 'text': '第一步：打开 ExampleTool 后台，设置 threshold=0.8。', 'heading_path': [], 'page_start': 0, 'page_end': 0},",
        "        {'block_id': 'p2', 'status': 'keep', 'type': 'paragraph', 'text': '<!-- page: 2 -->', 'heading_path': [], 'page_start': 1, 'page_end': 1},",
        "        {'block_id': 'b2', 'status': 'keep', 'type': 'paragraph', 'text': '第二步：记录 failure_reason=timeout，并保留 retry_count=3。' * 260, 'heading_path': [], 'page_start': 1, 'page_end': 1},",
        "    ]",
        "    render(blocks, str(run_dir), 'sha', 'run')",
        "    cleaned = (run_dir / 'cleaned.md').read_text(encoding='utf-8')",
        "    assert '<!-- page:' not in cleaned, cleaned[:300]",
        "    assert 'threshold=0.8' in cleaned, cleaned",
        "    assert 'retry_count=3' in cleaned, cleaned",
        "    part_text = '\\n'.join(p.read_text(encoding='utf-8') for p in sorted((run_dir / 'parts').glob('part_*.md')))",
        "    assert '<!-- page:' not in part_text, part_text[:300]",
      ].join("\n"),
      [],
    );
  });

  it("writes trace metadata for discarded, review, and evidence outputs", () => {
    runPython(
      [
        "from pathlib import Path",
        "from tempfile import TemporaryDirectory",
        "from kbprep_worker.render_outputs import render",
        "with TemporaryDirectory() as tmp:",
        "    run_dir = Path(tmp)",
        "    blocks = [",
        "        {'block_id': 'keep1', 'status': 'keep', 'type': 'paragraph', 'text': '正文保留。', 'heading_path': ['第一章'], 'page_start': 0, 'page_end': 0},",
        "        {'block_id': 'drop1', 'status': 'discard', 'type': 'marketing_cta', 'text': '扫码入群领取体验卡', 'heading_path': ['第一章', '广告页'], 'page_start': 3, 'page_end': 3, 'risk_tags': ['cta'], 'confidence': 0.95, 'reason': 'matches discard pattern: marketing_cta'},",
        "        {'block_id': 'review1', 'status': 'review', 'type': 'paragraph', 'text': '这段需要人工确认。', 'heading_path': ['第二章'], 'page_start': 4, 'page_end': 5, 'risk_tags': ['low_confidence'], 'confidence': 0.52, 'reason': 'low confidence'},",
        "        {'block_id': 'evidence1', 'status': 'evidence', 'type': 'testimonial', 'text': '学员评价截图说明。', 'heading_path': ['证据'], 'page_start': 6, 'page_end': 6, 'confidence': 0.80, 'reason': 'matches evidence pattern: testimonial'},",
        "    ]",
        "    render(blocks, str(run_dir), 'sha', 'run')",
        "    discarded = (run_dir / 'discarded.md').read_text(encoding='utf-8')",
        "    review = (run_dir / 'review_needed.md').read_text(encoding='utf-8')",
        "    evidence = (run_dir / 'evidence' / 'marketing_pages.md').read_text(encoding='utf-8')",
        "    assert '[drop1]' in discarded and 'page=3' in discarded and 'risk_tags=[\"cta\"]' in discarded, discarded",
        "    assert 'heading=[\"第一章\", \"广告页\"]' in discarded and 'confidence=0.95' in discarded, discarded",
        "    assert 'reason=matches discard pattern: marketing_cta' in discarded, discarded",
        "    assert '[review1]' in review and 'page=4-5' in review and 'risk_tags=[\"low_confidence\"]' in review, review",
        "    assert '[evidence1]' in evidence and 'type=testimonial' in evidence and 'confidence=0.80' in evidence, evidence",
      ].join("\n"),
      [],
    );
  });

});

