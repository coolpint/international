import json
import os
import unittest
from unittest.mock import patch

from src.monitor.models import MonitoredItem
from src.monitor.notifier import (
    build_slack_message, build_telegram_message, send_slack_message,
    send_slack_text, slack_is_configured,
)


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


class SlackNotifierTests(unittest.TestCase):
    WEBHOOK = "https://hooks.slack.com/services/TTEST/BTEST/fake_test_token"

    def make_item(self) -> MonitoredItem:
        return MonitoredItem(
            source_id="adb_news", source_label="ADB News",
            url="https://www.adb.org/news/example", title="English title",
            summary="English summary", body="", published_at="2026-03-12",
            confidence="high", matched_terms=["North Korea", "Seoul"],
        )

    def test_builds_korean_message_with_original_text_and_url(self) -> None:
        message = build_slack_message(self.make_item(), "new")
        for expected in (
            "[ADB 뉴스] 한국 관련 신규 알림", "관련도: 높음",
            "근거 키워드: 북한, 서울", "발행: 2026-03-12",
            "원문 제목: English title", "원문 요약: English summary",
            "원문 URL: https://www.adb.org/news/example",
        ):
            self.assertIn(expected, message)

    def test_only_valid_international_webhook_is_configured(self) -> None:
        with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": self.WEBHOOK}):
            self.assertTrue(slack_is_configured())
        invalid_urls = (
            "", "  ", "http://hooks.slack.com/services/T/B/token",
            "https://example.com/services/T/B/token",
            "https://hooks.slack.com.evil.test/services/T/B/token",
            "https://user@hooks.slack.com/services/T/B/token",
            "https://hooks.slack.com:443/services/T/B/token",
            self.WEBHOOK + "?secret=1", self.WEBHOOK + "#fragment",
            self.WEBHOOK + "?", self.WEBHOOK + "#",
            " " + self.WEBHOOK, self.WEBHOOK + "\n",
            "https://hooks.slack.com/services/T/B", "https://[invalid",
        )
        for url in invalid_urls:
            with self.subTest(url=url), patch.dict(os.environ, {"SLACK_WEBHOOK_URL": url}):
                self.assertFalse(slack_is_configured())
                with patch("src.monitor.notifier.request_text") as request:
                    with self.assertRaises(RuntimeError) as error:
                        send_slack_text("test")
                    request.assert_not_called()
                    self.assertNotIn("services/", str(error.exception))
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(slack_is_configured())

    def test_posts_plain_json_without_http_retries(self) -> None:
        with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": self.WEBHOOK}), patch(
            "src.monitor.notifier.request_text", return_value=("ok\n", {})
        ) as request:
            send_slack_text("한국 <@U123> <!channel> & *literal*")
        request.assert_called_once()
        args = request.call_args.kwargs
        self.assertEqual(args["url"], self.WEBHOOK)
        self.assertEqual(args["method"], "POST")
        self.assertEqual(args["retry_attempts"], 0)
        payload = json.loads(args["data"])
        self.assertEqual(payload["text"], "한국 &lt;@U123&gt; &lt;!channel&gt; &amp; *literal*")
        self.assertFalse(payload["mrkdwn"])
        self.assertEqual(payload["parse"], "none")
        self.assertFalse(payload["link_names"])
        self.assertFalse(payload["unfurl_links"])
        self.assertFalse(payload["unfurl_media"])

    def test_message_sender_uses_shared_delivery(self) -> None:
        item = self.make_item()
        with patch("src.monitor.notifier.send_slack_text") as send:
            send_slack_message(item, "updated")
        send.assert_called_once_with(build_slack_message(item, "updated"))

    def test_rejection_and_transport_errors_are_redacted(self) -> None:
        for response in ("invalid_payload", '{"ok":true}', "", "secret response"):
            with self.subTest(response=response), patch.dict(
                os.environ, {"SLACK_WEBHOOK_URL": self.WEBHOOK}
            ), patch("src.monitor.notifier.request_text", return_value=(response, {})):
                with self.assertRaises(RuntimeError) as error:
                    send_slack_text("private article text")
                self.assertEqual(str(error.exception), "Slack delivery was not confirmed; queued for retry")
        with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": self.WEBHOOK}), patch(
            "src.monitor.notifier.request_text",
            side_effect=RuntimeError(self.WEBHOOK + " private article text"),
        ) as request:
            with self.assertRaises(RuntimeError) as error:
                send_slack_text("private article text")
        request.assert_called_once()
        self.assertEqual(str(error.exception), "Slack delivery was not confirmed; queued for retry")
        self.assertIsNone(error.exception.__cause__)
        self.assertTrue(error.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
