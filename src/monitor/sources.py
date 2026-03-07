from __future__ import annotations

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .http import fetch_text
from .models import MonitoredItem, SourceConfig


def collect_items(source: SourceConfig) -> list[MonitoredItem]:
    if not source.list_url:
        raise RuntimeError(f"{source.id} has no list URL configured.")

    html, _ = fetch_text(source.list_url)
    soup = BeautifulSoup(html, "html.parser")

    if source.type == "un_news_latest":
        urls = _extract_un_news_links(source.list_url, soup)
    elif source.type == "un_press_listing":
        urls = _extract_press_links(source.list_url, soup)
    elif source.type == "unctad_publications":
        urls = _extract_unctad_publication_links(source.list_url, soup)
    else:
        raise RuntimeError(f"Unsupported active source type: {source.type}")

    items = []
    for url in urls[: source.max_items]:
        try:
            items.append(_fetch_detail_item(source, url))
        except Exception as exc:
            print(f"[warn] {source.id}: failed to parse {url}: {exc}")
    return items


def _dedupe_preserve_order(urls: list[str]) -> list[str]:
    unique_urls = []
    seen = set()
    for url in urls:
        clean_url = url.split("#", 1)[0]
        if clean_url in seen:
            continue
        seen.add(clean_url)
        unique_urls.append(clean_url)
    return unique_urls


def _extract_un_news_links(base_url: str, soup: BeautifulSoup) -> list[str]:
    urls = []
    for anchor in soup.select('a[href*="/en/story/"]'):
        href = anchor.get("href")
        if not href:
            continue
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.netloc != "news.un.org":
            continue
        if parsed.path.startswith("/en/story/"):
            urls.append(url)
    return _dedupe_preserve_order(urls)


def _extract_press_links(base_url: str, soup: BeautifulSoup) -> list[str]:
    urls = []
    for anchor in soup.select('a[href$=".doc.htm"]'):
        href = anchor.get("href")
        if not href:
            continue
        url = urljoin(base_url, href)
        if url.endswith(".doc.htm") and "/en/" in url:
            urls.append(url)
    return _dedupe_preserve_order(urls)


def _extract_unctad_publication_links(base_url: str, soup: BeautifulSoup) -> list[str]:
    urls = []
    for anchor in soup.select('a[href^="/publication/"], a[href*="unctad.org/publication/"]'):
        href = anchor.get("href")
        if not href:
            continue
        url = urljoin(base_url, href)
        if "/publication/" in url:
            urls.append(url)
    return _dedupe_preserve_order(urls)


def _fetch_detail_item(source: SourceConfig, url: str) -> MonitoredItem:
    html, headers = fetch_text(url)
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title(soup)
    summary = _extract_summary(soup)
    body = _extract_body_text(soup)
    published_at = _extract_published_at(soup) or headers.get("last-modified")

    return MonitoredItem(
        source_id=source.id,
        source_label=source.label,
        url=url,
        title=title,
        summary=summary,
        body=body,
        published_at=published_at,
    )


def _extract_title(soup: BeautifulSoup) -> str:
    for selector, attr in [
        ('meta[property="og:title"]', "content"),
        ('meta[name="twitter:title"]', "content"),
    ]:
        tag = soup.select_one(selector)
        if tag and tag.get(attr):
            return tag.get(attr, "").strip()

    heading = soup.select_one("h1")
    if heading:
        return " ".join(heading.get_text(" ", strip=True).split())

    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        return title.split("|", 1)[0].strip()

    return ""


def _extract_summary(soup: BeautifulSoup) -> str:
    for selector, attr in [
        ('meta[name="description"]', "content"),
        ('meta[property="og:description"]', "content"),
    ]:
        tag = soup.select_one(selector)
        if tag and tag.get(attr):
            return " ".join(tag.get(attr, "").split())

    paragraph = soup.select_one("article p, main p, #main-content p")
    if paragraph:
        return " ".join(paragraph.get_text(" ", strip=True).split())

    return ""


def _extract_body_text(soup: BeautifulSoup) -> str:
    selectors = [
        "article p",
        "main p",
        "#main-content p",
        ".field--name-body p",
        ".node__content p",
        ".ny-card__body p",
    ]

    parts = []
    seen = set()
    for selector in selectors:
        for node in soup.select(selector):
            text = " ".join(node.get_text(" ", strip=True).split())
            if len(text) < 40 or text in seen:
                continue
            seen.add(text)
            parts.append(text)
            if len(parts) >= 20:
                return "\n".join(parts)
    return "\n".join(parts)


def _extract_published_at(soup: BeautifulSoup) -> str | None:
    for selector, attr in [
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="article:published_time"]', "content"),
        ('meta[name="date"]', "content"),
        ("time[datetime]", "datetime"),
    ]:
        tag = soup.select_one(selector)
        if tag and tag.get(attr):
            return tag.get(attr, "").strip()
    return None
