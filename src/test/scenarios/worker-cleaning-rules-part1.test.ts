import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  repoRoot,
  runPython,
  runWorker,
  runWorkerRawInput,
} from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - cleanup rules part 1", () => {
  it("splits obvious promotional lines out of otherwise useful source blocks", () => {
    runPython(
      [
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.quality import _detail_retention_stats",
        "blocks = [",
        "  {",
        "    'block_id': 'cover1',",
        "    'status': 'keep',",
        "    'type': 'paragraph',",
        "    'text': '\\n'.join([",
        "      '信息来源：ExampleTool 官方文档 · GitHub 仓库 · 社区调研文档版本：v1.1.0',",
        "      '如有勘误或建议，欢迎关注公众号「ExampleAuthor」反馈交流。',",
        "      '配套视频教程：B站「ExampleTool从0到1」 · 后续更新：飞书文档',",
        "      '第一步：打开 ExampleTool 后台，设置 threshold=0.8。',",
        "    ]),",
        "    'heading_path': [], 'page_start': 0, 'page_end': 0, 'risk_tags': [], 'protected': False,",
        "  },",
        "]",
        "cleaned = apply_clean_rules(blocks, rule_templates=['self_media_course'])",
        "kept = next(b for b in cleaned if b['block_id'] == 'cover1')",
        "discarded = [b for b in cleaned if b.get('status') == 'discard']",
        "assert '信息来源：ExampleTool 官方文档' in kept['text'], kept",
        "assert 'threshold=0.8' in kept['text'], kept",
        "assert '欢迎关注公众号' not in kept['text'], kept",
        "assert '配套视频教程' not in kept['text'], kept",
        "assert len(discarded) == 2, discarded",
        "assert all(b['type'] == 'marketing_cta' for b in discarded), discarded",
        "assert '欢迎关注公众号' in discarded[0]['text'], discarded",
        "assert '配套视频教程' in discarded[1]['text'], discarded",
        "stats = _detail_retention_stats(cleaned)",
        "assert stats['discarded_detail_block_ids'] == [], stats",
      ].join("\n"),
      [],
    );
  });

  it("loads platform cleanup only through the optional self-media template", () => {
    runPython(
      [
        "from kbprep_worker.clean_rules import apply_clean_rules",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "base = load_cleaning_rules()",
        "templated = load_cleaning_rules(templates=('self_media_course',))",
        "base_text = '\\n'.join([r.pattern for r in base.promotional_line_rules] + list(base.cta_keywords))",
        "templated_text = '\\n'.join([r.pattern for r in templated.promotional_line_rules] + list(templated.cta_keywords))",
        "for term in ['公众号', '小红书', 'B站', '抖音', 'YouTube']:",
        "    assert term not in base_text, base_text",
        "assert '公众号' in templated_text and 'B站' in templated_text, templated_text",
        "blocks = [{",
        "  'block_id': 'follow1',",
        "  'status': 'keep',",
        "  'type': 'paragraph',",
        "  'text': '欢迎关注公众号「ExampleAuthor」反馈交流。',",
        "  'heading_path': [], 'page_start': 0, 'page_end': 0, 'risk_tags': [], 'protected': False,",
        "}]",
        "generic = apply_clean_rules([dict(blocks[0])])",
        "self_media = apply_clean_rules([dict(blocks[0])], rule_templates=['self_media_course'])",
        "assert generic[0]['status'] == 'keep', generic",
        "assert self_media[0]['status'] == 'discard', self_media",
        "assert self_media[0]['cleaning_rule_source'].replace('\\\\', '/').endswith('.kbprep/rules/templates/self_media_course.json'), self_media",
      ].join("\n"),
      [],
    );
  });

  it("loads platform CTA classification only through the optional self-media template", () => {
    runPython(
      [
        "from kbprep_worker.classify_blocks import classify_blocks",
        "blocks = [{",
        "  'block_id': 'follow1',",
        "  'status': 'unclassified',",
        "  'type': 'paragraph',",
        "  'text': '欢迎关注公众号「ExampleAuthor」反馈交流。',",
        "  'heading_path': [], 'page_start': 0, 'page_end': 0, 'risk_tags': [], 'protected': False,",
        "}]",
        "generic = classify_blocks([dict(blocks[0])])",
        "self_media = classify_blocks([dict(blocks[0])], rule_templates=['self_media_course'])",
        "assert generic[0]['status'] == 'keep', generic",
        "assert self_media[0]['status'] == 'discard', self_media",
        "assert self_media[0]['type'] == 'marketing_cta', self_media",
      ].join("\n"),
      [],
    );
  });

  it("loads evidence, footer, and refund classification signals from dictionaries", () => {
    runPython(
      [
        "from kbprep_worker.classify_blocks import classify_blocks",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "rules = load_cleaning_rules()",
        "assert any(signal.label == 'testimonial' and '学员评价' in signal.pattern for signal in rules.evidence_patterns), rules.evidence_patterns",
        "assert any('无理由退款' in pattern for pattern in rules.refund_patterns), rules.refund_patterns",
        "assert any('page' in pattern.lower() for pattern in rules.footer_patterns), rules.footer_patterns",
        "blocks = [",
        "  {'block_id': 'e1', 'status': 'unclassified', 'type': 'paragraph', 'text': '学员评价：这个方法帮助团队记录失败经验。'},",
        "  {'block_id': 'r1', 'status': 'unclassified', 'type': 'paragraph', 'text': '3天无理由退款'},",
        "  {'block_id': 'f1', 'status': 'unclassified', 'type': 'paragraph', 'text': 'Page 12'},",
        "]",
        "classified = {block['block_id']: block for block in classify_blocks(blocks)}",
        "assert classified['e1']['status'] == 'evidence' and classified['e1']['type'] == 'testimonial', classified",
        "assert classified['r1']['status'] == 'discard' and classified['r1']['type'] == 'refund_policy', classified",
        "assert classified['f1']['status'] == 'discard' and classified['f1']['type'] == 'footer', classified",
      ].join("\n"),
      [],
    );
  });

  it("loads transcript filler classification signals from dictionaries", () => {
    runPython(
      [
        "from kbprep_worker.classify_blocks import classify_blocks",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "rules = load_cleaning_rules()",
        "assert any('点赞' in pattern for pattern in rules.transcript_filler_patterns), rules.transcript_filler_patterns",
        "assert any('watching' in pattern.lower() for pattern in rules.transcript_filler_patterns), rules.transcript_filler_patterns",
        "blocks = [",
        "  {'block_id': 'zh1', 'status': 'unclassified', 'type': 'paragraph', 'text': '点赞关注，下期见！'},",
        "  {'block_id': 'en1', 'status': 'unclassified', 'type': 'paragraph', 'text': 'thanks for watching'},",
        "  {'block_id': 'body1', 'status': 'unclassified', 'type': 'paragraph', 'text': '这个教程解释为什么不要把正文案例误删。'},",
        "]",
        "classified = {block['block_id']: block for block in classify_blocks(blocks)}",
        "assert classified['zh1']['status'] == 'discard' and classified['zh1']['type'] == 'transcript_filler', classified",
        "assert classified['en1']['status'] == 'discard' and classified['en1']['type'] == 'transcript_filler', classified",
        "assert classified['body1']['status'] == 'keep', classified",
      ].join("\n"),
      [],
    );
  });

  it("loads protected block classification signals from dictionaries", () => {
    runPython(
      [
        "from kbprep_worker.classify_blocks import classify_blocks",
        "from kbprep_worker.rule_loader import load_cleaning_rules",
        "rules = load_cleaning_rules()",
        "labels = {signal.label for signal in rules.protected_patterns}",
        "assert {'operation_step', 'prompt', 'tool_instruction'} <= labels, rules.protected_patterns",
        "blocks = [",
        "  {'block_id': 's1', 'status': 'unclassified', 'type': 'paragraph', 'text': '第一步：打开后台并设置阈值。'},",
        "  {'block_id': 'p1', 'status': 'unclassified', 'type': 'paragraph', 'text': '提示词：请提取失败原因和限制条件。'},",
        "  {'block_id': 't1', 'status': 'unclassified', 'type': 'paragraph', 'text': '工具名：ExampleTool，参数 threshold=0.8，retry_count=3。'},",
        "]",
        "classified = {block['block_id']: block for block in classify_blocks(blocks)}",
        "assert classified['s1']['status'] == 'keep' and classified['s1']['type'] == 'operation_step' and classified['s1']['protected'] is True, classified",
        "assert classified['p1']['status'] == 'keep' and classified['p1']['type'] == 'prompt' and classified['p1']['protected'] is True, classified",
        "assert classified['t1']['status'] == 'keep' and classified['t1']['type'] == 'tool_instruction' and classified['t1']['protected'] is True, classified",
      ].join("\n"),
      [],
    );
  });

  it("accepts UTF-8 BOM JSON stdin from Windows shells", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const envelope = runWorkerRawInput(
        "diagnose",
        `\ufeff${JSON.stringify({ input_path: path.join(repoRoot, "README.md"), output_root: root })}`,
      );

      expect(envelope.ok).toBe(true);
      expect(envelope.data.detected_format).toBe("markdown");
      expect(envelope.data.source_type).toBe("markdown_note");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("detects broad source families from the shared format table", () => {
    runPython(
      [
        "from kbprep_worker.detect import detect_source_family, detect_source_type",
        "assert detect_source_type('notes.md') == 'markdown_note'",
        "assert detect_source_type('lesson.srt') == 'subtitle_transcript'",
        "assert detect_source_type('analysis.ipynb') == 'generic_block'",
        "assert detect_source_family('analysis.ipynb') == 'notebook'",
        "assert detect_source_family('script.py') == 'code'",
        "assert detect_source_family('book.epub') == 'ebook'",
        "assert detect_source_family('slides.pptx') == 'presentation'",
        "assert detect_source_family('clip.mp4') == 'video'",
      ].join("\n"),
      [],
    );
  });

  it("classifies document types with reasons and confidence", () => {
    runPython(
      [
        "from kbprep_worker.document_type import classify_document_type",
        "from kbprep_worker.document_type_signals import load_document_type_signals",
        "signals = load_document_type_signals()",
        "assert any(signal.document_type == 'course' and '学习目标' in signal.pattern for signal in signals.content_patterns), signals.content_patterns",
        "assert any(signal.document_type == 'report' and '市场规模' in signal.pattern for signal in signals.content_patterns), signals.content_patterns",
        "cases = [",
        "  ('course', 'markdown_note', {'detected_format': 'markdown'}, '# 第1课\\n\\n学习目标\\n\\n练习：配置参数 threshold=0.8'),",
        "  ('report', 'pdf_like', {'detected_format': 'pdf'}, '# 2026 行业趋势报告\\n\\n摘要\\n\\n同比增长 20%。'),",
        "  ('transcript', 'subtitle_transcript', {'detected_format': 'subtitle_transcript'}, '# Transcript\\n\\n00:00 这一段是访谈字幕。'),",
        "  ('webpage', 'markdown_note', {'detected_format': 'html'}, '# 产品页面\\n\\n导航 首页 登录 订阅'),",
        "  ('ebook', 'generic_block', {'detected_format': 'ebook'}, '# Chapter 1\\n\\nTable of Contents\\n\\n正文'),",
        "  ('code', 'generic_block', {'detected_format': 'code'}, '```python\\ndef run():\\n    return 1\\n```'),",
        "  ('unknown', 'generic_block', {'detected_format': 'unknown'}, '零散文字。'),",
        "]",
        "for expected, source_type, diagnosis, text in cases:",
        "    result = classify_document_type(text=text, source_type=source_type, diagnosis=diagnosis)",
        "    assert result['document_type'] == expected, (expected, result)",
        "    assert 0 <= result['confidence'] <= 1, result",
        "    assert result['reasons'], result",
      ].join("\n"),
      [],
    );
  });

  it("derives a readable content title from PDF cover text before cleanup discards the cover", () => {
    runPython(
      [
        "from pathlib import Path",
        "from tempfile import TemporaryDirectory",
        "from kbprep_worker.prepare_diagnosis import source_title_for_render",
        "from kbprep_worker.title_filters import load_title_filters",
        "with TemporaryDirectory() as tmp:",
        "    filters = load_title_filters()",
        "    assert filters.source.replace('\\\\', '/').endswith('rules/base/title_filters.json'), filters",
        "    assert '仅供' in filters.reject_patterns, filters",
        "    converted = Path(tmp) / 'converted.md'",
        "    converted.write_text('\\n'.join([",
        "        '<!-- page: 1 -->',",
        "        '',",
        "        \"The Founder\\'s Playbook示例行动手册✻ Claude\",",
        "        'Anthropic · 2026 年 5 月Building an AI-Native Startup示例译者 译横版 36 页中文译本仅供个人学习与内部研究',",
        "        '',",
        "        '<!-- page: 2 -->',",
        "        '目录',",
        "    ]), encoding='utf-8')",
        "    title = source_title_for_render(Path(tmp) / 'founders-playbook.pdf', converted)",
        "    assert title == '示例行动手册', title",
      ].join("\n"),
      [],
    );
  });

  it("classifies long heading-rich documents with colon lines as reports, not transcripts", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const sourcePath = path.join(root, "technical-manual.md");
      const sections = Array.from({ length: 12 }, (_, index) => [
        `# 第${index + 1}章 配置说明`,
        "",
        "模型名称： gpt-4.1-mini",
        "参数 threshold： 0.8",
        "失败原因： 需要记录原始错误，不要总结掉。",
        "操作步骤： 打开后台，选择项目，填写参数，保存配置。",
        "注意事项： 如果接口返回 429，需要等待并重试。",
        "",
        "这是一段正文，用来描述章节里的知识背景、限制条件、案例过程和复盘细节。".repeat(60),
      ].join("\n"));
      writeFileSync(sourcePath, sections.join("\n\n"), "utf8");

      const envelope = runWorker("diagnose", {
        input_path: sourcePath,
        output_root: root,
        source_type: "auto",
      });

      expect(envelope.ok).toBe(true);
      expect(envelope.data.heading_count).toBeGreaterThanOrEqual(12);
      expect(envelope.data.speaker_line_count).toBeGreaterThanOrEqual(8);
      expect(envelope.data.text_profile).toBe("ebook_or_long_report");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("keeps tutorial steps that mention CTA phrases as policy examples", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "tutorial.md");
      writeFileSync(
        sourcePath,
        [
          "# 小红书账号规则教程",
          "",
          "第一步：检查文案里是否出现“扫码加入社群”。如果是在讲平台规则或违规案例，这句话必须保留，因为它是判断标准，不是广告。",
          "",
          "第二步：把检测结果记录到字段 risk_label，并把参数 threshold 设置为 0.8，方便后续复盘误判原因。",
          "",
          "第三步：只删除真正的购买引导、体验卡和无关广告，不要删除案例里的平台、账号、社群、引流等词。",
          "",
          "扫码加入社群领取体验卡。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_plus_review_pack",
        language: "zh",
        force: true,
      });

      const runDir = envelope.data.run_dir;
      const cleaned = readFileSync(path.join(runDir, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(runDir, "discarded.md"), "utf8");
      const conversionReport = JSON.parse(readFileSync(path.join(runDir, "conversion_report.json"), "utf8"));
      const quality = JSON.parse(readFileSync(path.join(runDir, "quality_report.json"), "utf8"));
      const packageVersion = JSON.parse(readFileSync("package.json", "utf8")).version;

      expect(envelope.data.strict_errors).toEqual([]);
      expect(quality.plugin_version).toBe(packageVersion);
      expect(envelope.data.outputs.images_dir).toContain("images");
      expect(envelope.data.latest_outputs.images_dir).toContain("images");
      expect(conversionReport.runtime.python_executable).toContain("python");
      expect(conversionReport.runtime).toHaveProperty("mineru_path");
      expect(conversionReport.runtime).toHaveProperty("torch_cuda_available");
      expect(conversionReport.runtime).toHaveProperty("mineru_device");
      expect(existsSync(path.join(outputRoot, "converted.md"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "blocks.jsonl"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "cleaned.md"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "discarded.md"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "review_needed.md"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "quality_report.json"))).toBe(true);
      expect(cleaned).toContain("讲平台规则或违规案例");
      expect(cleaned).toContain("threshold 设置为 0.8");
      expect(cleaned).not.toContain("领取体验卡");
      expect(discarded).toContain("领取体验卡");
      expect(discarded).not.toContain("讲平台规则或违规案例");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

});

