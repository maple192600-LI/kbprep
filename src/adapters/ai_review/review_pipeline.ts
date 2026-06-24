const REVIEW_PACK_MAX_CHARS = 80_000;
const REVIEW_PACK_BATCH_TARGET_CHARS = 60_000;

const AI_REVIEW_ALLOWED_FIELDS = new Set(["status", "risk_tags", "reason", "confidence"]);
const AI_REVIEW_ALLOWED_STATUSES = new Set(["keep", "discard", "evidence", "review"]);

export const AI_REVIEW_MAX_ATTEMPTS = 2;

export const AI_REVIEW_SYSTEM_PROMPT = [
  "You are a conservative knowledge-base cleaning reviewer.",
  "Your job is only to classify existing blocks as keep, discard, evidence, or review.",
  "You must not rewrite, compress, paraphrase, or summarize source text.",
  "Prefer keep or review when a block might contain usable knowledge or when removal could break context.",
  "Pure author bios, usernames, personal introductions, credentials, and advertising wrappers are not knowledge body.",
].join(" ");

export function buildReviewPrompt(reviewPack: string, batchNumber = 1, batchCount = 1, attempt = 1): string {
  const policyContext = summarizePolicyContext(reviewPack);
  return [
    `Review this kbprep review_pack.json batch ${batchNumber}/${batchCount}.`,
    "Return ONLY an RFC 6902 JSON Patch array.",
    "Allowed patch paths must be exactly /blocks/{block_id}/status, /blocks/{block_id}/risk_tags, /blocks/{block_id}/reason, or /blocks/{block_id}/confidence.",
    "Allowed ops: replace status/reason/confidence/risk_tags, or add a single risk_tags string.",
    "Allowed statuses are keep, discard, evidence, review.",
    "Never rewrite text. Never summarize. Never discard steps, prompts, code, tables, tool names, numbers, parameters, links, or concrete examples.",
    "For curated Obsidian knowledge-base use, discard pure author bios, usernames, personal introductions, credentials, and ad/backstory blocks that do not carry reusable knowledge.",
    "Keep original source text intact. If deleting a block would break pronoun/reference continuity or remove setup needed by a later method, set status to review instead of discard.",
    "If context is insufficient, set status to review.",
    ...policyContext,
    attempt > 1 ? "Previous response was invalid or unsafe. Return a valid patch array only, or [] if no safe change is needed." : "",
    "",
    reviewPack,
  ]
    .filter(Boolean)
    .join("\n");
}

export function buildReviewBatches(reviewPack: string): string[] {
  if (reviewPack.length <= REVIEW_PACK_MAX_CHARS) return [reviewPack];

  let parsed: unknown;
  try {
    parsed = JSON.parse(reviewPack);
  } catch {
    return [];
  }
  if (!parsed || typeof parsed !== "object") return [];

  const pack = parsed as Record<string, unknown>;
  const blocks = Array.isArray(pack.blocks) ? pack.blocks : [];
  if (!blocks.length) return [JSON.stringify({ ...pack, blocks: [] }, null, 2)];

  const batches: string[] = [];
  let current: unknown[] = [];
  for (const block of blocks) {
    const candidate = serializeReviewBatch(pack, [...current, block]);
    if (candidate.length > REVIEW_PACK_BATCH_TARGET_CHARS && current.length > 0) {
      batches.push(serializeReviewBatch(pack, current));
      current = [block];
    } else {
      current.push(block);
    }
  }
  if (current.length) batches.push(serializeReviewBatch(pack, current));

  return batches;
}

export function serializeReviewBatch(pack: Record<string, unknown>, blocks: unknown[]): string {
  const batched = {
    ...pack,
    batching: {
      original_block_count: Array.isArray(pack.blocks) ? pack.blocks.length : blocks.length,
      batch_block_count: blocks.length,
    },
    blocks,
  };
  return JSON.stringify(batched, null, 2);
}

export function extractJsonPatch(messages: unknown[]): unknown[] | null {
  for (const message of [...messages].reverse()) {
    const text = stringifyMessage(message);
    const parsed = parseFirstJsonArray(text);
    if (parsed && parsed.every((item) => typeof item === "object" && item !== null && "op" in item && "path" in item)) {
      return parsed;
    }
  }
  return null;
}

function summarizePolicyContext(reviewPack: string): string[] {
  const pack = parseReviewPackObject(reviewPack);
  const policy = pack ? objectField(pack, "policy_context") : undefined;
  if (!policy) return [];

  const documentType = stringField(policy, "document_type");
  const profile = stringField(policy, "profile");
  const relevantTerms = stringArrayField(policy, "relevant_terms");
  const protectedPatterns = protectedPatternLabels(policy);
  const ruleSources = stringArrayField(policy, "rule_sources");

  return [
    "Policy context:",
    documentType ? `document_type: ${documentType}` : "",
    profile ? `profile: ${profile}` : "",
    relevantTerms.length ? `relevant terms: ${relevantTerms.join(", ")}` : "",
    protectedPatterns.length ? `protected patterns: ${protectedPatterns.join(", ")}` : "",
    ruleSources.length ? `rule sources: ${ruleSources.join(", ")}` : "",
  ].filter(Boolean);
}

function parseReviewPackObject(reviewPack: string): Record<string, unknown> | undefined {
  try {
    const parsed = JSON.parse(reviewPack) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : undefined;
  } catch {
    return undefined;
  }
}

function objectField(record: Record<string, unknown>, key: string): Record<string, unknown> | undefined {
  const value = record[key];
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}

function stringArrayField(record: Record<string, unknown>, key: string): string[] {
  const value = record[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function protectedPatternLabels(policy: Record<string, unknown>): string[] {
  const value = policy.protected_patterns;
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (item && typeof item === "object" && !Array.isArray(item) ? stringField(item as Record<string, unknown>, "label") : ""))
    .filter(Boolean);
}

export function validateAiReviewPatch(patch: unknown[]): {
  valid: unknown[];
  rejected: string[];
  rejectedOperations: Array<{ operation: unknown; reason: string }>;
} {
  const valid: unknown[] = [];
  const rejected: string[] = [];
  const rejectedOperations: Array<{ operation: unknown; reason: string }> = [];

  for (const item of patch) {
    const reject = (reason: string) => {
      rejected.push(reason);
      rejectedOperations.push({ operation: item, reason });
    };
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      reject("operation is not an object");
      continue;
    }
    const op = item as Record<string, unknown>;
    const opType = op.op;
    const path = op.path;
    const value = op.value;
    if (opType !== "replace" && opType !== "add") {
      reject(`unsupported op ${String(opType)}`);
      continue;
    }
    if (typeof path !== "string") {
      reject("path must be a string");
      continue;
    }
    const parts = path.split("/").filter(Boolean);
    if (parts.length !== 3 || parts[0] !== "blocks") {
      reject(`invalid path ${path}`);
      continue;
    }
    const field = parts[2];
    if (!AI_REVIEW_ALLOWED_FIELDS.has(field)) {
      reject(`field ${field} is not allowed`);
      continue;
    }

    const valueError = validateAiReviewPatchValue(opType, field, value);
    if (valueError) {
      reject(valueError);
      continue;
    }

    valid.push(item);
  }

  return { valid, rejected, rejectedOperations };
}

export function formatRejectedPatchWarning(batchNumber: number, batchCount: number, attempt: number, rejected: string[]): string {
  const shown = rejected.slice(0, 3).join("; ");
  const suffix = rejected.length > 3 ? `; ${rejected.length - 3} more` : "";
  return `W_LLM_REVIEW_PATCH_OP_REJECTED: batch ${batchNumber}/${batchCount} attempt ${attempt}/${AI_REVIEW_MAX_ATTEMPTS} rejected ${rejected.length} unsafe op(s): ${shown}${suffix}.`;
}

function validateAiReviewPatchValue(opType: "replace" | "add", field: string, value: unknown): string | null {
  if (field === "risk_tags" && opType === "add") {
    return typeof value === "string" ? null : "risk_tags add value must be a string";
  }
  if (opType !== "replace") {
    return `add is not supported for field ${field}`;
  }
  if (field === "status") {
    return typeof value === "string" && AI_REVIEW_ALLOWED_STATUSES.has(value) ? null : `invalid status ${String(value)}`;
  }
  if (field === "risk_tags") {
    return Array.isArray(value) && value.every((item) => typeof item === "string")
      ? null
      : "risk_tags replace value must be a string array";
  }
  if (field === "reason") {
    return typeof value === "string" ? null : "reason must be a string";
  }
  if (field === "confidence") {
    return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1
      ? null
      : "confidence must be a number between 0 and 1";
  }
  return `field ${field} is not allowed`;
}

function stringifyMessage(message: unknown): string {
  if (typeof message === "string") return message;
  if (message && typeof message === "object") {
    const record = message as Record<string, unknown>;
    for (const key of ["content", "text", "message", "body"]) {
      const value = record[key];
      if (typeof value === "string") return value;
    }
  }
  return JSON.stringify(message);
}

function parseFirstJsonArray(text: string): unknown[] | null {
  const fencedCandidates = [...text.matchAll(/```(?:json)?\s*([\s\S]*?)```/gi)].map((match) => match[1]);
  const candidates = [...fencedCandidates, text];
  for (const candidate of candidates) {
    const parsed = parseJsonArrayCandidate(candidate.trim());
    if (parsed) return parsed;
  }
  return null;
}

function parseJsonArrayCandidate(candidate: string): unknown[] | null {
  for (let start = 0; start < candidate.length; start += 1) {
    if (candidate[start] !== "[") continue;

    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let index = start; index < candidate.length; index += 1) {
      const char = candidate[index];
      if (inString) {
        if (escaped) {
          escaped = false;
        } else if (char === "\\") {
          escaped = true;
        } else if (char === '"') {
          inString = false;
        }
        continue;
      }

      if (char === '"') {
        inString = true;
      } else if (char === "[") {
        depth += 1;
      } else if (char === "]") {
        depth -= 1;
        if (depth === 0) {
          try {
            const parsed = JSON.parse(candidate.slice(start, index + 1));
            if (Array.isArray(parsed)) return parsed;
          } catch {}
          break;
        }
      }
    }
  }
  return null;
}
