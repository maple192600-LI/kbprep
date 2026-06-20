import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { runManagedProcess, ManagedProcessTimeoutError } from "./subprocess.js";

describe("managed subprocess timeout behavior", () => {
  it("returns stdout and stderr for successful commands", async () => {
    const result = await runManagedProcess({
      command: process.execPath,
      args: ["-e", "process.stdout.write('ok'); process.stderr.write('note')"],
      label: "test success",
      timeoutMs: 5_000,
    });

    expect(result.code).toBe(0);
    expect(result.stdout).toBe("ok");
    expect(result.stderr).toBe("note");
    expect(result.timedOut).toBe(false);
  });

  it("waits for close after timeout and reports stderr tail with timing details", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-subprocess-timeout-"));
    const scriptPath = path.join(root, "slow.mjs");
    writeFileSync(scriptPath, [
      "process.stderr.write('before-timeout\\n');",
      "setInterval(() => {}, 1000);",
    ].join("\n"), "utf8");

    try {
      await expect(runManagedProcess({
        command: process.execPath,
        args: [scriptPath],
        label: "test timeout",
        timeoutMs: 100,
        terminateGraceMs: 100,
      })).rejects.toMatchObject({
        name: "ManagedProcessTimeoutError",
        timeoutMs: 100,
        stderrTail: expect.stringContaining("before-timeout"),
      });
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("exposes a typed timeout error", () => {
    const error = new ManagedProcessTimeoutError("label", 123, {
      code: null,
      signal: "SIGTERM",
      stderr: "line",
    });

    expect(error.timeoutMs).toBe(123);
    expect(error.signal).toBe("SIGTERM");
    expect(error.stderrTail).toBe("line");
  });
});
