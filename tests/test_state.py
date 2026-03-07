import unittest

from src.monitor.models import MonitoredItem
from src.monitor.state import register_item


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

        unchanged = register_item(state, item, "2026-03-07T08:00:00Z")
        self.assertIsNone(unchanged)

        item.body = "Body changed"
        updated = register_item(state, item, "2026-03-07T16:00:00Z")
        self.assertEqual(updated["event"], "updated")


if __name__ == "__main__":
    unittest.main()
