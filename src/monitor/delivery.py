"""Durable outbox. No credentials or recipient identifiers are persisted."""
from dataclasses import asdict
import hashlib
import json
import re

from .models import MonitoredItem


def queue_item(state, item, event_type):
    # One pending version per canonical URL; changes supersede unsent older versions.
    state.setdefault('notification_outbox', {})['item:' + item.url] = {
        'kind': 'item', 'item': asdict(item), 'event': event_type,
        'content_hash': state['items'][item.url]['content_hash'],
    }


def collection_status(reports):
    active = [r for r in reports if r.get('enabled')]
    failed = [r for r in active if r['status'] in {'error', 'partial'}]
    if not active or (failed and len(failed) == len(active) and not any(r.get('succeeded', 0) for r in active)):
        return 'total_failure'
    return 'partial_failure' if failed else 'success'


def _failure_signature(report):
    details = [str(report.get('detail') or '')]
    for error in report.get('errors', []):
        details.append(str(error.get('detail', '')) if isinstance(error, dict) else str(error))
    # Article URLs, counts and challenge request IDs change on every poll. They
    # must not create a new incident. HTTP status changes still create an alert.
    codes = sorted(set(re.findall(r'HTTP\s+(\d{3})', ' '.join(details))))
    if codes:
        cause = ['HTTP ' + c for c in codes]
    else:
        normalized = re.sub(r'https?://\S+', '<url>', ' '.join(details))
        normalized = re.sub(r'\b\d+\b', '#', normalized)
        cause = [normalized[:300]]
    return hashlib.sha256(json.dumps([report['status'], cause]).encode()).hexdigest(), cause


def queue_health(state, reports, run_at):
    health = state.setdefault('collection_health', {})
    outbox = state.setdefault('notification_outbox', {})
    overall = collection_status(reports)
    for report in reports:
        if not report.get('enabled'):
            continue
        source_id = report['source_id']
        previous = health.get(source_id, {})
        failed = report['status'] in {'error', 'partial'}
        signature, causes = _failure_signature(report) if failed else ('healthy', [])
        health[source_id] = {**previous, 'observed_signature': signature,
                             'status': report['status'], 'observed_at': run_at}
        key = 'health:' + source_id
        if previous.get('delivered_signature') == signature:
            outbox.pop(key, None)
            continue
        if not failed and not previous:
            health[source_id]['delivered_signature'] = signature
            continue
        if not failed and previous.get('observed_signature') == 'healthy' and key not in outbox:
            continue
        if outbox.get(key, {}).get('signature') == signature:
            continue
        label = report.get('source_label', source_id)
        transition = '최초 장애' if not previous else ('장애 변경' if failed else '복구')
        # A pending incident may never have reached Telegram; current condition
        # supersedes it so a recovery is never followed by a stale failure alert.
        text = (f'international 수집 {transition}: {label}\n'
                f'전체 판정: {overall}; 소스 판정: {report["status"]}\n'
                f'수집 {report.get("collected", 0)}건; 실패 {report.get("failed")}건\n'
                + ('원인: ' + ', '.join(causes) if failed else '공식 수집 경로 정상 응답 확인'))
        outbox[key] = {'kind': 'health', 'source_id': source_id,
                       'signature': signature, 'text': text}


def deliver_outbox(state, run_at, send_item, send_text, checkpoint):
    outbox = state.setdefault('notification_outbox', {})
    delivered = failed = 0
    counts = {"item_delivered": 0, "health_delivered": 0}
    # Persist before the first external side effect. At-least-once delivery:
    # a process loss after Telegram accepts but before save can duplicate a send.
    checkpoint()
    for key, entry in list(outbox.items()):
        try:
            if entry['kind'] == 'item':
                send_item(MonitoredItem(**entry['item']), entry['event'])
            else:
                send_text(entry['text'])
        except Exception as exc:
            entry['attempts'] = entry.get('attempts', 0) + 1
            entry['last_attempt_at'] = run_at
            # Transport exception messages may contain the bot token URL.
            entry['last_error'] = type(exc).__name__
            failed += 1
        else:
            if entry['kind'] == 'item':
                record = state['items'].get(entry['item']['url'], {})
                record['last_notified_at'] = run_at
                record['last_notified_hash'] = entry['content_hash']
            else:
                state['collection_health'][entry['source_id']]['delivered_signature'] = entry['signature']
            del outbox[key]
            delivered += 1
            counts[entry["kind"] + "_delivered"] += 1
        checkpoint()
    return {'delivered': delivered, 'failed': failed, 'pending': len(outbox), **counts}
