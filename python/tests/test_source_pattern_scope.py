import json
import unittest

from kbprep_worker.rule_loader import _source_pattern_matches


class SourcePatternScopeBehaviorTests(unittest.TestCase):
    def _identity(self, **values):
        return json.dumps(values, ensure_ascii=False)

    def test_plain_source_pattern_uses_path_or_name_prefix_boundaries(self):
        site_identity = self._identity(source_name="site-a-page.md", input_path="/vault/site-a-page.md")
        contest_identity = self._identity(source_name="contest_report.pdf", input_path="/vault/contest_report.pdf")
        latest_identity = self._identity(source_name="latest_summary.md", input_path="/vault/latest_summary.md")
        report_identity = self._identity(source_name="report-2026.md", input_path="/vault/reports/report-2026.md")

        self.assertTrue(_source_pattern_matches({"source_pattern": "site-a"}, site_identity))
        self.assertFalse(_source_pattern_matches({"source_pattern": "test"}, contest_identity))
        self.assertFalse(_source_pattern_matches({"source_pattern": "test"}, latest_identity))
        self.assertFalse(_source_pattern_matches({"source_pattern": "report"}, contest_identity))
        self.assertTrue(_source_pattern_matches({"source_pattern": "report"}, report_identity))

    def test_keyed_source_domain_only_matches_domain_field(self):
        domain_identity = self._identity(
            source_domain="example.com",
            source_url="https://example.com/course/lesson-1",
            source_name="lesson.md",
        )
        url_only_identity = self._identity(
            source_url="https://example.com/course/lesson-1",
            source_name="example.com-export.md",
        )
        subdomain_identity = self._identity(source_domain="docs.example.com", source_name="lesson.md")

        self.assertTrue(_source_pattern_matches({"source_pattern": "source_domain:example.com"}, domain_identity))
        self.assertTrue(_source_pattern_matches({"source_pattern": "source_domain:example.com"}, subdomain_identity))
        self.assertFalse(_source_pattern_matches({"source_pattern": "source_domain:example.com"}, url_only_identity))

    def test_keyed_source_url_matches_url_prefix_on_path_boundary(self):
        identity = self._identity(source_url="https://example.com/course/lesson-1?page=2")
        unrelated = self._identity(source_url="https://example.com/courseware/lesson-1")

        self.assertTrue(_source_pattern_matches({"source_pattern": "source_url:https://example.com/course"}, identity))
        self.assertFalse(_source_pattern_matches({"source_pattern": "source_url:https://example.com/course"}, unrelated))

    def test_plain_source_pattern_does_not_match_url_only_identity(self):
        identity = self._identity(source_url="https://example.com/course/lesson-1")

        self.assertFalse(_source_pattern_matches({"source_pattern": "example"}, identity))
        self.assertFalse(_source_pattern_matches({"source_pattern": "course"}, identity))


if __name__ == "__main__":
    unittest.main()
