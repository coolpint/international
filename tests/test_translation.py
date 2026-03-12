import unittest
from unittest.mock import patch

from src.monitor.translation import NotificationTranslation, _response_output_text, translate_alert_text


class TranslationTests(unittest.TestCase):
    def test_extracts_output_text_from_responses_payload(self) -> None:
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"title_ko":"한국어 제목","summary_ko":"한국어 요약"}',
                        }
                    ],
                }
            ]
        }

        text = _response_output_text(payload)
        self.assertEqual(text, '{"title_ko":"한국어 제목","summary_ko":"한국어 요약"}')

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_original_text_without_api_key(self) -> None:
        translated = translate_alert_text("English title", "English summary")
        self.assertEqual(
            translated,
            NotificationTranslation(title="English title", summary="English summary"),
        )


if __name__ == "__main__":
    unittest.main()
