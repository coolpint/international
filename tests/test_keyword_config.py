import json
import unittest
from pathlib import Path

from src.monitor.filtering import classify_item
from src.monitor.models import MonitoredItem


class KeywordConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.keywords = json.loads(
            Path("config/keywords.json").read_text(encoding="utf-8")
        )

    def test_company_terms_are_unique_and_avoid_ambiguous_short_aliases(self) -> None:
        terms = self.keywords["korean_company_terms"]

        self.assertEqual(len(terms), len(set(terms)))
        for ambiguous in ["SK", "LG", "KT", "Kia", "Samsung", "Hyundai"]:
            self.assertNotIn(ambiguous, terms)

    def test_real_config_classifies_multilingual_country_and_company_terms(self) -> None:
        examples = [
            "La Corée du Sud et la France renforcent leur coopération",
            "Südkorea kündigt neue Investitionen an",
            "中国与韩国举行高级别对话",
            "Samsung Electronics opens a new research centre",
            "SK海力士宣布新的投资计划",
            "現代自動車が新工場を発表",
        ]

        for title in examples:
            with self.subTest(title=title):
                result = classify_item(
                    MonitoredItem(
                        source_id="test",
                        source_label="Test",
                        url="https://example.com/item",
                        title=title,
                        summary="",
                        body="",
                    ),
                    self.keywords,
                )
                self.assertTrue(result.relevant)
                self.assertEqual(result.confidence, "high")

    def test_real_config_excludes_korean_media_attribution(self) -> None:
        examples = [
            (
                "North Korea prepares a launch",
                "The claim was reported by Yonhap News Agency.",
            ),
            (
                "North Korea prepares a launch",
                "Yonhap News Agency reported that preparations were under way.",
            ),
            (
                "North Korea prepares a launch",
                "Yonhap reported Tuesday that preparations were under way.",
            ),
            (
                "韩国宣布新的产业政策",
                "据韩联社报道，该政策将于明年实施。",
            ),
        ]

        for title, summary in examples:
            with self.subTest(title=title):
                result = classify_item(
                    MonitoredItem(
                        source_id="test",
                        source_label="Test",
                        url="https://example.com/item",
                        title=title,
                        summary=summary,
                        body="",
                    ),
                    self.keywords,
                )
                self.assertFalse(result.relevant)
