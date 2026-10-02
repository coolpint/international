from __future__ import annotations

import html
import os

from .http import post_form
from .models import MonitoredItem


SOURCE_LABELS_KO = {
    "UN News": "유엔 뉴스",
    "UN Press Releases": "유엔 보도자료",
    "UN Meetings Coverage": "유엔 회의보도",
    "UNCTAD Publications": "UNCTAD 간행물",
    "UNRISD News": "UNRISD 뉴스",
    "UNRISD Publications": "UNRISD 간행물",
    "WTO Latest News": "WTO 최신 뉴스",
    "ILO Newsroom": "ILO 뉴스룸",
    "The New York Times — Korea": "뉴욕타임스 한국 뉴스",
    "The Wall Street Journal — Korea": "월스트리트저널 한국 뉴스",
    "ADB News": "ADB 뉴스",
    "World Bank News": "세계은행 뉴스",
    "AIIB News": "AIIB 뉴스",
    "BIS Press Releases": "BIS 보도자료",
    "ECB Press": "ECB 보도자료",
    "EIB Press Releases": "EIB 보도자료",
    "DOJ Press Releases": "미 법무부 보도자료",
    "U.S. Treasury Press Releases": "미 재무부 보도자료",
    "USTR Press Releases": "USTR 보도자료",
    "FBI National Press Releases": "FBI 전국 보도자료",
    "CISA North Korea Cyber Advisories": "CISA 북한 사이버 권고",
    "38 North": "38노스",
    "NK News": "NK News",
    "Daily NK English": "데일리NK English",
    "VOA Korean Peninsula": "VOA 한국어 한반도",
    "Crisis Group Korean Peninsula": "국제위기그룹 한반도",
    "SIPRI Publications": "SIPRI 간행물",
    "Bruegel Publications": "브뤼헐 간행물",
    "CSIS Korea Chair": "CSIS Korea Chair",
    "RUSI Publications": "RUSI 간행물",
}

EVENT_LABELS_KO = {
    "new": "신규",
    "updated": "업데이트",
    "retry": "재시도",
    "bootstrap": "초기 기준선",
}

CONFIDENCE_LABELS_KO = {
    "high": "높음",
    "medium": "중간",
    "low": "낮음",
}

TERM_LABELS_KO = {
    "Republic of Korea": "대한민국",
    "South Korea": "한국",
    "ROK": "대한민국",
    "Seoul": "서울",
    "North Korea": "북한",
    "DPRK": "북한",
    "Democratic People's Republic of Korea": "조선민주주의인민공화국",
    "Pyongyang": "평양",
    "Korean Peninsula": "한반도",
    "inter-Korean": "남북한",
    "North Korea specialist source": "북한 전문 소스",
    "North Korea cyber advisory source": "북한 사이버 권고 소스",
    "Korean Peninsula source": "한반도 전문 소스",
    "NYT Korea priority source": "뉴욕타임스 한국 고우선 소스",
    "WSJ Korea priority source": "월스트리트저널 한국 고우선 소스",
}


def telegram_is_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _trim_summary(text: str, limit: int = 280) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def _translate_term(term: str) -> str:
    return TERM_LABELS_KO.get(term, term)


def build_telegram_message(item: MonitoredItem, event_type: str) -> str:
    title = " ".join(item.title.split())
    summary = _trim_summary(item.summary or item.body)
    matched = ", ".join(_translate_term(term) for term in item.matched_terms[:5])
    event_label = EVENT_LABELS_KO.get(event_type, event_type)
    confidence_label = CONFIDENCE_LABELS_KO.get(item.confidence, item.confidence)
    source_label = SOURCE_LABELS_KO.get(item.source_label, item.source_label)

    lines = [
        f"<b>[{html.escape(source_label)}] 한국 관련 {html.escape(event_label)} 알림</b>",
        f"관련도: {html.escape(confidence_label)}",
    ]

    if matched:
        lines.append(f"근거 키워드: {html.escape(matched)}")
    if item.published_at:
        lines.append(f"발행: {html.escape(item.published_at)}")
    if title:
        lines.append(f"원문 제목: {html.escape(title)}")
    if summary:
        lines.append(f"원문 요약: {html.escape(summary)}")

    lines.append(f'<a href="{html.escape(item.url, quote=True)}">원문 보기</a>')
    return "\n".join(lines)


def send_telegram_message(item: MonitoredItem, event_type: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")

    payload = {
        "chat_id": chat_id,
        "text": build_telegram_message(item, event_type),
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    post_form(f"https://api.telegram.org/bot{token}/sendMessage", payload)


def send_telegram_text(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")

    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }
    post_form(f"https://api.telegram.org/bot{token}/sendMessage", payload)
