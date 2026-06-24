"""Phase E: envelope status field (completed / completed_with_warnings / failed).

Tests the status_from_findings helper that maps quality gate findings to a
job status per core design §17.
"""
import unittest

from kbprep_worker.envelope import status_from_findings


class StatusFromFindingsTest(unittest.TestCase):
    def test_clean_run_is_completed(self):
        self.assertEqual(status_from_findings(strict_errors=[], warnings=[]), "completed")

    def test_warnings_only_is_completed_with_warnings(self):
        self.assertEqual(
            status_from_findings(strict_errors=[], warnings=["W_LOW_COVERAGE: x"]),
            "completed_with_warnings",
        )

    def test_strict_errors_is_failed(self):
        self.assertEqual(
            status_from_findings(strict_errors=["E_X: y"], warnings=[]),
            "failed",
        )

    def test_strict_errors_dominate_warnings(self):
        self.assertEqual(
            status_from_findings(strict_errors=["E_X: y"], warnings=["W_A: z"]),
            "failed",
        )


if __name__ == "__main__":
    unittest.main()
