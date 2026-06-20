import unittest

from kbprep_worker.obsidian_kb.frontmatter import _yaml_safe, frontmatter_lines


class FrontmatterSafetyTests(unittest.TestCase):
    def test_frontmatter_escapes_newlines_colons_and_quotes_on_one_yaml_line(self):
        lines = frontmatter_lines({"title": '第一行\n副标题: "引号"'})

        self.assertEqual(lines, ["---", 'title: "第一行\\n副标题: \\"引号\\""', "---"])
        self.assertEqual(len("\n".join(lines).splitlines()), 3)

    def test_yaml_safe_escapes_control_characters(self):
        self.assertEqual(_yaml_safe("a\nb\tc"), "a\\nb\\tc")


if __name__ == "__main__":
    unittest.main()
