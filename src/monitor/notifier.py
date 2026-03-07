from __future__ import annotations

import html
import os

from .http import post_form
from .models import MonitoredItem


def telegram_is_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _trim_summary(text: str, limit: int = 280) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def send_telegram_message(item: MonitoredItem, event_type: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")

    summary = _trim_summary(item.summary or item.body)
    matched = ", ".join(item.matched_terms[:5])
    event_label = event_type.upper()

    lines = [
        f"<b>[{html.escape(item.source_label)}] {html.escape(item.title)}</b>",
        f"{html.escape(event_label)} | confidence: {html.escape(item.confidence)}",
    ]

    if matched:
        lines.append(f"match: {html.escape(matched)}")
    if item.published_at:
        lines.append(f"published: {html.escape(item.published_at)}")
    if summary:
        lines.append(html.escape(summary))

    lines.append(f'<a href="{html.escape(item.url, quote=True)}">Open source</a>')

    payload = {
        "chat_id": chat_id,
        "text": "\n".join(lines),
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    post_form(f"https://api.telegram.org/bot{token}/sendMessage", payload)

