import { describe, it } from "vitest";
import { runPython } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - quality gates part 1", () => {
  it("excludes image-only evidence from text coverage gates", () => {
    runPython(
      [
        "from pathlib import Path",
        "import json",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'images').mkdir()",
        "(run_dir / 'images' / 'a.jpg').write_bytes(b'fake')",
        "(run_dir / 'images' / 'b.jpg').write_bytes(b'fake')",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落。' * 80, encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'b1', 'status': 'keep', 'type': 'paragraph', 'text': '正文知识段落。' * 80},",
        "  {'block_id': 'b2', 'status': 'review', 'type': 'image_evidence', 'text': '![](images/a.jpg)'},",
        "  {'block_id': 'b3', 'status': 'evidence', 'type': 'image_evidence', 'text': '![](images/b.jpg)'},",
        "  {'block_id': 'b4', 'status': 'discard', 'type': 'marketing_cta', 'text': '扫码入群领取体验卡'},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'pdf_like', {'file_id': 'test'})",
        "assert report['coverage_excluded_blocks'] == 3",
        "assert report['coverage_ratio'] > 0.95",
        "assert report['discard_ratio_excluded_blocks'] == 3",
        "assert report['retention']['image_total'] == 2",
        "assert report['retention']['image_review'] == 1",
        "assert report['retention']['image_evidence'] == 1",
        "assert report['retention']['image_missing_files'] == 0",
        "assert report['image_retention']['referenced_file_count'] == 2",
        "assert not any('coverage' in err for err in report['strict_errors']), report",
        "assert not any('image files are missing' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("excludes slide deck page furniture and translator marketing back matter from body-loss gates", () => {
    runPython(
      [
        "from pathlib import Path",
        "import json",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('MVP 阶段的核心目标不是把产品做完整，而是验证最小闭环。' * 80, encoding='utf-8')",
        "(run_dir / 'cleaned.md').write_text('## MVP 阶段\\n\\nMVP 阶段的核心目标不是把产品做完整，而是验证最小闭环。', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'body1', 'status': 'keep', 'type': 'paragraph', 'text': 'MVP 阶段的核心目标不是把产品做完整，而是验证最小闭环。'},",
        "  {'block_id': 'page1', 'status': 'discard', 'type': 'page_marker', 'text': '<!-- page: 15 -->'},",
        "  {'block_id': 'divider1', 'status': 'discard', 'type': 'slide_chapter_divider', 'text': 'Chapter 4\\nMVP 阶段\\n15'},",
        "  {'block_id': 'back1', 'status': 'discard', 'type': 'translator_marketing_back_matter', 'text': '译后记：欢迎在 B 站、小红书、公众号和 example.com 找到我。'},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'pdf_like', {'file_id': 'slide-furniture-test'})",
        "assert report['discard_ratio'] == 0, report",
        "assert report['discard_ratio_excluded_blocks'] == 3, report",
        "assert report['coverage_ratio'] > 0.95, report",
        "assert report['detail_retention']['discarded_detail_block_ids'] == [], report",
        "assert not report['strict_errors'], report",
      ].join("\n"),
      [],
    );
  });

  it("treats a broken PDF text layer as superseded after OCR conversion succeeds", () => {
    runPython(
      [
        "from pathlib import Path",
        "import json, tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('Reusable method body. ' * 80, encoding='utf-8')",
        "(run_dir / 'cleaned.md').write_text('Reusable method body. ' * 80, encoding='utf-8')",
        "(run_dir / 'conversion_report.json').write_text(json.dumps({'converter': 'mineru', 'converted_bytes': 2048}), encoding='utf-8')",
        "blocks = [{'block_id': 'body1', 'status': 'keep', 'type': 'paragraph', 'text': 'Reusable method body. ' * 80}]",
        "diagnosis = {",
        "  'file_id': 'garbled-pdf',",
        "  'needs_ocr': True,",
        "  'pdf_subtype': 'garbled_text_layer',",
        "  'text_layer_health': 'bad',",
        "  'text_quality': {'garbled_ratio': 0.12, 'unreadable_text_ratio': 0.6281, 'mojibake_ratio': 0.0},",
        "}",
        "report = run_quality_check(blocks, str(run_dir), 'pdf_like', diagnosis)",
        "assert report['source_text_layer']['superseded_by_conversion'] is True, report",
        "assert not any(err.startswith('E_TEXT_LAYER_') for err in report['strict_errors']), report",
        "assert any('W_SOURCE_TEXT_LAYER_SUPERSEDED' in warn for warn in report['warnings']), report",
      ].join("\n"),
      [],
    );
  });

  it("still fails unreadable PDF text layer when no OCR conversion superseded it", () => {
    runPython(
      [
        "from pathlib import Path",
        "import json, tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('Reusable method body. ' * 80, encoding='utf-8')",
        "(run_dir / 'cleaned.md').write_text('Reusable method body. ' * 80, encoding='utf-8')",
        "(run_dir / 'conversion_report.json').write_text(json.dumps({'converter': 'pdf_text_layer', 'converted_bytes': 2048}), encoding='utf-8')",
        "blocks = [{'block_id': 'body1', 'status': 'keep', 'type': 'paragraph', 'text': 'Reusable method body. ' * 80}]",
        "diagnosis = {",
        "  'file_id': 'bad-text-layer',",
        "  'needs_ocr': False,",
        "  'text_quality': {'garbled_ratio': 0.0, 'unreadable_text_ratio': 0.6281, 'mojibake_ratio': 0.0},",
        "}",
        "report = run_quality_check(blocks, str(run_dir), 'pdf_like', diagnosis)",
        "assert any(err.startswith('E_TEXT_LAYER_UNREADABLE') for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("reports conversion structure integrity when converted markdown reaches block trace", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('# 第一章\\n\\n| 字段 | 值 |\\n| --- | --- |\\n| threshold | 0.8 |\\n\\n```python\\nretry_count = 3\\n```\\n\\n![](images/a.png)\\n' * 20, encoding='utf-8')",
        "(run_dir / 'images').mkdir()",
        "(run_dir / 'images' / 'a.png').write_bytes(b'fake')",
        "(run_dir / 'converted.md').write_text('# 第一章\\n\\n## 参数表\\n\\n| 字段 | 值 |\\n| --- | --- |\\n| threshold | 0.8 |\\n\\n```python\\nretry_count = 3\\n```\\n\\n![](images/a.png)\\n', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'h1', 'status': 'keep', 'type': 'section_heading', 'text': '# 第一章'},",
        "  {'block_id': 'h2', 'status': 'keep', 'type': 'section_heading', 'text': '## 参数表'},",
        "  {'block_id': 't1', 'status': 'keep', 'type': 'table', 'text': '| 字段 | 值 |\\n| --- | --- |\\n| threshold | 0.8 |', 'protected': True},",
        "  {'block_id': 'c1', 'status': 'keep', 'type': 'code', 'text': '```python\\nretry_count = 3\\n```', 'protected': True},",
        "  {'block_id': 'i1', 'status': 'keep', 'type': 'image_operation', 'text': '![](images/a.png)'},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'structure-pass'})",
        "integrity = report['conversion_structure_integrity']",
        "assert integrity['checked'] is True, integrity",
        "assert integrity['missing_heading_count'] == 0, integrity",
        "assert integrity['missing_table_count'] == 0, integrity",
        "assert integrity['missing_code_block_count'] == 0, integrity",
        "assert integrity['missing_image_ref_count'] == 0, integrity",
        "assert not any('E_CONVERSION_STRUCTURE_LOSS' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("fails quality when converted headings disappear before block trace", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('# 第一章\\n\\n正文知识段落。' * 60, encoding='utf-8')",
        "(run_dir / 'converted.md').write_text('# 第一章\\n\\n## 第二章\\n\\n正文知识段落。\\n', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'h1', 'status': 'keep', 'type': 'section_heading', 'text': '# 第一章'},",
        "  {'block_id': 'body', 'status': 'keep', 'type': 'paragraph', 'text': '正文知识段落。' * 40},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'missing-heading'})",
        "integrity = report['conversion_structure_integrity']",
        "assert integrity['missing_heading_count'] == 1, integrity",
        "assert '第二章' in ''.join(integrity['missing_headings']), integrity",
        "assert any('converted headings missing from block trace' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("fails quality when converted tables disappear before block trace", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落。' * 80, encoding='utf-8')",
        "(run_dir / 'converted.md').write_text('| 字段 | 值 |\\n| --- | --- |\\n| threshold | 0.8 |\\n', encoding='utf-8')",
        "blocks = [{'block_id': 'body', 'status': 'keep', 'type': 'paragraph', 'text': '正文知识段落。' * 40}]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'missing-table'})",
        "integrity = report['conversion_structure_integrity']",
        "assert integrity['converted_tables'] == 1 and integrity['block_tables'] == 0, integrity",
        "assert integrity['missing_table_count'] == 1, integrity",
        "assert any('converted tables missing from block trace' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("turns strict quality errors into named gates and next cleanup actions", () => {
    runPython(
      [
        "from pathlib import Path",
        "import json",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('# 第一章\\n\\n正文知识段落。' * 80, encoding='utf-8')",
        "(run_dir / 'converted.md').write_text('# 第一章\\n\\n## 第二章\\n\\n正文知识段落。\\n', encoding='utf-8')",
        "(run_dir / 'cleaned.md').write_text('扫码入群领取资料\\n', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'h1', 'status': 'keep', 'type': 'section_heading', 'text': '# 第一章'},",
        "  {'block_id': 'cta', 'status': 'keep', 'type': 'paragraph', 'text': '扫码入群领取资料'},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'named-gates'}, profile='curated_obsidian_kb')",
        "gates = {gate['name']: gate for gate in report['quality_gates']}",
        "assert gates['conversion_integrity']['status'] == 'fail', gates",
        "assert gates['cleanup_safety']['status'] == 'fail', gates",
        "assert gates['export_readiness']['status'] == 'fail', gates",
        "assert any(action['gate'] == 'conversion_integrity' for action in report['next_actions']), report",
        "assert any(action['gate'] == 'cleanup_safety' and action['target'] == 'cleaning_rules' for action in report['next_actions']), report",
        "assert any(action['gate'] == 'export_readiness' and action['action'] == 'block_export' for action in report['next_actions']), report",
        "tasks = report['quality_tasks']",
        "assert tasks['schema'] == 'kbprep.quality_tasks.v1', tasks",
        "assert tasks['run_dir'] == str(run_dir), tasks",
        "assert any(task['gate'] == 'conversion_integrity' for task in tasks['tasks']), tasks",
        "cleanup_task = next(task for task in tasks['tasks'] if task['gate'] == 'cleanup_safety')",
        "for key in ['id', 'gate', 'action', 'reason', 'evidence_paths', 'commands', 'acceptance_checks', 'evidence']:",
        "    assert key in cleanup_task, cleanup_task",
        "for key in ['goal', 'background', 'must_read_files', 'allowed_modifications', 'forbidden_modifications', 'implementation_steps', 'risk_points', 'test_commands', 'acceptance_criteria', 'review_after_completion', 'rollback_plan']:",
        "    assert key not in cleanup_task, cleanup_task",
        "assert any('rules/' in item for item in cleanup_task['evidence_paths']), cleanup_task",
        "assert any('quality_report.json' in item for item in cleanup_task['acceptance_checks']), cleanup_task",
        "gate_dir = run_dir / 'quality_gates'",
        "assert gate_dir.exists(), list(run_dir.iterdir())",
        "conversion_gate = json.loads((gate_dir / 'conversion_integrity.json').read_text(encoding='utf-8'))",
        "cleanup_gate = json.loads((gate_dir / 'cleanup_safety.json').read_text(encoding='utf-8'))",
        "export_gate = json.loads((gate_dir / 'export_readiness.json').read_text(encoding='utf-8'))",
        "assert conversion_gate['schema'] == 'kbprep.quality_gate.v1', conversion_gate",
        "assert conversion_gate['gate']['name'] == 'conversion_integrity', conversion_gate",
        "assert conversion_gate['gate']['status'] == 'fail', conversion_gate",
        "assert 'converted.md' in ''.join(conversion_gate['input_artifacts']), conversion_gate",
        "assert cleanup_gate['gate']['name'] == 'cleanup_safety', cleanup_gate",
        "assert 'discarded.md' in ''.join(cleanup_gate['input_artifacts']), cleanup_gate",
        "assert export_gate['gate']['name'] == 'export_readiness', export_gate",
        "assert export_gate['blocks_publication'] is True, export_gate",
        "artifact_path = report['quality_gate_artifacts']['conversion_integrity'].replace('\\\\', '/')",
        "assert artifact_path.endswith('quality_gates/conversion_integrity.json'), report",
      ].join("\n"),
      [],
    );
  });

  it("records quality loop iteration state and stops when the retry limit is reached", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落。' * 80, encoding='utf-8')",
        "(run_dir / 'cleaned.md').write_text('扫码入群领取资料\\n', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'cta', 'status': 'keep', 'type': 'paragraph', 'text': '扫码入群领取资料'},",
        "]",
        "report = run_quality_check(",
        "  blocks, str(run_dir), 'markdown_note', {'file_id': 'iteration-limit'},",
        "  profile='standard', quality_iteration=3, max_quality_iterations=3",
        ")",
        "assert report['quality_loop']['current_iteration'] == 3, report",
        "assert report['quality_loop']['max_iterations'] == 3, report",
        "assert report['quality_loop']['can_continue'] is False, report",
        "assert any(err.startswith('E_QUALITY_ITERATION_LIMIT') for err in report['strict_errors']), report",
        "assert any(action['action'] == 'stop_iteration' for action in report['next_actions']), report",
        "gates = {gate['name']: gate for gate in report['quality_gates']}",
        "assert gates['export_readiness']['status'] == 'fail', gates",
      ].join("\n"),
      [],
    );
  });

  it("fails quality when CTA pollution remains in kept body blocks", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落' * 120, encoding='utf-8')",
        "(run_dir / 'cleaned.md').write_text('扫码入群领取体验卡\\n\\n案例：平台规则里出现扫码入群时，要记录 risk_label=引流违规。\\n', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'cta-leak', 'status': 'keep', 'type': 'paragraph', 'text': '扫码入群领取体验卡', 'protected': False},",
        "  {'block_id': 'case-context', 'status': 'keep', 'type': 'paragraph', 'text': '案例：平台规则里出现扫码入群时，要记录 risk_label=引流违规。', 'protected': False},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'cta-leak-test'})",
        "assert any('CTA patterns found' in err for err in report['strict_errors']), report",
      ].join("\n"),
      [],
    );
  });

  it("reports source-to-converted integrity loss for text sources", () => {
    runPython(
      [
        "import json, tempfile",
        "from pathlib import Path",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp(prefix='kbprep-source-conversion-'))",
        "source = run_dir / 'source.md'",
        "source.write_text('# Source Title\\n\\n## Critical Section\\n\\nKeep threshold=0.8.\\n', encoding='utf-8')",
        "(run_dir / 'converted.md').write_text('# Source Title\\n\\nKeep threshold=0.8.\\n', encoding='utf-8')",
        "(run_dir / 'conversion_report.json').write_text(json.dumps({",
        "  'input_file': source.name,",
        "  'input_extension': '.md',",
        "  'converter': 'direct_text',",
        "  'converted_md': str(run_dir / 'converted.md'),",
        "  'converted_bytes': (run_dir / 'converted.md').stat().st_size,",
        "}), encoding='utf-8')",
        "(run_dir / 'run_metadata.json').write_text(json.dumps({'input_path': str(source)}), encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'h1', 'status': 'keep', 'type': 'section_heading', 'text': '# Source Title'},",
        "  {'block_id': 'p1', 'status': 'keep', 'type': 'paragraph', 'text': 'Keep threshold=0.8.'},",
        "]",
        "report = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'source-loss'}, profile='standard')",
        "assert any('source headings missing from converted Markdown' in err for err in report['strict_errors']), report",
        "assert report['source_conversion_integrity']['missing_heading_count'] == 1, report",
        "assert report['source_conversion_integrity']['missing_headings'] == ['critical section'], report",
        "assert (run_dir / 'source_conversion_integrity.json').exists(), list(run_dir.iterdir())",
        "gates = {gate['name']: gate for gate in report['quality_gates']}",
        "assert gates['conversion_integrity']['status'] == 'fail', gates",
      ].join("\n"),
      [],
    );
  });

  it("uses cleaning dictionaries for CTA quality gates instead of hardcoded platform terms", () => {
    runPython(
      [
        "from pathlib import Path",
        "import tempfile",
        "from kbprep_worker.quality import run_quality_check",
        "run_dir = Path(tempfile.mkdtemp())",
        "(run_dir / 'chunks').mkdir()",
        "(run_dir / 'chunks' / 'chunk_001.md').write_text('正文知识段落' * 120, encoding='utf-8')",
        "(run_dir / 'cleaned.md').write_text('欢迎关注公众号「ExampleAuthor」反馈交流。', encoding='utf-8')",
        "blocks = [",
        "  {'block_id': 'platform-follow', 'status': 'keep', 'type': 'paragraph', 'text': '欢迎关注公众号「ExampleAuthor」反馈交流。', 'protected': False},",
        "]",
        "standard = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'qa-rule-source-standard'}, profile='standard')",
        "templated = run_quality_check(blocks, str(run_dir), 'markdown_note', {'file_id': 'qa-rule-source-template'}, profile='curated_obsidian_kb')",
        "assert not any('CTA patterns found' in err for err in standard['strict_errors']), standard",
        "assert any('CTA patterns found' in err for err in templated['strict_errors']), templated",
        "standard_sources = [source.replace('\\\\', '/') for source in standard['cleaning_rule_sources']]",
        "assert 'rules/base/obvious_noise.json' in standard_sources, standard",
        "assert any(source.replace('\\\\', '/').endswith('.kbprep/rules/templates/self_media_course.json') for source in templated['cleaning_rule_sources']), templated",
      ].join("\n"),
      [],
    );
  });
});
