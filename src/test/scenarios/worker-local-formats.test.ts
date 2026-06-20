import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  makeEpubFixture,
  makeGarbledTextLayerPdf,
  makeImageOnlyPdf,
  makeLandscapeImagePdf,
  makeLandscapeTextPdf,
  makeOfficeFixtures,
  makeTextLayerPdf,
  normalizeMarkdownText,
  parseEnvelope,
  repoRoot,
  runPython,
  runPythonJson,
  runWorker,
  runWorkerRawInput,
} from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - local formats", () => {
  it("converts modern Office files through the local XML fallback when MinerU is unnecessary", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-office-"));
    try {
      const inputDir = path.join(root, "input");
      mkdirSync(inputDir);
      const docxPath = path.join(inputDir, "tutorial.docx");
      const pptxPath = path.join(inputDir, "slides.pptx");
      const xlsxPath = path.join(inputDir, "params.xlsx");
      makeOfficeFixtures(docxPath, pptxPath, xlsxPath);

      const cases = [
        {
          input: docxPath,
          out: path.join(root, "docx-out"),
          format: "docx",
          expected: [
            "# DOCX Tutorial",
            "threshold=0.8",
            "## Embedded Images",
            "![DOCX Image 1](images/office/docx/doc-step.png)",
            "| Field | Value |",
            "| retry_count | 3 |",
          ],
        },
        {
          input: pptxPath,
          out: path.join(root, "pptx-out"),
          format: "pptx",
          expected: [
            "# Slide 1: PPT Tutorial Slide",
            "failure_reason=timeout",
            "![Slide 1 Image 1](images/office/slide_001/step.png)",
            "# Slide 2: PPT Case Slide",
            "retry_count=3",
          ],
        },
        {
          input: xlsxPath,
          out: path.join(root, "xlsx-out"),
          format: "xlsx",
          expected: ["# Params", "| Name | Value |", "| threshold | 0.8 |"],
        },
      ];

      for (const item of cases) {
        const diagnosis = runWorker("diagnose", {
          input_path: item.input,
          output_root: item.out,
          source_type: "auto",
        });
        expect(diagnosis.data.detected_format).toBe(item.format);
        expect(diagnosis.data.recommended_pipeline).toBe("office_xml");
        expect(diagnosis.data.conversion_strategy).toBe("office_xml");

        const envelope = runWorker("prepare", {
          input_path: item.input,
          output_root: item.out,
          profile: "tutorial",
          mode: "rules_only",
          language: "zh",
          force: true,
        });
        const converted = readFileSync(path.join(envelope.data.run_dir, "converted.md"), "utf8");
        const cleaned = readFileSync(path.join(envelope.data.run_dir, "cleaned.md"), "utf8");
        const diagnosisReport = JSON.parse(readFileSync(path.join(envelope.data.run_dir, "diagnosis_report.json"), "utf8"));
        const conversionReport = JSON.parse(readFileSync(path.join(envelope.data.run_dir, "conversion_report.json"), "utf8"));

        expect(envelope.data.strict_errors).toEqual([]);
        expect(envelope.data.outputs.diagnosis_report).toContain("diagnosis_report.json");
        expect(envelope.data.latest_outputs.diagnosis_report).toContain("diagnosis_report.json");
        expect(diagnosisReport.schema).toBe("kbprep.diagnosis_report.v1");
        expect(diagnosisReport.detected_format).toBe(item.format);
        expect(diagnosisReport.recommended_pipeline).toBe("office_xml");
        expect(conversionReport.converter).toBe("office_xml");
        expect(conversionReport.diagnosed_format).toBe(item.format);
        expect(conversionReport.diagnosed_pipeline).toBe("office_xml");
        expect(conversionReport.diagnosed_strategy).toBe("office_xml");
        if (item.format === "docx") {
          expect(conversionReport.mineru_artifacts.office_image_assets.copied_count).toBe(1);
          expect(existsSync(path.join(item.out, "images", "office", "docx", "doc-step.png"))).toBe(true);
        }
        if (item.format === "pptx") {
          expect(conversionReport.diagnosed_split_strategy).toBe("preserve_slide_or_page_order");
          expect(conversionReport.mineru_artifacts.content_list_path).toContain("pptx_content_list.json");
          const manifest = readFileSync(path.join(envelope.data.run_dir, "chunk_manifest.jsonl"), "utf8")
            .trim()
            .split(/\r?\n/)
            .map((line) => JSON.parse(line));
          expect(manifest.map((entry) => entry.split_strategy)).toContain("preserve_slide_or_page_order");
          expect(manifest.some((entry) => entry.page_start === 0)).toBe(true);
          expect(manifest.some((entry) => entry.page_start === 1)).toBe(true);
          expect(conversionReport.mineru_artifacts.office_image_assets.copied_count).toBe(1);
          expect(existsSync(path.join(item.out, "images", "office", "slide_001", "step.png"))).toBe(true);
        }
        for (const expected of item.expected) {
          expect(converted).toContain(expected);
          expect(cleaned).toContain(expected);
        }
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 30_000);

  it("converts EPUB ebooks through local XHTML extraction instead of MinerU", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-epub-"));
    try {
      const inputDir = path.join(root, "input");
      mkdirSync(inputDir);
      const epubPath = path.join(inputDir, "tutorial.epub");
      const outputRoot = path.join(root, "output");
      makeEpubFixture(epubPath);

      const diagnosis = runWorker("diagnose", {
        input_path: epubPath,
        output_root: outputRoot,
        source_type: "auto",
      });
      expect(diagnosis.data.detected_format).toBe("ebook");
      expect(diagnosis.data.recommended_pipeline).toBe("epub_xhtml");
      expect(diagnosis.data.conversion_strategy).toBe("epub_xhtml");

      const envelope = runWorker("prepare", {
        input_path: epubPath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        source_type: "auto",
        force: true,
      });

      expect(envelope.ok).toBe(true);
      expect(envelope.data.strict_errors).toEqual([]);
      const converted = readFileSync(path.join(outputRoot, "converted.md"), "utf8");
      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const discarded = readFileSync(path.join(outputRoot, "discarded.md"), "utf8");
      const conversionReport = JSON.parse(readFileSync(path.join(outputRoot, "conversion_report.json"), "utf8"));

      expect(conversionReport.converter).toBe("epub_xhtml");
      expect(conversionReport.diagnosed_strategy).toBe("epub_xhtml");
      expect(converted).toContain("[open tool](https://example.com/epub-tool)");
      expect(converted).toContain("![EPUB screenshot](images/epub/OEBPS/images/step.png)");
      expect(conversionReport.mineru_artifacts.epub_image_assets.copied_count).toBe(1);
      expect(existsSync(path.join(outputRoot, "images", "epub", "OEBPS", "images", "step.png"))).toBe(true);
      expect(converted.indexOf("# 第一章 工具准备")).toBeLessThan(converted.indexOf("# 第二章 案例复盘"));
      expect(cleaned).toContain("threshold=0.8");
      expect(cleaned).toContain("failure_reason=timeout");
      expect(cleaned).toContain("retry_count=3");
      expect(cleaned).not.toContain("扫码加入社群领取体验卡");
      expect(discarded).toContain("扫码加入社群领取体验卡");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 30_000);

  it("converts trusted text-layer PDFs without invoking MinerU", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-pdf-text-"));
    try {
      const inputPath = path.join(root, "tutorial.pdf");
      const outputRoot = path.join(root, "output");
      makeTextLayerPdf(inputPath);

      const envelope = runWorker("prepare", {
        input_path: inputPath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        source_type: "auto",
        force: true,
      });

      expect(envelope.ok).toBe(true);
      const converted = readFileSync(path.join(outputRoot, "converted.md"), "utf8");
      expect(converted).toContain("Step 1: open settings and set threshold to 0.8.");
      expect(converted).toContain("retry_count values");

      const conversionReport = JSON.parse(readFileSync(path.join(outputRoot, "conversion_report.json"), "utf8"));
      expect(conversionReport.converter).toBe("pdf_text_layer");
      expect(conversionReport.diagnosed_strategy).toBe("pdf_text_layer");
      expect(conversionReport.route_decision.declared_route).toBe("pdf_diagnosis_selected");
      expect(conversionReport.route_decision.diagnosed_strategy).toBe("pdf_text_layer");
      expect(conversionReport.route_decision.actual_converter).toBe("pdf_text_layer");
      expect(conversionReport.route_decision.actual_route).toBe("pdf_text_layer");
      expect(conversionReport.route_decision.fallback_applied).toBe(false);
      expect(conversionReport.mineru_artifacts.source_md_path).toContain("converted.md");
      expect(conversionReport.mineru_artifacts.content_list_path).toContain("pdf_text_content_list.json");

      const blocks = readFileSync(path.join(outputRoot, "blocks.jsonl"), "utf8")
        .trim()
        .split(/\r?\n/)
        .map((line) => JSON.parse(line));
      const stepBlock = blocks.find((block) => block.text.includes("threshold to 0.8"));
      expect(stepBlock.page_start).toBe(0);
      expect(stepBlock.page_end).toBe(0);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 10_000);

});
