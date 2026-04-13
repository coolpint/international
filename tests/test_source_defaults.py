import unittest

from src.main import _apply_source_default_classification
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


if __name__ == "__main__":
    unittest.main()
