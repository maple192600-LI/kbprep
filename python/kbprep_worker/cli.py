"""
CLI entry point for kbprep_worker.

Usage:
    python -m kbprep_worker.cli <command> --json-stdin

Commands: setup-env, preflight, diagnose, prepare, apply-review, feedback, cleanup
"""
import argparse
import json
import logging
import sys

from .envelope import fail


def setup_stderr_logging() -> None:
    """Configure logging to stderr as JSONL."""
    class JsonlHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            import json as _json
            entry = {
                "level": record.levelname.lower(),
                "stage": getattr(record, "stage", "cli"),
                "message": record.getMessage(),
            }
            if hasattr(record, "code"):
                entry["code"] = record.code
            if record.exc_info and record.exc_info[1]:
                entry["error"] = str(record.exc_info[1])
            sys.stderr.write(_json.dumps(entry, ensure_ascii=False) + "\n")
            sys.stderr.flush()

    handler = JsonlHandler()
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)


def main() -> None:
    setup_stderr_logging()

    parser = argparse.ArgumentParser(prog="kbprep_worker", description="KBPrep Python worker CLI")
    parser.add_argument("command", choices=[
        "setup-env", "setup_env", "preflight", "diagnose", "prepare", "apply-review", "apply_review",
        "feedback",
        "prepare-batch", "prepare_batch", "cleanup"
    ], help="Command to execute")
    parser.add_argument("--json-stdin", action="store_true", required=True,
                        help="Read JSON input from stdin")

    args = parser.parse_args()

    if not args.json_stdin:
        fail("E_INPUT_NOT_FOUND", "--json-stdin flag is required")

    try:
        raw = sys.stdin.read().lstrip("\ufeff")
        input_data = json.loads(raw)
    except json.JSONDecodeError as e:
        fail("E_INVALID_INPUT", f"Invalid JSON on stdin: {e}")
        return

    dispatch = {
        "setup-env": cmd_setup_env,
        "setup_env": cmd_setup_env,
        "preflight": cmd_preflight,
        "diagnose": cmd_diagnose,
        "prepare": cmd_prepare,
        "apply-review": cmd_apply_review,
        "apply_review": cmd_apply_review,
        "feedback": cmd_feedback,
        "prepare-batch": cmd_prepare_batch,
        "prepare_batch": cmd_prepare_batch,
        "cleanup": cmd_cleanup,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        fail("E_INTERNAL", f"Unknown command: {args.command}")
        return

    try:
        handler(input_data)
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled error in %s", args.command)
        fail("E_INTERNAL", str(e), details={"exception_type": type(e).__name__})


def cmd_preflight(data: dict) -> None:
    from . import preflight as pf
    pf.run(data)


def cmd_setup_env(data: dict) -> None:
    from .envelope import ok
    from .setup_env import setup_gpu
    ok(data=setup_gpu(
        device_override=data.get("device_override"),
        backend_override=data.get("backend_override"),
        install_mineru=bool(data.get("install_mineru")),
    ))


def cmd_diagnose(data: dict) -> None:
    from . import diagnose as diag
    diag.run(data)


def cmd_prepare(data: dict) -> None:
    from . import prepare as pr
    pr.run(data)


def cmd_apply_review(data: dict) -> None:
    from . import apply_patch as ap
    ap.run(data)


def cmd_feedback(data: dict) -> None:
    from . import feedback as fb
    fb.run(data)


def cmd_prepare_batch(data: dict) -> None:
    from . import prepare_batch as pb
    pb.run(data)


def cmd_cleanup(data: dict) -> None:
    from . import cleanup as cu
    cu.run(data)


if __name__ == "__main__":
    main()
