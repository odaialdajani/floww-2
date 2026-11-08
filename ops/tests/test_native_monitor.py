"""Deterministic native-monitor admission; no provider, model or live HTTP."""
import copy
import io
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS))
try:
    import native_monitor as monitor
except ImportError:
    monitor = None

NOW = 1794254400
COLUMNS = ['underlying_ticker', 'ticker', 'contract_type', 'strike_price',
           'expiration_date', 'day_volume', 'open_interest', 'implied_volatility',
           'delta', 'underlying_price']


def page(symbol):
    key = symbol + '|call|500|2026-11-10'
    clocks = {'received_at': NOW - 1, 'event_time': NOW - 2,
              'quote_source_time': NOW - 3, 'bid_source_time': NOW - 3,
              'ask_source_time': NOW - 2}
    return {'source': 'public-scan-observations', 'live': False, 'trade_eligible': False,
            'columns': COLUMNS, 'rows': [[symbol, symbol + '261110C00500000', 'call',
            500, '2026-11-10', 10, 2, .3, .5, 500]], 'count': 1,
            'total': 1, 'limit': 3, 'offset': 0, 'next_offset': None,
            'row_observations': {key: {**clocks, 'source': 'public_api',
                                     'scope': 'saved:test', 'data_status': 'available'}},
            'quote_truth': {key: {'bid': 1, 'ask': 1.1,
                                 'bid_source_time': NOW - 3, 'ask_source_time': NOW - 2}},
            'observations_by_ticker': {symbol: {'source': 'public_api', 'scope': 'saved:test'}},
            'coverage': {}}


def ledger():
    return {'schema': 'floww-research-admission.v1', 'daily_pair_limit': 4,
            'circuit_parked': False, 'attempts': {}}


class NativeMonitorTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(monitor, 'native cache monitor is missing')
        return monitor

    def test_new_fresh_spy_and_qqq_emit_stable_nonexecutable_evidence(self):
        m = self.module()
        result = m.compile_events([page('SPY'), page('QQQ')], NOW)
        self.assertEqual(result['schema'], 'floww-native-monitor.v1')
        self.assertEqual([event['symbol'] for event in result['events']], ['QQQ', 'SPY'])
        self.assertFalse(result['executable'])
        self.assertFalse(result['trade_eligible'])
        self.assertIn('oi_and_greek_clocks_not_verified', result['limitations'])
        self.assertRegex(result['event_digest'], '^[a-f0-9]{64}$')
        self.assertEqual(len(result['events']), 2)

    def test_poll_time_age_checked_at_and_new_receipt_do_not_mint_source_events(self):
        m = self.module()
        pages = [page('SPY'), page('QQQ')]
        first = m.compile_events(pages, NOW)
        altered = copy.deepcopy(pages)
        for p in altered:
            p['checked_at'] = NOW + 5
            p['age_seconds'] = 999
            for row in p['row_observations'].values():
                row['received_at'] = NOW + 4
        self.assertEqual(first, m.compile_events(altered, NOW + 5))

    def test_missing_stale_future_or_conflicting_clock_holds_only_its_symbol(self):
        m = self.module()
        for field, value in [('bid_source_time', None), ('ask_source_time', NOW - 61),
                             ('event_time', NOW + 1), ('received_at', None)]:
            pages = [page('SPY'), page('QQQ')]
            for container in ['row_observations', 'quote_truth']:
                row = next(iter(pages[0][container].values()))
                if field in row:
                    row[field] = value
            with self.subTest(field=field):
                result = m.compile_events(pages, NOW)
                self.assertEqual(result['coverage']['eligible_symbols'], ['QQQ'])
                self.assertIn('SPY', result['coverage']['held_symbols'])
        pages = [page('SPY'), page('QQQ')]
        next(iter(pages[0]['quote_truth'].values()))['ask_source_time'] = NOW - 4
        self.assertEqual(m.compile_events(pages, NOW)['coverage']['eligible_symbols'], ['QQQ'])

    def test_wrong_ticker_scope_and_malformed_page_never_substitute_symbol_evidence(self):
        m = self.module()
        bad = [page('SPY'), page('QQQ')]
        bad[0]['observations_by_ticker']['SPY']['scope'] = 'forged'
        cases = [[page('SPY'), page('SPY')], bad,
                 [page('SPY'), {**page('QQQ'), 'count': 2}]]
        for pages in cases:
            with self.subTest(pages=pages):
                result = m.compile_events(pages, NOW)
                self.assertEqual(len(result['coverage']['eligible_symbols']), 1)
                self.assertEqual(len(result['coverage']['held_symbols']), 1)

    def test_fresh_spy_with_missing_qqq_and_fresh_qqq_with_stale_spy_are_independent(self):
        m = self.module()
        missing = {**page('QQQ'), 'rows': [], 'count': 0}
        result = m.compile_events([page('SPY'), missing], NOW)
        self.assertEqual(result['coverage']['eligible_symbols'], ['SPY'])
        self.assertEqual(result['coverage']['held_symbols'], {'QQQ': 'missing_observations'})
        self.assertEqual({x['symbol'] for x in result['events']}, {'SPY'})
        stale = page('SPY')
        next(iter(stale['row_observations'].values()))['received_at'] = NOW - 100
        result = m.compile_events([stale, page('QQQ')], NOW)
        self.assertEqual(result['coverage']['eligible_symbols'], ['QQQ'])

    def test_coverage_only_changes_cannot_wake_consumed_source_event(self):
        m = self.module()
        result = m.compile_events([page('SPY'), page('QQQ')], NOW)
        seen = [x['source_event_id'] for x in result['events']]
        with self.assertRaisesRegex(m.Hold, 'no_new_source_event'):
            m.compile_events([page('SPY'), {}], NOW, seen=seen)

    def test_changed_value_without_new_provider_clock_cannot_reuse_consumed_event(self):
        m = self.module()
        pages = [page('SPY'), page('QQQ')]
        seen = [event['source_event_id'] for event in m.compile_events(pages, NOW)['events']]
        pages[0]['rows'][0][6] = 999
        next(iter(pages[0]['quote_truth'].values()))['bid'] = 1.05
        with self.assertRaisesRegex(m.Hold, 'no_new_source_event'):
            m.compile_events(pages, NOW, seen=seen)

    def test_seen_source_events_hold_even_when_receipt_changes(self):
        m = self.module()
        pages = [page('SPY'), page('QQQ')]
        events = m.compile_events(pages, NOW)['events']
        seen = [event['source_event_id'] for event in events]
        with self.assertRaisesRegex(m.Hold, 'no_new_source_event'):
            m.compile_events(pages, NOW, seen=seen)

    def test_monitor_hold_is_nonzero_empty_stdout_even_on_first_tick(self):
        m = self.module()
        out, err = io.StringIO(), io.StringIO()
        code = m.run('monitor', now=NOW, pages=[], controls=ledger(), stdout=out, stderr=err)
        self.assertNotEqual(code, 0)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('held:', err.getvalue())

    def test_no_agent_hold_is_successfully_silent_and_success_is_same_digest(self):
        m = self.module()
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(m.run('no-agent', now=NOW, pages=[], controls=ledger(),
                               stdout=out, stderr=err), 0)
        self.assertEqual(out.getvalue(), '')
        self.assertEqual(err.getvalue(), '')
        pages = [page('SPY'), page('QQQ')]
        self.assertEqual(m.run('no-agent', now=NOW, pages=pages, controls=ledger(),
                               stdout=out, stderr=err), 0)
        self.assertEqual(json.loads(out.getvalue())['event_digest'],
                         m.compile_events(pages, NOW)['event_digest'])

    def test_parked_or_unfinished_admission_never_reads_cache(self):
        m = self.module()
        for controls in [{**ledger(), 'circuit_parked': True},
                         {**ledger(), 'attempts': {'a' * 64: {'status': 'started', 'day_utc': '2026-11-09'}}}]:
            with self.subTest(controls=controls), mock.patch.object(m, 'fetch_saved', side_effect=AssertionError('cache read forbidden')):
                out, err = io.StringIO(), io.StringIO()
                self.assertNotEqual(m.run('monitor', now=NOW, controls=controls,
                                         stdout=out, stderr=err), 0)
                self.assertEqual(out.getvalue(), '')

    def test_duplicate_json_keys_and_nonfinite_values_are_rejected(self):
        m = self.module()
        for raw in [b'{"rows":[],"rows":[1]}', b'{"value":NaN}', b'[]']:
            with self.subTest(raw=raw), self.assertRaises(m.Hold):
                m.parse_json(raw)

    def test_http_reader_has_only_two_fixed_cache_gets_and_refuses_redirects(self):
        m = self.module()
        seen = []
        class Connection:
            def __init__(self, host, port, timeout):
                self.asserted = (host, port, timeout)
            def request(self, method, path, headers):
                seen.append((self.asserted[:2], method, path, headers))
            def getresponse(self):
                return Response(page('SPY' if len(seen) == 1 else 'QQQ'))
            def close(self):
                pass
        pages = m.fetch_saved(connection_factory=Connection)
        self.assertEqual(len(pages), 2)
        self.assertEqual([(x[0], x[1], x[2]) for x in seen], [
            (('127.0.0.1', 8213), 'GET', '/api/flowseeker/scan-public/observations?ticker=SPY&limit=3&order=received'),
            (('127.0.0.1', 8213), 'GET', '/api/flowseeker/scan-public/observations?ticker=QQQ&limit=3&order=received')])
        self.assertTrue(all('Authorization' not in x[3] for x in seen))
        with mock.patch.object(Connection, 'getresponse', return_value=Response({}, status=302)):
            with self.assertRaises(m.Hold):
                m.compile_events(m.fetch_saved(connection_factory=Connection), NOW)

    def test_http_body_and_wall_deadline_are_bounded(self):
        m = self.module()
        class Connection:
            def __init__(self, *args, **kwargs):
                pass
            def request(self, *args, **kwargs):
                pass
            def getresponse(self):
                return Response({}, raw=b' ' * (256 * 1024 + 1))
            def close(self):
                pass
        with self.assertRaises(m.Hold):
            m.compile_events(m.fetch_saved(connection_factory=Connection), NOW)
        def delayed(_):
            time.sleep(.5)
            return Response({})
        started = time.monotonic()
        with mock.patch.object(Connection, 'getresponse', delayed):
            with self.assertRaises(m.Hold):
                m.compile_events(m.fetch_saved(connection_factory=Connection, deadline_seconds=.05), NOW)
        self.assertLess(time.monotonic() - started, .4)

    def test_one_cache_http_failure_does_not_hide_other_symbols_fresh_evidence(self):
        m = self.module()
        class Connection:
            def __init__(self, *args, **kwargs):
                self.path = None
            def request(self, method, path, headers):
                self.path = path
            def getresponse(self):
                return Response(page('QQQ')) if 'ticker=QQQ&' in self.path else Response({}, status=503)
            def close(self):
                pass
        result = m.compile_events(m.fetch_saved(connection_factory=Connection), NOW)
        self.assertEqual(result['coverage']['eligible_symbols'], ['QQQ'])
        self.assertEqual(result['coverage']['held_symbols'], {'SPY': 'saved_http_refused'})

    def test_output_over_native_context_limit_holds_without_partial_stdout(self):
        m = self.module()
        pages = [page('SPY'), page('QQQ')]
        with mock.patch.object(m, 'MAX_OUTPUT', 100, create=True):
            out, err = io.StringIO(), io.StringIO()
            self.assertEqual(m.run('monitor', now=NOW, pages=pages, controls=ledger(),
                                   stdout=out, stderr=err), 3)
            self.assertEqual(out.getvalue(), '')
            self.assertIn('monitor_output_limit', err.getvalue())

    def test_budget_and_corrupt_admission_fail_before_cache_read(self):
        m = self.module()
        day = '2026-11-09'
        cases = [{'schema': 'forged'}, {**ledger(), 'daily_pair_limit': True},
                 {**ledger(), 'daily_pair_limit': 1, 'attempts': {
                     'a' * 64: {'status': 'accepted', 'day_utc': day}}}]
        for controls in cases:
            with self.subTest(controls=controls), mock.patch.object(m, 'fetch_saved', side_effect=AssertionError('cache read forbidden')):
                self.assertEqual(m.run('monitor', now=NOW, controls=controls,
                                       stdout=io.StringIO(), stderr=io.StringIO()), 3)

    def test_control_reads_preserve_all_bytes_and_a_stop_prevents_data_read(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            state = root / 'research'
            state.mkdir()
            control = state / 'control.json'
            control.write_text('{"schema":"floww-research-control.v1","enabled":true}')
            admission = root / 'admission.json'
            admission.write_text(json.dumps(ledger()))
            consumed = root / 'consumed.json'
            consumed.write_text('{"schema":"floww-native-consumed-events.v1","source_event_ids":[]}')
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (control, admission, consumed)}
            with mock.patch.multiple(m, ROOT=root, STATE=state, ADMISSION=admission, SEEN=consumed):
                out, err = io.StringIO(), io.StringIO()
                self.assertEqual(m.run('monitor', now=NOW, pages=[page('SPY'), page('QQQ')],
                                       stdout=out, stderr=err), 0)
                (state / 'PAUSED').write_text('held')
                with mock.patch.object(m, 'fetch_saved', side_effect=AssertionError('stop must precede read')):
                    self.assertEqual(m.run('monitor', now=NOW, stdout=io.StringIO(), stderr=io.StringIO()), 3)
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})

    def test_symlink_or_missing_control_is_a_hold_without_credential_reads(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            target = root / 'target.json'
            target.write_text('{"not":"a credential"}')
            link = root / 'link.json'
            link.symlink_to(target)
            for path in (root / 'missing', link):
                with self.subTest(path=path), self.assertRaises(m.Hold):
                    m.safe_json(path)

    def test_read_only_compiler_does_not_create_bytecode_in_installed_script_directory(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            shutil.copyfile(OPS / 'research_intake.py', root / 'research_intake.py')
            with mock.patch.object(m, '__file__', str(root / 'native_monitor.py')), \
                    mock.patch.object(sys, 'dont_write_bytecode', False):
                m.compile_events([page('SPY'), page('QQQ')], NOW)
                self.assertFalse(sys.dont_write_bytecode)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['research_intake.py'])

    def test_stop_or_circuit_change_during_cache_read_prevents_output(self):
        m = self.module()
        with mock.patch.object(m, 'read_controls', side_effect=[ledger(), m.Hold('research_held')]), \
                mock.patch.object(m, 'fetch_saved', return_value=[page('SPY'), page('QQQ')]):
            out, err = io.StringIO(), io.StringIO()
            self.assertEqual(m.run('monitor', now=NOW, stdout=out, stderr=err), 3)
            self.assertEqual(out.getvalue(), '')


class Response:
    def __init__(self, value, status=200, raw=None):
        self.status = status
        self.body = io.BytesIO(json.dumps(value).encode() if raw is None else raw)
        self.length = len(self.body.getvalue())
    def getheader(self, key, default=None):
        return {'Content-Type': 'application/json', 'Content-Length': str(self.length)}.get(key, default)
    def read1(self, n):
        return self.body.read(n)


if __name__ == '__main__':
    unittest.main()
