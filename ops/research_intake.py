"""Pure saved-data intake and a closed, cited-facts research envelope.

No I/O, model, account, venue or order capability. Historical copied facts are
retrospective only. A locally hashed observation ID is a saved-payload identity,
not proof of a fresh provider event or permission to trade.
"""
import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re

MAX_INPUT_BYTES = 256 * 1024
MAX_PACKET_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_ROWS = 64
MAX_CLAIMS = 64
FRESH_SECONDS = Decimal('60')
COLUMNS = ['underlying_ticker', 'ticker', 'contract_type', 'strike_price',
           'expiration_date', 'day_volume', 'open_interest', 'implied_volatility',
           'delta', 'underlying_price']
CLOCKS = ['received_at', 'event_time', 'volume_source_time', 'quote_source_time',
          'bid_source_time', 'ask_source_time', 'last_source_time', 'oi_source_time']
# The saved endpoint supplies column names, not verified numeric units.
UNITS = {name: 'unspecified_source_units' for name in
         ['strike_price', 'day_volume', 'open_interest', 'implied_volatility',
          'delta', 'underlying_price', 'bid', 'ask', 'last']}
FIELD_CLOCK = {'day_volume': 'volume_source_time', 'open_interest': 'oi_source_time',
               'bid': 'bid_source_time', 'ask': 'ask_source_time', 'last': 'last_source_time',
               'bid_size': 'bid_source_time', 'ask_size': 'ask_source_time'}
COVERAGE_FIELDS = ['universe', 'observed_tickers', 'missing_tickers', 'available_tickers',
                   'stale_tickers', 'partial_tickers', 'stored_tickers', 'rows_per_ticker_cap']
FORBIDDEN = {
    'execution': 'unsupported_execution_claim', 'action': 'unsupported_execution_claim',
    'order': 'unsupported_execution_claim', 'trade': 'unsupported_execution_claim',
    'quantity': 'unsupported_execution_claim', 'account_id': 'unsupported_execution_claim',
    'approval': 'unsupported_execution_claim', 'liquid': 'unsupported_liquid_claim',
    'venue': 'unsupported_venue_claim', 'product': 'unsupported_product_claim',
    'product_kind': 'unsupported_product_claim', 'instrument_type': 'unsupported_product_claim',
    'confidence': 'unsupported_confidence_claim', 'probability': 'unsupported_confidence_claim',
    'win_rate': 'unsupported_confidence_claim', 'profitability': 'unsupported_confidence_claim',
    'fresh': 'unsupported_freshness_claim', 'freshness': 'unsupported_freshness_claim',
    'live': 'unsupported_execution_claim', 'trade_eligible': 'unsupported_execution_claim',
}
LIMITATIONS = ['retrospective_saved_data_only', 'latest_bounded_snapshot_not_complete_history',
               'not_a_trade_tape', 'unknown_clocks_and_sizes_remain_unknown',
               'stale_facts_do_not_become_fresh', 'not_execution_admission']


class IntakeError(ValueError):
    """The exception text is a stable refusal code, never raw input text."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _bounded(value, limit, kind):
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if depth > 20 or nodes > 16000:
            raise IntakeError(kind + '_structure_limit')
        if type(item) is int and item.bit_length() > 256:
            raise IntakeError(kind + '_numeric_limit')
        if isinstance(item, (dict, list)) and len(item) > 4096:
            raise IntakeError(kind + '_structure_limit')
        if isinstance(item, str) and len(item) > limit:
            raise IntakeError(kind + '_byte_limit')
        if type(item) is float and not math.isfinite(item):
            raise IntakeError('nonfinite_' + kind)
        if isinstance(item, dict):
            if any(type(key) is not str for key in item):
                raise IntakeError('invalid_' + kind)
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise IntakeError('invalid_' + kind)
    encoded = _canonical(value)
    if len(encoded.encode('ascii')) > limit:
        raise IntakeError(kind + '_byte_limit')
    return encoded


def _decimal(value):
    if type(value) not in (str, int, float):
        raise IntakeError('invalid_numeric_value')
    if isinstance(value, str) and len(value) > 96:
        raise IntakeError('numeric_range_exceeded')
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise IntakeError('invalid_numeric_value')
    if not number.is_finite():
        raise IntakeError('nonfinite_value')
    if number.is_zero():
        return Decimal(0)
    digits = number.as_tuple()
    if (len(digits.digits) > 32 or not -18 <= digits.exponent <= 24
            or number.copy_abs() >= Decimal('1e24')):
        raise IntakeError('numeric_range_exceeded')
    return number


def _text(number):
    if number == 0:
        return '0'
    text = format(number, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def _instant(value):
    if value is None:
        return None
    if type(value) in (int, float):
        return _decimal(value)
    if isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            raise IntakeError('invalid_timestamp')
    if not isinstance(value, datetime.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise IntakeError('invalid_timestamp')
    epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    try:
        elapsed = value.astimezone(datetime.timezone.utc) - epoch
    except (OverflowError, ValueError):
        raise IntakeError('invalid_timestamp')
    return Decimal(elapsed.days * 86400 + elapsed.seconds) + Decimal(elapsed.microseconds) / Decimal(1000000)


def _clock(value, decision, name):
    try:
        instant = _instant(value)
    except IntakeError:
        raise IntakeError('invalid_' + name)
    if instant is None:
        return {'value': None, 'knowledge': 'unknown', 'freshness': 'unknown', 'age_seconds': None}
    if instant > decision:
        raise IntakeError('future_' + name)
    age = decision - instant
    return {'value': _text(instant), 'knowledge': 'known',
            'freshness': 'stale' if age > FRESH_SECONDS else 'fresh', 'age_seconds': _text(age)}


def _field(value, unit, whole=False, nonnegative=False):
    if value is None:
        return {'value': None, 'unit': unit, 'status': 'missing'}
    number = _decimal(value)
    if whole and number != number.to_integral_value() or nonnegative and number < 0:
        raise IntakeError('invalid_numeric_value')
    return {'value': _text(number), 'unit': unit, 'status': 'zero' if number == 0 else 'measured'}


def _observation(row, saved, decision):
    if not isinstance(row, list) or len(row) != 10:
        raise IntakeError('row_shape_invalid')
    underlying, contract, kind, strike, expiry = row[:5]
    if not isinstance(underlying, str) or not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,11}', underlying):
        raise IntakeError('underlying_invalid')
    if not isinstance(contract, str) or not isinstance(expiry, str):
        raise IntakeError('contract_identity_missing')
    match = re.fullmatch(r'([A-Z][A-Z0-9.-]{0,11})([0-9]{6})([CP])([0-9]{8})', contract)
    if match is None or match.group(1) != underlying or kind not in ('call', 'put'):
        raise IntakeError('contract_identity_mismatch')
    try:
        parsed_expiry = datetime.date.fromisoformat(expiry)
        encoded_expiry = datetime.date(2000 + int(match.group(2)[:2]),
                                       int(match.group(2)[2:4]), int(match.group(2)[4:]))
    except ValueError:
        raise IntakeError('expiry_invalid')
    if parsed_expiry != encoded_expiry:
        raise IntakeError('expiry_mismatch')
    if match.group(3) != ('C' if kind == 'call' else 'P'):
        raise IntakeError('option_type_mismatch')
    if strike is None:
        raise IntakeError('strike_missing')
    strike_number = _decimal(strike)
    if strike_number <= 0 or strike_number != Decimal(match.group(4)) / Decimal(1000):
        raise IntakeError('strike_mismatch')
    key = underlying + '|' + kind + '|' + _text(strike_number) + '|' + expiry
    metadata = saved['row_observations'].get(key)
    extras = saved['quote_truth'].get(key, {})
    ticker = saved['observations_by_ticker'].get(underlying, {})
    if not isinstance(metadata, dict) or not isinstance(extras, dict) or not isinstance(ticker, dict):
        raise IntakeError('row_metadata_missing')
    if metadata.get('source') != 'public_api':
        raise IntakeError('unsupported_provider')
    scope = metadata.get('scope')
    if not isinstance(scope, str) or not 1 <= len(scope) <= 100 or not re.fullmatch(r'[A-Za-z0-9_.:-]+', scope):
        raise IntakeError('scope_unavailable')
    if 'scope' in ticker and ticker['scope'] != scope:
        raise IntakeError('scope_mismatch')
    if 'source' in ticker and ticker['source'] != metadata['source']:
        raise IntakeError('provider_mismatch')
    clocks = {}
    for name in CLOCKS:
        clocks[name] = _clock(metadata.get(name), decision, name)
        if name in extras:
            supplied = _clock(extras[name], decision, name)
            if name in metadata and supplied['value'] != clocks[name]['value']:
                raise IntakeError('clock_conflict')
            if name not in metadata:
                clocks[name] = supplied
    received = clocks['received_at']['value']
    if received is not None and any(clock['value'] is not None and Decimal(clock['value']) > Decimal(received)
                                    for name, clock in clocks.items() if name != 'received_at'):
        raise IntakeError('source_after_receipt')
    if all(clocks[name]['value'] is None for name in ['received_at', 'event_time', 'quote_source_time']):
        raise IntakeError('observation_clock_unavailable')
    fields = {}
    for name, value in zip(COLUMNS[3:], row[3:]):
        if name == 'expiration_date':
            continue
        fields[name] = _field(value, UNITS[name], whole=name in ('day_volume', 'open_interest'),
                              nonnegative=name != 'delta')
    for name in ['bid', 'ask', 'last']:
        fields[name] = _field(extras.get(name), UNITS[name], nonnegative=True)
    size_unit = extras.get('size_unit')
    if size_unit not in (None, 'contracts'):
        raise IntakeError('unsupported_size_unit')
    for name in ['bid_size', 'ask_size']:
        fields[name] = _field(extras.get(name), size_unit or 'unknown', whole=True, nonnegative=True)
    result = {'underlying_ticker': underlying, 'contract_id': contract, 'option_type': kind,
              'expiry': expiry, 'provider': 'public_api', 'scope': scope,
              'currency': None, 'contract_multiplier': None,
              'fields': fields, 'clocks': clocks,
              'data_status': metadata.get('data_status') if metadata.get('data_status') in
                             ('available', 'partial', 'legacy_limited') else 'unknown',
              'live': False, 'trade_eligible': False}
    # Provider polling ages and decision-time ages never mint a source event.
    stable = {**result, 'clocks': {name: clock['value'] for name, clock in clocks.items()}}
    digest = hashlib.sha256(_canonical(stable).encode('ascii')).hexdigest()
    result['observation_id'] = 'obs_' + digest
    event = [contract, 'public_api', scope, stable['clocks']]
    event_id = hashlib.sha256(_canonical(event).encode('ascii')).hexdigest()
    return result, event_id


def _packet_digest(packet):
    core = {key: value for key, value in packet.items() if key != 'packet_id'}
    return 'research_' + hashlib.sha256(_canonical(core).encode('ascii')).hexdigest()


def compile_snapshot(saved_input, decision_time):
    """Compile one finite saved page; bad rows are excluded with stable reasons.

    Unknown source times stay None. checked_at and precomputed polling ages
    are ignored. decision_time must be explicit and aware/epoch-based; it is
    never substituted for a missing source or receipt clock. Quote currency,
    price units and contract multiplier are unspecified when the saved endpoint
    does not supply them; no USD or standard-contract multiplier is inferred.
    """
    _bounded(saved_input, MAX_INPUT_BYTES, 'input')
    decision = _instant(decision_time)
    if decision is None:
        raise IntakeError('decision_time_required')
    if not isinstance(saved_input, dict) or saved_input.get('source') != 'public-scan-observations':
        raise IntakeError('unsupported_source')
    if saved_input.get('live') is not False or saved_input.get('trade_eligible') is not False:
        raise IntakeError('saved_research_only')
    if saved_input.get('columns') != COLUMNS:
        raise IntakeError('unsupported_columns')
    rows = saved_input.get('rows')
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise IntakeError('row_limit_exceeded')
    if saved_input.get('count') != len(rows) or type(saved_input.get('count')) is not int:
        raise IntakeError('row_count_mismatch')
    saved = dict(saved_input)
    for name in ['row_observations', 'quote_truth', 'observations_by_ticker']:
        if not isinstance(saved.get(name), dict):
            raise IntakeError('row_metadata_missing')
    candidates = {}
    excluded = []
    for row in rows:
        contract = row[1] if isinstance(row, list) and len(row) > 1 and isinstance(row[1], str) and re.fullmatch(r'[A-Z0-9.-]{1,32}', row[1]) else None
        try:
            observation, event = _observation(row, saved, decision)
            candidates.setdefault(event, []).append(observation)
        except IntakeError as exc:
            excluded.append({'contract_id': contract, 'reason': str(exc)})
    observations = []
    for group in candidates.values():
        different = len({item['observation_id'] for item in group}) > 1
        if different:
            excluded.extend({'contract_id': item['contract_id'], 'reason': 'conflicting_observation'} for item in group)
        else:
            observations.append(group[0])
            excluded.extend({'contract_id': item['contract_id'], 'reason': 'duplicate_observation'} for item in group[1:])
    coverage_input = saved.get('coverage') or {}
    if not isinstance(coverage_input, dict):
        raise IntakeError('invalid_coverage')
    coverage = {}
    for key in COVERAGE_FIELDS:
        value = coverage_input.get(key)
        if value is not None and (type(value) is not int or not 0 <= value <= 10 ** 9):
            raise IntakeError('invalid_coverage')
        coverage[key] = value
    page = {}
    for key in ['total', 'offset', 'limit', 'next_offset']:
        value = saved.get(key)
        if value is not None and (type(value) is not int or not 0 <= value <= 10 ** 9):
            raise IntakeError('invalid_page')
        page[key] = value
    page['supplied_rows'] = len(rows)
    packet = {'schema': 'floww-saved-research.v1', 'status': 'review_only', 'executable': False,
              'scope': 'internal_research', 'source': 'public-scan-observations',
              'decision_time': _text(decision), 'id_basis': 'canonical_saved_payload',
              'observations': sorted(observations, key=lambda item: item['contract_id']),
              'excluded': sorted(excluded, key=_canonical), 'coverage': coverage, 'page': page,
              'complete_history': False, 'complete_realtime_market': False,
              'live': False, 'trade_eligible': False, 'limitations': list(LIMITATIONS)}
    packet['packet_id'] = _packet_digest(packet)
    _bounded(packet, MAX_PACKET_BYTES, 'packet')
    return packet


def _refuse(reason):
    return {'accepted': False, 'reason': reason, 'status': 'review_only',
            'executable': False, 'scope': 'internal_research'}


def _forbidden_claim(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN:
                return FORBIDDEN[key.lower()]
            if key == 'field' and isinstance(child, str) and child.lower() in FORBIDDEN:
                return FORBIDDEN[child.lower()]
            found = _forbidden_claim(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _forbidden_claim(child)
            if found:
                return found
    return None


def _fact(observation, field):
    if field in observation['fields']:
        value = observation['fields'][field]
        clock = observation['clocks'].get(FIELD_CLOCK.get(field), {})
        return value['value'], value['unit'], True, clock
    if field in observation['clocks']:
        clock = observation['clocks'][field]
        return clock['value'], 'UTC_epoch_seconds', True, clock
    if field in ('expiry', 'provider', 'scope', 'contract_id', 'underlying_ticker', 'option_type',
                  'currency', 'contract_multiplier'):
        return observation[field], 'calendar_date' if field == 'expiry' else 'identifier', False, {}
    raise IntakeError('unknown_field')


def validate_research(packet, response):
    """Accept only exact supplied fields, units and citations; no free prose.

    Required response keys: packet_id/status/executable/scope/claims. Each
    claim has observation_id/field/value/unit/citations, and each citation
    has exactly observation_id/field. Acceptance is not execution admission.
    """
    try:
        _bounded(packet, MAX_PACKET_BYTES, 'packet')
        _bounded(response, MAX_RESPONSE_BYTES, 'response')
        if not isinstance(packet, dict) or packet.get('packet_id') != _packet_digest(packet):
            return _refuse('packet_digest_mismatch')
        if not isinstance(response, dict):
            return _refuse('unsupported_response_fields')
        forbidden = _forbidden_claim(response)
        if forbidden:
            return _refuse(forbidden)
        if response.get('executable') is not False or response.get('status') != 'review_only' or response.get('scope') != 'internal_research':
            return _refuse('unsupported_execution_claim')
        if set(response) != {'packet_id', 'status', 'executable', 'scope', 'claims'}:
            return _refuse('unsupported_response_fields')
        if response['packet_id'] != packet['packet_id']:
            return _refuse('packet_id_mismatch')
        claims = response['claims']
        if not isinstance(claims, list) or not 1 <= len(claims) <= MAX_CLAIMS:
            return _refuse('claims_required_or_limit_exceeded')
        observations = {item['observation_id']: item for item in packet['observations']}
        accepted, seen = [], set()
        for claim in claims:
            if not isinstance(claim, dict) or set(claim) != {'observation_id', 'field', 'value', 'unit', 'citations'}:
                return _refuse('claim_fields_required')
            identity, field = claim['observation_id'], claim['field']
            if not isinstance(identity, str) or identity not in observations:
                return _refuse('unknown_observation_id')
            if not isinstance(field, str):
                return _refuse('unknown_field')
            if (identity, field) in seen:
                return _refuse('duplicate_claim')
            seen.add((identity, field))
            citations = claim['citations']
            if not isinstance(citations, list) or not 1 <= len(citations) <= 4:
                return _refuse('citations_required')
            for citation in citations:
                if not isinstance(citation, dict) or set(citation) != {'observation_id', 'field'}:
                    return _refuse('citation_fields_required')
                if not isinstance(citation['observation_id'], str) or citation['observation_id'] not in observations:
                    return _refuse('unknown_observation_id')
                if citation != {'observation_id': identity, 'field': field}:
                    return _refuse('citation_mismatch')
            observation = observations[identity]
            value, unit, numeric, clock = _fact(observation, field)
            if claim['unit'] != unit:
                return _refuse('unit_mismatch')
            supplied = claim['value']
            if numeric and supplied is not None:
                supplied = _text(_decimal(supplied))
            if value is None or not numeric:
                if supplied != value or type(supplied) is not type(value):
                    return _refuse('value_mismatch')
            elif supplied != value:
                return _refuse('numeric_mismatch')
            accepted.append({'observation_id': identity, 'field': field, 'value': value,
                             'unit': unit, 'citations': [{'observation_id': identity, 'field': field}],
                             'freshness': clock.get('freshness', 'unknown'),
                             'source_time': clock.get('value'),
                             'received_at': observation['clocks']['received_at']['value']})
        return {'accepted': True, 'reason': 'accepted_copied_facts', 'status': 'review_only',
                'executable': False, 'scope': 'internal_research', 'packet_id': packet['packet_id'],
                'claims': accepted, 'limitations': list(LIMITATIONS)}
    except IntakeError as exc:
        return _refuse('nonfinite_response' if str(exc) == 'nonfinite_value' else str(exc))
    except (KeyError, TypeError, ValueError, RecursionError):
        return _refuse('invalid_envelope')
