import { ManagedProcessTimeoutError, runManagedProcess } from "../../runtime/subprocess.js";

export type AIReviewBackendName = "external" | "local_rules";

export type AIReviewBackend = {
  review: (params: {
    sessionKey: string;
    message: string;
    systemPrompt: string;
    provider?: string;
    model?: string;
    timeoutMs?: number;
    idempotencyKey?: string;
  }) => Promise<{ messages: unknown[]; warning?: string }>;
};

export function resolveBackendName(value?: string): AIReviewBackendName {
  if (value === "local_rules" || value === "external") return value;
  return "external";
}

export function buildBackend(
  name: AIReviewBackendName,
  options: {
    explicit?: AIReviewBackend;
    externalCommand?: string;
  },
): AIReviewBackend | undefined {
  if (options.explicit) return options.explicit;
  if (name === "local_rules") return localRulesBackend();
  if (options.externalCommand?.trim()) return externalCommandBackend(options.externalCommand.trim());
  return missingExternalBackend(name);
}

function localRulesBackend(): AIReviewBackend {
  return {
    async review() {
      return { messages: ["[]"], warning: "W_LLM_REVIEW_LOCAL_RULES: no external AI backend configured; kept deterministic rules-only classifications." };
    },
  };
}

function missingExternalBackend(name: AIReviewBackendName): AIReviewBackend {
  return {
    async review() {
      return {
        messages: [],
        warning: `W_LLM_REVIEW_BACKEND_UNAVAILABLE: ${name} review backend is not built into standalone KBPrep. Inject a host-provided AIReviewBackend or use rules_plus_review_pack for human/agent review patches.`,
      };
    },
  };
}

function externalCommandBackend(command: string): AIReviewBackend {
  return {
    async review(params) {
      const result = await runExternalReviewCommand(command, {
        sessionKey: params.sessionKey,
        message: params.message,
        systemPrompt: params.systemPrompt,
        provider: params.provider,
        model: params.model,
        timeoutMs: params.timeoutMs,
        idempotencyKey: params.idempotencyKey,
      }, params.timeoutMs ?? 60_000);
      return result;
    },
  };
}

function runExternalReviewCommand(
  command: string,
  payload: Record<string, unknown>,
  timeoutMs: number,
): Promise<{ messages: unknown[]; warning?: string }> {
  return runManagedProcess({
    command,
    label: "AI review command",
    timeoutMs,
    shell: true,
    stdin: JSON.stringify(payload),
  }).then((result) => {
    if (result.code !== 0) {
      rejectExternalCommandExit(result.code, result.stderr);
    }
    try {
      const parsed = JSON.parse(result.stdout.trim()) as unknown;
      if (!parsed || typeof parsed !== "object" || !Array.isArray((parsed as { messages?: unknown }).messages)) {
        throw new Error("AI review command must return JSON with a messages array.");
      }
      return {
        messages: (parsed as { messages: unknown[] }).messages,
        warning: typeof (parsed as { warning?: unknown }).warning === "string"
          ? (parsed as { warning: string }).warning
          : undefined,
      };
    } catch (err) {
      throw new Error(`AI review command returned invalid JSON: ${String(err)}`);
    }
  }).catch((err) => {
    if (err instanceof ManagedProcessTimeoutError) {
      throw new Error(`AI review command timed out after ${err.timeoutMs}ms. ${err.stderrTail || err.stdoutTail}`);
    }
    throw err;
  });
}

function rejectExternalCommandExit(code: number | null, stderr: string): never {
  throw new Error(`AI review command exited ${code}: ${stderr.split(/\r?\n/).filter(Boolean).slice(-10).join("\n")}`);
}
