import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src import main
from src.monitor.delivery import queue_item, queue_health, deliver_outbox, collection_status
from src.monitor.models import MonitoredItem, SourceConfig, Classification
from src.monitor.state import register_item, load_state, save_state
from src.monitor.sources import CollectionResult, collect_items
from src.monitor.backfill import observed_failures, collect_backfill
from src.monitor.notifier import send_telegram_text


def article(title='Korea policy'):
    return MonitoredItem('source', 'Source', 'https://example.org/article', title,
                         'Republic of Korea', 'Full body Republic of Korea', confidence='high')


def report(status='error', detail='HTTP 403 for https://example.org/a: challenge abc'):
    return {'source_id':'source','source_label':'Source','enabled':True,'status':status,
            'detail':detail,'collected':1 if status in {'ok','partial'} else 0,
            'succeeded':1 if status in {'ok','partial'} else 0,'failed':1 if status=='partial' else 0}


class DeliveryTests(unittest.TestCase):
    def test_retry_survives_restart_and_absent_article(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json'; state={}; item=article()
            event=register_item(state,item,'t1'); queue_item(state,item,event['event'])
            checkpoint=lambda: save_state(p,state)
            failed=Mock(side_effect=RuntimeError('secret bot URL'))
            result=deliver_outbox(state,'t1',failed,Mock(),checkpoint)
            self.assertEqual(result['pending'],1)
            self.assertNotIn('secret',p.read_text())
            state=load_state(p)
            self.assertIsNone(register_item(state,item,'t2'))
            sent=Mock();deliver_outbox(state,'t2',sent,Mock(),lambda:save_state(p,state))
            sent.assert_called_once();self.assertFalse(state['notification_outbox'])
            self.assertEqual(state['items'][item.url]['last_notified_at'],'t2')
            deliver_outbox(state,'t3',sent,Mock(),lambda:None)
            sent.assert_called_once()

    def test_changed_unsent_article_supersedes_old_version(self):
        state={}
        for title in ['old','new']:
            item=article(title);e=register_item(state,item,'t');queue_item(state,item,e['event'])
        send=Mock(); deliver_outbox(state,'t',send,Mock(),lambda:None)
        self.assertEqual(send.call_args.args[0].title,'new');send.assert_called_once()

    def test_health_first_change_recovery_dedup_and_request_url_churn(self):
        state={}; send=Mock()
        def run(r,t):
            queue_health(state,[r],t);return deliver_outbox(state,t,Mock(),send,lambda:None)
        run(report(),'t1');self.assertEqual(send.call_count,1)
        run(report(detail='HTTP 403 for https://example.org/new: challenge xyz'),'t2')
        self.assertEqual(send.call_count,1)
        run(report(detail='HTTP 406 for https://example.org/new: Not acceptable'),'t3')
        self.assertEqual(send.call_count,2)
        run(report('ok',None),'t4');self.assertEqual(send.call_count,3)
        self.assertIn('복구',send.call_args.args[0])
        run(report('ok',None),'t5');self.assertEqual(send.call_count,3)

    def test_failed_health_send_persists_attempts_then_retries(self):
        state={};queue_health(state,[report()],'t1')
        send=Mock(side_effect=TimeoutError())
        deliver_outbox(state,'t1',Mock(),send,lambda:None)
        queue_health(state,[report()],'t2')
        self.assertEqual(state['notification_outbox']['health:source']['attempts'],1)
        send.side_effect=None;deliver_outbox(state,'t2',Mock(),send,lambda:None)
        queue_health(state,[report()],'t3');self.assertFalse(state['notification_outbox'])

    def test_recovery_replaces_pending_failure(self):
        state={};queue_health(state,[report()],'t1')
        queue_health(state,[report('ok',None)],'t2')
        send=Mock();deliver_outbox(state,'t2',Mock(),send,lambda:None)
        self.assertIn('복구',send.call_args.args[0]);send.assert_called_once()

    def test_status_distinguishes_success_partial_total(self):
        self.assertEqual(collection_status([report('ok',None)]),'success')
        self.assertEqual(collection_status([report(),report('ok',None)]),'partial_failure')
        self.assertEqual(collection_status([report('partial')]),'partial_failure')
        self.assertEqual(collection_status([report()]),'total_failure')
        self.assertEqual(collection_status([{**report(), 'backfill':{'succeeded':1}}]),'partial_failure')

    def test_telegram_rejection_invalid_json_and_token_redaction(self):
        for response in ['{"ok":false}','not json']:
            with patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'sensitive','TELEGRAM_CHAT_ID':'existing'}), patch('src.monitor.notifier.post_form',return_value=response):
                with self.assertRaisesRegex(RuntimeError,'not confirmed'): send_telegram_text('alert')
        with patch.dict('os.environ',{'TELEGRAM_BOT_TOKEN':'sensitive','TELEGRAM_CHAT_ID':'existing'}), patch('src.monitor.notifier.post_form',side_effect=RuntimeError('https://api.telegram.org/botsensitive')):
            with self.assertRaises(RuntimeError) as e:send_telegram_text('alert')
            self.assertNotIn('sensitive',str(e.exception))


class RecoveryTests(unittest.TestCase):
    def test_cisa_seed_recovery_keeps_listing_failure_visible_and_canonical_urls(self):
        source=SourceConfig('cisa','CISA','html_listing',True,'https://www.cisa.gov/north-korea',20,
            options={'link_selector':'table a[href]','recovery_detail_urls':['https://www.cisa.gov/news-events/cybersecurity-advisories/aa24-207a']})
        detail='<h1>North Korea advisory</h1><article><p>This is the official full advisory body, North Korea malicious actors and defenses.</p></article>'
        with patch('src.monitor.sources.fetch_text',side_effect=[RuntimeError('HTTP 403'),(detail,{})]):
            result=collect_items(source)
        self.assertEqual(result.status,'partial');self.assertEqual(len(result),1)
        self.assertIn('only known',result.failure_reason);self.assertIn('HTTP 403',result.errors[0]['detail'])

    def test_backfill_uses_only_observed_official_urls_and_skips_current_attempts(self):
        source=SourceConfig('un_press_releases','UN','un_press_listing',True,'https://press.un.org/en/content/press-release',20)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'2026-10.ndjson'
            urls=['https://press.un.org/en/2026/one.doc.htm','https://press.un.org/en/2026/two.doc.htm','https://evil.org/en/2026/bad.doc.htm','https://press.un.org/en/rss.xml']
            p.write_text(json.dumps({'sources':[{'source_id':source.id,'errors':[{'url':u} for u in urls]}]})+'\n')
            self.assertEqual(observed_failures(Path(d),source),urls[:2])
            current=CollectionResult();current.errors=[{'url':urls[0]}]
            with patch('src.monitor.sources.fetch_text',return_value=('<h1>Korea</h1><main><p>Republic of Korea cooperation article body is long enough for the extraction rule.</p></main>',{})) as fetch:
                result=collect_backfill(source,Path(d),current)
            fetch.assert_called_once_with(urls[1]);self.assertEqual(result[0].url,urls[1])


class FullRunTests(unittest.TestCase):
    def test_failed_article_retries_next_run_without_new_event_or_collection(self):
        source=SourceConfig('source','Source','rss_xml',True,'https://example.org/feed',20)
        result=CollectionResult();result.candidates=result.succeeded=1;result.append(article())
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'state.json'
            save_state(p,{'bootstrapped':True,'source_bootstrapped_at':{'source':'t0'},'items':{}})
            args=argparse.Namespace(sources='',keywords='',state=str(p),history_dir=str(root/'history'),run_log_dir=str(root/'logs'),dry_run=False,test_telegram=False)
            with patch('src.main.parse_args',return_value=args), patch('src.main.load_sources',return_value=[source]), patch('src.main.load_keywords',return_value={}), patch('src.main.classify_item',return_value=Classification(True,'high',['Korea'])), patch('src.main.telegram_is_configured',return_value=True), patch('src.main.send_telegram_text'), contextlib.redirect_stdout(io.StringIO()):
                with patch('src.main.collect_items',return_value=result), patch('src.main.send_telegram_message',side_effect=TimeoutError()) as send:
                    self.assertEqual(main.main(),1)
                self.assertEqual(len(load_state(p)['notification_outbox']),1)
                with patch('src.main.collect_items',return_value=CollectionResult()), patch('src.main.send_telegram_message') as send:
                    self.assertEqual(main.main(),0);send.assert_called_once()
                self.assertFalse(load_state(p)['notification_outbox'])

    def test_all_sources_unavailable_still_persists_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);args=argparse.Namespace(sources='',keywords='',state=str(root/'state.json'),history_dir=str(root/'history'),run_log_dir=str(root/'logs'),dry_run=False,test_telegram=False)
            source=SourceConfig('source','Source','rss_xml',True,'https://example.org/feed',20)
            with patch('src.main.parse_args',return_value=args), patch('src.main.load_sources',return_value=[source]), patch('src.main.load_keywords',return_value={}), patch('src.main.collect_items',side_effect=RuntimeError('HTTP 403')), patch('src.main.telegram_is_configured',return_value=True), patch('src.main.send_telegram_text') as send, contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main.main(),1);send.assert_called_once()
            log=json.loads(next((root/'logs').glob('*')).read_text());self.assertEqual(log['status'],'total_failure')

    def test_backfill_survives_listing_failure_and_preserves_high_confidence_dedupe(self):
        source=SourceConfig('un_press_releases','UN','un_press_listing',True,'https://press.un.org/en/content/press-release',20)
        item=article();item.source_id=source.id
        recovered=CollectionResult();recovered.candidates=recovered.succeeded=1;recovered.append(item)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'state.json'
            save_state(p,{'bootstrapped':True,'source_bootstrapped_at':{source.id:'t0'},'items':{}})
            args=argparse.Namespace(sources='',keywords='',state=str(p),history_dir=str(root/'history'),run_log_dir=str(root/'logs'),dry_run=False,test_telegram=False,backfill=True)
            with patch('src.main.parse_args',return_value=args), patch('src.main.load_sources',return_value=[source]), patch('src.main.load_keywords',return_value={}), patch('src.main.classify_item',return_value=Classification(True,'high',['Korea'])), patch('src.main.collect_items',side_effect=RuntimeError('HTTP 406')), patch('src.main.collect_backfill',return_value=recovered) as backfill, patch('src.main.telegram_is_configured',return_value=True), patch('src.main.send_telegram_text'), patch('src.main.send_telegram_message') as send, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                main.main();main.main()
                self.assertEqual(backfill.call_count,2);send.assert_called_once()
            logs=[json.loads(l) for l in next((root/'logs').glob('*')).read_text().splitlines()]
            self.assertEqual(logs[0]['sources'][0]['backfill']['succeeded'],1)

    def test_missing_telegram_keeps_eligible_delivery_pending(self):
        source=SourceConfig('source','Source','rss_xml',True,'https://example.org/feed',20)
        result=CollectionResult();result.candidates=result.succeeded=1;result.append(article())
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'state.json'
            save_state(p,{'bootstrapped':True,'source_bootstrapped_at':{'source':'t0'},'items':{}})
            args=argparse.Namespace(sources='',keywords='',state=str(p),history_dir=str(root/'history'),run_log_dir=str(root/'logs'),dry_run=False,test_telegram=False)
            with patch('src.main.parse_args',return_value=args), patch('src.main.load_sources',return_value=[source]), patch('src.main.load_keywords',return_value={}), patch('src.main.classify_item',return_value=Classification(True,'high',['Korea'])), patch('src.main.collect_items',return_value=result), patch('src.main.telegram_is_configured',return_value=False), patch('src.main.send_telegram_message') as send, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main.main(),1);send.assert_not_called()
            self.assertEqual(len(load_state(p)['notification_outbox']),1)
