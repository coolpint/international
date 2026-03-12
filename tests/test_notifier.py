import unittest
from unittest.mock import patch

from src.monitor.models import MonitoredItem
from src.monitor.notifier import build_telegram_message
from src.monitor.translation import NotificationTranslation


class NotifierTests(unittest.TestCase):
    @patch("src.monitor.notifier.translate_alert_text")
    def test_builds_korean_message(self, mock_translate) -> None:
        mock_translate.return_value = NotificationTranslation(
            title="한국어 제목",
            summary="한국어 요약",
        )
        item = MonitoredItem(
            source_id="adb_news",
            source_label="ADB News",
            url="https://www.adb.org/news/example",
            title="English title",
            summary="English summary",
            body="",
            published_at="2026-03-12",
            confidence="high",
            matched_terms=["North Korea", "Seoul"],
        )

        message = build_telegram_message(item, "new")

        self.assertIn("[ADB 뉴스] 한국어 제목", message)
        self.assertIn("신규 | 관련도: 높음", message)
        self.assertIn("근거 키워드: 북한, 서울", message)
        self.assertIn("발행: 2026-03-12", message)
        self.assertIn("한국어 요약", message)
        self.assertIn("원문 보기", message)


if __name__ == "__main__":
    unittest.main()
