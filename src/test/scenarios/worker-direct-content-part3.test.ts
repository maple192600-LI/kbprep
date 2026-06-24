import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runWorker } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - direct content conversion part 3", () => {
  it("converts Jupyter notebooks into readable Markdown cells with code and text outputs", () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-notebook-"));
    try {
      const inputDir = path.join(root, "input");
      const outputRoot = path.join(root, "output");
      mkdirSync(inputDir);
      mkdirSync(outputRoot);
      const notebookPath = path.join(inputDir, "tutorial.ipynb");
      writeFileSync(
        notebookPath,
        JSON.stringify({
          cells: [
            {
              cell_type: "markdown",
              source: ["# Notebook 教程\n", "步骤1：配置 threshold=0.82，参考 https://example.com/notebook\n"],
            },
            {
              cell_type: "code",
              source: ["retry_count = 3\n", "failure_reason = 'timeout'\n", "print(failure_reason)\n"],
              outputs: [
                { output_type: "stream", name: "stdout", text: ["timeout\n"] },
                { output_type: "execute_result", data: { "text/plain": ["{'status': 'review'}"] } },
              ],
            },
          ],
          metadata: { kernelspec: { language: "python", name: "python3" } },
          nbformat: 4,
          nbformat_minor: 5,
        }),
        "utf8",
      );

      const diagnosis = runWorker("diagnose", {
        input_path: notebookPath,
        output_root: outputRoot,
        source_type: "auto",
      });
      expect(diagnosis.ok).toBe(true);
      expect(diagnosis.data.detected_format).toBe("notebook");
      expect(diagnosis.data.recommended_pipeline).toBe("direct");
      expect(diagnosis.data.conversion_strategy).toBe("notebook_json");

      const prepared = runWorker("prepare", {
        input_path: notebookPath,
        output_root: outputRoot,
        profile: "tutorial",
        mode: "rules_only",
        language: "zh",
        force: true,
      });
      expect(prepared.ok).toBe(true);

      const converted = readFileSync(path.join(outputRoot, "converted.md"), "utf8");
      const cleaned = readFileSync(path.join(outputRoot, "cleaned.md"), "utf8");
      const quality = JSON.parse(readFileSync(path.join(outputRoot, "quality_report.json"), "utf8"));
      const conversionReport = JSON.parse(readFileSync(path.join(outputRoot, "conversion_report.json"), "utf8"));

      expect(converted).toContain("# Notebook 教程");
      expect(converted).toContain("```python");
      expect(converted).toContain("retry_count = 3");
      expect(converted).toContain("## Cell 2 Output");
      expect(converted).toContain("timeout");
      expect(converted).toContain("{'status': 'review'}");
      expect(cleaned).toContain("failure_reason = 'timeout'");
      expect(quality.strict_errors).toEqual([]);
      expect(quality.detail_retention.parameter.total_blocks).toBeGreaterThan(0);
      expect(quality.output_retention.cleaned_md.parameter.missing_count).toBe(0);
      expect(conversionReport.converter).toBe("notebook_json");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
