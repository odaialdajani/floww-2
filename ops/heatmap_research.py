"""One closed, hash-pinned retained-heatmap trial; never trading admission.

The source is the reviewed November 7 packet, not caller facts or a refresh URL.
Native transport, profiles, admission lease, prepaid budget and failure circuit
belong to research_worker. This task cannot resume them or install a schedule.
"""
import hashlib
import json
import os
import stat
import time
from pathlib import Path

TASK_ID = 'retained-heatmap-v1'
SOURCE_FILE = Path(__file__).with_name('fixtures') / 'heatmap-retained-20261107.json'
SOURCE_SHA256 = '3e22636a60f77bd5987fb83921778a7463b8cbb418a6e3e442854bc612f3e3a5'
SOURCE_LIMIT = 32 * 1024
RESPONSE_LIMIT = 16 * 1024
POLICY = 'retained-heatmap-v1;frozen-source;investigator-then-auditor;root-review;no-action;no-retry'
LIMITATIONS = ['stale_saturday', 'greek_clock_unknown', 'oi_effective_unknown', 'qqq_gap_nov6_nov7',
               'partial_vex_model', 'window_unavailable', 'no_trade_side', 'no_instrument_mapping',
               'no_current_actionability']
REQUIRED_EVIDENCE = ['verified_next_session', 'new_source_event_clocks', 'same_contract_population',
                     'observed_price_sequence', 'bound_comparison_window', 'proven_oi_and_greek_clocks']
QUESTION_SPECS = {
    'cluster_retest': {'wall_id': 'w_6961d4e00f17',
        'fact_ids': ['cluster.raw', 'cluster.delta', 'cluster.turnover'],
        'question': 'Does the retained cluster persist in a fresh comparable next-session observation, and what does the price sequence show at its edges?',
        'rationale': 'Retained spot lies within the named cluster; fresh comparable evidence is required.'},
    'weighting_divergence': {'wall_id': 'w_5ac6d95aa9dd',
        'fact_ids': ['divergence.raw', 'divergence.delta', 'divergence.turnover'],
        'question': 'Does the raw versus turnover weighting disagreement persist after reconciling source clocks and the contract population?',
        'rationale': 'The recorded weightings disagree; turnover does not establish trade side.'},
}
AUDIT_REASONS = ['unsupported_narrative', 'unsupported_direction', 'stale_as_live', 'scope_mismatch',
                 'numeric_mismatch', 'missing_fresh_evidence', 'instrument_substitution']
SYSTEM = ('You are a bounded retained-heatmap research investigator or independent auditor. '
          'Use only supplied source facts and exact citations. You have no tools, personal history or account authority. '
          'Return only closed JSON. Keep all limitations and fresh-evidence requirements. '
          'Research questions are conditional and require root review. Never propose direction, entry, stop, size, '
          'orders, confidence or profit, and never upgrade actionability.')
META_FIELDS = ('success', 'native_failed', 'http_request_count', 'blocked_http_attempt_count',
               'native_valid_tool_names', 'cost_status', 'usage', 'preflight', 'exception_type', 'refusal_code',
               'wire_refusals', 'offline_replay', 'elapsed_seconds', 'transport_error_type', 'http_status',
               'finish_reason', 'response_usage', 'blocked_origins', 'request_body_bytes', 'message_characters',
               'response_bytes', 'response_chunks', 'sse_events', 'stream_done', 'stream_refusal',
               'first_response_byte_seconds', 'last_response_byte_seconds')


class HeatmapError(ValueError):
    """Stable nonsecret refusal code."""


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise HeatmapError('invalid_json_value') from exc


def parse_response(text):
    if not isinstance(text, str) or len(text.encode()) > RESPONSE_LIMIT:
        raise HeatmapError('response_byte_limit')

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise HeatmapError('duplicate_json_key')
            value[key] = item
        return value

    try:
        return json.loads(text, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(HeatmapError('nonfinite_json')))
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise HeatmapError('response_json_refused') from exc


def _source():
    # A fixed file and compiled hash are the trust anchor. Callers supply neither.
    if any(path.is_symlink() for path in [SOURCE_FILE, *SOURCE_FILE.parents]):
        raise HeatmapError('unsafe_source_file')
    try:
        fd = os.open(SOURCE_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise HeatmapError('unsafe_source_file')
            body = handle.read(SOURCE_LIMIT + 1)
    except OSError as exc:
        raise HeatmapError('source_unavailable') from exc
    if len(body) > SOURCE_LIMIT or hashlib.sha256(body).hexdigest() != SOURCE_SHA256:
        raise HeatmapError('source_digest_mismatch')
    # The exact digest fixes all JSON values, including absent clocks and gaps.
    return json.loads(body)


def _base_packet():
    source = _source()
    spy = source['spy']
    scope = {'snapshot_id': spy['snapshot_id'], 'query_key': spy['query_key'], 'mode': 'retained',
             'timeframe': spy['map_query']['mode'], 'expiries': spy['expiries'], 'provider': spy['provider'],
             'formula': spy['formula_version'], 'snapshot_basis': spy['snapshot_basis'],
             'raw_cell_basis': spy['raw_cell_basis']}
    facts = []
    for label, index in (('cluster', 0), ('divergence', 1)):
        wall = spy['walls'][index]
        for suffix, key in (('raw', 'net'), ('delta', 'delta_oi_net'), ('turnover', 'session_delta_volume_net')):
            facts.append({'id': label + '.' + suffix, 'value': str(wall[key]), 'unit': 'USD/1% spot move',
                          'citation': '/spy/walls/' + str(index) + '/' + key})
    packet = {'task_id': TASK_ID, 'source_sha256': SOURCE_SHA256, 'scope': scope, 'facts': facts,
              'clocks': {'observer_at': source['observer_at'], 'capture': spy['asof'], 'received': spy['received_at'],
                         'spot': spy['spot'], 'spot_event': spy['spot_event_time'],
                         'bid_event_range': [spy['source_clock_profile']['bid_ts'][name] for name in ('min', 'max')],
                         'ask_event_range': [spy['source_clock_profile']['ask_ts'][name] for name in ('min', 'max')],
                         'greek_event': None, 'oi_effective': None},
              'objects': [{'wall_id': wall['wall_id'], 'low': wall['low'], 'high': wall['high'],
                           'members': wall['members']} for wall in spy['walls'][:2]],
              'coverage': {'contracts': spy['coverage']['returned'], 'strikes': len(spy['strike_axis']),
                           'vex_missing_inputs': spy['vex']['missing_vanna_inputs'],
                           'vex_model': spy['vex']['model'], 'vex_unit': spy['vex']['unit'],
                           'window': 'IDENTITY_UNDECLARED', 'qqq_checked_days': source['qqq']['checked_utc_days'],
                           'qqq_snapshot_count': source['qqq']['snapshot_count']},
              'limitations': LIMITATIONS, 'required_evidence': REQUIRED_EVIDENCE,
              'review_only': True, 'executable': False, 'root_review_required': True}
    packet['packet_id'] = hashlib.sha256(canonical(packet).encode()).hexdigest()
    return packet


def _same(a, b):
    return canonical(a) == canonical(b)


def request_for(role, investigator=None):
    if role not in ('research', 'audit'):
        raise HeatmapError('role_not_registered')
    packet = _base_packet()
    packet['role'] = role
    if role == 'audit':
        if investigator is None:
            raise HeatmapError('missing_investigator_output')
        if not validate_investigator(investigator)['accepted']:
            raise HeatmapError('invalid_investigator_output')
        packet['investigator'] = json.loads(canonical(investigator))
        packet['investigator_sha256'] = hashlib.sha256(canonical(investigator).encode()).hexdigest()
    elif investigator is not None:
        raise HeatmapError('unexpected_investigator_output')
    return json.loads(canonical(packet))


def role_view(packet):
    if not isinstance(packet, dict):
        raise HeatmapError('untrusted_task_packet')
    expected = request_for(packet.get('role'), packet.get('investigator'))
    if not _same(packet, expected):
        raise HeatmapError('untrusted_task_packet')
    return expected


def _header(packet):
    return {'task_id': TASK_ID, 'packet_id': packet['packet_id'], 'scope': packet['scope'],
            'status': 'review_only', 'executable': False, 'root_review_required': True,
            'limitations': LIMITATIONS}


def validate_investigator(response):
    try:
        packet = _base_packet()
        if len(canonical(response).encode()) > RESPONSE_LIMIT or not isinstance(response, dict):
            raise HeatmapError('response_shape_refused')
        header = _header(packet)
        if set(response) != set(header) | {'claims', 'questions', 'required_evidence'}:
            raise HeatmapError('investigator_fields_refused')
        if not _same({key: response[key] for key in header}, header):
            raise HeatmapError('source_scope_or_posture_mismatch')
        if not _same(response['required_evidence'], REQUIRED_EVIDENCE):
            raise HeatmapError('fresh_evidence_requirements_missing')
        questions, claims = response['questions'], response['claims']
        if not isinstance(questions, list) or not 1 <= len(questions) <= 2 or not isinstance(claims, list):
            raise HeatmapError('question_count_refused')
        selected = set()
        required = set()
        for question in questions:
            if not isinstance(question, dict) or set(question) != {'type', 'wall_id', 'fact_ids', 'rationale'}:
                raise HeatmapError('question_fields_refused')
            kind = question['type']
            if not isinstance(kind, str) or kind not in QUESTION_SPECS or kind in selected:
                raise HeatmapError('question_type_refused')
            spec = QUESTION_SPECS[kind]
            if question['wall_id'] != spec['wall_id'] or not _same(question['fact_ids'], spec['fact_ids']):
                raise HeatmapError('question_identity_mismatch')
            if question['rationale'] != spec['rationale']:
                raise HeatmapError('question_narrative_refused')
            selected.add(kind)
            required.update(spec['fact_ids'])
        if len(claims) != len(required):
            raise HeatmapError('cited_claim_coverage_mismatch')
        facts = {fact['id']: fact for fact in packet['facts']}
        seen = set()
        for claim in claims:
            if not isinstance(claim, dict) or set(claim) != {'fact_id', 'value', 'unit', 'citation'}:
                raise HeatmapError('claim_fields_refused')
            fact_id = claim['fact_id']
            if not isinstance(fact_id, str) or fact_id not in required or fact_id in seen:
                raise HeatmapError('claim_identity_mismatch')
            expected = {'fact_id': fact_id, **{key: facts[fact_id][key] for key in ('value', 'unit', 'citation')}}
            if not _same(claim, expected):
                raise HeatmapError('literal_fact_mismatch')
            seen.add(fact_id)
        return {'accepted': True, 'reason': 'literal_facts_and_conditional_questions_valid',
                'semantic_audit_required': True, 'root_review_required': True, 'executable': False}
    except (HeatmapError, TypeError, KeyError) as exc:
        return {'accepted': False, 'reason': str(exc) if isinstance(exc, HeatmapError) else 'response_shape_refused',
                'executable': False}


def validate_audit(investigator, response):
    try:
        packet = request_for('audit', investigator)
        header = _header(packet)
        header['investigator_sha256'] = packet['investigator_sha256']
        if (len(canonical(response).encode()) > RESPONSE_LIMIT or not isinstance(response, dict)
                or set(response) != set(header) | {'verdicts'}):
            raise HeatmapError('audit_fields_refused')
        if not _same({key: response[key] for key in header}, header):
            raise HeatmapError('audit_binding_mismatch')
        questions = {question['type']: question for question in investigator['questions']}
        if not isinstance(response['verdicts'], list) or len(response['verdicts']) != len(questions):
            raise HeatmapError('audit_coverage_mismatch')
        seen, rejected = set(), False
        for verdict in response['verdicts']:
            if not isinstance(verdict, dict) or set(verdict) != {'type', 'verdict', 'reason', 'citations'}:
                raise HeatmapError('audit_verdict_fields_refused')
            kind = verdict['type']
            if not isinstance(kind, str) or kind not in questions or kind in seen:
                raise HeatmapError('audit_coverage_mismatch')
            if not _same(verdict['citations'], questions[kind]['fact_ids']):
                raise HeatmapError('audit_citation_mismatch')
            if verdict['verdict'] == 'accept_research_only' and verdict['reason'] == 'supported_conditional_research':
                pass
            elif verdict['verdict'] == 'reject' and verdict['reason'] in AUDIT_REASONS:
                rejected = True
            else:
                raise HeatmapError('audit_reason_refused')
            seen.add(kind)
        return {'valid': True, 'accepted': not rejected,
                'reason': 'audit_rejected' if rejected else 'research_only_audit_pending_root_review',
                'root_review_required': True, 'executable': False}
    except (HeatmapError, TypeError, KeyError) as exc:
        return {'valid': False, 'accepted': False,
                'reason': str(exc) if isinstance(exc, HeatmapError) else 'audit_shape_refused', 'executable': False}


def fixture_response(packet, role):
    """Offline installed-SDK fixture only; never accepted as a native result."""
    packet = role_view(packet)
    if packet['role'] != role:
        raise HeatmapError('role_packet_mismatch')
    result = _header(packet)
    if role == 'research':
        result.update(claims=[{'fact_id': fact['id'], **{key: fact[key] for key in ('value', 'unit', 'citation')}}
                              for fact in packet['facts']],
                      questions=[{'type': kind, **{key: spec[key] for key in ('wall_id', 'fact_ids', 'rationale')}}
                                 for kind, spec in QUESTION_SPECS.items()], required_evidence=REQUIRED_EVIDENCE)
    else:
        result.update(investigator_sha256=packet['investigator_sha256'], verdicts=[
            {'type': question['type'], 'verdict': 'accept_research_only', 'reason': 'supported_conditional_research',
             'citations': question['fact_ids']} for question in packet['investigator']['questions']])
    return json.loads(canonical(result))


def prompt_for(packet, role):
    packet = role_view(packet)
    if packet['role'] != role:
        raise HeatmapError('role_packet_mismatch')
    example = fixture_response(packet, role)
    if role == 'research':
        instructions = ('Choose one or two question types from the example. Include every corresponding claim verbatim. '
                        'Keep the exact scope, limitations and required_evidence. Copy each chosen type\'s registered '
                        'rationale verbatim; no free-form rationale. The named type fixes the conditional question. ')
    else:
        instructions = ('Independently check each completed investigator question and its exact registered rationale '
                        'against the original source facts and clocks. Cover every question exactly once. '
                        'Use accept_research_only/supported_conditional_research or reject with one of: '
                        + ','.join(AUDIT_REASONS) + '. Never upgrade actionability. ')
    return ('Registered task ' + TASK_ID + ', role ' + role + '. ' + instructions
            + 'Return only JSON shaped like: ' + canonical(example) + '\nSource: ' + canonical(packet))


def input_key():
    # Deliberately independent of state aliases and rule/code changes. The same
    # frozen evidence is never a new automatic attempt merely after an edit.
    MODEL = _worker().MODEL
    return hashlib.sha256(canonical({'task_id': TASK_ID, 'source': SOURCE_SHA256,
                                     'model': MODEL, 'policy': POLICY}).encode()).hexdigest()


def _native_envelope(native):
    return (isinstance(native, dict) and native.get('success') is True and native.get('native_failed') is False
            and native.get('offline_replay') is False and type(native.get('http_request_count')) is int
            and native['http_request_count'] == 1 and type(native.get('blocked_http_attempt_count')) is int
            and native['blocked_http_attempt_count'] == 0 and native.get('native_valid_tool_names') == []
            and native.get('stream_done') is True and native.get('finish_reason') == 'stop')


def run_once(state, *, role_runner=None, now=None):
    """Manual registered trial using the unchanged fixed global admission ledger."""
    worker = _worker()
    state = Path(state)
    real_clock = now is None
    now = time.time() if real_clock else now
    runner = worker.run_native_role if role_runner is None else role_runner

    def finish(result, path=None):
        result.setdefault('started_at', now)
        result.update(finished_at=time.time() if real_clock else now, executable=False,
                      root_review_required=True, scope='registered_heatmap_trial_only')
        if path is not None:
            worker.atomic_json(path, result)
        worker.atomic_json(state / 'latest.json', result)
        return result

    if worker.paused(state):
        return {'status': 'paused', 'executable': False, 'scope': 'registered_heatmap_trial_only'}
    try:
        with worker.Lease(state), worker.Lease(worker.ADMISSION_STATE) as admission:
            if worker.paused(state):
                return {'status': 'paused', 'executable': False, 'scope': 'registered_heatmap_trial_only'}
            try:
                packet = request_for('research')
            except HeatmapError as exc:
                return finish({'status': 'parked', 'reason': str(exc)})
            key = input_key()
            worker.ensure_dir(state / 'receipts')
            path = state / 'receipts' / (key + '.json')
            if path.exists() or path.is_symlink():
                old = worker.parse_json(worker.read_bytes(path))
                return finish({'status': 'duplicate_no_call', 'input_key': key, 'previous_status': old.get('status')})
            if len(list((state / 'receipts').glob('*.json'))) >= worker.MAX_RECEIPTS:
                return finish({'status': 'parked', 'reason': 'receipt_capacity_manual_archive_required'})
            ledger = worker.admission_ledger()
            admission.check()
            refusal = worker.reserve_pair(ledger, key, now)
            if refusal is not None:
                return finish(refusal)
            rule_files = [Path(__file__), Path(worker.__file__), worker.ROLE_HELPER, SOURCE_FILE]
            receipt = {'schema': 'floww-heatmap-run.v1', 'task_id': TASK_ID, 'input_key': key,
                       'packet_id': packet['packet_id'], 'source_sha256': SOURCE_SHA256,
                       'status': 'started', 'started_at': now, 'model': worker.MODEL, 'policy': POLICY,
                       'rule_hash': hashlib.sha256(b''.join(p.read_bytes() for p in rule_files)).hexdigest(),
                       'executable': False, 'root_review_required': True, 'automatic_retries': 0,
                       'cost_usd': None, 'cost_status': 'unknown', 'roles': {}}
            worker.atomic_json(path, receipt)
            worker.atomic_json(state / 'packets' / (key + '.json'), packet)
            investigator = None
            for role in ('research', 'audit'):
                admission.check()
                if worker.paused(state):
                    receipt['reason'] = 'worker_paused'
                    break
                try:
                    request = request_for(role, investigator if role == 'audit' else None)
                    native = runner(role, request, state)
                    if not isinstance(native, dict):
                        raise HeatmapError('native_protocol_refused')
                    response = native.get('response')
                    validation = (validate_investigator(response) if role == 'research'
                                  else validate_audit(investigator, response))
                    if not _native_envelope(native):
                        validation = {'accepted': False, 'reason': 'native_envelope_refused', 'executable': False}
                    record = {key: native[key] for key in META_FIELDS if key in native}
                    record['validation'] = validation
                    receipt['roles'][role] = record
                    if validation['accepted']:
                        record['response'] = json.loads(canonical(response))
                        if role == 'research':
                            investigator = record['response']
                    elif role == 'audit' and validation.get('valid') and _native_envelope(native):
                        record['response'] = json.loads(canonical(response))
                    admission.check()
                    worker.atomic_json(path, receipt)
                    if not validation['accepted']:
                        receipt['reason'] = validation['reason']
                        break
                except (HeatmapError, worker.WorkerError, OSError, ValueError, TypeError):
                    receipt['roles'][role] = {'validation': {'accepted': False, 'reason': 'role_refused'}}
                    receipt['reason'] = 'role_refused'
                    break
            accepted = (len(receipt['roles']) == 2 and
                        all(record['validation']['accepted'] for record in receipt['roles'].values()))
            receipt['status'] = 'validated_research_pending_root_review' if accepted else 'parked'
            receipt['reason'] = 'research_only_audit_pending_root_review' if accepted else receipt.get('reason', 'role_refused')
            ledger['attempts'][key]['status'] = 'accepted' if accepted else 'parked'
            ledger['circuit_parked'] = not accepted
            admission.check()
            worker.atomic_json(worker.ADMISSION_STATE / 'admission.json', ledger)
            return finish(receipt, path)
    except worker.WorkerError as exc:
        if str(exc) == 'lease_busy':
            return {'status': 'busy', 'executable': False, 'scope': 'registered_heatmap_trial_only'}
        raise


def status(state):
    worker = _worker()
    path = Path(state) / 'latest.json'
    if worker.paused(state):
        return {'status': 'paused', 'scope': 'registered_heatmap_trial_only', 'executable': False}
    return worker.parse_json(worker.read_bytes(path)) if path.exists() else {
        'status': 'ready', 'scope': 'registered_heatmap_trial_only', 'executable': False}


def _worker():
    try:
        from . import research_worker
    except ImportError:
        import research_worker
    return research_worker
