import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const defaultRepoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const args = parseArgs(process.argv.slice(2));
const repoRoot = path.resolve(args.repoRoot ?? defaultRepoRoot);
const checkedFiles = args.check.length ? args.check : ["python/kbprep_worker"];
const violations = [];

for (const relative of checkedFiles) {
  const absolute = path.join(repoRoot, relative);
  if (!existsSync(absolute)) continue;
  for (const file of pythonFiles(absolute)) {
    const source = readFileSync(file, "utf8");
    const relativeFile = path.relative(repoRoot, file).replaceAll(path.sep, "/");
    inspectRegexHtmlPatterns(relativeFile, source);
    inspectFStringYaml(relativeFile, source);
  }
}

function inspectRegexHtmlPatterns(file, source) {
  const callPattern = /\bre\.(?:sub|search|match|findall|finditer|split|compile)\(\s*(?:r|R|u|U|f|F|fr|rf|Fr|Rf|fR|rF)?(['"])([\s\S]*?)\1/g;
  for (const match of source.matchAll(callPattern)) {
    const pattern = match[2];
    if (!looksLikeHtmlParsingRegex(pattern)) continue;
    violations.push({
      file,
      line: lineNumber(source, match.index ?? 0),
      rule: "regex_html_parsing",
      pattern,
    });
  }
}

function inspectFStringYaml(file, source) {
  const frontmatterPattern = /\bf(?:r|R)?("""|''')([\s\S]*?)\1/g;
  for (const match of source.matchAll(frontmatterPattern)) {
    const body = match[2];
    if (!looksLikeYamlFrontmatter(body)) continue;
    violations.push({
      file,
      line: lineNumber(source, match.index ?? 0),
      rule: "fstring_yaml_generation",
    });
  }
}

function looksLikeHtmlParsingRegex(pattern) {
  const compact = pattern.toLowerCase().replace(/\s+/g, "");
  return ["<[^>]+>", "<table[^", "</table", "<tr[^", "</tr", "<t[dh]", "</t[dh]", "<br", "<(script|style", "</(p|div|li|h"].some((token) =>
    compact.includes(token),
  );
}

function looksLikeYamlFrontmatter(body) {
  return body.includes("---") && /(^|\n)[a-zA-Z_][\w-]*\s*:/.test(body);
}

function pythonFiles(target) {
  const stat = statSync(target);
  if (stat.isFile()) {
    return target.endsWith(".py") ? [target] : [];
  }
  return readdirSync(target, { withFileTypes: true }).flatMap((entry) => {
    const child = path.join(target, entry.name);
    if (entry.isDirectory()) {
      if (["__pycache__", ".venv", ".git", "build", "dist"].includes(entry.name)) {
        return [];
      }
      return pythonFiles(child);
    }
    return entry.isFile() && entry.name.endsWith(".py") ? [child] : [];
  });
}

function lineNumber(source, index) {
  return source.slice(0, index).split(/\r?\n/).length;
}

function parseArgs(rawArgs) {
  const result = { check: [] };
  for (let index = 0; index < rawArgs.length; index += 1) {
    const arg = rawArgs[index];
    if (arg === "--repo-root") {
      result.repoRoot = rawArgs[++index];
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

process.stdout.write(
  JSON.stringify(
    {
      checkedFiles: checkedFiles.length,
      violations,
    },
    null,
    2,
  ),
);
process.stdout.write("\n");
