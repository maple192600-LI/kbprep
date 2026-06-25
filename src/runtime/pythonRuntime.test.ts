import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  ensurePythonRuntime,
  isRuntimeMarkerCurrent,
  kbprepVenvPythonPath,
  resolvePythonPath,
  runtimeSetupStepsForTest,
  runSetupCommandForTest,
} from "./pythonRuntime.js";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

describe("python runtime setup ergonomics", () => {
  it("exposes bounded setup steps for progress reporting", () => {
    const steps = runtimeSetupStepsForTest();

    expect(steps.map((step) => step.id)).toEqual(["create_venv", "upgrade_packaging", "install_worker", "probe_environment"]);
    expect(steps.every((step) => step.timeoutMs > 0)).toBe(true);
    expect(steps.reduce((total, step) => total + step.timeoutMs, 0)).toBeLessThanOrEqual(105 * 60_000);
  });

  it("clamps runtime setup timeout environment overrides", () => {
    const originalCreate = process.env.KBPREP_CREATE_VENV_TIMEOUT_MS;
    const originalUpgrade = process.env.KBPREP_UPGRADE_PACKAGING_TIMEOUT_MS;
    const originalInstall = process.env.KBPREP_INSTALL_WORKER_TIMEOUT_MS;
    try {
      process.env.KBPREP_CREATE_VENV_TIMEOUT_MS = "1";
      process.env.KBPREP_UPGRADE_PACKAGING_TIMEOUT_MS = String(120 * 60_000);
      process.env.KBPREP_INSTALL_WORKER_TIMEOUT_MS = "not-a-number";

      const steps = runtimeSetupStepsForTest();
      const byId = Object.fromEntries(steps.map((step) => [step.id, step.timeoutMs]));

      expect(byId.create_venv).toBe(30_000);
      expect(byId.upgrade_packaging).toBe(90 * 60_000);
      expect(byId.install_worker).toBe(60 * 60_000);
    } finally {
      restoreEnv("KBPREP_CREATE_VENV_TIMEOUT_MS", originalCreate);
      restoreEnv("KBPREP_UPGRADE_PACKAGING_TIMEOUT_MS", originalUpgrade);
      restoreEnv("KBPREP_INSTALL_WORKER_TIMEOUT_MS", originalInstall);
    }
  });

  it("recognizes current runtime markers and rejects stale or failed markers", () => {
    const pkg = JSON.parse(readFileSync(path.join(repoRoot, "package.json"), "utf8")) as {
      version: string;
    };
    const marker = {
      schema: "kbprep.local_venv.v1",
      kbprep_version: pkg.version,
      python_executable: kbprepVenvPythonPath(),
      requested_device_override: "cpu",
      python_project: {
        dependency_spec:
          "mineru[all]>=3.2.1,<4;PyMuPDF>=1.27,<2;pymupdf4llm>=0.0.27,<1;beautifulsoup4==4.14.3;lxml==6.0.2;yt-dlp>=2025.1,<2027",
      },
      setup_env: {
        ok: true,
        data: { actions_taken: [] },
      },
    };

    expect(isRuntimeMarkerCurrent(marker, { device_override: "cpu" })).toBe(true);
    expect(isRuntimeMarkerCurrent({ ...marker, kbprep_version: "0.0.0" }, { device_override: "cpu" })).toBe(false);
    expect(isRuntimeMarkerCurrent(marker, { device_override: "cuda" })).toBe(false);
    expect(
      isRuntimeMarkerCurrent(
        {
          ...marker,
          setup_env: { ok: true, data: { actions_taken: ["cuda_install_failed: no wheel"] } },
        },
        { device_override: "cpu" },
      ),
    ).toBe(false);
    expect(isRuntimeMarkerCurrent(null, { device_override: "cpu" })).toBe(false);
  });

  it("supports legacy runtime marker fields during migration checks", () => {
    const pkg = JSON.parse(readFileSync(path.join(repoRoot, "package.json"), "utf8")) as {
      version: string;
    };
    const legacyMarker = {
      schema: "kbprep.local_venv.v1",
      plugin_version: pkg.version,
      python_executable: kbprepVenvPythonPath(),
      device_override: "cuda",
      python_project: {
        dependency_spec:
          "mineru[all]>=3.2.1,<4;PyMuPDF>=1.27,<2;pymupdf4llm>=0.0.27,<1;beautifulsoup4==4.14.3;lxml==6.0.2;yt-dlp>=2025.1,<2027",
      },
      setup_env: {
        ok: true,
        data: { device: "cuda" },
      },
    };

    expect(isRuntimeMarkerCurrent(legacyMarker, { device_override: "cuda" })).toBe(true);
    expect(isRuntimeMarkerCurrent({ ...legacyMarker, device_override: "invalid" }, { device_override: "cuda" })).toBe(false);
    expect(
      isRuntimeMarkerCurrent(
        {
          ...legacyMarker,
          python_project: { dependency_spec: "old-dependencies" },
        },
        { device_override: "cuda" },
      ),
    ).toBe(false);
  });

  it("uses configured Python fallbacks when skipped setup cannot reuse the ready marker", async () => {
    const originalSkip = process.env.KBPREP_SKIP_AUTO_SETUP;
    const originalKbprepPython = process.env.KBPREP_PYTHON;
    try {
      process.env.KBPREP_SKIP_AUTO_SETUP = "1";
      process.env.KBPREP_PYTHON = "env-python";

      expect(
        resolvePythonPath(undefined, {
          device_override: "cuda",
          python_path: "configured-python",
        }),
      ).toBe("configured-python");
      expect(resolvePythonPath(undefined, { device_override: "cuda" })).toBe("env-python");
      await expect(
        ensurePythonRuntime({
          device_override: "cuda",
          python_path: "configured-python",
        }),
      ).resolves.toBe("configured-python");
    } finally {
      restoreEnv("KBPREP_SKIP_AUTO_SETUP", originalSkip);
      restoreEnv("KBPREP_PYTHON", originalKbprepPython);
    }
  });

  it("reports setup command timeout with stderr evidence", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-runtime-timeout-"));
    const scriptPath = path.join(root, "slow-runtime.mjs");
    writeFileSync(scriptPath, ["process.stderr.write('before runtime timeout\\n');", "setInterval(() => {}, 1000);"].join("\n"), "utf8");

    try {
      await expect(runSetupCommandForTest(process.execPath, [scriptPath], "test runtime timeout", 100)).rejects.toThrow(
        /Timed out while trying to test runtime timeout.*before runtime timeout/s,
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("returns stdout and stderr for successful setup commands", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-runtime-success-"));
    const scriptPath = path.join(root, "good-runtime.mjs");
    writeFileSync(
      scriptPath,
      [
        "let input = '';",
        "process.stdin.on('data', chunk => input += chunk);",
        "process.stdin.on('end', () => {",
        "  process.stderr.write('setup warning\\n');",
        "  process.stdout.write(JSON.stringify({ received: input }));",
        "});",
      ].join("\n"),
      "utf8",
    );

    try {
      const result = await runSetupCommandForTest(process.execPath, [scriptPath], "test runtime success", 5_000, "payload");

      expect(JSON.parse(result.stdout)).toEqual({ received: "payload" });
      expect(result.stderr).toContain("setup warning");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("reports setup command nonzero exits with stderr tail", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-runtime-nonzero-"));
    const scriptPath = path.join(root, "bad-runtime.mjs");
    writeFileSync(
      scriptPath,
      ["for (let i = 0; i < 25; i += 1) process.stderr.write('runtime fail line ' + i + '\\n');", "process.exit(7);"].join("\n"),
      "utf8",
    );

    try {
      await expect(runSetupCommandForTest(process.execPath, [scriptPath], "test runtime nonzero", 5_000)).rejects.toThrow(
        /Failed to test runtime nonzero.*runtime fail line 24/s,
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("routes Python self-check scripts through the managed KBPrep venv wrapper", async () => {
    const pkg = JSON.parse(readFileSync(path.join(repoRoot, "package.json"), "utf8")) as {
      scripts: Record<string, string>;
    };
    const scriptNames = [
      "python:check-size",
      "python:coverage",
      "python:ruff",
      "python:test",
      "python:test-contract",
      "python:typecheck",
      "acceptance:round2",
      "acceptance:formats",
    ];

    for (const scriptName of scriptNames) {
      const command = pkg.scripts[scriptName];
      expect(command, scriptName).toContain("node scripts/python-venv.mjs");
      expect(command, scriptName).not.toMatch(/(?:^|&&\s*)python(?:\s|$)/);
    }

    expect(existsSync(path.join(repoRoot, "scripts", "python-venv.mjs"))).toBe(true);
    const runtime = await import("../../scripts/python-venv.mjs");
    expect(runtime.kbprepVenvPythonPathForTest(repoRoot)).toBe(
      path.join(
        repoRoot,
        ".kbprep",
        "venv",
        process.platform === "win32" ? "Scripts" : "bin",
        process.platform === "win32" ? "python.exe" : "python",
      ),
    );

    const wrapper = readFileSync(path.join(repoRoot, "scripts", "python-venv.mjs"), "utf8");
    expect(wrapper).toContain('"--no-deps", "-e"');
    expect(wrapper).toContain('"PyMuPDF>=1.27,<2"');
    expect(wrapper).toContain('"pymupdf4llm>=0.0.27,<1"');
    expect(wrapper).toContain('"beautifulsoup4==4.14.3"');
    expect(wrapper).toContain('"lxml==6.0.2"');
    expect(wrapper).toContain('"yt-dlp>=2025.1,<2027"');
    expect(wrapper).toContain('"setuptools<82"');
    expect(wrapper).toContain('stdio: "pipe"');
    expect(wrapper).toContain("process.stderr.write(output)");
    expect(wrapper).toContain("dev-runtime.lock");
    expect(wrapper).toContain("acquireDevRuntimeLock");
    expect(wrapper).toContain("reclaimStaleDevRuntimeLock");
    expect(wrapper).toContain('"wx"');
    expect(wrapper).toContain("KBPREP_VENV_LOCK_TIMEOUT_MS");
    expect(wrapper).not.toContain('python) + "[dev]"');

    const nestedCheckScripts = ["scripts/checks/capability-matrix.mjs", "scripts/checks/cleaning-hardcodes.mjs"];
    for (const script of nestedCheckScripts) {
      const text = readFileSync(path.join(repoRoot, script), "utf8");
      expect(text, script).toContain("scripts/python-venv.mjs");
      expect(text, script).not.toMatch(/spawnSync\(\s*["']python["']/);
      expect(text, script).not.toContain('command: "py"');
      expect(text, script).not.toContain('"python3"');
    }
  });

  it("does not use system Python as a skipped-setup test fallback", () => {
    const originalSkip = process.env.KBPREP_SKIP_AUTO_SETUP;
    const originalKbprepPython = process.env.KBPREP_PYTHON;
    const originalPython = process.env.PYTHON;
    try {
      process.env.KBPREP_SKIP_AUTO_SETUP = "1";
      delete process.env.KBPREP_PYTHON;
      process.env.PYTHON = "system-python-sentinel";

      expect(resolvePythonPath(undefined, { device_override: "cpu" })).toBe(kbprepVenvPythonPath());
    } finally {
      restoreEnv("KBPREP_SKIP_AUTO_SETUP", originalSkip);
      restoreEnv("KBPREP_PYTHON", originalKbprepPython);
      restoreEnv("PYTHON", originalPython);
    }
  });

  it("recovers stale dev runtime locks before running Python commands", () => {
    const lockPath = path.join(repoRoot, ".kbprep", "dev-runtime.lock");
    const markerPath = path.join(repoRoot, ".kbprep", "dev-runtime-ready.json");
    const originalMarker = existsSync(markerPath) ? readFileSync(markerPath, "utf8") : null;
    try {
      mkdirSync(path.dirname(lockPath), { recursive: true });
      rmSync(markerPath, { force: true });
      writeFileSync(lockPath, JSON.stringify({ pid: process.pid, created_at: "2000-01-01T00:00:00.000Z" }), "utf8");

      const result = spawnSync(process.execPath, [path.join(repoRoot, "scripts", "python-venv.mjs"), "-c", "print('lock-check')"], {
        cwd: repoRoot,
        encoding: "utf8",
        env: { ...process.env, KBPREP_VENV_LOCK_STALE_MS: "1", KBPREP_VENV_LOCK_TIMEOUT_MS: "2000" },
        timeout: 120_000,
      });

      expect(result.status, result.stderr || result.stdout).toBe(0);
      expect(result.stdout).toContain("lock-check");
      expect(existsSync(lockPath)).toBe(false);
    } finally {
      rmSync(lockPath, { force: true });
      if (originalMarker !== null && !existsSync(markerPath)) {
        writeFileSync(markerPath, originalMarker, "utf8");
      }
    }
  });
});

function restoreEnv(name: string, value: string | undefined): void {
  if (value === undefined) {
    delete process.env[name];
    return;
  }
  process.env[name] = value;
}
