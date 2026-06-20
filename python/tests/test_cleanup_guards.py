import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from kbprep_worker import cleanup
from kbprep_worker.envelope import EnvelopeExit


class CleanupGuardTests(unittest.TestCase):
    def test_finalize_refuses_review_needed_content_without_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            final_md = root / "source.cleaned.md"
            final_md.write_text("# Final\n", encoding="utf-8")
            (root / "latest.json").write_text(
                json.dumps({
                    "input_path": str(root / "source.md"),
                    "latest_outputs": {
                        "final_artifact_type": "markdown",
                        "final_md": str(final_md),
                    },
                }),
                encoding="utf-8",
            )
            (root / "review_needed.md").write_text("needs human review\n", encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                with self.assertRaises(EnvelopeExit) as raised:
                    cleanup.run({"output_root": str(root), "action": "finalize"})

            self.assertEqual(raised.exception.code, 1)
            envelope = json.loads(stream.getvalue())
            self.assertFalse(envelope["ok"])
            self.assertEqual(envelope["error"]["code"], "KBPREP_REVIEW_NEEDED")
            self.assertTrue((root / "review_needed.md").exists())


if __name__ == "__main__":
    unittest.main()
