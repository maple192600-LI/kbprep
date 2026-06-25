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
    expect(harnessText).not.toContain('command: "py"');
    expect(harnessText).not.toContain('"python3"');
    expect(harnessText).not.toContain('PYTHONPATH: path.join(repoRoot, "python")');
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

      const result = spawnSync(
        process.execPath,
        [
          "scripts/checks/ts-coverage-floor.mjs",
          "--summary",
          summaryPath,
          "--total-lines",
          "85",
          "--file",
          "src/runtime/pythonRuntime.ts",
          "--file-lines",
          "80",
        ],
        {
          cwd: repoRoot,
          encoding: "utf8",
          timeout: 30_000,
        },
      );

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
      const pass = spawnSync(
        process.execPath,
        [
          "scripts/checks/ts-coverage-floor.mjs",
          "--summary",
          summaryPath,
          "--total-lines",
          "85",
          "--file",
          "src/runtime/pythonRuntime.ts",
          "--file-lines",
          "80",
        ],
        {
          cwd: repoRoot,
          encoding: "utf8",
          timeout: 30_000,
        },
      );

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

      const result = spawnSync(process.execPath, ["scripts/checks/project-env-commands.mjs", "--repo-root", root, "--check", "README.md"], {
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
          '        "python",',
          '        "-m",',
          '        "kbprep_worker.cli",',
          '        "--help",',
          "    ])",
        ].join("\n"),
        "utf8",
      );

      const result = spawnSync(process.execPath, ["scripts/checks/project-env-commands.mjs", "--repo-root", root], {
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
        ["import re", "", "def strip_html(value: str) -> str:", '    return re.sub(r"<[^>]+>", "", value)'].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(workerDir, "bad_yaml.py"),
        ["def frontmatter(title: str) -> str:", '    return f"""---', "title: {title}", "---", '"""'].join("\n"),
        "utf8",
      );

      const result = spawnSync(
        process.execPath,
        [
          "scripts/checks/forbidden-patterns.mjs",
          "--repo-root",
          root,
          "--check",
          "python/kbprep_worker/bad_html.py",
          "--check",
          "python/kbprep_worker/bad_yaml.py",
        ],
        {
          cwd: repoRoot,
          encoding: "utf8",
          timeout: 30_000,
        },
      );

      expect(result.status).toBe(1);
      expect(result.stderr).toContain("regex_html_parsing");
      expect(result.stderr).toContain("fstring_yaml_generation");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("blocks implementation status files that omit required capability ids", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-implementation-status-required-"));
    try {
      const statusDir = path.join(root, "docs", "development");
      mkdirSync(statusDir, { recursive: true });
      writeFileSync(
        path.join(statusDir, "kbprep-implementation-status.json"),
        JSON.stringify(
          {
            schema: "kbprep.implementation_status.v1",
            capabilities: [
              {
                id: "design_source_alignment",
                label: "Protected design and flowchart alignment",
                status: "implemented",
                scope: "Design sources are aligned.",
                evidence: ["docs/kbprep-core-flow-design.md", "scripts/checks/development-docs.mjs"],
                prohibitedClaims: [],
              },
            ],
          },
          null,
          2,
        ),
        "utf8",
      );

      const result = spawnSync(process.execPath, ["scripts/checks/implementation-status.mjs", "--repo-root", root], {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30_000,
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain("missing required capability id: document_type_classification");
      expect(result.stderr).toContain("missing required capability id: job_status_envelope");
      expect(result.stderr).toContain("missing required capability id: youtube_url_routes");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("requires implemented and partial status capabilities to cite code or test evidence", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-implementation-status-evidence-"));
    try {
      const statusDir = path.join(root, "docs", "development");
      mkdirSync(statusDir, { recursive: true });
      writeFileSync(
        path.join(statusDir, "kbprep-implementation-status.json"),
        JSON.stringify(
          {
            schema: "kbprep.implementation_status.v1",
            capabilities: [
              statusCapability("design_source_alignment", "implemented", [
                "docs/kbprep-core-flow-design.md",
                "scripts/checks/development-docs.mjs",
              ]),
              statusCapability("source_side_publish", "implemented", ["README.md", "python/tests/test_publish_safety.py"]),
              statusCapability("conversion_quality_gate", "partial", [
                "docs/development/04-conversion-quality-gate.md",
                "python/tests/test_conversion_gate.py",
              ]),
              statusCapability("canonical_ir_contract", "partial", [
                "docs/development/02-canonical-ir-contract.md",
                "python/tests/test_canonical_ir_manifest.py",
              ]),
              statusCapability("document_type_classification", "partial", ["docs/development/05-document-type-classification.md"]),
              statusCapability("cleaning_policy_snapshot", "partial", [
                "docs/development/06-cleaning-policy-library.md",
                "python/tests/test_cleaning_policy_snapshot.py",
              ]),
              statusCapability("patch_clean_view", "design_only", ["docs/development/07-cleaning-unit-patch-clean-view.md"]),
              statusCapability("job_status_envelope", "implemented", ["python/tests/test_envelope_status.py"]),
              statusCapability("feedback_rule_learning", "partial", [
                "docs/feedback-learning.md",
                "python/tests/test_feedback_proposals.py",
              ]),
              statusCapability("batch_playlist_rerun", "partial", ["python/tests/test_batch_status_manifest.py"]),
              statusCapability("media_local_transcript", "partial", ["src/test/scenarios/worker-core-runtime-part2.test.ts"]),
              statusCapability("youtube_url_routes", "design_only", ["docs/development/11-multimedia-youtube-optional.md"]),
            ],
          },
          null,
          2,
        ),
        "utf8",
      );

      const result = spawnSync(process.execPath, ["scripts/checks/implementation-status.mjs", "--repo-root", root], {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30_000,
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain("implemented or partial capabilities must cite at least one code or test evidence file");
      expect(result.stderr).toContain("document_type_classification");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("locks the code-or-test evidence exemption set to design_source_alignment only", () => {
    const script = readFileSync(path.join(repoRoot, "scripts", "checks", "implementation-status.mjs"), "utf8");
    const match = script.match(/codeOrTestEvidenceExemptions\s*=\s*new Set\(\s*\[([\s\S]*?)\]\s*\)/);

    expect(match, "codeOrTestEvidenceExemptions set must exist").not.toBeNull();

    const ids = match[1]
      .split(",")
      .map((entry) => entry.trim().replace(/^["']|["']$/g, ""))
      .filter(Boolean);

    // design_source_alignment is the only capability that is genuinely
    // documentation/script alignment work with no business code, so it is the
    // only legitimate exemption from the code-or-test evidence rule. Adding
    // any other id here silently bypasses the rule — update this assertion
    // deliberately, never by accident.
    expect(ids).toEqual(["design_source_alignment"]);
  });
});

function statusCapability(id: string, status: string, evidence: string[]) {
  return {
    id,
    label: id,
    status,
    scope: `${id} scope`,
    evidence,
    prohibitedClaims: status === "implemented" ? [] : [`${id} is fully implemented`],
  };
}
