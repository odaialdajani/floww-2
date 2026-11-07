#!/usr/bin/env python3
"""Daily local review receipt. No workers, models, network, accounts or execution."""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time

DEFAULT_STATE = Path.home() / 'Library/Application Support/FLOWW/operations'
SCHEMA = 'floww-operations-receipt.v1'
ACCEPTANCE_SCHEMA = 'floww-operations-acceptance.v1'
TASKS = ('research', 'coding', 'internal_paper', 'liquid')
STAGES = ('source', 'native', 'runtime')
TASK_SCOPES = {'research': 'saved retrospective copied facts', 'coding': 'fixed arithmetic fixture',
               'internal_paper': 'isolated synthetic book', 'liquid': 'authenticated read-only'}
RECEIPT_KEYS = ('schema', 'date', 'collected_at', 'read_at', 'state', 'review', 'watchdog',
                'paper_effective', 'summary', 'next_action', 'capabilities', 'task_scopes', 'metrics')
COUNTERS = ('admitted', 'active', 'blocked', 'accepted_outputs', 'interventions',
            'first_pass_accepted', 'repeat_failures', 'rollbacks', 'accepted_tests', 'refused_evidence')
REFUSALS = frozenset(('evidence_missing', 'evidence_stale', 'evidence_invalid',
                     'independent_review_pending', 'native_unverified', 'runtime_unverified',
                     'paper_unresolved', 'mode_binding_unverified', 'worker_closed',
                     'provider_parked', 'budget_unknown', 'test_failure'))
CAPABILITIES = dict.fromkeys(('admission', 'execution', 'autofix', 'workers', 'models', 'network',
                             'account_actions', 'trading', 'service_control'), False)
MAX_INPUT = 32768
MAX_OUTPUT = 32768
REVIEW_MAX_AGE = 86400
WATCHDOG_MAX_AGE = 600
RETENTION_DAYS = 30
FAILURES = (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError)


class Deadline(Exception):
    """One-shot CLI deadline; inner input error handling must never swallow it."""


class Busy(Exception):
    """Another receipt operation holds the nonblocking kernel lease."""


def _unknown(reason, state='unknown'):
    return {'schema': SCHEMA, 'state': state, 'reason': reason,
            'capabilities': dict(CAPABILITIES)}


def _now(clock):
    value = clock()
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value < 253402300799:
        raise ValueError('Invalid clock')
    return float(value)


def _iso(value):
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('Invalid timestamp')
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise ValueError('UTC timestamp required')
    number = parsed.timestamp()
    if not math.isfinite(number) or number < 0:
        raise ValueError('Invalid timestamp')
    return number


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('Closed object required')


def _integer(value):
    if value is not None and (type(value) is not int or not 0 <= value <= 1_000_000_000):
        raise ValueError('Invalid counter')


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate key')
        result[key] = value
    return result


def _tree(value, depth=0, budget=None):
    if budget is None:
        budget = [0]
    budget[0] += 1
    if depth > 8 or budget[0] > 512:
        raise ValueError('Metadata bound exceeded')
    if type(value) is dict:
        if len(value) > 32:
            raise ValueError('Too many keys')
        for key, item in value.items():
            if len(key) > 80:
                raise ValueError('Oversized key')
            _tree(item, depth + 1, budget)
    elif type(value) is list:
        if len(value) > 32:
            raise ValueError('Oversized list')
        for item in value:
            _tree(item, depth + 1, budget)
    elif type(value) is str and len(value) > 200:
        raise ValueError('Oversized string')
    elif type(value) is float and not math.isfinite(value):
        raise ValueError('Nonfinite number')


def _private(info, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077 or (not directory and info.st_nlink != 1)):
        raise ValueError('Unsafe local state')


@contextlib.contextmanager
def _directory(path, create=False):
    """Open every path component without following a link; pin final directory fd."""
    absolute = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in absolute.parts[1:]:
            if create:
                with contextlib.suppress(FileExistsError):
                    os.mkdir(part, 0o700, dir_fd=fd)
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        _private(os.fstat(fd), directory=True)
        yield fd
    finally:
        os.close(fd)


@contextlib.contextmanager
def _child_directory(parent, name, create=False):
    if create:
        with contextlib.suppress(FileExistsError):
            os.mkdir(name, 0o700, dir_fd=parent)
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        _private(os.fstat(fd), directory=True)
        yield fd
    finally:
        os.close(fd)


def _read(directory, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        _private(os.fstat(fd))
        if os.fstat(fd).st_size > MAX_INPUT:
            raise ValueError('Oversized metadata')
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            body = stream.read(MAX_INPUT + 1)
        if len(body) > MAX_INPUT:
            raise ValueError('Oversized metadata')
        value = json.loads(body, object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite number')))
        _tree(value)
        return value
    finally:
        if fd is not None:
            os.close(fd)


def _exists(directory, name):
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _atomic(directory, name, value):
    body = (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode()
    if len(body) > MAX_OUTPUT:
        raise ValueError('Oversized receipt')
    if _exists(directory, name):
        _private(os.stat(name, dir_fd=directory, follow_symlinks=False))
    # One daily staging file bounds leftovers even if the process dies each day.
    pending = '.daily.pending' if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', name) else '.' + name + '.pending'
    fd = os.open(pending, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
    try:
        _private(os.fstat(fd))
        os.ftruncate(fd, 0)
        with os.fdopen(fd, 'wb') as stream:
            fd = None
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        if fd is not None:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(pending, dir_fd=directory)


@contextlib.contextmanager
def _lease(directory):
    fd = os.open('receipt.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                 0o600, dir_fd=directory)
    try:
        _private(os.fstat(fd))
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Busy() from error
        yield
    finally:
        os.close(fd)


def _paused(directory, now):
    if _exists(directory, 'OPERATIONS_STOP'):
        return True
    try:
        value = _read(directory, 'receipt-control.json')
        _keys(value, ('schema', 'resumed_at'))
        return value['schema'] != 'floww-operations-control.v1' or _timestamp(value['resumed_at']) > now
    except FAILURES:
        return True


def _acceptance(value, now):
    _keys(value, ('schema', 'reviewed_at', 'source_commit', 'tasks', 'counters', 'last_progress_at',
                  'refusal_codes', 'cost_usd', 'paper'))
    reviewed = _timestamp(value['reviewed_at'])
    if value['schema'] != ACCEPTANCE_SCHEMA or reviewed > now:
        raise ValueError('Invalid review')
    if not isinstance(value['source_commit'], str) or not re.fullmatch('[a-f0-9]{40}', value['source_commit']):
        raise ValueError('Invalid commit')
    _keys(value['tasks'], TASKS)
    for item in value['tasks'].values():
        _keys(item, STAGES)
        if any(type(status) is not str or status not in ('accepted', 'blocked', 'unknown') for status in item.values()):
            raise ValueError('Invalid stage')
    _keys(value['counters'], COUNTERS)
    for count in value['counters'].values():
        _integer(count)
    cost = value['cost_usd']
    if cost is not None and (type(cost) not in (int, float) or not math.isfinite(cost) or not 0 <= cost <= 1e9):
        raise ValueError('Invalid cost')
    if value['last_progress_at'] is not None and _timestamp(value['last_progress_at']) > reviewed:
        raise ValueError('Future progress')
    refusals = value['refusal_codes']
    if (type(refusals) is not list or len(refusals) > len(REFUSALS)
            or any(type(code) is not str or code not in REFUSALS for code in refusals)
            or len(set(refusals)) != len(refusals)):
        raise ValueError('Invalid refusal')
    paper = value['paper']
    _keys(paper, ('status', 'positions', 'ledger_reviewed_at'))
    _integer(paper['positions'])
    if paper['status'] == 'unknown':
        if paper['positions'] is not None or paper['ledger_reviewed_at'] is not None:
            raise ValueError('Unknown paper requires unknown evidence')
    elif paper['status'] in ('verified_none', 'verified_unresolved'):
        if paper['positions'] is None or _timestamp(paper['ledger_reviewed_at']) > reviewed:
            raise ValueError('Missing ledger review')
        if (paper['status'] == 'verified_none') != (paper['positions'] == 0):
            raise ValueError('Contradictory ledger')
    else:
        raise ValueError('Invalid paper state')
    return value


def _watchdog(value, now):
    _keys(value, ('schema', 'checked_at', 'state', 'checks', 'identity', 'capabilities', 'scope'))
    if (value['schema'] != 'floww-watchdog.v1' or value['state'] not in
            ('healthy', 'unhealthy', 'unknown', 'paused') or type(value['checks']) is not dict
            or type(value['identity']) is not dict or type(value['capabilities']) is not dict
            or value['scope'] != 'local transport and release identity only'):
        raise ValueError('Invalid watchdog')
    if value['state'] == 'healthy':
        checks, identity = value['checks'], value['identity']
        _keys(checks, ('backend_version', 'backend_health', 'frontend'))
        _keys(identity, ('state', 'expected_sha', 'backend_sha', 'frontend_sha256', 'expected_frontend_sha256'))
        for name, fields in [('backend_version', ('state', 'sha', 'http_status')),
                             ('backend_health', ('state', 'health', 'http_status')),
                             ('frontend', ('state', 'sha256', 'http_status'))]:
            _keys(checks[name], fields)
            if checks[name]['state'] != 'ok' or type(checks[name]['http_status']) is not int or checks[name]['http_status'] != 200:
                raise ValueError('Watchdog availability unavailable')
        sha, back, digest = identity['expected_sha'], checks['backend_version']['sha'], checks['frontend']['sha256']
        if (identity['state'] != 'matched' or type(sha) is not str or not re.fullmatch('[a-f0-9]{40}', sha)
                or type(back) is not str or not re.fullmatch('[a-f0-9]{7,40}', back) or not sha.startswith(back)
                or type(digest) is not str or not re.fullmatch('[a-f0-9]{64}', digest)
                or checks['backend_health']['health'] != 'ok' or identity['backend_sha'] != back
                or identity['frontend_sha256'] != digest or identity['expected_frontend_sha256'] != digest):
            raise ValueError('Watchdog identity unavailable')
    age = now - _timestamp(value['checked_at'])
    if age < 0:
        raise ValueError('Future sample')
    fresh = age <= WATCHDOG_MAX_AGE
    return {'state': value['state'] if fresh else 'unknown', 'checked_at': value['checked_at'],
            'freshness': 'fresh' if fresh else 'stale', 'age_seconds': round(age, 3),
            'scope': 'local_availability_and_release_metadata_only'}


def _review(directory, now):
    try:
        value = _acceptance(_read(directory, 'acceptance.json'), now)
        result = {key: value[key] for key in value if key != 'schema'}
        result.update(evidence_scope='last_manual_review_only', counter_scope='last_integrator_review', reason=None)
        return result
    except FileNotFoundError:
        reason = 'acceptance_missing'
    except FAILURES:
        reason = 'acceptance_invalid'
    return {'reviewed_at': None, 'source_commit': None, 'tasks': None,
            'counters': dict.fromkeys(COUNTERS), 'last_progress_at': None, 'refusal_codes': [],
            'cost_usd': None, 'paper': {'status': 'unknown', 'positions': None, 'ledger_reviewed_at': None},
            'evidence_scope': 'last_manual_review_only', 'counter_scope': 'last_integrator_review', 'reason': reason}


def _ratio(numerator, denominator):
    if numerator is None or not denominator:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def _summarize(value, now):
    """Re-evaluate ages on every read; never promote reviewed facts to current proof."""
    review = value['review']
    reviewed = review['reviewed_at']
    age = now - _timestamp(reviewed) if reviewed is not None else None
    if age is not None and age < 0:
        raise ValueError('Clock rollback')
    fresh = age is not None and age <= REVIEW_MAX_AGE
    review['age_seconds'] = round(age, 3) if age is not None else None
    review['freshness'] = 'fresh' if fresh else ('stale' if age is not None else 'unknown')
    ledger_time = review['paper']['ledger_reviewed_at']
    ledger_fresh = fresh and ledger_time is not None and 0 <= now - _timestamp(ledger_time) <= REVIEW_MAX_AGE
    value['paper_effective'] = (review['paper'] if ledger_fresh else
                                {'status': 'unknown', 'positions': None, 'ledger_reviewed_at': None})
    summary = {name: dict.fromkeys(('accepted', 'blocked', 'unknown'), 0) for name in (*STAGES, 'tasks')}
    for name in TASKS:
        task = review['tasks'][name] if fresh else dict.fromkeys(STAGES, 'unknown')
        for stage in STAGES:
            summary[stage][task[stage]] += 1
        overall = 'blocked' if 'blocked' in task.values() else (
            'accepted' if all(item == 'accepted' for item in task.values()) else 'unknown')
        summary['tasks'][overall] += 1
    value['summary'] = summary
    watchdog = value['watchdog']
    if watchdog['checked_at'] is None:
        watchdog.update(state='unknown', age_seconds=None, freshness='unknown')
    else:
        sample_age = now - _timestamp(watchdog['checked_at'])
        if sample_age < 0:
            raise ValueError('Clock rollback')
        watchdog['age_seconds'] = round(sample_age, 3)
        if sample_age > WATCHDOG_MAX_AGE:
            watchdog.update(state='unknown', freshness='stale')
    unresolved = value['paper_effective']['status'] == 'verified_unresolved'
    value['state'] = ('blocked' if unresolved or summary['tasks']['blocked'] else
                      'reviewed' if summary['tasks']['accepted'] == len(TASKS) and ledger_fresh
                      and watchdog['state'] == 'healthy' else 'unknown')
    if unresolved:
        action = 'resolve_paper_ledger'
    elif review['reason'] is not None:
        action = 'provide_reviewed_evidence'
    elif not fresh:
        action = 'refresh_integrator_review'
    elif watchdog['state'] != 'healthy':
        action = 'inspect_local_availability'
    elif value['state'] != 'reviewed':
        action = 'independent_review_required'
    else:
        action = 'none'
    outputs, interventions, cost = review['counters']['accepted_outputs'], review['counters']['interventions'], review['cost_usd']
    value['metrics'] = {
        'scope': 'last_integrator_review',
        'accepted_outputs_per_intervention': _ratio(outputs, interventions),
        'accepted_outputs_per_usd': _ratio(outputs, cost)}
    value.update(next_action=action, capabilities=dict(CAPABILITIES), read_at=_iso(now), task_scopes=dict(TASK_SCOPES))
    return value


def _validate_saved(value, now):
    _keys(value, RECEIPT_KEYS)
    if value['schema'] != SCHEMA or _timestamp(value['collected_at']) > now:
        raise ValueError('Invalid receipt')
    # Revalidate retained typed evidence instead of trusting saved derived fields.
    reviewed = value['review']
    _keys(reviewed, ('reviewed_at', 'source_commit', 'tasks', 'counters', 'last_progress_at', 'refusal_codes',
                     'cost_usd', 'paper', 'evidence_scope', 'counter_scope', 'reason', 'age_seconds', 'freshness'))
    if (reviewed['evidence_scope'] != 'last_manual_review_only' or reviewed['counter_scope'] != 'last_integrator_review'
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value['date'])
            or value['date'] != value['collected_at'][:10]):
        raise ValueError('Invalid receipt scope')
    if reviewed['reviewed_at'] is not None:
        source = {key: reviewed[key] for key in ('reviewed_at', 'source_commit', 'tasks', 'counters',
                                                'last_progress_at', 'refusal_codes', 'cost_usd', 'paper')}
        _acceptance(dict(source, schema=ACCEPTANCE_SCHEMA), _timestamp(value['collected_at']))
        if reviewed['reason'] is not None:
            raise ValueError('Contradictory review')
    elif reviewed['tasks'] is not None or reviewed['reason'] not in ('acceptance_missing', 'acceptance_invalid'):
        raise ValueError('Invalid missing review')
    else:
        if (reviewed['source_commit'] is not None or reviewed['last_progress_at'] is not None
                or reviewed['refusal_codes'] != [] or reviewed['cost_usd'] is not None
                or reviewed['counters'] != dict.fromkeys(COUNTERS)
                or reviewed['paper'] != {'status': 'unknown', 'positions': None, 'ledger_reviewed_at': None}):
            raise ValueError('Invalid unknown review')
    availability = value['watchdog']
    _keys(availability, ('state', 'checked_at', 'freshness', 'age_seconds', 'scope'))
    if (availability['state'] not in ('healthy', 'unhealthy', 'unknown', 'paused')
            or availability['scope'] != 'local_availability_and_release_metadata_only'
            or availability['freshness'] not in ('fresh', 'stale', 'unknown')
            or (availability['checked_at'] is None and availability['state'] != 'unknown')):
        raise ValueError('Invalid watchdog state')
    # Derived output is reconstructed so arbitrary saved values cannot be echoed.
    value = {key: value[key] for key in ('schema', 'date', 'collected_at', 'review', 'watchdog')}
    return _summarize(value, now)


def _saved(directory, now):
    return _validate_saved(_read(directory, 'operations-status.json'), now)


def _retain(directory, today, now):
    # Only this module's closed, private, dated derived receipts are eligible.
    with os.scandir(directory) as entries:
        names = []
        for index, entry in enumerate(entries):
            if index >= 512:
                raise ValueError('History directory exceeds bound')
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json', entry.name):
                names.append(entry.name)
    for name in names:
        try:
            date = dt.date.fromisoformat(name[:-5])
            if (today - date).days < RETENTION_DAYS:
                continue
            value = _read(directory, name)
            if type(value) is dict and value.get('schema') == SCHEMA and value.get('date') == name[:-5]:
                _validate_saved(value, now)
                os.unlink(name, dir_fd=directory)
        except FAILURES:
            continue


def collect(state_dir=DEFAULT_STATE, clock=time.time):
    try:
        start = _now(clock)
        with _directory(state_dir, create=True) as directory, _lease(directory):
            if _exists(directory, 'operations-status.json'):
                _saved(directory, start)  # Refuse rollback or corrupt previous publication.
            if _paused(directory, start):
                return _unknown('receipt_paused', 'paused')
            review = _review(directory, start)
            try:
                availability = _watchdog(_read(directory, 'status.json'), start)
            except FAILURES:
                availability = {'state': 'unknown', 'checked_at': None, 'freshness': 'unknown',
                                'age_seconds': None, 'scope': 'local_availability_and_release_metadata_only'}
            end = _now(clock)
            if end < start or end - start > 4:
                raise ValueError('Clock changed during collection')
            if _paused(directory, end):
                return _unknown('receipt_paused', 'paused')
            date = _iso(end)[:10]
            result = _summarize({'schema': SCHEMA, 'date': date, 'collected_at': _iso(end),
                                 'review': review, 'watchdog': availability}, end)
            with _child_directory(directory, 'daily', create=True) as daily:
                _retain(daily, dt.date.fromisoformat(date), end)
                _atomic(daily, date + '.json', result)
            _atomic(directory, 'operations-status.json', result)
            return result
    except Busy:
        return _unknown('receipt_already_running', 'busy')
    except FAILURES:
        return _unknown('receipt_state_unavailable')


def status(state_dir=DEFAULT_STATE, clock=time.time):
    try:
        now = _now(clock)
        with _directory(state_dir) as directory:
            value = _saved(directory, now)
            if _paused(directory, now):
                value.update(state='paused', reason='receipt_paused')
            return value
    except FileNotFoundError:
        return _unknown('receipt_missing')
    except FAILURES:
        return _unknown('receipt_state_unavailable')


def pause(state_dir=DEFAULT_STATE, clock=time.time):
    try:
        now = _now(clock)
        with _directory(state_dir, create=True) as directory:
            # Publish stop before lease acquisition; collection checks it before writes.
            _atomic(directory, 'OPERATIONS_STOP', {'schema': 'floww-operations-stop.v1', 'paused_at': _iso(now)})
        return _unknown('receipt_paused', 'paused')
    except FAILURES:
        return _unknown('receipt_state_unavailable')


def resume(state_dir=DEFAULT_STATE, clock=time.time):
    try:
        now = _now(clock)
        with _directory(state_dir, create=True) as directory, _lease(directory):
            if _exists(directory, 'operations-status.json'):
                _saved(directory, now)
            _atomic(directory, 'receipt-control.json', {'schema': 'floww-operations-control.v1', 'resumed_at': _iso(now)})
            if _exists(directory, 'OPERATIONS_STOP'):
                _private(os.stat('OPERATIONS_STOP', dir_fd=directory, follow_symlinks=False))
                os.unlink('OPERATIONS_STOP', dir_fd=directory)
                os.fsync(directory)
        return _unknown('collection_needed')
    except Busy:
        return _unknown('receipt_already_running', 'busy')
    except FAILURES:
        return _unknown('receipt_state_unavailable')


def _deadline(_signal, _frame):
    raise Deadline()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE,
                        help='isolated private state for local checks; input filenames are fixed')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('collect', 'status', 'pause', 'resume'):
        commands.add_parser(name)
    check = commands.add_parser('check')
    check.add_argument('mode', choices=['once'])
    args = parser.parse_args(argv)
    old_handler = signal.signal(signal.SIGALRM, _deadline)
    signal.setitimer(signal.ITIMER_REAL, 4.0)
    try:
        action = {'collect': collect, 'check': collect, 'status': status, 'pause': pause, 'resume': resume}[args.command]
        result = action(args.state_dir)
    except Deadline:
        result = _unknown('receipt_deadline_exceeded')
    except FAILURES:
        result = _unknown('receipt_state_unavailable')
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return {'reviewed': 0, 'blocked': 1, 'unknown': 2, 'paused': 3, 'busy': 4}.get(result['state'], 2)


if __name__ == '__main__':
    sys.exit(main())
