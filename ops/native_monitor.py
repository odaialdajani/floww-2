#!/usr/bin/env python3
"""Read fixed stored SPY/QQQ evidence; emit stable research candidates, never run agents.

No model/provider/account/order/refresh/alert calls, shell, writes or dispatch.
Native monitor mode holds with nonzero exit before inference. No-agent mode
holds silently. A candidate still needs trusted shared-budget reservation.
"""
import argparse
import datetime
import hashlib
import http.client
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import sys
import threading
import time

MAX_BODY = 256 * 1024
MAX_OUTPUT = 7000  # Native monitor context caps output at 8000 characters.
SYMBOLS = ('SPY', 'QQQ')
PATHS = tuple('/api/flowseeker/scan-public/observations?ticker=' + symbol + '&limit=3&order=received'
              for symbol in SYMBOLS)
ROOT = Path('/Users/nav')
STATE = ROOT / 'Library/Application Support/FLOWW/operations/research'
ADMISSION = STATE.parent / 'research-admission/admission.json'
SEEN = STATE.parent / 'native-monitor/consumed-events.json'
REQUIRED_CLOCKS = ('received_at', 'event_time', 'quote_source_time', 'bid_source_time', 'ask_source_time')


class Hold(ValueError):
    """Only stable, nonsecret hold codes reach output."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def parse_json(body):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Hold('duplicate_json_key')
            result[key] = value
        return result
    try:
        value = json.loads(body, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(Hold('nonfinite_json')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Hold('invalid_json') from exc
    if not isinstance(value, dict):
        raise Hold('invalid_json_object')
    return value


def safe_json(path):
    try:
        if any(p.is_symlink() for p in [path, *path.parents]):
            raise Hold('unsafe_control_file')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise Hold('unsafe_control_file')
            body = handle.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise Hold('control_byte_limit')
        return parse_json(body)
    except OSError as exc:
        raise Hold('control_unavailable') from exc


def read_controls():
    stops = [ROOT / '.hermes/ESTOP', STATE / 'PAUSED']
    stops += [ROOT / '.hermes/profiles' / ('floww-' + role) / 'ESTOP' for role in ('research', 'audit')]
    if any(p.exists() or p.is_symlink() for p in stops):
        raise Hold('research_held')
    control = safe_json(STATE / 'control.json')
    if control.get('schema') != 'floww-research-control.v1' or control.get('enabled') is not True:
        raise Hold('research_not_enabled')
    ledger = safe_json(ADMISSION)
    # An independent consumer must record events before inference; this reader
    # never creates the index or treats a missing one as an unused budget.
    seen = safe_json(SEEN)
    if (seen.get('schema') != 'floww-native-consumed-events.v1'
            or not isinstance(seen.get('source_event_ids'), list)
            or len(seen['source_event_ids']) > 4096
            or any(not isinstance(x, str) or not re.fullmatch('event_[a-f0-9]{64}', x)
                   for x in seen['source_event_ids'])):
        raise Hold('invalid_consumed_events')
    return {**ledger, 'consumed_source_events': seen['source_event_ids']}


def validate_controls(ledger, now):
    if (not isinstance(ledger, dict) or ledger.get('schema') != 'floww-research-admission.v1'
            or type(ledger.get('daily_pair_limit')) is not int
            or not 1 <= ledger['daily_pair_limit'] <= 4
            or type(ledger.get('circuit_parked')) is not bool
            or not isinstance(ledger.get('attempts'), dict) or len(ledger['attempts']) > 1024):
        raise Hold('invalid_admission_ledger')
    day = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).date().isoformat()
    attempts = ledger['attempts']
    for key, attempt in attempts.items():
        if (not isinstance(key, str) or not re.fullmatch('[a-f0-9]{64}', key)
                or not isinstance(attempt, dict) or attempt.get('status') not in ('started', 'accepted', 'parked')
                or not isinstance(attempt.get('day_utc'), str)
                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', attempt['day_utc'])):
            raise Hold('invalid_admission_ledger')
    if ledger['circuit_parked'] or any(a['status'] == 'started' for a in attempts.values()):
        raise Hold('native_circuit_parked')
    if attempts and day < max(a['day_utc'] for a in attempts.values()):
        raise Hold('admission_clock_regressed')
    if sum(a['day_utc'] == day for a in attempts.values()) >= ledger['daily_pair_limit']:
        raise Hold('daily_pair_budget_exhausted')
    if len(attempts) >= 1024:
        raise Hold('admission_capacity_manual_review_required')


def fetch_saved(connection_factory=http.client.HTTPConnection, deadline_seconds=4.5):
    """POSIX main-thread wall deadline; literal loopback, fixed GETs, no redirect/retry."""
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, 'setitimer'):
        raise Hold('wall_deadline_unavailable')
    def expired(signum, frame):
        raise Hold('saved_deadline')
    old_handler = signal.signal(signal.SIGALRM, expired)
    old_timer = signal.setitimer(signal.ITIMER_REAL, deadline_seconds)
    started = time.monotonic()
    pages = []
    try:
        for path in PATHS:
            if time.monotonic() - started >= deadline_seconds:
                pages.append({'monitor_hold': 'saved_deadline'})
                continue
            connection = None
            try:
                connection = connection_factory('127.0.0.1', 8213, timeout=2)
                connection.request('GET', path, headers={'Accept': 'application/json', 'Connection': 'close'})
                response = connection.getresponse()
                if response.status != 200:
                    raise Hold('saved_http_refused')
                if response.getheader('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                    raise Hold('saved_content_type')
                if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                    raise Hold('saved_encoding_refused')
                length = response.getheader('Content-Length')
                if length is not None and (not re.fullmatch('[0-9]{1,9}', length) or int(length) > MAX_BODY):
                    raise Hold('saved_body_limit')
                body = bytearray()
                while True:
                    chunk = response.read1(min(8192, MAX_BODY + 1 - len(body)))
                    body.extend(chunk)
                    if len(body) > MAX_BODY:
                        raise Hold('saved_body_limit')
                    if not chunk:
                        break
                if length is not None and len(body) != int(length):
                    raise Hold('saved_incomplete_body')
                pages.append(parse_json(body))
            except Hold as exc:
                pages.append({'monitor_hold': str(exc)})
            except (OSError, http.client.HTTPException):
                pages.append({'monitor_hold': 'saved_unavailable'})
            finally:
                if connection is not None:
                    connection.close()
        return pages
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        if old_timer[0]:
            signal.setitimer(signal.ITIMER_REAL, max(.001, old_timer[0] - (time.monotonic() - started)), old_timer[1])


def compile_events(pages, now, seen=()):
    """Keep provider source identity stable while independently requiring fresh receipts."""
    if type(now) not in (int, float) or not math.isfinite(now):
        raise Hold('invalid_clock')
    if not isinstance(pages, list) or len(pages) > 2:
        raise Hold('stored_page_limit')
    # Load only the existing pure compiler, never research_worker/native runtime.
    spec = importlib.util.spec_from_file_location('_floww_monitor_intake', Path(__file__).with_name('research_intake.py'))
    intake = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(intake)
    finally:
        sys.dont_write_bytecode = previous
    events, held = {}, {}
    for index, symbol in enumerate(SYMBOLS):
        page = pages[index] if index < len(pages) else {}
        try:
            if isinstance(page, dict) and page.get('monitor_hold') in {
                    'saved_deadline', 'saved_http_refused', 'saved_content_type', 'saved_encoding_refused',
                    'saved_body_limit', 'saved_incomplete_body', 'saved_unavailable', 'invalid_json',
                    'invalid_json_object', 'duplicate_json_key', 'nonfinite_json'}:
                raise Hold(page['monitor_hold'])
            if not isinstance(page, dict) or 'rows' not in page or page['rows'] == []:
                raise Hold('missing_observations')
            rows = page['rows']
            if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
                raise Hold('stored_row_limit')
            if any(row[0] != symbol for row in rows):
                raise Hold('stored_symbol_mismatch')
            packet = intake.compile_snapshot(page, now)
            if packet['excluded']:
                raise Hold('excluded_stored_evidence')
            fresh = 0
            for row in packet['observations']:
                clocks = row['clocks']
                if any(clocks[k]['value'] is None or clocks[k]['freshness'] != 'fresh' for k in REQUIRED_CLOCKS):
                    continue
                fresh += 1
                stable = {'symbol': symbol, 'contract_id': row['contract_id'], 'expiry': row['expiry'],
                          'provider': row['provider'], 'scope': row['scope'], 'fields': row['fields'],
                          'source_clocks': {k: v['value'] for k, v in clocks.items() if k != 'received_at'}}
                identity = {key: value for key, value in stable.items() if key != 'fields'}
                key = 'event_' + hashlib.sha256(canonical(identity).encode()).hexdigest()
                events[key] = {**stable, 'source_event_id': key}
            if not fresh:
                raise Hold('fresh_source_clocks_required')
        except Hold as exc:
            held[symbol] = str(exc)
        except (KeyError, IndexError, TypeError, ValueError, RecursionError):
            held[symbol] = 'invalid_stored_evidence'
    if not events:
        raise Hold('no_eligible_source_events')
    if not set(events) - set(seen):
        raise Hold('no_new_source_event')
    ordered = sorted(events.values(), key=lambda event: (event['symbol'], event['contract_id'], event['source_event_id']))
    return {'schema': 'floww-native-monitor.v1', 'status': 'research_candidate',
            'events': ordered, 'event_digest': hashlib.sha256(canonical(ordered).encode()).hexdigest(),
            'coverage': {'eligible_symbols': sorted(set(SYMBOLS) - set(held)),
                         'held_symbols': held, 'row_cap_per_symbol': 3},
            'executable': False, 'trade_eligible': False, 'requires_shared_budget_reservation': True,
            'limitations': ['saved_options_only', 'not_heatmap_or_orderflow_coverage',
                            'oi_and_greek_clocks_not_verified', 'not_execution_admission']}


def run(mode='monitor', *, now=None, pages=None, controls=None, stdout=None, stderr=None):
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    try:
        now = time.time() if now is None else now
        live_controls = controls is None
        controls = read_controls() if live_controls else controls
        validate_controls(controls, now)
        pages = fetch_saved() if pages is None else pages
        if live_controls:
            controls = read_controls()
            validate_controls(controls, now)
        result = compile_events(pages, now,
                                seen=controls.get('consumed_source_events', ()))
        encoded = canonical(result)
        if len(encoded) > MAX_OUTPUT:
            raise Hold('monitor_output_limit')
    except Hold as exc:
        if mode == 'no-agent':
            return 0
        print('held:' + str(exc), file=stderr)
        return 3
    print(encoded, file=stdout)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['monitor', 'no-agent'], default='monitor')
    return run(parser.parse_args().mode)


if __name__ == '__main__':
    raise SystemExit(main())
