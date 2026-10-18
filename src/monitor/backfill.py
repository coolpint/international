"""Replay observed failed detail URLs; never infer complete archive coverage."""
import json
from urllib.parse import urlparse

from .sources import _collect_details

REPAIR_SOURCES = {'un_press_releases', 'un_meetings_coverage',
                  'unctad_publications', 'cisa_north_korea_cyber_advisories'}


def observed_failures(log_directory, source):
    urls = set()
    for path in sorted(log_directory.glob('*.ndjson')):
        for line in path.read_text().splitlines():
            report = json.loads(line)
            for entry in report.get('sources', []):
                if entry.get('source_id') != source.id:
                    continue
                for error in entry.get('errors', []):
                    if not isinstance(error, dict):
                        continue
                    url = error.get('url', '')
                    parsed = urlparse(url)
                    if parsed.scheme != 'https' or parsed.netloc != urlparse(source.list_url).netloc:
                        continue
                    if source.type == 'un_press_listing' and parsed.path.startswith('/en/') and parsed.path.endswith('.doc.htm'):
                        urls.add(url)
    return sorted(urls)


def collect_backfill(source, log_directory, current):
    urls = observed_failures(log_directory, source)
    # Don't repeat requests already attempted by normal collection this run.
    attempted = {item.url for item in current}
    attempted.update(e.get('url') for e in current.errors if isinstance(e, dict))
    urls = [url for url in urls if url not in attempted]
    from dataclasses import replace
    result = _collect_details(replace(source, max_items=max(1, len(urls))), urls) if urls else None
    return result
