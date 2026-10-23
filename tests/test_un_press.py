"""UN renderer tests use synthetic DOM and mocked browser sessions only."""
from contextlib import contextmanager
import unittest
from unittest.mock import Mock, patch

from src.monitor.models import SourceConfig
from src.monitor.un_press import (
    _listing_urls, _render, collect_un_press_items, collect_un_press_urls, fetch_un_press_detail,
    parse_un_press_detail,
)


def source(**kwargs):
    return SourceConfig("un_press_releases", "UN Press Releases", "un_press_listing",
                        True, "https://press.un.org/en/content/press-release", 20, **kwargs)


def detail(symbol="SG/SM/23342", document="sgsm23342", count=25):
    paragraphs = "".join(f"<p>Paragraph {i}: Republic of Korea participates in international cooperation.</p>" for i in range(count))
    return f'''<html><head><link rel="canonical" href="https://press.un.org/en/2026/{document}.doc.htm"></head>
    <body><main><article class="node--view-mode-full node--type-press">
    <h1>Secretary-General calls for international cooperation</h1>
    <div class="field--name-field-doctype">Press Release</div>
    <div class="field--name-field-symbol"><div class="field__item">{symbol}</div></div>
    <time datetime="2026-10-21T12:00:00Z">21 October 2026</time>
    <div class="field--name-body">{paragraphs}</div></article></main>
    <footer><p>Unrelated daily briefing</p></footer></body></html>'''


def listing(count=4):
    return '<main>' + ''.join(f'''<article class="node--view-mode-content-list-item">
        <div class="field--name-field-doctype">Press Release</div>
        <div class="field--name-field-display-title"><h3><a href="/en/2026/sgsm{i}.doc.htm">Title</a></h3></div>
        <p><a href="https://other.example/en/2026/notarticle.doc.htm">Citation</a></p>
        </article>''' for i in range(count)) + '</main><footer><a href="/en/2026/db261023.doc.htm">Daily</a></footer>'


class UnPressTests(unittest.TestCase):
    url = "https://press.un.org/en/2026/sgsm23342.doc.htm"

    def test_extracts_complete_body_date_and_original_canonical_url(self):
        item = parse_un_press_detail(source(), self.url, detail())
        self.assertEqual(item.url, self.url)
        self.assertEqual(item.published_at, "2026-10-21T12:00:00Z")
        self.assertIn("Paragraph 24:", item.body)
        self.assertEqual(item.body.count("Paragraph "), 25)
        self.assertNotIn("Unrelated daily", item.body)
        self.assertIn("Paragraph 0:", item.summary)

    def test_inline_markup_preserves_multiword_keyword_matching(self):
        from src.monitor.filtering import classify_item
        html = detail().replace('Republic of Korea', 'Republic of <em>Korea</em>')
        item = parse_un_press_detail(source(), self.url, html)
        self.assertIn('Republic of Korea', item.body)
        self.assertTrue(classify_item(item, {'high_confidence_terms': ['Republic of Korea']}).relevant)

    def test_browser_modes_are_explicit_and_reported(self):
        from src.monitor.un_press import _browser_mode
        for mode in ('headless', 'headed'):
            with patch.dict('os.environ', {'UN_PRESS_BROWSER_MODE': mode}):
                self.assertEqual(_browser_mode(), mode)
                result, _ = self.run_collection(1, iter([detail(symbol='SG/SM/0', document='sgsm0')]))
                self.assertEqual(result.report()['transport'], 'chromium-' + mode)
        with patch.dict('os.environ', {'UN_PRESS_BROWSER_MODE': 'unsupported'}):
            with self.assertRaises(ValueError):
                _browser_mode()

    def test_country_reference_after_long_meeting_introduction_is_classified(self):
        from src.monitor.filtering import classify_item
        html = detail(count=0).replace('</div></article>',
            '<p>' + ('General discussion of the agenda. ' * 200) + '</p>'
            '<table><tr><td>Republic of <em>Korea</em> addressed the meeting.</td></tr></table>'
            '</div></article>')
        item = parse_un_press_detail(source(), self.url, html)
        self.assertGreater(item.body.index('Republic of Korea'), 4000)
        self.assertTrue(classify_item(item, {'high_confidence_terms': ['Republic of Korea']}).relevant)

    def test_preserves_list_table_and_div_body_evidence(self):
        html = detail().replace("Republic of Korea", "Delegates").replace('</div></article>', """<ul><li>Republic of Korea list evidence</li></ul>
            <table><tr><td>South Korea table evidence</td></tr></table>
            <div>Korean Peninsula div evidence</div><script>secret script</script>
            <style>secret style</style></div></article>""")
        item = parse_un_press_detail(source(), self.url, html)
        for text in ("Republic of Korea list evidence", "South Korea table evidence", "Korean Peninsula div evidence"):
            self.assertIn(text, item.body)
        self.assertNotIn("Korea", item.summary)
        self.assertNotIn("secret script", item.body)
        self.assertNotIn("secret style", item.body)
        only_nonparagraphs = detail(count=0).replace('</div></article>',
            '<table><tr><td>' + ('Republic of Korea table evidence. ' * 8) + '</td></tr></table></div></article>')
        self.assertIn("Republic of Korea table evidence", parse_un_press_detail(source(), self.url, only_nonparagraphs).body)

    def test_official_slug_typo_requires_exact_canonical_and_explicit_symbol(self):
        meetings = SourceConfig("un_meetings_coverage", "UN Meetings Coverage", "un_press_listing",
                                True, "https://press.un.org/en/content/meetings-coverage", 20)
        url = "https://press.un.org/en/2026/gashc448.doc.htm"
        html = detail(symbol="GA/SHC/4448", document="gashc448").replace(
            ">Press Release<", ">Meetings Coverage<").replace("2026-10-21", "2026-10-22")
        self.assertEqual(parse_un_press_detail(meetings, url, html).url, url)
        invalid = (
            html.replace('rel="canonical"', 'rel="other"'),
            html.replace('href="' + url + '"', 'href="https://press.un.org/en/2026/gashc4448.doc.htm"'),
            html.replace("GA/SHC/4448", "GA/SHC/4449"),
            html.replace("2026-10-22", "2026-10-21"),
            html.replace("2026", "2025"),
            html.replace(">Meetings Coverage<", ">Press Release<"),
            detail(symbol="GA/SHC/4448", document="gashc448", count=0).replace(
                ">Press Release<", ">Meetings Coverage<").replace("2026-10-21", "2026-10-22"),
        )
        for content in invalid:
            with self.assertRaises(ValueError):
                parse_un_press_detail(meetings, url, content)
        # Nearby unknown typos retain the ordinary strict symbol-to-ID check.
        with self.assertRaises(ValueError):
            parse_un_press_detail(meetings, url.replace("gashc448", "gashc449"),
                                  html.replace("gashc448", "gashc449"))

    def test_document_type_is_required_and_exact(self):
        for html in (detail().replace('class="field--name-field-doctype"', 'class="unknown"'),
                     detail().replace('>Press Release<', '>Meetings Coverage<'),
                     detail().replace('>Press Release<', '>Not Press Release<')):
            with self.assertRaises(ValueError):
                parse_un_press_detail(source(), self.url, html)
        with self.assertRaises(ValueError):
            _listing_urls(source(), listing(1).replace('class="field--name-field-doctype"', 'class="unknown"'))

    def test_rejects_challenge_and_missing_or_mismatched_identity(self):
        html = detail()
        invalid = [
            "<html><title>Please wait</title><p>Enable JavaScript</p></html>",
            detail(symbol="SG/SM/99999"),
            html.replace('datetime="2026-10-21T12:00:00Z"', 'datetime="invalid"'),
            html.replace('datetime="2026-10-21T12:00:00Z"', 'datetime="2025-10-21T12:00:00Z"'),
            html.replace('<h1>', '<h2>').replace('</h1>', '</h2>'),
            detail(count=0),
            html.replace('rel="canonical" href="https://press.un.org/en/2026/sgsm23342.doc.htm"',
                         'rel="canonical" href="https://press.un.org/en/2026/sgsm999.doc.htm"'),
        ]
        for content in invalid:
            with self.subTest(content=content[:60]), self.assertRaises(ValueError):
                parse_un_press_detail(source(), self.url, content)

    def test_rejects_nonofficial_urls_before_browser_launch(self):
        for url in ["http://press.un.org/en/2026/sgsm23342.doc.htm",
                    "https://evil.example/en/2026/sgsm23342.doc.htm",
                    self.url + "?x=1", self.url + "#x",
                    "https://user@press.un.org/en/2026/sgsm23342.doc.htm"]:
            with self.subTest(url=url), patch("src.monitor.un_press._browser_page") as browser:
                with self.assertRaises(ValueError):
                    fetch_un_press_detail(source(), url)
                browser.assert_not_called()

    def test_listing_keeps_title_links_and_scope_excludes_footer_and_crossdomain(self):
        html = listing(2).replace('</main>', '''
        <article class="node--view-mode-content-list-item">
        <div class="field--name-field-doctype">Press Release</div>
        <div class="field--name-field-display-title"><a href="https://evil.example/en/2026/x.doc.htm">Evil</a></div></article>
        <article class="node--view-mode-content-list-item">
        <div class="field--name-field-doctype">Meetings Coverage</div>
        <div class="field--name-field-display-title"><a href="/en/2026/sc999.doc.htm">Wrong type</a></div></article></main>''')
        urls, filtered = _listing_urls(source(), html)
        self.assertEqual(urls, ["https://press.un.org/en/2026/sgsm0.doc.htm", "https://press.un.org/en/2026/sgsm1.doc.htm"])
        self.assertEqual(filtered, 2)

    def test_render_requires_article_readiness_even_on_http_200(self):
        page = Mock()
        page.url = self.url
        page.goto.return_value.status = 200
        page.wait_for_selector.side_effect = TimeoutError("challenge")
        with self.assertRaises(TimeoutError):
            _render(page, self.url, detail=True)
        page.content.assert_not_called()
        page.goto.assert_called_once_with(self.url, wait_until="domcontentloaded", timeout=30000)

    def run_collection(self, count, detail_results):
        page = Mock()
        @contextmanager
        def browser():
            yield page
        def render(_, url, **kwargs):
            if not kwargs.get("detail"):
                return listing(count)
            result = next(detail_results)
            if isinstance(result, Exception):
                raise result
            return result
        with patch("src.monitor.un_press._browser_page", side_effect=browser) as launch, patch(
                "src.monitor.un_press._render", side_effect=render) as rendered:
            result = collect_un_press_items(source())
        self.assertEqual(launch.call_count, 1)
        self.assertTrue(all(call.args[0] is page for call in rendered.call_args_list))
        return result, rendered.call_count

    def test_single_browser_full_success_and_twenty_item_cap(self):
        result, calls = self.run_collection(22, iter(detail(symbol=f"SG/SM/{i}", document=f"sgsm{i}") for i in range(20)))
        self.assertEqual(result.status, "ok")
        self.assertEqual((result.candidates, result.succeeded, result.failed, result.deferred), (22, 20, 0, 2))
        self.assertEqual(calls, 21)

    def test_three_consecutive_access_failures_defer_remaining(self):
        result, calls = self.run_collection(6, iter([TimeoutError("challenge")] * 3))
        self.assertEqual(result.status, "error")
        self.assertEqual((result.failed, result.deferred), (3, 3))
        self.assertEqual(calls, 4)
        self.assertNotIn("challenge", result.errors[0]["detail"])

    def test_success_resets_failure_streak_and_partial_stays_visible(self):
        values = [TimeoutError(), detail(symbol="SG/SM/1", document="sgsm1"),
                  TimeoutError(), TimeoutError(), TimeoutError()]
        result, _ = self.run_collection(6, iter(values))
        self.assertEqual(result.status, "partial")
        self.assertEqual((result.succeeded, result.failed, result.deferred), (1, 4, 1))

    def test_backfill_urls_share_browser_and_stop_after_three_failures(self):
        page = Mock()
        @contextmanager
        def browser():
            yield page
        urls = [f"https://press.un.org/en/2026/sgsm{i}.doc.htm" for i in range(6)]
        with patch("src.monitor.un_press._browser_page", side_effect=browser) as launch, patch(
                "src.monitor.un_press._render", side_effect=TimeoutError()) as render:
            result = collect_un_press_urls(source(), urls)
        launch.assert_called_once()
        self.assertEqual(render.call_count, 3)
        self.assertTrue(all(call.args[0] is page for call in render.call_args_list))
        self.assertEqual((result.failed, result.deferred), (3, 3))
        self.assertEqual(result.status, "error")

    def test_backfill_urls_cap_twenty_and_validate_before_browser(self):
        page = Mock()
        @contextmanager
        def browser():
            yield page
        urls = [f"https://press.un.org/en/2026/sgsm{i}.doc.htm" for i in range(22)]
        def render(_, url, **kwargs):
            document = url.rsplit('/', 1)[1].split('.')[0]
            return detail(symbol="SG/SM/" + document[4:], document=document)
        with patch("src.monitor.un_press._browser_page", side_effect=browser) as launch, patch(
                "src.monitor.un_press._render", side_effect=render) as rendered:
            result = collect_un_press_urls(source(), urls)
        launch.assert_called_once()
        self.assertEqual((result.succeeded, result.deferred), (20, 2))
        self.assertEqual(rendered.call_count, 20)
        with patch("src.monitor.un_press._browser_page") as launch:
            rejected = collect_un_press_urls(source(), ["https://evil.example/article"])
        self.assertEqual(rejected.status, "error")
        launch.assert_not_called()

    def test_filtered_listing_remains_filtered(self):
        @contextmanager
        def browser():
            yield Mock()
        html = listing(2).replace("Press Release", "Meetings Coverage")
        with patch("src.monitor.un_press._browser_page", side_effect=browser), patch(
                "src.monitor.un_press._render", return_value=html):
            result = collect_un_press_items(source())
        self.assertEqual(result.status, "filtered")
        self.assertEqual((result.candidates, result.filtered, result.failed), (2, 2, 0))

    def test_listing_challenge_is_error_without_false_success(self):
        @contextmanager
        def browser():
            yield Mock()
        with patch("src.monitor.un_press._browser_page", side_effect=browser), patch(
                "src.monitor.un_press._render", side_effect=TimeoutError("private challenge body")):
            result = collect_un_press_items(source())
        self.assertEqual(result.status, "error")
        self.assertEqual(result.succeeded, 0)
        self.assertNotIn("private challenge body", result.failure_reason)


if __name__ == "__main__":
    unittest.main()
