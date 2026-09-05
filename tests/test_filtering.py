import unittest

from src.monitor.filtering import classify_item
from src.monitor.models import MonitoredItem


KEYWORDS = {
    "high_confidence_terms": [
        "South Korea",
        "South Korean",
        "North Korea",
        "North Korean",
        "Republic of Korea",
        "DPRK",
        "Korean Peninsula",
        "북한",
        "Corée du Sud",
        "Südkorea",
        "韩国",
    ],
    "korean_company_terms": [
        "Samsung Electronics",
        "SK hynix",
        "三星电子",
    ],
    "medium_confidence_terms": [
        "Korea",
        "Korean",
        "Seoul",
        "Pyongyang",
    ],
    "min_medium_hits_for_high": 2,
    "excluded_attribution_rules": [
        {
            "label": "korean_media_attribution",
            "outlet_terms": ["Yonhap News Agency", "연합뉴스", "韩联社"],
            "attribution_terms": ["according to", "reported by", "보도", "据", "报道"],
        }
    ],
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

    def test_high_confidence_when_north_korean_adjective_appears(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/1a",
            title="FBI warns of North Korean cyber activity",
            summary="",
            body="",
        )
        result = classify_item(item, KEYWORDS)
        self.assertTrue(result.relevant)
        self.assertEqual(result.confidence, "high")

    def test_high_confidence_when_korean_keyword_appears(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/1b",
            title="북한 외무상, 중국 외교부장과 회담",
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
        self.assertEqual(result.confidence, "high")

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

    def test_foreign_language_korea_terms_are_high_confidence(self) -> None:
        for title in [
            "La Corée du Sud annonce un nouvel accord",
            "Südkorea und Deutschland vertiefen ihre Zusammenarbeit",
            "中国与韩国举行经贸磋商",
        ]:
            with self.subTest(title=title):
                item = MonitoredItem(
                    source_id="x",
                    source_label="Test",
                    url="https://example.com/foreign-language",
                    title=title,
                    summary="",
                    body="",
                )

                result = classify_item(item, KEYWORDS)

                self.assertTrue(result.relevant)
                self.assertEqual(result.confidence, "high")

    def test_korean_company_terms_are_high_confidence_without_country_name(self) -> None:
        for company in ["Samsung Electronics", "SK hynix", "三星电子"]:
            with self.subTest(company=company):
                item = MonitoredItem(
                    source_id="x",
                    source_label="Test",
                    url="https://example.com/company",
                    title=f"{company} announces a new overseas investment",
                    summary="",
                    body="",
                )

                result = classify_item(item, KEYWORDS)

                self.assertTrue(result.relevant)
                self.assertEqual(result.confidence, "high")
                self.assertIn(company, result.matched_terms)

    def test_short_ambiguous_company_alias_is_not_a_company_match(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/ambiguous",
            title="LG and KT are abbreviations in this unrelated document",
            summary="",
            body="",
        )

        result = classify_item(item, KEYWORDS)

        self.assertFalse(result.relevant)

    def test_korean_media_attribution_is_excluded_even_with_high_korea_term(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/reported",
            title="North Korea prepares new launch",
            summary="The claim was reported by Yonhap News Agency.",
            body="",
        )

        result = classify_item(item, KEYWORDS)

        self.assertFalse(result.relevant)
        self.assertEqual(result.confidence, "low")

    def test_direct_korean_government_statement_is_not_excluded(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/official",
            title="Republic of Korea issues an official statement",
            summary="The Ministry of Foreign Affairs published the statement directly.",
            body="",
        )

        result = classify_item(item, KEYWORDS)

        self.assertTrue(result.relevant)
        self.assertEqual(result.confidence, "high")

    def test_outlet_name_without_attribution_marker_is_not_excluded(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/outlet-subject",
            title="Yonhap News Agency joins an international safety initiative",
            summary="The Republic of Korea participated in the meeting.",
            body="",
        )

        result = classify_item(item, KEYWORDS)

        self.assertTrue(result.relevant)
        self.assertEqual(result.confidence, "high")

    def test_unrelated_attribution_in_another_sentence_is_not_excluded(self) -> None:
        item = MonitoredItem(
            source_id="x",
            source_label="Test",
            url="https://example.com/separate-sentences",
            title="Republic of Korea joins an international safety initiative",
            summary=(
                "According to the Ministry, the programme starts next year. "
                "Yonhap News Agency joined the initiative as an observer."
            ),
            body="",
        )

        result = classify_item(item, KEYWORDS)

        self.assertTrue(result.relevant)
        self.assertEqual(result.confidence, "high")


if __name__ == "__main__":
    unittest.main()
