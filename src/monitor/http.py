from __future__ import annotations

import json
import ssl
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_RETRY_ATTEMPTS = 2
TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def fetch_text(url: str, timeout: int = 30) -> tuple[str, dict[str, str]]:
    return request_text(url=url, timeout=timeout)


def request_text(
    url: str,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    data: bytes | None = None,
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
) -> tuple[str, dict[str, str]]:
    request_headers = {**DEFAULT_HEADERS, **(headers or {})}

    for attempt in range(retry_attempts + 1):
        request = Request(url, data=data, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout, context=TLS_CONTEXT) as response:
                raw = response.read()
                headers = {key.lower(): value for key, value in response.headers.items()}
                charset = response.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace"), headers
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace").strip()
            if exc.code in RETRYABLE_HTTP_STATUS_CODES and attempt < retry_attempts:
                sleep(attempt + 1)
                continue
            snippet = body[:200].replace("\n", " ")
            raise RuntimeError(f"HTTP {exc.code} for {url}: {snippet or exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"Request failed for {url}: {exc.reason}") from exc

    raise RuntimeError(f"Request failed for {url}: exhausted retries")


def fetch_json(url: str, timeout: int = 30, headers: dict[str, str] | None = None) -> object:
    text, _ = request_text(url=url, timeout=timeout, headers=headers)
    return json.loads(text)


def post_form(url: str, payload: dict[str, str], timeout: int = 30) -> str:
    body = urlencode(payload).encode("utf-8")
    headers = {
        **DEFAULT_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout, context=TLS_CONTEXT) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        snippet = body[:200].replace("\n", " ")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {snippet or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc.reason}") from exc


def post_json(url: str, payload: dict[str, object], timeout: int = 30, headers: dict[str, str] | None = None) -> object:
    body = json.dumps(payload).encode("utf-8")
    text, _ = request_text(
        url=url,
        timeout=timeout,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
        data=body,
    )
    return json.loads(text)
