import unittest
from xml.etree import ElementTree

from src.monitor.models import SourceConfig
from src.monitor.sources import _build_rss_item, _xml_html_text


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

        item = _build_rss_item(self.source, node)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.url, "https://www.wto.org/english/news_e/example.htm")
        self.assertEqual(item.title, "Trade update")
        self.assertEqual(item.summary, "Republic of Korea export update")
        self.assertIn("DPRK supply chain detail.", item.body)
        self.assertIn("Categories: Press release", item.body)
        self.assertEqual(item.published_at, "Sat, 07 Mar 2026 09:35:57 GMT")


if __name__ == "__main__":
    unittest.main()
