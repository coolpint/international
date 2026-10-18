"""One explicitly verified co-publisher archive; never a discovery replacement."""
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

from .http import DEFAULT_HEADERS
from .models import MonitoredItem

FBI_AA24_207A = 'https://www.fbi.gov/file-repository/north-korea-cyber-group-conducts-global-espionage-campaign-to-advance-regimes-military-and-nuclear-programs-072524.pdf'
CISA_AA24_207A = 'https://www.cisa.gov/news-events/cybersecurity-advisories/aa24-207a'


def fetch_archive_bytes(url):
    # No proxy, challenge handling, alternate identity or credentials.
    if url != FBI_AA24_207A:
        raise ValueError('unverified archive URL')
    try:
        with urlopen(Request(url, headers=DEFAULT_HEADERS), timeout=30) as response:
            if urlparse(response.geturl()).hostname != 'www.fbi.gov':
                raise ValueError('archive redirected outside verified publisher')
            data = response.read(5 * 1024 * 1024 + 1)
    except HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code} for official FBI AA24-207A archive') from None
    except URLError:
        raise RuntimeError('official FBI archive request failed') from None
    if len(data) > 5 * 1024 * 1024 or not data.startswith(b'%PDF'):
        raise ValueError('official archive is not a bounded PDF response')
    return data


def collect_verified_archive(source, canonical_url, primary_error):
    if source.id != 'cisa_north_korea_cyber_advisories' or canonical_url != CISA_AA24_207A:
        return None
    reader = PdfReader(BytesIO(fetch_archive_bytes(FBI_AA24_207A)))
    if len(reader.pages) != 30:
        raise ValueError('AA24-207A archive has unexpected page count')
    pages = [page.extract_text() or '' for page in reader.pages]
    if not all(text.strip() for text in pages):
        raise ValueError('archive contains pages without readable text')
    text = '\n'.join(pages)
    first_page = ' '.join(pages[0].split())
    if 'AA24-207A' not in first_page or 'July 25, 2024' not in first_page:
        raise ValueError('official archive advisory ID/date mismatch')
    return MonitoredItem(
        source_id=source.id, source_label=source.label, url=canonical_url,
        title='North Korea Cyber Group Conducts Global Espionage Campaign to Advance Regime’s Military and Nuclear Programs',
        summary='Official co-published AA24-207A archive, issued July 25, 2024; current CISA page unavailable.',
        body=text, published_at='2024-07-25', archive_fallback=True,
        retrieval_url=FBI_AA24_207A,
        retrieval_note=str(primary_error),
    )
