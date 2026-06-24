import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { expect } from "vitest";
export { parseEnvelope } from "../../worker.js";

export const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

const privateTemplatesDir = path.join(repoRoot, ".kbprep", "rules", "templates");
let privateTemplateFixturesReady = false;

const selfMediaCourseTemplate = {
  schema: "kbprep.cleaning_rules.v1",
  description: "Test-only private self-media/course cleanup template.",
  rules: [
    {
      type: "promotional_line",
      id: "test-private-follow-account",
      action: "discard",
      match: "regex",
      pattern: "欢迎关注公众号|配套视频教程.*B站|配套视频教程",
      reason: "test private self-media CTA",
      risk_tag: "private_self_media_cta",
    },
    {
      type: "promotional_line",
      id: "test-private-scan-community",
      action: "discard",
      match: "regex",
      pattern: "扫码(?:体验|加入社群|进群)|长按识别二维码|免费领取体验卡|添加老师",
      reason: "test private QR/community CTA",
      risk_tag: "private_self_media_qr_cta",
    },
  ],
  keyword_sets: {
    cta_keywords: ["公众号", "欢迎关注公众号", "配套视频教程", "扫码体验", "扫码加入社群", "免费领取体验卡"],
    qr_image_markers: ["二维码", "扫码", "长按识别"],
    image_qr_indicators: ["二维码", "扫码", "长按识别", "领取体验卡", "公众号", "关注公众号"],
    image_marketing_indicators: ["海报", "宣传", "课程封面"],
    image_operation_indicators: ["操作", "步骤", "后台", "设置", "threshold"],
    image_proof_indicators: ["收益", "成交", "转化", "数据截图"],
    image_educational_heading_indicators: ["教程", "步骤", "方法", "操作"],
    marketing_wrapper_passthrough_titles: ["ExampleCourse", "《ExampleCourse》"],
    marketing_wrapper_heading_terms: ["找项目", "版权声明", "致谢", "ExampleProgram3"],
    marketing_wrapper_back_matter_terms: ["写在最后", "版权声明", "致谢"],
    marketing_wrapper_line_patterns: [
      "和\\s*\\d{4,}\\+\\s*实战派同行",
      "3\\s*天内无理由退款",
      "扫码体验.*ExampleProgram3",
    ],
    business_method_context_terms: ["方法", "步骤", "案例", "复盘", "运营", "转化", "账号矩阵", "工具"],
  },
};

const obsidianCourseTemplate = {
  schema: "kbprep.obsidian_template.v1",
  description: "Test-only private course Obsidian template.",
  categories: ["认知", "方法", "案例"],
  default_category: "认知",
  method_category: "方法",
  cognition_category: "认知",
  case_category: "案例",
  social_profile_labels: ["讲解", "作者", "嘉宾"],
  social_profile_platforms: ["B站", "抖音", "小红书", "YouTube", "公众号", "X", "官网"],
  provenance_terms: ["基于", "阅读原文", "来源", "出处"],
  author_bio_terms: ["Let me introduce myself", "ExamplePersona1", "ExamplePersona3"],
  bio_role_terms: ["ExamplePersona2", "自媒体博主", "ExamplePersona3"],
  author_credential_terms: ["ExampleMarketingClaim"],
  knowledge_terms: ["为什么", "核心", "方法", "步骤", "流程", "策略", "案例", "复盘", "参数", "SOP"],
  case_terms: ["案例", "ExampleMember", "融资", "营收", "AI产品出海", "内容出海"],
  method_terms: ["方法", "步骤", "脚本", "流程", "SOP", "策略"],
  cognition_terms: ["为什么", "认知", "机会", "底层逻辑"],
  packaging_heading_terms: ["ExampleCourse", "ExampleCommunity", "写在最后", "版权声明", "致谢", "ExampleProgram3"],
  packaging_heading_regexes: [],
  brand_heading_replacements: [
    ["认知篇：", ""],
    ["方法篇：", ""],
    ["案例篇：", ""],
    ["ExampleCommunityInsight", "AI领域看到的3个超级机会"],
    ["ExampleCommunityPrep", ""],
  ],
  layout_table_terms: ["帐户明细", "日期范围"],
  brand_program_packaging_terms: ["ExampleProgram1", "ExampleProgram2", "ExampleCommunityAction"],
  translator_back_matter_terms: ["译后记", "ExampleAuthor", "ExampleAuthor", "小红书", "公众号", "YouTube", "example.com", "@ExampleHandle"],
};

function ensurePrivateTemplateFixtures() {
  if (privateTemplateFixturesReady) return;
  mkdirSync(privateTemplatesDir, { recursive: true });
  writeFileSync(
    path.join(privateTemplatesDir, "self_media_course.json"),
    JSON.stringify(selfMediaCourseTemplate, null, 2),
    "utf8",
  );
  writeFileSync(
    path.join(privateTemplatesDir, "obsidian_course_kb.json"),
    JSON.stringify(obsidianCourseTemplate, null, 2),
    "utf8",
  );
  privateTemplateFixturesReady = true;
}

export function pythonCommand(_usePluginRuntime = false) {
  return {
    command: process.execPath,
    prefix: [path.join(repoRoot, "scripts", "python-venv.mjs")],
  };
}

export function shouldUsePluginRuntime(payload: Record<string, unknown>) {
  const inputPath = typeof payload.input_path === "string" ? payload.input_path : "";
  const ext = path.extname(inputPath).toLowerCase();
  return new Set([
    ".pdf", ".mobi", ".doc", ".ppt", ".xls",
    ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif",
  ]).has(ext);
}

export function runWorker(command: string, payload: Record<string, unknown>, expectedStatus = 0) {
  ensurePrivateTemplateFixtures();
  const python = pythonCommand(shouldUsePluginRuntime(payload));
  const result = spawnSync(python.command, [...python.prefix, "-m", "kbprep_worker.cli", command, "--json-stdin"], {
    cwd: repoRoot,
    input: JSON.stringify(payload),
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONUTF8: "1",
    },
    timeout: 30_000,
  });

  expect(result.status, result.stderr).toBe(expectedStatus);
  const lines = result.stdout.trim().split(/\r?\n/).filter(Boolean);
  return JSON.parse(lines.at(-1) ?? "{}");
}

export function runWorkerRawInput(command: string, rawInput: string, expectedStatus = 0) {
  ensurePrivateTemplateFixtures();
  const python = pythonCommand();
  const result = spawnSync(python.command, [...python.prefix, "-m", "kbprep_worker.cli", command, "--json-stdin"], {
    cwd: repoRoot,
    input: rawInput,
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONUTF8: "1",
    },
    timeout: 30_000,
  });

  expect(result.status, result.stderr).toBe(expectedStatus);
  const lines = result.stdout.trim().split(/\r?\n/).filter(Boolean);
  return JSON.parse(lines.at(-1) ?? "{}");
}

export function runPython(code: string, args: string[], usePluginRuntime = false) {
  ensurePrivateTemplateFixtures();
  const python = pythonCommand(usePluginRuntime);
  const result = spawnSync(python.command, [...python.prefix, "-", ...args], {
    cwd: repoRoot,
    input: code,
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONUTF8: "1",
    },
    timeout: 30_000,
  });

  expect(result.status, result.stderr).toBe(0);
}

export function runPythonJson(code: string, args: string[] = [], extraEnv: Record<string, string> = {}) {
  ensurePrivateTemplateFixtures();
  const python = pythonCommand();
  const result = spawnSync(python.command, [...python.prefix, "-", ...args], {
    cwd: repoRoot,
    input: code,
    encoding: "utf8",
    env: {
      ...process.env,
      ...extraEnv,
      PYTHONUTF8: "1",
    },
    timeout: 30_000,
  });

  expect(result.status, result.stderr).toBe(0);
  return JSON.parse(result.stdout.trim() || "{}");
}

export function makeTextLayerPdf(pdfPath: string) {
  runPython(
    [
      "import fitz, sys",
      "pdf_path = sys.argv[1]",
      "doc = fitz.open()",
      "page = doc.new_page(width=595, height=842)",
      "page.insert_text((72, 72), 'Step 1: open settings and set threshold to 0.8.')",
      "page.insert_text((72, 96), 'Step 2: record failure details and retry_count values.')",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath],
    true,
  );
}

export function makeChineseTextLayerPdf(pdfPath: string) {
  runPython(
    [
      "import fitz, sys",
      "pdf_path = sys.argv[1]",
      "doc = fitz.open()",
      "page = doc.new_page(width=595, height=842)",
      "page.insert_text((72, 72), '步骤 1：打开设置并保留 threshold=0.8。')",
      "page.insert_text((72, 96), '步骤 2：记录失败原因和 retry_count=3。')",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath],
    true,
  );
}

export function makeMultiColumnTextPdf(pdfPath: string) {
  runPython(
    [
      "import fitz, sys",
      "pdf_path = sys.argv[1]",
      "doc = fitz.open()",
      "page = doc.new_page(width=595, height=842)",
      "left_lines = [",
      "    'Column A step 1: open settings and keep threshold=0.8.',",
      "    'Column A step 2: record retry_count=3 before export.',",
      "]",
      "right_lines = [",
      "    'Column B step 3: verify failure_reason=timeout.',",
      "    'Column B step 4: keep the exact audit evidence.',",
      "]",
      "for index, text in enumerate(left_lines):",
      "    page.insert_textbox(fitz.Rect(72, 72 + index * 90, 250, 145 + index * 90), text)",
      "for index, text in enumerate(right_lines):",
      "    page.insert_textbox(fitz.Rect(340, 72 + index * 90, 520, 145 + index * 90), text)",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath],
    true,
  );
}

export function makeTableHeavyPdf(pdfPath: string) {
  runPython(
    [
      "import fitz, sys",
      "pdf_path = sys.argv[1]",
      "doc = fitz.open()",
      "page = doc.new_page(width=595, height=842)",
      "x0, y0, cell_w, cell_h = 72, 72, 130, 36",
      "for row in range(5):",
      "    y = y0 + row * cell_h",
      "    page.draw_line((x0, y), (x0 + cell_w * 3, y), color=(0, 0, 0), width=0.8)",
      "for col in range(4):",
      "    x = x0 + col * cell_w",
      "    page.draw_line((x, y0), (x, y0 + cell_h * 4), color=(0, 0, 0), width=0.8)",
      "rows = [",
      "    ('Metric', 'Value', 'Reason'),",
      "    ('threshold', '0.8', 'kept for setup'),",
      "    ('retry_count', '3', 'kept for replay'),",
      "    ('failure_reason', 'timeout', 'kept for audit'),",
      "]",
      "for row_index, row in enumerate(rows):",
      "    for col_index, text in enumerate(row):",
      "        page.insert_text((x0 + col_index * cell_w + 8, y0 + row_index * cell_h + 22), text)",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath],
    true,
  );
}

export function makeImageOnlyPdf(pdfPath: string, imagePath: string) {
  const png1x1 = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
    "base64",
  );
  writeFileSync(imagePath, png1x1);
  runPython(
    [
      "import fitz, sys",
      "pdf_path, image_path = sys.argv[1], sys.argv[2]",
      "doc = fitz.open()",
      "page = doc.new_page(width=595, height=842)",
      "page.insert_image(fitz.Rect(72, 72, 320, 320), filename=image_path)",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath, imagePath],
    true,
  );
}

export function makeLandscapeImagePdf(pdfPath: string, imagePath: string) {
  const png1x1 = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
    "base64",
  );
  writeFileSync(imagePath, png1x1);
  runPython(
    [
      "import fitz, sys",
      "pdf_path, image_path = sys.argv[1], sys.argv[2]",
      "doc = fitz.open()",
      "for _ in range(3):",
      "    page = doc.new_page(width=1280, height=720)",
      "    page.insert_image(fitz.Rect(0, 0, 1280, 720), filename=image_path)",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath, imagePath],
    true,
  );
}

export function makeLandscapeTextPdf(pdfPath: string) {
  runPython(
    [
      "import fitz, sys",
      "pdf_path = sys.argv[1]",
      "doc = fitz.open()",
      "for index in range(4):",
      "    page = doc.new_page(width=1280, height=720)",
      "    page.insert_text((72, 72), f'Slide {index + 1}: keep concrete setup step threshold=0.8.')",
      "    page.insert_text((72, 104), 'Record retry_count=3 and failure_reason=timeout.')",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath],
    true,
  );
}

export function makeGarbledTextLayerPdf(pdfPath: string) {
  runPython(
    [
      "import fitz, sys",
      "pdf_path = sys.argv[1]",
      "doc = fitz.open()",
      "garbled = 'Ჭ䌦圳➉ᵜⰭ䕇✮⦽ ' * 80",
      "for index in range(6):",
      "    page = doc.new_page(width=595, height=842)",
      "    page.insert_textbox(fitz.Rect(72, 72, 520, 760), garbled)",
      "doc.save(pdf_path)",
    ].join("\n"),
    [pdfPath],
    true,
  );
}

export function makeOfficeFixtures(docxPath: string, pptxPath: string, xlsxPath: string) {
  runPython(
    [
      "import base64, sys, zipfile",
      "docx_path, pptx_path, xlsx_path = sys.argv[1:4]",
      "png1x1 = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=')",
      "def write_zip(path, files):",
      "    with zipfile.ZipFile(path, 'w') as z:",
      "        for name, content in files.items():",
      "            z.writestr(name, content)",
      "write_zip(docx_path, {",
      "  '[Content_Types].xml': '<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"/>',",
      "  'word/document.xml': '''<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><w:body>",
      "    <w:p><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr><w:r><w:t>DOCX Tutorial</w:t></w:r></w:p>",
      "    <w:p><w:r><w:t>Open the dashboard and set threshold=0.8 before exporting.</w:t></w:r></w:p>",
      "    <w:p><w:r><w:drawing><a:blip r:embed=\"rIdDocImage1\"/></w:drawing></w:r></w:p>",
      "    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Field</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc></w:tr>",
      "    <w:tr><w:tc><w:p><w:r><w:t>retry_count</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>3</w:t></w:r></w:p></w:tc></w:tr></w:tbl>",
      "  </w:body></w:document>''',",
      "  'word/_rels/document.xml.rels': '''<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rIdDocImage1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image\" Target=\"media/doc-step.png\"/></Relationships>''',",
      "  'word/media/doc-step.png': png1x1",
      "})",
      "write_zip(pptx_path, {",
      "  '[Content_Types].xml': '<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"/>',",
      "  'ppt/slides/slide1.xml': '''<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><p:cSld><p:spTree>",
      "    <p:sp><p:txBody><a:p><a:r><a:t>PPT Tutorial Slide</a:t></a:r></a:p><a:p><a:r><a:t>Keep platform setup steps and failure_reason=timeout.</a:t></a:r></a:p></p:txBody></p:sp>",
      "    <p:pic><p:blipFill><a:blip r:embed=\"rIdImage1\"/></p:blipFill></p:pic>",
      "  </p:spTree></p:cSld></p:sld>''',",
      "  'ppt/slides/_rels/slide1.xml.rels': '''<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rIdImage1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image\" Target=\"../media/step.png\"/></Relationships>''',",
      "  'ppt/media/step.png': png1x1,",
      "  'ppt/slides/slide2.xml': '''<p:sld xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"><p:cSld><p:spTree>",
      "    <p:sp><p:txBody><a:p><a:r><a:t>PPT Case Slide</a:t></a:r></a:p><a:p><a:r><a:t>Record retry_count=3 and keep the failed account example.</a:t></a:r></a:p></p:txBody></p:sp>",
      "  </p:spTree></p:cSld></p:sld>'''",
      "})",
      "write_zip(xlsx_path, {",
      "  '[Content_Types].xml': '<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"/>',",
      "  'xl/workbook.xml': '''<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheets><sheet name=\"Params\" sheetId=\"1\" r:id=\"rId1\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"/></sheets></workbook>''',",
      "  'xl/sharedStrings.xml': '''<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><si><t>Name</t></si><si><t>Value</t></si><si><t>threshold</t></si><si><t>0.8</t></si></sst>''',",
      "  'xl/worksheets/sheet1.xml': '''<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData><row><c t=\"s\"><v>0</v></c><c t=\"s\"><v>1</v></c></row><row><c t=\"s\"><v>2</v></c><c t=\"s\"><v>3</v></c></row></sheetData></worksheet>'''",
      "})",
    ].join("\n"),
    [docxPath, pptxPath, xlsxPath],
  );
}

export function makeEpubFixture(epubPath: string) {
  runPython(
    [
      "import base64, sys, zipfile",
      "epub_path = sys.argv[1]",
      "png1x1 = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=')",
      "files = {",
      "  'mimetype': 'application/epub+zip',",
      "  'META-INF/container.xml': '''<?xml version=\"1.0\"?><container version=\"1.0\" xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\"><rootfiles><rootfile full-path=\"OEBPS/content.opf\" media-type=\"application/oebps-package+xml\"/></rootfiles></container>''',",
      "  'OEBPS/content.opf': '''<?xml version=\"1.0\"?><package version=\"3.0\" xmlns=\"http://www.idpf.org/2007/opf\"><manifest><item id=\"c1\" href=\"chapter1.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"c2\" href=\"chapter2.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"c3\" href=\"links.xhtml\" media-type=\"application/xhtml+xml\"/><item id=\"img1\" href=\"images/step.png\" media-type=\"image/png\"/></manifest><spine><itemref idref=\"c1\"/><itemref idref=\"c2\"/><itemref idref=\"c3\"/></spine></package>''',",
      "  'OEBPS/chapter1.xhtml': '''<html xmlns=\"http://www.w3.org/1999/xhtml\"><body><h1>第一章 工具准备</h1><p>第一步：打开 ExampleTool 后台，把 threshold=0.8，并记录 failure_reason=timeout。</p><p>这一步必须保留工具名、参数和失败原因。</p></body></html>''',",
      "  'OEBPS/chapter2.xhtml': '''<html xmlns=\"http://www.w3.org/1999/xhtml\"><body><h1>第二章 案例复盘</h1><p>案例：账号设置里出现 retry_count=3 时，需要记录限制条件，不能总结成一句话。</p><p>扫码加入社群领取体验卡。</p></body></html>''',",
      "  'OEBPS/links.xhtml': '''<html xmlns=\"http://www.w3.org/1999/xhtml\"><body><h1>EPUB Assets</h1><p>Tool link: <a href=\"https://example.com/epub-tool\">open tool</a></p><p><img src=\"images/step.png\" alt=\"EPUB screenshot\"/></p></body></html>''',",
      "  'OEBPS/images/step.png': png1x1,",
      "}",
      "with zipfile.ZipFile(epub_path, 'w') as z:",
      "    for name, content in files.items():",
      "        z.writestr(name, content)",
    ].join("\n"),
    [epubPath],
  );
}

export function normalizeMarkdownText(text: string) {
  return text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
}
