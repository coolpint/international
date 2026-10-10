# Fixture provenance

Public official GET responses read on Skyblue.local, 2026-10-10 UTC, using the repository's existing HTTP client without cookies, challenges, proxies, or new credentials:

- `ustr_listing.html`: `https://ustr.gov/about-us/policy-offices/press-office/press-releases`, retained `ul.listing` subtree (29 distinct article links). The old `div.view-content div.views-row .views-field-title a[href]` selector matched zero links.
- `ilo_cards.html`: `https://www.ilo.org/resource/news`, retained `a.ilo--card--link` elements. Eight links pass the configured article/news/statement path filters. `/rss.xml` returned HTML instead of a news feed.
- `bis_feed.xml`: `https://www.bis.org/doclist/all_pressrels.rss`, original XML structure with only the first three items retained. The item links use `/media-releases/`.

Detail bodies, blocked responses, empty feeds and invalid records in tests are synthetic. No operational state or credentials are included. These fixtures freeze a structure for regression tests; they do not prove future availability from GitHub Actions.
