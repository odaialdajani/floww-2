"""Local-only receipt contracts; fixtures never contact services or models."""
import fcntl
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

OPS = Path(__file__).resolve().parents[1]
SCRIPT = OPS / 'operations_receipt.py'
sys.path.insert(0, str(OPS))
NOW = 1794088800  # 2026-11-07 22:00:00 UTC


def acceptance():
    return {'schema': 'floww-operations-acceptance.v1',
            'reviewed_at': '2026-11-07T22:00:00Z', 'source_commit': 'a' * 40,
            'tasks': {name: {'source': 'accepted', 'native': 'unknown', 'runtime': 'unknown'}
                      for name in ('research', 'coding', 'internal_paper', 'liquid')},
            'counters': {name: None for name in (
                'admitted', 'active', 'blocked', 'accepted_outputs', 'interventions',
                'first_pass_accepted', 'repeat_failures', 'rollbacks', 'accepted_tests', 'refused_evidence')},
            'last_progress_at': None, 'refusal_codes': ['independent_review_pending'],
            'cost_usd': None, 'paper': {'status': 'unknown', 'positions': None, 'ledger_reviewed_at': None}}


def watchdog():
    return {'schema': 'floww-watchdog.v1', 'checked_at': '2026-11-07T22:00:00Z',
            'state': 'healthy', 'checks': {
                'backend_version': {'state': 'ok', 'sha': 'a' * 9, 'http_status': 200},
                'backend_health': {'state': 'ok', 'health': 'ok', 'http_status': 200},
                'frontend': {'state': 'ok', 'sha256': 'b' * 64, 'http_status': 200}},
            'identity': {'state': 'matched', 'expected_sha': 'a' * 40, 'backend_sha': 'a' * 9,
                         'frontend_sha256': 'b' * 64, 'expected_frontend_sha256': 'b' * 64},
            'capabilities': {}, 'scope': 'local transport and release identity only'}


class CliContract(unittest.TestCase):
    def test_missing_status_is_unknown_without_creating_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve() / 'absent'
            run = subprocess.run([sys.executable, str(SCRIPT), '--state-dir', str(target), 'status'],
                                 capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 2)
            self.assertTrue(run.stdout.startswith('{'), 'receipt status command missing')
            self.assertEqual(json.loads(run.stdout)['reason'], 'receipt_missing')
            self.assertFalse(target.exists())


class ReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global receipt
        import operations_receipt as receipt

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.clock = lambda: NOW

    def write(self, name, value):
        target = self.root / name
        target.write_text(json.dumps(value))
        target.chmod(0o600)
        return target

    def prepare(self):
        receipt.resume(self.root, clock=self.clock)
        self.write('acceptance.json', acceptance())
        self.write('status.json', watchdog())

    def collect(self, now=NOW):
        return receipt.collect(self.root, clock=lambda: now)

    def test_default_paused_then_resume_collects_once_with_honest_unknowns(self):
        paused = self.collect()
        self.assertEqual(paused['state'], 'paused')
        self.assertFalse((self.root / 'daily').exists())
        self.prepare()
        result = self.collect()
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(result['watchdog']['state'], 'healthy')
        self.assertEqual(result['review']['freshness'], 'fresh')
        self.assertEqual(result['review']['evidence_scope'], 'last_manual_review_only')
        self.assertEqual(result['summary']['source'], {'accepted': 4, 'blocked': 0, 'unknown': 0})
        self.assertEqual(result['summary']['tasks'], {'accepted': 0, 'blocked': 0, 'unknown': 4})
        self.assertIsNone(result['review']['counters']['accepted_tests'])
        self.assertIsNone(result['review']['cost_usd'])
        self.assertEqual(result['review']['paper']['status'], 'unknown')
        self.assertTrue(all(flag is False for flag in result['capabilities'].values()))
        self.assertEqual(result['next_action'], 'independent_review_required')

    def test_daily_updates_same_date_and_writes_private_atomic_files(self):
        self.prepare()
        self.collect()
        pending = self.root / 'daily' / '.daily.pending'
        pending.write_text('interrupted prior day')
        pending.chmod(0o600)
        value = acceptance()
        value['counters']['accepted_tests'] = 7
        self.write('acceptance.json', value)
        result = self.collect(now=NOW + 1)
        self.assertEqual(result['review']['counters']['accepted_tests'], 7)
        self.assertEqual([x.name for x in (self.root / 'daily').iterdir()], ['2026-11-07.json'])
        for name in ['operations-status.json', 'daily/2026-11-07.json']:
            self.assertEqual(stat.S_IMODE((self.root / name).stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.root / 'daily').stat().st_mode), 0o700)
        self.assertFalse(list(self.root.rglob('*.pending')))

    def test_stale_review_becomes_unknown_without_erasing_last_review_facts(self):
        self.prepare()
        result = self.collect(now=NOW + 86401)
        self.assertEqual(result['review']['freshness'], 'stale')
        self.assertEqual(result['review']['tasks']['coding']['source'], 'accepted')
        self.assertEqual(result['summary']['source']['unknown'], 4)
        self.assertEqual(result['watchdog']['state'], 'unknown')
        self.assertEqual(result['watchdog']['freshness'], 'stale')
        self.assertNotEqual(result['state'], 'healthy')

    def test_status_recalculates_ages_instead_of_repeating_old_green(self):
        self.prepare()
        self.collect()
        status = receipt.status(self.root, clock=lambda: NOW + 86401)
        self.assertEqual(status['review']['freshness'], 'stale')
        self.assertEqual(status['summary']['source']['unknown'], 4)
        self.assertEqual(status['watchdog']['state'], 'unknown')

    def test_missing_malformed_and_stale_watchdog_never_become_healthy(self):
        self.prepare()
        for value in [None, [], {'schema': 'wrong'}, dict(watchdog(), checked_at='bad'),
                      dict(watchdog(), checked_at='2026-11-07T21:00:00Z'),
                      dict(watchdog(), state='unhealthy')]:
            with self.subTest(value=value):
                if value is None:
                    (self.root / 'status.json').unlink(missing_ok=True)
                else:
                    self.write('status.json', value)
                result = self.collect()
                self.assertNotEqual(result['watchdog']['state'], 'healthy')

    def test_acceptance_rejects_unknown_keys_and_unsafe_values_without_echoing_them(self):
        self.prepare()
        cases = []
        for key, value in [('url', 'https://secret.invalid'), ('source_commit', 'SECRET'),
                           ('reviewed_at', '2026-11-07T22:00:01Z'), ('cost_usd', float('nan')),
                           ('cost_usd', True), ('last_progress_at', '2026-11-07T22:00:01Z')]:
            sample = acceptance()
            sample[key] = value
            cases.append(sample)
        for value in [-1, True, 1.5, 10**20]:
            sample = acceptance()
            sample['counters']['accepted_tests'] = value
            cases.append(sample)
        sample = acceptance()
        sample['tasks']['foreign'] = sample['tasks']['coding']
        cases.append(sample)
        sample = acceptance()
        sample['refusal_codes'] = ['secret text']
        cases.append(sample)
        sample = acceptance()
        sample['paper'] = {'status': 'verified_none', 'positions': 0, 'ledger_reviewed_at': None}
        cases.append(sample)
        for value in cases:
            with self.subTest(value=value):
                self.write('acceptance.json', value)
                result = self.collect()
                self.assertEqual(result['review']['reason'], 'acceptance_invalid')
                self.assertEqual(result['summary']['tasks']['unknown'], 4)
                self.assertNotIn('SECRET', json.dumps(result))
                self.assertNotIn('https:', json.dumps(result))

    def test_duplicate_keys_depth_and_oversize_are_unknown(self):
        self.prepare()
        path = self.root / 'acceptance.json'
        for body in ['{"schema":"x","schema":"y"}', '[' * 1000 + ']' * 1000, ' ' * 32769]:
            path.write_text(body)
            result = self.collect()
            self.assertEqual(result['review']['reason'], 'acceptance_invalid')

    def test_symlink_hardlink_fifo_and_public_input_are_never_followed(self):
        self.prepare()
        target = self.root / 'acceptance.json'
        outside = self.write('outside.json', acceptance())
        for kind in ['symlink', 'hardlink', 'fifo', 'public']:
            target.unlink()
            if kind == 'symlink':
                target.symlink_to(outside)
            elif kind == 'hardlink':
                os.link(outside, target)
            elif kind == 'fifo':
                os.mkfifo(target, 0o600)
            else:
                self.write('acceptance.json', acceptance()).chmod(0o644)
            started = time.monotonic()
            result = self.collect()
            self.assertLess(time.monotonic() - started, 1)
            self.assertEqual(result['review']['reason'], 'acceptance_invalid')
        self.assertEqual(json.loads(outside.read_text()), acceptance())

    def test_symlink_directory_or_output_refuses_without_touching_target(self):
        self.prepare()
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir(mode=0o700)
        (self.root / 'daily').symlink_to(elsewhere, target_is_directory=True)
        result = self.collect()
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(list(elsewhere.iterdir()), [])
        (self.root / 'daily').unlink()
        untouched = self.write('untouched', {'safe': True})
        (self.root / 'operations-status.json').symlink_to(untouched)
        result = self.collect()
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(json.loads(untouched.read_text()), {'safe': True})

    def test_symlink_in_state_parent_is_refused(self):
        alias = self.root / 'alias'
        real = self.root / 'real'
        real.mkdir(mode=0o700)
        alias.symlink_to(real, target_is_directory=True)
        result = receipt.resume(alias / 'state', clock=self.clock)
        self.assertEqual(result['state'], 'unknown')
        self.assertFalse((real / 'state').exists())

    def test_nonblocking_lease_and_stop_entry(self):
        self.prepare()
        lock = os.open(self.root / 'receipt.lock', os.O_RDWR)
        self.addCleanup(os.close, lock)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertEqual(self.collect()['state'], 'busy')
        fcntl.flock(lock, fcntl.LOCK_UN)
        receipt.pause(self.root, clock=self.clock)
        self.assertEqual(self.collect()['state'], 'paused')
        self.assertTrue((self.root / 'status.json').exists())
        receipt.resume(self.root, clock=self.clock)
        self.assertNotEqual(self.collect()['state'], 'paused')
        (self.root / 'OPERATIONS_STOP').symlink_to(self.root / 'absent')
        self.assertEqual(self.collect()['state'], 'paused')

    def test_clock_rollback_nan_and_exception_never_publish(self):
        self.prepare()
        self.collect()
        original = (self.root / 'operations-status.json').read_bytes()
        for clock in [lambda: NOW - 1, lambda: float('nan'), lambda: float('inf'),
                      lambda: True, mock.Mock(side_effect=OSError('sensitive error')),
                      mock.Mock(side_effect=[NOW + 1, NOW])]:
            with self.subTest(clock=clock):
                result = receipt.collect(self.root, clock=clock)
                self.assertEqual(result['state'], 'unknown')
                self.assertEqual((self.root / 'operations-status.json').read_bytes(), original)
                self.assertNotIn('sensitive', json.dumps(result))

    def test_fresh_verified_paper_retains_count_and_requires_resolution(self):
        self.prepare()
        sample = acceptance()
        sample['paper'] = {'status': 'verified_unresolved', 'positions': 2,
                           'ledger_reviewed_at': '2026-11-07T22:00:00Z'}
        self.write('acceptance.json', sample)
        result = self.collect()
        self.assertEqual(result['state'], 'blocked')
        self.assertEqual(result['review']['paper']['positions'], 2)
        self.assertEqual(result['next_action'], 'resolve_paper_ledger')

    def test_retention_removes_only_old_valid_derived_daily_receipts(self):
        self.prepare()
        self.collect()
        daily = self.root / 'daily'
        old = json.loads((daily / '2026-11-07.json').read_text())
        old['date'] = '2026-09-01'
        old['collected_at'] = '2026-09-01T22:00:00Z'
        old['read_at'] = '2026-09-01T22:00:00Z'
        old['review']['reviewed_at'] = '2026-09-01T22:00:00Z'
        old['watchdog']['checked_at'] = '2026-09-01T22:00:00Z'
        (daily / '2026-09-01.json').write_text(json.dumps(old))
        (daily / '2026-09-01.json').chmod(0o600)
        (daily / '2026-08-01.json').write_text('{"keep":"source"}')
        (daily / '2026-08-01.json').chmod(0o600)
        malformed = dict(old, date='2026-07-01', review={'not': 'derived evidence'})
        (daily / '2026-07-01.json').write_text(json.dumps(malformed))
        (daily / '2026-07-01.json').chmod(0o600)
        (daily / '2026-06-01.json').write_text('[]')
        (daily / '2026-06-01.json').chmod(0o600)
        (daily / 'acceptance.json').write_text('preserve')
        self.collect()
        self.assertFalse((daily / '2026-09-01.json').exists())
        self.assertTrue((daily / '2026-08-01.json').exists())
        self.assertTrue((daily / '2026-07-01.json').exists())
        self.assertTrue((daily / '2026-06-01.json').exists())
        self.assertTrue((daily / 'acceptance.json').exists())
        self.assertTrue((self.root / 'acceptance.json').exists())

    def test_runtime_clock_failure_during_collection_is_unknown(self):
        self.prepare()
        counter = iter([NOW, OSError('private')])
        def clock():
            value = next(counter)
            if isinstance(value, Exception):
                raise value
            return value
        result = receipt.collect(self.root, clock=clock)
        self.assertEqual(result['state'], 'unknown')
        self.assertFalse((self.root / 'operations-status.json').exists())

    def test_source_native_runtime_acceptance_does_not_grant_capabilities(self):
        self.prepare()
        sample = acceptance()
        for task in sample['tasks'].values():
            task.update(source='accepted', native='accepted', runtime='accepted')
        sample['paper'] = {'status': 'verified_none', 'positions': 0,
                           'ledger_reviewed_at': '2026-11-07T22:00:00Z'}
        self.write('acceptance.json', sample)
        result = self.collect()
        self.assertEqual(result['summary']['tasks']['accepted'], 4)
        self.assertEqual(result['state'], 'reviewed')
        self.assertFalse(any(result['capabilities'].values()))
        self.assertEqual(result['next_action'], 'none')

    def test_watchdog_healthy_requires_complete_availability_and_identity_evidence(self):
        self.prepare()
        for field, value in [('checks', {}), ('identity', {'state': 'matched'}),
                             ('checks', {'frontend': {'state': 'ok'}})]:
            sample = watchdog()
            sample[field] = value
            self.write('status.json', sample)
            self.assertEqual(self.collect()['watchdog']['state'], 'unknown')

    def test_old_ledger_does_not_become_current_when_review_is_refreshed(self):
        self.prepare()
        sample = acceptance()
        sample['paper'] = {'status': 'verified_unresolved', 'positions': 2,
                           'ledger_reviewed_at': '2026-11-05T22:00:00Z'}
        self.write('acceptance.json', sample)
        result = self.collect()
        self.assertEqual(result['paper_effective']['status'], 'unknown')
        self.assertIsNone(result['paper_effective']['positions'])
        self.assertEqual(result['review']['paper']['positions'], 2)

    def test_task_scopes_and_metrics_are_historical_and_not_capabilities(self):
        self.prepare()
        sample = acceptance()
        sample['counters'].update(accepted_outputs=6, interventions=2, first_pass_accepted=4)
        sample['cost_usd'] = 3
        self.write('acceptance.json', sample)
        result = self.collect()
        self.assertEqual(result['task_scopes']['coding'], 'fixed arithmetic fixture')
        self.assertEqual(result['review']['counter_scope'], 'last_integrator_review')
        self.assertEqual(result['metrics']['accepted_outputs_per_intervention'], 3)
        self.assertEqual(result['metrics']['accepted_outputs_per_usd'], 2)
        sample['cost_usd'] = 0
        sample['counters']['interventions'] = 0
        self.write('acceptance.json', sample)
        result = self.collect()
        self.assertIsNone(result['metrics']['accepted_outputs_per_intervention'])
        self.assertIsNone(result['metrics']['accepted_outputs_per_usd'])

    def test_saved_unknown_review_cannot_echo_arbitrary_context(self):
        self.prepare()
        self.collect()
        target = self.root / 'operations-status.json'
        sample = json.loads(target.read_text())
        sample['review']['secret'] = 'SENSITIVE'
        self.write(target.name, sample)
        result = receipt.status(self.root, clock=self.clock)
        self.assertEqual(result['state'], 'unknown')
        self.assertNotIn('SENSITIVE', json.dumps(result))

    def test_cross_process_lease_refuses_cli_collection_without_waiting(self):
        self.prepare()
        lock = os.open(self.root / 'receipt.lock', os.O_RDWR)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            started = time.monotonic()
            run = subprocess.run([sys.executable, str(SCRIPT), '--state-dir', str(self.root), 'collect'],
                                 capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 4)
            self.assertEqual(json.loads(run.stdout)['state'], 'busy')
            self.assertLess(time.monotonic() - started, 1)
        finally:
            os.close(lock)

    def test_cli_deadline_returns_closed_unknown_without_retry(self):
        program = ("import sys,time;sys.path.insert(0,sys.argv[1]);import operations_receipt as r;"
                   "r.collect=lambda _:time.sleep(20);raise SystemExit(r.main(['collect']))")
        started = time.monotonic()
        run = subprocess.run([sys.executable, '-c', program, str(OPS)], capture_output=True, text=True, timeout=5)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stdout)['state'], 'unknown')
        self.assertLess(time.monotonic() - started, 5)

    def test_cli_deadline_escapes_inner_input_error_handlers(self):
        self.prepare()
        program = ("import sys,time;sys.path.insert(0,sys.argv[1]);import operations_receipt as r;"
                   "original=r._read;"
                   "r._read=lambda d,n:(time.sleep(20) if n in ('acceptance.json','status.json') else None) or original(d,n);"
                   "raise SystemExit(r.main(['--state-dir',sys.argv[2],'collect']))")
        started = time.monotonic()
        run = subprocess.run([sys.executable, '-c', program, str(OPS), str(self.root)],
                             capture_output=True, text=True, timeout=5)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stdout)['reason'], 'receipt_deadline_exceeded')
        self.assertLess(time.monotonic() - started, 5)

    def test_tiny_finite_cost_does_not_create_nonfinite_derived_metric(self):
        self.prepare()
        sample = acceptance()
        sample['cost_usd'] = 1e-320
        sample['counters']['accepted_outputs'] = 100
        self.write('acceptance.json', sample)
        result = self.collect()
        self.assertIn('metrics', result)
        self.assertIsNone(result['metrics']['accepted_outputs_per_usd'])
        json.dumps(result, allow_nan=False)

    def test_unknown_availability_cannot_yield_success_from_reviewed_stages(self):
        self.prepare()
        sample = acceptance()
        for task in sample['tasks'].values():
            task.update(source='accepted', native='accepted', runtime='accepted')
        sample['paper'] = {'status': 'verified_none', 'positions': 0,
                           'ledger_reviewed_at': '2026-11-07T22:00:00Z'}
        self.write('acceptance.json', sample)
        (self.root / 'status.json').unlink()
        result = self.collect()
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(result['next_action'], 'inspect_local_availability')

    def test_status_malformed_receipt_never_trusts_saved_capabilities(self):
        self.write('operations-status.json', {'schema': 'floww-operations-receipt.v1',
                                             'capabilities': {'execution': True}})
        result = receipt.status(self.root, clock=self.clock)
        self.assertEqual(result['state'], 'unknown')
        self.assertFalse(any(result['capabilities'].values()))


if __name__ == '__main__':
    unittest.main()
