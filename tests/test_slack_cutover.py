"""Offline regression coverage for the Telegram-to-Slack delivery boundary."""
import argparse
from contextlib import ExitStack
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src import main
from src.monitor.delivery import queue_item
from src.monitor.models import Classification, MonitoredItem, SourceConfig
from src.monitor.sources import CollectionResult
from src.monitor.state import load_state, register_item, save_state


class SlackCutoverTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.path = self.root / "state.json"
        self.args = argparse.Namespace(
            sources="unused", keywords="unused", state=str(self.path),
            history_dir=str(self.root / "history"),
            run_log_dir=str(self.root / "logs"), dry_run=False,
            test_slack=False, backfill=False,
        )
        self.item = MonitoredItem(
            "source", "Source", "https://example.org/article", "Korea policy",
            "Republic of Korea", "Full body Republic of Korea",
            confidence="high", matched_terms=["Korea"],
        )
        self.state = {
            "bootstrapped": True,
            "source_bootstrapped_at": {"source": "2026-10-20T00:00:00Z"},
            "items": {},
        }
        self.stack.enter_context(patch("src.main.parse_args", return_value=self.args))
        self.stack.enter_context(patch("src.main.load_sources", return_value=[
            SourceConfig("source", "Source", "rss_xml", True,
                         "https://example.org/feed", 20),
        ]))
        self.stack.enter_context(patch("src.main.load_keywords", return_value={}))
        self.stack.enter_context(patch("src.main.classify_item", return_value=
                                      Classification(True, "high", ["Korea"])))
        self.collect = self.stack.enter_context(patch("src.main.collect_items"))
        self.collect.return_value = self.collection(self.item)
        self.slack_item = self.stack.enter_context(patch("src.main.send_slack_message"))
        self.slack_text = self.stack.enter_context(patch("src.main.send_slack_text"))
        self.telegram_item = self.stack.enter_context(patch("src.monitor.notifier.send_telegram_message"))
        self.telegram_text = self.stack.enter_context(patch("src.monitor.notifier.send_telegram_text"))
        self.telegram_http = self.stack.enter_context(patch("src.monitor.notifier.post_form"))
        self.stack.enter_context(patch("src.monitor.notifier.request_text",
                                      side_effect=AssertionError("Network forbidden in cutover tests")))
        self.stack.enter_context(patch("sys.stdout", new=io.StringIO()))
        self.stack.enter_context(patch("sys.stderr", new=io.StringIO()))
        self.stack.enter_context(patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "fake_legacy_token",
            "TELEGRAM_CHAT_ID": "fake_legacy_chat",
        }, clear=True))

    @staticmethod
    def collection(*items):
        result = CollectionResult()
        result.candidates = result.succeeded = len(items)
        result.extend(items)
        return result

    def assert_no_telegram(self):
        self.telegram_item.assert_not_called()
        self.telegram_text.assert_not_called()
        self.telegram_http.assert_not_called()

    def pending_legacy_state(self):
        event = register_item(self.state, self.item, "2026-10-20T00:00:00Z")
        queue_item(self.state, self.item, event["event"])
        save_state(self.path, self.state)

    def test_delivered_telegram_hash_is_not_replayed_or_relabelled(self):
        register_item(self.state, self.item, "2026-10-20T00:00:00Z")
        record = self.state["items"][self.item.url]
        record.update(last_notified_at="2026-10-20T00:00:00Z",
                      last_notified_hash=record["content_hash"],
                      last_notified_channel="telegram")
        old_hash = record["last_notified_hash"]
        save_state(self.path, self.state)
        with patch("src.main.slack_is_configured", return_value=True):
            self.assertEqual(main.main(), 0)
        record = load_state(self.path)["items"][self.item.url]
        self.assertEqual(record["last_notified_hash"], old_hash)
        self.assertEqual(record["last_notified_at"], "2026-10-20T00:00:00Z")
        self.assertEqual(record["last_notified_channel"], "telegram")
        self.slack_item.assert_not_called()
        self.slack_text.assert_not_called()
        self.assert_no_telegram()

    def test_pending_legacy_outbox_retries_to_slack_across_runs(self):
        self.pending_legacy_state()
        self.slack_item.side_effect = TimeoutError("mock failure")
        with patch("src.main.slack_is_configured", return_value=True):
            self.assertEqual(main.main(), 1)
            failed = load_state(self.path)
            entry = failed["notification_outbox"]["item:" + self.item.url]
            self.assertEqual(entry["attempts"], 1)
            self.assertEqual(entry["last_error"], "TimeoutError")
            self.assertIsNone(failed["items"][self.item.url]["last_notified_at"])
            self.assertNotIn("last_notified_channel", failed["items"][self.item.url])
            self.collect.return_value = self.collection()
            self.slack_item.side_effect = None
            self.assertEqual(main.main(), 0)
        delivered = load_state(self.path)
        self.assertFalse(delivered["notification_outbox"])
        record = delivered["items"][self.item.url]
        self.assertEqual(record["last_notified_channel"], "slack")
        self.assertEqual(record["last_notified_hash"], record["content_hash"])
        self.assertEqual(self.slack_item.call_count, 2)
        self.assert_no_telegram()

    def test_only_telegram_credentials_keep_pending_and_fail(self):
        self.pending_legacy_state()
        self.assertEqual(main.main(), 1)
        persisted = load_state(self.path)
        self.assertIn("item:" + self.item.url, persisted["notification_outbox"])
        self.slack_item.assert_not_called()
        self.slack_text.assert_not_called()
        self.assert_no_telegram()

    def test_test_slack_uses_only_slack_and_skips_collection(self):
        self.args.test_slack = True
        with patch.dict(os.environ, {
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/TTEST/BTEST/fake_token",
        }):
            self.assertEqual(main.main(), 0)
        self.slack_text.assert_called_once_with("international monitor 테스트 메시지")
        self.slack_item.assert_not_called()
        self.collect.assert_not_called()
        self.assertFalse(self.path.exists())
        self.assert_no_telegram()

    def test_test_slack_without_webhook_fails_without_telegram_fallback(self):
        self.args.test_slack = True
        self.assertEqual(main.main(), 1)
        self.slack_text.assert_not_called()
        self.slack_item.assert_not_called()
        self.collect.assert_not_called()
        self.assertFalse(self.path.exists())
        self.assert_no_telegram()


if __name__ == "__main__":
    unittest.main()
