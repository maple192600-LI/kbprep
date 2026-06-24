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
    writeFileSync(scriptPath, ["process.stderr.write('before-timeout\\n');", "setInterval(() => {}, 1000);"].join("\n"), "utf8");

    try {
      await expect(
        runManagedProcess({
          command: process.execPath,
          args: [scriptPath],
          label: "test timeout",
          timeoutMs: 100,
          terminateGraceMs: 100,
        }),
      ).rejects.toMatchObject({
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

  // Regression: multi-byte UTF-8 (e.g. Chinese) must survive even when a single
  // character is split across two stdout/stderr chunks. The previous implementation
  // decoded each chunk independently with chunk.toString("utf-8"), which corrupts
  // any character straddling a chunk boundary. See AGENTS.md I/O correctness rule.
  it("preserves multi-byte UTF-8 stdout split across chunk boundaries", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-subprocess-mb-"));
    const scriptPath = path.join(root, "multibyte.mjs");
    // Each CJK char is 3 bytes in UTF-8; a 4096-byte write step (4096 % 3 != 0)
    // repeatedly splits characters across chunk boundaries.
    const payload = "中文测试内容".repeat(4000);
    writeFileSync(
      scriptPath,
      [
        "const buf = Buffer.from(JSON.parse(process.argv[2]));",
        "for (let i = 0; i < buf.length; i += 4096) {",
        "  process.stdout.write(buf.subarray(i, i + 4096));",
        "}",
      ].join("\n"),
      "utf8",
    );
    try {
      const result = await runManagedProcess({
        command: process.execPath,
        args: [scriptPath, JSON.stringify(payload)],
        label: "test multibyte stdout",
        timeoutMs: 10_000,
      });
      expect(result.code).toBe(0);
      expect(result.stdout).toBe(payload);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("preserves multi-byte UTF-8 stderr split across chunk boundaries", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "kbprep-subprocess-mb-"));
    const scriptPath = path.join(root, "multibyte-stderr.mjs");
    const payload = "日志行中文内容".repeat(4000);
    writeFileSync(
      scriptPath,
      [
        "const buf = Buffer.from(JSON.parse(process.argv[2]));",
        "for (let i = 0; i < buf.length; i += 4096) {",
        "  process.stderr.write(buf.subarray(i, i + 4096));",
        "}",
      ].join("\n"),
      "utf8",
    );
    try {
      const result = await runManagedProcess({
        command: process.execPath,
        args: [scriptPath, JSON.stringify(payload)],
        label: "test multibyte stderr",
        timeoutMs: 10_000,
      });
      expect(result.stderr).toBe(payload);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
