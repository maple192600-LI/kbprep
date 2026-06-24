import {
  KBPREP_ERROR_CODES,
  KBPREP_RUNTIME_ERROR_CODES,
  KBPREP_WARNING_CODES,
  type KBPrepErrorCode,
  type KBPrepWarningCode,
} from "./errorCodes.js";

export { KBPREP_ERROR_CODES, KBPREP_RUNTIME_ERROR_CODES, KBPREP_WARNING_CODES, type KBPrepErrorCode, type KBPrepWarningCode };

export interface KBPrepError {
  code: KBPrepErrorCode;
  message: string;
  recoverable: boolean;
  suggested_action: string;
  details: Record<string, unknown>;
}

export class KBPrepException extends Error {
  public readonly kbprepError: KBPrepError;

  constructor(err: KBPrepError) {
    super(err.message);
    this.name = "KBPrepException";
    this.kbprepError = err;
  }
}

export function makeError(
  code: KBPrepErrorCode,
  message: string,
  opts: {
    recoverable?: boolean;
    suggested_action?: string;
    details?: Record<string, unknown>;
  } = {},
): KBPrepError {
  return {
    code,
    message,
    recoverable: opts.recoverable ?? true,
    suggested_action: opts.suggested_action ?? "Check input and retry.",
    details: opts.details ?? {},
  };
}
