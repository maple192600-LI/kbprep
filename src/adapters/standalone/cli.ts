import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { parse, relative, resolve } from "node:path";
import { callWorker, type WorkerConfig, type WorkerResult } from "../../worker.js";
import { ensurePythonRuntime, type RuntimeConfig } from "../../runtime/pythonRuntime.js";

export type StandaloneCommand = "preflight" | "diagnose" | "prepare" | "apply_review" | "feedback" | "cleanup" | "prepare_batch";

type ParsedArgs = {
  help: boolean;
  options: Record<string, string | boolean>;
};

type CliPlan = {
  command: StandaloneCommand;
  input: Record<string, unknown>;
  cwd?: string;
  timeoutMs: number;
};

type CliRunResult = {
  exitCode: number;
  output: string;
};

const MAX_PATCH_JSON_BYTES = 1_000_000;
const MAX_CONFIG_JSON_BYTES = 64_000;
const RUNTIME_CONFIG_KEYS = new Set(["device_override", "max_cpu_threads", "min_free_memory_gb", "mineru_timeout_seconds", "python_path"]);

const HELP: Record<StandaloneCommand, string> = {
  preflight: [
    "Usage: kbprep-preflight [--workdir <dir>] [--profile lite|standard] [--config-file <file>]",
    "",
    "Checks KBPrep runtime readiness. Omit device_override to let KBPrep choose CPU/GPU automatically.",
  ].join("\n"),
  diagnose: [
    "Usage: kbprep-analyze --input <file|youtube.url|youtube-url> [--youtube-video-id <id>] [--output <dir>] [--source-type auto|pdf_like|markdown_note|generic_block|subtitle_transcript] [--config-file <file>]",
    "",
    "Reads one source file, local YouTube .url descriptor, direct YouTube URL, or explicit YouTube video id and reports source type, quality, and recommended processing route.",
  ].join("\n"),
  prepare: [
    "Usage: kbprep-prepare --input <file|youtube.url|youtube-url> [--youtube-video-id <id>] --output <dir> [--profile lite|standard|obsidian_kb|curated_obsidian_kb] [--mode rules_only|rules_plus_review_pack] [--source-url <url>] [--source-domain <domain>] [--site-name <name>] [--allow-youtube-media-fallback] [--max-quality-iterations <n>] [--force] [--config-file <file>]",
    "",
    "Converts one local source file, YouTube .url descriptor, direct YouTube URL, or explicit YouTube video id. Default profile standard publishes source-side Markdown; obsidian_kb publishes a generic Obsidian vault; curated_obsidian_kb is a compatibility template for course or self-media documents.",
  ].join("\n"),
  apply_review: [
    "Usage: kbprep-apply-review --run-dir <dir> --patch-file <json> [--config-file <file>]",
    "",
    "Applies a safe review JSON Patch to an existing KBPrep run.",
  ].join("\n"),
  feedback: [
    "Usage: kbprep-feedback --run-dir <dir> (--feedback-text <text>|--feedback-file <file>) [--action discard|review|protect] [--scope user|project|document_type|source_pattern|global] [--source-pattern <text>] [--risk-note <text>] [--rules-dir <dir>] [--config-file <file>]",
    "       kbprep-feedback --accept-proposal <id|latest> --confirm-rule-acceptance [--rerun-after-accept] [--rules-dir <dir>] [--config-file <file>]",
    "       kbprep-feedback --plan-rerun (--run-dir <dir>|--accepted-proposal <id|latest>|--document-type <type>) [--rules-dir <dir>] [--target-rules-dir <dir>] [--promotion-history-file <file>] [--config-file <file>]",
    "       kbprep-feedback --execute-rerun (--run-dir <dir>|--accepted-proposal <id|latest>|--document-type <type>) [--rules-dir <dir>] [--target-rules-dir <dir>] [--promotion-history-file <file>] [--config-file <file>]",
    "       kbprep-feedback --reject-proposal <id|latest> [--reject-reason <text>] [--rules-dir <dir>] [--config-file <file>]",
    "       kbprep-feedback --suggest-dictionary-updates [--min-feedback-count <n>] [--rules-dir <dir>] [--config-file <file>]",
    "       kbprep-feedback --promote-dictionary-suggestion --document-type <type> --confirm-dictionary-update [--confirm-public-write] [--rerun-after-promotion] [--allow-failed-promotion-history] [--representative-run-dir <dir>] [--rules-dir <dir>] [--target-rules-dir <dir>] [--config-file <file>]",
    "       kbprep-feedback --summarize-promotion-history [--document-type <type>] [--target-rules-dir <dir>] [--promotion-history-file <file>] [--config-file <file>]",
    "       kbprep-feedback --resolve-promotion-failures --document-type <type> --confirm-failure-resolved --representative-run-dir <dir> [--target-rules-dir <dir>] [--config-file <file>]",
    "",
    "Records user cleanup feedback as a reviewable rule proposal. Accepted proposals become user cleaning rules; rejected proposals are remembered but inactive. Dictionary suggestions promote to private .kbprep/rules by default; packaged public writes require --confirm-public-write.",
  ].join("\n"),
  cleanup: [
    "Usage: kbprep-cleanup --output <dir> [--action finalize|expired|all] [--older-than-days <n>] [--dry-run] [--config-file <file>]",
    "",
    "Cleans intermediate KBPrep artifacts while preserving the profile-specific final deliverable.",
  ].join("\n"),
  prepare_batch: [
    "Usage: kbprep-batch --input <dir> --output <dir> [--profile lite|standard|obsidian_kb|curated_obsidian_kb] [--mode rules_only|rules_plus_review_pack] [--max-quality-iterations <n>] [--convert-jobs <n>] [--config-file <file>]",
    "       kbprep-batch --playlist <youtube-playlist-url> --output <dir> [--playlist-limit <n>] [--allow-youtube-media-fallback] [--config-file <file>]",
    "       kbprep-batch --rerun --batch-manifest <batch_manifest.json> [--rerun-scope failed_only|pending_only|failed_and_pending|recommended] [--force] [--config-file <file>]",
    "",
    "Processes a directory or explicit YouTube playlist through the same agent-independent Python worker used by all callers. Rerun mode reprocesses only failed or pending children named by an existing batch manifest.",
  ].join("\n"),
};

export function parseStandaloneArgs(argv: string[]): ParsedArgs {
  const options: Record<string, string | boolean> = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--help" || token === "-h") return { help: true, options };
    if (!token.startsWith("--")) {
      throw new Error(`Unexpected positional argument: ${token}`);
    }
    const eqIndex = token.indexOf("=");
    if (eqIndex > 2) {
      const key = normalizeKey(token.slice(2, eqIndex));
      options[key] = token.slice(eqIndex + 1);
      continue;
    }
    const key = normalizeKey(token.slice(2));
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      options[key] = true;
      continue;
    }
    options[key] = next;
    index += 1;
  }
  return { help: false, options };
}

export function buildCliPlan(command: StandaloneCommand, options: Record<string, string | boolean>): CliPlan {
  switch (command) {
    case "preflight": {
      const workspacePath = resolveOutputDir(readString(options, "workdir") ?? process.cwd(), "workdir");
      mkdirSync(workspacePath, { recursive: true });
      return {
        command,
        input: {
          workspace_path: workspacePath,
          profile: readString(options, "profile") ?? "lite",
        },
        cwd: workspacePath,
        timeoutMs: 120_000,
      };
    }
    case "diagnose": {
      const outputRoot = resolveOutputDir(readString(options, "output") ?? ".kbprep/analyze", "output");
      mkdirSync(outputRoot, { recursive: true });
      const input = requireInputOrYoutubeDescriptor(options, "input", outputRoot);
      return {
        command,
        input: {
          input_path: input.inputPath,
          output_root: outputRoot,
          source_type: readString(options, "source_type") ?? "auto",
          source_url: input.sourceUrl,
        },
        timeoutMs: 120_000,
      };
    }
    case "prepare": {
      const outputRoot = requireOutputDir(options, "output");
      mkdirSync(outputRoot, { recursive: true });
      const input = requireInputOrYoutubeDescriptor(options, "input", outputRoot);
      return {
        command,
        input: {
          input_path: input.inputPath,
          output_root: outputRoot,
          profile: readString(options, "profile") ?? "standard",
          mode: readString(options, "mode") ?? "rules_only",
          force: readBoolean(options, "force", false),
          artifact_policy: readString(options, "artifact_policy") ?? "keep_latest",
          language: readString(options, "language") ?? "zh",
          source_type: readString(options, "source_type") ?? "auto",
          source_url: input.sourceUrl ?? readString(options, "source_url"),
          source_domain: readString(options, "source_domain"),
          site_name: readString(options, "site_name"),
          allow_youtube_media_fallback: readBoolean(options, "allow_youtube_media_fallback", false),
          splitter: readString(options, "splitter") ?? "auto",
          max_quality_iterations: readNumber(options, "max_quality_iterations", 3),
        },
        cwd: outputRoot,
        timeoutMs: 5_400_000,
      };
    }
    case "apply_review":
      return {
        command,
        input: {
          run_dir: requirePath(options, "run_dir"),
          patch_json: readPatchJson(options),
        },
        timeoutMs: 120_000,
      };
    case "feedback":
      return {
        command,
        input: {
          run_dir: isRunDirOptionalFeedback(options) ? undefined : requirePath(options, "run_dir"),
          feedback_text: readString(options, "feedback_text"),
          feedback_file: readOptionalFilePath(options, "feedback_file"),
          accept_proposal: readString(options, "accept_proposal"),
          accepted_proposal: readString(options, "accepted_proposal"),
          confirm_rule_acceptance: readBoolean(options, "confirm_rule_acceptance", false),
          plan_rerun: readBoolean(options, "plan_rerun", false),
          execute_rerun: readBoolean(options, "execute_rerun", false),
          rerun_after_accept: readBoolean(options, "rerun_after_accept", false),
          reject_proposal: readString(options, "reject_proposal"),
          reject_reason: readString(options, "reject_reason"),
          suggest_dictionary_updates: readBoolean(options, "suggest_dictionary_updates", false),
          min_feedback_count: readNumber(options, "min_feedback_count", undefined),
          promote_dictionary_suggestion: readBoolean(options, "promote_dictionary_suggestion", false),
          confirm_dictionary_update: readBoolean(options, "confirm_dictionary_update", false),
          confirm_public_write: readBoolean(options, "confirm_public_write", false),
          rerun_after_promotion: readBoolean(options, "rerun_after_promotion", false),
          allow_failed_promotion_history: readBoolean(options, "allow_failed_promotion_history", false),
          representative_run_dirs: readOptionalPathList(options, "representative_run_dir"),
          summarize_promotion_history: readBoolean(options, "summarize_promotion_history", false),
          promotion_history_file: readOptionalPath(options, "promotion_history_file"),
          resolve_promotion_failures: readBoolean(options, "resolve_promotion_failures", false),
          confirm_failure_resolved: readBoolean(options, "confirm_failure_resolved", false),
          target_rules_dir: readOptionalPath(options, "target_rules_dir"),
          suggestions_file: readOptionalPath(options, "suggestions_file"),
          action: readString(options, "action"),
          scope: readString(options, "scope") ?? "user",
          source_pattern: readString(options, "source_pattern"),
          document_type: readString(options, "document_type"),
          pattern: readString(options, "pattern"),
          match: readString(options, "match") ?? "literal",
          reason: readString(options, "reason"),
          risk_note: readString(options, "risk_note"),
          rules_dir: readOptionalPath(options, "rules_dir"),
        },
        timeoutMs: 120_000,
      };
    case "cleanup":
      const cleanupDryRun = readBoolean(options, "dry_run", false);
      return {
        command,
        input: {
          output_root: requireCleanupOutput(options, "output"),
          action: readString(options, "action") ?? (cleanupDryRun ? "all" : "finalize"),
          older_than_days: readNumber(options, "older_than_days", 7),
          confirm_review_needed: readBoolean(options, "confirm_review_needed", false),
          dry_run: cleanupDryRun,
        },
        timeoutMs: 120_000,
      };
    case "prepare_batch": {
      if (readBoolean(options, "rerun", false)) {
        return {
          command,
          input: {
            rerun: true,
            batch_manifest_path: requireFilePath(options, "batch_manifest"),
            rerun_scope: readBatchRerunScope(options),
            force: readOptionalBoolean(options, "force"),
            profile: readString(options, "profile"),
            mode: readString(options, "mode"),
            artifact_policy: readString(options, "artifact_policy"),
            language: readString(options, "language"),
            convert_jobs: readNumber(options, "convert_jobs", undefined),
            max_quality_iterations: readNumber(options, "max_quality_iterations", undefined),
          },
          timeoutMs: 10_800_000,
        };
      }
      const outputRoot = requireOutputDir(options, "output");
      mkdirSync(outputRoot, { recursive: true });
      const playlistUrl = readString(options, "playlist");
      if (playlistUrl) {
        if (readString(options, "input")) throw new Error("--playlist cannot be combined with --input.");
        return {
          command,
          input: {
            playlist_url: requireYouTubePlaylistUrl(playlistUrl),
            output_root: outputRoot,
            profile: readString(options, "profile") ?? "standard",
            mode: readString(options, "mode") ?? "rules_only",
            force: readBoolean(options, "force", false),
            artifact_policy: readString(options, "artifact_policy") ?? "keep_latest",
            language: readString(options, "language") ?? "zh",
            convert_jobs: readNumber(options, "convert_jobs", 1),
            max_quality_iterations: readNumber(options, "max_quality_iterations", 3),
            playlist_limit: readNumber(options, "playlist_limit", undefined),
            allow_youtube_media_fallback: readBoolean(options, "allow_youtube_media_fallback", false),
          },
          cwd: outputRoot,
          timeoutMs: 10_800_000,
        };
      }
      return {
        command,
        input: {
          input_dir: requireInputDir(options, "input"),
          output_root: outputRoot,
          profile: readString(options, "profile") ?? "standard",
          mode: readString(options, "mode") ?? "rules_only",
          force: readBoolean(options, "force", false),
          artifact_policy: readString(options, "artifact_policy") ?? "keep_latest",
          language: readString(options, "language") ?? "zh",
          convert_jobs: readNumber(options, "convert_jobs", 1),
          max_quality_iterations: readNumber(options, "max_quality_iterations", 3),
        },
        cwd: outputRoot,
        timeoutMs: 10_800_000,
      };
    }
    default:
      return assertNever(command);
  }
}

export async function runStandaloneCli(command: StandaloneCommand, argv = process.argv.slice(2)): Promise<CliRunResult> {
  try {
    const parsed = parseStandaloneArgs(argv);
    if (parsed.help) return { exitCode: 0, output: `${HELP[command]}\n` };

    const config = readRuntimeConfig(parsed.options);
    const plan = buildCliPlan(command, parsed.options);
    const pythonPath = await ensurePythonRuntime(config);
    const result = await callWorker(plan.command, plan.input, {
      pythonPath,
      cwd: plan.cwd,
      timeoutMs: plan.timeoutMs,
      config: workerConfig(config),
    });
    return formatResult(result);
  } catch (error) {
    return {
      exitCode: 1,
      output: `${JSON.stringify(
        {
          ok: false,
          error: {
            code: "KBPREP_CLI_ERROR",
            message: error instanceof Error ? error.message : String(error),
          },
        },
        null,
        2,
      )}\n`,
    };
  }
}

export async function main(command: StandaloneCommand, argv = process.argv.slice(2)): Promise<void> {
  const result = await runStandaloneCli(command, argv);
  process.stdout.write(result.output);
  process.exitCode = result.exitCode;
}

function readRuntimeConfig(options: Record<string, string | boolean>): RuntimeConfig {
  const configPath = readString(options, "config_file");
  const fileConfig = configPath ? readJsonObjectFile(resolvePath(configPath), "config file", MAX_CONFIG_JSON_BYTES) : {};
  validateRuntimeConfig(fileConfig);
  return {
    device_override: readDeviceOverride(options, fileConfig),
    max_cpu_threads: readNumber(options, "max_cpu_threads", readOptionalNumber(fileConfig.max_cpu_threads)),
    min_free_memory_gb: readNumber(options, "min_free_memory_gb", readOptionalNumber(fileConfig.min_free_memory_gb)),
    mineru_timeout_seconds: readNumber(options, "mineru_timeout_seconds", readOptionalNumber(fileConfig.mineru_timeout_seconds)),
    python_path: readString(options, "python_path") ?? readOptionalString(fileConfig.python_path),
  };
}

function workerConfig(config: RuntimeConfig): WorkerConfig {
  return {
    device_override: config.device_override,
    max_cpu_threads: config.max_cpu_threads,
    min_free_memory_gb: config.min_free_memory_gb,
    mineru_timeout_seconds: config.mineru_timeout_seconds,
  };
}

function formatResult(result: WorkerResult): CliRunResult {
  return {
    exitCode: result.ok ? 0 : 1,
    output: `${JSON.stringify(result, null, 2)}\n`,
  };
}

function readPatchJson(options: Record<string, string | boolean>): unknown {
  const inline = readString(options, "patch_json");
  if (inline) return JSON.parse(inline);
  const patchFile = readString(options, "patch_file");
  if (patchFile) return readJsonFile(resolvePath(patchFile), "patch file", MAX_PATCH_JSON_BYTES);
  throw new Error("--patch-file or --patch-json is required.");
}

function readJsonObjectFile(filePath: string, label: string, maxBytes: number): Record<string, unknown> {
  const payload = readJsonFile(filePath, label, maxBytes);
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`${label} must contain a JSON object.`);
  }
  return payload as Record<string, unknown>;
}

function readJsonFile(filePath: string, label: string, maxBytes: number): unknown {
  const stats = statSync(filePath);
  if (!stats.isFile()) throw new Error(`${label} is not a file: ${filePath}`);
  if (stats.size > maxBytes) {
    throw new Error(`${label} is too large: ${stats.size} bytes exceeds ${maxBytes} bytes.`);
  }
  return JSON.parse(readFileSync(filePath, "utf-8"));
}

function validateRuntimeConfig(config: Record<string, unknown>): void {
  for (const key of Object.keys(config)) {
    if (!RUNTIME_CONFIG_KEYS.has(key)) throw new Error(`Unknown config key: ${key}`);
  }
}

function isRunDirOptionalFeedback(options: Record<string, string | boolean>): boolean {
  return Boolean(
    readString(options, "accept_proposal") ||
    readString(options, "accepted_proposal") ||
    readBoolean(options, "plan_rerun", false) ||
    readBoolean(options, "execute_rerun", false) ||
    readString(options, "reject_proposal") ||
    readBoolean(options, "suggest_dictionary_updates", false) ||
    readBoolean(options, "promote_dictionary_suggestion", false) ||
    readBoolean(options, "summarize_promotion_history", false) ||
    readBoolean(options, "resolve_promotion_failures", false),
  );
}

function readDeviceOverride(
  options: Record<string, string | boolean>,
  fileConfig: Record<string, unknown>,
): RuntimeConfig["device_override"] {
  const raw = readString(options, "device_override") ?? readOptionalString(fileConfig.device_override);
  if (!raw) return undefined;
  if (raw === "auto") return undefined;
  if (raw === "cuda" || raw === "cpu") return raw;
  throw new Error(`Invalid device_override: ${raw}`);
}

function requirePath(options: Record<string, string | boolean>, key: string): string {
  const value = readString(options, key);
  if (!value) throw new Error(`--${key.replace(/_/g, "-")} is required.`);
  return resolveBoundedPath(value, key);
}

function requireFilePath(options: Record<string, string | boolean>, key: string): string {
  const filePath = requirePath(options, key);
  let stats;
  try {
    stats = statSync(filePath);
  } catch {
    throw new Error(`--${key.replace(/_/g, "-")} must be a file: ${filePath}`);
  }
  if (!stats.isFile()) throw new Error(`--${key.replace(/_/g, "-")} must be a file: ${filePath}`);
  return filePath;
}

function requireInputFile(options: Record<string, string | boolean>, key: string): string {
  const value = readString(options, key);
  if (!value) throw new Error(`--${key.replace(/_/g, "-")} is required.`);
  const filePath = resolvePath(value);
  let stats;
  try {
    stats = statSync(filePath);
  } catch {
    throw new Error(`--${key.replace(/_/g, "-")} must be a file: ${filePath}`);
  }
  if (!stats.isFile()) throw new Error(`--${key.replace(/_/g, "-")} must be a file: ${filePath}`);
  return filePath;
}

function requireInputOrYoutubeDescriptor(
  options: Record<string, string | boolean>,
  key: string,
  outputRoot: string,
): { inputPath: string; sourceUrl?: string } {
  const value = readString(options, key);
  const explicitVideoId = readString(options, "youtube_video_id");
  if (!value && !explicitVideoId) throw new Error(`--${key.replace(/_/g, "-")} is required.`);
  if (explicitVideoId) {
    const youtubeUrl = youtubeUrlFromVideoId(explicitVideoId);
    const descriptor = youtubeDescriptorPath(outputRoot, youtubeUrl);
    mkdirSync(resolve(outputRoot, ".kbprep-inputs", "youtube"), { recursive: true });
    writeFileSync(descriptor, `[InternetShortcut]\nURL=${youtubeUrl}\n`, "utf-8");
    return { inputPath: descriptor, sourceUrl: youtubeUrl };
  }
  if (!value) throw new Error(`--${key.replace(/_/g, "-")} is required.`);
  const candidatePath = resolvePath(value);
  try {
    if (statSync(candidatePath).isFile()) return { inputPath: candidatePath };
  } catch {
    // Fall through so direct YouTube URLs and video ids can become descriptors.
  }
  const youtubeUrl = normalizeYouTubeInput(value);
  if (!youtubeUrl) return { inputPath: requireInputFile(options, key) };
  const descriptor = youtubeDescriptorPath(outputRoot, youtubeUrl);
  mkdirSync(resolve(outputRoot, ".kbprep-inputs", "youtube"), { recursive: true });
  writeFileSync(descriptor, `[InternetShortcut]\nURL=${youtubeUrl}\n`, "utf-8");
  return { inputPath: descriptor, sourceUrl: youtubeUrl };
}

function requireInputDir(options: Record<string, string | boolean>, key: string): string {
  const value = readString(options, key);
  if (!value) throw new Error(`--${key.replace(/_/g, "-")} is required.`);
  const dirPath = resolvePath(value);
  const stats = statSync(dirPath);
  if (!stats.isDirectory()) throw new Error(`--${key.replace(/_/g, "-")} must be a directory: ${dirPath}`);
  return dirPath;
}

function requireOutputDir(options: Record<string, string | boolean>, key: string): string {
  const value = readString(options, key);
  if (!value) throw new Error(`--${key.replace(/_/g, "-")} is required.`);
  return resolveOutputDir(value, key);
}

function requireCleanupOutput(options: Record<string, string | boolean>, key: string): string {
  return requireOutputDir(options, key);
}

function resolveOutputDir(value: string, label: string): string {
  const outputPath = resolveBoundedPath(value, label);
  rejectDangerousOutputRoot(outputPath, label);
  return outputPath;
}

function rejectDangerousOutputRoot(outputPath: string, label: string): void {
  const parsed = parse(outputPath);
  if (outputPath === parsed.root) {
    throw new Error(`--${label.replace(/_/g, "-")} cannot point at a filesystem root: ${outputPath}`);
  }
}

function readOptionalPath(options: Record<string, string | boolean>, key: string): string | undefined {
  const value = readString(options, key);
  return value ? resolvePath(value) : undefined;
}

function readOptionalFilePath(options: Record<string, string | boolean>, key: string): string | undefined {
  const filePath = readOptionalPath(options, key);
  if (!filePath) return undefined;
  const stats = statSync(filePath);
  if (!stats.isFile()) throw new Error(`${key} must be a file: ${filePath}`);
  return filePath;
}

function readOptionalPathList(options: Record<string, string | boolean>, key: string): string[] | undefined {
  const value = readOptionalPath(options, key);
  return value ? [value] : undefined;
}

function resolvePath(value: string): string {
  return resolve(process.cwd(), value);
}

function resolveBoundedPath(value: string, label: string): string {
  const resolved = resolvePath(value);
  const boundary = process.env.KBPREP_CLI_BOUNDARY_DIR?.trim();
  if (!boundary) return resolved;
  const boundaryPath = resolve(process.cwd(), boundary);
  const relation = relative(boundaryPath, resolved);
  if (relation === "" || (!relation.startsWith("..") && !parse(relation).root)) return resolved;
  throw new Error(`Path escapes CLI boundary for --${label.replace(/_/g, "-")}: ${value}`);
}

function readString(options: Record<string, string | boolean>, key: string): string | undefined {
  const value = options[key];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function readOptionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function readNumber(options: Record<string, string | boolean>, key: string, fallback: number | undefined): number | undefined {
  const raw = readString(options, key);
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`--${key.replace(/_/g, "-")} must be a number.`);
  return value;
}

function readOptionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function readBoolean(options: Record<string, string | boolean>, key: string, fallback: boolean): boolean {
  const value = options[key];
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (value === "true") return true;
    if (value === "false") return false;
    throw new Error(`--${key.replace(/_/g, "-")} must be true or false.`);
  }
  return fallback;
}

function readOptionalBoolean(options: Record<string, string | boolean>, key: string): boolean | undefined {
  if (!(key in options)) return undefined;
  return readBoolean(options, key, false);
}

function readBatchRerunScope(options: Record<string, string | boolean>): string {
  const raw = readString(options, "rerun_scope") ?? "recommended";
  const normalized = raw.replace(/-/g, "_");
  const allowed = new Set(["recommended", "failed_only", "pending_only", "failed_and_pending"]);
  if (!allowed.has(normalized)) {
    throw new Error("--rerun-scope must be recommended, failed_only, pending_only, or failed_and_pending.");
  }
  return normalized;
}

function normalizeYouTubeInput(value: string): string | undefined {
  if (isYouTubeUrl(value)) return value.trim();
  return undefined;
}

function requireYouTubePlaylistUrl(value: string): string {
  if (isYouTubePlaylistUrl(value)) return value.trim();
  throw new Error("--playlist must be a YouTube playlist URL.");
}

function youtubeUrlFromVideoId(value: string): string {
  const videoId = safeVideoId(value);
  if (!videoId) throw new Error("--youtube-video-id must contain a YouTube video id.");
  return `https://www.youtube.com/watch?v=${videoId}`;
}

function youtubeDescriptorPath(outputRoot: string, sourceUrl: string): string {
  const videoId = videoIdFromYouTubeUrl(sourceUrl) ?? "youtube";
  return resolve(outputRoot, ".kbprep-inputs", "youtube", `${videoId}.url`);
}

function isYouTubeUrl(value: string): boolean {
  try {
    return videoIdFromYouTubeUrl(value) !== undefined;
  } catch {
    return false;
  }
}

function videoIdFromYouTubeUrl(value: string): string | undefined {
  const url = new URL(value.trim());
  if (url.protocol !== "http:" && url.protocol !== "https:") return undefined;
  const host = url.hostname.toLowerCase();
  if (host === "youtu.be") return safeVideoId(url.pathname.slice(1).split("/")[0]);
  if (!["youtube.com", "www.youtube.com", "m.youtube.com"].includes(host)) return undefined;
  if (url.pathname === "/watch") return safeVideoId(url.searchParams.get("v") ?? undefined);
  const match = url.pathname.match(/^\/(?:shorts|embed)\/([^/?#]+)/);
  return match ? safeVideoId(match[1]) : undefined;
}

function isYouTubePlaylistUrl(value: string): boolean {
  try {
    const url = new URL(value.trim());
    if (url.protocol !== "http:" && url.protocol !== "https:") return false;
    const host = url.hostname.toLowerCase();
    if (!["youtube.com", "www.youtube.com", "m.youtube.com"].includes(host)) return false;
    if (url.pathname !== "/playlist" && url.pathname !== "/watch") return false;
    return safeVideoId(url.searchParams.get("list") ?? undefined) !== undefined;
  } catch {
    return false;
  }
}

function safeVideoId(value: string | undefined): string | undefined {
  const sanitized = (value ?? "").replace(/[^A-Za-z0-9_-]+/g, "").slice(0, 64);
  return sanitized || undefined;
}

function normalizeKey(key: string): string {
  return key.replace(/-/g, "_");
}

function assertNever(value: never): never {
  throw new Error(`Unhandled command: ${value}`);
}
