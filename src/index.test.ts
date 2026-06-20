import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  buildCliPlan,
  isRuntimeMarkerCurrent,
  kbprepVenvPythonPath,
  parseStandaloneArgs,
  resolvePythonPath,
  runStandaloneCli,
} from "./index.js";

describe("kbprep package entry", () => {
  it("exports the agent-independent standalone CLI contract", async () => {
    const result = await runStandaloneCli("prepare", ["--help"]);

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain("Usage: kbprep-prepare");

    const parsed = parseStandaloneArgs(["--input", "README.md", "--output", ".kbprep/index-test"]);
    const plan = buildCliPlan("prepare", parsed.options);
    expect(plan.command).toBe("prepare");
    expect(plan.input.input_path).toContain("README.md");
  });

  it("does not expose host plugin metadata from the root entry", async () => {
    const entry = await import("./index.js");
    const rootSource = readFileSync("src/index.ts", "utf-8");
    const pkg = JSON.parse(readFileSync("package.json", "utf-8")) as Record<string, unknown>;

    expect(entry.default).toBeUndefined();
    expect(rootSource).not.toContain("adapters/vendor_host");
    expect(rootSource).not.toContain("plugin-sdk");
    expect(pkg).not.toHaveProperty("agentHost");
  });

  it("targets a KBPrep-local Python environment instead of a workspace or system dependency environment", () => {
    const runtimePath = kbprepVenvPythonPath();

    expect(runtimePath).toContain(join(".kbprep", "venv"));
    expect(runtimePath).toContain(process.platform === "win32" ? join("Scripts", "python.exe") : join("bin", "python"));
    expect(resolvePythonPath(join(tmpdir(), "kbprep-output"))).not.toContain(join(".agent-host", "workspace-wiki"));
  });

  it("rejects stale KBPrep-local Python runtime markers instead of reusing wrong environments", () => {
    const packageVersion = JSON.parse(readFileSync("package.json", "utf-8")).version;
    const validMarker = {
      schema: "kbprep.local_venv.v1",
      kbprep_version: packageVersion,
      python_executable: kbprepVenvPythonPath(),
      requested_device_override: null,
      actual_device: "cpu",
      python_project: {
        dependency_spec: "mineru[all]>=3.2.1,<4;PyMuPDF>=1.27,<2;beautifulsoup4==4.14.3;lxml==6.0.2",
      },
      setup_env: { ok: true, data: { device: "cpu" } },
    };

    expect(isRuntimeMarkerCurrent(validMarker)).toBe(true);
    expect(isRuntimeMarkerCurrent({ ...validMarker, schema: "kbprep.local_venv.v2" })).toBe(false);
    expect(isRuntimeMarkerCurrent({ ...validMarker, kbprep_version: "0.4.0" })).toBe(false);
    expect(isRuntimeMarkerCurrent({ ...validMarker, setup_env: { ok: false } })).toBe(false);
    expect(isRuntimeMarkerCurrent({
      ...validMarker,
      setup_env: { ok: true, data: { actions_taken: ["cuda_install_failed: timed out"] } },
    })).toBe(false);
    expect(isRuntimeMarkerCurrent(validMarker, { device_override: "cpu" })).toBe(false);
  });
});
