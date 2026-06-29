import { spawn, spawnSync, type ChildProcess, type SpawnOptionsWithoutStdio } from "node:child_process";

export type ManagedProcessResult = {
  code: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
  forcedKill: boolean;
};

export type ManagedProcessOptions = {
  command: string;
  args?: string[];
  label: string;
  timeoutMs: number;
  terminateGraceMs?: number;
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  shell?: boolean;
  stdin?: string;
  signal?: AbortSignal;
  onStdoutData?: (chunk: Buffer) => void;
  onStderrData?: (chunk: Buffer) => void;
};

const DEFAULT_TERMINATE_GRACE_MS = 5_000;
const TAIL_LINES = 20;

export class ManagedProcessTimeoutError extends Error {
  readonly timeoutMs: number;
  readonly code: number | null;
  readonly signal: NodeJS.Signals | null;
  readonly stderrTail: string;
  readonly stdoutTail: string;

  constructor(
    label: string,
    timeoutMs: number,
    result: Pick<ManagedProcessResult, "code" | "signal"> & Partial<Pick<ManagedProcessResult, "stderr" | "stdout">>,
  ) {
    const stderrTail = tailText(result.stderr ?? "");
    const stdoutTail = tailText(result.stdout ?? "");
    const evidence = stderrTail || stdoutTail;
    super(
      [
        `Timed out while trying to ${label} after ${timeoutMs}ms`,
        `(exit ${result.code ?? "unknown"}, signal ${result.signal ?? "unknown"})`,
        evidence ? evidence : "",
      ]
        .filter(Boolean)
        .join(". "),
    );
    this.name = "ManagedProcessTimeoutError";
    this.timeoutMs = timeoutMs;
    this.code = result.code;
    this.signal = result.signal;
    this.stderrTail = stderrTail;
    this.stdoutTail = stdoutTail;
  }
}

export async function runManagedProcess(options: ManagedProcessOptions): Promise<ManagedProcessResult> {
  const child = spawnManagedProcess(options);
  return await collectManagedProcess(child, options);
}

function spawnManagedProcess(options: ManagedProcessOptions): ChildProcess {
  const spawnOptions: SpawnOptionsWithoutStdio = {
    cwd: options.cwd,
    env: options.env,
    shell: options.shell,
    signal: options.signal,
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  };
  return spawn(options.command, options.args ?? [], spawnOptions);
}

function collectManagedProcess(child: ChildProcess, options: ManagedProcessOptions): Promise<ManagedProcessResult> {
  return new Promise((resolve, reject) => {
    // Accumulate raw Buffer chunks and decode once at the end. Decoding each
    // chunk independently (chunk.toString("utf-8")) corrupts any multi-byte
    // character split across a chunk boundary — common with CJK output where
    // each character is 3 bytes and chunk boundaries rarely align to them.
    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    const decodeStdout = () => Buffer.concat(stdoutChunks).toString("utf-8");
    const decodeStderr = () => Buffer.concat(stderrChunks).toString("utf-8");
    let timedOut = false;
    let forcedKill = false;
    let settled = false;
    let terminateTimer: NodeJS.Timeout | undefined;

    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeoutTimer);
      if (terminateTimer) clearTimeout(terminateTimer);
      fn();
    };

    const timeoutTimer = setTimeout(() => {
      timedOut = true;
      terminateProcessTree(child, false);
      terminateTimer = setTimeout(() => {
        forcedKill = true;
        terminateProcessTree(child, true);
        settle(() =>
          reject(
            new ManagedProcessTimeoutError(options.label, options.timeoutMs, {
              code: null,
              signal: "SIGKILL",
              stderr: decodeStderr(),
              stdout: decodeStdout(),
            }),
          ),
        );
      }, options.terminateGraceMs ?? DEFAULT_TERMINATE_GRACE_MS);
    }, options.timeoutMs);

    child.stdout?.on("data", (chunk: Buffer) => {
      stdoutChunks.push(chunk);
      options.onStdoutData?.(chunk);
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      stderrChunks.push(chunk);
      options.onStderrData?.(chunk);
    });
    child.on("error", (err) => {
      settle(() => reject(err));
    });
    child.on("close", (code, signal) => {
      const result: ManagedProcessResult = {
        code,
        signal,
        stdout: decodeStdout(),
        stderr: decodeStderr(),
        timedOut,
        forcedKill,
      };
      settle(() => {
        if (timedOut) {
          reject(new ManagedProcessTimeoutError(options.label, options.timeoutMs, result));
          return;
        }
        resolve(result);
      });
    });

    child.stdin?.on("error", () => {});
    child.stdin?.end(options.stdin ?? "");
  });
}

// taskkill.exe normally returns near-instantly. Bound it so a hung cleanup
// call cannot block the Node event loop inside the timeout path.
const TASKKILL_TIMEOUT_MS = 5000;

function terminateProcessTree(child: ChildProcess, force: boolean): void {
  if (process.platform !== "win32" || !child.pid) {
    child.kill(force ? "SIGKILL" : "SIGTERM");
    return;
  }
  const pid = String(child.pid);
  const killWith = (forceKill: boolean) => {
    // `/t` kills the whole process tree (Node's child.kill cannot reach
    // shell-launched grandchildren on Windows).
    const args = ["/pid", pid, "/t"];
    if (forceKill) {
      args.push("/f");
    }
    return spawnSync("taskkill.exe", args, {
      stdio: "ignore",
      windowsHide: true,
      timeout: TASKKILL_TIMEOUT_MS,
    });
  };
  // Graceful stage: try without `/f` first so windowed workers can clean up.
  // Console workers (the Python worker) have no window, so taskkill without
  // `/f` returns non-zero and we retry with `/f` to keep teardown deterministic.
  let result = killWith(force);
  if (!force && (Boolean(result.error) || (result.status !== null && result.status !== 0))) {
    result = killWith(true);
  }
  // spawnSync only sets `error` when taskkill.exe could not be launched; a
  // non-zero exit status also means termination failed and we must fall back.
  const failed = Boolean(result.error) || (result.status !== null && result.status !== 0);
  if (failed) {
    // Last-resort fallback when taskkill itself is unavailable or the pid is
    // already gone. On Windows child.kill only reaches the direct child, not
    // shell-launched grandchildren; the common path above (taskkill /t /f)
    // handles grandchildren, and a full fallback would need a Job Object or
    // descendant-pid enumeration, which is out of scope for the timeout path.
    child.kill(force ? "SIGKILL" : "SIGTERM");
  }
}

function tailText(text: string): string {
  return text.split(/\r?\n/).filter(Boolean).slice(-TAIL_LINES).join("\n");
}
