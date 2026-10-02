import unittest

from src.monitor.models import MonitoredItem
from src.monitor.state import mark_notified, register_item


class StateTests(unittest.TestCase):
    def test_register_new_and_updated_items(self) -> None:
        state = {"bootstrapped": True, "items": {}}
        item = MonitoredItem(
            source_id="source",
            source_label="Source",
            url="https://example.com/story",
            title="Title",
            summary="Summary",
            body="Body",
            confidence="high",
            matched_terms=["North Korea"],
        )

        created = register_item(state, item, "2026-03-07T00:00:00Z")
        self.assertEqual(created["event"], "new")
        mark_notified(state, item.url, "2026-03-07T00:00:01Z")

        unchanged = register_item(state, item, "2026-03-07T08:00:00Z")
        self.assertIsNone(unchanged)

        item.body = "Body changed"
        updated = register_item(state, item, "2026-03-07T16:00:00Z")
        self.assertEqual(updated["event"], "updated")
        retry_updated = register_item(state, item, "2026-03-08T00:00:00Z")
        self.assertEqual(retry_updated["event"], "retry")

    def test_unnotified_high_item_retries_until_marked_notified(self) -> None:
        state = {"bootstrapped": True, "items": {}}
        item = MonitoredItem(
            source_id="nyt_korea_news",
            source_label="The New York Times — Korea",
            url="https://news.google.com/rss/articles/story",
            title="South Korea policy shift",
            summary="",
            body="",
            confidence="high",
            matched_terms=["NYT Korea priority source"],
        )

        created = register_item(state, item, "2026-08-18T00:00:00Z")
        retried = register_item(state, item, "2026-08-18T08:00:00Z")
        self.assertEqual(created["event"], "new")
        self.assertEqual(retried["event"], "retry")

        mark_notified(state, item.url, "2026-08-18T08:00:01Z")
        unchanged = register_item(state, item, "2026-08-18T16:00:00Z")
        self.assertIsNone(unchanged)

    def test_bootstrap_item_is_not_retried_as_missed_notification(self) -> None:
        state = {"bootstrapped": True, "items": {}}
        item = MonitoredItem(
            source_id="wsj_korea_news",
            source_label="The Wall Street Journal — Korea",
            url="https://news.google.com/rss/articles/baseline",
            title="North Korea update",
            summary="",
            body="",
            confidence="high",
        )

        created = register_item(
            state,
            item,
            "2026-08-18T00:00:00Z",
            bootstrapping=True,
        )
        unchanged = register_item(state, item, "2026-08-18T08:00:00Z")

        self.assertEqual(created["event"], "bootstrap")
        self.assertIsNone(unchanged)

    def test_legacy_notified_item_migrates_without_retry(self) -> None:
        item = MonitoredItem(
            source_id="source",
            source_label="Source",
            url="https://example.com/legacy",
            title="South Korea update",
            summary="",
            body="",
            confidence="high",
        )
        state = {"bootstrapped": True, "items": {}}
        register_item(state, item, "2026-08-17T00:00:00Z")
        record = state["items"][item.url]
        record["last_notified_at"] = "2026-08-17T00:00:01Z"
        record.pop("last_notified_hash")

        unchanged = register_item(state, item, "2026-08-18T00:00:00Z")

        self.assertIsNone(unchanged)
        self.assertEqual(record["last_notified_hash"], record["content_hash"])


if __name__ == "__main__":
    unittest.main()
