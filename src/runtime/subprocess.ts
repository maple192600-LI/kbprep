import { spawn, type ChildProcess, type SpawnOptionsWithoutStdio } from "node:child_process";

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
    super([
      `Timed out while trying to ${label} after ${timeoutMs}ms`,
      `(exit ${result.code ?? "unknown"}, signal ${result.signal ?? "unknown"})`,
      evidence ? evidence : "",
    ].filter(Boolean).join(". "));
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

function collectManagedProcess(
  child: ChildProcess,
  options: ManagedProcessOptions,
): Promise<ManagedProcessResult> {
  return new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";
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
      child.kill("SIGTERM");
      terminateTimer = setTimeout(() => {
        forcedKill = true;
        child.kill("SIGKILL");
        settle(() => reject(new ManagedProcessTimeoutError(options.label, options.timeoutMs, {
          code: null,
          signal: "SIGKILL",
          stderr,
          stdout,
        })));
      }, options.terminateGraceMs ?? DEFAULT_TERMINATE_GRACE_MS);
    }, options.timeoutMs);

    child.stdout?.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf-8");
      options.onStdoutData?.(chunk);
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
      options.onStderrData?.(chunk);
    });
    child.on("error", (err) => {
      settle(() => reject(err));
    });
    child.on("close", (code, signal) => {
      const result: ManagedProcessResult = {
        code,
        signal,
        stdout,
        stderr,
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

function tailText(text: string): string {
  return text.split(/\r?\n/).filter(Boolean).slice(-TAIL_LINES).join("\n");
}
