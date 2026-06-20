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

describe("kbprep worker pipeline - batch and long documents part 2", () => {
  it("renders long documents into ordered parts that reconstruct cleaned markdown", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const sourcePath = path.join(inputDir, "long-guide.md");
      const chapters = Array.from({ length: 9 }, (_, index) => {
        const chapterNo = index + 1;
        const body = Array.from({ length: 18 }, (__, paragraphIndex) =>
          `第${chapterNo}章第${paragraphIndex + 1}段：这是一个教程正文段落，保留 LONG_PART_MARKER_${chapterNo}_${paragraphIndex + 1}。这里包含工具名 ExampleTool、参数 threshold=0.8、retry_count=3、失败原因、限制条件和复盘标准，不能被总结成概念。`,
        ).join("\n\n");
        return `# 第${chapterNo}章 长文档章节 ${chapterNo}\n\n${body}`;
      }).join("\n\n");
      writeFileSync(sourcePath, chapters, "utf8");

      const envelope = runWorker("prepare", {
        input_path: sourcePath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });

      const cleaned = normalizeMarkdownText(readFileSync(path.join(outputRoot, "cleaned.md"), "utf8"));
      const partsDir = path.join(outputRoot, "parts");
      const manifestPath = path.join(partsDir, "parts_manifest.json");
      const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as Array<{
        part_id: string;
        block_ids: string[];
        char_count: number;
      }>;
      const partFiles = readdirSync(partsDir).filter((name) => /^part_\d{3}\.md$/.test(name)).sort();
      const reconstructed = partFiles.map((name) => {
        const raw = readFileSync(path.join(partsDir, name), "utf8");
        return normalizeMarkdownText(raw.replace(/^---[\s\S]*?---\s*/, ""));
      }).join("\n\n").trim();

      expect(envelope.data.strict_errors).toEqual([]);
      expect(partFiles.length).toBeGreaterThan(1);
      expect(manifest.map((entry) => `${entry.part_id}.md`)).toEqual(partFiles);
      expect(manifest.every((entry) => entry.block_ids.length > 0 && entry.char_count > 0)).toBe(true);
      expect(reconstructed).toBe(cleaned);
      expect(cleaned.indexOf("LONG_PART_MARKER_1_1")).toBeLessThan(cleaned.indexOf("LONG_PART_MARKER_9_18"));
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }, 15_000);

  it("diagnoses text-layer, image-only, and PPT-like PDFs differently", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-worker-"));
    try {
      const outputRoot = path.join(root, "output");
      mkdirSync(outputRoot);
      const textPdf = path.join(root, "text-layer.pdf");
      const imagePdf = path.join(root, "image-only.pdf");
      const imagePath = path.join(root, "pixel.png");
      const slidePdf = path.join(root, "slide-export.pdf");
      const slideImagePath = path.join(root, "slide-pixel.png");
      const slideTextPdf = path.join(root, "slide-text-layer.pdf");
      const garbledPdf = path.join(root, "garbled-text-layer.pdf");

      makeTextLayerPdf(textPdf);
      makeImageOnlyPdf(imagePdf, imagePath);
      makeLandscapeImagePdf(slidePdf, slideImagePath);
      makeLandscapeTextPdf(slideTextPdf);
      makeGarbledTextLayerPdf(garbledPdf);

      const textDiag = runWorker("diagnose", {
        input_path: textPdf,
        output_root: outputRoot,
        source_type: "auto",
      });
      const imageDiag = runWorker("diagnose", {
        input_path: imagePdf,
        output_root: outputRoot,
        source_type: "auto",
      });
      const slideDiag = runWorker("diagnose", {
        input_path: slidePdf,
        output_root: outputRoot,
        source_type: "auto",
      });
      const slideTextDiag = runWorker("diagnose", {
        input_path: slideTextPdf,
        output_root: outputRoot,
        source_type: "auto",
      });
      const garbledDiag = runWorker("diagnose", {
        input_path: garbledPdf,
        output_root: outputRoot,
        source_type: "auto",
      });

      expect(textDiag.data.detected_format).toBe("pdf");
      expect(textDiag.data.source_type).toBe("pdf_like");
      expect(textDiag.data.pdf_subtype).toBe("text_layer");
      expect(textDiag.data.needs_ocr).toBe(false);
      expect(textDiag.data.text_pages).toBe(1);
      expect(textDiag.data.text_profile).toBe("tutorial");
      expect(textDiag.data.char_count).toBeGreaterThan(20);
      expect(textDiag.data.recommended_pipeline).toBe("pdf_text_layer");
      expect(textDiag.data.conversion_strategy).toBe("pdf_text_layer");
      expect(textDiag.data.split_strategy).toBe("content_structure");

      expect(imageDiag.data.detected_format).toBe("pdf");
      expect(imageDiag.data.source_type).toBe("pdf_like");
      expect(imageDiag.data.pdf_subtype).toBe("image_only_or_scanned");
      expect(imageDiag.data.needs_ocr).toBe(true);
      expect(imageDiag.data.image_pages).toBe(1);
      expect(imageDiag.data.text_pages).toBe(0);
      expect(imageDiag.data.conversion_strategy).toBe("mineru_ocr");

      expect(slideDiag.data.detected_format).toBe("pdf");
      expect(slideDiag.data.pdf_subtype).toBe("ppt_exported_or_scanned");
      expect(slideDiag.data.needs_ocr).toBe(true);
      expect(slideDiag.data.landscape_pages).toBe(3);
      expect(slideDiag.data.layout_profile).toBe("slide_deck_or_ppt_export");
      expect(slideDiag.data.conversion_strategy).toBe("mineru_ocr");
      expect(slideDiag.data.split_strategy).toBe("preserve_slide_or_page_order");

      expect(slideTextDiag.data.pdf_subtype).toBe("ppt_exported_text_layer");
      expect(slideTextDiag.data.needs_ocr).toBe(false);
      expect(slideTextDiag.data.layout_profile).toBe("slide_deck_or_ppt_export");
      expect(slideTextDiag.data.slide_like_score).toBeGreaterThanOrEqual(0.65);
      expect(slideTextDiag.data.average_text_chars_per_text_page).toBeGreaterThan(20);
      expect(slideTextDiag.data.recommended_pipeline).toBe("mineru_pipeline");
      expect(slideTextDiag.data.conversion_strategy).toBe("mineru_auto");
      expect(slideTextDiag.data.split_strategy).toBe("preserve_slide_or_page_order");
      expect(JSON.stringify(slideTextDiag.data.processing_hints)).toContain("complex visual layout");

      expect(garbledDiag.data.pdf_subtype).toBe("garbled_text_layer");
      expect(["bad", "degraded"]).toContain(garbledDiag.data.text_layer_health);
      expect(garbledDiag.data.needs_ocr).toBe(true);
      expect(garbledDiag.data.conversion_strategy).toBe("mineru_ocr");
      expect(JSON.stringify(garbledDiag.data.warnings)).toContain("W_PDF_TEXT_LAYER_UNTRUSTED");

      expect(textDiag.data.pdf_route_diagnostics.schema).toBe("kbprep.pdf_route_diagnostics.v1");
      expect(textDiag.data.pdf_route_diagnostics.text_layer.trusted).toBe(true);
      expect(textDiag.data.pdf_route_diagnostics.layout_complexity.level).toBe("simple");
      expect(textDiag.data.pdf_route_diagnostics.image_coverage.ratio).toBe(0);
      expect(textDiag.data.pdf_route_diagnostics.recommended_tier).toBe("tier_1");
      expect(textDiag.data.pdf_route_diagnostics.recommended_route).toBe("pymupdf4llm");

      expect(imageDiag.data.pdf_route_diagnostics.text_layer.trusted).toBe(false);
      expect(imageDiag.data.pdf_route_diagnostics.image_coverage.level).toBe("high");
      expect(imageDiag.data.pdf_route_diagnostics.ocr_triggers).toContain("high_image_coverage");
      expect(imageDiag.data.pdf_route_diagnostics.recommended_tier).toBe("tier_3");
      expect(imageDiag.data.pdf_route_diagnostics.recommended_route).toBe("mineru_ocr");

      expect(slideTextDiag.data.pdf_route_diagnostics.text_layer.trusted).toBe(true);
      expect(slideTextDiag.data.pdf_route_diagnostics.layout_complexity.level).toBe("complex");
      expect(slideTextDiag.data.pdf_route_diagnostics.structure_signals.slide_like).toBe(true);
      expect(slideTextDiag.data.pdf_route_diagnostics.recommended_tier).toBe("tier_2");
      expect(slideTextDiag.data.pdf_route_diagnostics.recommended_route).toBe("mineru_auto");

      expect(garbledDiag.data.pdf_route_diagnostics.text_layer.trusted).toBe(false);
      expect(garbledDiag.data.pdf_route_diagnostics.text_risk.cid_or_tounicode_risk).toBe(true);
      expect(garbledDiag.data.pdf_route_diagnostics.ocr_triggers).toContain("untrusted_text_layer");
      expect(garbledDiag.data.pdf_route_diagnostics.recommended_tier).toBe("tier_3");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
