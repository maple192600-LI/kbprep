import { readFile } from "node:fs/promises";
import {
  buildBackend,
  resolveBackendName,
  type AIReviewBackend,
} from "./adapters/ai_review/index.js";
import {
  AI_REVIEW_MAX_ATTEMPTS as PIPELINE_AI_REVIEW_MAX_ATTEMPTS,
  AI_REVIEW_SYSTEM_PROMPT as PIPELINE_AI_REVIEW_SYSTEM_PROMPT,
  buildReviewBatches as pipelineBuildReviewBatches,
  buildReviewPrompt as pipelineBuildReviewPrompt,
  extractJsonPatch as pipelineExtractJsonPatch,
  formatRejectedPatchWarning as pipelineFormatRejectedPatchWarning,
  validateAiReviewPatch as pipelineValidateAiReviewPatch,
} from "./adapters/ai_review/review_pipeline.js";
import { callWorker, type WorkerResult } from "./worker.js";

type PluginConfig = {
  ai_review_backend?: "external" | "local_rules";
  ai_review_provider?: string;
  ai_review_model?: string;
  ai_review_command?: string;
  device_override?: "cuda" | "cpu";
  max_cpu_threads?: number;
  min_free_memory_gb?: number;
};

type AiReviewParams = {
  mode?: "rules_only" | "rules_plus_review_pack" | "ai_review";
  ai_review_backend?: "external" | "local_rules";
  ai_review_provider?: string;
  ai_review_model?: string;
  ai_review_command?: string;
};

type AiReviewContext = {
  api: {
    runtime?: {
      aiReviewBackend?: AIReviewBackend;
    };
  };
  toolCallId: string;
  signal?: AbortSignal;
};

// Timeout for applying a validated AI review patch to the run workspace.
// Separate from opts.timeoutMs (the LLM review call) because this is a fast,
// bounded filesystem operation that deserves its own explicit budget.
const AI_REVIEW_APPLY_PATCH_TIMEOUT_MS = 120_000;

const AI_REVIEWABLE_QUALITY_ERROR_CODES = new Set([
  "E_QA_FAILED",
  "E_PROTECTED_BLOCK_LOSS",
  "E_OPERATION_STEP_LOSS",
  "E_CODE_BLOCK_LOSS",
  "E_TABLE_BLOCK_LOSS",
  "E_CTA_RESIDUE",
  "E_QR_RESIDUE",
  "E_DISCARD_RATIO_EXCEEDED",
  "E_BROKEN_CODE_BLOCK",
  "E_TEXT_COVERAGE_LOW",
  "E_IMAGE_FILE_MISSING",
  "E_SVG_INVALID",
  "E_DETAIL_BLOCK_DISCARDED",
  "E_OUTPUT_RETENTION_MISSING",
]);

export async function maybeRunAiReview<T extends Record<string, unknown>>(
  result: WorkerResult<T>,
  params: AiReviewParams,
  config: PluginConfig,
  context: AiReviewContext,
  opts: {
    pythonPath: string;
    timeoutMs: number;
    workerConfig: Record<string, unknown>;
  },
): Promise<WorkerResult<T>> {
  if (params.mode !== "ai_review") {
    return result;
  }
  if (!result.ok && !isAiReviewableQualityFailure(result)) {
    return result;
  }

  const backend = resolveAiReviewBackend(context, params, config);
  const sourceData = (result.ok ? result.data : result.error?.details) as Record<string, unknown> | undefined;
  const sourceOutputs = (sourceData?.outputs as Record<string, unknown> | undefined) ?? {};
  const runDir = String(sourceData?.run_dir ?? "");
  const reviewPackPath = String(sourceOutputs.review_pack ?? "");

  if (!backend || !runDir || !reviewPackPath) {
    return withAiWarning(result, "W_LLM_REVIEW_SKIPPED: AI review unavailable or review_pack missing.");
  }

  let reviewPack = "";
  try {
    reviewPack = await readFile(reviewPackPath, "utf-8");
  } catch (err) {
    return withAiWarning(result, `W_LLM_REVIEW_SKIPPED: could not read review_pack.json (${String(err)}).`);
  }

  const batches = pipelineBuildReviewBatches(reviewPack);
  if (!batches.length) {
    return withAiWarning(result, "W_LLM_REVIEW_SKIPPED: review_pack.json could not be split into review batches.");
  }

  const combinedPatch: unknown[] = [];
  const aiWarnings: string[] = [];
  let failedBatches = 0;
  for (const [index, batch] of batches.entries()) {
    let accepted = false;
    for (let attempt = 1; attempt <= PIPELINE_AI_REVIEW_MAX_ATTEMPTS; attempt += 1) {
      const sessionKey = `kbprep-review:${context.toolCallId}:${Date.now()}:${index + 1}:${attempt}`;
      const message = pipelineBuildReviewPrompt(batch, index + 1, batches.length, attempt);

      const reviewed = await backend.review({
        sessionKey,
        message,
        provider: params.ai_review_provider ?? config.ai_review_provider,
        model: params.ai_review_model ?? config.ai_review_model,
        systemPrompt: PIPELINE_AI_REVIEW_SYSTEM_PROMPT,
        timeoutMs: opts.timeoutMs,
        idempotencyKey: `${context.toolCallId}:${index + 1}:${attempt}`,
      });
      if (reviewed.warning) aiWarnings.push(reviewed.warning);
      const patch = pipelineExtractJsonPatch(reviewed.messages);
      if (!patch) {
        aiWarnings.push(`W_LLM_REVIEW_BATCH_ATTEMPT_FAILED: batch ${index + 1}/${batches.length} attempt ${attempt}/${PIPELINE_AI_REVIEW_MAX_ATTEMPTS} did not return a JSON Patch array.`);
        continue;
      }

      const validation = pipelineValidateAiReviewPatch(patch);
      if (validation.rejected.length) {
        aiWarnings.push(pipelineFormatRejectedPatchWarning(index + 1, batches.length, attempt, validation.rejected));
      }
      if (validation.valid.length) {
        combinedPatch.push(...validation.valid);
        accepted = true;
        break;
      }
      if (patch.length === 0) {
        accepted = true;
        break;
      }
    }
    if (!accepted) {
      failedBatches += 1;
      aiWarnings.push(`W_LLM_REVIEW_BATCH_SKIPPED: batch ${index + 1}/${batches.length} did not produce any safe patch operations.`);
    }
  }

  if (combinedPatch.length === 0 && failedBatches === batches.length) {
    return {
      ...result,
      warnings: [...(result.warnings ?? []), ...aiWarnings, "W_LLM_REVIEW_SKIPPED: all AI review batches failed."],
    };
  }

  const applied = await callWorker<T>("apply_review", {
    run_dir: runDir,
    patch_json: combinedPatch,
  }, {
    pythonPath: opts.pythonPath,
    timeoutMs: AI_REVIEW_APPLY_PATCH_TIMEOUT_MS,
    signal: context.signal,
    config: opts.workerConfig,
  });

  if (!applied.ok) {
    return withAiWarning(result, `W_LLM_REVIEW_SKIPPED: AI patch was rejected (${applied.error?.message ?? "unknown error"}).`);
  }

  const originalData = (sourceData ?? {}) as Record<string, unknown>;
  const appliedData = (applied.data ?? {}) as Record<string, unknown>;
  const originalOutputs = (originalData.outputs ?? {}) as Record<string, unknown>;
  const updatedOutputs = (appliedData.updated_outputs ?? {}) as Record<string, unknown>;

  return {
    ...applied,
    data: ({
      ...originalData,
      ...appliedData,
      run_id: originalData.run_id,
      run_dir: originalData.run_dir,
      outputs: {
        ...originalOutputs,
        ...updatedOutputs,
      },
      latest_outputs: appliedData.latest_outputs ?? originalData.latest_outputs,
      ai_review: {
        applied: appliedData.applied ?? 0,
        rejected: appliedData.rejected ?? 0,
        rejected_details: appliedData.rejected_details ?? [],
        published: appliedData.published ?? false,
        batches: batches.length,
        patch_ops: combinedPatch.length,
      },
    } as unknown) as T,
    warnings: [...(result.warnings ?? []), ...aiWarnings, ...(applied.warnings ?? [])],
  };
}

function isAiReviewableQualityFailure<T extends Record<string, unknown>>(result: WorkerResult<T>): boolean {
  const code = result.error?.code ?? "";
  if (AI_REVIEWABLE_QUALITY_ERROR_CODES.has(code)) return true;
  const details = result.error?.details as Record<string, unknown> | undefined;
  return details?.legacy_code === "E_QA_FAILED";
}

function resolveAiReviewBackend(context: AiReviewContext, params: AiReviewParams, config: PluginConfig): AIReviewBackend | undefined {
  const name = resolveBackendName(params.ai_review_backend ?? config.ai_review_backend);
  return buildBackend(name, {
    explicit: context.api.runtime?.aiReviewBackend,
    externalCommand: params.ai_review_command ?? config.ai_review_command,
  });
}

function withAiWarning<T extends Record<string, unknown>>(result: WorkerResult<T>, warning: string): WorkerResult<T> {
  return {
    ...result,
    warnings: [...(result.warnings ?? []), warning],
  };
}
