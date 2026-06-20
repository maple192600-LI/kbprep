import { describe, expect, it } from "vitest";
import { KBPrepException, makeError } from "./errors.js";

describe("kbprep error helpers", () => {
  it("creates recoverable errors with default retry guidance", () => {
    const error = makeError("E_INVALID_INPUT", "Bad input");

    expect(error).toEqual({
      code: "E_INVALID_INPUT",
      message: "Bad input",
      recoverable: true,
      suggested_action: "Check input and retry.",
      details: {},
    });
  });

  it("preserves explicit nonrecoverable error details in exceptions", () => {
    const error = makeError("E_INTERNAL", "Unexpected failure", {
      recoverable: false,
      suggested_action: "Open the run audit and report the error.",
      details: { run_id: "run-1" },
    });
    const exception = new KBPrepException(error);

    expect(exception.name).toBe("KBPrepException");
    expect(exception.message).toBe("Unexpected failure");
    expect(exception.kbprepError).toBe(error);
  });
});
