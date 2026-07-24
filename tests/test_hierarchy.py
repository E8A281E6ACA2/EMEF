import unittest

from src.core.extraction.smart_hierarchy_parser import SmartHierarchyParser


class SmartHierarchyParserTests(unittest.TestCase):
    def test_markdown_headings_are_split(self) -> None:
        parser = SmartHierarchyParser(mode="auto")
        sections, metadata = parser.parse("# 引言\n内容A\n## 方法\n内容B")

        self.assertEqual([section.title for section in sections], ["引言", "方法"])
        self.assertEqual(metadata["strategy"], "markdown")
        self.assertEqual(metadata["total_sections"], 2)

    def test_chinese_numbered_headings_are_split(self) -> None:
        parser = SmartHierarchyParser(mode="auto")
        sections, metadata = parser.parse("一、材料\n内容A\n（二）方法\n内容B")

        self.assertEqual([section.title for section in sections], ["材料", "方法"])
        self.assertEqual(metadata["strategy"], "numbering")


if __name__ == "__main__":
    unittest.main()
