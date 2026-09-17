import unittest
from unittest.mock import patch
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from src.monitor.models import SourceConfig
from src.monitor.sources import (
    _build_rss_item,
    _collect_rss_items,
    _excluded_rss_feed_urls,
    _extract_bruegel_publication_links,
    _extract_rusi_publication_links,
    _xml_html_text,
)


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

    def test_builds_rss_item_from_guid_when_link_is_missing(self) -> None:
        node = ElementTree.fromstring(
            """
            <item>
              <title>North Korean cyber update</title>
              <description>FBI update on DPRK cyber activity</description>
              <guid>https://www.fbi.gov/news/press-releases/example</guid>
              <pubDate>Fri, 13 Mar 2026 10:30:00 +0000</pubDate>
            </item>
            """
        )

        item = _build_rss_item(self.source, node, self.source.list_url or "")
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.url, "https://www.fbi.gov/news/press-releases/example")
        self.assertEqual(item.title, "North Korean cyber update")

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

    def test_collect_rss_items_applies_url_filters(self) -> None:
        source = SourceConfig(
            id="sipri_publications",
            label="SIPRI Publications",
            type="rss_xml",
            enabled=True,
            list_url="https://www.sipri.org/rss/combined.xml",
            max_items=20,
            options={
                "allowed_url_patterns": ["/publications/"],
                "deny_url_patterns": ["/news/"],
            },
        )
        root = ElementTree.fromstring(
            """
            <rss version="2.0">
              <channel>
                <item>
                  <title>Publication</title>
                  <link>https://www.sipri.org/publications/example</link>
                  <description>Republic of Korea report</description>
                  <pubDate>2026-03-20</pubDate>
                </item>
                <item>
                  <title>News</title>
                  <link>https://www.sipri.org/news/example</link>
                  <description>Republic of Korea article</description>
                  <pubDate>2026-03-19</pubDate>
                </item>
              </channel>
            </rss>
            """
        )

        with patch("src.monitor.sources.fetch_text", return_value=(ElementTree.tostring(root, encoding="unicode"), {})):
            items = _collect_rss_items(source)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://www.sipri.org/publications/example")

    @patch("src.monitor.sources.fetch_text")
    def test_google_news_feed_verifies_publisher_and_denies_non_news_titles(
        self, mock_fetch_text
    ) -> None:
        source = SourceConfig(
            id="nyt_korea_news",
            label="The New York Times — Korea",
            type="rss_xml",
            enabled=True,
            list_url="https://news.google.com/rss/search?q=Korea+site:nytimes.com",
            max_items=100,
            options={
                "allowed_domains": ["news.google.com"],
                "allowed_feed_source_names": ["The New York Times"],
                "allowed_feed_source_domains": ["www.nytimes.com"],
                "deny_title_patterns": [" - NYT Cooking"],
                "minimum_items": 1,
            },
        )
        mock_fetch_text.return_value = (
            """<?xml version="1.0" encoding="utf-8"?>
            <rss version="2.0">
              <channel>
                <item>
                  <title>South Korea policy shift - The New York Times</title>
                  <link>https://news.google.com/rss/articles/valid</link>
                  <description>South Korea policy shift</description>
                  <source url="https://www.nytimes.com">The New York Times</source>
                </item>
                <item>
                  <title>Imposter result</title>
                  <link>https://news.google.com/rss/articles/imposter</link>
                  <description>Korea</description>
                  <source url="https://example.com">The New York Times</source>
                </item>
                <item>
                  <title>Korean Fried Chicken Recipe - NYT Cooking</title>
                  <link>https://news.google.com/rss/articles/recipe</link>
                  <description>Korean Fried Chicken Recipe</description>
                  <source url="https://www.nytimes.com">The New York Times</source>
                </item>
                <item>
                  <title>South Korea's Recipe for Growth - The New York Times</title>
                  <link>https://news.google.com/rss/articles/growth</link>
                  <description>South Korea's Recipe for Growth</description>
                  <source url="https://www.nytimes.com">The New York Times</source>
                </item>
              </channel>
            </rss>""",
            {},
        )

        items = _collect_rss_items(source)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "South Korea policy shift - The New York Times")
        self.assertEqual(
            items[1].title,
            "South Korea's Recipe for Growth - The New York Times",
        )

    @patch("src.monitor.sources.fetch_text")
    def test_priority_feed_rejects_zero_verified_items(self, mock_fetch_text) -> None:
        source = SourceConfig(
            id="wsj_korea_news",
            label="The Wall Street Journal — Korea",
            type="rss_xml",
            enabled=True,
            list_url="https://news.google.com/rss/search?q=Korea+site:wsj.com",
            max_items=100,
            options={
                "allowed_feed_source_names": ["WSJ"],
                "allowed_feed_source_domains": ["www.wsj.com"],
                "minimum_items": 1,
            },
        )
        mock_fetch_text.return_value = (
            """<rss version="2.0"><channel>
              <item>
                <title>Unverified Korea result</title>
                <link>https://news.google.com/rss/articles/unverified</link>
              </item>
            </channel></rss>""",
            {},
        )

        with self.assertRaisesRegex(RuntimeError, "expected at least 1"):
            _collect_rss_items(source)

    @patch("src.monitor.sources.fetch_text")
    def test_priority_feed_excludes_re_reported_article_by_stable_guid(
        self, mock_fetch_text
    ) -> None:
        source = SourceConfig(
            id="nyt_korea_news",
            label="The New York Times — Korea",
            type="rss_xml",
            enabled=True,
            list_url="https://news.google.com/rss/search?q=Korea+site:nytimes.com",
            max_items=100,
            options={
                "excluded_feed_site": "nytimes.com",
                "excluded_feed_outlet_terms": ["Yonhap", '"The Korea Herald"'],
                "allowed_domains": ["news.google.com"],
                "allowed_feed_source_names": ["The New York Times"],
                "allowed_feed_source_domains": ["www.nytimes.com"],
                "minimum_items": 1,
            },
        )
        main_feed = """<rss version="2.0"><channel>
          <item>
            <title>South Korea original reporting - The New York Times</title>
            <link>https://news.google.com/rss/articles/original</link>
            <guid isPermaLink="false">original-id</guid>
            <source url="https://www.nytimes.com">The New York Times</source>
          </item>
          <item>
            <title>South Korea re-report - The New York Times</title>
            <link>https://news.google.com/rss/articles/re-report</link>
            <guid isPermaLink="false">re-report-id</guid>
            <source url="https://www.nytimes.com">The New York Times</source>
          </item>
        </channel></rss>"""
        exclusion_feed = """<rss version="2.0"><channel>
          <item>
            <title>South Korea re-report - The New York Times</title>
            <link>https://news.google.com/rss/articles/re-report</link>
            <guid isPermaLink="false">re-report-id</guid>
            <source url="https://www.nytimes.com">The New York Times</source>
          </item>
        </channel></rss>"""
        empty_exclusion_feed = "<rss version='2.0'><channel></channel></rss>"
        mock_fetch_text.side_effect = [
            (main_feed, {}),
            (exclusion_feed, {}),
            (empty_exclusion_feed, {}),
        ]

        items = _collect_rss_items(source)

        self.assertEqual([item.title for item in items], [
            "South Korea original reporting - The New York Times"
        ])

    def test_priority_feed_builds_short_publisher_scoped_exclusion_urls(self) -> None:
        source = SourceConfig(
            id="nyt_korea_news",
            label="The New York Times — Korea",
            type="rss_xml",
            enabled=True,
            list_url="https://news.google.com/rss/search?q=Korea+site:nytimes.com",
            max_items=100,
            options={
                "excluded_feed_site": "nytimes.com",
                "excluded_feed_outlet_terms": ["Yonhap", '"The Korea Herald"'],
            },
        )

        urls = _excluded_rss_feed_urls(source)

        self.assertEqual(len(urls), 2)
        self.assertIn("site%3Anytimes.com+Yonhap", urls[0])
        self.assertIn("site%3Anytimes.com+%22The+Korea+Herald%22", urls[1])
        self.assertNotIn("Korea+Herald", urls[0])

    @patch("src.monitor.sources.fetch_text")
    def test_priority_feed_fails_closed_on_unverified_exclusion_results(
        self, mock_fetch_text
    ) -> None:
        source = SourceConfig(
            id="nyt_korea_news",
            label="The New York Times — Korea",
            type="rss_xml",
            enabled=True,
            list_url="https://news.google.com/rss/search?q=Korea+site:nytimes.com",
            max_items=100,
            options={
                "excluded_feed_site": "nytimes.com",
                "excluded_feed_outlet_terms": ["Yonhap"],
                "allowed_feed_source_names": ["The New York Times"],
                "allowed_feed_source_domains": ["www.nytimes.com"],
            },
        )
        main_feed = "<rss version='2.0'><channel></channel></rss>"
        drifted_exclusion_feed = """<rss version="2.0"><channel>
          <item>
            <title>Korea story - Yonhap News Agency</title>
            <link>https://news.google.com/rss/articles/unrelated</link>
            <guid isPermaLink="false">unrelated-id</guid>
            <source url="https://en.yna.co.kr">Yonhap News Agency</source>
          </item>
        </channel></rss>"""
        mock_fetch_text.side_effect = [
            (main_feed, {}),
            (drifted_exclusion_feed, {}),
        ]

        with self.assertRaisesRegex(RuntimeError, "none matched the required publisher"):
            _collect_rss_items(source)

    @patch("src.monitor.sources.fetch_text")
    def test_priority_feed_fails_closed_when_exclusion_feed_fails(
        self, mock_fetch_text
    ) -> None:
        source = SourceConfig(
            id="wsj_korea_news",
            label="The Wall Street Journal — Korea",
            type="rss_xml",
            enabled=True,
            list_url="https://news.google.com/rss/search?q=Korea+site:wsj.com",
            max_items=100,
            options={
                "excluded_feed_url": "https://news.google.com/rss/search?q=Yonhap+site:wsj.com",
            },
        )
        main_feed = "<rss version='2.0'><channel></channel></rss>"
        mock_fetch_text.side_effect = [
            (main_feed, {}),
            RuntimeError("exclusion feed unavailable"),
        ]

        with self.assertRaisesRegex(RuntimeError, "exclusion feed unavailable"):
            _collect_rss_items(source)

    def test_collect_rss_items_supports_rdf_rss(self) -> None:
        source = SourceConfig(
            id="bis_press_releases",
            label="BIS Press Releases",
            type="rss_xml",
            enabled=True,
            list_url="https://www.bis.org/doclist/all_pressrels.rss",
            max_items=20,
            options={"allowed_url_patterns": ["/press/"]},
        )
        root = ElementTree.fromstring(
            """
            <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                     xmlns="http://purl.org/rss/1.0/"
                     xmlns:dc="http://purl.org/dc/elements/1.1/">
              <channel rdf:about="https://www.bis.org/doclist/all_pressrels.rss">
                <title>Press releases</title>
                <link>https://www.bis.org/doclist/all_pressrels.rss</link>
                <description>Press releases</description>
              </channel>
              <item rdf:about="https://www.bis.org/press/p260322.htm">
                <title>Statement on the nomination of Hyun Song Shin as Governor of the Bank of Korea</title>
                <link>https://www.bis.org/press/p260322.htm</link>
                <description>Following the nomination of Hyun Song Shin as Governor of the Bank of Korea.</description>
                <dc:date>2026-03-22T12:08:00Z</dc:date>
              </item>
            </rdf:RDF>
            """
        )

        with patch("src.monitor.sources.fetch_text", return_value=(ElementTree.tostring(root, encoding="unicode"), {})):
            items = _collect_rss_items(source)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://www.bis.org/press/p260322.htm")
        self.assertEqual(items[0].published_at, "2026-03-22T12:08:00Z")

    def test_extract_bruegel_publication_links(self) -> None:
        soup = BeautifulSoup(
            """
            <div class="c-listing__items">
              <div class="views-row">
                <article class="c-list-item c-list-item--article">
                  <h2 class="c-list-item__title">
                    <a href="/working-paper/example-paper">Example paper</a>
                  </h2>
                </article>
              </div>
              <div class="views-row">
                <article class="c-list-item c-list-item--article">
                  <h2 class="c-list-item__title">
                    <a href="/analysis/example-analysis">Example analysis</a>
                  </h2>
                </article>
              </div>
            </div>
            """,
            "html.parser",
        )

        urls = _extract_bruegel_publication_links("https://www.bruegel.org/publications", soup)

        self.assertEqual(
            urls,
            [
                "https://www.bruegel.org/working-paper/example-paper",
                "https://www.bruegel.org/analysis/example-analysis",
            ],
        )

    def test_extract_rusi_publication_links(self) -> None:
        soup = BeautifulSoup(
            """
            <div>
              <a class="RelatedArticle-module--mainLink--4c03e" href="/explore-our-research/publications/insights-papers/example-paper"></a>
              <a class="RelatedArticle-module--mainLink--4c03e" href="/explore-our-research/publications/research-papers/example-report"></a>
              <a class="RelatedArticle-module--mainLink--4c03e" href="/podcasts/example"></a>
            </div>
            """,
            "html.parser",
        )

        urls = _extract_rusi_publication_links("https://www.rusi.org/", soup)

        self.assertEqual(
            urls,
            [
                "https://www.rusi.org/explore-our-research/publications/insights-papers/example-paper",
                "https://www.rusi.org/explore-our-research/publications/research-papers/example-report",
            ],
        )


if __name__ == "__main__":
    unittest.main()
