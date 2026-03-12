import unittest

from src.monitor.models import MonitoredItem
from src.monitor.notifier import build_telegram_message


class NotifierTests(unittest.TestCase):
    def test_builds_korean_message(self) -> None:
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

        self.assertIn("[ADB 뉴스] 한국 관련 신규 알림", message)
        self.assertIn("관련도: 높음", message)
        self.assertIn("근거 키워드: 북한, 서울", message)
        self.assertIn("발행: 2026-03-12", message)
        self.assertIn("원문 제목: English title", message)
        self.assertIn("원문 요약: English summary", message)
        self.assertIn("원문 보기", message)


if __name__ == "__main__":
    unittest.main()
