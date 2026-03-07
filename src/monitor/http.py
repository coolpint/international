from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_text(url: str, timeout: int = 30) -> tuple[str, dict[str, str]]:
    request = Request(url, headers=DEFAULT_HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            headers = {key.lower(): value for key, value in response.headers.items()}
            charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace"), headers
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        snippet = body[:200].replace("\n", " ")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {snippet or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc.reason}") from exc


def post_form(url: str, payload: dict[str, str], timeout: int = 30) -> str:
    body = urlencode(payload).encode("utf-8")
    headers = {
        **DEFAULT_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        snippet = body[:200].replace("\n", " ")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {snippet or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc.reason}") from exc

