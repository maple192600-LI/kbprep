import { dirname, join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type RuntimeFileState = {
  files: Map<string, string>;
  dirs: Set<string>;
  calls: Array<{
    command: string;
    args?: string[];
    stdin?: string;
    env?: NodeJS.ProcessEnv;
    label: string;
  }>;
  lockOpenPaths: string[];
  setupStdout: string;
};

const runtimeState = vi.hoisted<RuntimeFileState>(() => ({
  files: new Map(),
  dirs: new Set(),
  calls: [],
  lockOpenPaths: [],
  setupStdout: JSON.stringify({ ok: true, data: { device: "cpu", actions_taken: [] } }),
}));

vi.mock("node:fs", () => ({
  closeSync() {},
  existsSync(pathLike: string) {
    const path = String(pathLike);
    return runtimeState.files.has(path) || runtimeState.dirs.has(path);
  },
  mkdirSync(pathLike: string) {
    runtimeState.dirs.add(String(pathLike));
  },
  readFileSync(pathLike: string) {
    const path = String(pathLike);
    if (path.endsWith("package.json")) {
      return JSON.stringify({ version: "9.9.9-test" });
    }
    const value = runtimeState.files.get(path);
    if (value === undefined) {
      throw new Error(`missing mocked file: ${path}`);
    }
    return value;
  },
  rmSync(pathLike: string) {
    const path = String(pathLike);
    runtimeState.files.delete(path);
    runtimeState.dirs.delete(path);
    for (const key of [...runtimeState.files.keys()]) {
      if (key.startsWith(`${path}\\`) || key.startsWith(`${path}/`)) {
        runtimeState.files.delete(key);
      }
    }
  },
  statSync() {
    return { mtimeMs: 0 };
  },
  openSync(pathLike: string, flag: string) {
    const path = String(pathLike);
    if (flag === "wx" && runtimeState.files.has(path)) {
      const error = new Error("mock lock exists") as NodeJS.ErrnoException;
      error.code = "EEXIST";
      throw error;
    }
    runtimeState.lockOpenPaths.push(path);
    runtimeState.files.set(path, "");
    return path;
  },
  writeFileSync(pathLike: string, data: string) {
    runtimeState.files.set(String(pathLike), String(data));
  },
}));

vi.mock("./subprocess.js", () => ({
  ManagedProcessTimeoutError: class ManagedProcessTimeoutError extends Error {},
  async runManagedProcess(options: { command: string; args?: string[]; stdin?: string; env?: NodeJS.ProcessEnv; label: string }) {
    runtimeState.calls.push({
      command: options.command,
      args: options.args,
      stdin: options.stdin,
      env: options.env,
      label: options.label,
    });
    return {
      code: 0,
      signal: null,
      stdout: options.args?.includes("setup-env") ? runtimeState.setupStdout : "",
      stderr: "",
      timedOut: false,
      forcedKill: false,
    };
  },
}));

describe("python runtime full setup orchestration", () => {
  const originalVitest = process.env.VITEST;

  beforeEach(() => {
    runtimeState.files.clear();
    runtimeState.dirs.clear();
    runtimeState.calls = [];
    runtimeState.lockOpenPaths = [];
    runtimeState.setupStdout = JSON.stringify({ ok: true, data: { device: "cpu", actions_taken: [] } });
    delete process.env.VITEST;
    delete process.env.KBPREP_SKIP_AUTO_SETUP;
  });

  afterEach(() => {
    restoreEnv("VITEST", originalVitest);
  });

  it("runs every setup step and writes a current runtime marker", async () => {
    const { ensurePythonRuntime, kbprepVenvPythonPath } = await import("./pythonRuntime.js");
    const events: string[] = [];

    const pythonPath = await ensurePythonRuntime({ device_override: "cpu" }, (event) => {
      events.push(`${event.type}:${event.step.id}`);
    });

    expect(pythonPath).toBe(kbprepVenvPythonPath());
    expect(events).toEqual([
      "step_start:create_venv",
      "step_success:create_venv",
      "step_start:upgrade_packaging",
      "step_success:upgrade_packaging",
      "step_start:install_worker",
      "step_success:install_worker",
      "step_start:probe_environment",
      "step_success:probe_environment",
    ]);
    expect(runtimeState.calls.map((call) => call.label)).toEqual([
      "create KBPrep local Python virtual environment",
      "upgrade pip in KBPrep local Python virtual environment",
      "install kbprep worker dependencies into KBPrep local Python virtual environment",
      "detect hardware and tune KBPrep local Python dependencies",
    ]);
    expect(runtimeState.calls[0].args).toContain("venv");
    expect(runtimeState.calls[1].args).toEqual(["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]);
    expect(runtimeState.calls[2].args).toContain("-e");
    expect(runtimeState.calls[3].stdin).toBe(JSON.stringify({ device_override: "cpu" }));
    expect(runtimeState.calls.every((call) => call.env?.PYTHONUTF8 === "1")).toBe(true);

    const markerPath = [...runtimeState.files.keys()].find((path) => path.endsWith("runtime-ready.json"));
    expect(markerPath).toBeDefined();
    const marker = JSON.parse(runtimeState.files.get(markerPath ?? "") ?? "{}");
    expect(marker).toMatchObject({
      schema: "kbprep.local_venv.v1",
      kbprep_version: "9.9.9-test",
      requested_device_override: "cpu",
      actual_device: "cpu",
      setup_env: { ok: true, data: { device: "cpu", actions_taken: [] } },
    });
    expect(marker.python_project.dependency_spec).toContain("mineru[all]");
    expect(runtimeState.lockOpenPaths.some((file) => file.endsWith("dev-runtime.lock"))).toBe(true);
    expect([...runtimeState.files.keys()].some((file) => file.endsWith("dev-runtime.lock"))).toBe(false);
  });

  it("clears stale dev runtime marker when runtime setup rebuilds the shared venv", async () => {
    const { ensurePythonRuntime, kbprepVenvPythonPath } = await import("./pythonRuntime.js");
    const kbprepDir = dirname(dirname(dirname(kbprepVenvPythonPath())));
    const devMarkerPath = join(kbprepDir, "dev-runtime-ready.json");
    runtimeState.files.set(devMarkerPath, JSON.stringify({ schema: "kbprep.dev_venv.v1" }));

    await ensurePythonRuntime();

    expect([...runtimeState.files.keys()].some((file) => file.endsWith("dev-runtime-ready.json"))).toBe(false);
    expect([...runtimeState.files.keys()].some((file) => file.endsWith("runtime-ready.json"))).toBe(true);
  });

  it("reclaims orphaned shared setup locks before rebuilding the shared venv", async () => {
    const { ensurePythonRuntime, kbprepVenvPythonPath } = await import("./pythonRuntime.js");
    const kbprepDir = dirname(dirname(dirname(kbprepVenvPythonPath())));
    const lockPath = join(kbprepDir, "dev-runtime.lock");
    runtimeState.files.set(lockPath, JSON.stringify({ pid: 999999, created_at: "2000-01-01T00:00:00.000Z" }));

    await ensurePythonRuntime();

    expect(runtimeState.lockOpenPaths.filter((file) => file.endsWith("dev-runtime.lock")).length).toBe(1);
    expect([...runtimeState.files.keys()].some((file) => file.endsWith("dev-runtime.lock"))).toBe(false);
    expect([...runtimeState.files.keys()].some((file) => file.endsWith("runtime-ready.json"))).toBe(true);
  });

  it("records raw setup output when setup-env emits non-json stdout", async () => {
    runtimeState.setupStdout = "not json from setup-env";
    const { ensurePythonRuntime } = await import("./pythonRuntime.js");

    await ensurePythonRuntime();

    const markerPath = [...runtimeState.files.keys()].find((path) => path.endsWith("runtime-ready.json"));
    const marker = JSON.parse(runtimeState.files.get(markerPath ?? "") ?? "{}");
    expect(marker.actual_device).toBeNull();
    expect(marker.setup_env.raw_stdout_preview).toBe("not json from setup-env");
  });
});

function restoreEnv(name: string, value: string | undefined): void {
  if (value === undefined) {
    delete process.env[name];
    return;
  }
  process.env[name] = value;
}
