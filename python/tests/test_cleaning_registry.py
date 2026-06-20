import unittest
from pathlib import Path

from kbprep_worker.cleaning_registry import (
    CleaningRuleRouteKind,
    select_accepted_rule_routes,
    select_base_cleaning_routes,
)


class CleaningRegistryTests(unittest.TestCase):
    def test_selects_base_document_type_and_templates_in_stable_order(self):
        routes = select_base_cleaning_routes(
            Path("/repo/rules"),
            profile="curated_obsidian_kb",
            document_type="report",
            templates=("obsidian_course_kb", "self_media_course"),
        )

        self.assertEqual(
            [(route.kind, route.source) for route in routes],
            [
                (CleaningRuleRouteKind.BASE, "rules/base/obvious_noise.json"),
                (CleaningRuleRouteKind.DOCUMENT_TYPE, "rules/document_types/report.json"),
                (CleaningRuleRouteKind.PROFILE_TEMPLATE, "rules/templates/self_media_course.json"),
                (CleaningRuleRouteKind.REQUESTED_TEMPLATE, "rules/templates/obsidian_course_kb.json"),
            ],
        )
        self.assertEqual([route.priority for route in routes], sorted(route.priority for route in routes))
        self.assertTrue(all(route.cache_strategy == "base_rules" for route in routes))

    def test_accepted_user_rules_are_declared_as_runtime_routes(self):
        routes = select_accepted_rule_routes(
            Path("/repo/rules"),
            cwd=Path("/repo/work"),
            user_rule_dirs=(Path("/extra/user_rules"),),
        )

        self.assertTrue(all(route.kind is CleaningRuleRouteKind.ACCEPTED_USER for route in routes))
        self.assertEqual(
            [route.path for route in routes],
            [
                Path("/extra/user_rules/accepted_rules.jsonl"),
                Path("/repo/work/.kbprep/rules/user/accepted_rules.jsonl"),
            ],
        )
        self.assertTrue(all(route.runtime_filter == "document_type_and_source_pattern" for route in routes))
        self.assertTrue(all(route.cache_strategy == "accepted_rules_file_stat" for route in routes))


if __name__ == "__main__":
    unittest.main()
