from __future__ import annotations

import hashlib
from copy import deepcopy
import json
from datetime import datetime
from pathlib import Path

from .models import MonitoredItem


DEFAULT_STATE = {
    "bootstrapped": False,
    "source_bootstrapped_at": {},
    "items": {},
}


def load_state(path: Path) -> dict:
    if not path.exists():
        return deepcopy(DEFAULT_STATE)
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _content_hash(item: MonitoredItem) -> str:
    body = item.body if item.source_id in {"un_press_releases", "un_meetings_coverage"} else item.body[:4000]
    payload = "\n".join(
        [
            item.title.strip(),
            item.summary.strip(),
            body.strip(),
        ]
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def register_item(state: dict, item: MonitoredItem, run_at: str, bootstrapping: bool = False) -> dict | None:
    items = state.setdefault("items", {})
    existing = items.get(item.url)
    fingerprint = _content_hash(item)
    if item.archive_fallback:
        reference = {"advisory_id": "AA24-207A", "published_at": item.published_at,
                     "retrieval_url": item.retrieval_url, "last_checked_at": run_at}
        if existing is not None:
            # A dated PDF is evidence of the original advisory, not evidence of
            # a new revision of the blocked current web page. Preserve its hash
            # and notification history; never resend a format-only change.
            existing["archive_reference"] = reference
            existing["last_seen_at"] = run_at
            return None
        bootstrapping = True  # This verified 2024 archive predates monitoring.

    record = {
        "source_id": item.source_id,
        "source_label": item.source_label,
        "url": item.url,
        "title": item.title,
        "summary": item.summary[:500],
        "published_at": item.published_at,
        "content_hash": fingerprint,
        "confidence": item.confidence,
        "matched_terms": item.matched_terms,
        "last_seen_at": run_at,
        "last_event": "unchanged",
    }

    if existing is None:
        record["first_seen_at"] = run_at
        record["last_notified_at"] = None
        event_type = "bootstrap" if bootstrapping else "new"
    elif existing.get("content_hash") != fingerprint:
        record["first_seen_at"] = existing.get("first_seen_at", run_at)
        record["last_notified_at"] = existing.get("last_notified_at")
        event_type = "updated"
    else:
        existing["last_seen_at"] = run_at
        existing["confidence"] = item.confidence
        existing["matched_terms"] = item.matched_terms
        return None

    if item.archive_fallback:
        record["archive_reference"] = reference
    record["last_event"] = event_type
    items[item.url] = record

    return {
        "event": event_type,
        "run_at": run_at,
        "source_id": item.source_id,
        "source_label": item.source_label,
        "url": item.url,
        "title": item.title,
        "published_at": item.published_at,
        "confidence": item.confidence,
        "matched_terms": item.matched_terms,
        "notified": False,
    }


def mark_notified(state: dict, url: str, run_at: str) -> None:
    state.setdefault("items", {}).setdefault(url, {})
    state["items"][url]["last_notified_at"] = run_at


def append_history(history_dir: Path, events: list[dict]) -> None:
    if not events:
        return

    history_dir.mkdir(parents=True, exist_ok=True)
    event_time = datetime.fromisoformat(events[0]["run_at"].replace("Z", "+00:00"))
    history_path = history_dir / f"{event_time:%Y-%m}.ndjson"

    with history_path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def append_run_log(run_log_dir: Path, report: dict) -> None:
    run_log_dir.mkdir(parents=True, exist_ok=True)
    event_time = datetime.fromisoformat(report["run_at"].replace("Z", "+00:00"))
    report_path = run_log_dir / f"{event_time:%Y-%m}.ndjson"

    with report_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n")
