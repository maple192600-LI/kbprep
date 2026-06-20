/**
 * Python worker spawner for kbprep.
 * Uses child_process.spawn to call Python CLI.
 * No HTTP service, no daemon, no persistent worker.
 */
import { randomUUID } from "node:crypto";
import { mkdir, appendFile } from "node:fs/promises";
import { delimiter, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import Type from "typebox";
import { Value } from "typebox/value";
import { makeError, type KBPrepError } from "./errors.js";
import { ManagedProcessTimeoutError, runManagedProcess } from "./runtime/subprocess.js";

export interface WorkerResult<T = Record<string, unknown>> {
  ok: boolean;
  data?: T;
  metrics?: Record<string, unknown>;
  warnings?: string[];
  error?: KBPrepError;
}

export interface WorkerCallOptions {
  pythonPath: string;
  cwd?: string;
  timeoutMs: number;
  signal?: AbortSignal;
  logDir?: string;
  config?: WorkerConfig;
}

export interface WorkerConfig {
  device_override?: "cuda" | "cpu";
  max_cpu_threads?: number;
  min_free_memory_gb?: number;
  mineru_timeout_seconds?: number;
}

const EnvelopeRecordSchema = Type.Record(Type.String(), Type.Unknown());
const GenericDataSchema = EnvelopeRecordSchema;
const PrepareDataSchema = Type.Object({
  run_id: Type.Optional(Type.String()),
  run_dir: Type.String(),
  outputs: Type.Optional(EnvelopeRecordSchema),
  latest_outputs: Type.Optional(EnvelopeRecordSchema),
  strict_errors: Type.Optional(Type.Array(Type.String())),
  warnings: Type.Optional(Type.Array(Type.String())),
}, { additionalProperties: true });
const DiagnoseDataSchema = Type.Object({
  input_file: Type.Optional(Type.String()),
  detected_format: Type.Optional(Type.String()),
  recommended_pipeline: Type.Optional(Type.String()),
}, { additionalProperties: true });
const ApplyReviewDataSchema = Type.Object({
  run_dir: Type.Optional(Type.String()),
  applied: Type.Optional(Type.Number()),
  rejected: Type.Optional(Type.Number()),
  latest_outputs: Type.Optional(EnvelopeRecordSchema),
}, { additionalProperties: true });
const FeedbackDataSchema = GenericDataSchema;
const CleanupDataSchema = GenericDataSchema;
const PrepareBatchDataSchema = GenericDataSchema;
const WorkerDataSchemas = {
  diagnose: DiagnoseDataSchema,
  prepare: PrepareDataSchema,
  apply_review: ApplyReviewDataSchema,
  feedback: FeedbackDataSchema,
  cleanup: CleanupDataSchema,
  prepare_batch: PrepareBatchDataSchema,
} as const;
const WorkerEnvelopeSchema = Type.Union([
  Type.Object({
    ok: Type.Literal(true),
    data: Type.Optional(EnvelopeRecordSchema),
    metrics: Type.Optional(EnvelopeRecordSchema),
    warnings: Type.Optional(Type.Array(Type.String())),
  }, { additionalProperties: false }),
  Type.Object({
    ok: Type.Literal(false),
    error: Type.Object({
      code: Type.String(),
      message: Type.String(),
      recoverable: Type.Boolean(),
      suggested_action: Type.String(),
      details: EnvelopeRecordSchema,
    }, { additionalProperties: false }),
    warnings: Type.Optional(Type.Array(Type.String())),
  }, { additionalProperties: false }),
]);

/**
 * Call Python worker via CLI mode.
 * stdout: single JSON envelope
 * stderr: JSONL logs
 */
export async function callWorker<T = Record<string, unknown>>(
  command: string,
  input: Record<string, unknown>,
  options: WorkerCallOptions,
): Promise<WorkerResult<T>> {
  const { pythonPath, cwd, timeoutMs, signal, logDir } = options;
  const jobId = randomUUID().replace(/-/g, "").slice(0, 16);

  const args = ["-m", "kbprep_worker.cli", command, "--json-stdin"];

  const env = { ...process.env } as Record<string, string>;
  const pluginDir = dirname(fileURLToPath(import.meta.url));
  const bundledPythonDir = join(pluginDir, "..", "python");
  env.PYTHONPATH = bundledPythonDir;
  env.PYTHONNOUSERSITE = "1";
  if (/[\\/]Scripts[\\/]python\.exe$/i.test(pythonPath) || /[\\/]bin[\\/]python(?:\d+(?:\.\d+)?)?$/i.test(pythonPath)) {
    const venvDir = pythonPath.replace(/[\\/](Scripts[\\/]python\.exe|bin[\\/]python(?:\d+(?:\.\d+)?)?)$/i, "");
    const venvBin = process.platform === "win32"
      ? join(venvDir, "Scripts")
      : join(venvDir, "bin");
    env.PATH = `${venvBin}${delimiter}${env.PATH || ""}`;
  }
  env.PYTHONUTF8 = "1";
  env.PYTHONIOENCODING = "utf-8";

  // Pass worker runtime config as environment variables.
  if (options.config?.device_override) {
    env.MINERU_DEVICE_MODE = options.config.device_override;
  }
  if (options.config?.max_cpu_threads) {
    env.TORCH_NUM_THREADS = String(options.config.max_cpu_threads);
    env.OMP_NUM_THREADS = String(options.config.max_cpu_threads);
  }
  if (options.config?.mineru_timeout_seconds) {
    env.KBPREP_MINERU_TIMEOUT_SECONDS = String(options.config.mineru_timeout_seconds);
  }

  const stderrLines: string[] = [];
  let logPath: string | undefined;
  if (logDir) {
    await mkdir(logDir, { recursive: true });
    logPath = join(logDir, `${jobId}.jsonl`);
  }
  const collectStderr = (chunk: Buffer) => {
    const text = chunk.toString("utf-8");
    for (const line of text.split("\n")) {
      const trimmed = line.trim();
      if (trimmed) stderrLines.push(trimmed);
    }
    if (logPath) {
      void appendFile(logPath, chunk).catch(() => {});
    }
  };

  try {
    const result = await runManagedProcess({
      command: pythonPath,
      args,
      label: `worker ${command}`,
      timeoutMs,
      cwd,
      signal,
      env,
      stdin: JSON.stringify(input),
      onStderrData: collectStderr,
    });
    const envelope = parseEnvelope<T>(result.stdout, stderrLines.slice(-120), command);

    if (!envelope.ok && !envelope.error) {
      return {
        ok: false,
        error: makeError("E_TIMEOUT", `Worker exited with code ${result.code}`, {
          details: { exitCode: result.code, signal: result.signal, stderr_tail: stderrLines.slice(-10) },
        }),
        warnings: envelope.warnings,
      };
    }

    return envelope;
  } catch (err: unknown) {
    if (isAbortError(err)) {
      return {
        ok: false,
        error: makeError("E_CANCELLED", "Worker call was cancelled.", {
          recoverable: true,
          suggested_action: "Retry if needed.",
        }),
      };
    }
    if (err instanceof ManagedProcessTimeoutError) {
      const timeoutStderrTail = (err.stderrTail || "").split(/\r?\n/).filter(Boolean);
      return {
        ok: false,
        error: makeError("E_TIMEOUT", `Worker timed out after ${timeoutMs}ms`, {
          recoverable: true,
          suggested_action: "Increase timeout or check worker health.",
          details: {
            timeout_ms: timeoutMs,
            exitCode: err.code,
            signal: err.signal,
            stderr_tail: timeoutStderrTail.length ? timeoutStderrTail.slice(-10) : stderrLines.slice(-10),
          },
        }),
      };
    }
    return {
      ok: false,
      error: makeError("E_INTERNAL", String(err), {
        details: { stderr_tail: stderrLines.slice(-10) },
      }),
    };
  }
}

export function parseEnvelope<T>(raw: string, stderrTail: string[], command?: string): WorkerResult<T> {
  const trimmed = raw.trim();
  if (!trimmed) {
    return {
      ok: false,
      error: makeError("E_WORKER_BAD_JSON", "Worker returned empty stdout.", {
        details: { stderr_tail: stderrTail },
      }),
    };
  }
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (!Value.Check(WorkerEnvelopeSchema, parsed)) {
      const validationErrors = [...Value.Errors(WorkerEnvelopeSchema, parsed)]
        .slice(0, 8)
        .map((error) => ({
          path: "path" in error ? error.path : undefined,
          message: error.message,
        }));
      return {
        ok: false,
        error: makeError("E_WORKER_BAD_JSON", "Worker returned a malformed JSON envelope.", {
          details: {
            validation_errors: validationErrors,
            stdout_preview: trimmed.slice(0, 500),
            stderr_tail: stderrTail,
          },
        }),
      };
    }
    const dataValidation = validateCommandData(parsed, command, trimmed, stderrTail);
    if (dataValidation) return dataValidation as WorkerResult<T>;
    return parsed as WorkerResult<T>;
  } catch (err) {
    return {
      ok: false,
      error: makeError("E_WORKER_BAD_JSON", `Failed to parse worker stdout: ${err}`, {
        details: { stdout_preview: trimmed.slice(0, 500), stderr_tail: stderrTail },
      }),
    };
  }
}

function validateCommandData(
  parsed: unknown,
  command: string | undefined,
  stdout: string,
  stderrTail: string[],
): WorkerResult<Record<string, unknown>> | null {
  if (!command || !parsed || typeof parsed !== "object") return null;
  const envelope = parsed as { ok?: unknown; data?: unknown };
  if (envelope.ok !== true) return null;
  const schema = WorkerDataSchemas[command as keyof typeof WorkerDataSchemas];
  if (!schema || Value.Check(schema, envelope.data)) return null;

  const validationErrors = [...Value.Errors(schema, envelope.data)]
    .slice(0, 8)
    .map((error) => ({
      path: "path" in error ? error.path : undefined,
      message: error.message,
    }));
  return {
    ok: false,
    error: makeError("E_WORKER_BAD_JSON", `Worker returned malformed data for ${command}.`, {
      details: {
        command,
        validation_errors: validationErrors,
        stdout_preview: stdout.slice(0, 500),
        stderr_tail: stderrTail,
      },
    }),
  };
}

interface TimeoutMarker extends Error {
  __kbprep_timeout: true;
}

function createTimeoutError(ms: number): TimeoutMarker {
  const err = new Error(`Worker timed out after ${ms}ms`) as TimeoutMarker;
  err.__kbprep_timeout = true;
  return err;
}

function isTimeoutError(err: unknown): err is TimeoutMarker {
  return err instanceof Error && "__kbprep_timeout" in err;
}

function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === "AbortError";
}
