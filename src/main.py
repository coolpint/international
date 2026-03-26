from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .monitor.config import load_keywords, load_sources
from .monitor.filtering import classify_item
from .monitor.notifier import send_telegram_message, telegram_is_configured
from .monitor.sources import collect_items
from .monitor.state import append_history, append_run_log, load_state, mark_notified, register_item, save_state


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = REPO_ROOT / "config" / "sources.json"
DEFAULT_KEYWORDS = REPO_ROOT / "config" / "keywords.json"
DEFAULT_STATE = REPO_ROOT / "data" / "state.json"
DEFAULT_HISTORY_DIR = REPO_ROOT / "data" / "history"
DEFAULT_RUN_LOG_DIR = REPO_ROOT / "data" / "run_logs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor UN sources for Korea-related updates.")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    parser.add_argument("--keywords", default=str(DEFAULT_KEYWORDS))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--run-log-dir", default=str(DEFAULT_RUN_LOG_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-telegram", action="store_true")
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    args = parse_args()
    run_at = utc_now_iso()

    if args.test_telegram:
        if not telegram_is_configured():
            print("[error] Telegram secrets not configured.", file=sys.stderr)
            return 1

        from .monitor.notifier import send_telegram_text

        send_telegram_text("international monitor 테스트 메시지")
        print("[summary] sent test telegram message")
        return 0

    sources = load_sources(Path(args.sources))
    keywords = load_keywords(Path(args.keywords))
    state = load_state(Path(args.state))

    bootstrapping = not state.get("bootstrapped", False)
    source_bootstrapped_at = state.setdefault("source_bootstrapped_at", {})
    if not source_bootstrapped_at and state.get("bootstrapped"):
        for record in state.get("items", {}).values():
            source_id = record.get("source_id")
            if not source_id:
                continue
            source_bootstrapped_at.setdefault(
                source_id,
                record.get("first_seen_at") or state.get("bootstrapped_at") or run_at,
            )
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
            source_reports.append(
                {
                    "source_id": source.id,
                    "source_label": source.label,
                    "enabled": True,
                    "status": "error",
                    "detail": str(exc),
                }
            )
            continue

        successful_source_ids.append(source.id)
        print(f"[source] {source.id}: collected {len(items)} items")
        source_bootstrapping = bootstrapping or source.id not in source_bootstrapped_at
        if source_bootstrapping and not bootstrapping:
            print(f"[bootstrap] New source detected for {source.id}; storing current relevant items without Telegram alerts.")
        source_reports.append(
            {
                "source_id": source.id,
                "source_label": source.label,
                "enabled": True,
                "status": "ok",
                "collected": len(items),
                "bootstrapping": source_bootstrapping,
            }
        )

        for item in items:
            classification = classify_item(item, keywords)
            if not classification.relevant:
                continue

            item.relevant = True
            item.confidence = classification.confidence
            item.matched_terms = classification.matched_terms
            relevant_items.append((item, source_bootstrapping))

    if bootstrapping:
        print("[bootstrap] First run detected; storing current relevant items without Telegram alerts.")

    telegram_ready = telegram_is_configured()
    if not telegram_ready:
        print("[info] Telegram secrets not configured; notifications will be skipped.")

    for item, source_bootstrapping in relevant_items:
        event = register_item(state, item, run_at, bootstrapping=bootstrapping or source_bootstrapping)
        if event is None:
            continue

        should_notify = (
            not bootstrapping
            and not args.dry_run
            and telegram_ready
            and item.confidence == "high"
            and event["event"] in {"new", "updated"}
        )

        event["notified"] = False

        if should_notify:
            try:
                send_telegram_message(item, event["event"])
            except Exception as exc:
                event["notification_error"] = str(exc)
                print(f"[warn] notify failed for {item.url}: {exc}", file=sys.stderr)
            else:
                mark_notified(state, item.url, run_at)
                event["notified"] = True

        events.append(event)

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
        "bootstrapping": bootstrapping,
        "telegram_ready": telegram_ready,
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
        save_state(Path(args.state), state)
        append_history(Path(args.history_dir), events)
        append_run_log(Path(args.run_log_dir), run_report)

    print(f"[summary] {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
