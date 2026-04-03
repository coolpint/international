import io
import unittest
from email.message import Message
from urllib.error import HTTPError
from unittest.mock import patch

from src.monitor.http import request_text


class _FakeResponse:
    def __init__(self, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
        self._body = text.encode("utf-8")
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class HttpTests(unittest.TestCase):
    @patch("src.monitor.http.sleep", return_value=None)
    @patch("src.monitor.http.urlopen")
    def test_request_text_retries_retryable_http_error(self, mock_urlopen, mock_sleep) -> None:
        transient_error = HTTPError(
            url="https://example.com/feed",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=io.BytesIO(b"temporary upstream failure"),
        )
        mock_urlopen.side_effect = [transient_error, _FakeResponse("ok")]

        text, _ = request_text("https://example.com/feed")

        self.assertEqual(text, "ok")
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @patch("src.monitor.http.sleep", return_value=None)
    @patch("src.monitor.http.urlopen")
    def test_request_text_does_not_retry_non_retryable_http_error(self, mock_urlopen, mock_sleep) -> None:
        blocked_error = HTTPError(
            url="https://example.com/feed",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=io.BytesIO(b"blocked by challenge page"),
        )
        mock_urlopen.side_effect = blocked_error

        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            request_text("https://example.com/feed")

        self.assertEqual(mock_urlopen.call_count, 1)
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
