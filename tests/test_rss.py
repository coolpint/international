import unittest
from unittest.mock import patch
from xml.etree import ElementTree

from src.monitor.models import SourceConfig
from src.monitor.sources import _build_rss_item, _collect_rss_items, _xml_html_text


class RssTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = SourceConfig(
            id="wto_latest_news",
            label="WTO Latest News",
            type="rss_xml",
            enabled=True,
            list_url="https://www.wto.org/library/rss/latest_news_e.xml",
            max_items=20,
        )

    def test_html_text_normalizes_entities_and_tags(self) -> None:
        text = _xml_html_text("&lt;p&gt;Republic of Korea&lt;/p&gt;&lt;p&gt;DPRK update&lt;/p&gt;")
        self.assertEqual(text, "Republic of Korea\nDPRK update")

    def test_builds_rss_item_from_description_and_content(self) -> None:
        node = ElementTree.fromstring(
            """
            <item xmlns:content="http://purl.org/rss/1.0/modules/content/">
              <title>Trade update</title>
              <link>/english/news_e/example.htm</link>
              <description><![CDATA[<p>Republic of Korea export update</p>]]></description>
              <content:encoded><![CDATA[<div><p>DPRK supply chain detail.</p></div>]]></content:encoded>
              <pubDate>Sat, 07 Mar 2026 09:35:57 GMT</pubDate>
              <category>Press release</category>
            </item>
            """
        )

        item = _build_rss_item(self.source, node, self.source.list_url or "")
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.url, "https://www.wto.org/english/news_e/example.htm")
        self.assertEqual(item.title, "Trade update")
        self.assertEqual(item.summary, "Republic of Korea export update")
        self.assertIn("DPRK supply chain detail.", item.body)
        self.assertIn("Categories: Press release", item.body)
        self.assertEqual(item.published_at, "Sat, 07 Mar 2026 09:35:57 GMT")

    @patch("src.monitor.sources.fetch_text")
    def test_collect_rss_items_uses_fallback_url(self, mock_fetch_text) -> None:
        source = SourceConfig(
            id="adb_news",
            label="ADB News",
            type="rss_xml",
            enabled=True,
            list_url="https://www.adb.org/rss/news",
            max_items=20,
            options={"fallback_urls": ["https://feeds.feedburner.com/adb_news"]},
        )
        mock_fetch_text.side_effect = [
            RuntimeError("HTTP 403 for https://www.adb.org/rss/news"),
            (
                """<?xml version="1.0" encoding="utf-8"?>
                <rss version="2.0">
                  <channel>
                    <item>
                      <title>ADB fallback item</title>
                      <link>https://www.adb.org/news/example</link>
                      <description>Republic of Korea related example</description>
                      <pubDate>2026-03-17</pubDate>
                    </item>
                  </channel>
                </rss>""",
                {},
            ),
        ]

        items = _collect_rss_items(source)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "ADB fallback item")
        self.assertEqual(items[0].url, "https://www.adb.org/news/example")


if __name__ == "__main__":
    unittest.main()
