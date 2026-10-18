import unittest
from unittest.mock import Mock,patch
from src.monitor.archive import collect_verified_archive,CISA_AA24_207A,FBI_AA24_207A
from src.monitor.models import SourceConfig
from src.monitor.state import register_item


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.source=SourceConfig('cisa_north_korea_cyber_advisories','CISA','html_listing',True,'https://www.cisa.gov/north-korea',20)

    def item(self,id='AA24-207A',date='July 25, 2024',pages=30):
        page=Mock();page.extract_text.return_value=f'{id} {date} Republic of Korea official archive body'
        reader=Mock();reader.pages=[page]*pages
        with patch('src.monitor.archive.fetch_archive_bytes',return_value=b'%PDFfixture'),patch('src.monitor.archive.PdfReader',return_value=reader):
            return collect_verified_archive(self.source,CISA_AA24_207A,RuntimeError('HTTP 403'))

    def test_only_verified_canonical_advisory_has_archive(self):
        self.assertIsNone(collect_verified_archive(self.source,'https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-040a','HTTP 403'))
        item=self.item();self.assertTrue(item.archive_fallback)
        self.assertEqual(item.url,CISA_AA24_207A);self.assertEqual(item.retrieval_url,FBI_AA24_207A)
        self.assertEqual(item.published_at,'2024-07-25')

    def test_wrong_id_date_or_page_count_are_rejected(self):
        for opts in [{'id':'AA23-040A'},{'date':'July 25, 2026'},{'pages':29}]:
            with self.assertRaises(ValueError):self.item(**opts)

    def test_existing_archive_does_not_change_original_hash_or_notify(self):
        state={'items':{CISA_AA24_207A:{'content_hash':'original','last_notified_at':'previous','first_seen_at':'baseline'}}}
        self.assertIsNone(register_item(state,self.item(),'now'))
        record=state['items'][CISA_AA24_207A]
        self.assertEqual(record['content_hash'],'original');self.assertEqual(record['last_notified_at'],'previous')
        self.assertEqual(record['archive_reference']['advisory_id'],'AA24-207A')

    def test_unseen_old_archive_is_baseline_not_new_alert(self):
        state={};event=register_item(state,self.item(),'now')
        self.assertEqual(event['event'],'bootstrap');self.assertFalse(event['notified'])

    def test_fallback_remains_partial_and_preserves_primary_error(self):
        from src.monitor.sources import _collect_details
        with patch('src.monitor.sources._fetch_detail_item',return_value=self.item()):
            result=_collect_details(self.source,[CISA_AA24_207A])
        self.assertEqual(result.status,'partial')
        self.assertEqual(result.succeeded,1);self.assertIn('current primary',result.failure_reason)
        self.assertIn('HTTP 403',result.errors[0]['detail'])
