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
    "excluded_contexts": [
        {
            "label": "cacao_crop",
            "terms": ["cacao", "cocoa", "kakao"],
            "context_terms": ["crop", "farmers", "beans", "chocolate"],
            "unless_terms": ["Kakao Corp", "KakaoBank", "KakaoTalk"],
        }
    ],
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

    def test_rok_does_not_match_inside_other_words(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/3",
            title="A broken system needs reform",
            summary="No direct reference here.",
            body="",
        )
        result = classify_item(item, KEYWORDS)
        self.assertNotIn("ROK", result.matched_terms)

    def test_cacao_crop_context_is_excluded(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/4",
            title="Korean buyers support kakao farmers",
            summary="The programme helps cacao crop producers and cocoa beans exporters.",
            body="",
        )

        result = classify_item(item, KEYWORDS)

        self.assertFalse(result.relevant)
        self.assertEqual(result.confidence, "low")

    def test_kakao_company_context_is_not_excluded(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/5",
            title="South Korean platform company Kakao Corp expands overseas",
            summary="Kakao Corp announced a new investment plan.",
            body="",
        )

        result = classify_item(item, KEYWORDS)

        self.assertTrue(result.relevant)
        self.assertEqual(result.confidence, "medium")

    def test_explicit_high_confidence_korea_term_is_not_excluded_by_cacao_context(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/6",
            title="South Korea reviews cocoa import rules",
            summary="The update covers cocoa beans and chocolate producers.",
            body="",
        )

        result = classify_item(item, KEYWORDS)

        self.assertTrue(result.relevant)
        self.assertEqual(result.confidence, "high")


if __name__ == "__main__":
    unittest.main()
