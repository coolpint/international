"""Offline integration coverage for the narrowly scoped UN renderer baseline."""
import argparse
from contextlib import ExitStack
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src import main
from src.monitor.delivery import queue_item
from src.monitor.models import Classification, MonitoredItem, SourceConfig
from src.monitor.sources import CollectionResult
from src.monitor.state import load_state, register_item, save_state


REVISION = "2026-10-un-browser"
RUN_AT = "2026-10-23T10:00:00Z"
OLD_BOOTSTRAP = "2026-08-01T00:00:00Z"


class UnPartialBaselineTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.path = self.root / "state.json"
        self.source = SourceConfig(
            "un_press_releases", "UN Press Releases", "un_press_listing", True,
            "https://press.un.org/en/content/press-release", 20,
            options={"render_javascript": True, "collection_revision": REVISION},
        )
        self.good = self.article("sgsm23342")
        self.failed_url = "https://press.un.org/en/2026/sgsm23339.doc.htm"
        self.state = {
            "bootstrapped": True, "bootstrapped_at": OLD_BOOTSTRAP,
            "source_bootstrapped_at": {self.source.id: OLD_BOOTSTRAP},
            "collection_revisions": {self.source.id: "previous-transport"}, "items": {},
        }
        self.args = argparse.Namespace(
            sources="unused", keywords="unused", state=str(self.path),
            history_dir=str(self.root / "history"), run_log_dir=str(self.root / "logs"),
            dry_run=False, test_slack=False, backfill=False,
        )
        for name, value in (
            ("parse_args", self.args), ("load_sources", [self.source]),
            ("load_keywords", {}), ("classify_item", Classification(True, "high", ["Korea"])),
            ("slack_is_configured", True), ("utc_now_iso", RUN_AT),
        ):
            self.stack.enter_context(patch("src.main." + name, return_value=value))
        self.collect = self.stack.enter_context(patch("src.main.collect_items"))
        self.send = self.stack.enter_context(patch("src.main.send_slack_message"))
        self.health_send = self.stack.enter_context(patch("src.main.send_slack_text"))
        self.stack.enter_context(patch("src.monitor.notifier.request_text", side_effect=AssertionError("Network forbidden")))
        self.stack.enter_context(patch("src.monitor.notifier.post_form", side_effect=AssertionError("Network forbidden")))
        self.stack.enter_context(patch("sys.stdout", new=io.StringIO()))
        self.stack.enter_context(patch("sys.stderr", new=io.StringIO()))
        save_state(self.path, self.state)

    def article(self, document):
        return MonitoredItem(
            self.source.id, self.source.label,
            f"https://press.un.org/en/2026/{document}.doc.htm", "Korea cooperation announcement",
            "Republic of Korea cooperation", "Verified full article about Republic of Korea cooperation.",
            published_at="2026-10-23T00:00:00Z", confidence="high", matched_terms=["Korea"],
        )

    def result(self, items, failed_urls=()):
        result = CollectionResult()
        result.extend(items)
        result.succeeded = len(items)
        result.failed = len(failed_urls)
        result.candidates = len(items) + len(failed_urls)
        result.errors = [{"url": url, "detail": "HTTP 406 from UN Press"} for url in failed_urls]
        result.document_urls = [item.url for item in items] + list(failed_urls)
        return result

    def run_with(self, result):
        self.collect.return_value = result
        code = main.main()
        return code, load_state(self.path)

    def logs(self):
        return [json.loads(line) for file in (self.root / "logs").glob("*.ndjson") for line in file.read_text().splitlines()]

    def test_partial_baseline_preserves_health_and_suppresses_only_old_documents(self):
        _, state = self.run_with(self.result([self.good], [self.failed_url]))
        self.send.assert_not_called()
        self.assertEqual(state["collection_revisions"][self.source.id], REVISION)
        metadata = state["collection_revision_baselines"][self.source.id]
        self.assertEqual(metadata["revision"], REVISION)
        self.assertEqual(metadata["run_at"], RUN_AT)
        self.assertEqual(metadata["collection_status"], "partial")
        self.assertEqual(metadata["verified_documents"], 1)
        self.assertIn(self.failed_url, json.dumps(state["deferred_collection_baselines"][self.source.id]))
        self.assertEqual(state["source_bootstrapped_at"][self.source.id], OLD_BOOTSTRAP)
        self.assertEqual(state["bootstrapped_at"], OLD_BOOTSTRAP)
        first_log = self.logs()[0]
        self.assertEqual(first_log["status"], "partial_failure")
        self.assertEqual(first_log["sources"][0]["status"], "partial")
        self.assertEqual(first_log["sources"][0]["errors"][0]["url"], self.failed_url)
        self.health_send.assert_called_once()

        # A later genuine publication can notify while a known baseline URL recovers silently.
        recovered = self.article("sgsm23339")
        new_article = self.article("sgsm23399")
        _, state = self.run_with(self.result([self.good, recovered, new_article]))
        self.send.assert_called_once()
        self.assertEqual(self.send.call_args.args[0].url, new_article.url)
        self.assertIsNone(state["items"][recovered.url]["last_notified_at"])
        self.assertEqual(state["items"][new_article.url]["last_notified_channel"], "slack")
        self.assertNotIn(self.failed_url, json.dumps(state.get("deferred_collection_baselines", {})))
        self.assertEqual(state["collection_revision_baselines"][self.source.id], metadata)
        recovered.title = "Updated Korea cooperation announcement"
        self.run_with(self.result([recovered]))
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual(self.send.call_args.args[0].url, recovered.url)
        self.assertEqual(self.send.call_args.args[1], "updated")

    def test_meetings_coverage_uses_same_explicit_partial_exception(self):
        self.source.id = "un_meetings_coverage"
        self.source.label = "UN Meetings Coverage"
        self.source.list_url = "https://press.un.org/en/content/meetings-coverage"
        self.state["source_bootstrapped_at"] = {self.source.id: OLD_BOOTSTRAP}
        self.state["collection_revisions"] = {self.source.id: "previous-transport"}
        save_state(self.path, self.state)
        _, state = self.run_with(self.result([self.article("sc23342")], [self.failed_url]))
        self.assertEqual(state["collection_revisions"][self.source.id], REVISION)
        self.assertEqual(state["collection_revision_baselines"][self.source.id]["collection_status"], "partial")
        self.send.assert_not_called()

    def test_total_failure_does_not_confirm_revision(self):
        code, state = self.run_with(self.result([], [self.failed_url]))
        self.assertEqual(code, 1)
        self.assertEqual(state["collection_revisions"][self.source.id], "previous-transport")
        self.assertNotIn(self.source.id, state.get("collection_revision_baselines", {}))
        self.send.assert_not_called()
        self.assertEqual(self.logs()[0]["status"], "total_failure")

    def test_new_source_partial_does_not_confirm_revision(self):
        self.state["source_bootstrapped_at"] = {}
        self.state["collection_revisions"] = {}
        save_state(self.path, self.state)
        _, state = self.run_with(self.result([self.good], [self.failed_url]))
        self.assertNotIn(self.source.id, state.get("collection_revisions", {}))
        self.assertNotIn(self.source.id, state.get("collection_revision_baselines", {}))
        self.send.assert_not_called()

    def test_exception_is_not_applied_to_other_sources_revisions_or_transports(self):
        cases = (
            ("other_source", REVISION, True),
            ("un_press_releases", "future-revision", True),
            ("un_press_releases", REVISION, False),
        )
        for source_id, revision, render in cases:
            with self.subTest(source_id=source_id, revision=revision, render=render):
                self.source.id = source_id
                self.source.options = {"collection_revision": revision, "render_javascript": render}
                self.state["source_bootstrapped_at"] = {source_id: OLD_BOOTSTRAP}
                self.state["collection_revisions"] = {source_id: "previous-transport"}
                save_state(self.path, self.state)
                item = self.article("sgsm23342")
                _, state = self.run_with(self.result([item], [self.failed_url]))
                self.assertEqual(state["collection_revisions"][source_id], "previous-transport")
                self.assertNotIn(source_id, state.get("collection_revision_baselines", {}))
        self.send.assert_not_called()

    def test_pending_outbox_is_preserved_when_partial_baseline_send_fails(self):
        pending = self.article("sgsm23000")
        event = register_item(self.state, pending, OLD_BOOTSTRAP)
        queue_item(self.state, pending, event["event"])
        original = self.state["notification_outbox"]["item:" + pending.url].copy()
        save_state(self.path, self.state)
        self.send.side_effect = TimeoutError("offline fixture")
        code, state = self.run_with(self.result([self.good], [self.failed_url]))
        self.assertEqual(code, 1)
        entry = state["notification_outbox"]["item:" + pending.url]
        self.assertEqual(entry["item"], original["item"])
        self.assertEqual(entry["content_hash"], original["content_hash"])
        self.assertEqual(entry["attempts"], 1)
        self.assertEqual(self.send.call_args.args[0].url, pending.url)
        self.assertEqual(state["collection_revisions"][self.source.id], REVISION)
        self.assertIsNone(state["items"][pending.url]["last_notified_at"])


if __name__ == "__main__":
    unittest.main()
