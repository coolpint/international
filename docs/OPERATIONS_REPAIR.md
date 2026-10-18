# Collection and delivery repair (2026-10-18)

This repair is based on clean main `68d2dc1`. No pre-existing working changes
were present in the new checkout. Existing state, history, URL keys and keyword
rules are preserved. Operations use only the existing Actions Telegram secrets.

## Collection scope and unresolved restrictions

- UN type-specific lists now use `/en/content/press-release` and
  `/en/content/meetings-coverage`, both linked in the official site navigation.
  Ordinary GET requests returned article links locally. A sample article still
  returned HTTP 406. These list repairs do not recover inaccessible article text.
- UN's `/en/rss.xml` is a short, mixed feed. It is not used as a full-text or
  type-equivalent replacement.
- UNCTAD `/publications` and `/rss.xml` returned HTTP 403 challenge locally.
  No equivalent official discovery/full-text replacement has been verified.
  Collection continues to report this error. An official accessible API/feed or
  a publisher-approved access channel is required for complete recovery.
- The CISA North Korea list locally contains two advisory links, `aa24-207a`
  and `aa23-040a`. Both original article pages returned readable bodies. When
  Actions cannot load the list, these two verified original URLs are retried.
  This is explicitly **partial coverage**: discovery of future list additions
  remains unavailable. The official overview page links only one of the two;
  `/cybersecurity-advisories/all.xml` contains 30 recent records and neither
  original advisory. Neither is treated as an equivalent replacement list.
- No challenge-solving, proxy, identity/header rotation, alternate credentials,
  new recipient, or security setting changes are introduced.

## Backfill

Dispatch `monitor.yml` with `mode=backfill` (or `python -m src.main --backfill`).
It runs normal collection and also replays distinct UN article URLs actually
recorded in historical source errors, excluding URLs already attempted this run.
Historical replay stops after three consecutive HTTP 403/406 responses and
reports remaining candidates as deferred, rather than repeatedly loading a
source that is still refusing requests. A later explicit backfill can retry.
Only HTTPS canonical `press.un.org/en/*.doc.htm` URLs are accepted. All recovered
articles pass the unchanged relevance/confidence rules and URL/content dedupe.
Only existing high-confidence Korea-related new/updated items may be sent.

The baseline contains 29 distinct failed UN press article URLs and 49 meeting
article URLs. Historical UNCTAD/CISA list failures did not record unknown article
URLs. Replaying observed failures cannot prove an exhaustive archive backfill.
Longer listing outages can hide documents never observed by this monitor; those
remain unquantified until the publisher provides accessible archive discovery.
Replay also runs if the current type-specific list itself is unavailable.
Nested `backfill` counters in each source's run report preserve replay outcomes.

## Status, alerts and delivery

Run reports distinguish `success`, `partial_failure` and `total_failure`.
Partial source failures emit an Actions warning and persistent source reports;
other sources continue. Total collection failure exits 1. Any pending delivery
also exits 1, even when some collection succeeds. Unconfigured Telegram retains
eligible items/health alerts in the outbox instead of silently discarding them.

Source health alerts are sent on first failure, changed status/cause, and
recovery. HTTP cause signatures ignore article URL/challenge-ID churn. A pending
health alert is superseded by the current condition. Repeated unchanged failures
do not send duplicate alerts after confirmed delivery.

Items and health alerts share a persistent `notification_outbox`. Eligible item
payloads are queued before delivery, independently of `register_item` returning
an event on later runs. Retry works even if the article disappears from the
current feed. Newer unsent content replaces the previous pending URL version.
Telegram's JSON `ok=true` is required for acknowledgment. Error payloads never
include transport URLs, tokens, or recipient IDs. State writes use atomic replace.
The workflow commits state after a normal monitor success or failure.

Delivery is at least once: a process/machine loss or ambiguous network timeout
after Telegram acceptance but before durable acknowledgment can cause a repeat.
Telegram `sendMessage` provides no application idempotency key. This limitation
cannot be eliminated by claiming exactly-once delivery.

## Verification

69 offline regression tests pass, including production-config dry-run without
network, disk writes or sends; partial/total failures; explicit partial CISA
recovery; historical replay allowlisting; unchanged/absent item retry after state
reload; newest-version replacement; Telegram rejection and token redaction;
first/change/recovery alert dedupe and failed-health retry. The same suite runs
inside the operational Actions workflow before collection. Runtime verification
results are recorded below after dispatch.


## Actual Actions verification (2026-10-18 UTC)

Code commits: initial repair `da513c1acf2d1cea455443fbcc5099f8c6352cd6`,
listing-outage replay follow-up `e13f37c`, bounded replay
`fbcc3f69ad0aef2a9c3f66f49fccb861ead3486a`.

| Run | Regression tests | Collected | Relevant observations | New/updated | Telegram item / health sends | Failed / pending |
|---|---:|---:|---:|---:|---:|---:|
| [39173971218](https://github.com/coolpint/international/actions/runs/39173971218) | 66 passed | 243 | 18 | 0 / 0 | 0 / 4 | 0 / 0 |
| [39174538700](https://github.com/coolpint/international/actions/runs/39174538700) | 69 passed | 243 | 17 | 0 / 0 | 0 / 0 | 0 / 0 |

Both Actions jobs concluded success, while their persisted collection status is
explicitly `partial_failure`, with warnings and four remaining failed sources.
State commits are `81482a3` and `616ec7d`. The second run confirms that the same
four incidents do not resend alerts after acknowledged Telegram delivery.
Retry after failed Telegram delivery and recovery alerts were validated with
isolated mocks/state reload, rather than deliberately breaking the live channel.

Actual outstanding coverage:

- UN Press: first run attempted 11 current article URLs and 20 other observed
  historical URLs; all 31 returned HTTP 406. The initial historical set was 29,
  and two additional current URLs enlarged the observed union to 31. Second run
  retried 3 historical URLs, again 406, and deferred 17 already denied in run 1.
- UN Meetings: the type-specific list itself returned HTTP 406. The final replay
  still loaded the 49 historically observed article URLs, attempted 3 (all 406),
  and explicitly deferred 46. These 46 were not individually retried in this
  repair session. There is no claim of complete historical recovery.
- UNCTAD list returned HTTP 403 in both runs. Unknown publications during the
  discovery outage cannot be counted or backfilled without accessible official
  archive discovery.
- CISA list **and both known original articles** returned HTTP 403 in Actions.
  Local access to those two pages succeeded, but their existing collector hashes
  matched stored state (8,226 / 6,218 extracted body characters respectively).
  This does not restore scheduled Actions discovery or prove an exhaustive
  North Korea advisory archive. No duplicate baseline articles were sent.

No missing article was successfully recovered for supplementary delivery. Four
failure alerts were sent only to the existing configured Telegram destination.
All original state URL keys and content hashes remained intact across both runs.
One previously observed FBI article was absent from the second relevant-observation
set; its existing state record was retained. No new recipients, credentials or
security settings were introduced or changed. Complete collection recovery still
requires a verified accessible official API/feed/archive or a publisher-approved
access channel; restriction bypasses were neither attempted nor configured.


## Follow-up: weekly reconciliation and verified archive

The weekly report now reads the current `notification_outbox` and run-log
`delivery` acknowledgments. Successful retries without a new history event count
as actual item deliveries; health deliveries are listed separately. Modern
history events are not counted again alongside run delivery totals. Legacy
history-only rows remain supported. Current backlog is distinct from historical
failed attempts, including attempts later recovered. Verified empty/fully
filtered responses reset the zero streak; inconsistent or legacy unverified
zeros remain warnings. A successfully delivered warning report exits 0 with an
Actions warning. Explicit latest `total_failure` and report/API/Telegram errors
still fail the check. Long reports are split within Telegram's UTF-16 size limit.
The weekly workflow retains its original read-only permissions and secrets.

The official co-published FBI AA24-207A PDF was verified as 30 readable pages,
issued July 25, 2024, with matching advisory ID. The collector now tries this
single explicitly allowlisted archive if its canonical CISA article is blocked:
https://www.fbi.gov/file-repository/north-korea-cyber-group-conducts-global-espionage-campaign-to-advance-regimes-military-and-nuclear-programs-072524.pdf

Its original CISA URL remains the dedupe key. A dated archive is never interpreted
as a new revision of the current CISA article: existing content hash and previous
notification timestamp are preserved, and only archive provenance/observation
metadata is added. An unseen 2024 archive creates a baseline, not a new alert.
Primary access errors and incomplete discovery remain explicit partial/error
reports even when the archive succeeds. No archive was verified for AA23-040A;
CISA CSAF was not substituted for the missing North Korea advisory scope.

83 offline regression tests pass, including retry counting, legacy/modern
non-double-counting, pending item and health failures, verified filtered zeros,
warning-vs-total-failure exit semantics, Telegram-size splitting, advisory
ID/date/page validation, canonical URL preservation and old-archive alert
suppression. Live follow-up results are recorded after dispatch below.

### Follow-up live results

- [Monitor 39175567333](https://github.com/coolpint/international/actions/runs/39175567333), code `b3aef3b821c8a1ffc07e329d89b5c0a6fd7967c6`: 83 tests passed; 244 collected, 18 Korea-related observations, zero new/updated item events. CISA recovered the single dated AA24-207A FBI archive, reporting `partial` (1 success, 1 failed known article, discovery still 403). Overall collection remains `partial_failure`. Exactly one legitimate error→partial health-change alert was accepted; no article alert was sent; failures/pending both zero. State commit `7a3470e` contains archive ID/date/retrieval URL. The existing original content hash and notification timestamp remained unchanged, and all original URL keys/hashes were preserved.
- [Weekly 39175808141](https://github.com/coolpint/international/actions/runs/39175808141): 83 tests passed; report sent successfully with `health-status=warning`, Actions warning annotation, and job conclusion `success`. The report retained 95 source-error observations in its 7-day window and the explicit outstanding UN/UNCTAD/CISA normal-access warnings. It counted 15 historical item deliveries and 5 health deliveries, current backlog 0. These are period totals, not 15 newly resent articles. SIPRI showed a healthy recent response and zero unverified-zero streak. Read-only workflow permissions and existing recipients/secrets were retained.

The archive restores **one dated advisory body only**, not CISA discovery, the other known advisory, current web-page revisions, or the complete missing interval. UN/UNCTAD access restrictions and the 46 deferred meetings article URLs remain unresolved. No successful full historical backfill is claimed.
