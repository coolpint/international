from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .monitor.config import load_keywords, load_sources
from .monitor.filtering import classify_item
from .monitor.notifier import send_slack_message, send_slack_text, slack_is_configured
from .monitor.backfill import collect_backfill, REPAIR_SOURCES
from .monitor.delivery import queue_item, queue_health, collection_status, deliver_outbox
from .monitor.models import Classification, MonitoredItem, SourceConfig
from .monitor.sources import collect_items, CollectionResult
from .monitor.state import append_history, append_run_log, load_state, register_item, save_state


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = REPO_ROOT / "config" / "sources.json"
DEFAULT_KEYWORDS = REPO_ROOT / "config" / "keywords.json"
DEFAULT_STATE = REPO_ROOT / "data" / "state.json"
DEFAULT_HISTORY_DIR = REPO_ROOT / "data" / "history"
DEFAULT_RUN_LOG_DIR = REPO_ROOT / "data" / "run_logs"
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor UN sources for Korea-related updates.")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    parser.add_argument("--keywords", default=str(DEFAULT_KEYWORDS))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--run-log-dir", default=str(DEFAULT_RUN_LOG_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backfill", action="store_true", help="Replay historically observed failed official detail URLs")
    parser.add_argument("--test-slack", action="store_true")
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _option_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()]


def _apply_source_default_classification(
    item: MonitoredItem,
    classification: Classification,
    source: SourceConfig,
) -> Classification:
    default_confidence = str(source.options.get("default_confidence", "")).strip().lower()
    if default_confidence not in CONFIDENCE_RANK:
        return classification

    current_rank = CONFIDENCE_RANK.get(classification.confidence, 0) if classification.relevant else 0
    if CONFIDENCE_RANK[default_confidence] <= current_rank:
        return classification

    default_terms = _option_string_list(source.options.get("default_matched_terms")) or [source.label]
    matched_terms = list(classification.matched_terms)
    for term in default_terms:
        if term not in matched_terms:
            matched_terms.append(term)

    return Classification(relevant=True, confidence=default_confidence, matched_terms=matched_terms)


def main() -> int:
    args = parse_args()
    run_at = utc_now_iso()

    if args.test_slack:
        if not slack_is_configured():
            print("[error] Slack secrets not configured.", file=sys.stderr)
            return 1

        send_slack_text("international monitor 테스트 메시지")
        print("[summary] sent test slack message")
        return 0

    sources = load_sources(Path(args.sources))
    keywords = load_keywords(Path(args.keywords))
    state = load_state(Path(args.state))

    bootstrapping = not state.get("bootstrapped", False)
    source_bootstrapped_at = state.setdefault("source_bootstrapped_at", {})
    if not state.get("source_bootstrap_migrated") and not source_bootstrapped_at and state.get("bootstrapped"):
        for record in state.get("items", {}).values():
            source_id = record.get("source_id")
            if not source_id:
                continue
            source_bootstrapped_at.setdefault(
                source_id,
                record.get("first_seen_at") or state.get("bootstrapped_at") or run_at,
            )
    state["source_bootstrap_migrated"] = True
    collection_revisions = state.setdefault("collection_revisions", {})
    deferred_baselines = state.setdefault("deferred_collection_baselines", {})
    successful_revisions = {}
    relevant_items = []
    events = []
    successful_source_ids = []
    source_reports = []

    for source in sources:
        if not source.enabled:
            reason = source.note or "disabled"
            print(f"[skip] {source.id}: {reason}")
            source_reports.append(
                {
                    "source_id": source.id,
                    "source_label": source.label,
                    "enabled": False,
                    "status": "disabled",
                    "detail": reason,
                }
            )
            continue

        try:
            items = collect_items(source)
        except Exception as exc:
            print(f"[error] {source.id}: {exc}", file=sys.stderr)
            items = CollectionResult()
            items.selected_url = source.list_url
            items.failure_reason = str(exc)
            items.candidates = items.failed = items.filtered = None

        collection_report = items.report()
        if items.status in {"ok", "empty", "filtered"}:
            successful_source_ids.append(source.id)
        print(f"[source] {source.id}: {collection_report}")
        revision = source.options.get("collection_revision")
        revision_changed = revision is not None and collection_revisions.get(source.id) != revision
        source_bootstrapping = bootstrapping or source.id not in source_bootstrapped_at or revision_changed
        if revision_changed and items.status == "ok" and items:
            successful_revisions[source.id] = revision
        # A repaired, already-bootstrapped UN source can keep collecting valid
        # documents while a few URLs remain blocked. Confirm only the observed
        # notification baseline, without changing the source's partial status.
        partial_un_baseline = (
            revision_changed
            and revision == "2026-10-un-browser"
            and source.id in {"un_press_releases", "un_meetings_coverage"}
            and source.type == "un_press_listing"
            and source.options.get("render_javascript") is True
            and source.id in source_bootstrapped_at
            and not bootstrapping
            and items.status == "partial"
            and items.succeeded > 0
            and bool(items)
        )
        if partial_un_baseline:
            successful_revisions[source.id] = revision
            known = set(getattr(items, "document_urls", []))
            known.update(error["url"] for error in items.errors
                         if isinstance(error, dict) and error.get("url"))
            known.difference_update(item.url for item in items)
            deferred_baselines[source.id] = sorted(known)
            state.setdefault("collection_revision_baselines", {})[source.id] = {
                "revision": revision, "run_at": run_at,
                "collection_status": "partial", "verified_documents": len(items),
            }
        if source_bootstrapping and not bootstrapping:
            print(f"[bootstrap] Baseline required for {source.id}; storing current relevant items without Slack alerts.")
        source_reports.append(
            {
                "source_id": source.id,
                "source_label": source.label,
                "enabled": True,
                **collection_report,
                "bootstrapping": source_bootstrapping,
            }
        )

        if getattr(args, "backfill", False) and source.id in REPAIR_SOURCES:
            recovered = collect_backfill(source, Path(args.run_log_dir), items)
            if recovered is not None:
                source_reports[-1]["backfill"] = recovered.report()
                print(f"[backfill] {source.id}: {recovered.report()}")
                items.extend(recovered)

        for item in items:
            deferred_baseline = item.url in deferred_baselines.get(source.id, [])
            if deferred_baseline:
                deferred_baselines[source.id].remove(item.url)
            classification = classify_item(item, keywords)
            classification = _apply_source_default_classification(item, classification, source)
            if not classification.relevant:
                continue

            item.relevant = True
            item.confidence = classification.confidence
            item.matched_terms = classification.matched_terms
            relevant_items.append((item, source_bootstrapping or deferred_baseline))

    if bootstrapping:
        print("[bootstrap] First run detected; storing current relevant items without Slack alerts.")

    # Retain existing delivery hashes as the cutover baseline; only pending/new
    # items move to Slack. Historical Telegram deliveries are not replayed.
    state["notification_channel"] = "slack"
    slack_ready = slack_is_configured()
    if not slack_ready:
        print("[info] Slack secrets not configured; notifications will be skipped.")

    for item, source_bootstrapping in relevant_items:
        event = register_item(state, item, run_at, bootstrapping=bootstrapping or source_bootstrapping)
        if event is None:
            continue

        should_notify = (
            not bootstrapping
            and not source_bootstrapping
            and item.confidence == "high"
            and event["event"] in {"new", "updated"}
        )

        event["notified"] = False

        if should_notify:
            queue_item(state, item, event["event"])

        events.append(event)

    status = collection_status(source_reports)
    queue_health(state, source_reports, run_at)
    delivery = {"delivered": 0, "failed": 0, "pending": len(state.get("notification_outbox", {}))}
    if not args.dry_run and slack_ready:
        delivery = deliver_outbox(state, run_at, send_slack_message, send_slack_text,
                                  lambda: save_state(Path(args.state), state))
        for event in events:
            record = state["items"][event["url"]]
            event["notified"] = (record.get("last_notified_at") == run_at
                                 and record.get("last_notified_hash") == record.get("content_hash"))
    print(f"[delivery] {delivery}")
    if status != "success":
        print(f"::warning::Collection status: {status}; see source reports and persisted health alerts")
    print(f"[status] {status}")

    summary = {
        "relevant_items": len(relevant_items),
        "events": len(events),
        "new": sum(1 for event in events if event["event"] == "new"),
        "updated": sum(1 for event in events if event["event"] == "updated"),
        "bootstrap": sum(1 for event in events if event["event"] == "bootstrap"),
        "notified": sum(1 for event in events if event.get("notified")),
    }
    run_report = {
        "run_at": run_at,
        "status": status,
        "delivery": delivery,
        "bootstrapping": bootstrapping,
        "slack_ready": slack_ready,
        "notification_channel": "slack",
        "sources": source_reports,
        "summary": summary,
    }

    if args.dry_run:
        print("[dry-run] State files were not changed.")
    else:
        if bootstrapping:
            state["bootstrapped"] = True
            state["bootstrapped_at"] = run_at
        for source_id in successful_source_ids:
            source_bootstrapped_at.setdefault(source_id, run_at)
        collection_revisions.update(successful_revisions)
        save_state(Path(args.state), state)
        append_history(Path(args.history_dir), events)
        append_run_log(Path(args.run_log_dir), run_report)

    print(f"[summary] {summary}")
    return 1 if status == "total_failure" or (delivery["pending"] and not args.dry_run) else 0


if __name__ == "__main__":
    raise SystemExit(main())
