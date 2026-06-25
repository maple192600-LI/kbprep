import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { repoRoot, runPython, runWorker } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - core/runtime part 2", () => {
  it("keeps shared format routing consistent across diagnose, prepare, detect, and batch", () => {
    runPython(
      [
        "from kbprep_worker.supported_formats import (",
        "    BATCH_SUPPORTED_EXTENSIONS, DIRECT_EXTENSIONS, FORMAT_BY_EXTENSION, MEDIA_EXTENSIONS, MINERU_EXTENSIONS,",
        "    CODE_EXTENSIONS, EPUB_EXTENSIONS, NOTEBOOK_EXTENSIONS, OFFICE_XML_EXTENSIONS, SOURCE_TYPE_BY_EXTENSION",
        ")",
        "from kbprep_worker import diagnose, detect, prepare, prepare_batch",
        "assert diagnose.EXTENSION_MAP is FORMAT_BY_EXTENSION",
        "assert prepare.DIRECT_EXTENSIONS is DIRECT_EXTENSIONS",
        "assert prepare.EPUB_EXTENSIONS is EPUB_EXTENSIONS",
        "assert prepare.MEDIA_EXTENSIONS is MEDIA_EXTENSIONS",
        "assert prepare.OFFICE_XML_EXTENSIONS is OFFICE_XML_EXTENSIONS",
        "assert prepare_batch.SUPPORTED_EXTENSIONS is BATCH_SUPPORTED_EXTENSIONS",
        "assert detect.EXTENSION_MAP is SOURCE_TYPE_BY_EXTENSION",
        "assert '.epub' in EPUB_EXTENSIONS",
        "assert '.epub' not in MINERU_EXTENSIONS",
        "assert '.pdf' in MINERU_EXTENSIONS",
        "assert '.py' in CODE_EXTENSIONS",
        "assert '.yaml' in CODE_EXTENSIONS",
        "assert '.ipynb' in NOTEBOOK_EXTENSIONS",
        "for ext in ['.json', '.html', '.csv', '.vtt', '.py', '.yaml', '.ipynb', '.docx', '.pptx', '.xlsx', '.epub']:",
        "    assert ext in FORMAT_BY_EXTENSION, ext",
        "    assert ext in BATCH_SUPPORTED_EXTENSIONS, ext",
        "for ext in ['.ogg', '.avi']:",
        "    assert ext in FORMAT_BY_EXTENSION, ext",
        "    assert ext in MEDIA_EXTENSIONS, ext",
        "    assert ext not in BATCH_SUPPORTED_EXTENSIONS, ext",
        "for ext in ['.doc', '.ppt', '.xls', '.png']:",
        "    assert ext in FORMAT_BY_EXTENSION, ext",
        "    assert ext not in MINERU_EXTENSIONS, ext",
        "    assert ext in BATCH_SUPPORTED_EXTENSIONS, ext",
        "for ext in ['.mobi']:",
        "    assert ext in FORMAT_BY_EXTENSION, ext",
        "    assert ext not in MINERU_EXTENSIONS, ext",
        "    assert ext not in BATCH_SUPPORTED_EXTENSIONS, ext",
      ].join("\n"),
      [],
    );
  });

  it("declares converter capabilities and exposes the chosen capability through diagnosis", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-capability-"));
    try {
      const sourcePath = path.join(root, "notes.md");
      writeFileSync(sourcePath, "# Notes\n\nKeep threshold=0.8.", "utf8");

      runPython(
        [
          "from kbprep_worker.converter_capabilities import capability_gap_report, get_capability_for_extension, capability_matrix_rows",
          "markdown = get_capability_for_extension('.md')",
          "pdf = get_capability_for_extension('.pdf')",
          "video = get_capability_for_extension('.mp4')",
          "assert markdown['route'] == 'direct_text', markdown",
          "assert markdown['status'] == 'verified', markdown",
          "assert markdown['test_evidence'], markdown",
          "assert 'headings' in markdown['preserves'], markdown",
          "assert pdf['route'] == 'pdf_diagnosis_selected', pdf",
          "assert pdf['status'] == 'verified', pdf",
          "assert pdf['test_evidence'], pdf",
          "assert video['route'] == 'media_to_transcript', video",
          "assert video['status'] == 'partial', video",
          "youtube = get_capability_for_extension('.url')",
          "assert youtube['id'] == 'youtube_url_routes', youtube",
          "assert youtube['route'] == 'youtube_subtitle_then_media_transcript', youtube",
          "assert youtube['status'] == 'partial', youtube",
          "rows = capability_matrix_rows()",
          "assert any(row['route'] == 'office_xml' and row['status'] == 'partial' for row in rows), rows",
          "for row in rows:",
          "    if row['status'] == 'verified':",
          "        assert row.get('test_evidence'), row",
          "gaps = capability_gap_report()",
          "assert gaps['schema'] == 'kbprep.capability_gap_report.v1', gaps",
          "assert gaps['summary']['partial'] >= 1, gaps",
          "assert gaps['summary']['unsupported'] >= 1, gaps",
          "by_id = {item['id']: item for item in gaps['gaps']}",
          "assert 'pdf_diagnosis_selected' not in by_id, by_id",
          "assert by_id['image_ocr']['current_status'] == 'experimental', by_id",
          "assert 'image_to_pdf' in by_id['image_ocr']['current_route'], by_id",
          "assert by_id['image_ocr']['required_evidence'], by_id",
        ].join("\n"),
        [],
      );

      const diagnosis = runWorker("diagnose", {
        input_path: sourcePath,
        output_root: root,
        source_type: "auto",
      });

      expect(diagnosis.ok).toBe(true);
      expect(diagnosis.data.capability.route).toBe("direct_text");
      expect(diagnosis.data.capability.status).toBe("verified");
      expect(diagnosis.data.capability.reason).toContain(".md");
      expect(diagnosis.data.capability.preserves).toContain("headings");
      expect(diagnosis.data.capability.test_evidence.length).toBeGreaterThan(0);

      const prepared = runWorker("prepare", {
        input_path: sourcePath,
        output_root: path.join(root, "output"),
        profile: "standard",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      expect(prepared.ok).toBe(true);
      const diagnosisReport = JSON.parse(readFileSync(path.join(prepared.data.run_dir, "diagnosis_report.json"), "utf8"));
      expect(diagnosisReport.capability.route).toBe("direct_text");
      expect(diagnosisReport.capability.status).toBe("verified");
      expect(diagnosisReport.capability.preserves).toContain("headings");
      expect(diagnosisReport.capability.test_evidence.length).toBeGreaterThan(0);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("proves optional media and YouTube routes with mocked golden fixtures", () => {
    runPython(
      [
        "import tempfile",
        "from pathlib import Path",
        "from kbprep_worker.converters.external_tools import ExternalCommandResult, extract_youtube_transcript, transcribe_media_with_whisper",
        "root = Path(tempfile.mkdtemp(prefix='kbprep-media-youtube-'))",
        "media = root / 'lesson.mp4'",
        "media.write_bytes(b'golden media placeholder')",
        "def media_runner(command, cwd, timeout_seconds):",
        "    if command[0] == 'ffmpeg': Path(command[-1]).write_bytes(b'wav')",
        "    if command[0] == 'whisper':",
        "        out = Path(command[-1]); out.mkdir(parents=True, exist_ok=True)",
        "        (out / 'lesson.txt').write_text('Step 1: keep threshold=0.8.\\n', encoding='utf-8')",
        "    return ExternalCommandResult(0, '', '')",
        "media_result = transcribe_media_with_whisper(media, root / 'media-run', which=lambda tool: tool, runner=media_runner)",
        "assert media_result.ok, media_result.report",
        "assert media_result.report['route_decision']['external_route'] == 'media_to_transcript', media_result.report",
        "def youtube_runner(command, cwd, timeout_seconds):",
        "    if '--dump-single-json' in command:",
        '        return ExternalCommandResult(0, \'{"subtitles":{"en":[{}]},"automatic_captions":{}}\', \'\')',
        "    if '--skip-download' in command:",
        "        out = Path(command[command.index('--output') + 1]); out.parent.mkdir(parents=True, exist_ok=True)",
        "        out.with_name(out.name + '.en.vtt').write_text('WEBVTT\\n\\n00:00:00.000 --> 00:00:02.000\\nKeep setup step threshold=0.8.\\n', encoding='utf-8')",
        "    return ExternalCommandResult(0, '', '')",
        "youtube_result = extract_youtube_transcript('https://www.youtube.com/watch?v=ExampleVideo01', root / 'youtube-run', which=lambda tool: tool, runner=youtube_runner)",
        "assert youtube_result.ok, youtube_result.report",
        "assert youtube_result.report['route_decision']['external_route'] == 'youtube_subtitle', youtube_result.report",
        "assert 'threshold=0.8' in youtube_result.artifact_path.read_text(encoding='utf-8')",
      ].join("\n"),
      [],
    );
  });

  it("diagnoses local external-converter formats and keeps MOBI explicitly unsupported", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-unverified-formats-"));
    try {
      const imagePath = path.join(root, "scan.png");
      const legacyDocPath = path.join(root, "legacy.doc");
      const mobiPath = path.join(root, "book.mobi");
      writeFileSync(imagePath, "not a real image", "utf8");
      writeFileSync(legacyDocPath, "legacy binary placeholder", "utf8");
      writeFileSync(mobiPath, "mobi placeholder", "utf8");

      const imageDiagnosis = runWorker("diagnose", {
        input_path: imagePath,
        output_root: path.join(root, "diagnose"),
        source_type: "auto",
      });
      expect(imageDiagnosis.ok).toBe(true);
      expect(imageDiagnosis.data.capability.status).toBe("experimental");
      expect(imageDiagnosis.data.recommended_pipeline).toBe("image_to_pdf_ocr");
      expect(imageDiagnosis.data.conversion_strategy).toBe("image_to_pdf_then_mineru_ocr");

      const legacyDiagnosis = runWorker("diagnose", {
        input_path: legacyDocPath,
        output_root: path.join(root, "diagnose"),
        source_type: "auto",
      });
      expect(legacyDiagnosis.ok).toBe(true);
      expect(legacyDiagnosis.data.capability.status).toBe("experimental");
      expect(legacyDiagnosis.data.recommended_pipeline).toBe("legacy_office_to_pdf");
      expect(legacyDiagnosis.data.conversion_strategy).toBe("legacy_office_to_pdf_route");

      for (const inputPath of [mobiPath]) {
        const diagnosis = runWorker("diagnose", {
          input_path: inputPath,
          output_root: path.join(root, "diagnose"),
          source_type: "auto",
        });
        expect(diagnosis.ok).toBe(true);
        expect(diagnosis.data.capability.status).toBe("unsupported");
        expect(diagnosis.data.recommended_pipeline).toBe("unsupported");
        expect(diagnosis.data.conversion_strategy).toBe("unsupported_extension");

        const prepared = runWorker(
          "prepare",
          {
            input_path: inputPath,
            output_root: path.join(root, "output"),
            profile: "standard",
            mode: "rules_only",
            language: "zh",
            force: true,
          },
          1,
        );
        expect(prepared.ok).toBe(false);
        expect(prepared.error.code).toBe("E_UNSUPPORTED_TYPE");
        expect(prepared.error.message).toContain("not supported by KBPrep's verified conversion routes");
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("validates the capability matrix against converter declarations", () => {
    const result = spawnSync(process.execPath, ["scripts/checks/capability-matrix.mjs"], {
      cwd: repoRoot,
      encoding: "utf8",
      env: {
        ...process.env,
        PYTHONUTF8: "1",
      },
      timeout: 30_000,
    });

    expect(result.status, result.stderr || result.stdout).toBe(0);
    const summary = JSON.parse(result.stdout.trim());
    expect(summary.checked).toBeGreaterThan(0);
    expect(summary.missing).toEqual([]);
  });

  it("keeps platform and marketing cleanup terms out of Python worker logic", () => {
    const result = spawnSync(process.execPath, ["scripts/checks/cleaning-hardcodes.mjs"], {
      cwd: repoRoot,
      encoding: "utf8",
      timeout: 30_000,
    });

    expect(result.status, result.stderr || result.stdout).toBe(0);
    const summary = JSON.parse(result.stdout.trim());
    expect(summary.violations).toEqual([]);
    expect(summary.checkedFiles).toBeGreaterThan(0);
  });

  it("detects escaped Chinese cleanup terms in raw Python string literals", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-hardcode-"));
    try {
      const workerDir = path.join(root, "python", "kbprep_worker");
      const rulesDir = path.join(root, "rules", "base");
      mkdirSync(workerDir, { recursive: true });
      mkdirSync(rulesDir, { recursive: true });
      writeFileSync(path.join(workerDir, "bad.py"), 'TITLE = r"\\u516c\\u4f17\\u53f7"\n', "utf8");
      writeFileSync(path.join(rulesDir, "obvious_noise.json"), JSON.stringify({ keyword_sets: {} }), "utf8");

      const result = spawnSync(
        process.execPath,
        ["scripts/checks/cleaning-hardcodes.mjs", "--repo-root", root, "--check", "python/kbprep_worker/bad.py", "--rules-root", "rules"],
        {
          cwd: repoRoot,
          encoding: "utf8",
          timeout: 30_000,
        },
      );

      expect(result.status).toBe(1);
      expect(result.stderr).toContain("公众号");
      expect(result.stderr).toContain("decoded_string");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("keeps runtime code agent-neutral instead of shipping named agent backends", () => {
    const result = spawnSync(process.execPath, ["scripts/checks/agent-neutral-runtime.mjs"], {
      cwd: repoRoot,
      encoding: "utf8",
      timeout: 30_000,
    });

    expect(result.status, result.stderr || result.stdout).toBe(0);
    const summary = JSON.parse(result.stdout.trim());
    expect(summary.violations).toEqual([]);
    expect(summary.checkedFiles).toBeGreaterThan(0);
  });

  it("returns a structured timeout error when MinerU conversion exceeds its subprocess budget", () => {
    runPython(
      [
        "import io, json, os, sys, tempfile",
        "from pathlib import Path",
        "from kbprep_worker import mineru_adapter, prepare",
        "root = Path(tempfile.mkdtemp(prefix='kbprep-timeout-'))",
        "input_path = root / 'slow.pdf'",
        "output_root = root / 'out'",
        "input_path.write_bytes(b'%PDF-1.4\\n% fake pdf for timeout path')",
        "os.environ['KBPREP_MINERU_TIMEOUT_SECONDS'] = '45'",
        "assert mineru_adapter.mineru_timeout_seconds() == 45",
        "def fake_run_mineru(**kwargs):",
        "    raise TimeoutError('MinerU timed out after 45s processing slow.pdf')",
        "mineru_adapter.run_mineru = fake_run_mineru",
        "stdout = io.StringIO()",
        "old_stdout = sys.stdout",
        "try:",
        "    sys.stdout = stdout",
        "    try:",
        "        prepare.run({",
        "        'input_path': str(input_path),",
        "        'output_root': str(output_root),",
        "        'profile': 'lite',",
        "        'mode': 'rules_only',",
        "        'language': 'zh',",
        "        'force': True,",
        "        })",
        "    except SystemExit as exc:",
        "        assert exc.code == 1, exc.code",
        "finally:",
        "    sys.stdout = old_stdout",
        "payload = json.loads(stdout.getvalue())",
        "assert payload['ok'] is False, payload",
        "assert payload['error']['code'] == 'E_TIMEOUT', payload",
        "details = payload['error']['details']",
        "assert details['mineru_timeout_seconds'] == 45, details",
        "error_report = Path(details['error_report'])",
        "assert error_report.exists(), details",
        "report = json.loads(error_report.read_text(encoding='utf-8'))",
        "assert report['code'] == 'E_TIMEOUT', report",
        "assert report['original_file'], report",
        "assert report['diagnosis']['detected_format'] == 'pdf', report",
      ].join("\n"),
      [],
    );
  });

  it("does not reuse an existing run created by a different runtime", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-runtime-cache-"));
    try {
      runPython(
        [
          "import json, sys",
          "from pathlib import Path",
          "from kbprep_worker.prepare import _find_existing_run",
          "root = Path(sys.argv[1])",
          "run_dir = root / 'runs' / 'old_run'",
          "run_dir.mkdir(parents=True, exist_ok=True)",
          "(run_dir / 'quality_report.json').write_text(json.dumps({",
          "    'source_sha256': 'abc',",
          "    'config_hash': 'cfg',",
          "    'plugin_version': '0.4.0',",
          "    'runtime_cache_key': 'cpu-runtime'",
          "}), encoding='utf-8')",
          "assert _find_existing_run(root, 'abc', 'cfg', '0.4.0', 'gpu-runtime') is None",
          "match = _find_existing_run(root, 'abc', 'cfg', '0.4.0', 'cpu-runtime')",
          "assert match and match['run_id'] == 'old_run'",
        ].join("\n"),
        [root],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("prunes old run history by age during keep_latest artifact retention", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-retention-age-"));
    try {
      runPython(
        [
          "import os, time, sys",
          "from pathlib import Path",
          "from kbprep_worker.prepare import _apply_artifact_policy",
          "root = Path(sys.argv[1])",
          "runs = root / 'runs'",
          "current = runs / 'current'",
          "recent = runs / 'recent'",
          "old = runs / 'old'",
          "for path in [current, recent, old]:",
          "    path.mkdir(parents=True, exist_ok=True)",
          "    (path / 'marker.txt').write_text(path.name, encoding='utf-8')",
          "now = time.time()",
          "os.utime(recent, (now - 3600, now - 3600))",
          "os.utime(old, (now - 10 * 86400, now - 10 * 86400))",
          "_apply_artifact_policy(root, current, 'keep_latest')",
          "assert current.exists(), 'current run should remain'",
          "assert recent.exists(), 'recent run should remain'",
          "assert not old.exists(), 'old run should be pruned by age'",
        ].join("\n"),
        [root],
      );
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
