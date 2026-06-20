import { existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runStandaloneCli } from "../../adapters/standalone/cli.js";
import { runWorker } from "../helpers/workerHarness.js";

describe("kbprep worker pipeline - feedback standalone CLI", () => {
  it("refuses proposal acceptance without explicit confirmation", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-feedback-cli-confirm-"));
    try {
      const runDir = path.join(root, "run");
      const rulesDir = path.join(root, "rules", "user");
      mkdirSync(runDir, { recursive: true });

      const proposed = runWorker("feedback", {
        run_dir: runDir,
        rules_dir: rulesDir,
        feedback_text: "以后删除「内部训练营限时招募」这种污染",
        counterexamples: ["正文段落"],
      });

      const cliResult = await runStandaloneCli("feedback", [
        "--rules-dir",
        rulesDir,
        "--accept-proposal",
        proposed.data.proposal.id,
      ]);
      const envelope = JSON.parse(cliResult.output);

      expect(cliResult.exitCode).toBe(1);
      expect(envelope.ok).toBe(false);
      expect(envelope.error.code).toBe("E_CONFIRMATION_REQUIRED");
      expect(existsSync(path.join(rulesDir, "accepted_rules.jsonl"))).toBe(false);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
