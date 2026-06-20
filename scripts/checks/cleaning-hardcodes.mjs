import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const defaultRepoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const pythonVenvScript = "scripts/python-venv.mjs";
const args = parseArgs(process.argv.slice(2));
const repoRoot = path.resolve(args.repoRoot ?? defaultRepoRoot);
const rulesRoot = path.resolve(repoRoot, args.rulesRoot ?? "rules");

const defaultCheckedFiles = [
  "python/kbprep_worker/clean_rules.py",
  "python/kbprep_worker/classify_blocks.py",
  "python/kbprep_worker/images.py",
  "python/kbprep_worker/diagnose",
  "python/kbprep_worker/prepare_diagnosis.py",
  "python/kbprep_worker/quality",
  "python/kbprep_worker/obsidian_kb",
  "python/kbprep_worker/feedback",
  "python/kbprep_worker/document_type.py",
];
const checkedFiles = args.check.length ? args.check : defaultCheckedFiles;

const baseForbiddenTerms = [
  "PROMOTIONAL_LINE_RE",
  "CONTEXTUAL_CTA_KEYWORDS",
  "SOCIAL_PROFILE_PLATFORMS",
  "BRAND_PROGRAM_PACKAGING_TERMS",
  "公众号",
  "小红书",
  "二维码",
  "扫码",
  "入群",
  "加微信",
  "关注",
  "生财AI宝典",
  "生财",
  "课程品牌",
];

const fileSpecificForbiddenTerms = {
  "python/kbprep_worker/document_type.py": [
  "课程",
  "报告",
  "摘要",
  "市场规模",
  "订阅",
  "购物车",
  "主持人",
  "嘉宾",
  ],
};

const violations = [];
const rulesText = rulesCorpus(rulesRoot);
for (const relative of checkedFiles) {
  const absolute = path.join(repoRoot, relative);
  const forbiddenTerms = [
    ...baseForbiddenTerms,
    ...(fileSpecificForbiddenTerms[relative] ?? []),
  ];
  for (const file of pythonFiles(absolute)) {
    const fileRelative = path.relative(repoRoot, file).replaceAll(path.sep, "/");
    const text = readFileSync(file, "utf8");
    const lines = text.split(/\r?\n/);
    for (const [index, line] of lines.entries()) {
      for (const term of forbiddenTerms) {
        if (line.includes(term)) {
          violations.push({ file: fileRelative, line: index + 1, term });
        }
      }
    }
    for (const literal of pythonStringLiterals(file)) {
      for (const term of forbiddenTerms) {
        if (literal.value.includes(term)) {
          violations.push({ file: fileRelative, line: literal.line, term, source: "decoded_string" });
        }
      }
      for (const term of sensitiveRuleTerms(literal.value)) {
        if (!rulesText.includes(term)) {
          violations.push({ file: fileRelative, line: literal.line, term, source: "string_not_in_rules" });
        }
      }
    }
  }
}

function pythonFiles(target) {
  const stat = statSync(target);
  if (stat.isFile()) {
    return target.endsWith(".py") ? [target] : [];
  }
  return readdirSync(target, { withFileTypes: true })
    .flatMap((entry) => {
      const child = path.join(target, entry.name);
      if (entry.isDirectory()) {
        return pythonFiles(child);
      }
      return entry.isFile() && entry.name.endsWith(".py") ? [child] : [];
    });
}

function pythonStringLiterals(file) {
  const code = [
    "import ast, json, sys",
    "path = sys.argv[1]",
    "tree = ast.parse(open(path, encoding='utf-8').read(), filename=path)",
    "items = []",
    "for node in ast.walk(tree):",
    "    if isinstance(node, ast.Constant) and isinstance(node.value, str):",
    "        items.append({'line': node.lineno, 'value': node.value})",
    "print(json.dumps(items, ensure_ascii=False))",
  ].join("\n");
  const result = spawnSync(process.execPath, [path.join(defaultRepoRoot, pythonVenvScript), "-", file], {
    cwd: defaultRepoRoot,
    input: code,
    encoding: "utf8",
  });
  if (result.status !== 0) {
    violations.push({
      file: path.relative(repoRoot, file).replaceAll(path.sep, "/"),
      line: 0,
      term: "python_ast_parse_failed",
      source: result.stderr || result.stdout || String(result.error || ""),
    });
    return [];
  }
  return JSON.parse(result.stdout || "[]");
}

function rulesCorpus(root) {
  if (!existsSync(root)) return "";
  return collectFiles(root)
    .filter((file) => file.endsWith(".json") || file.endsWith(".jsonl"))
    .map((file) => readFileSync(file, "utf8"))
    .join("\n");
}

function collectFiles(target) {
  const stat = statSync(target);
  if (stat.isFile()) return [target];
  return readdirSync(target, { withFileTypes: true }).flatMap((entry) => {
    const child = path.join(target, entry.name);
    return entry.isDirectory() ? collectFiles(child) : [child];
  });
}

function sensitiveRuleTerms(value) {
  const terms = new Set();
  for (const match of value.matchAll(/[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9＋+·《》「」]{1,}/g)) {
    const term = match[0].replace(/[《》「」]/g, "");
    if (isSensitiveBusinessTerm(term)) {
      terms.add(term);
    }
  }
  return [...terms];
}

function isSensitiveBusinessTerm(term) {
  if (term.length > 12) {
    return false;
  }
  return /(?:品牌|课程|训练营|社群|入群|扫码|二维码|关注|小红书|公众号|视频号|抖音|生财|宝典|会员|优惠|退款|体验卡|领取|购买|营销|广告)/.test(term);
}

function parseArgs(rawArgs) {
  const result = { check: [] };
  for (let index = 0; index < rawArgs.length; index += 1) {
    const arg = rawArgs[index];
    if (arg === "--repo-root") {
      result.repoRoot = rawArgs[++index];
    } else if (arg === "--rules-root") {
      result.rulesRoot = rawArgs[++index];
    } else if (arg === "--check") {
      result.check.push(rawArgs[++index]);
    }
  }
  return result;
}

if (violations.length) {
  process.stderr.write(JSON.stringify({ violations }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(JSON.stringify({
  checkedFiles: checkedFiles.length,
  baseForbiddenTerms: baseForbiddenTerms.length,
  fileSpecificForbiddenTerms: Object.values(fileSpecificForbiddenTerms).reduce((total, terms) => total + terms.length, 0),
  violations,
}, null, 2));
process.stdout.write("\n");
