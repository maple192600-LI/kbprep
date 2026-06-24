import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runPython, runWorker } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - output lifecycle part 1", () => {
  it("renders a curated Obsidian knowledge base without author bios or identity wrappers", () => {
    runPython(
      [
        "from pathlib import Path",
        "from tempfile import TemporaryDirectory",
        "from kbprep_worker.obsidian_template import load_obsidian_template",
        "from kbprep_worker.obsidian_kb import apply_curated_obsidian_policy, render_obsidian_vault",
        "with TemporaryDirectory() as tmp:",
        "    template = load_obsidian_template('obsidian_course_kb')",
        "    assert template.source.replace('\\\\', '/').endswith('.kbprep/rules/templates/obsidian_course_kb.json'), template",
        "    assert template.categories == ('认知', '方法', '案例'), template",
        "    run_dir = Path(tmp)",
        "    blocks = [",
        "        {'block_id': 'h1', 'type': 'section_heading', 'status': 'keep', 'text': '# ExampleCreator: YouTube AI 内容出海把全球第一的视频平台变成自己的金矿？', 'heading_path': ['ExampleCreator: YouTube AI 内容出海把全球第一的视频平台变成自己的金矿？']},",
        "        {'block_id': 'wrapper_title', 'type': 'section_heading', 'status': 'keep', 'text': '# ExampleCourse', 'heading_path': ['ExampleCourse']},",
        "        {'block_id': 'brand_heading', 'type': 'section_heading', 'status': 'keep', 'text': '# ExampleCommunityInsight', 'heading_path': ['ExampleCommunityInsight']},",
        "        {'block_id': 'toc_h1', 'type': 'section_heading', 'status': 'keep', 'text': '# 认知篇：ExampleCommunityInsight', 'heading_path': ['认知篇：ExampleCommunityInsight']},",
        "        {'block_id': 'toc_h2', 'type': 'section_heading', 'status': 'keep', 'text': '## AIGC', 'heading_path': ['认知篇：ExampleCommunityInsight', 'AIGC']},",
        "        {'block_id': 'toc_body', 'type': 'tool_instruction', 'status': 'keep', 'protected': True, 'text': 'ExampleFounder1：为什么AIGC是超级机会？ 01\\nExampleCreator：YouTubeAI内容出海，把全球第一的视频平台变成自己的金矿 05\\nExampleFounder2：AI赋能视频号，如何通过账号矩阵实现ExampleRevenue3 19', 'heading_path': ['认知篇：ExampleCommunityInsight', 'AIGC']},",
        "        {'block_id': 'real_h', 'type': 'section_heading', 'status': 'keep', 'text': '## AI领域看到的3个超级机会', 'heading_path': ['AI领域看到的3个超级机会']},",
        "        {'block_id': 'brand_program', 'type': 'paragraph', 'status': 'keep', 'text': '过去一年，ExampleCommunityAction这条路径，也发布了9条ExampleProgram1，这些超级标也形成了完整的ExampleProgram2。', 'heading_path': ['二、AI对大多数ExampleMember的机会，集中在4个确定性方向']},",
        "        {'block_id': 'bio', 'type': 'paragraph', 'status': 'keep', 'text': 'ExampleCreator，ExamplePersona1，ExamplePersona3，擅长 YouTube 内容出海，下面先Let me introduce myself。', 'heading_path': ['ExampleCreator: YouTube AI 内容出海把全球第一的视频平台变成自己的金矿？']},",
        "        {'block_id': 'author_handle', 'type': 'paragraph', 'status': 'keep', 'text': '@ExampleFounder2', 'heading_path': ['LC AIGCExampleFounder2：AI赋能视频号如何通过账号矩阵实现ExampleRevenue3']},",
        "        {'block_id': 'author_role', 'type': 'paragraph', 'status': 'keep', 'text': 'ExamplePersona2', 'heading_path': ['LC AIGCExampleFounder2：AI赋能视频号如何通过账号矩阵实现ExampleRevenue3']},",
        "        {'block_id': 'author_credential', 'type': 'paragraph', 'status': 'keep', 'text': 'ExampleMarketingClaim', 'heading_path': ['LC AIGCExampleFounder2：AI赋能视频号如何通过账号矩阵实现ExampleRevenue3']},",
        "        {'block_id': 'author_h2', 'type': 'section_heading', 'status': 'keep', 'text': '# AI产品ExampleStaff1：AI产品出海如何高效系统化地获取流量', 'heading_path': ['AI产品ExampleStaff1：AI产品出海如何高效系统化地获取流量']},",
        "        {'block_id': 'author_handle_2', 'type': 'paragraph', 'status': 'keep', 'text': '@ExampleStaff1', 'heading_path': ['AI产品ExampleStaff1：AI产品出海如何高效系统化地获取流量']},",
        "        {'block_id': 'body', 'type': 'paragraph', 'status': 'keep', 'text': '为什么在 YouTube 做 AI 内容出海？核心是先选择垂类赛道，再用脚本模板测试点击率，最后把可复用流程沉淀成 SOP。', 'heading_path': ['ExampleCreator: YouTube AI 内容出海把全球第一的视频平台变成自己的金矿？']},",
        "        {'block_id': 'inline_case_context', 'type': 'operation_step', 'status': 'keep', 'text': '4.不少ExampleMember靠AI产品已经赚到钱，比如ExampleMember@ExampleStaff1两款AI产品年营收ExampleRevenue2，其中ExampleVendor拿到了ExampleRevenue1融资。', 'heading_path': ['为什么AI产品是超级机会？']},",
        "        {'block_id': 'step', 'type': 'operation_step', 'status': 'keep', 'protected': True, 'text': '1）脚本测试：先生成 10 个标题，用 Gemini 判断信息差，再保留 CTR 高的方向。', 'heading_path': ['ExampleCreator: YouTube AI 内容出海把全球第一的视频平台变成自己的金矿？']},",
        "        {'block_id': 'img', 'type': 'image_operation', 'status': 'keep', 'text': '![作者头像](images/avatar.png)', 'heading_path': ['ExampleCreator: YouTube AI 内容出海把全球第一的视频平台变成自己的金矿？']},",
        "        {'block_id': 'layout_table', 'type': 'table', 'status': 'keep', 'protected': True, 'text': '| 20:44 |  |  |\\n| --- | --- | --- |\\n| <返回 |  | 帐户明细 |\\n| 日期范围 | 近7日 | 近30日 |\\n|  |  |  |', 'heading_path': ['ExampleCreator: YouTube AI 内容出海把全球第一的视频平台变成自己的金矿？']},",
        "        {'block_id': 'method_table', 'type': 'table', 'status': 'keep', 'protected': True, 'text': '| 工具 | 问题 |\\n| --- | --- |\\n| RPA | 录制图形界面操作，界面一变就失效 |\\n| n8n | 更适合连接本地应用和模型节点 |', 'heading_path': ['ExampleCreator: YouTube AI 内容出海把全球第一的视频平台变成自己的金矿？']},",
        "        {'block_id': 'h2', 'type': 'section_heading', 'status': 'keep', 'text': '# 老黄牛：不要用 AI 优化传统的工作，而是重构流程', 'heading_path': ['老黄牛：不要用 AI 优化传统的工作，而是重构流程']},",
        "        {'block_id': 'body2', 'type': 'paragraph', 'status': 'keep', 'text': '不要用 AI 优化传统的工作，而是把输入、判断、输出重新拆开，让模型参与每一个可验证节点。', 'heading_path': ['老黄牛：不要用 AI 优化传统的工作，而是重构流程']},",
        "    ]",
        "    blocks = apply_curated_obsidian_policy(blocks, template_name='obsidian_course_kb')",
        "    render_obsidian_vault(blocks, str(run_dir), source_title='ExampleCourseManual', source_hash='sha', run_id='run', profile='curated_obsidian_kb', template_name='obsidian_course_kb')",
        "    complete_path = run_dir / 'obsidian' / 'ExampleCourseManual.md'",
        "    assert complete_path.exists(), list((run_dir / 'obsidian').glob('*.md'))",
        "    assert not (run_dir / 'obsidian' / '01-完整正文.md').exists()",
        "    complete = complete_path.read_text(encoding='utf-8')",
        "    index = (run_dir / 'obsidian' / '00-索引.md').read_text(encoding='utf-8')",
        "    assert '[[ExampleCourseManual|完整正文]]' in index, index",
        "    index = (run_dir / 'obsidian' / '00-索引.md').read_text(encoding='utf-8')",
        "    discarded = (run_dir / 'obsidian' / '_audit' / 'discarded.md').read_text(encoding='utf-8')",
        "    source_map = (run_dir / 'obsidian' / '_audit' / 'source-map.jsonl').read_text(encoding='utf-8')",
        "    case_files = list((run_dir / 'obsidian' / '案例').glob('*.md'))",
        "    method_files = list((run_dir / 'obsidian' / '方法').glob('*.md'))",
        "    assert 'ExampleCreator:' not in complete, complete",
        "    assert '老黄牛：' not in complete, complete",
        "    assert '# ExampleCourse' not in complete, complete",
        "    assert 'ExampleCommunityInsight' not in complete, complete",
        "    assert 'ExampleFounder1：为什么AIGC是超级机会？ 01' not in complete, complete",
        "    assert 'ExampleProgram1' not in complete, complete",
        "    assert '@ExampleFounder2' not in complete, complete",
        "    assert 'ExamplePersona2' not in complete, complete",
        "    assert 'ExampleMarketingClaim' not in complete, complete",
        "    assert 'ExampleVendor拿到了ExampleRevenue1融资' in complete, complete",
        "    assert 'ExampleMember@ExampleStaff1两款AI产品' in complete, complete",
        "    assert 'AI领域看到的3个超级机会' in complete, complete",
        "    assert complete.count('AI领域看到的3个超级机会') == 1, complete",
        "    assert 'ExamplePersona1' not in complete, complete",
        "    assert '作者头像' not in complete, complete",
        "    assert '帐户明细' not in complete, complete",
        "    assert 'RPA' in complete, complete",
        "    assert '为什么在 YouTube 做 AI 内容出海？' in complete, complete",
        "    assert '脚本测试' in complete, complete",
        "    assert '不要用 AI 优化传统的工作' in complete, complete",
        "    assert '[[案例/' in index, index",
        "    assert '[[方法/' in index, index",
        "    assert case_files, 'expected at least one case note'",
        "    assert method_files, 'expected at least one method note'",
        "    assert 'ExamplePersona1' in discarded, discarded",
        "    assert 'author_identity' in discarded, discarded",
        "    assert 'ExampleMarketingClaim' in discarded, discarded",
        "    assert 'drop_image_for_text_kb' in discarded, discarded",
        "    assert 'layout_table_artifact' in discarded, discarded",
        "    assert 'drop_brand_program_packaging_for_text_kb' in discarded, discarded",
        '    assert \'"block_id": "body"\' in source_map, source_map',
      ].join("\n"),
      [],
    );
  });

  it("removes slide deck page markers, chapter divider slides, and translator marketing back matter from curated Obsidian output", () => {
    runPython(
      [
        "from pathlib import Path",
        "from tempfile import TemporaryDirectory",
        "from kbprep_worker.obsidian_kb import apply_curated_obsidian_policy, render_obsidian_vault",
        "with TemporaryDirectory() as tmp:",
        "    run_dir = Path(tmp)",
        "    blocks = [",
        "        {'block_id': 'page_marker', 'type': 'paragraph', 'status': 'keep', 'text': '<!-- page: 8 -->', 'heading_path': [], 'page_start': 7, 'page_end': 7},",
        "        {'block_id': 'divider_intro', 'type': 'paragraph', 'status': 'keep', 'text': 'Chapter 1\\n创业生命周期，\\n为 2026 重新启动\\n3', 'heading_path': [], 'page_start': 2, 'page_end': 2},",
        "        {'block_id': 'body_intro', 'type': 'paragraph', 'status': 'keep', 'text': 'Chapter 1\\n创业生命周期，\\n为 2026 重新启动创业生命周期，为 2026 重新启动AI 正在重塑创业公司的搭建方式。\\n4', 'heading_path': [], 'page_start': 3, 'page_end': 3},",
        "        {'block_id': 'divider', 'type': 'paragraph', 'status': 'keep', 'text': 'Chapter 4\\nMVP 阶段\\n15', 'heading_path': [], 'page_start': 14, 'page_end': 14},",
        "        {'block_id': 'body', 'type': 'paragraph', 'status': 'keep', 'text': 'Chapter 4\\nMVP 阶段MVP 阶段的核心目标不是把产品做完整，而是验证一个最小闭环。\\n16', 'heading_path': [], 'page_start': 15, 'page_end': 15},",
        "        {'block_id': 'afterword', 'type': 'paragraph', 'status': 'keep', 'text': '译后记这本《ExampleProgramTitle》是 Anthropic 2026 年 5 月发布的官方手册。\\n本译本仅供个人学习与内部研究使用，不做商业发行。\\n如果你也在用 AI 做产品、做公司，欢迎在下面这些地方找到我：\\nExampleAuthor · space.bilibili.com/12345678\\nX\\n@ExampleHandle\\nYouTube\\n@ExampleHandle\\n小红书\\nExampleAuthor\\n公众号\\nExampleAuthor\\n官网\\nexample.com', 'heading_path': [], 'page_start': 35, 'page_end': 35},",
        "    ]",
        "    blocks = apply_curated_obsidian_policy(blocks, template_name='obsidian_course_kb')",
        "    render_obsidian_vault(blocks, str(run_dir), source_title='founders-playbook', source_hash='sha', run_id='run', profile='curated_obsidian_kb', template_name='obsidian_course_kb')",
        "    complete = (run_dir / 'obsidian' / 'founders-playbook.md').read_text(encoding='utf-8')",
        "    discarded = (run_dir / 'obsidian' / '_audit' / 'discarded.md').read_text(encoding='utf-8')",
        "    assert '<!-- page:' not in complete, complete",
        "    assert 'Chapter 4\\nMVP 阶段\\n15' not in complete, complete",
        "    assert '## 创业生命周期， 为 2026 重新启动' in complete, complete",
        "    assert '创业生命周期，为 2026 重新启动AI 正在' not in complete, complete",
        "    assert 'AI 正在重塑创业公司的搭建方式。' in complete, complete",
        "    assert '## MVP 阶段' in complete, complete",
        "    assert 'MVP 阶段的核心目标' in complete, complete",
        "    assert '\\n4\\n' not in complete, complete",
        "    assert '\\n16\\n' not in complete, complete",
        "    assert 'ExampleAuthor' not in complete, complete",
        "    assert 'example.com' not in complete, complete",
        "    assert '译后记' not in complete, complete",
        "    assert 'slide_chapter_divider' in discarded, discarded",
        "    assert 'translator_marketing_back_matter' in discarded, discarded",
        "    assert 'ExampleAuthor' in discarded, discarded",
        "    assert 'example.com' in discarded, discarded",
      ].join("\n"),
      [],
    );
  });

  it("drops only front-matter presenter/social strips and visual separators", () => {
    runPython(
      [
        "from kbprep_worker.obsidian_kb import apply_curated_obsidian_policy",
        "blocks = [",
        "    {'block_id': 'h1', 'type': 'section_heading', 'status': 'keep', 'text': '# Example Agent 在大型代码库中的最佳实践'},",
        "    {'block_id': 'source', 'type': 'paragraph', 'status': 'keep', 'text': '基于 Claude 官方博客 · [阅读原文](https://claude.com/blog/example)'},",
        "    {'block_id': 'presenter', 'type': 'paragraph', 'status': 'keep', 'text': '讲解：ExampleCreator2 [B站](https://space.bilibili.com/example) [抖音](https://www.douyin.com/user/example) [小红书](https://www.xiaohongshu.com/user/example) [YouTube](https://www.youtube.com/@example)'},",
        "    {'block_id': 'sep', 'type': 'paragraph', 'status': 'keep', 'text': '==================== 第一章 ===================='},",
        "    {'block_id': 'h2', 'type': 'section_heading', 'status': 'keep', 'text': '## 一、核心认知'},",
        "    {'block_id': 'case', 'type': 'paragraph', 'status': 'keep', 'text': '案例中作者介绍了自己为什么选择这个方案，并给出判断方法。'},",
        "    {'block_id': 'body_social', 'type': 'paragraph', 'status': 'keep', 'text': '正文里提到讲解：某团队在 YouTube 上测试标题，并保留 CTR 高的方向。'},",
        "]",
        "blocks = apply_curated_obsidian_policy(blocks, template_name='obsidian_course_kb')",
        "by_id = {b['block_id']: b for b in blocks}",
        "assert by_id['source']['status'] == 'keep', by_id['source']",
        "assert by_id['presenter']['status'] == 'discard', by_id['presenter']",
        "assert by_id['sep']['status'] == 'discard', by_id['sep']",
        "assert by_id['case']['status'] == 'keep', by_id['case']",
        "assert by_id['body_social']['status'] == 'keep', by_id['body_social']",
      ].join("\n"),
      [],
    );
  });

  it("exports inline HTML SVG diagrams as uncropped standalone SVG assets", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-html-svg-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "diagram.html");
      writeFileSync(
        sourcePath,
        [
          "<html><head><title>Diagram Test</title></head><body><main>",
          "<h1>Diagram Test</h1>",
          '<svg viewbox="0 0 680 480" width="100%" role="img" aria-label="Workflow diagram">',
          '<rect x="0" y="0" width="680" height="480" fill="#fff"/>',
          '<text x="340" y="240">threshold=0.8</text>',
          "</svg>",
          "<p>Step 1: keep the complete diagram and threshold=0.8.</p>",
          "</main></body></html>",
        ].join(""),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const converted = readFileSync(path.join(envelope.data.run_dir, "converted.md"), "utf8");
      const svgText = readFileSync(path.join(outputRoot, "images", "Diagram-Test-diagram-01.svg"), "utf8");
      const quality = JSON.parse(readFileSync(path.join(envelope.data.run_dir, "quality_report.json"), "utf8"));
      expect(envelope.data.strict_errors).toEqual([]);
      expect(converted).toContain("![Workflow diagram](images/Diagram-Test-diagram-01.svg)");
      expect(quality.image_retention.invalid_svg_count).toBe(0);
      expect(svgText).toContain('viewBox="0 0 680 480"');
      expect(svgText).toContain('width="680"');
      expect(svgText).toContain('height="480"');
      expect(svgText).toContain('preserveAspectRatio="xMidYMid meet"');
      expect(svgText).not.toContain("viewbox=");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("prepares curated Obsidian outputs when the legacy curated profile is selected", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-curated-obsidian-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "ExampleCourseManual.md");
      writeFileSync(
        sourcePath,
        [
          "# ExampleCreator: YouTube AI 内容出海把全球第一的视频平台变成自己的金矿？",
          "",
          "ExampleCreator，ExamplePersona1，ExamplePersona3，擅长 YouTube 内容出海，下面先Let me introduce myself。",
          "",
          "为什么在 YouTube 做 AI 内容出海？核心是先选择垂类赛道，再用脚本模板测试点击率，最后把可复用流程沉淀成 SOP。",
          "",
          "1）脚本测试：先生成 10 个标题，用 Gemini 判断信息差，再保留 CTR 高的方向。",
          "",
          "![作者头像](images/avatar.png)",
          "",
          "# 老黄牛：不要用 AI 优化传统的工作，而是重构流程",
          "",
          "不要用 AI 优化传统的工作，而是把输入、判断、输出重新拆开，让模型参与每一个可验证节点。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "curated_obsidian_kb",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const runDir = envelope.data.run_dir;
      const obsidianDir = path.join(runDir, "obsidian");
      const latestObsidianDir = path.join(outputRoot, "obsidian");
      const completePath = path.join(obsidianDir, "ExampleCourseManual.md");
      const latestCompletePath = path.join(latestObsidianDir, "ExampleCourseManual.md");
      const complete = readFileSync(completePath, "utf8");
      const latestCleaned = readFileSync(envelope.data.latest_outputs.cleaned_md, "utf8");
      const sourceFinalPath = path.join(inputDir, "鏅€氫汉鐨凙I搴旂敤瀹濆吀.cleaned.md");
      const index = readFileSync(path.join(obsidianDir, "00-索引.md"), "utf8");
      const discarded = readFileSync(path.join(obsidianDir, "_audit", "discarded.md"), "utf8");
      const auditDir = path.join(obsidianDir, "_audit");
      const latestAuditDir = path.join(latestObsidianDir, "_audit");
      const exportedQuality = JSON.parse(readFileSync(path.join(auditDir, "quality_report.json"), "utf8"));
      const exportedConversion = JSON.parse(readFileSync(path.join(auditDir, "conversion_report.json"), "utf8"));
      const exportedDiagnosis = JSON.parse(readFileSync(path.join(auditDir, "diagnosis_report.json"), "utf8"));
      const exportedMetadata = JSON.parse(readFileSync(path.join(auditDir, "run_metadata.json"), "utf8"));
      const exportedAudit = readFileSync(path.join(auditDir, "audit.md"), "utf8");

      expect(envelope.data.outputs.obsidian_dir).toBe(obsidianDir);
      expect(envelope.data.outputs.obsidian_complete).toBe(completePath);
      expect(envelope.data.latest_outputs.obsidian_dir).toBe(latestObsidianDir);
      expect(envelope.data.latest_outputs.obsidian_index).toBe(path.join(latestObsidianDir, "00-索引.md"));
      expect(envelope.data.latest_outputs.obsidian_complete).toBe(latestCompletePath);
      expect(envelope.data.latest_outputs.final_artifact_type).toBe("obsidian_dir");
      expect(envelope.data.latest_outputs.final_md).toBe(null);
      expect(existsSync(sourceFinalPath)).toBe(false);
      expect(existsSync(path.join(latestObsidianDir, "00-索引.md"))).toBe(true);
      expect(existsSync(latestCompletePath)).toBe(true);
      expect(complete).not.toContain("ExampleCreator:");
      expect(latestCleaned).not.toContain("ExampleCreator:");
      expect(complete).not.toContain("ExamplePersona1");
      expect(complete).toContain("为什么在 YouTube 做 AI 内容出海？");
      expect(complete).toContain("脚本测试");
      expect(index).toContain("[[ExampleCourseManual|完整正文]]");
      expect(index).toContain("[[案例/");
      expect(discarded).toContain("author_identity");
      expect(exportedQuality.strict_errors).toEqual([]);
      expect(exportedConversion.route_decision.actual_converter).toBe("direct_text");
      expect(exportedDiagnosis.capability.route).toBe("direct_text");
      expect(exportedMetadata.input_path).toBe(sourcePath);
      expect(exportedMetadata.source_sha256).toBe(exportedQuality.source_sha256);
      expect(exportedAudit).toContain("# kbprep audit");
      expect(existsSync(path.join(latestAuditDir, "quality_report.json"))).toBe(true);
      expect(existsSync(path.join(latestAuditDir, "conversion_report.json"))).toBe(true);
      expect(existsSync(path.join(latestAuditDir, "diagnosis_report.json"))).toBe(true);
      expect(existsSync(path.join(latestAuditDir, "run_metadata.json"))).toBe(true);
      expect(existsSync(path.join(latestAuditDir, "audit.md"))).toBe(true);
      expect(existsSync(path.join(auditDir, "quality_gates", "export_readiness.json"))).toBe(true);
      expect(existsSync(path.join(latestAuditDir, "quality_gates", "export_readiness.json"))).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("publishes the final markdown beside the source file with a source-derived name", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-final-name-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "ExampleTool橙皮书.txt");
      writeFileSync(sourcePath, ["# ExampleTool橙皮书", "", "步骤1：保留 FINAL_NAME_MARKER，并设置 threshold=0.8。"].join("\n"), "utf8");

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const finalPath = path.join(inputDir, "ExampleTool橙皮书.md");
      expect(envelope.data.latest_outputs.final_md).toBe(finalPath);
      expect(existsSync(finalPath)).toBe(true);
      expect(readFileSync(finalPath, "utf8")).toContain("FINAL_NAME_MARKER");
      expect(existsSync(path.join(outputRoot, "cleaned.md"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "runs"))).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not overwrite markdown source files when publishing the final markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-final-md-source-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "daily-note.md");
      const original = ["# 原始笔记", "", "步骤1：保留 ORIGINAL_MARKDOWN_MARKER。"].join("\n");
      writeFileSync(sourcePath, original, "utf8");

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const finalPath = path.join(inputDir, "daily-note.cleaned.md");
      expect(envelope.data.latest_outputs.final_md).toBe(finalPath);
      expect(readFileSync(sourcePath, "utf8")).toBe(original);
      expect(readFileSync(finalPath, "utf8")).toContain("ORIGINAL_MARKDOWN_MARKER");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
