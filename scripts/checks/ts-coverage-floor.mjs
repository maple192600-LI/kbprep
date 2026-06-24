import { existsSync, readFileSync } from "node:fs";

const args = parseArgs(process.argv.slice(2));
const summaryPath = args.summary ?? "coverage/coverage-summary.json";
const totalLinesFloor = numberArg(args["total-lines"], 85, "--total-lines");
const filePath = args.file ?? "src/runtime/pythonRuntime.ts";
const fileLinesFloor = numberArg(args["file-lines"], 80, "--file-lines");

if (!existsSync(summaryPath)) {
  fail(`coverage summary not found: ${summaryPath}`);
}

const summary = JSON.parse(readFileSync(summaryPath, "utf8"));
const totalLines = linePct(summary.total, "total");
const fileEntry = findFileEntry(summary, filePath);
const fileLines = linePct(fileEntry, filePath);
const failures = [];

if (totalLines < totalLinesFloor) {
  failures.push(`total line coverage ${totalLines}% is below ${totalLinesFloor}%`);
}
if (fileLines < fileLinesFloor) {
  failures.push(`${filePath} line coverage ${fileLines}% is below ${fileLinesFloor}%`);
}

if (failures.length) {
  fail(failures.join("\n"));
}

process.stdout.write(
  JSON.stringify(
    {
      ok: true,
      total_lines: totalLines,
      total_lines_floor: totalLinesFloor,
      file: filePath,
      file_lines: fileLines,
      file_lines_floor: fileLinesFloor,
    },
    null,
    2,
  ),
);
process.stdout.write("\n");

function parseArgs(rawArgs) {
  const parsed = {};
  for (let index = 0; index < rawArgs.length; index += 1) {
    const key = rawArgs[index];
    if (!key.startsWith("--")) continue;
    parsed[key.slice(2)] = rawArgs[index + 1];
    index += 1;
  }
  return parsed;
}

function numberArg(value, fallback, label) {
  if (value === undefined) return fallback;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    fail(`${label} must be a positive number`);
  }
  return parsed;
}

function findFileEntry(summary, requestedPath) {
  const normalizedRequested = normalizePath(requestedPath);
  const foundKey = Object.keys(summary).find((key) => normalizePath(key).endsWith(normalizedRequested));
  if (!foundKey) {
    fail(`coverage summary does not contain ${requestedPath}`);
  }
  return summary[foundKey];
}

function linePct(entry, label) {
  const pct = entry?.lines?.pct;
  if (typeof pct !== "number" || !Number.isFinite(pct)) {
    fail(`coverage summary entry missing numeric line pct: ${label}`);
  }
  return pct;
}

function normalizePath(value) {
  return String(value).replace(/\\/g, "/");
}

function fail(message) {
  process.stderr.write(`ts-coverage-floor failed:\n${message}\n`);
  process.exit(1);
}
