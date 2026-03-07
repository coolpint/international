import unittest

from src.monitor.filtering import classify_item
from src.monitor.models import MonitoredItem


KEYWORDS = {
    "high_confidence_terms": [
        "South Korea",
        "North Korea",
        "DPRK",
        "Korean Peninsula",
    ],
    "medium_confidence_terms": [
        "Korea",
        "Korean",
        "Seoul",
        "Pyongyang",
    ],
    "min_medium_hits_for_high": 2,
}


class FilteringTests(unittest.TestCase):
    def test_high_confidence_when_specific_term_appears(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/1",
            title="UN envoy briefs Security Council on North Korea",
            summary="",
            body="",
        )
        result = classify_item(item, KEYWORDS)
        self.assertTrue(result.relevant)
        self.assertEqual(result.confidence, "high")

    def test_medium_confidence_when_single_generic_term_appears(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/2",
            title="Regional development update",
            summary="Officials met in Seoul.",
            body="",
        )
        result = classify_item(item, KEYWORDS)
        self.assertTrue(result.relevant)
        self.assertEqual(result.confidence, "medium")


if __name__ == "__main__":
    unittest.main()

