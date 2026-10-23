import argparse
import contextlib
import io
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from src import healthcheck
from src.monitor.models import SourceConfig


class WeeklyDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,18,23,tzinfo=timezone.utc)
        self.runs=[{'conclusion':'success','updated_at':self.now.isoformat()}]*3
        self.source={'source_id':'source','enabled':True,'status':'ok','collected':1,'candidates':1}

    def log(self, hours=0, **extra):
        return {'run_at':(self.now-timedelta(hours=hours)).isoformat(),'sources':[self.source],**extra}

    def build(self, logs, history=None, state=None):
        return healthcheck.build_health_report(self.runs,history or [],logs,self.now,1,monitor_state=state)

    def test_retried_deliveries_count_even_without_history_events(self):
        logs=[self.log(8,delivery={'delivered':0,'item_delivered':0,'health_delivered':0,'failed':1,'pending':1}),self.log(delivery={'delivered':2,'item_delivered':1,'health_delivered':1,'failed':0,'pending':0})]
        history=[{'run_at':logs[0]['run_at'],'event':'new','notification_error':'old failed attempt'}]
        report=self.build(logs,history,{'notification_outbox':{}})
        self.assertIn('실제 전송 1건',report.message)
        self.assertIn('장애·복구 알림 전송: 1건',report.message)
        self.assertIn('현재 전송 대기: 0건',report.message)
        self.assertIn('실패 시도가 1회',report.message)

    def test_modern_and_legacy_counts_do_not_double_count(self):
        log=self.log(delivery={'delivered':3,'item_delivered':2,'health_delivered':1,'failed':0,'pending':0})
        history=[{'run_at':log['run_at'],'notified':True},{'run_at':self.log(8)['run_at'],'notified':True}]
        self.assertIn('실제 전송 3건',self.build([log],history).message)

    def test_current_outbox_overrides_historical_pending_and_flags_new_failure(self):
        log=self.log(delivery={'delivered':0,'item_delivered':0,'failed':0,'pending':0})
        state={'notification_outbox':{'item:a':{'kind':'item','attempts':2},'health:b':{'kind':'health','attempts':1}}}
        report=self.build([log],state=state)
        self.assertEqual(report.status,'warning')
        self.assertIn('전송 대기: 2건 (자료 1, 장애·복구 1)',report.message)
        self.assertIn('전송 대기가 2건',report.message)

    def test_three_verified_filtered_or_empty_responses_are_healthy(self):
        for source in [dict(self.source,status='filtered',collected=0,candidates=15,filtered=15,failed=0),dict(self.source,status='empty',collected=0,candidates=0,failed=0)]:
            logs=[{**self.log(h),'sources':[source]} for h in [16,8,0]]
            report=self.build(logs)
            self.assertEqual(report.status,'healthy');self.assertIn('연속 0건 0회',report.message)

    def test_inconsistent_filtered_zero_is_still_a_warning(self):
        source=dict(self.source,status='filtered',collected=0,candidates=15,filtered=1,failed=0)
        report=self.build([{**self.log(h),'sources':[source]} for h in [16,8,0]])
        self.assertEqual(report.status,'warning');self.assertIn('연속 0건 3회',report.message)

    def test_latest_total_failure_remains_explicit_error(self):
        report=self.build([self.log(status='total_failure')])
        self.assertEqual(report.status,'error');self.assertIn('전체 수집 실패',report.message)

    def test_long_report_chunks_preserve_all_text_and_fit_telegram_limit(self):
        text=('source: 한국 관련 점검 🧭\n'*500)+'tail'
        chunks=healthcheck._slack_chunks(text)
        self.assertGreater(len(chunks),1);self.assertEqual(''.join(chunks),text)
        self.assertTrue(all(len(chunk.encode('utf-16-le'))//2<=3500 for chunk in chunks))

    def run_main(self,total=False,send_failure=False):
        with tempfile.TemporaryDirectory() as d:
            args=argparse.Namespace(days=1,workflow_file='monitor.yml',history_dir=d,run_log_dir=d,state=str(Path(d)/'state.json'),dry_run=False)
            log=self.log(status='total_failure' if total else 'partial_failure')
            log['sources']=[dict(self.source,status='error',collected=0,detail='HTTP 406')]
            with patch('src.healthcheck.parse_args',return_value=args),patch('src.healthcheck.utc_now',return_value=self.now),patch('src.healthcheck._load_ndjson_since',return_value=[log]),patch('src.healthcheck.load_monitor_runs',return_value=self.runs),patch('src.healthcheck.load_sources',return_value=[SourceConfig('source','Source','rss_xml',True,'https://example.org',20)]),patch('src.healthcheck.slack_is_configured',return_value=True),patch('src.healthcheck.send_slack_text',side_effect=RuntimeError('unconfirmed') if send_failure else None) as send,contextlib.redirect_stdout(io.StringIO()):
                if send_failure:
                    with self.assertRaises(RuntimeError):healthcheck.main()
                    return
                code=healthcheck.main();send.assert_called()
                return code

    def test_successfully_delivered_warning_does_not_fail_weekly_job(self):
        self.assertEqual(self.run_main(),0)

    def test_total_failure_and_actual_send_failure_still_fail(self):
        self.assertEqual(self.run_main(total=True),1)
        self.run_main(send_failure=True)
