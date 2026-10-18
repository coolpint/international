# Collection and delivery repair (2026-10-19)

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
