import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { pythonCommand, repoRoot } from "../helpers/workerHarness.js";

describe("kbprep worker governance guards", () => {
  it("routes TypeScript worker scenarios through the managed KBPrep venv wrapper", () => {
    const command = pythonCommand();
    const harnessText = readFileSync(path.join(repoRoot, "src", "test", "helpers", "workerHarness.ts"), "utf8");

    expect(command.command).toBe(process.execPath);
    expect(command.prefix).toEqual([path.join(repoRoot, "scripts", "python-venv.mjs")]);
    expect(harnessText).toContain("python-venv.mjs");
    expect(harnessText).not.toContain("KBPREP_TEST_PYTHON");
    expect(harnessText).not.toContain("command: \"py\"");
    expect(harnessText).not.toContain("\"python3\"");
    expect(harnessText).not.toContain("PYTHONPATH: path.join(repoRoot, \"python\")");
  });

  it("keeps TypeScript integration and coverage gates in project checks", () => {
    const packageJson = JSON.parse(readFileSync(path.join(repoRoot, "package.json"), "utf8"));
    const releaseCheckText = readFileSync(path.join(repoRoot, "scripts", "release-check.mjs"), "utf8");

    expect(packageJson.scripts["dev:check"]).toMatch(/\bnpm test\b/);
    expect(packageJson.scripts["test:coverage"]).toContain("vitest run");
    expect(packageJson.scripts["test:coverage"]).toContain("coverage.thresholds.lines=85");
    expect(packageJson.scripts["test:coverage"]).toContain("scripts/checks/ts-coverage-floor.mjs");
    expect(releaseCheckText).toContain("Run TypeScript coverage");
    expect(releaseCheckText).toContain("test:coverage");
  });

  it("blocks TypeScript coverage summaries that pass globally but leave runtime undercovered", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-ts-coverage-floor-"));
    try {
      const summaryPath = path.join(root, "coverage-summary.json");
      writeFileSync(
        summaryPath,
        JSON.stringify({
          total: { lines: { pct: 86 } },
          "C:/repo/src/runtime/pythonRuntime.ts": { lines: { pct: 70 } },
        }),
        "utf8",
      );

      const result = spawnSync(process.execPath, [
        "scripts/checks/ts-coverage-floor.mjs",
        "--summary",
        summaryPath,
        "--total-lines",
        "85",
        "--file",
        "src/runtime/pythonRuntime.ts",
        "--file-lines",
        "80",
      ], {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30_000,
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain("pythonRuntime.ts line coverage 70% is below 80%");

      writeFileSync(
        summaryPath,
        JSON.stringify({
          total: { lines: { pct: 86 } },
          "C:/repo/src/runtime/pythonRuntime.ts": { lines: { pct: 81 } },
        }),
        "utf8",
      );
      const pass = spawnSync(process.execPath, [
        "scripts/checks/ts-coverage-floor.mjs",
        "--summary",
        summaryPath,
        "--total-lines",
        "85",
        "--file",
        "src/runtime/pythonRuntime.ts",
        "--file-lines",
        "80",
      ], {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30_000,
      });

      expect(pass.status).toBe(0);
      expect(JSON.parse(pass.stdout).file_lines).toBe(81);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("blocks project guidance that tells tests or checks to use system Python", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-project-env-commands-"));
    try {
      writeFileSync(
        path.join(root, "README.md"),
        [
          "# Bad Commands",
          "",
          "```powershell",
          "cd python",
          "python -m unittest discover -s python/tests",
          "```",
          "",
          "```bash",
          "PYTHONPATH=python python -m kbprep_worker.cli --help",
          "```",
        ].join("\n"),
        "utf8",
      );

      const result = spawnSync(process.execPath, [
        "scripts/checks/project-env-commands.mjs",
        "--repo-root",
        root,
        "--check",
        "README.md",
      ], {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30_000,
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain("direct_system_python_command");
      expect(result.stderr).toContain("direct_pythonpath_command");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("blocks CI and Python tests that bypass the managed project environment", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-project-env-ci-"));
    try {
      mkdirSync(path.join(root, ".github", "workflows"), { recursive: true });
      mkdirSync(path.join(root, "python", "tests"), { recursive: true });
      writeFileSync(
        path.join(root, ".github", "workflows", "ci.yml"),
        [
          "name: CI",
          "jobs:",
          "  python:",
          "    steps:",
          "      - run: uv pip install --system -e python",
          "      - run: python -m unittest discover -s python/tests",
          "      - env:",
          "          PYTHONPATH: python",
          "        run: python -m kbprep_worker.cli --help",
        ].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(root, "python", "tests", "test_bad_env.py"),
        [
          "import subprocess",
          "",
          "def test_bad_env():",
          "    subprocess.run([",
          "        \"python\",",
          "        \"-m\",",
          "        \"kbprep_worker.cli\",",
          "        \"--help\",",
          "    ])",
        ].join("\n"),
        "utf8",
      );

      const result = spawnSync(process.execPath, [
        "scripts/checks/project-env-commands.mjs",
        "--repo-root",
        root,
      ], {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30_000,
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain(".github/workflows/ci.yml");
      expect(result.stderr).toContain("system_package_install");
      expect(result.stderr).toContain("direct_system_python_command");
      expect(result.stderr).toContain("github_actions_pythonpath");
      expect(result.stderr).toContain("python/tests/test_bad_env.py");
      expect(result.stderr).toContain("python_test_subprocess_system_python");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("blocks regex HTML parsing and f-string YAML generation in Python worker logic", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-forbidden-patterns-"));
    try {
      const workerDir = path.join(root, "python", "kbprep_worker");
      mkdirSync(workerDir, { recursive: true });
      writeFileSync(
        path.join(workerDir, "bad_html.py"),
        [
          "import re",
          "",
          "def strip_html(value: str) -> str:",
          "    return re.sub(r\"<[^>]+>\", \"\", value)",
        ].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(workerDir, "bad_yaml.py"),
        [
          "def frontmatter(title: str) -> str:",
          "    return f\"\"\"---",
          "title: {title}",
          "---",
          "\"\"\"",
        ].join("\n"),
        "utf8",
      );

      const result = spawnSync(process.execPath, [
        "scripts/checks/forbidden-patterns.mjs",
        "--repo-root",
        root,
        "--check",
        "python/kbprep_worker/bad_html.py",
        "--check",
        "python/kbprep_worker/bad_yaml.py",
      ], {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30_000,
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain("regex_html_parsing");
      expect(result.stderr).toContain("fstring_yaml_generation");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
