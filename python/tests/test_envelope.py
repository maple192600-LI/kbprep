import io
import json
import sys
import unittest

from kbprep_worker.envelope import EnvelopeExit, fail, ok


class EnvelopeTests(unittest.TestCase):
    def capture_envelope(self, fn):
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            with self.assertRaises(EnvelopeExit) as raised:
                fn()
            payload = json.loads(sys.stdout.getvalue())
            return raised.exception, payload
        finally:
            sys.stdout = old_stdout

    def test_ok_writes_success_envelope_and_raises_controlled_exit(self):
        exc, payload = self.capture_envelope(lambda: ok(data={"value": 1}))

        self.assertEqual(exc.code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"], {"value": 1})
        self.assertEqual(payload["warnings"], [])

    def test_fail_writes_error_envelope_and_raises_controlled_exit(self):
        exc, payload = self.capture_envelope(
            lambda: fail("E_TEST", "broken", details={"field": "value"}, recoverable=False)
        )

        self.assertEqual(exc.code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "E_TEST")
        self.assertEqual(payload["error"]["details"], {"field": "value"})
        self.assertFalse(payload["error"]["recoverable"])


if __name__ == "__main__":
    unittest.main()
