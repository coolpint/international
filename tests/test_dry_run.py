"""Offline smoke test using production configuration and real collectors."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from src import main
from src.monitor.config import load_sources

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'
DETAIL = '<h1>Korea policy</h1><main><p>Republic of Korea policy cooperation with international institutions is the subject of this fixture article.</p></main>'


class OfflineDryRunTests(unittest.TestCase):
    def test_all_configured_collectors_continue_after_blocks_without_io(self):
        sources = load_sources(ROOT/'config/sources.json')
        by_url = {source.list_url: source for source in sources if source.enabled}
        blocked = {'unctad_publications', 'cisa_north_korea_cyber_advisories'}

        def request(url):
            source = by_url.get(url)
            if source is None:
                if 'press.un.org' in url:
                    raise RuntimeError('HTTP 406: fixture access restriction')
                return DETAIL, {}
            if source.id in blocked:
                raise RuntimeError('HTTP 403: fixture access restriction')
            fixture = {'ustr_press_releases':'ustr_listing.html', 'ilo_newsroom':'ilo_cards.html',
                       'bis_press_releases':'bis_feed.xml'}.get(source.id)
            if fixture:
                return (FIXTURES/fixture).read_text(), {}
            if source.type == 'rss_xml':
                domain = source.options.get('allowed_domains', [urlparse(url).netloc])[0]
                path = source.options.get('allowed_url_patterns', ['/item/'])[0]
                link = 'https://' + domain + path + 'fixture'
                return f'<rss><channel><item><title>Korea policy</title><link>{escape(link)}</link><description>Republic of Korea</description></item></channel></rss>', {}
            if source.type == 'un_news_latest':
                return '<a href="https://news.un.org/en/story/2026/10/fixture">News</a>', {}
            if source.type == 'un_press_listing':
                return '<a href="/en/2026/fixture.doc.htm">Release</a>', {}
            if source.type == 'rusi_publications':
                return '<a class="RelatedArticle-module--mainLink--4c03e" href="/explore-our-research/publications/insights-papers/fixture">Analysis</a>', {}
            if source.type == 'html_listing':
                return '<h3 class="featured-stories__headline"><a href="/news/press-releases/fixture">Treasury</a></h3>', {}
            raise AssertionError(f'Unexpected text request: {source.id}')

        def fetch_json(url, **kwargs):
            if 'worldbank.org' in url:
                return {'documents':{'fixture':{'title':'Korea policy','url':'https://www.worldbank.org/en/news/fixture','lnchdt':'2026-01-01T00:00:00Z','descr':'Republic of Korea'}}}
            if 'api.unrisd.org' in url:
                return {'data':[{'attributes':{'title':'Korea policy','slug':'fixture','summary':'Republic of Korea'}}]}
            raise AssertionError('Unexpected JSON request')

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            argv = ['monitor','--dry-run','--state',str(root/'state.json'),
                    '--history-dir',str(root/'history'),'--run-log-dir',str(root/'logs')]
            output, errors = io.StringIO(), io.StringIO()
            with patch('sys.argv',argv), patch('src.monitor.sources.fetch_text',side_effect=request), \
                 patch('src.monitor.sources.fetch_json',side_effect=fetch_json), \
                 patch('src.monitor.sources.post_json',return_value={'access_token':'mock-only'}), \
                 patch('src.monitor.http.urlopen',side_effect=AssertionError('Network disabled')) as network, \
                 patch('src.main.telegram_is_configured',return_value=True), \
                 patch('src.main.send_telegram_message') as send, \
                 contextlib.redirect_stdout(output),contextlib.redirect_stderr(errors):
                code = main.main()
            self.assertEqual(code,1)
            send.assert_not_called()
            network.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])
            text = output.getvalue()
            for source in sources:
                self.assertIn(source.id,text+errors.getvalue())
            for source_id in ['bis_press_releases','ustr_press_releases','ilo_newsroom','world_bank_news']:
                self.assertIn(f'[source] {source_id}:',text)
            self.assertIn("'status': 'error'",text)  # All UN Press details failed.
            self.assertIn('[dry-run] State files were not changed.',text)


if __name__ == '__main__': unittest.main()
