import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildCliPlan, parseStandaloneArgs, runStandaloneCli } from "./cli.js";

describe("standalone KBPrep CLI adapter", () => {
  it("prints help without requiring an agent-host adapter or Python setup", async () => {
    const result = await runStandaloneCli("prepare", ["--help"]);

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain("Usage: kbprep-prepare");
    expect(result.output).toContain("--input <file|youtube.url|youtube-url>");
    expect(result.output).toContain("--youtube-video-id <id>");
    expect(result.output).toContain("--allow-youtube-media-fallback");
    expect(result.output).toContain("Default profile standard");
    expect(result.output).toContain("compatibility template");
    expect(result.output).not.toContain("legacy course/self-media");
  });

  it("describes cleanup as preserving the profile-specific final deliverable", async () => {
    const result = await runStandaloneCli("cleanup", ["--help"]);

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain("Usage: kbprep-cleanup");
    expect(result.output).toContain("profile-specific final deliverable");
    expect(result.output).not.toContain("source-side final outputs");
  });

  it("prints help for every standalone command without touching Python setup", async () => {
    const commands = [
      ["preflight", "kbprep-preflight"],
      ["diagnose", "kbprep-analyze"],
      ["prepare", "kbprep-prepare"],
      ["apply_review", "kbprep-apply-review"],
      ["feedback", "kbprep-feedback"],
      ["cleanup", "kbprep-cleanup"],
      ["prepare_batch", "kbprep-batch"],
    ] as const;

    for (const [command, binName] of commands) {
      const result = await runStandaloneCli(command, ["--help"]);
      expect(result.exitCode).toBe(0);
      expect(result.output).toContain(`Usage: ${binName}`);
    }
  });

  it("returns a JSON CLI error when apply-review is missing a patch", async () => {
    const result = await runStandaloneCli("apply_review", ["--run-dir", ".kbprep/missing-patch"]);
    const payload = JSON.parse(result.output) as { ok: boolean; error: { code: string; message: string } };

    expect(result.exitCode).toBe(1);
    expect(payload.ok).toBe(false);
    expect(payload.error.code).toBe("KBPREP_CLI_ERROR");
    expect(payload.error.message).toContain("--patch-file or --patch-json is required");
  });

  it("returns a JSON CLI error for invalid boolean options instead of silently using defaults", async () => {
    const result = await runStandaloneCli("cleanup", ["--output", ".kbprep/cleanup", "--dry-run", "maybe"]);
    const payload = JSON.parse(result.output) as { ok: boolean; error: { code: string; message: string } };

    expect(result.exitCode).toBe(1);
    expect(payload.ok).toBe(false);
    expect(payload.error.code).toBe("KBPREP_CLI_ERROR");
    expect(payload.error.message).toContain("--dry-run must be true or false");
  });

  it("returns a JSON CLI error when config files contain unknown keys", async () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-config-"));
    try {
      const configPath = join(root, "config.json");
      writeFileSync(configPath, JSON.stringify({ python_path: "python", unexpected: true }), "utf-8");

      const result = await runStandaloneCli("preflight", ["--workdir", root, "--config-file", configPath]);
      const payload = JSON.parse(result.output) as { ok: boolean; error: { code: string; message: string } };

      expect(result.exitCode).toBe(1);
      expect(payload.ok).toBe(false);
      expect(payload.error.code).toBe("KBPREP_CLI_ERROR");
      expect(payload.error.message).toContain("Unknown config key: unexpected");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("returns a JSON CLI error instead of reading oversized patch files", async () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-patch-"));
    try {
      const patchPath = join(root, "patch.json");
      writeFileSync(patchPath, `[${'"x"'.repeat(1_100_000)}]`, "utf-8");

      const result = await runStandaloneCli("apply_review", ["--run-dir", root, "--patch-file", patchPath]);
      const payload = JSON.parse(result.output) as { ok: boolean; error: { code: string; message: string } };

      expect(result.exitCode).toBe(1);
      expect(payload.ok).toBe(false);
      expect(payload.error.code).toBe("KBPREP_CLI_ERROR");
      expect(payload.error.message).toContain("patch file is too large");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("allows explicit absolute input paths while rejecting filesystem-root outputs", async () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-paths-"));
    try {
      const inputPath = join(root, "source.md");
      writeFileSync(inputPath, "# Source\n", "utf-8");
      const parsed = parseStandaloneArgs(["--input", inputPath, "--output", ".kbprep/absolute-input"]);
      const plan = buildCliPlan("prepare", parsed.options);
      expect(plan.input.input_path).toBe(inputPath);

      const rootOutput = process.platform === "win32" ? inputPath.slice(0, 3) : "/";
      const rejected = await runStandaloneCli("cleanup", ["--output", rootOutput]);
      const payload = JSON.parse(rejected.output) as { ok: boolean; error: { message: string } };
      expect(rejected.exitCode).toBe(1);
      expect(payload.error.message).toContain("cannot point at a filesystem root");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("keeps explicit input reads outside the optional CLI boundary while blocking output writes", () => {
    const boundary = mkdtempSync(join(tmpdir(), "kbprep-cli-boundary-"));
    const outside = mkdtempSync(join(tmpdir(), "kbprep-cli-outside-"));
    const previous = process.env.KBPREP_CLI_BOUNDARY_DIR;
    try {
      process.env.KBPREP_CLI_BOUNDARY_DIR = boundary;
      const inputPath = join(outside, "source.md");
      writeFileSync(inputPath, "# External source\n", "utf-8");

      const parsed = parseStandaloneArgs(["--input", inputPath, "--output", join(boundary, "out")]);
      const plan = buildCliPlan("prepare", parsed.options);
      expect(plan.input.input_path).toBe(inputPath);

      const rejected = parseStandaloneArgs(["--input", inputPath, "--output", join(outside, "out")]);
      expect(() => buildCliPlan("prepare", rejected.options)).toThrow(/Path escapes CLI boundary/);
    } finally {
      if (previous === undefined) delete process.env.KBPREP_CLI_BOUNDARY_DIR;
      else process.env.KBPREP_CLI_BOUNDARY_DIR = previous;
      rmSync(boundary, { recursive: true, force: true });
      rmSync(outside, { recursive: true, force: true });
    }
  });

  it("rejects feedback file paths that are directories before calling the worker", async () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-feedback-file-"));
    try {
      const result = await runStandaloneCli("feedback", ["--run-dir", root, "--feedback-file", root]);
      const payload = JSON.parse(result.output) as { ok: boolean; error: { message: string } };

      expect(result.exitCode).toBe(1);
      expect(payload.error.message).toContain("feedback_file must be a file");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("maps analyze CLI options to the Python diagnose worker command", () => {
    const parsed = parseStandaloneArgs(["--input", "README.md"]);
    const plan = buildCliPlan("diagnose", parsed.options);

    expect(plan.command).toBe("diagnose");
    expect(plan.input.input_path).toContain("README.md");
    expect(plan.input.output_root).toContain(join(".kbprep", "analyze"));
    expect(plan.input.source_type).toBe("auto");
  });

  it("keeps prepare defaults aligned with the generic standard profile", () => {
    const parsed = parseStandaloneArgs([
      "--input",
      "README.md",
      "--output",
      ".kbprep/cli-test",
      "--max-quality-iterations",
      "4",
      "--force",
    ]);
    const plan = buildCliPlan("prepare", parsed.options);

    expect(plan.command).toBe("prepare");
    expect(plan.input.profile).toBe("standard");
    expect(plan.input.mode).toBe("rules_only");
    expect(plan.input.force).toBe(true);
    expect(plan.input.artifact_policy).toBe("keep_latest");
    expect(plan.input.max_quality_iterations).toBe(4);
  });

  it("maps prepare source identity options to the Python worker command", () => {
    const parsed = parseStandaloneArgs([
      "--input",
      "README.md",
      "--output",
      ".kbprep/cli-source-identity",
      "--source-url",
      "https://example.com/course/lesson-1",
      "--source-domain",
      "example.com",
      "--site-name",
      "Example Course",
    ]);
    const plan = buildCliPlan("prepare", parsed.options);

    expect(plan.command).toBe("prepare");
    expect(plan.input.source_url).toBe("https://example.com/course/lesson-1");
    expect(plan.input.source_domain).toBe("example.com");
    expect(plan.input.site_name).toBe("Example Course");
  });

  it("maps direct YouTube URL input to a local descriptor without enabling media fallback by default", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-youtube-"));
    try {
      const parsed = parseStandaloneArgs(["--input", "https://www.youtube.com/watch?v=ExampleVideo01", "--output", root]);
      const plan = buildCliPlan("prepare", parsed.options);

      expect(plan.command).toBe("prepare");
      expect(plan.input.source_url).toBe("https://www.youtube.com/watch?v=ExampleVideo01");
      expect(plan.input.input_path).toContain(join(".kbprep-inputs", "youtube", "ExampleVideo01.url"));
      expect(readFileSync(plan.input.input_path as string, "utf-8")).toContain("URL=https://www.youtube.com/watch?v=ExampleVideo01");
      expect(plan.input.allow_youtube_media_fallback).toBe(false);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("maps accepted YouTube URL shapes to stable local descriptors", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-youtube-shapes-"));
    const cases = [
      ["https://www.youtube.com/watch?v=ExampleVideo01&t=30s", "ExampleVideo01"],
      ["https://youtu.be/ExampleVideo02?si=share", "ExampleVideo02"],
      ["https://www.youtube.com/shorts/ExampleVideo03?feature=share", "ExampleVideo03"],
      ["https://www.youtube.com/embed/ExampleVideo04?start=12", "ExampleVideo04"],
      ["https://m.youtube.com/watch?v=ExampleVideo05", "ExampleVideo05"],
    ];
    try {
      for (const [url, videoId] of cases) {
        const parsed = parseStandaloneArgs(["--input", url, "--output", root]);
        const plan = buildCliPlan("prepare", parsed.options);

        expect(plan.input.source_url).toBe(url);
        expect(plan.input.input_path).toContain(join(".kbprep-inputs", "youtube", `${videoId}.url`));
        expect(readFileSync(plan.input.input_path as string, "utf-8")).toContain(`URL=${url}`);
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects undocumented YouTube URL shapes as local inputs", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-youtube-unsupported-"));
    try {
      const parsed = parseStandaloneArgs(["--input", "https://www.youtube.com/live/ExampleVideo06?v=ExampleVideo06", "--output", root]);

      expect(() => buildCliPlan("prepare", parsed.options)).toThrow("--input must be a file");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("maps explicit YouTube video ids and fallback to the worker command", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-youtube-id-"));
    try {
      const parsed = parseStandaloneArgs(["--youtube-video-id", "ExampleVideo01", "--output", root, "--allow-youtube-media-fallback"]);
      const plan = buildCliPlan("prepare", parsed.options);

      expect(plan.input.source_url).toBe("https://www.youtube.com/watch?v=ExampleVideo01");
      expect(plan.input.input_path).toContain(join(".kbprep-inputs", "youtube", "ExampleVideo01.url"));
      expect(plan.input.allow_youtube_media_fallback).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not mistake a missing local filename for a YouTube video id", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-missing-local-"));
    try {
      const parsed = parseStandaloneArgs(["--input", "chapter01", "--output", root]);

      expect(() => buildCliPlan("prepare", parsed.options)).toThrow(/must be a file/);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("maps cleanup dry-run options to the Python cleanup worker command", () => {
    const parsed = parseStandaloneArgs(["--output", ".kbprep/cleanup", "--action", "expired", "--older-than-days", "30", "--dry-run"]);
    const plan = buildCliPlan("cleanup", parsed.options);

    expect(plan.command).toBe("cleanup");
    expect(plan.input.output_root).toContain(join(".kbprep", "cleanup"));
    expect(plan.input.action).toBe("expired");
    expect(plan.input.older_than_days).toBe(30);
    expect(plan.input.dry_run).toBe(true);
  });

  it("defaults cleanup dry-run to all-artifact preview without weakening finalize cleanup", () => {
    const parsed = parseStandaloneArgs(["--output", ".kbprep/cleanup", "--dry-run"]);
    const plan = buildCliPlan("cleanup", parsed.options);

    expect(plan.command).toBe("cleanup");
    expect(plan.input.action).toBe("all");
    expect(plan.input.dry_run).toBe(true);
  });

  it("maps batch options to the Python prepare_batch worker command", () => {
    const parsed = parseStandaloneArgs([
      "--input",
      "docs",
      "--output",
      ".kbprep/batch",
      "--convert-jobs",
      "2",
      "--max-quality-iterations",
      "5",
      "--force",
    ]);
    const plan = buildCliPlan("prepare_batch", parsed.options);

    expect(plan.command).toBe("prepare_batch");
    expect(plan.input.input_dir).toContain("docs");
    expect(plan.input.output_root).toContain(join(".kbprep", "batch"));
    expect(plan.input.convert_jobs).toBe(2);
    expect(plan.input.max_quality_iterations).toBe(5);
    expect(plan.input.force).toBe(true);
    expect(plan.input.profile).toBe("standard");
  });

  it("maps explicit YouTube playlist input to the Python prepare_batch worker command", () => {
    const parsed = parseStandaloneArgs([
      "--playlist",
      "https://www.youtube.com/playlist?list=ExamplePlaylist01",
      "--output",
      ".kbprep/playlist",
      "--playlist-limit",
      "2",
      "--allow-youtube-media-fallback",
      "--force",
    ]);
    const plan = buildCliPlan("prepare_batch", parsed.options);

    expect(plan.command).toBe("prepare_batch");
    expect(plan.input.input_dir).toBeUndefined();
    expect(plan.input.playlist_url).toBe("https://www.youtube.com/playlist?list=ExamplePlaylist01");
    expect(plan.input.playlist_limit).toBe(2);
    expect(plan.input.allow_youtube_media_fallback).toBe(true);
    expect(plan.input.output_root).toContain(join(".kbprep", "playlist"));
  });

  it("maps batch rerun options to the Python prepare_batch worker command", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-batch-rerun-"));
    try {
      const manifest = join(root, "batch_manifest.json");
      writeFileSync(manifest, "{}", "utf-8");
      const parsed = parseStandaloneArgs(["--rerun", "--batch-manifest", manifest, "--rerun-scope", "failed-and-pending", "--force"]);
      const plan = buildCliPlan("prepare_batch", parsed.options);

      expect(plan.command).toBe("prepare_batch");
      expect(plan.input.rerun).toBe(true);
      expect(plan.input.batch_manifest_path).toBe(manifest);
      expect(plan.input.rerun_scope).toBe("failed_and_pending");
      expect(plan.input.force).toBe(true);
      expect(plan.input.input_dir).toBeUndefined();
      expect(plan.input.output_root).toBeUndefined();
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not override batch rerun manifest force defaults unless force is passed", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-batch-rerun-force-"));
    try {
      const manifest = join(root, "batch_manifest.json");
      writeFileSync(manifest, "{}", "utf-8");
      const parsed = parseStandaloneArgs(["--rerun", "--batch-manifest", manifest]);
      const plan = buildCliPlan("prepare_batch", parsed.options);

      expect(plan.input.force).toBeUndefined();
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects batch rerun when the manifest file is missing", () => {
    const parsed = parseStandaloneArgs(["--rerun", "--batch-manifest", ".kbprep/missing-batch-manifest.json"]);

    expect(() => buildCliPlan("prepare_batch", parsed.options)).toThrow("--batch-manifest must be a file");
  });

  it("rejects invalid batch rerun scope values", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-batch-rerun-scope-"));
    try {
      const manifest = join(root, "batch_manifest.json");
      writeFileSync(manifest, "{}", "utf-8");
      const parsed = parseStandaloneArgs(["--rerun", "--batch-manifest", manifest, "--rerun-scope", "all"]);

      expect(() => buildCliPlan("prepare_batch", parsed.options)).toThrow("--rerun-scope must be");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("does not expose internal affected batch rerun scope as a public CLI option", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-batch-rerun-affected-"));
    try {
      const manifest = join(root, "batch_manifest.json");
      writeFileSync(manifest, "{}", "utf-8");
      const parsed = parseStandaloneArgs(["--rerun", "--batch-manifest", manifest, "--rerun-scope", "affected"]);

      expect(() => buildCliPlan("prepare_batch", parsed.options)).toThrow("--rerun-scope must be");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("maps batch policy_affected rerun scope and affected identity to the worker payload", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-batch-rerun-policy-affected-"));
    try {
      const manifest = join(root, "batch_manifest.json");
      writeFileSync(manifest, "{}", "utf-8");
      const parsed = parseStandaloneArgs([
        "--rerun",
        "--batch-manifest",
        manifest,
        "--rerun-scope",
        "policy-affected",
        "--affected-document-id",
        "doc-123",
        "--affected-policy-snapshot-hash",
        "abc123",
        "--affected-source-identity",
        '{"source_domain":"example.com"}',
      ]);
      const plan = buildCliPlan("prepare_batch", parsed.options);

      expect(plan.command).toBe("prepare_batch");
      expect(plan.input.rerun).toBe(true);
      expect(plan.input.rerun_scope).toBe("policy_affected");
      expect(plan.input.affected_document_id).toBe("doc-123");
      expect(plan.input.affected_policy_snapshot_hash).toBe("abc123");
      expect(plan.input.affected_source_identity).toEqual({ source_domain: "example.com" });
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("accepts policy_affected scope without affected identity (worker validates)", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-batch-rerun-policy-affected-bare-"));
    try {
      const manifest = join(root, "batch_manifest.json");
      writeFileSync(manifest, "{}", "utf-8");
      const parsed = parseStandaloneArgs([
        "--rerun",
        "--batch-manifest",
        manifest,
        "--rerun-scope",
        "policy-affected",
      ]);
      const plan = buildCliPlan("prepare_batch", parsed.options);

      expect(plan.input.rerun_scope).toBe("policy_affected");
      expect(plan.input.affected_document_id).toBeUndefined();
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("rejects affected_source_identity that is not a JSON object", () => {
    const root = mkdtempSync(join(tmpdir(), "kbprep-cli-batch-rerun-source-identity-"));
    try {
      const manifest = join(root, "batch_manifest.json");
      writeFileSync(manifest, "{}", "utf-8");
      const parsed = parseStandaloneArgs([
        "--rerun",
        "--batch-manifest",
        manifest,
        "--rerun-scope",
        "policy-affected",
        "--affected-document-id",
        "doc-123",
        "--affected-source-identity",
        '["not","an","object"]',
      ]);

      expect(() => buildCliPlan("prepare_batch", parsed.options)).toThrow(
        "--affected-source-identity must be",
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("maps feedback selective rerun node-ids option to a list", () => {
    const parsed = parseStandaloneArgs([
      "--plan-rerun",
      "--run-dir",
      ".kbprep/source/runs/run-1",
      "--node-ids",
      "n_000001,n_000003",
    ]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.command).toBe("feedback");
    expect(plan.input.plan_rerun).toBe(true);
    expect(plan.input.node_ids).toEqual(["n_000001", "n_000003"]);
  });

  it("leaves feedback node_ids undefined when the option is absent", () => {
    const parsed = parseStandaloneArgs(["--plan-rerun", "--run-dir", ".kbprep/source/runs/run-1"]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.input.node_ids).toBeUndefined();
  });

  it("maps feedback options to a proposal-only Python worker command", () => {
    const parsed = parseStandaloneArgs([
      "--run-dir",
      ".kbprep/source/runs/run-1",
      "--feedback-text",
      "下次删除「关注公众号」这种污染",
      "--rules-dir",
      ".kbprep/rules/user",
    ]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.command).toBe("feedback");
    expect(plan.input.run_dir).toContain(join(".kbprep", "source", "runs", "run-1"));
    expect(plan.input.feedback_text).toBe("下次删除「关注公众号」这种污染");
    expect(plan.input.scope).toBe("user");
    expect(plan.input.match).toBe("literal");
    expect(plan.input.rules_dir).toContain(join(".kbprep", "rules", "user"));
  });

  it("maps feedback proposal acceptance without requiring a run directory", () => {
    const parsed = parseStandaloneArgs([
      "--accept-proposal",
      "latest",
      "--confirm-rule-acceptance",
      "--rerun-after-accept",
      "--rules-dir",
      ".kbprep/rules/user",
    ]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.command).toBe("feedback");
    expect(plan.input.run_dir).toBeUndefined();
    expect(plan.input.accept_proposal).toBe("latest");
    expect(plan.input.confirm_rule_acceptance).toBe(true);
    expect(plan.input.rerun_after_accept).toBe(true);
    expect(plan.input.rules_dir).toContain(join(".kbprep", "rules", "user"));
  });

  it("maps feedback selective rerun planning options", () => {
    const parsed = parseStandaloneArgs([
      "--plan-rerun",
      "--accepted-proposal",
      "latest",
      "--rules-dir",
      ".kbprep/rules/user",
      "--target-rules-dir",
      ".kbprep/rules",
      "--document-type",
      "course",
    ]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.command).toBe("feedback");
    expect(plan.input.run_dir).toBeUndefined();
    expect(plan.input.plan_rerun).toBe(true);
    expect(plan.input.accepted_proposal).toBe("latest");
    expect(plan.input.rules_dir).toContain(join(".kbprep", "rules", "user"));
    expect(plan.input.target_rules_dir).toContain(join(".kbprep", "rules"));
    expect(plan.input.document_type).toBe("course");
  });

  it("maps feedback selective rerun execution options", () => {
    const parsed = parseStandaloneArgs([
      "--execute-rerun",
      "--accepted-proposal",
      "latest",
      "--rules-dir",
      ".kbprep/rules/user",
      "--target-rules-dir",
      ".kbprep/rules",
      "--document-type",
      "course",
    ]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.command).toBe("feedback");
    expect(plan.input.run_dir).toBeUndefined();
    expect(plan.input.execute_rerun).toBe(true);
    expect(plan.input.plan_rerun).toBe(false);
    expect(plan.input.accepted_proposal).toBe("latest");
    expect(plan.input.rules_dir).toContain(join(".kbprep", "rules", "user"));
    expect(plan.input.target_rules_dir).toContain(join(".kbprep", "rules"));
    expect(plan.input.document_type).toBe("course");
  });

  it("maps feedback proposal rejection without requiring a run directory", () => {
    const parsed = parseStandaloneArgs([
      "--reject-proposal",
      "latest",
      "--reject-reason",
      "这条只是当前文档案例，不要变成通用规则",
      "--rules-dir",
      ".kbprep/rules/user",
    ]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.command).toBe("feedback");
    expect(plan.input.run_dir).toBeUndefined();
    expect(plan.input.reject_proposal).toBe("latest");
    expect(plan.input.reject_reason).toBe("这条只是当前文档案例，不要变成通用规则");
    expect(plan.input.rules_dir).toContain(join(".kbprep", "rules", "user"));
  });

  it("maps feedback dictionary suggestions without requiring a run directory", () => {
    const parsed = parseStandaloneArgs(["--suggest-dictionary-updates", "--rules-dir", ".kbprep/rules/user", "--min-feedback-count", "2"]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.command).toBe("feedback");
    expect(plan.input.run_dir).toBeUndefined();
    expect(plan.input.suggest_dictionary_updates).toBe(true);
    expect(plan.input.min_feedback_count).toBe(2);
    expect(plan.input.rules_dir).toContain(join(".kbprep", "rules", "user"));
  });

  it("maps confirmed feedback dictionary promotion without requiring a run directory", () => {
    const parsed = parseStandaloneArgs([
      "--promote-dictionary-suggestion",
      "--confirm-dictionary-update",
      "--document-type",
      "course",
      "--rerun-after-promotion",
      "--allow-failed-promotion-history",
      "--confirm-public-write",
      "--representative-run-dir",
      ".kbprep/source/runs/run-1",
      "--rules-dir",
      ".kbprep/rules/user",
      "--target-rules-dir",
      "rules",
    ]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.command).toBe("feedback");
    expect(plan.input.run_dir).toBeUndefined();
    expect(plan.input.promote_dictionary_suggestion).toBe(true);
    expect(plan.input.confirm_dictionary_update).toBe(true);
    expect(plan.input.confirm_public_write).toBe(true);
    expect(plan.input.rerun_after_promotion).toBe(true);
    expect(plan.input.allow_failed_promotion_history).toBe(true);
    expect(plan.input.representative_run_dirs).toHaveLength(1);
    expect((plan.input.representative_run_dirs as string[])[0]).toContain(join(".kbprep", "source", "runs", "run-1"));
    expect(plan.input.document_type).toBe("course");
    expect(plan.input.rules_dir).toContain(join(".kbprep", "rules", "user"));
    expect(plan.input.target_rules_dir).toContain("rules");
  });

  it("keeps public dictionary promotion confirmation disabled by default", () => {
    const parsed = parseStandaloneArgs([
      "--promote-dictionary-suggestion",
      "--confirm-dictionary-update",
      "--document-type",
      "course",
      "--target-rules-dir",
      "rules",
    ]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.command).toBe("feedback");
    expect(plan.input.confirm_dictionary_update).toBe(true);
    expect(plan.input.confirm_public_write).toBe(false);
    expect(plan.input.target_rules_dir).toContain("rules");
  });

  it("maps promotion history summaries without requiring a run directory", () => {
    const parsed = parseStandaloneArgs(["--summarize-promotion-history", "--document-type", "course", "--target-rules-dir", "rules"]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.command).toBe("feedback");
    expect(plan.input.run_dir).toBeUndefined();
    expect(plan.input.summarize_promotion_history).toBe(true);
    expect(plan.input.document_type).toBe("course");
    expect(plan.input.target_rules_dir).toContain("rules");
  });

  it("maps promotion failure resolution without requiring a run directory", () => {
    const parsed = parseStandaloneArgs([
      "--resolve-promotion-failures",
      "--confirm-failure-resolved",
      "--document-type",
      "course",
      "--representative-run-dir",
      ".kbprep/source/runs/run-1",
      "--target-rules-dir",
      "rules",
    ]);
    const plan = buildCliPlan("feedback", parsed.options);

    expect(plan.command).toBe("feedback");
    expect(plan.input.run_dir).toBeUndefined();
    expect(plan.input.resolve_promotion_failures).toBe(true);
    expect(plan.input.confirm_failure_resolved).toBe(true);
    expect(plan.input.document_type).toBe("course");
    expect(plan.input.representative_run_dirs).toHaveLength(1);
    expect(plan.input.target_rules_dir).toContain("rules");
  });

  it("ships standalone bin entries in the npm package manifest", () => {
    const pkg = JSON.parse(readFileSync("package.json", "utf-8")) as {
      bin: Record<string, string>;
      scripts: Record<string, string>;
      peerDependencies?: Record<string, string>;
      peerDependenciesMeta?: Record<string, { optional?: boolean }>;
      openclaw?: unknown;
    };

    expect(pkg.bin["kbprep-preflight"]).toBe("dist/adapters/standalone/bin/preflight.js");
    expect(pkg.bin["kbprep-analyze"]).toBe("dist/adapters/standalone/bin/analyze.js");
    expect(pkg.bin["kbprep-prepare"]).toBe("dist/adapters/standalone/bin/prepare.js");
    expect(pkg.bin["kbprep-feedback"]).toBe("dist/adapters/standalone/bin/feedback.js");
    expect(pkg.scripts["pack:check"]).toBeDefined();
    expect(pkg.peerDependencies?.openclaw).toBeUndefined();
    expect(pkg.peerDependenciesMeta?.openclaw).toBeUndefined();
    expect(pkg.openclaw).toBeUndefined();
  });

  it("keeps the standalone adapter independent from host SDKs", () => {
    const source = readFileSync("src/adapters/standalone/cli.ts", "utf-8");

    expect(source).not.toContain("openclaw/plugin-sdk");
    expect(source).not.toMatch(/from\s+["']openclaw/);
  });
});
