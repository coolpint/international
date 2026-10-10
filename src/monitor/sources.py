from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from .http import fetch_json, fetch_text, post_json
from .models import MonitoredItem, SourceConfig


class CollectionResult(list[MonitoredItem]):
    """List-compatible result with counts before source filters and item limits."""

    def __init__(self) -> None:
        super().__init__()
        self.candidates = 0
        self.succeeded = 0
        self.failed = 0
        self.filtered = 0
        self.deferred = 0
        self.errors = []
        self.selected_url = None
        self.failure_reason = None

    @property
    def status(self) -> str:
        if self.failure_reason:
            return "error"
        if self.failed:
            return "partial" if self.succeeded else "error"
        if not self.candidates:
            return "empty"
        return "ok" if self else "filtered"

    def report(self) -> dict:
        return {
            "status": self.status, "collected": len(self),
            "candidates": self.candidates, "succeeded": self.succeeded,
            "failed": self.failed, "filtered": self.filtered,
            "deferred": self.deferred, "errors": self.errors,
            "selected_url": self.selected_url, "detail": self.failure_reason,
        }


def _collect_details(source: SourceConfig, urls: list[str], result=None) -> CollectionResult:
    result = result if result is not None else CollectionResult()
    if not urls and not result.candidates:
        result.failure_reason = "listing selector found no candidates; structure may have changed"
        return result
    if not result.candidates:
        result.candidates = len(urls)
    result.deferred = max(0, len(urls) - source.max_items)
    for url in urls[:source.max_items]:
        try:
            item = _fetch_detail_item(source, url)
            if not item.title or not (item.summary or item.body):
                raise ValueError("detail is missing title or article text")
            result.append(item)
            result.succeeded += 1
        except Exception as exc:
            result.failed += 1
            result.errors.append({"url": url, "detail": str(exc)})
    return result


def collect_items(source: SourceConfig) -> CollectionResult:
    if not source.list_url:
        raise RuntimeError(f"{source.id} has no list URL configured.")

    if source.type == "unrisd_api":
        return _collect_unrisd_api_items(source)
    if source.type == "rss_xml":
        return _collect_rss_items(source)
    if source.type == "html_listing":
        return _collect_html_listing_items(source)
    if source.type == "world_bank_news_api":
        return _collect_world_bank_news_items(source)
    if source.type == "bruegel_publications":
        return _collect_bruegel_publication_items(source)
    if source.type == "rusi_publications":
        return _collect_rusi_publication_items(source)

    html_text, _ = fetch_text(source.list_url)
    soup = BeautifulSoup(html_text, "html.parser")

    if source.type == "un_news_latest":
        selector = 'a[href*="/en/story/"]'
        urls = _extract_un_news_links(source.list_url, soup)
    elif source.type == "un_press_listing":
        selector = 'a[href$=".doc.htm"]'
        urls = _extract_press_links(source.list_url, soup)
    elif source.type == "unctad_publications":
        selector = 'a[href^="/publication/"], a[href*="unctad.org/publication/"]'
        urls = _extract_unctad_publication_links(source.list_url, soup)
    else:
        raise RuntimeError(f"Unsupported active source type: {source.type}")

    return _collect_listing_details(source, soup, selector, urls)


def _raw_listing_urls(base_url: str, soup: BeautifulSoup, selector: str) -> list[str]:
    return _dedupe_preserve_order([
        urljoin(base_url, anchor["href"])
        for anchor in soup.select(selector) if anchor.get("href")
    ])


def _collect_listing_details(source: SourceConfig, soup: BeautifulSoup, selector: str,
                             urls: list[str]) -> CollectionResult:
    result = CollectionResult()
    result.selected_url = source.list_url
    result.candidates = len(_raw_listing_urls(source.list_url, soup, selector))
    result.filtered = result.candidates - len(urls)
    return _collect_details(source, urls, result)


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


def _extract_bruegel_publication_links(base_url: str, soup: BeautifulSoup) -> list[str]:
    urls = []
    for anchor in soup.select("div.c-listing__items article.c-list-item--article h2 a[href]"):
        href = anchor.get("href")
        if not href:
            continue
        url = urljoin(base_url, href)
        if urlparse(url).netloc != "www.bruegel.org":
            continue
        urls.append(url)
    return _dedupe_preserve_order(urls)


def _extract_rusi_publication_links(base_url: str, soup: BeautifulSoup) -> list[str]:
    urls = []
    for anchor in soup.select('a.RelatedArticle-module--mainLink--4c03e[href*="/explore-our-research/publications/"]'):
        href = anchor.get("href")
        if not href:
            continue
        url = urljoin(base_url, href)
        if urlparse(url).netloc != "www.rusi.org":
            continue
        urls.append(url)
    return _dedupe_preserve_order(urls)


def _fetch_detail_item(source: SourceConfig, url: str) -> MonitoredItem:
    html, headers = fetch_text(url)
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title(soup)
    if title.casefold().rstrip(".! ") in {
        "access denied", "just a moment", "not acceptable",
        "attention required", "attention required | cloudflare",
    } or soup.select_one('script[src*="/cdn-cgi/challenge-platform/"]'):
        raise RuntimeError("detail response is an access restriction or challenge page")
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


def _collect_rss_items(source: SourceConfig) -> CollectionResult:
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
            parsed_root = ElementTree.fromstring(xml_text)
            if _xml_local_name(parsed_root.tag) not in {"rss", "RDF", "feed"}:
                raise ValueError("response is not RSS/Atom XML")
            if _xml_local_name(parsed_root.tag) == "rss" and _xml_first_child(parsed_root, "channel") is None:
                raise ValueError("RSS feed is missing a channel element")
            root = parsed_root
            selected_feed_url = feed_url
            break
        except Exception as exc:
            errors.append(f"{feed_url}: {exc}")

    if root is None:
        joined = "; ".join(errors)
        raise RuntimeError(f"{source.id} feed fetch failed. {joined}")

    items = CollectionResult()
    items.selected_url = selected_feed_url
    # Fallback transport failures are diagnostic; a valid selected feed is usable.
    items.errors = errors
    root_name = _xml_local_name(root.tag)
    container = _xml_first_child(root, "channel") if root_name == "rss" else root
    node_name = "entry" if root_name == "feed" else "item"
    for node in container:
        if _xml_local_name(node.tag) != node_name:
            continue
        items.candidates += 1
        builder = _build_atom_item if root_name == "feed" else _build_rss_item
        try:
            item = builder(source, node, selected_feed_url)
            if item is None:
                raise ValueError("feed item is missing title or link")
        except Exception:
            items.failed += 1
            items.errors.append({"detail": "feed item is missing valid title or link", "candidate": items.candidates})
            continue
        if not _rss_item_matches_source_filters(item, source):
            items.filtered += 1
        elif len(items) >= source.max_items:
            items.deferred += 1
        else:
            items.append(item)
            items.succeeded += 1
    return items


def _collect_unrisd_api_items(source: SourceConfig) -> CollectionResult:
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
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise RuntimeError(f"{source.id}: API response is missing a data array")
    records = payload["data"]
    return _collect_records(records, lambda record: _build_unrisd_item(source, record, route_prefix), source.max_items)


def _collect_world_bank_news_items(source: SourceConfig) -> CollectionResult:
    api_url = str(source.options.get("api_url", "")).strip()
    if not api_url:
        raise RuntimeError(f"{source.id} is missing api_url.")

    payload = fetch_json(api_url)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{source.id} returned an unexpected response payload.")

    documents = payload.get("documents")
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

    result = _collect_records(records, lambda record: _build_world_bank_news_item(source, record), source.max_items)
    result.candidates = len(documents)
    result.filtered = sum(1 for record in documents.values() if isinstance(record, dict) and
                          (dt := _parse_iso_datetime(str(record.get("lnchdt") or ""))) and dt > now)
    result.failed += sum(1 for record in documents.values() if not isinstance(record, dict))
    return result


def _collect_bruegel_publication_items(source: SourceConfig) -> CollectionResult:
    html_text, _ = fetch_text(source.list_url)
    soup = BeautifulSoup(html_text, "html.parser")
    urls = _extract_bruegel_publication_links(source.list_url, soup)

    return _collect_listing_details(source, soup,
        "div.c-listing__items article.c-list-item--article h2 a[href]", urls)


def _collect_rusi_publication_items(source: SourceConfig) -> CollectionResult:
    html_text, _ = fetch_text(source.list_url)
    soup = BeautifulSoup(html_text, "html.parser")
    urls = _extract_rusi_publication_links(source.list_url, soup)

    return _collect_listing_details(source, soup,
        'a.RelatedArticle-module--mainLink--4c03e[href*="/explore-our-research/publications/"]', urls)


def _collect_html_listing_items(source: SourceConfig) -> CollectionResult:
    selector = str(source.options.get("link_selector", "")).strip()
    if not selector:
        raise RuntimeError(f"{source.id} is missing link_selector.")

    html_text, _ = fetch_text(source.list_url)
    soup = BeautifulSoup(html_text, "html.parser")
    raw_urls = _raw_listing_urls(source.list_url, soup, selector)
    urls = [url for url in raw_urls if _url_matches_source_filters(url, source)]
    return _collect_listing_details(source, soup, selector, urls)


def _collect_records(records, builder, max_items) -> CollectionResult:
    result = CollectionResult()
    result.candidates = len(records)
    result.deferred = max(0, len(records) - max_items)
    for record in records[:max_items]:
        try:
            item = builder(record)
            if item is None:
                raise ValueError("record is missing title or URL")
            result.append(item)
            result.succeeded += 1
        except Exception:
            result.failed += 1
            result.errors.append({"detail": "API record is missing valid title or URL"})
    return result


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


def _option_string_list(source: SourceConfig, key: str) -> list[str]:
    value = source.options.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()]


def _url_matches_source_filters(url: str, source: SourceConfig) -> bool:
    allowed_domains = _option_string_list(source, "allowed_domains")
    if allowed_domains:
        domain = urlparse(url).netloc.lower()
        allowed_domain_set = [entry.lower() for entry in allowed_domains]
        if not any(domain == allowed or domain.endswith("." + allowed) for allowed in allowed_domain_set):
            return False

    allowed_url_patterns = _option_string_list(source, "allowed_url_patterns")
    if allowed_url_patterns and not any(pattern in url for pattern in allowed_url_patterns):
        return False

    denied_url_patterns = _option_string_list(source, "deny_url_patterns")
    if denied_url_patterns and any(pattern in url for pattern in denied_url_patterns):
        return False

    return True


def _rss_item_matches_source_filters(item: MonitoredItem, source: SourceConfig) -> bool:
    return _url_matches_source_filters(item.url, source)


def _extract_html_listing_links(base_url: str, soup: BeautifulSoup, selector: str, source: SourceConfig) -> list[str]:
    urls = []
    for anchor in soup.select(selector):
        href = anchor.get("href")
        if not href:
            continue
        url = urljoin(base_url, href)
        if not _url_matches_source_filters(url, source):
            continue
        urls.append(url)
    return _dedupe_preserve_order(urls)


def _build_rss_item(source: SourceConfig, node: ElementTree.Element, feed_url: str) -> MonitoredItem | None:
    title = _xml_first_child_text(node, "title")
    url = _normalize_feed_link(feed_url, _xml_first_child_text(node, "link") or _xml_first_child_text(node, "guid"))
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
