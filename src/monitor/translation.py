from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .http import post_json


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_TRANSLATION_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class NotificationTranslation:
    title: str
    summary: str


def translation_is_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def translate_alert_text(title: str, summary: str) -> NotificationTranslation:
    original = NotificationTranslation(title=title, summary=summary)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not (title or summary):
        return original

    model = os.environ.get("OPENAI_TRANSLATION_MODEL", DEFAULT_TRANSLATION_MODEL)
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "Translate the provided alert title and summary into natural Korean for a Telegram news alert. "
                    "Preserve facts, dates, numbers, acronyms, and organization names. Do not add information."
                ),
            },
            {
                "role": "user",
                "content": f"Title:\n{title}\n\nSummary:\n{summary}",
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "telegram_translation",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "title_ko": {"type": "string"},
                        "summary_ko": {"type": "string"},
                    },
                    "required": ["title_ko", "summary_ko"],
                    "additionalProperties": False,
                },
            }
        },
    }

    try:
        response = post_json(
            OPENAI_RESPONSES_URL,
            payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        data = json.loads(_response_output_text(response))
    except Exception as exc:
        print(f"[warn] translation failed: {exc}")
        return original

    title_ko = str(data.get("title_ko") or title).strip()
    summary_ko = str(data.get("summary_ko") or summary).strip()
    return NotificationTranslation(title=title_ko, summary=summary_ko)


def _response_output_text(response: object) -> str:
    if not isinstance(response, dict):
        raise RuntimeError("Unexpected OpenAI response type.")

    texts = []
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and content.get("text"):
                texts.append(str(content["text"]))

    text = "".join(texts).strip()
    if not text:
        raise RuntimeError("OpenAI response did not include output text.")
    return text
