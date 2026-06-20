import { describe, expect, it } from "vitest";
import { parseEnvelope } from "./worker.js";

describe("worker command data schemas", () => {
  it("rejects empty worker stdout with stderr evidence", () => {
    const result = parseEnvelope("", ["worker stderr"]);

    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("E_WORKER_BAD_JSON");
    expect(result.error?.details.stderr_tail).toEqual(["worker stderr"]);
  });

  it("rejects non-json worker stdout with a bounded preview", () => {
    const result = parseEnvelope("not json".repeat(100), [], "diagnose");

    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("E_WORKER_BAD_JSON");
    expect(String(result.error?.details.stdout_preview)).toHaveLength(500);
  });

  it("rejects prepare envelopes missing run_dir", () => {
    const envelope = JSON.stringify({
      ok: true,
      data: {
        run_id: "run-1",
        latest_outputs: {},
      },
    });

    const result = parseEnvelope(envelope, [], "prepare");

    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("E_WORKER_BAD_JSON");
    expect(result.error?.details.validation_errors).toBeDefined();
    expect(result.error?.details.command).toBe("prepare");
  });

  it("rejects diagnose envelopes with malformed command data", () => {
    const envelope = JSON.stringify({
      ok: true,
      data: {
        input_file: 42,
        recommended_pipeline: "direct",
      },
    });

    const result = parseEnvelope(envelope, ["stderr tail"], "diagnose");

    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("E_WORKER_BAD_JSON");
    expect(result.error?.details.command).toBe("diagnose");
    expect(result.error?.details.stderr_tail).toEqual(["stderr tail"]);
  });

  it("accepts prepare envelopes with required output contract", () => {
    const envelope = JSON.stringify({
      ok: true,
      data: {
        run_id: "run-1",
        run_dir: "C:/tmp/run-1",
        latest_outputs: {},
      },
      warnings: [],
    });

    const result = parseEnvelope(envelope, [], "prepare");

    expect(result.ok).toBe(true);
    expect(result.data?.run_dir).toBe("C:/tmp/run-1");
  });

  it("rejects cleanup envelopes with non-object data", () => {
    const envelope = JSON.stringify({
      ok: true,
      data: "cleaned",
    });

    const result = parseEnvelope(envelope, [], "cleanup");

    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe("E_WORKER_BAD_JSON");
  });
});
