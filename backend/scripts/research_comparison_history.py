"""Prepare isolated owner-history inputs using production saved-anchor storage.

No completed research turns or answers are fabricated. Evidence clocks belong to
explicitly synthetic source records; admission/session clocks remain real time.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime

from scripts.research_comparison_inputs import check_clock
from services.agent.contracts import request_spec
from services.agent.read_budget import ReadBudget, budget_scope
from services.agent.reads import ResearchReads

_VARIANTS = {'matching_coverage', 'different_coverage_same_horizon',
             'prior_only_other_owner', 'late_evening_not_close', 'three_ticker_compatible_history'}


def _stamp(value):
    try:
        at = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if at.utcoffset() is None:
            raise ValueError
        return at.astimezone(UTC)
    except (TypeError, AttributeError, ValueError) as exc:
        raise ValueError('History input requires an aware source timestamp') from exc


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _coverage(raw):
    return _hash(sorted((str(c.get('expiry')), str(c.get('strike')), str(c.get('type')))
                        for c in raw['contracts']))


def _validate(item):
    spec = request_spec(item['body'])
    if spec['horizon'] != 'all' or spec.get('question_scope') or spec['screen'].get('selectedExpiry'):
        raise ValueError('History fixture supports only its declared all-expiry scope')
    at = _stamp(item['clock']['at'])
    if not item['history'] or set(item['history']) != set(spec['tickers']):
        raise ValueError('History ticker scope differs from request')
    for ticker, recipe in item['history'].items():
        variant = recipe['variant']
        if len(item['history']) != (3 if variant == 'three_ticker_compatible_history' else 1):
            raise ValueError('History variant requires its exact ticker count')
        if variant not in _VARIANTS or type(recipe['same_owner']) is not bool:
            raise ValueError('Unknown history variant or owner relation')
        if recipe['same_owner'] != (variant != 'prior_only_other_owner'):
            raise ValueError('History owner relation differs from declared variant')
        if recipe['prior_anchor_kind'] != ('intraday' if variant == 'late_evening_not_close' else 'observation'):
            raise ValueError('Synthetic history cannot fabricate a closing anchor')
        if recipe.get('store_inserted') is not False:
            raise ValueError('History source must declare uninserted preparation')
        prior, current = recipe['prior_raw'], item['chains'][ticker]
        for raw in (prior, current):
            if raw.get('ticker') != ticker or raw.get('source') != 'SYNTHETIC_CONTRACT_TEST':
                raise ValueError('Synthetic prior ticker/source identity differs')
            if raw.get('spot_source') != 'SYNTHETIC_CONTRACT_TEST' or not raw.get('contracts'):
                raise ValueError('Synthetic history requires source identity and contract coverage')
            if type(raw.get('spot')) not in (int, float) or not 0 < raw['spot'] < float('inf'):
                raise ValueError('Synthetic history price must be positive and finite')
            check_clock(raw, raw['spot_fetched_at'])
            if not _stamp(raw['event_time']) <= _stamp(raw['fetched_at']) <= at:
                raise ValueError('History chain source/receipt/clock order differs')
            if not _stamp(raw['spot_event_time']) <= _stamp(raw['spot_fetched_at']) <= at:
                raise ValueError('History source/receipt/clock order differs')
        if not _stamp(prior['spot_event_time']) < _stamp(current['spot_event_time']):
            raise ValueError('Prior source time is not earlier')
        if current['spot'] - prior['spot'] != recipe['raw_price_difference']:
            raise ValueError('Independent raw price difference differs')
        matching = _coverage(prior) == _coverage(current)
        if matching != (variant != 'different_coverage_same_horizon'):
            raise ValueError('Raw contract coverage differs from declared history variant')
    return spec


async def _snapshot(item, ticker, raw, at):
    spec = request_spec(item['body'])
    screen = spec['screen'] if not spec['context_conflict'] and spec['screen'].get('ticker') == ticker else {}
    def no_alerts(_ticker):
        raise RuntimeError('No recorded alert store supplied for synthetic history preparation')
    reads = ResearchReads(lambda name, _: copy.deepcopy(raw) if name == ticker else None,
                          lambda *_: None, no_alerts)
    budget = ReadBudget()
    try:
        with budget_scope(budget, spec):
            snapshot = await reads.snapshot(ticker, spec['horizon'], screen=screen, now=at)
    finally:
        budget.close()
    price = next((fact for fact in snapshot['facts'] if fact['metric'] == 'Underlying price'), None)
    if (not price or price['value'] != raw['spot'] or price['source'] != raw['spot_source']
            or price['event_time'] != _stamp(raw['spot_event_time']).isoformat()
            or snapshot['coverage'] != len(raw['contracts']) or snapshot['coverage_id'] != _coverage(raw)):
        raise ValueError('Actual prepared snapshot disagrees with independent raw source identity')
    return snapshot, budget.state()


async def current_snapshot(item, ticker):
    """Actual read path for pre-answer history input proof, not an answer."""
    _validate(item)
    snapshot, _ = await _snapshot(item, ticker, item['chains'][ticker], _stamp(item['clock']['at']))
    return snapshot


async def seed_history(repository, owner, item):
    """Validate every source before saving any synthetic prior anchor."""
    _validate(item)
    if (await repository.turns.count_documents({'owner': owner})
            or await repository.snapshots.count_documents({'owner': owner})):
        raise ValueError('History seed requires an empty isolated owner')
    if not await repository.sessions.find_one({'owner': owner, 'expires_at': {'$gt': datetime.now(UTC)}}):
        raise ValueError('History seed requires a real isolated session owner')
    prepared = []
    for ticker, recipe in item['history'].items():
        raw = recipe['prior_raw']
        # This is a declared synthetic capture at its source receipt; never a
        # replacement timestamp for a recorded real observation.
        at = _stamp(raw['spot_fetched_at'])
        snapshot, activity = await _snapshot(item, ticker, raw, at)
        snapshot['anchor_kind'] = recipe['prior_anchor_kind']
        prepared.append((ticker, recipe, snapshot, activity))
    receipts, attempted = [], []
    try:
        for ticker, recipe, snapshot, activity in prepared:
            target = owner
            if not recipe['same_owner']:
                target, _ = await repository.session()
            attempted.append((target, snapshot['snapshot_id']))
            await repository.save_anchor(target, snapshot)
            stored = await repository.snapshots.find_one({'owner': target, 'snapshot.snapshot_id': snapshot['snapshot_id']})
            if not stored or stored.get('snapshot') != snapshot:
                raise ValueError('Saved prior snapshot did not round trip')
            receipts.append({'ticker': ticker, 'variant': recipe['variant'],
                             'owner_relation': 'asking_owner' if recipe['same_owner'] else 'separate_owner',
                             'raw_sha256': _hash(recipe['prior_raw']),
                             'snapshot_sha256': _hash(snapshot), 'snapshot_id': snapshot['snapshot_id'],
                             'coverage_id': snapshot['coverage_id'], 'coverage': snapshot['coverage'],
                             'source_time': _stamp(recipe['prior_raw']['spot_event_time']).isoformat(),
                             'synthetic_capture_time': snapshot['captured_at'], 'anchor_kind': snapshot['anchor_kind'],
                             'storage_round_trip': True, 'preparation_read_activity': activity,
                             'scope': 'Pre-answer synthetic fixture preparation; not a research turn or its budget'})
    except BaseException as exc:
        try:
            for target, identity in attempted:
                # Only anchors attempted by this preparation, under owners
                # verified empty or freshly created here, are eligible.
                await repository.snapshots.delete_many({'owner': target, 'snapshot.snapshot_id': identity})
        except BaseException as cleanup_error:
            raise RuntimeError('History preparation failed and cleanup is unconfirmed; discard the isolated owner') from cleanup_error
        raise RuntimeError('History preparation failed; attempted anchors rolled back') from exc
    return receipts
