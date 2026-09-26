"""Prepare immutable raw comparison inputs. Never runs research, models or providers.

This is preparation, not an execution seal or truth/usefulness acceptance. Every
functional case remains present, including missing real inputs. Store recipes
remain unexecuted until the later isolated runner supplies actual query proof.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROPOSAL = ROOT / '.planning/eval/research-fresh-comparison-proposal-20260926.json'
STAMP = '2026-09-28T14:29:50Z'
RECEIPT = '2026-09-28T14:29:51Z'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def checked_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Source path outside project')
    return path


def verify_sources(root, references):
    sources = {}
    for ref in references:
        if ref['id'] in sources:
            raise ValueError('Duplicate source identity')
        data = checked_path(root, ref['path']).read_bytes()
        if digest(data) != ref['sha256']:
            raise ValueError('Referenced source changed: ' + ref['id'])
        sources[ref['id']] = json.loads(data) if ref['path'].endswith('.json') else None
    return sources


def archive_inputs(tickers, sources):
    chains = {}
    for ticker in tickers:
        try:
            envelope = (sources['archive_aapl'] if ticker == 'AAPL'
                        else sources['archive_chains']['sources'][ticker])
            raw = envelope['source']['raw_public_chain']
        except KeyError as exc:
            raise ValueError('Missing archived ticker input') from exc
        if raw.get('ticker') != ticker:
            raise ValueError('Archived ticker identity differs')
        chains[ticker] = copy.deepcopy(raw)
    return chains


def synthetic_chain(ticker, params):
    allowed = {'variant', 'spot', 'put_iv', 'call_oi', 'put_oi', 'source',
               'event_time', 'spot_event_time', 'fetched_at', 'spot_fetched_at'}
    variants = {None, 'put_iv_missing', 'zero_vs_null_oi', 'untrusted_source_label'}
    if set(params) - allowed or params.get('variant') not in variants:
        raise ValueError('Unsupported synthetic chain variant or field')
    raw = {'ticker': ticker, 'spot': params.get('spot', 100),
           'source': params.get('source', 'SYNTHETIC_CONTRACT_TEST'),
           'data_source': 'SYNTHETIC_CONTRACT_TEST', 'spot_source': 'SYNTHETIC_CONTRACT_TEST',
           'event_time': params.get('event_time', STAMP),
           'spot_event_time': params.get('spot_event_time', STAMP),
           'fetched_at': params.get('fetched_at', RECEIPT),
           'spot_fetched_at': params.get('spot_fetched_at', RECEIPT),
           'stale': False, 'cache_age_s': 0, 'expiries': ['2026-10-02'], 'contracts': []}
    for kind, iv, gamma, oi, delta in (
        ('call', .20, .010, params.get('call_oi', 100), .55),
        ('put', params.get('put_iv', .24), .012, params.get('put_oi', 80), -.45),
    ):
        raw['contracts'].append({'type': kind, 'strike': 100, 'expiry': '2026-10-02',
                                 'expiry_instant': '2026-10-02T20:00:00Z',
                                 'iv': iv, 'iv_event_time': raw['event_time'],
                                 'gamma': gamma, 'oi': oi, 'delta': delta})
    return raw


def chain_oracle(raw):
    """Independent raw-field inventory, not production-computed answer truth."""
    contracts = raw.get('contracts') or []
    oi = [c.get('open_interest', c.get('oi')) for c in contracts]
    return {'spot': raw.get('spot'), 'spot_unit': 'USD',
            'spot_source': raw.get('spot_source'), 'spot_event_time': raw.get('spot_event_time'),
            'chain_event_time': raw.get('event_time'), 'captured_contracts': len(contracts),
            'captured_expiries': sorted({str(c['expiry']) for c in contracts}),
            'zero_open_interest': sum(type(v) in (int, float) and v == 0 for v in oi),
            'missing_open_interest': sum(v is None for v in oi),
            'explicit_expiry_instants': sum(bool(c.get('expiry_instant')) for c in contracts),
            'scope': 'Raw captured input inventory before requested expiry slicing; not model answer facts'}


def map_inputs(case, sources, recipe):
    ticker = case['tickers'][0]
    screen = copy.deepcopy(case['body']['screen'])
    if recipe['id'] == 'archive_map':
        raw = copy.deepcopy(sources['archive_maps']['maps'][ticker]['body'])
        strikes = raw['grid']['strikes']
        expiries = raw['grid']['expiries']
        screen.update(mapQuery=copy.deepcopy(raw['map_query']), mapVersion=raw['asof'],
                      mapStrikes=copy.deepcopy(strikes), mapExpiries=copy.deepcopy(expiries),
                      selectedStrike=strikes[len(strikes) // 2], selectedExpiry=expiries[0])
    elif recipe['id'] == 'explicit_synthetic_map':
        raw = copy.deepcopy(recipe['parameters']['raw'])
        if raw.get('source') != 'SYNTHETIC_CONTRACT_TEST':
            raise ValueError('Explicit test map must be labeled synthetic')
        if raw.get('map_query') != screen['mapQuery'] or raw.get('asof') != screen['mapVersion']:
            raise ValueError('Explicit test map identity differs')
        grid = raw.get('grid', {})
        if (grid.get('strikes') != screen['mapStrikes'] or grid.get('expiries') != screen['mapExpiries']
                or screen.get('selectedStrike') not in grid.get('strikes', [])
                or screen.get('selectedExpiry') not in grid.get('expiries', [])):
            raise ValueError('Explicit test map axes or selection differ')
    else:
        raw = {'ticker': ticker, 'source': 'SYNTHETIC_CONTRACT_TEST', 'spot': 100,
               'spot_source': 'SYNTHETIC_CONTRACT_TEST', 'spot_event_time': STAMP,
               'spot_fetched_at': RECEIPT, 'map_query': copy.deepcopy(screen['mapQuery']),
               'asof': STAMP, 'event_time': STAMP, 'fetched_at': RECEIPT,
               'stale': False, 'stale_age_s': 0,
               'grid': {'strikes': copy.deepcopy(screen['mapStrikes']),
                        'expiries': copy.deepcopy(screen['mapExpiries']),
                        'grid': copy.deepcopy(recipe['parameters']['grid'])}}
    if raw.get('ticker') != ticker:
        raise ValueError('Map ticker differs')
    key = {'gex': 'grid', 'vex': 'vex_grid', 'charm': 'charm_grid'}[screen['metric']]
    matrix = raw['grid'][key]
    strikes = screen['mapStrikes']
    expiries = screen['mapExpiries']
    rows = [[matrix.get(e, {}).get(format(s, 'g')) for e in expiries] for s in strikes]
    net = [None if any(v is None for v in row) else sum(row) for row in rows]
    cumulative, total = [], 0
    for value in net:
        total = None if total is None or value is None else total + value
        cumulative.append(total)
    selected = matrix.get(screen['selectedExpiry'], {}).get(format(screen['selectedStrike'], 'g'))
    oracle = {'selected_value': selected, 'net': net, 'cumulative': cumulative,
              'unit': 'display gamma units' if screen['metric'] == 'gex' else 'display ' + screen['metric'] + ' units',
              'event_time': raw.get('event_time'),
              'scope': 'Independent arithmetic over the declared visible cells, not freshness acceptance'}
    return {ticker: raw}, screen, oracle


def history_inputs(chains, params):
    variant = params['variant']
    if variant not in {'matching_coverage', 'different_coverage_same_horizon', 'prior_only_other_owner',
                       'late_evening_not_close', 'three_ticker_compatible_history'}:
        raise ValueError('Unsupported history recipe')
    histories = {}
    for ticker, current in chains.items():
        current['spot'] = params.get('current_price', 102)
        prior = copy.deepcopy(current)
        prior['spot'] = params.get('prior_price', 100)
        stamp = params.get('prior_source_time', '2026-09-28T14:25:00Z')
        for field in ('event_time', 'spot_event_time'):
            prior[field] = stamp
        receipt = (datetime.fromisoformat(stamp.replace('Z', '+00:00')) + timedelta(seconds=1)).isoformat().replace('+00:00', 'Z')
        for field in ('fetched_at', 'spot_fetched_at'):
            prior[field] = receipt
        for contract in prior['contracts']:
            contract['iv_event_time'] = stamp
        if variant == 'different_coverage_same_horizon':
            extra = copy.deepcopy(prior['contracts'])
            for contract in extra:
                contract['expiry'] = '2026-10-09'
                contract['expiry_instant'] = '2026-10-09T20:00:00Z'
            prior['contracts'].extend(extra)
            prior['expiries'] = sorted({c['expiry'] for c in prior['contracts']})
        histories[ticker] = {'prior_raw': prior, 'same_owner': variant != 'prior_only_other_owner',
                              'variant': variant, 'store_inserted': False,
                              'event_order': [('other owner' if variant == 'prior_only_other_owner' else 'owned') + ' prior snapshot seed', 'current request admission'],
                              'prior_anchor_kind': params.get('prior_anchor_kind', 'observation'),
                              'raw_price_difference': current['spot'] - prior['spot'],
                              'comparison_eligibility': 'unverified until actual owned history path runs'}
    return histories


def check_clock(value, clock):
    """Observation/receipt times may not postdate the declared evidence clock."""
    at = datetime.fromisoformat(clock.replace('Z', '+00:00'))
    if at.utcoffset() is None:
        raise ValueError('Evaluation clock must have timezone')
    fields = {'event_time', 'observed_at', 'fetched_at', 'spot_event_time', 'spot_fetched_at',
              'iv_event_time', 'last_event_time', 'bid_event_time', 'ask_event_time', 'asof'}
    def walk(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if key in fields and child is not None:
                    dt = datetime.fromisoformat(child.replace('Z', '+00:00'))
                    if dt.utcoffset() is None or dt > at:
                        raise ValueError('Input time exceeds clock or lacks timezone')
                elif isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)


def prepare_case(case, sources):
    result = {'id': case['id'], 'body': copy.deepcopy(case['body']), 'clock': copy.deepcopy(case['clock']),
              'chains': {}, 'maps': {}, 'history': {}, 'alerts': {'mode': 'unbound'},
              'oracles': {}, 'pending': ['Actual route, source-quality and request-scope checks',
                                       'Independent semantic truth/criteria review', 'Execution seal']}
    for recipe in case['recipes']:
        name, params = recipe['id'], recipe['parameters']
        if name == 'archive_raw':
            result['chains'] = archive_inputs(case['tickers'], sources)
        elif name == 'synthetic_chain':
            result['chains'] = {ticker: synthetic_chain(ticker, params) for ticker in case['tickers']}
        elif name == 'explicit_synthetic_chain':
            raw = copy.deepcopy(params['raw'])
            if raw.get('source') != 'SYNTHETIC_CONTRACT_TEST' or case['tickers'] != [raw.get('ticker')]:
                raise ValueError('Explicit test chain must have matching ticker and synthetic label')
            result['chains'] = {raw['ticker']: raw}
        elif name in {'archive_map', 'synthetic_map', 'explicit_synthetic_map'}:
            result['maps'], result['body']['screen'], result['oracles']['map'] = map_inputs(case, sources, recipe)
        elif name == 'synthetic_owned_history':
            result['history'] = history_inputs(result['chains'], params)
            result['pending'].append('Actual isolated owner seed and history-read evidence')
        elif name in {'controlled_empty_alerts', 'controlled_alert_error', 'derived_alerts_unknown',
                      'synthetic_alerts_positive'}:
            result['alerts'] = {'mode': name, 'parameters': copy.deepcopy(params), 'query_proof': None}
            result['pending'].append('Actual isolated alert write/query proof: ' + name)
        elif name == 'fresh_real_capture':
            result['pending'].append('Missing proposed real-positive input; retain case in denominator')
        elif name != 'request_body_only':
            raise ValueError('Unsupported recipe: ' + name)
    if result['alerts']['mode'] == 'unbound' and result['chains']:
        result['pending'].append('Explicit isolated alert-read behavior binding')
    if 'independent_raw_oracle' in case:
        result['oracles']['reviewed_raw_criteria'] = copy.deepcopy(case['independent_raw_oracle'])
    result['oracles']['chains'] = {ticker: chain_oracle(raw) for ticker, raw in result['chains'].items()}
    if case['clock'].get('at'):
        check_clock({'chains': result['chains'], 'maps': result['maps'], 'history': result['history']}, case['clock']['at'])
    return result


def build_bundle(root, proposal_path, output):
    if output.exists():
        raise FileExistsError('Existing input bundle must not be overwritten')
    proposal_bytes = proposal_path.read_bytes()
    proposal = json.loads(proposal_bytes)
    cases = proposal['cases']
    if (len(cases) != 32 or len({c['id'] for c in cases}) != 32
            or any(not re.fullmatch('[a-z][a-z0-9_]{0,79}', c['id']) for c in cases)):
        raise ValueError('All32 unique functional cases are required')
    reserved = {'manifest', 'con', 'nul', 'aux', 'prn'} | {f'{prefix}{i}' for prefix in ('com', 'lpt') for i in range(1, 10)}
    if any(case['id'] in reserved for case in cases):
        raise ValueError('Case identity is reserved')
    sources = verify_sources(root, proposal['source_catalog'])
    prepared = [prepare_case(case, sources) for case in cases]
    verify_sources(root, proposal['source_catalog'])
    if proposal_path.read_bytes() != proposal_bytes:
        raise ValueError('Proposal changed during preparation')
    report = {'status': 'RAW_INPUT_PREPARATION_ONLY', 'execution_ready': False,
              'proposal_sha256': digest(proposal_bytes), 'preparer_sha256': digest(Path(__file__).read_bytes()),
              'model_calls': 0, 'provider_calls': 0, 'store_queries': 0,
              'critical_checks_executed': 0, 'cases': [],
              'limits': 'No research answers, actual query evidence, route proofs, execution seal or acceptance. Source hashes are original-byte identities.'}
    files = {}
    for case, item in zip(cases, prepared, strict=True):
        data = json_bytes(item)
        name = case['id'] + '.json'
        files[name] = data
        report['cases'].append({'id': case['id'], 'fixture': {'path': name, 'sha256': digest(data)},
                                'raw_inputs_present': bool(item['chains'] or item['maps']) or
                                any(r['id'] == 'request_body_only' for r in case['recipes']),
                                'history_store_proof': None, 'route_proof': None, 'pending': item['pending']})
    manifest = json_bytes(report)
    # Validate/serialize every case before creating output. Interrupted disk IO
    # may leave a manifest-less directory; never reuse or mistake it for ready.
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        with (output / name).open('xb') as target:
            target.write(data)
    with (output / 'manifest.json').open('xb') as target:
        target.write(manifest)
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proposal', type=Path, default=DEFAULT_PROPOSAL)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = build_bundle(ROOT, args.proposal, args.output)
    print(json.dumps({'status': report['status'], 'cases': len(report['cases']),
                      'raw_inputs_present': sum(c['raw_inputs_present'] for c in report['cases']),
                      'model_calls': 0, 'execution_ready': False}))
