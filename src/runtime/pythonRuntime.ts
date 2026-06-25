import { closeSync, existsSync, mkdirSync, openSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { ManagedProcessTimeoutError, runManagedProcess } from "./subprocess.js";

const RUNTIME_MARKER_SCHEMA = "kbprep.local_venv.v1";
const PYTHON_WORKER_DEPENDENCY_SPEC =
  "mineru[all]>=3.2.1,<4;PyMuPDF>=1.27,<2;pymupdf4llm>=0.0.27,<1;beautifulsoup4==4.14.3;lxml==6.0.2;yt-dlp>=2025.1,<2027";

export type RuntimeConfig = {
  device_override?: "cuda" | "cpu";
  max_cpu_threads?: number;
  min_free_memory_gb?: number;
  mineru_timeout_seconds?: number;
  python_path?: string;
};

export type RuntimeSetupStepId = "create_venv" | "upgrade_packaging" | "install_worker" | "probe_environment";

export type RuntimeSetupStep = {
  id: RuntimeSetupStepId;
  label: string;
  timeoutMs: number;
};

export type RuntimeSetupProgressEvent = {
  type: "step_start" | "step_success";
  step: RuntimeSetupStep;
};

export type RuntimeSetupProgress = (event: RuntimeSetupProgressEvent) => void;

const DEFAULT_RUNTIME_SETUP_STEPS: Array<Omit<RuntimeSetupStep, "timeoutMs"> & { defaultTimeoutMs: number; env: string }> = [
  {
    id: "create_venv",
    label: "create KBPrep local Python virtual environment",
    defaultTimeoutMs: 5 * 60_000,
    env: "KBPREP_CREATE_VENV_TIMEOUT_MS",
  },
  {
    id: "upgrade_packaging",
    label: "upgrade pip in KBPrep local Python virtual environment",
    defaultTimeoutMs: 10 * 60_000,
    env: "KBPREP_UPGRADE_PACKAGING_TIMEOUT_MS",
  },
  {
    id: "install_worker",
    label: "install kbprep worker dependencies into KBPrep local Python virtual environment",
    defaultTimeoutMs: 60 * 60_000,
    env: "KBPREP_INSTALL_WORKER_TIMEOUT_MS",
  },
  {
    id: "probe_environment",
    label: "detect hardware and tune KBPrep local Python dependencies",
    defaultTimeoutMs: 30 * 60_000,
    env: "KBPREP_PROBE_ENVIRONMENT_TIMEOUT_MS",
  },
];
const MIN_RUNTIME_SETUP_TIMEOUT_MS = 30_000;
const MAX_RUNTIME_SETUP_TIMEOUT_MS = 90 * 60_000;
const DEV_RUNTIME_LOCK_STALE_MS = runtimeSetupTimeoutMs("KBPREP_VENV_LOCK_STALE_MS", 2 * 60 * 60_000);
const DEV_RUNTIME_LOCK_TIMEOUT_MS = runtimeSetupTimeoutMs("KBPREP_VENV_LOCK_TIMEOUT_MS", 120_000);

export function resolvePythonPath(_startPath?: string, config?: RuntimeConfig): string {
  const runtimePython = kbprepVenvPythonPath();
  if (isKbprepVenvReady(config)) return runtimePython;

  if (shouldSkipAutoSetupForTests()) {
    if (config?.python_path?.trim()) return config.python_path.trim();
    if (process.env.KBPREP_PYTHON?.trim()) return process.env.KBPREP_PYTHON.trim();
    if (existsSync(runtimePython)) return runtimePython;

    throw new Error(
      "KBPrep project Python runtime is not available. Create .kbprep/venv through the project runtime wrapper before running skipped-setup tests.",
    );
  }

  return runtimePython;
}

export async function ensurePythonRuntime(config?: RuntimeConfig, onProgress?: RuntimeSetupProgress): Promise<string> {
  const pythonPath = kbprepVenvPythonPath();
  if (isKbprepVenvReady(config)) return pythonPath;

  if (shouldSkipAutoSetupForTests()) return resolvePythonPath(kbprepRootDir(), config);

  const releaseLock = acquireDevRuntimeLock();
  try {
    if (isKbprepVenvReady(config)) return pythonPath;
    const venvDir = kbprepVenvDir();
    cleanupStaleKbprepRuntime(config);
    rmSync(kbprepDevVenvReadyMarker(), { force: true });
    mkdirSync(dirname(venvDir), { recursive: true });
    const bootstrap = bootstrapPythonCommand(config);
    const steps = runtimeSetupSteps();
    await runRuntimeSetupStep(steps[0], onProgress, bootstrap.command, [...bootstrap.args, "-m", "venv", venvDir]);
    await runRuntimeSetupStep(steps[1], onProgress, pythonPath, ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]);
    await runRuntimeSetupStep(steps[2], onProgress, pythonPath, ["-m", "pip", "install", "-e", kbprepPythonProjectDir()]);
    const setupResult = await runRuntimeSetupStep(
      steps[3],
      onProgress,
      pythonPath,
      ["-m", "kbprep_worker.cli", "setup-env", "--json-stdin"],
      JSON.stringify({ device_override: config?.device_override }),
    );
    const setupEnvelope = parseSetupEnvelope(setupResult.stdout);
    writeFileSync(
      kbprepVenvReadyMarker(),
      JSON.stringify(
        {
          schema: RUNTIME_MARKER_SCHEMA,
          created_at: new Date().toISOString(),
          kbprep_version: kbprepPackageVersion(),
          python_executable: pythonPath,
          requested_device_override: config?.device_override ?? null,
          actual_device: actualDeviceFromSetupEnvelope(setupEnvelope),
          python_project: {
            path: kbprepPythonProjectDir(),
            dependency_spec: PYTHON_WORKER_DEPENDENCY_SPEC,
          },
          setup_env: setupEnvelope,
        },
        null,
        2,
      ),
      "utf-8",
    );
    return pythonPath;
  } finally {
    releaseLock();
  }
}

function runtimeSetupSteps(): RuntimeSetupStep[] {
  return DEFAULT_RUNTIME_SETUP_STEPS.map((step) => ({
    id: step.id,
    label: step.label,
    timeoutMs: runtimeSetupTimeoutMs(step.env, step.defaultTimeoutMs),
  }));
}

export function runtimeSetupStepsForTest(): RuntimeSetupStep[] {
  return runtimeSetupSteps();
}

async function runRuntimeSetupStep(
  step: RuntimeSetupStep,
  onProgress: RuntimeSetupProgress | undefined,
  command: string,
  args: string[],
  stdin = "",
): Promise<{ stdout: string; stderr: string }> {
  onProgress?.({ type: "step_start", step });
  const result = await runSetupCommand(command, args, step.label, step.timeoutMs, stdin);
  onProgress?.({ type: "step_success", step });
  return result;
}

function runtimeSetupTimeoutMs(envName: string, fallback: number): number {
  const raw = process.env[envName];
  if (!raw) return fallback;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback;
  return Math.min(Math.max(parsed, MIN_RUNTIME_SETUP_TIMEOUT_MS), MAX_RUNTIME_SETUP_TIMEOUT_MS);
}

/*
 * Kept small and exported for characterization tests; production callers should
 * go through ensurePythonRuntime so setup progress is emitted consistently.
 */
export async function runSetupCommandForTest(
  command: string,
  args: string[],
  label: string,
  timeoutMs: number,
  stdin = "",
): Promise<{ stdout: string; stderr: string }> {
  return runSetupCommand(command, args, label, timeoutMs, stdin);
}

function kbprepRootDir(): string {
  const moduleDir = dirname(fileURLToPath(import.meta.url));
  const leaf = basename(moduleDir);
  if (leaf === "dist" || leaf === "src") {
    return resolve(moduleDir, "..");
  }
  if (leaf === "runtime") {
    return resolve(moduleDir, "..", "..");
  }
  return moduleDir;
}

function kbprepPythonProjectDir(): string {
  return join(kbprepRootDir(), "python");
}

function kbprepVenvDir(): string {
  return join(kbprepRootDir(), ".kbprep", "venv");
}

function kbprepVenvReadyMarker(): string {
  return join(kbprepRootDir(), ".kbprep", "runtime-ready.json");
}

function kbprepDevVenvReadyMarker(): string {
  return join(kbprepRootDir(), ".kbprep", "dev-runtime-ready.json");
}

function kbprepDevRuntimeLockPath(): string {
  return join(kbprepRootDir(), ".kbprep", "dev-runtime.lock");
}

function acquireDevRuntimeLock(): () => void {
  const lockPath = kbprepDevRuntimeLockPath();
  const started = Date.now();
  while (Date.now() - started <= DEV_RUNTIME_LOCK_TIMEOUT_MS) {
    try {
      const fd = openSync(lockPath, "wx");
      writeFileSync(fd, JSON.stringify({ pid: process.pid, created_at: new Date().toISOString() }, null, 2), "utf-8");
      return () => {
        closeSync(fd);
        rmSync(lockPath, { force: true });
      };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      reclaimStaleDevRuntimeLock(lockPath);
      sleepSync(250);
    }
  }
  throw new Error(`Timed out waiting for KBPrep venv setup lock: ${lockPath}`);
}

function reclaimStaleDevRuntimeLock(lockPath: string): void {
  const lock = readDevRuntimeLock(lockPath);
  const stale = isDevRuntimeLockStale(lockPath, lock);
  if (lock?.pid && isProcessAlive(lock.pid) && !stale) return;
  if (!stale) return;
  rmSync(lockPath, { force: true });
}

function readDevRuntimeLock(lockPath: string): { pid: number | null; createdAt: number | null } | null {
  try {
    const data = JSON.parse(readFileSync(lockPath, "utf-8")) as Record<string, unknown>;
    const pid = Number(data.pid);
    const createdAt = Date.parse(String(data.created_at || ""));
    return {
      pid: Number.isInteger(pid) && pid > 0 ? pid : null,
      createdAt: Number.isFinite(createdAt) ? createdAt : null,
    };
  } catch {
    return null;
  }
}

function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function isPathOlderThan(path: string, ageMs: number): boolean {
  try {
    return Date.now() - statSync(path).mtimeMs > ageMs;
  } catch {
    return false;
  }
}

function isDevRuntimeLockStale(lockPath: string, lock: { pid: number | null; createdAt: number | null } | null): boolean {
  if (lock?.createdAt !== null && lock?.createdAt !== undefined) {
    return Date.now() - lock.createdAt > DEV_RUNTIME_LOCK_STALE_MS;
  }
  return isPathOlderThan(lockPath, DEV_RUNTIME_LOCK_STALE_MS);
}

function sleepSync(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function isKbprepVenvReady(config?: RuntimeConfig): boolean {
  if (!existsSync(kbprepVenvPythonPath()) || !existsSync(kbprepVenvReadyMarker())) {
    return false;
  }
  return isRuntimeMarkerCurrent(readRuntimeMarker(), config);
}

export function kbprepVenvPythonPath(): string {
  const venvDir = kbprepVenvDir();
  return process.platform === "win32" ? join(venvDir, "Scripts", "python.exe") : join(venvDir, "bin", "python");
}

function shouldSkipAutoSetupForTests(): boolean {
  return process.env.VITEST === "true" || process.env.KBPREP_SKIP_AUTO_SETUP === "1";
}

function cleanupStaleKbprepRuntime(config?: RuntimeConfig): void {
  if (!existsSync(kbprepVenvDir()) && !existsSync(kbprepVenvReadyMarker())) return;
  if (isKbprepVenvReady(config)) return;
  assertManagedRuntimePath(kbprepVenvDir());
  rmSync(kbprepVenvDir(), { recursive: true, force: true });
  rmSync(kbprepVenvReadyMarker(), { force: true });
}

function assertManagedRuntimePath(target: string): void {
  const expected = resolve(kbprepRootDir(), ".kbprep", "venv");
  const actual = resolve(target);
  if (actual !== expected) {
    throw new Error(`Refusing to remove unmanaged KBPrep runtime path: ${actual}`);
  }
}

function readRuntimeMarker(): unknown {
  try {
    return JSON.parse(readFileSync(kbprepVenvReadyMarker(), "utf-8"));
  } catch {
    return null;
  }
}

export function isRuntimeMarkerCurrent(marker: unknown, config?: RuntimeConfig): boolean {
  if (!marker || typeof marker !== "object") return false;
  const data = marker as Record<string, unknown>;
  const pythonProject = data.python_project as Record<string, unknown> | undefined;
  const setupEnv = data.setup_env as Record<string, unknown> | undefined;
  const setupData = setupEnv?.data as Record<string, unknown> | undefined;

  return (
    data.schema === RUNTIME_MARKER_SCHEMA &&
    markerVersion(data) === kbprepPackageVersion() &&
    data.python_executable === kbprepVenvPythonPath() &&
    requestedDeviceOverride(data) === (config?.device_override ?? null) &&
    pythonProject?.dependency_spec === PYTHON_WORKER_DEPENDENCY_SPEC &&
    setupEnv?.ok === true &&
    !hasCudaSetupFailure(setupData)
  );
}

function hasCudaSetupFailure(setupData?: Record<string, unknown>): boolean {
  const actions = setupData?.actions_taken;
  if (!Array.isArray(actions)) return false;
  return actions.some((action) => typeof action === "string" && action.startsWith("cuda_install_failed"));
}

function requestedDeviceOverride(marker: Record<string, unknown>): "cuda" | "cpu" | null {
  if ("requested_device_override" in marker) {
    return marker.requested_device_override === "cuda" || marker.requested_device_override === "cpu"
      ? marker.requested_device_override
      : null;
  }
  return marker.device_override === "cuda" || marker.device_override === "cpu" ? marker.device_override : null;
}

function markerVersion(data: Record<string, unknown>): unknown {
  return data.kbprep_version ?? data.plugin_version;
}

function kbprepPackageVersion(): string {
  try {
    const pkg = JSON.parse(readFileSync(join(kbprepRootDir(), "package.json"), "utf-8"));
    return String(pkg.version || "unknown");
  } catch {
    return "unknown";
  }
}

function bootstrapPythonCommand(config?: RuntimeConfig): { command: string; args: string[] } {
  if (config?.python_path?.trim()) return { command: config.python_path.trim(), args: [] };
  const envBootstrap = process.env.KBPREP_BOOTSTRAP_PYTHON?.trim();
  if (envBootstrap) return { command: envBootstrap, args: [] };
  if (process.platform === "win32") return { command: "py", args: ["-3"] };
  return { command: "python3", args: [] };
}

async function runSetupCommand(
  command: string,
  args: string[],
  label: string,
  timeoutMs: number,
  stdin = "",
): Promise<{ stdout: string; stderr: string }> {
  try {
    const result = await runManagedProcess({
      command,
      args,
      label,
      timeoutMs,
      cwd: kbprepRootDir(),
      stdin,
      env: {
        ...process.env,
        PIP_DISABLE_PIP_VERSION_CHECK: "1",
        PYTHONUTF8: "1",
        PYTHONIOENCODING: "utf-8",
      },
    });
    if (result.code === 0) return { stdout: result.stdout, stderr: result.stderr };

    const tail = (result.stderr || result.stdout).split(/\r?\n/).filter(Boolean).slice(-20).join("\n");
    throw new Error(`Failed to ${label} (exit ${result.code}, signal ${result.signal ?? "none"}). ${tail}`);
  } catch (err) {
    if (err instanceof ManagedProcessTimeoutError) {
      throw new Error(`Timed out while trying to ${label} after ${err.timeoutMs}ms. ${err.stderrTail || err.stdoutTail}`);
    }
    throw err;
  }
}

function parseSetupEnvelope(stdout: string): unknown {
  const trimmed = stdout.trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return { raw_stdout_preview: trimmed.slice(0, 500) };
  }
}

function actualDeviceFromSetupEnvelope(envelope: unknown): string | null {
  if (!envelope || typeof envelope !== "object") return null;
  const data = (envelope as Record<string, unknown>).data;
  if (!data || typeof data !== "object") return null;
  const device = (data as Record<string, unknown>).device;
  return typeof device === "string" ? device : null;
}
