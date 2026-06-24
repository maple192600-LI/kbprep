import { describe, expect, it } from "vitest";
import { Value } from "typebox/value";
import { WorkerEnvelopeSchema } from "../../worker.js";

describe("WorkerEnvelopeSchema status (Phase E)", () => {
  it("accepts ok:true with completed status", () => {
    const env = { ok: true, status: "completed", data: {}, metrics: {}, warnings: [] };
    expect(Value.Check(WorkerEnvelopeSchema, env)).toBe(true);
  });

  it("accepts ok:true with completed_with_warnings status", () => {
    const env = {
      ok: true,
      status: "completed_with_warnings",
      data: {},
      metrics: {},
      warnings: ["w"],
    };
    expect(Value.Check(WorkerEnvelopeSchema, env)).toBe(true);
  });

  it("accepts ok:false with failed status", () => {
    const env = {
      ok: false,
      status: "failed",
      error: { code: "E_X", message: "m", recoverable: true, suggested_action: "a", details: {} },
      warnings: [],
    };
    expect(Value.Check(WorkerEnvelopeSchema, env)).toBe(true);
  });

  it("rejects ok:true with failed status (failed belongs to ok:false)", () => {
    const env = { ok: true, status: "failed", data: {}, metrics: {}, warnings: [] };
    expect(Value.Check(WorkerEnvelopeSchema, env)).toBe(false);
  });
});
