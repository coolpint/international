from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from .http import fetch_json, fetch_text, post_json
from .models import MonitoredItem, SourceConfig


def collect_items(source: SourceConfig) -> list[MonitoredItem]:
    if not source.list_url:
        raise RuntimeError(f"{source.id} has no list URL configured.")

    if source.type == "unrisd_api":
        return _collect_unrisd_api_items(source)
    if source.type == "rss_xml":
        return _collect_rss_items(source)
    if source.type == "world_bank_news_api":
        return _collect_world_bank_news_items(source)

    html_text, _ = fetch_text(source.list_url)
    soup = BeautifulSoup(html_text, "html.parser")

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


def _collect_rss_items(source: SourceConfig) -> list[MonitoredItem]:
    feed_urls = [str(source.list_url)]
    fallback_urls = source.options.get("fallback_urls", [])
    if isinstance(fallback_urls, list):
        feed_urls.extend(str(url) for url in fallback_urls if str(url).strip())

    root = None
    selected_feed_url = ""
    errors = []
    for feed_url in feed_urls:
        try:
            xml_text, _ = fetch_text(feed_url)
            root = ElementTree.fromstring(xml_text)
            selected_feed_url = feed_url
            break
        except Exception as exc:
            errors.append(f"{feed_url}: {exc}")

    if root is None:
        joined = "; ".join(errors)
        raise RuntimeError(f"{source.id} feed fetch failed. {joined}")

    items = []
    root_name = _xml_local_name(root.tag)

    if root_name == "rss":
        channel = _xml_first_child(root, "channel")
        if channel is None:
            raise RuntimeError(f"{source.id} RSS feed is missing a channel element.")

        for node in channel:
            if _xml_local_name(node.tag) != "item":
                continue
            item = _build_rss_item(source, node, selected_feed_url)
            if item:
                items.append(item)
    elif root_name == "feed":
        for node in root:
            if _xml_local_name(node.tag) != "entry":
                continue
            item = _build_atom_item(source, node, selected_feed_url)
            if item:
                items.append(item)
    else:
        raise RuntimeError(f"{source.id} feed is not RSS/Atom XML.")

    return items[: source.max_items]


def _collect_unrisd_api_items(source: SourceConfig) -> list[MonitoredItem]:
    token_url = str(source.options.get("oauth_token_url", "")).strip()
    api_url = str(source.options.get("api_url", "")).strip()
    route_prefix = str(source.options.get("route_prefix", "")).strip()

    if not token_url or not api_url or not route_prefix:
        raise RuntimeError(f"{source.id} is missing oauth_token_url, api_url, or route_prefix.")

    token_payload = post_json(token_url, {"grantType": "client_credentials"})
    access_token = token_payload.get("access_token")
    if not access_token:
        raise RuntimeError(f"{source.id} failed to obtain UNRISD access token.")

    payload = fetch_json(
        f"{api_url}?limit={source.max_items}&sort=-publishAt&isPublished=1",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    records = payload.get("data", [])

    items = []
    for record in records:
        item = _build_unrisd_item(source, record, route_prefix)
        if item:
            items.append(item)
    return items


def _collect_world_bank_news_items(source: SourceConfig) -> list[MonitoredItem]:
    api_url = str(source.options.get("api_url", "")).strip()
    if not api_url:
        raise RuntimeError(f"{source.id} is missing api_url.")

    payload = fetch_json(api_url)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{source.id} returned an unexpected response payload.")

    documents = payload.get("documents", {})
    if not isinstance(documents, dict):
        raise RuntimeError(f"{source.id} payload did not contain a documents object.")

    records = []
    now = datetime.now(timezone.utc)
    for record in documents.values():
        if not isinstance(record, dict):
            continue

        published_at = str(record.get("lnchdt") or "").strip()
        published_dt = _parse_iso_datetime(published_at)
        if published_dt and published_dt > now:
            continue

        records.append(record)

    records.sort(key=lambda record: str(record.get("lnchdt") or ""), reverse=True)

    items = []
    for record in records[: source.max_items]:
        item = _build_world_bank_news_item(source, record)
        if item:
            items.append(item)
    return items


def _build_unrisd_item(source: SourceConfig, record: dict, route_prefix: str) -> MonitoredItem | None:
    attributes = record.get("attributes", {})
    slug = attributes.get("slug")
    title = (attributes.get("title") or "").strip()
    if not slug or not title:
        return None

    summary = " ".join((attributes.get("summary") or attributes.get("metaDescription") or "").split())
    body = _unrisd_search_index_text(attributes.get("searchIndex"))
    if not summary:
        summary = body[:280].strip()

    return MonitoredItem(
        source_id=source.id,
        source_label=source.label,
        url=f"https://www.unrisd.org{route_prefix}/{slug}",
        title=title,
        summary=summary,
        body=body,
        published_at=attributes.get("publishAt"),
    )


def _build_world_bank_news_item(source: SourceConfig, record: dict) -> MonitoredItem | None:
    title = _world_bank_text(record.get("title"))
    url = _normalize_world_bank_url(record.get("url"))
    if not title or not url:
        return None

    summary = _world_bank_text(record.get("descr"))
    body = _world_bank_text(record.get("content_1000")) or _world_bank_text(record.get("content"))
    if summary and body and body != summary:
        body = "\n".join([summary, body])
    elif summary and not body:
        body = summary
    elif body and not summary:
        summary = body[:280].strip()

    return MonitoredItem(
        source_id=source.id,
        source_label=source.label,
        url=url,
        title=title,
        summary=summary,
        body=body,
        published_at=str(record.get("lnchdt") or "").strip() or None,
    )


def _unrisd_search_index_text(search_index: str | None) -> str:
    if not search_index:
        return ""

    try:
        payload = json.loads(search_index)
    except json.JSONDecodeError:
        return ""

    chunks = []
    for value in payload.values():
        html = value.get("text")
        if not html:
            continue
        text = " ".join(BeautifulSoup(html, "html.parser").get_text(" ", strip=True).split())
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def _world_bank_text(value: object) -> str:
    if isinstance(value, dict):
        for key in ["cdata!", "#cdata-section", "text", "value"]:
            nested = value.get(key)
            if nested:
                return _xml_html_text(str(nested))
        return ""
    if value is None:
        return ""
    return _xml_html_text(str(value))


def _normalize_world_bank_url(url: object) -> str:
    if not url:
        return ""
    clean_url = str(url).strip()
    if clean_url.startswith("http://www.worldbank.org/"):
        return "https://" + clean_url[len("http://") :]
    if clean_url.startswith("http://worldbank.org/"):
        return "https://" + clean_url[len("http://") :]
    return clean_url


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_rss_item(source: SourceConfig, node: ElementTree.Element, feed_url: str) -> MonitoredItem | None:
    title = _xml_first_child_text(node, "title")
    url = _normalize_feed_link(feed_url, _xml_first_child_text(node, "link"))
    if not title or not url:
        return None

    summary = _xml_html_text(_xml_first_child_text(node, "description"))
    body_parts = []

    content = _xml_html_text(_xml_first_child_text(node, "encoded", "content", "summary"))
    if summary:
        body_parts.append(summary)
    if content and content != summary:
        body_parts.append(content)

    categories = _xml_all_child_text(node, "category")
    if categories:
        body_parts.append("Categories: " + ", ".join(categories))

    body = "\n".join(part for part in body_parts if part)
    if not summary:
        summary = body[:280].strip()

    return MonitoredItem(
        source_id=source.id,
        source_label=source.label,
        url=url,
        title=title,
        summary=summary,
        body=body,
        published_at=_xml_first_child_text(node, "pubDate", "published", "updated", "date"),
    )


def _build_atom_item(source: SourceConfig, node: ElementTree.Element, feed_url: str) -> MonitoredItem | None:
    title = _xml_first_child_text(node, "title")
    url = _normalize_feed_link(feed_url, _xml_atom_link(node))
    if not title or not url:
        return None

    summary = _xml_html_text(_xml_first_child_text(node, "summary"))
    content = _xml_html_text(_xml_first_child_text(node, "content"))
    body_parts = []
    if summary:
        body_parts.append(summary)
    if content and content != summary:
        body_parts.append(content)
    body = "\n".join(body_parts)
    if not body:
        body = summary
    if not summary:
        summary = body[:280].strip()

    return MonitoredItem(
        source_id=source.id,
        source_label=source.label,
        url=url,
        title=title,
        summary=summary,
        body=body,
        published_at=_xml_first_child_text(node, "published", "updated"),
    )


def _xml_local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _xml_first_child(node: ElementTree.Element, local_name: str) -> ElementTree.Element | None:
    for child in node:
        if _xml_local_name(child.tag) == local_name:
            return child
    return None


def _xml_first_child_text(node: ElementTree.Element, *local_names: str) -> str:
    for local_name in local_names:
        child = _xml_first_child(node, local_name)
        if child is None:
            continue

        text = "".join(child.itertext()).strip()
        if text:
            return text
        href = child.get("href", "").strip()
        if href:
            return href
    return ""


def _xml_all_child_text(node: ElementTree.Element, local_name: str) -> list[str]:
    values = []
    for child in node:
        if _xml_local_name(child.tag) != local_name:
            continue
        text = "".join(child.itertext()).strip()
        if text:
            values.append(" ".join(text.split()))
    return values


def _xml_atom_link(node: ElementTree.Element) -> str:
    for child in node:
        if _xml_local_name(child.tag) != "link":
            continue
        rel = child.get("rel", "alternate")
        href = child.get("href", "").strip()
        if rel == "alternate" and href:
            return href
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return ""


def _normalize_feed_link(feed_url: str, link: str) -> str:
    clean_link = link.strip()
    if not clean_link:
        return ""
    return urljoin(feed_url, clean_link)


def _xml_html_text(raw_text: str) -> str:
    if not raw_text:
        return ""

    text = BeautifulSoup(html.unescape(raw_text), "html.parser").get_text("\n", strip=True)
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


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
