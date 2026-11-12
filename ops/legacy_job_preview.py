#!/usr/bin/env python3
"""Bounded local legacy-job previews. No connector, model, files or delivery.

These contracts do not modify or restore the original Hermes jobs. A caller
snapshot is unverified data, never authenticated evidence or permission to act.
The CLI accepts only built-in synthetic fixtures, not host paths or commands.
"""
import argparse
import json
import math
import re
import time

SCHEMA = 'floww-legacy-job-preview.v1'
JOBS = {
    'deal-scraper': {'sources': ('public_listing',), 'max_age': 3600,
                     'projects': ('deals',), 'effect': 'local_deal_candidates_only'},
    'dashboard-updates': {'sources': ('linear', 'slack', 'project_notes'), 'max_age': 86400,
                          'projects': ('floww', 'public-trader', 'tidehunter', 'gbrain'),
                          'effect': 'proposed_tracker_changes_only'},
    'morning-briefing': {'sources': ('linear', 'slack', 'gmail', 'project_notes'), 'max_age': 259200,
                         'projects': ('floww', 'public-trader', 'tidehunter', 'gbrain'),
                         'effect': 'local_personal_briefing_only'},
}
CAPABILITIES = dict.fromkeys(('network', 'models', 'filesystem', 'delivery', 'tracker_mutation',
                             'note_mutation', 'account_actions', 'dispatch', 'schedule_changes'), False)
ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
MAX_BYTES = 16384


class PreviewError(ValueError):
    """Closed, non-sensitive refusal code."""


def _require(condition, code):
    if not condition:
        raise PreviewError(code)


def _keys(value, names):
    _require(type(value) is dict and set(value) == set(names), 'invalid_fields')


def _clock(value):
    _require(type(value) in (int, float) and math.isfinite(value) and 0 < value < 253402300799,
             'invalid_clock')
    return value


def preview(packet, *, now):
    """Return at most five cited proposals from a bounded, unverified snapshot.

    Conflict IDs never select a winning source. Missing, unavailable, stale or
    future source observations remain gaps. No output grants restoration,
    publication, source access or inference authority.
    """
    _clock(now)
    try:
        encoded = json.dumps(packet, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, RecursionError):
        raise PreviewError('invalid_packet') from None
    _require(len(encoded) <= MAX_BYTES, 'packet_too_large')
    _keys(packet, ('schema', 'job', 'sources'))
    _require(packet['schema'] == SCHEMA and type(packet['job']) is str and packet['job'] in JOBS,
             'unapproved_job')
    rule = JOBS[packet['job']]
    sources = packet['sources']
    _require(type(sources) is list and len(sources) <= len(rule['sources']), 'invalid_sources')
    seen, gaps, items, identities = set(), [], [], {}
    for source in sources:
        _keys(source, ('kind', 'status', 'observed_at', 'records'))
        kind = source['kind']
        _require(type(kind) is str and kind in rule['sources'] and kind not in seen, 'unapproved_source')
        seen.add(kind)
        _require(source['status'] in ('ok', 'unavailable'), 'invalid_source_status')
        age = now - _clock(source['observed_at'])
        records = source['records']
        _require(type(records) is list and len(records) <= 12, 'record_limit')
        _require(source['status'] != 'unavailable' or not records, 'unavailable_source_has_records')
        local_ids = set()
        validated = []
        for record in records:
            _keys(record, ('id', 'title', 'project', 'priority'))
            identity, title = record['id'], record['title']
            _require(type(identity) is str and ID.fullmatch(identity) and identity not in local_ids,
                     'invalid_record_id')
            local_ids.add(identity)
            _require(type(title) is str and 0 < len(title) <= 240
                     and all(ord(ch) >= 32 and ord(ch) != 127 for ch in title), 'invalid_record_text')
            _require(type(record['project']) is str and record['project'] in rule['projects'],
                     'unapproved_project')
            _require(type(record['priority']) is int and 1 <= record['priority'] <= 4, 'invalid_priority')
            validated.append({'id': identity, 'title': title, 'project': record['project'],
                              'priority': record['priority'], 'source': kind,
                              'reference': kind + ':' + identity, 'disposition': 'proposal_only'})
        reason = ('unavailable' if source['status'] != 'ok' else
                  'future' if age < 0 else 'stale' if age > rule['max_age'] else None)
        if reason:
            gaps.append(kind + ':' + reason)
            continue
        for item in validated:
            identities.setdefault(item['id'], []).append((item['title'], item['project'], item['priority']))
        items.extend(validated)
    gaps.extend(kind + ':missing' for kind in rule['sources'] if kind not in seen)
    conflicts = sorted(identity for identity, versions in identities.items() if len(set(versions)) > 1)
    items.sort(key=lambda item: (item['priority'], item['project'], item['id'], item['source']))
    return {'schema': SCHEMA, 'job': packet['job'], 'scope': 'caller_snapshot_preview_unverified',
            'authentication': 'not_verified', 'effect': rule['effect'], 'delivery': 'none',
            'capabilities': dict(CAPABILITIES), 'restoration_ready': False,
            'complete': not gaps, 'completeness_scope': 'provided_snapshot_sources_only',
            'gaps': sorted(gaps), 'conflicts': conflicts, 'items': items[:5],
            'overflow_count': max(0, len(items) - 5)}


def fixture(job, *, now):
    """Synthetic no-delivery inputs; no host or account context is inspected."""
    _clock(now)
    _require(type(job) is str and job in JOBS, 'unapproved_job')
    project = JOBS[job]['projects'][0]
    return {'schema': SCHEMA, 'job': job, 'sources': [
        {'kind': kind, 'status': 'ok', 'observed_at': now, 'records': [
            {'id': 'fixture-' + kind, 'title': 'Synthetic source item', 'project': project, 'priority': 2}]}
        for kind in JOBS[job]['sources']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True, choices=tuple(JOBS))
    args = parser.parse_args()
    now = time.time()
    print(json.dumps(preview(fixture(args.fixture, now=now), now=now), sort_keys=True))


if __name__ == '__main__':
    main()
