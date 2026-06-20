import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const maxScenarioFileLines = 400;

function lineCount(filePath: string): number {
  return readFileSync(filePath, "utf8").split(/\r?\n/).length;
}

describe("test suite structure", () => {
  it("keeps worker scenarios split into focused files", () => {
    const legacyPath = path.join("src", "test", "fixtures", "workerScenarios.ts");
    const scenarioDir = path.join("src", "test", "scenarios");
    const scenarioFiles = existsSync(scenarioDir)
      ? readdirSync(scenarioDir).filter((name) => name.endsWith(".test.ts"))
      : [];

    expect(scenarioFiles.length).toBeGreaterThanOrEqual(8);
    if (existsSync(legacyPath)) {
      expect(lineCount(legacyPath)).toBeLessThanOrEqual(maxScenarioFileLines);
    }
    for (const file of scenarioFiles) {
      expect(lineCount(path.join(scenarioDir, file)), file).toBeLessThanOrEqual(maxScenarioFileLines);
    }
  });
});
