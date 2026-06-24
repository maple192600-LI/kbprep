import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  runPython,
  runWorker,
} from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - batch and long documents part 1", () => {
  it("writes separate direct-use outputs for each file in a batch", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      writeFileSync(
        path.join(inputDir, "alpha.md"),
        [
          "# Alpha 教程",
          "",
          "第一步：保留 ALPHA_UNIQUE_MARKER，并记录参数 threshold=0.8。",
          "",
          "第二步：保留失败经验和限制条件，方便后续复盘。",
        ].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(inputDir, "beta.md"),
        [
          "# Beta 教程",
          "",
          "第一步：保留 BETA_UNIQUE_MARKER，并记录参数 retry_count=3。",
          "",
          "第二步：保留操作步骤和判断标准，不能总结成一句话。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare_batch", {
        input_dir: inputDir,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
        convert_jobs: 1,
      });

      const results = envelope.data.results as Array<{
        file: string;
        latest_outputs: { cleaned_md: string };
        batch_final_md?: string;
      }>;
      const cleanedDirs = new Set(results.map((result) => path.dirname(result.latest_outputs.cleaned_md)));

      expect(envelope.data.failed).toBe(0);
      expect(results).toHaveLength(2);
      expect(cleanedDirs.size).toBe(2);

      const alpha = results.find((result) => result.file === "alpha.md");
      const beta = results.find((result) => result.file === "beta.md");
      expect(alpha).toBeDefined();
      expect(beta).toBeDefined();

      const alphaCleaned = readFileSync(alpha!.latest_outputs.cleaned_md, "utf8");
      const betaCleaned = readFileSync(beta!.latest_outputs.cleaned_md, "utf8");
      expect(alphaCleaned).toContain("ALPHA_UNIQUE_MARKER");
      expect(alphaCleaned).not.toContain("BETA_UNIQUE_MARKER");
      expect(betaCleaned).toContain("BETA_UNIQUE_MARKER");
      expect(betaCleaned).not.toContain("ALPHA_UNIQUE_MARKER");
      expect(alpha!.batch_final_md).toBe(path.join(inputDir, "alpha.cleaned.md"));
      expect(beta!.batch_final_md).toBe(path.join(inputDir, "beta.cleaned.md"));
      expect(readFileSync(path.join(inputDir, "alpha.cleaned.md"), "utf8")).toContain("ALPHA_UNIQUE_MARKER");
      expect(readFileSync(path.join(inputDir, "beta.cleaned.md"), "utf8")).toContain("BETA_UNIQUE_MARKER");
      const manifest = JSON.parse(readFileSync(envelope.data.batch_manifest_json, "utf8"));
      expect(manifest.status).toBe("completed");
      expect(manifest.summary.failed).toBe(0);
      expect(manifest.summary.skipped_unsupported).toBe(0);
      expect(existsSync(path.join(outputRoot, "progress.json"))).toBe(true);
      expect(existsSync(path.join(outputRoot, "failures.json"))).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 15_000);

  it("records and finalizes curated Obsidian batch deliverables", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-curated-batch-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      writeFileSync(
        path.join(inputDir, "alpha.md"),
        [
          "# Alpha 方法",
          "",
          "第一步：保留 ALPHA_CURATED_MARKER，并设置 threshold=0.8。",
          "",
          "第二步：把操作流程写成可复盘 SOP。",
        ].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(inputDir, "beta.md"),
        [
          "# Beta 案例",
          "",
          "第一步：保留 BETA_CURATED_MARKER，并记录 retry_count=3。",
          "",
          "第二步：保留案例里的判断标准和失败原因。",
        ].join("\n"),
        "utf8",
      );

      const envelope = runWorker("prepare_batch", {
        input_dir: inputDir,
        output_root: outputRoot,
        profile: "curated_obsidian_kb",
        mode: "rules_only",
        language: "zh",
        force: true,
        convert_jobs: 1,
      });

      const results = envelope.data.results as Array<{
        file: string;
        final_artifact_type: string;
        batch_final_md?: string;
        batch_obsidian_dir?: string;
        batch_obsidian_index?: string;
        latest_outputs: {
          final_md: string | null;
          final_artifact_type: string;
          obsidian_dir: string;
          obsidian_index: string;
        };
      }>;

      expect(envelope.data.failed).toBe(0);
      expect(results).toHaveLength(2);
      for (const result of results) {
        expect(result.final_artifact_type).toBe("obsidian_dir");
        expect(result.latest_outputs.final_artifact_type).toBe("obsidian_dir");
        expect(result.latest_outputs.final_md).toBe(null);
        expect(result.batch_final_md).toBeUndefined();
        expect(result.batch_obsidian_dir).toBe(result.latest_outputs.obsidian_dir);
        expect(result.batch_obsidian_index).toBe(result.latest_outputs.obsidian_index);
        expect(existsSync(result.batch_obsidian_index!)).toBe(true);
      }

      const cleanup = runWorker("cleanup", {
        output_root: outputRoot,
        action: "finalize",
      });

      expect(cleanup.ok).toBe(true);
      const manifest = JSON.parse(readFileSync(path.join(outputRoot, "kbprep_batch_manifest.json"), "utf8"));
      expect(manifest.total_finalized).toBe(2);
      for (const entry of manifest.finalized) {
        expect(entry.final_artifact_type).toBe("obsidian_dir");
        expect(existsSync(entry.obsidian_dir)).toBe(true);
        expect(existsSync(entry.obsidian_index)).toBe(true);
      }
      expect(existsSync(path.join(outputRoot, "results.json"))).toBe(false);
      expect(existsSync(path.join(outputRoot, "progress.json"))).toBe(false);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 15_000);

  it("writes a batch inventory for unsupported local files instead of silently ignoring them", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-batch-inventory-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      writeFileSync(
        path.join(inputDir, "alpha.md"),
        ["# Alpha", "", "步骤1：保留 ALPHA_BATCH_MARKER，设置 threshold=0.8。"].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(inputDir, "repo.py"),
        ["retry_count = 3", "failure_reason = 'timeout'"].join("\n"),
        "utf8",
      );
      writeFileSync(path.join(inputDir, "lesson.mp4"), "not a real video", "utf8");
      writeFileSync(path.join(inputDir, "archive.bin"), "unknown local file", "utf8");

      const envelope = runWorker("prepare_batch", {
        input_dir: inputDir,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
        convert_jobs: 1,
      });

      const inventoryPath = envelope.data.batch_inventory_json;
      const inventory = JSON.parse(readFileSync(inventoryPath, "utf8")) as {
        files: Array<{ file: string; action: string; reason?: string; detected_format?: string }>;
      };

      expect(envelope.data.total).toBe(2);
      expect(envelope.data.discovered_total).toBe(4);
      expect(envelope.data.skipped_unsupported).toBe(2);
      expect(envelope.data.failed).toBe(0);
      expect(inventory.files.find((item) => item.file === "alpha.md")?.action).toBe("process");
      expect(inventory.files.find((item) => item.file === "repo.py")?.detected_format).toBe("code");
      expect(inventory.files.find((item) => item.file === "lesson.mp4")?.reason).toContain("media_binary_not_transcribed");
      expect(inventory.files.find((item) => item.file === "archive.bin")?.reason).toContain("unsupported_extension");
      expect(envelope.data.results.map((result: { file: string }) => result.file).sort()).toEqual(["alpha.md", "repo.py"]);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 15_000);

  it("recursively processes useful nested source files while skipping noisy project directories", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-recursive-batch-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(path.join(inputDir, "docs"), { recursive: true });
      mkdirSync(path.join(inputDir, "examples"), { recursive: true });
      mkdirSync(path.join(inputDir, "node_modules", "noise"), { recursive: true });
      mkdirSync(outputRoot);
      writeFileSync(
        path.join(inputDir, "docs", "guide.md"),
        ["# GitHub Guide", "", "步骤1：保留 GITHUB_DOC_MARKER，并设置 threshold=0.8。"].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(inputDir, "examples", "script.py"),
        ["retry_count = 3", "failure_reason = 'timeout'"].join("\n"),
        "utf8",
      );
      writeFileSync(
        path.join(inputDir, "node_modules", "noise", "ad.md"),
        "# Dependency noise\n\nSHOULD_NOT_BE_PROCESSED",
        "utf8",
      );

      const envelope = runWorker("prepare_batch", {
        input_dir: inputDir,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
        convert_jobs: 1,
      });

      const inventory = JSON.parse(readFileSync(envelope.data.batch_inventory_json, "utf8")) as {
        discovered_total: number;
        files: Array<{ file: string; relative_path: string; action: string; detected_format?: string }>;
      };
      const results = envelope.data.results as Array<{
        file: string;
        relative_path: string;
        latest_outputs: { cleaned_md: string };
      }>;

      expect(envelope.data.failed).toBe(0);
      expect(envelope.data.total).toBe(2);
      expect(inventory.discovered_total).toBe(2);
      expect(inventory.files.map((item) => item.relative_path).sort()).toEqual([
        "docs/guide.md",
        "examples/script.py",
      ]);
      expect(results.map((item) => item.relative_path).sort()).toEqual([
        "docs/guide.md",
        "examples/script.py",
      ]);
      expect(readFileSync(results.find((item) => item.relative_path === "docs/guide.md")!.latest_outputs.cleaned_md, "utf8"))
        .toContain("GITHUB_DOC_MARKER");
      expect(results.some((item) => item.relative_path.includes("node_modules"))).toBe(false);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 15_000);

  it("runs heavy batch conversion files serially even when convert_jobs is greater than one", () => {
    runPython(
      [
        "import io, json, sys, tempfile, threading, time",
        "from pathlib import Path",
        "from kbprep_worker import prepare_batch",
        "root = Path(tempfile.mkdtemp(prefix='kbprep-heavy-batch-'))",
        "input_dir = root / 'input'",
        "output_root = root / 'output'",
        "input_dir.mkdir()",
        "output_root.mkdir()",
        "(input_dir / '00-sample.md').write_text('# Sample\\n\\n步骤1：保留样本。', encoding='utf-8')",
        "(input_dir / '01-heavy.pdf').write_bytes(b'%PDF-1.4 heavy one')",
        "(input_dir / '02-heavy.pdf').write_bytes(b'%PDF-1.4 heavy two')",
        "(input_dir / '03-heavy.png').write_bytes(b'png')",
        "(input_dir / '04-heavy.doc').write_bytes(b'doc')",
        "(input_dir / '03-note.md').write_text('# Note\\n\\n步骤1：轻文本。', encoding='utf-8')",
        "lock = threading.Lock()",
        "active_heavy = 0",
        "max_active_heavy = 0",
        "calls = []",
        "def fake_process_one_file(file_path, output_root, profile, language, mode, force, artifact_policy='keep_latest', max_quality_iterations=None):",
        "    global active_heavy, max_active_heavy",
        "    suffix = Path(file_path).suffix.lower()",
        "    calls.append(Path(file_path).name)",
        "    if suffix in {'.pdf', '.png', '.doc', '.ppt', '.xls'}:",
        "        with lock:",
        "            active_heavy += 1",
        "            max_active_heavy = max(max_active_heavy, active_heavy)",
        "        time.sleep(0.08)",
        "        with lock:",
        "            active_heavy -= 1",
        "    return {'ok': True, 'data': {'run_id': Path(file_path).stem, 'strict_errors': [], 'latest_outputs': {'cleaned_md': str(Path(output_root) / 'cleaned.md')}}}",
        "prepare_batch._process_one_file = fake_process_one_file",
        "stdout = io.StringIO()",
        "old_stdout = sys.stdout",
        "try:",
        "    sys.stdout = stdout",
        "    try:",
        "        prepare_batch.run({",
        "            'input_dir': str(input_dir),",
        "            'output_root': str(output_root),",
        "            'profile': 'standard',",
        "            'mode': 'rules_only',",
        "            'language': 'zh',",
        "            'force': True,",
        "            'convert_jobs': 3,",
        "        })",
        "    except SystemExit:",
        "        pass",
        "finally:",
        "    sys.stdout = old_stdout",
        "payload = json.loads(stdout.getvalue())",
        "assert payload['ok'] is True, payload",
        "assert max_active_heavy == 1, {'max_active_heavy': max_active_heavy, 'calls': calls}",
        "assert payload['data']['heavy_conversion_files'] == 4, payload",
        "assert payload['data']['heavy_conversion_concurrency'] == 1, payload",
      ].join("\n"),
      [],
    );
  });

});
