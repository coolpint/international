import unittest
from pathlib import Path

from src.main import _apply_source_default_classification
from src.monitor.config import load_keywords, load_sources
from src.monitor.filtering import classify_item
from src.monitor.models import Classification, MonitoredItem, SourceConfig


class SourceDefaultTests(unittest.TestCase):
    def test_source_default_promotes_unmatched_item(self) -> None:
        source = SourceConfig(
            id="thirty_eight_north",
            label="38 North",
            type="rss_xml",
            enabled=True,
            list_url="https://www.38north.org/feed/",
            max_items=20,
            options={
                "default_confidence": "high",
                "default_matched_terms": ["North Korea specialist source"],
            },
        )
        item = MonitoredItem(
            source_id=source.id,
            source_label=source.label,
            url="https://www.38north.org/example",
            title="A probable new hospital at Wonsan-Kalma Beach Resort",
            summary="Satellite imagery shows new construction.",
            body="",
        )
        classification = Classification(relevant=False, confidence="low", matched_terms=[])

        result = _apply_source_default_classification(item, classification, source)

        self.assertTrue(result.relevant)
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.matched_terms, ["North Korea specialist source"])

    def test_source_default_does_not_downgrade_high_item(self) -> None:
        source = SourceConfig(
            id="example",
            label="Example",
            type="rss_xml",
            enabled=True,
            list_url="https://example.com/feed.xml",
            max_items=20,
            options={"default_confidence": "medium"},
        )
        item = MonitoredItem(
            source_id=source.id,
            source_label=source.label,
            url="https://example.com/1",
            title="North Korea update",
            summary="",
            body="",
        )
        classification = Classification(relevant=True, confidence="high", matched_terms=["North Korea"])

        result = _apply_source_default_classification(item, classification, source)

        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.matched_terms, ["North Korea"])

    def test_source_default_does_not_reactivate_excluded_attribution(self) -> None:
        sources = {
            source.id: source
            for source in load_sources(Path("config/sources.json"))
        }
        keywords = load_keywords(Path("config/keywords.json"))
        source = sources["thirty_eight_north"]
        item = MonitoredItem(
            source_id=source.id,
            source_label=source.label,
            url="https://www.38north.org/example",
            title="North Korea prepares a launch",
            summary="The claim was reported by Yonhap News Agency.",
            body="",
        )

        classification = classify_item(item, keywords)
        result = _apply_source_default_classification(item, classification, source)

        self.assertTrue(classification.excluded)
        self.assertFalse(result.relevant)
        self.assertEqual(result.confidence, "low")

    def test_priority_media_respects_attribution_exclusion(self) -> None:
        sources = {
            source.id: source
            for source in load_sources(Path("config/sources.json"))
        }
        keywords = load_keywords(Path("config/keywords.json"))
        source = sources["nyt_korea_news"]
        item = MonitoredItem(
            source_id=source.id,
            source_label=source.label,
            url="https://news.google.com/rss/articles/example",
            title="South Korea prepares a policy shift - The New York Times",
            summary="Yonhap News Agency reported that the change starts next year.",
            body="",
        )

        classification = classify_item(item, keywords)
        result = _apply_source_default_classification(item, classification, source)

        self.assertTrue(classification.excluded)
        self.assertFalse(result.relevant)
        self.assertEqual(result.confidence, "low")
        self.assertTrue(result.excluded)

    def test_priority_media_promotes_verified_non_attribution_result(self) -> None:
        sources = {
            source.id: source
            for source in load_sources(Path("config/sources.json"))
        }
        source = sources["wsj_korea_news"]
        item = MonitoredItem(
            source_id=source.id,
            source_label=source.label,
            url="https://news.google.com/rss/articles/chips",
            title="The Dating Scene That's Suddenly Dominated by Chip Nerds - WSJ",
            summary="",
            body="",
        )
        classification = Classification(
            relevant=False,
            confidence="low",
            matched_terms=[],
        )

        result = _apply_source_default_classification(item, classification, source)

        self.assertTrue(result.relevant)
        self.assertEqual(result.confidence, "high")
        self.assertIn("WSJ Korea priority source", result.matched_terms)

    def test_priority_media_sources_are_narrow_explicit_exceptions(self) -> None:
        sources = {
            source.id: source
            for source in load_sources(Path("config/sources.json"))
        }

        expected = {
            "nyt_korea_news": ("The New York Times", "www.nytimes.com"),
            "wsj_korea_news": ("WSJ", "www.wsj.com"),
        }
        configured_force_alert_ids = {
            source.id
            for source in sources.values()
            if source.options.get("force_alert") is True
        }
        self.assertEqual(configured_force_alert_ids, set())
        for source_id, (publisher, domain) in expected.items():
            with self.subTest(source_id=source_id):
                source = sources[source_id]
                self.assertTrue(source.enabled)
                self.assertEqual(source.options.get("default_confidence"), "high")
                self.assertEqual(
                    source.options.get("allowed_feed_source_names"), [publisher]
                )
                self.assertEqual(
                    source.options.get("allowed_feed_source_domains"), [domain]
                )

    def test_priority_media_exclusion_terms_stay_in_attribution_rule(self) -> None:
        sources = {
            source.id: source
            for source in load_sources(Path("config/sources.json"))
        }
        keywords = load_keywords(Path("config/keywords.json"))
        attribution_terms = {
            term.casefold()
            for rule in keywords["excluded_attribution_rules"]
            for term in rule["outlet_terms"]
        }

        for source_id in ("nyt_korea_news", "wsj_korea_news"):
            source_terms = {
                term.strip('"').casefold()
                for term in sources[source_id].options["excluded_feed_outlet_terms"]
            }
            self.assertTrue(source_terms.issubset(attribution_terms))

    def test_active_global_sources_declare_country_and_language(self) -> None:
        sources = {
            source.id: source
            for source in load_sources(Path("config/sources.json"))
        }
        expected = {
            "uk_fcdo_news": ("United Kingdom", "en"),
            "canada_global_affairs_news": ("Canada", "en"),
            "eu_council_press_fr": ("European Union", "fr"),
            "germany_foreign_office_press_de": ("Germany", "de"),
            "china_mfa_spokesperson_zh": ("China", "zh-Hans"),
        }

        for source_id, (country, language) in expected.items():
            with self.subTest(source_id=source_id):
                source = sources[source_id]
                self.assertTrue(source.enabled)
                self.assertEqual(source.options.get("country"), country)
                self.assertEqual(source.options.get("language"), language)

    def test_repaired_ilo_and_cisa_sources_use_live_official_endpoints(self) -> None:
        sources = {
            source.id: source
            for source in load_sources(Path("config/sources.json"))
        }

        ilo = sources["ilo_newsroom"]
        self.assertEqual(ilo.type, "html_listing")
        self.assertEqual(ilo.list_url, "https://www.ilo.org/resource/news/all-news-recent")

        cisa = sources["cisa_north_korea_cyber_advisories"]
        self.assertEqual(cisa.type, "rss_xml")
        self.assertEqual(cisa.list_url, "https://www.cisa.gov/cybersecurity-advisories/all.xml")
        self.assertNotIn("default_confidence", cisa.options)
        self.assertIn("/resources-tools/resources/", cisa.options.get("allowed_url_patterns", []))


if __name__ == "__main__":
    unittest.main()
