"""Render official UN Press pages with an ordinary, short-lived Chromium context."""
from contextlib import contextmanager
from datetime import datetime
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .models import MonitoredItem

DETAIL_SELECTOR = "main article.node--view-mode-full"
LIST_SELECTOR = "main article.node--view-mode-content-list-item"
TIMEOUT_MS = 30_000
# Official slug typo observed with an exactly matching official canonical URL.
DOCUMENT_SYMBOL_ALIASES = {"gashc448": "gashc4448"}


def _validate_url(url, *, detail=False):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "press.un.org"
            or parsed.query or parsed.fragment or "?" in url or "#" in url
            or any(c.isspace() for c in url)):
        raise ValueError("UN Press URL outside official HTTPS allowlist")
    if detail and not re.fullmatch(r"/en/\d{4}/[a-z0-9]+\.doc\.htm", parsed.path):
        raise ValueError("UN Press detail URL has no canonical document ID")
    return parsed


@contextmanager
def _browser_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium", headless=True)
        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                # Normal asset requests remain unchanged; navigation stays on UN Press.
                def guard(route):
                    request = route.request
                    if request.is_navigation_request():
                        try:
                            _validate_url(request.url)
                        except ValueError:
                            route.abort()
                            return
                    route.continue_()
                context.route("**/*", guard)
                yield page
            finally:
                context.close()
        finally:
            browser.close()


def _render(page, url, *, detail=False):
    _validate_url(url, detail=detail)
    response = page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    _validate_url(page.url, detail=detail)
    if response is not None and response.status >= 400:
        raise RuntimeError(f"HTTP {response.status} from UN Press")
    if detail:
        for suffix in ("h1", ".field--name-body", "time[datetime]", ".field--name-field-symbol", ".field--name-field-doctype"):
            page.wait_for_selector(f"{DETAIL_SELECTOR} {suffix}", timeout=TIMEOUT_MS)
    else:
        page.wait_for_selector(
            f'{LIST_SELECTOR} .field--name-field-display-title a[href$=".doc.htm"]',
            timeout=TIMEOUT_MS,
        )
    return page.content()


def _expected_doctype(source):
    expected = {"un_press_releases": "Press Release", "un_meetings_coverage": "Meetings Coverage"}.get(source.id)
    if expected is None:
        raise ValueError("UN Press source has no declared document type")
    return expected


def _doctype(article):
    node = article.select_one(".field--name-field-doctype")
    if node is None or not node.get_text(strip=True):
        raise ValueError("UN Press document type missing")
    return " ".join(node.get_text(" ", strip=True).split())


def parse_un_press_detail(source, url, html):
    parsed = _validate_url(url, detail=True)
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one(DETAIL_SELECTOR)
    if article is None:
        raise ValueError("UN Press article DOM missing; challenge or incomplete page")
    if _doctype(article) != _expected_doctype(source):
        raise ValueError("UN Press document type does not match source scope")
    title_node = article.select_one("h1")
    time_node = article.select_one("time[datetime]")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    body_node = article.select_one(".field--name-body")
    if body_node is not None:
        for unwanted in body_node.select("script, style, noscript, template"):
            unwanted.decompose()
    body = body_node.get_text("\n\n", strip=True) if body_node else ""
    first_paragraph = body_node.select_one("p") if body_node else None
    summary = first_paragraph.get_text(" ", strip=True) if first_paragraph else body[:500]
    if len(title) < 10 or len(body) < 100:
        raise ValueError("UN Press article title or full body is incomplete")
    if time_node is None:
        raise ValueError("UN Press publication date missing")
    published = str(time_node.get("datetime", ""))
    try:
        date = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("UN Press publication date invalid") from None
    if str(date.year) != parsed.path.split("/")[2]:
        raise ValueError("UN Press publication year does not match document URL")
    symbols = article.select(".field--name-field-symbol .field__item")
    if not symbols:
        symbols = article.select(".field--name-field-symbol")
    document_id = parsed.path.rsplit("/", 1)[1].removesuffix(".doc.htm")
    symbol_ids = [re.sub(r"[^a-z0-9]", "", n.get_text(strip=True).lower()) for n in symbols]
    expected_symbol = DOCUMENT_SYMBOL_ALIASES.get(document_id, document_id)
    if expected_symbol not in symbol_ids:
        raise ValueError("UN Press document symbol does not match canonical document ID")
    canonical = soup.select_one('link[rel="canonical"]')
    if document_id in DOCUMENT_SYMBOL_ALIASES and canonical is None:
        raise ValueError("UN Press aliased document requires an exact official canonical URL")
    if canonical is not None:
        canonical_url = str(canonical.get("href", ""))
        _validate_url(canonical_url, detail=True)
        if canonical_url != url:
            raise ValueError("UN Press canonical URL does not match requested document")
    return MonitoredItem(
        source_id=source.id, source_label=source.label, url=url,
        title=title, summary=summary, body=body,
        published_at=published,
    )


def fetch_un_press_detail(source, url):
    _validate_url(url, detail=True)
    with _browser_page() as page:
        return parse_un_press_detail(source, url, _render(page, url, detail=True))


def _listing_urls(source, html):
    from .sources import _extract_press_links
    soup = BeautifulSoup(html, "html.parser")
    scoped = BeautifulSoup("<main></main>", "html.parser")
    expected = _expected_doctype(source)
    rejected = 0
    for article in soup.select(LIST_SELECTOR):
        doctype = _doctype(article)
        links = article.select(".field--name-field-display-title a[href]")
        for link in links:
            if doctype != expected:
                rejected += 1
                continue
            scoped.main.append(BeautifulSoup(str(link), "html.parser"))
    urls = []
    for url in _extract_press_links(source.list_url, scoped):
        try:
            _validate_url(url, detail=True)
        except ValueError:
            rejected += 1
        else:
            urls.append(url)
    return urls, rejected


def collect_un_press_items(source):
    from .sources import CollectionResult
    result = CollectionResult()
    result.selected_url = source.list_url
    try:
        _validate_url(source.list_url)
        with _browser_page() as page:
            urls, result.filtered = _listing_urls(source, _render(page, source.list_url))
            result.candidates = len(urls) + result.filtered
            if not urls:
                if not result.candidates:
                    result.failure_reason = "UN Press listing contains no official document candidates"
                return result
            _collect_on_page(source, urls, page, result)
    except Exception as exc:
        result.failure_reason = _safe_error(exc)
        result.errors.append({"url": source.list_url, "detail": result.failure_reason})
    return result


def _collect_on_page(source, urls, page, result):
    limit = min(20, max(0, source.max_items))
    selected = urls[:limit]
    result.deferred = len(urls) - len(selected)
    consecutive_failures = 0
    for index, url in enumerate(selected):
        try:
            result.append(parse_un_press_detail(source, url, _render(page, url, detail=True)))
            result.succeeded += 1
            consecutive_failures = 0
        except Exception as exc:
            result.failed += 1
            result.errors.append({"url": url, "detail": _safe_error(exc)})
            # Timeout/challenge and invalid rendered DOM are access failures too.
            consecutive_failures += 1
            if consecutive_failures >= 3:
                result.deferred += len(selected) - index - 1
                break


def collect_un_press_urls(source, urls):
    """Replay observed official document URLs in one ordinary browser session."""
    from .sources import CollectionResult
    result = CollectionResult()
    result.selected_url = source.list_url
    urls = list(dict.fromkeys(urls))
    result.candidates = len(urls)
    if not urls:
        return result
    try:
        # Validate the complete input before creating a browser or navigating.
        for url in urls:
            _validate_url(url, detail=True)
        with _browser_page() as page:
            _collect_on_page(source, urls, page, result)
    except Exception as exc:
        result.failure_reason = _safe_error(exc)
        result.errors.append({"url": source.list_url, "detail": result.failure_reason})
    return result


def _safe_error(exc):
    # Playwright traces can contain headers or response content. Keep a compact cause.
    status = re.search(r"HTTP (\d{3})", str(exc))
    if status:
        return f"HTTP {status.group(1)} from UN Press"
    if isinstance(exc, ValueError):
        return str(exc)
    return f"UN Press browser rendering failed ({type(exc).__name__}); article readiness not confirmed"
