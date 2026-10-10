import argparse
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src import main, healthcheck
from src.monitor.config import load_sources
from src.monitor.models import SourceConfig, MonitoredItem
from src.monitor.sources import collect_items, CollectionResult

FIXTURES = Path(__file__).parent / 'fixtures'
SOURCES = {s.id: s for s in load_sources(Path('config/sources.json'))}
DETAIL = '<h1>Korea cooperation</h1><main><p>Republic of Korea cooperation with international institutions advances policy and economic research.</p></main>'


def listing_source(max_items=20):
    return SourceConfig('example', 'Example', 'html_listing', True,
                        'https://example.org/news', max_items,
                        options={'link_selector': 'article a[href]', 'allowed_domains': ['example.org']})


class CollectionTests(unittest.TestCase):
    def collect_details(self, responses, max_items=20):
        with patch('src.monitor.sources.fetch_text', side_effect=responses):
            return collect_items(listing_source(max_items))

    def test_all_details_blocked_is_error(self):
        result = self.collect_details([('<article><a href="/one">one</a><a href="/two">two</a></article>', {}),
                                       RuntimeError('HTTP 406'), RuntimeError('HTTP 403')])
        self.assertEqual(result.status, 'error')
        self.assertEqual((result.candidates, result.succeeded, result.failed), (2, 0, 2))
        self.assertEqual(len(result.errors), 2)

    def test_partial_details_keep_successful_items(self):
        result = self.collect_details([('<article><a href="/one">one</a><a href="/two">two</a></article>', {}),
                                       RuntimeError('HTTP 406'), (DETAIL, {})])
        self.assertEqual(result.status, 'partial')
        self.assertEqual((result.candidates, result.succeeded, result.failed), (2, 1, 1))
        self.assertEqual(result[0].url, 'https://example.org/two')

    def test_selector_mismatch_is_error_not_empty(self):
        result = self.collect_details([('<main><a href="/one">Release</a></main>', {})])
        self.assertEqual(result.status, 'error')
        self.assertEqual(result.candidates, 0)
        self.assertIn('selector', result.report()['detail'])

    def test_filtered_and_limit_exclusions_are_separate(self):
        result = self.collect_details([('<article><a href="https://outside.org/a">a</a><a href="/one">1</a><a href="/two">2</a><a href="/one">duplicate</a></article>', {}), (DETAIL, {})], max_items=1)
        self.assertEqual((result.candidates, result.filtered, result.deferred, result.failed), (3, 1, 1, 0))
        self.assertEqual(result.status, 'ok')

    def test_all_links_filtered_are_not_selector_failure(self):
        result = self.collect_details([('<article><a href="https://outside.org/a">a</a></article>', {})])
        self.assertEqual(result.status, 'filtered')
        self.assertEqual((result.candidates, result.filtered, result.failed), (1, 1, 0))

    def test_missing_article_text_fails_validation(self):
        result = self.collect_details([('<article><a href="/one">1</a></article>', {}), ('<title>Access Denied</title>', {})])
        self.assertEqual(result.status, 'error')
        self.assertEqual(result.failed, 1)

    def test_http_200_challenge_with_text_is_not_an_article(self):
        result = self.collect_details([('<article><a href="/one">1</a></article>', {}),
                                       ('<h1>Just a moment...</h1><main><p>Checking your browser before accessing this protected resource. Please wait for verification.</p></main>', {})])
        self.assertEqual(result.status, 'error')
        self.assertEqual(result.failed, 1)
        self.assertIn('challenge', result.errors[0]['detail'])

    def rss(self, xml):
        source = SourceConfig('feed','Feed','rss_xml',True,'https://example.org/feed',20)
        with patch('src.monitor.sources.fetch_text', return_value=(xml, {})):
            return collect_items(source)

    def test_valid_empty_rss_and_atom(self):
        for xml in ['<rss><channel><title>Empty</title></channel></rss>', '<feed xmlns="http://www.w3.org/2005/Atom"><title>Empty</title></feed>']:
            result = self.rss(xml)
            self.assertEqual(result.status, 'empty')
            self.assertEqual(result.candidates, 0)

    def test_invalid_xml_html_and_missing_channel_fail(self):
        for xml in ['<rss>', '<html><title>Forbidden</title></html>', '<rss/>']:
            with self.assertRaises(RuntimeError): self.rss(xml)

    def test_bad_rss_records_are_errors_and_partial_is_visible(self):
        bad = '<item><title>Missing link</title></item>'
        good = '<item><title>Good</title><link>https://example.org/item</link></item>'
        self.assertEqual(self.rss('<rss><channel>'+bad+'</channel></rss>').status, 'error')
        result = self.rss('<rss><channel>'+bad+good+'</channel></rss>')
        self.assertEqual(result.status, 'partial')
        self.assertEqual((result.candidates, result.failed, result.succeeded), (2, 1, 1))

    def test_fallback_checks_document_type_before_selecting(self):
        source = SourceConfig('feed','Feed','rss_xml',True,'https://example.org/feed',20,
                              options={'fallback_urls':['https://example.org/backup']})
        with patch('src.monitor.sources.fetch_text', side_effect=[('<html/>', {}), ('<rss><channel/></rss>', {})]):
            result = collect_items(source)
        self.assertEqual(result.status, 'empty')
        self.assertEqual(result.selected_url, 'https://example.org/backup')
        self.assertTrue(result.errors)

    def test_current_bis_fixture_keeps_new_media_release_paths(self):
        with patch('src.monitor.sources.fetch_text', return_value=((FIXTURES/'bis_feed.xml').read_text(), {})):
            result = collect_items(SOURCES['bis_press_releases'])
        self.assertEqual(result.status, 'ok')
        self.assertEqual(result.filtered, 0)
        self.assertTrue(all('/media-releases/' in item.url for item in result))
        self.assertEqual(len(result), 3)

    def test_current_ustr_and_ilo_listing_fixtures(self):
        for source_id, fixture in [('ustr_press_releases','ustr_listing.html'), ('ilo_newsroom','ilo_cards.html')]:
            source = SOURCES[source_id]
            def request(url):
                return ((FIXTURES/fixture).read_text(), {}) if url == source.list_url else (DETAIL, {})
            with patch('src.monitor.sources.fetch_text', side_effect=request):
                result = collect_items(source)
            self.assertEqual(result.status, 'ok')
            self.assertGreater(result.candidates, 0)
            self.assertEqual(result.failed, 0)

    def test_api_missing_schema_is_not_empty(self):
        with patch('src.monitor.sources.fetch_json', return_value={}):
            with self.assertRaises(RuntimeError): collect_items(SOURCES['world_bank_news'])
        with patch('src.monitor.sources.post_json', return_value={'access_token':'fixture-token'}), patch('src.monitor.sources.fetch_json', return_value={}):
            with self.assertRaises(RuntimeError): collect_items(SOURCES['unrisd_news'])


class MonitorIntegrationTests(unittest.TestCase):
    def run_monitor(self, dry_run, results, initial_state=None, revision=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(sources='unused', keywords='unused',state=str(root/'state.json'),
                history_dir=str(root/'history'),run_log_dir=str(root/'logs'),dry_run=dry_run,test_telegram=False)
            if initial_state is not None:
                (root/'state.json').write_text(json.dumps(initial_state))
            sources=[listing_source(), SourceConfig('normal','Normal','rss_xml',True,'https://example.org/feed',20)]
            if revision is not None:
                sources[0].options['collection_revision'] = revision
            with patch('src.main.parse_args',return_value=args), patch('src.main.load_sources',return_value=sources), \
                 patch('src.main.load_keywords',return_value={}), patch('src.main.collect_items',side_effect=results), \
                 patch('src.main.telegram_is_configured',return_value=True), \
                 patch('src.main.classify_item',return_value=main.Classification(True,'high',['Korea'])), \
                 patch('src.main.send_telegram_message') as send, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code=main.main()
            send.assert_not_called()
            if dry_run:
                self.assertEqual(list(root.iterdir()), [] if initial_state is None else [root/'state.json'])
                return code, None, None
            state=json.loads((root/'state.json').read_text())
            report=json.loads(next((root/'logs').glob('*.ndjson')).read_text())
            return code,state,report

    def good(self, source_id='normal'):
        result=CollectionResult();result.candidates=result.succeeded=1
        result.append(MonitoredItem(source_id,'Normal','https://example.org/good','Korea','Korea policy','Korea body'))
        return result

    def test_dry_run_has_no_writes_or_notifications_when_one_source_fails(self):
        code,_,_=self.run_monitor(True,[RuntimeError('HTTP 403'),self.good()])
        self.assertEqual(code,1)

    def test_failure_persists_normal_source_and_diagnostic_in_isolated_directory(self):
        code,state,report=self.run_monitor(False,[RuntimeError('HTTP 403'),self.good()])
        self.assertEqual(code,1)
        self.assertIn('https://example.org/good',state['items'])
        self.assertEqual([s['status'] for s in report['sources']],['error','ok'])
        self.assertNotIn('example',state['source_bootstrapped_at'])
        self.assertIn('normal',state['source_bootstrapped_at'])

    def test_partial_source_cannot_complete_bootstrap(self):
        partial=self.good();partial.failed=1;partial.candidates=2
        code,state,report=self.run_monitor(False,[partial,self.good()])
        self.assertEqual(code,1)
        self.assertEqual(report['sources'][0]['status'],'partial')
        self.assertNotIn('example',state['source_bootstrapped_at'])

    def test_valid_empty_source_is_success(self):
        code,_,_=self.run_monitor(True,[CollectionResult(),self.good()])
        self.assertEqual(code,0)

    def test_repaired_source_rebaselines_existing_updates_without_notifications(self):
        state={'bootstrapped': True, 'source_bootstrapped_at': {'example':'2026-01-01T00:00:00Z'},
               'items': {'https://example.org/good': {'source_id':'example','content_hash':'old',
                         'first_seen_at':'2026-01-01T00:00:00Z'}}}
        code,updated,report=self.run_monitor(False,[self.good('example'),CollectionResult()],state,'repair-v1')
        self.assertEqual(code,0)
        self.assertTrue(report['sources'][0]['bootstrapping'])
        self.assertEqual(updated['collection_revisions']['example'],'repair-v1')
        self.assertEqual(report['summary']['notified'],0)

    def test_partial_repair_does_not_record_revision(self):
        partial=self.good('example');partial.failed=1
        _,state,_=self.run_monitor(False,[partial,CollectionResult()],revision='repair-v1')
        self.assertNotIn('example',state['collection_revisions'])


class SourceHealthTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,10,12,tzinfo=timezone.utc)
        self.runs=[{'conclusion':'success','updated_at':self.now.isoformat()}]*3

    def log(self,hours,status='ok',collected=0,**extra):
        return {'run_at':(self.now-timedelta(hours=hours)).isoformat(),
                'sources':[{'source_id':'example','status':status,'collected':collected,**extra}]}

    def report(self,logs,history=None):
        return healthcheck.build_health_report(self.runs,[],logs,self.now,1,history)

    def test_legacy_ok_zero_streak_is_warning_and_does_not_prove_health(self):
        report=self.report([self.log(16),self.log(8),self.log(0)])
        self.assertEqual(report.status,'warning')
        self.assertIn('연속 0건 3회',report.message)
        self.assertIn('마지막 정상 시각 없음',report.message)

    def test_partial_and_last_normal_before_window(self):
        old=self.log(48,'ok',10)
        recent=self.log(0,'partial',1)
        report=self.report([recent],[old,recent])
        self.assertEqual(report.status,'warning')
        self.assertIn('소스 에러가 1회',report.message)
        self.assertIn('2026-10-08',report.message)

    def test_success_resets_streak_and_unsorted_history_is_sorted(self):
        report=self.report([self.log(0,'ok',5),self.log(8),self.log(16),self.log(24)])
        self.assertEqual(report.status,'healthy')
        self.assertIn('연속 0건 0회',report.message)

    def test_one_verified_empty_feed_is_healthy(self):
        self.assertEqual(self.report([self.log(0,'empty',0,candidates=0)]).status,'healthy')

    def test_disabled_sources_do_not_warn(self):
        self.assertEqual(self.report([self.log(0,'error',0,enabled=False)]).status,'healthy')


if __name__ == '__main__': unittest.main()
