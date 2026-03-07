import unittest

from src.monitor.models import SourceConfig
from src.monitor.sources import _build_unrisd_item, _unrisd_search_index_text


class UnrisdTests(unittest.TestCase):
    def test_extracts_search_index_text(self) -> None:
        raw = '{"1": {"text": "<p>Republic of Korea cooperation</p><p>Next line.</p>"}}'
        text = _unrisd_search_index_text(raw)
        self.assertIn("Republic of Korea cooperation", text)
        self.assertIn("Next line.", text)

    def test_builds_unrisd_item(self) -> None:
        source = SourceConfig(
            id="unrisd_news",
            label="UNRISD News",
            type="unrisd_api",
            enabled=True,
            list_url="https://www.unrisd.org/news",
            max_items=20,
            options={
                "oauth_token_url": "https://www.unrisd.org/oauth/token",
                "api_url": "https://api.unrisd.org/en/news-items",
                "route_prefix": "/en/activities/news-items",
            },
        )
        record = {
            "attributes": {
                "slug": "example-slug",
                "title": "Example title",
                "summary": "",
                "publishAt": "2026-03-01 12:00:00",
                "searchIndex": '{"1": {"text": "<p>DPRK and Seoul were both referenced.</p>"}}',
            }
        }

        item = _build_unrisd_item(source, record, "/en/activities/news-items")
        self.assertIsNotNone(item)
        self.assertEqual(item.url, "https://www.unrisd.org/en/activities/news-items/example-slug")
        self.assertIn("DPRK", item.body)
        self.assertTrue(item.summary)


if __name__ == "__main__":
    unittest.main()
