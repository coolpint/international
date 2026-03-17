import unittest
from unittest.mock import patch

from src.monitor.models import SourceConfig
from src.monitor.sources import _build_world_bank_news_item, _collect_world_bank_news_items


class WorldBankTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = SourceConfig(
            id="world_bank_news",
            label="World Bank News",
            type="world_bank_news_api",
            enabled=True,
            list_url="https://www.worldbank.org/en/news/all",
            max_items=20,
            options={
                "api_url": "https://search.worldbank.org/api/v2/news?format=json&rows=40&src=cq55&apilang=en&lang_exact=English",
            },
        )

    def test_builds_world_bank_item(self) -> None:
        record = {
            "url": "http://www.worldbank.org/en/news/press-release/2026/03/16/example",
            "title": {"cdata!": "Republic of Korea energy update"},
            "descr": {"cdata!": "New support for energy transition."},
            "content_1000": {"cdata!": "<p>Seoul and wider Korea cooperation details.</p>"},
            "lnchdt": "2026-03-16T11:51:00Z",
        }

        item = _build_world_bank_news_item(self.source, record)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.url, "https://www.worldbank.org/en/news/press-release/2026/03/16/example")
        self.assertEqual(item.title, "Republic of Korea energy update")
        self.assertIn("New support for energy transition.", item.summary)
        self.assertIn("Seoul and wider Korea cooperation details.", item.body)
        self.assertEqual(item.published_at, "2026-03-16T11:51:00Z")

    @patch("src.monitor.sources.fetch_json")
    def test_collect_world_bank_items_sorts_and_skips_future(self, mock_fetch_json) -> None:
        mock_fetch_json.return_value = {
            "documents": {
                "future": {
                    "url": "http://www.worldbank.org/en/news/brief/2026/06/02/future-item",
                    "title": {"cdata!": "Future item"},
                    "descr": {"cdata!": "Should be ignored."},
                    "lnchdt": "2026-06-02T21:20:00Z",
                },
                "older": {
                    "url": "http://www.worldbank.org/en/news/press-release/2026/03/15/older-item",
                    "title": {"cdata!": "Older Korea item"},
                    "descr": {"cdata!": "Republic of Korea support"},
                    "lnchdt": "2026-03-15T11:51:00Z",
                },
                "newer": {
                    "url": "http://www.worldbank.org/en/news/press-release/2026/03/16/newer-item",
                    "title": {"cdata!": "Newer Seoul item"},
                    "descr": {"cdata!": "Seoul update"},
                    "lnchdt": "2026-03-16T11:51:00Z",
                },
            }
        }

        items = _collect_world_bank_news_items(self.source)

        self.assertEqual([item.title for item in items], ["Newer Seoul item", "Older Korea item"])


if __name__ == "__main__":
    unittest.main()
