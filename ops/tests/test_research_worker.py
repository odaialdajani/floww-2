"""No live network: bounded producers, native wire and durable orchestration."""
import copy
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS))
import research_intake as intake  # noqa: E402


def fixture():
    return {'columns': list(intake.COLUMNS), 'rows': [
        ['SPY', 'SPY261110C00655000', 'call', 655, '2026-11-10', 255, 1, .7421, .9581, 736.51]],
        'source': 'public-scan-observations', 'live': False, 'trade_eligible': False,
        'count': 1, 'total': 1, 'offset': 0, 'limit': 3, 'next_offset': None,
        'quote_truth': {'SPY|call|655|2026-11-10': {'bid': 80.04, 'ask': 82.73,
            'bid_source_time': 1793999698, 'ask_source_time': 1793999699}},
        'row_observations': {'SPY|call|655|2026-11-10': {'received_at': 1794077218,
            'quote_source_time': 1793999698, 'bid_source_time': 1793999698,
            'ask_source_time': 1793999699, 'source': 'public_api', 'scope': 'saved:test', 'data_status': 'partial'}},
        'observations_by_ticker': {'SPY': {'source': 'public_api', 'scope': 'saved:test'}}, 'coverage': {}}


def response(packet):
    obs = packet['observations'][0]
    return {'packet_id': packet['packet_id'], 'status': 'review_only', 'executable': False,
            'scope': 'internal_research', 'claims': [{'observation_id': obs['observation_id'],
             'field': 'bid', 'value': obs['fields']['bid']['value'], 'unit': 'unspecified_source_units',
             'citations': [{'observation_id': obs['observation_id'], 'field': 'bid'}]}]}


class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global worker
        import research_worker as worker

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name).resolve() / 'state'
        self.admission = self.state.parent / 'shared-admission'
        patcher = mock.patch.object(worker, 'ADMISSION_STATE', self.admission, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        worker.set_paused(self.state, False)
        self.calls = []

    def role(self, role, packet, state):
        self.calls.append((role, copy.deepcopy(packet)))
        return {'success': True, 'response': response(packet), 'http_request_count': 1,
                'blocked_http_attempt_count': 0, 'native_valid_tool_names': [], 'cost_usd': None,
                'cost_status': 'unknown', 'usage': {'output_tokens': 200}}

    def run_worker(self, saved=None, runner=None, now=1794085822):
        return worker.run_once(self.state, saved=fixture() if saved is None else saved,
                               role_runner=runner or self.role, now=now)

    def test_minimal_role_view_preserves_selected_bid_identity_and_clocks(self):
        full = intake.compile_snapshot(fixture(), 1794085822)
        original = copy.deepcopy(full)
        view = worker.role_view(full)
        self.assertEqual(full, original)
        self.assertEqual(set(view), {'packet_id', 'source', 'decision_time', 'observations'})
        self.assertEqual(view['packet_id'], full['packet_id'])
        self.assertEqual(view['source'], full['source'])
        self.assertEqual(view['decision_time'], full['decision_time'])
        for index, actual in enumerate(view['observations']):
            expected = full['observations'][index]
            self.assertEqual(set(actual), {'observation_id', 'contract_id', 'provider', 'scope', 'fields', 'clocks'})
            for name in ('observation_id', 'contract_id', 'provider', 'scope'):
                self.assertEqual(actual[name], expected[name])
            self.assertEqual(actual['fields'], {'bid': expected['fields']['bid']})
            self.assertEqual(actual['clocks'], {k: expected['clocks'][k] for k in ('received_at', 'bid_source_time')})
        self.assertLess(len(worker.canonical(view)), len(worker.canonical(full)) / 2)
        self.run_worker()
        self.assertEqual(self.calls[0][1], view)
        self.assertEqual(self.calls[0][1], self.calls[1][1])
        self.assertTrue(intake.validate_research(full, response(view))['accepted'])

    def test_minimal_view_labels_missing_bid_and_clock_without_inference(self):
        saved = fixture()
        saved['quote_truth']['SPY|call|655|2026-11-10'].pop('bid')
        saved['quote_truth']['SPY|call|655|2026-11-10'].pop('bid_source_time')
        saved['row_observations']['SPY|call|655|2026-11-10'].pop('bid_source_time')
        self.run_worker(saved=saved)
        obs = self.calls[0][1]['observations'][0]
        self.assertEqual(obs['fields']['bid']['status'], 'missing')
        self.assertIsNone(obs['fields']['bid']['value'])
        self.assertEqual(obs['clocks']['bid_source_time']['knowledge'], 'unknown')
        self.assertIsNone(obs['clocks']['bid_source_time']['value'])

    def test_role_view_caps_six_observations_and_rejects_hidden_fact_claims(self):
        saved = fixture()
        saved['rows'] = []
        for symbol in ('SPY', 'QQQ'):
            for strike in (655, 656, 657):
                row = fixture()['rows'][0][:]
                row[0], row[1], row[3] = symbol, symbol + '261110C' + str(strike * 1000).zfill(8), strike
                saved['rows'].append(row)
                key = symbol + '|call|' + str(strike) + '|2026-11-10'
                saved['quote_truth'][key] = copy.deepcopy(fixture()['quote_truth']['SPY|call|655|2026-11-10'])
                saved['row_observations'][key] = copy.deepcopy(fixture()['row_observations']['SPY|call|655|2026-11-10'])
            saved['observations_by_ticker'][symbol] = {'source': 'public_api', 'scope': 'saved:test'}
        saved['count'] = 6
        full = worker.compile_pages([saved], 1794085822)
        self.assertEqual(len(full['observations']), 6)
        def hidden(role, packet, state):
            result = self.role(role, packet, state)
            result['response'] = response({**full, 'observations': full['observations'][3:]})
            return result
        result = self.run_worker(saved=saved, runner=hidden)
        self.assertEqual(len(self.calls[0][1]['observations']), 3)
        self.assertEqual(result['roles']['research']['validation']['reason'], 'role_view_claim_refused')

    def test_closed_validation_rejects_altered_bid_unit_identity_and_citation(self):
        full = intake.compile_snapshot(fixture(), 1794085822)
        view = worker.role_view(full)
        for key, value in (('value', '80.05'), ('unit', 'USD'), ('observation_id', 'invented'),
                           ('citations', [{'observation_id': view['observations'][0]['observation_id'], 'field': 'ask'}])):
            with self.subTest(key=key):
                altered = response(view)
                altered['claims'][0][key] = value
                self.assertFalse(intake.validate_research(full, altered)['accepted'])
        view['observations'][0]['fields']['bid']['value'] = '999'
        self.assertEqual(full['observations'][0]['fields']['bid']['value'], '80.04')
        self.assertFalse(intake.validate_research(full, response(view))['accepted'])

    def changed(self, offset):
        saved = fixture()
        saved['quote_truth']['SPY|call|655|2026-11-10']['bid'] += offset
        return saved

    def test_global_daily_budget_survives_restart_and_different_state_directories(self):
        for index in range(4):
            state = self.state.parent / ('worker_' + str(index))
            worker.set_paused(state, False)
            result = worker.run_once(state, saved=self.changed(index), role_runner=self.role, now=1794085822)
            self.assertEqual(result['status'], 'accepted_retrospective_facts')
        result = self.run_worker(saved=self.changed(4))
        self.assertEqual(result['reason'], 'daily_pair_budget_exhausted')
        self.assertEqual(len(self.calls), 8)

    def test_failure_parks_changed_inputs_until_explicit_global_resume(self):
        def failed(role, packet, state):
            result = self.role(role, packet, state)
            result['success'] = False
            return result
        self.assertEqual(self.run_worker(runner=failed)['status'], 'parked')
        worker.set_paused(self.state, False)
        self.assertEqual(self.run_worker(saved=self.changed(1))['reason'], 'native_circuit_parked')
        self.assertEqual(len(self.calls), 2)
        worker.resume_circuit()
        self.assertEqual(self.run_worker(saved=self.changed(1))['status'], 'accepted_retrospective_facts')

    def test_global_dedupe_survives_local_receipt_removal(self):
        first = self.run_worker()
        (self.state / 'receipts' / (first['input_key'] + '.json')).unlink()
        result = self.run_worker()
        self.assertEqual(result['status'], 'duplicate_no_call')
        self.assertEqual(len(self.calls), 2)

    def test_shared_admission_lease_refuses_concurrent_state_directories(self):
        with worker.Lease(self.admission):
            result = self.run_worker()
        self.assertEqual(result['status'], 'busy')
        self.assertEqual(len(self.calls), 0)

    def test_interrupted_pair_circuits_new_input_without_replay(self):
        def crash(role, packet, state):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.run_worker(runner=crash)
        result = self.run_worker(saved=self.changed(1))
        self.assertEqual(result['reason'], 'native_circuit_parked')
        self.assertEqual(len(self.calls), 0)

    def test_budget_rollover_keeps_global_dedupe_and_configured_lower_limit(self):
        first = self.run_worker()
        ledger = worker.parse_json(worker.read_bytes(self.admission / 'admission.json'))
        ledger['daily_pair_limit'] = 1
        worker.atomic_json(self.admission / 'admission.json', ledger)
        self.assertEqual(self.run_worker(saved=self.changed(1))['reason'], 'daily_pair_budget_exhausted')
        self.assertEqual(self.run_worker(saved=self.changed(1), now=1794172222)['status'], 'accepted_retrospective_facts')
        (self.state / 'receipts' / (first['input_key'] + '.json')).unlink()
        self.assertEqual(self.run_worker(now=1794172222)['status'], 'duplicate_no_call')
        self.assertEqual(len(self.calls), 4)

    def test_invalid_budget_and_admission_capacity_never_release_dedupe(self):
        self.run_worker()
        ledger = worker.parse_json(worker.read_bytes(self.admission / 'admission.json'))
        ledger['daily_pair_limit'] = 5
        worker.atomic_json(self.admission / 'admission.json', ledger)
        with self.assertRaises(worker.WorkerError):
            self.run_worker(saved=self.changed(1))
        ledger['daily_pair_limit'] = 4
        worker.atomic_json(self.admission / 'admission.json', ledger)
        with mock.patch.object(worker, 'MAX_ADMISSIONS', 1):
            result = self.run_worker(saved=self.changed(1))
        self.assertEqual(result['reason'], 'admission_capacity_manual_review_required')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(worker.admission_ledger()['attempts']), 1)

    def test_failure_circuit_is_shared_and_does_not_expire_at_midnight(self):
        def failed(role, packet, state):
            result = self.role(role, packet, state)
            result['success'] = False
            return result
        self.run_worker(runner=failed)
        other = self.state.parent / 'different-worker'
        worker.set_paused(other, False)
        result = worker.run_once(other, saved=self.changed(1), role_runner=self.role, now=1794172222)
        self.assertEqual(result['reason'], 'native_circuit_parked')
        self.assertEqual(len(self.calls), 2)
        worker.resume_circuit()
        self.assertEqual(len(worker.admission_ledger()['attempts']), 1)

    def test_shared_lease_replacement_blocks_second_role_and_preserves_crash_reservation(self):
        def replace_lock(role, packet, state):
            result = self.role(role, packet, state)
            (self.admission / 'worker.lock').unlink()
            (self.admission / 'worker.lock').touch(mode=0o600)
            return result
        with self.assertRaises(worker.WorkerError) as caught:
            self.run_worker(runner=replace_lock)
        self.assertEqual(str(caught.exception), 'lease_identity_changed')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.run_worker(saved=self.changed(1))['reason'], 'native_circuit_parked')

    def test_state_aliases_cannot_bypass_fixed_shared_admission(self):
        self.run_worker()
        for state in (self.state.parent / 'sibling', self.state.parent / 'unused' / '..' / 'alias'):
            worker.set_paused(state, False)
            result = worker.run_once(state, saved=fixture(), role_runner=self.role, now=1794085822)
            self.assertEqual(result['status'], 'duplicate_no_call')
        self.assertEqual(len(self.calls), 2)

    def test_shared_admission_rejects_symlink_and_hardlinked_lock_or_ledger(self):
        self.admission.mkdir(mode=0o700)
        other = self.state.parent / 'other-admission'
        other.symlink_to(self.admission, target_is_directory=True)
        with mock.patch.object(worker, 'ADMISSION_STATE', other), self.assertRaises(worker.WorkerError):
            self.run_worker()
        import os
        target = self.admission / 'original'
        target.write_text('{}')
        for name in ('worker.lock', 'admission.json'):
            with self.subTest(name=name):
                os.link(target, self.admission / name)
                with self.assertRaises(worker.WorkerError):
                    self.run_worker()
                (self.admission / name).unlink()
        self.assertEqual(len(self.calls), 0)

    def test_each_page_source_envelope_and_metadata_are_admitted_before_combining(self):
        qqq = json.loads(json.dumps(fixture()).replace('SPY', 'QQQ'))
        invalid = [('source', 'public-scan'), ('live', True), ('trade_eligible', True),
                   ('count', 999), ('count', True), ('count', 1.0), ('columns', []),
                   ('quote_truth', []), ('row_observations', []), ('observations_by_ticker', []),
                   ('coverage', {'stored_tickers': -1}), ('offset', -1)]
        for index, (field, value) in enumerate(invalid):
            with self.subTest(field=field, value=value):
                bad = copy.deepcopy(fixture())
                bad[field] = value
                for pages in ([bad], [bad, qqq], [qqq, bad]):
                    state = self.state / ('case_' + str(index) + '_' + str(len(pages)) + '_' + str(pages[0]['rows'][0][0]))
                    worker.set_paused(state, False)
                    result = worker.run_once(state, producer=lambda pages=pages: pages, role_runner=self.role, now=1794085822)
                    self.assertEqual(result['status'], 'parked')
        self.assertEqual(len(self.calls), 0)

    def test_valid_two_symbol_pages_are_independently_admitted_and_remain_review_only(self):
        qqq = json.loads(json.dumps(fixture()).replace('SPY', 'QQQ'))
        result = worker.run_once(self.state, producer=lambda: [fixture(), qqq],
                                 role_runner=self.role, now=1794085822)
        self.assertEqual(result['status'], 'accepted_retrospective_facts')
        self.assertFalse(result['executable'])
        self.assertEqual(len(self.calls[0][1]['observations']), 2)

    def test_explicit_native_failure_overrides_valid_facts_and_success_flag(self):
        def failed(role, packet, state):
            result = self.role(role, packet, state)
            result.update(native_failed=True, http_status=200, finish_reason='stop')
            return result
        result = self.run_worker(runner=failed)
        self.assertEqual(result['status'], 'parked')
        for role in result['roles'].values():
            self.assertTrue(role['native_failed'])
            self.assertFalse(role['validation']['accepted'])

    def test_startup_input_is_nonblocking_and_deadline_supervised(self):
        started = time.monotonic()
        with self.assertRaises(worker.WorkerError) as caught:
            worker.bounded_process([sys.executable, '-c', 'import time; time.sleep(.8)'],
                                   b'x' * (128 * 1024), timeout=.1)
        self.assertEqual(str(caught.exception), 'role_deadline')
        self.assertLess(time.monotonic() - started, .5)

    def test_startup_broken_pipe_is_a_stable_refusal_and_kills_descendants(self):
        command = [sys.executable, '-c',
                   'import os,time; os.close(0); pid=os.fork(); time.sleep(10) if pid==0 else os._exit(0)']
        started = time.monotonic()
        with self.assertRaises(worker.WorkerError) as caught:
            worker.bounded_process(command, b'x' * (128 * 1024), timeout=.5)
        self.assertEqual(str(caught.exception), 'role_stdin_closed')
        self.assertLess(time.monotonic() - started, 2)

    def test_every_persisted_terminal_path_records_actual_finish_clock(self):
        for kind in ('producer_failure', 'duplicate', 'capacity'):
            with self.subTest(kind=kind):
                state = self.state / kind
                worker.set_paused(state, False)
                if kind == 'duplicate':
                    worker.run_once(state, saved=fixture(), role_runner=self.role, now=1794085822)
                self.calls.clear()
                def producer(kind=kind):
                    if kind == 'producer_failure':
                        raise worker.WorkerError('saved_deadline')
                    return [fixture()]
                start, end = 1794085822, 1794085828
                with mock.patch.object(worker.time, 'time', side_effect=[start, end]), \
                        mock.patch.object(worker, 'MAX_RECEIPTS', 0 if kind == 'capacity' else 512):
                    result = worker.run_once(state, producer=producer, role_runner=self.role)
                self.assertEqual(result['started_at'], start)
                self.assertEqual(result['finished_at'], end)
                daily = json.loads(next((state / 'daily').glob('*.json')).read_text())
                self.assertEqual(daily['updated_at'], end)
                self.assertEqual(len(self.calls), 0)

    def test_real_clock_records_finish_and_daily_progress_after_long_role_pair(self):
        started, finished = 1794085822, 1794085883.697
        with mock.patch.object(worker.time, 'time', side_effect=[started, finished]):
            result = worker.run_once(self.state, saved=fixture(), role_runner=self.role)
        self.assertEqual(result['started_at'], started)
        self.assertEqual(result['finished_at'], finished)
        daily = json.loads(next((self.state / 'daily').glob('*.json')).read_text())
        self.assertEqual(daily['updated_at'], finished)
        self.assertEqual(daily['last_substantive_progress'], finished)

    def test_independent_roles_receive_identical_packet_without_other_answer(self):
        result = self.run_worker()
        self.assertEqual(result['status'], 'accepted_retrospective_facts')
        self.assertEqual([x[0] for x in self.calls], ['research', 'audit'])
        self.assertEqual(self.calls[0][1], self.calls[1][1])
        self.assertFalse(result['executable'])
        self.assertEqual(result['roles']['research']['validation']['claims'][0]['freshness'], 'stale')
        self.assertIsNone(result['cost_usd'])
        self.assertEqual(result['native_task_status'], 'blocked_pending_independent_acceptance')

    def test_polltime_and_precomputed_ages_do_not_spend_again_after_restart(self):
        first = self.run_worker()
        saved = fixture()
        saved['checked_at'] = 1794085999
        saved['row_observations']['SPY|call|655|2026-11-10']['receipt_age_seconds'] = 999
        second = self.run_worker(saved=saved, now=1794086000)
        self.assertEqual(second['status'], 'duplicate_no_call')
        self.assertEqual(first['input_key'], second['input_key'])
        self.assertEqual(len(self.calls), 2)

    def test_rule_hash_changes_identity_and_decision_packet_id_does_not(self):
        a = intake.compile_snapshot(fixture(), 1794085822)
        b = intake.compile_snapshot(fixture(), 1794085922)
        self.assertNotEqual(a['packet_id'], b['packet_id'])
        self.assertEqual(worker.input_key(a), worker.input_key(b))
        self.assertNotEqual(worker.input_key(a), worker.input_key(a, rule_hash='different'))

    def test_offline_replay_can_never_be_accepted_as_a_real_role(self):
        def fake(role, packet, state):
            result = self.role(role, packet, state)
            result['offline_replay'] = True
            return result
        self.assertEqual(self.run_worker(runner=fake)['status'], 'parked')

    def test_unknown_failure_parks_same_input_and_audit_does_not_consume_answer(self):
        def refused(role, packet, state):
            result = self.role(role, packet, state)
            if role == 'research':
                result['response']['claims'][0]['value'] = '1'
            return result
        result = self.run_worker(runner=refused)
        self.assertEqual(result['status'], 'parked')
        self.assertEqual(result['roles']['research']['validation']['reason'], 'numeric_mismatch')
        self.assertEqual(self.run_worker()['status'], 'duplicate_no_call')
        self.assertEqual(len(self.calls), 2)

    def test_crash_marker_is_a_permanent_no_retry_record(self):
        packet = intake.compile_snapshot(fixture(), 1794085822)
        key = worker.input_key(packet)
        worker.atomic_json(self.state / 'receipts' / (key + '.json'), {'status': 'started', 'input_key': key})
        result = self.run_worker()
        self.assertEqual(result['status'], 'duplicate_no_call')
        self.assertEqual(result['previous_status'], 'started')
        self.assertEqual(len(self.calls), 0)

    def test_pause_before_producer_and_pause_between_roles(self):
        worker.set_paused(self.state, True)
        self.assertEqual(worker.run_once(self.state, producer=lambda: self.fail('producer called'))['status'], 'paused')
        worker.set_paused(self.state, False)
        def pause(role, packet, state):
            result = self.role(role, packet, state)
            worker.set_paused(state, True)
            return result
        self.assertEqual(self.run_worker(runner=pause)['status'], 'parked')
        self.assertEqual(len(self.calls), 1)

    def test_lease_excludes_second_owner(self):
        with worker.Lease(self.state):
            self.assertEqual(self.run_worker()['status'], 'busy')
        self.assertEqual(len(self.calls), 0)

    def test_default_state_is_paused_and_status_is_model_free(self):
        other = self.state.parent / 'other'
        self.assertEqual(worker.status(other)['status'], 'paused')
        self.assertEqual(worker.run_once(other, producer=lambda: self.fail('producer called'))['status'], 'paused')

    def test_empty_future_or_unapproved_ticker_produces_no_model_calls(self):
        for mutate in ('empty', 'future', 'ticker'):
            saved = fixture()
            if mutate == 'empty':
                saved['rows'], saved['count'] = [], 0
            elif mutate == 'future':
                saved['row_observations']['SPY|call|655|2026-11-10']['received_at'] = 1894085822
            else:
                saved['rows'][0][0] = 'AAPL'
            result = self.run_worker(saved=saved)
            self.assertEqual(result['status'], 'parked')
        self.assertEqual(len(self.calls), 0)

    def test_receipts_are_private_atomic_and_local_daily_scope_is_explicit(self):
        result = self.run_worker()
        receipt = self.state / 'receipts' / (result['input_key'] + '.json')
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        daily = json.loads(next((self.state / 'daily').glob('*.json')).read_text())
        self.assertEqual(daily['scope'], 'saved_research_worker_only')
        self.assertEqual(daily['unresolved_paper_positions'], 'not_observed_by_this_worker')
        self.assertEqual(daily['accepted_pairs'], 1)
        self.assertEqual(daily['cost_status'], 'unknown')
        self.assertFalse(list(self.state.rglob('*.tmp')))

    def test_symlink_state_and_receipt_refuse(self):
        link = self.state.parent / 'link'
        link.symlink_to(self.state, target_is_directory=True)
        with self.assertRaises(worker.WorkerError):
            worker.set_paused(link, False)
        packet = intake.compile_snapshot(fixture(), 1794085822)
        target = self.state / 'receipts' / (worker.input_key(packet) + '.json')
        target.parent.mkdir(mode=0o700, exist_ok=True)
        target.symlink_to(self.state / 'control.json')
        with self.assertRaises(worker.WorkerError):
            self.run_worker()

    def test_bounded_child_kills_hanging_group_and_discards_oversized_output(self):
        for command, code in (([sys.executable, '-c', 'import time; time.sleep(20)'], 'role_deadline'),
                              ([sys.executable, '-c', 'print("x" * 200000)'], 'role_output_limit')):
            started = time.monotonic()
            with self.assertRaises(worker.WorkerError) as caught:
                worker.bounded_process(command, b'', timeout=.25, output_limit=1024)
            self.assertEqual(str(caught.exception), code)
            self.assertLess(time.monotonic() - started, 3)

    def test_deadline_also_kills_descendant_when_group_leader_exits(self):
        command = [sys.executable, '-c',
                   'import os,time; pid=os.fork(); time.sleep(10) if pid==0 else os._exit(0)']
        started = time.monotonic()
        with self.assertRaises(worker.WorkerError) as caught:
            worker.bounded_process(command, b'', timeout=.25)
        self.assertEqual(str(caught.exception), 'role_deadline')
        self.assertLess(time.monotonic() - started, 3)

    def test_row_cap_and_missing_source_clock_do_not_become_a_fresh_signal(self):
        saved = fixture()
        saved['rows'] *= 4
        saved['count'] = 4
        self.assertEqual(self.run_worker(saved=saved)['reason'], 'saved_row_limit')
        saved = fixture()
        result = self.run_worker(saved=saved)
        packet = self.calls[0][1]
        self.assertEqual(packet['observations'][0]['clocks']['bid_source_time']['freshness'], 'stale')
        self.assertEqual(result['roles']['audit']['validation']['claims'][0]['freshness'], 'stale')

    def test_child_group_memory_cap_is_observed_and_terminated(self):
        with self.assertRaises(worker.WorkerError) as caught:
            worker.bounded_process([sys.executable, '-c',
                'import time; x=bytearray(80*1024*1024); time.sleep(10)'], b'', timeout=3,
                memory_limit=48*1024*1024)
        self.assertEqual(str(caught.exception), 'role_memory_limit')

    def test_producer_rejects_oversize_body_and_redirect_without_following(self):
        for response_status, payload, expected in ((302, b'', 'saved_endpoint_unavailable'),
                (200, b'x' * (worker.MAX_BODY + 1), 'saved_body_limit')):
            class Response:
                status = response_status
                pending = payload
                def getheader(self, name, default=None):
                    return 'application/json'
                def read1(self, count):
                    result, self.pending = self.pending[:count], self.pending[count:]
                    return result
            class Conn:
                def __init__(self, *args, **kwargs): pass
                def request(self, *args, **kwargs): pass
                def getresponse(self): return Response()
                def close(self): pass
            with self.assertRaises(worker.WorkerError) as caught:
                worker.fetch_saved(('SPY',), connection_factory=Conn)
            self.assertEqual(str(caught.exception), expected)

    def test_producer_is_only_two_literal_saved_gets_with_body_and_symbol_caps(self):
        seen = []
        class Response:
            status = 200
            def getheader(self, name, default=None): return 'application/json' if name.lower() == 'content-type' else default
            pending = json.dumps(fixture()).encode()
            def read1(self, count):
                result, self.pending = self.pending[:count], self.pending[count:]
                return result
        class Conn:
            def __init__(self, host, port, timeout): seen.append((host, port, timeout))
            def request(self, method, path, headers): seen.append((method, path))
            def getresponse(self): return Response()
            def close(self): pass
        pages = worker.fetch_saved(('SPY',), connection_factory=Conn)
        self.assertEqual(len(pages), 1)
        self.assertEqual(seen[1], ('GET', '/api/flowseeker/scan-public/observations?ticker=SPY&limit=3&order=received'))
        with self.assertRaises(worker.WorkerError):
            worker.fetch_saved(('AAPL',), connection_factory=Conn)
        with self.assertRaises(worker.WorkerError):
            worker.fetch_saved(('SPY', 'SPY'), connection_factory=Conn)


class WireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global native, worker
        import research_native_role as native
        import research_worker as worker

    def request(self, **extra):
        result = {'model': native.MODEL, 'max_tokens': 1024, 'messages': [
            {'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'packet'}]}
        result.update(extra)
        return result

    def test_actual_admitted_wire_size_is_safe_numeric_metadata(self):
        guard = native.WireGuard('test-secret', self.request()['messages'])
        guard.phase = 'run'
        body = json.dumps(self.request()).encode()
        guard.admit(native.ENDPOINT, 'POST', body)
        self.assertEqual(guard.request_body_bytes, len(body))
        self.assertEqual(guard.message_characters, len('systempacket'))

    def test_wire_rejects_secret_tools_endpoint_caps_and_additional_requests(self):
        guard = native.WireGuard('test-secret', self.request()['messages'])
        guard.phase = 'run'
        for url, method, body in ((native.ENDPOINT + '/x', 'POST', self.request()),
                                  (native.ENDPOINT, 'GET', self.request()),
                                  (native.ENDPOINT, 'POST', self.request(max_tokens=1025)),
                                  (native.ENDPOINT, 'POST', self.request(tools=[{'type': 'function'}])),
                                  (native.ENDPOINT, 'POST', self.request(model='other')),
                                  (native.ENDPOINT, 'POST', self.request(messages=[{'role': 'user', 'content': 'test-secret'}]))):
            with self.assertRaises(native.NativeError):
                guard.admit(url, method, json.dumps(body).encode())
        guard = native.WireGuard('test-secret', self.request()['messages'])
        guard.phase = 'run'
        guard.admit(native.ENDPOINT, 'POST', json.dumps(self.request()).encode())
        with self.assertRaises(native.NativeError):
            guard.admit(native.ENDPOINT, 'POST', json.dumps(self.request()).encode())
        self.assertEqual(guard.requests, 1)

    def test_guard_requires_exact_parent_messages_not_native_personal_context(self):
        guard = native.WireGuard('test-secret', self.request()['messages'])
        guard.phase = 'run'
        body = self.request()
        body['messages'].insert(1, {'role': 'system', 'content': 'private history'})
        with self.assertRaises(native.NativeError):
            guard.admit(native.ENDPOINT, 'POST', json.dumps(body).encode())
        self.assertEqual(guard.requests, 0)

    def test_native_full_conversation_offline_replay_has_one_bounded_fake_request(self):
        packet = intake.compile_snapshot(fixture(), 1794085822)
        with tempfile.TemporaryDirectory(dir='/Users/nav') as folder:
            state = Path(folder) / 'state'
            worker.set_paused(state, False)
            profile = worker.HERMES_ROOT / 'profiles/floww-research'
            before = (profile / 'ESTOP').read_bytes()
            with worker.Lease(profile / '.floww-saved-research-lease'):
                result = worker._run_native_role_held('research', packet, state, offline_replay=True)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['http_request_count'], 1)
        self.assertEqual(result['blocked_http_attempt_count'], 0)
        self.assertTrue(result['offline_replay'])
        self.assertTrue(intake.validate_research(packet, result['response'])['accepted'])
        self.assertEqual(before, (profile / 'ESTOP').read_bytes())

    def test_native_offline_timeout_and_rate_limit_keep_safe_distinct_diagnostics(self):
        packet = intake.compile_snapshot(fixture(), 1794085822)
        for fault in ('timeout', 'rate_limit'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(dir='/Users/nav') as folder:
                state = Path(folder) / 'state'
                worker.set_paused(state, False)
                profile = worker.HERMES_ROOT / 'profiles/floww-research'
                before = (profile / 'ESTOP').read_bytes()
                with worker.Lease(profile / '.floww-saved-research-lease'):
                    result = worker._run_native_role_held('research', packet, state,
                        offline_replay=True, offline_fault=fault)
            self.assertFalse(result['success'])
            self.assertEqual(result['http_request_count'], 1)
            self.assertEqual(result['cost_status'], 'unknown')
            if fault == 'timeout':
                self.assertEqual(result['transport_error_type'], 'ReadTimeout')
                self.assertIsNone(result['http_status'])
            else:
                self.assertEqual(result['http_status'], 429)
                self.assertIsNone(result['transport_error_type'])
            if result['blocked_http_attempt_count']:
                self.assertTrue(result['blocked_origins'])
            serialized = json.dumps(result)
            self.assertNotIn('offline-fixture-secret', serialized)
            self.assertNotIn('Authorization', serialized)
            self.assertNotIn('Packet:', serialized)
            self.assertEqual(before, (profile / 'ESTOP').read_bytes())

    def test_premature_wire_attempt_is_refused_without_consuming_quota(self):
        guard = native.WireGuard('test-secret', self.request()['messages'])
        with self.assertRaises(native.NativeError):
            guard.admit(native.ENDPOINT, 'POST', json.dumps(self.request()).encode())
        self.assertEqual(guard.requests, 0)

    def test_real_native_agent_preflight_keeps_estop_and_makes_no_http(self):
        import os
        packet = intake.compile_snapshot(fixture(), 1794085822)
        env = {k: v for k, v in os.environ.items() if not any(word in k.upper() for word in
               ('TOKEN', 'KEY', 'SECRET', 'PASSWORD', 'CREDENTIAL', 'AUTHORIZATION')) and not k.startswith('HERMES_')}
        env.update(HERMES_HOME='/Users/nav/.hermes/profiles/floww-research', HERMES_IGNORE_RULES='1',
                   PYTHONDONTWRITEBYTECODE='1')
        sentinel = Path(env['HERMES_HOME']) / 'ESTOP'
        before = sentinel.read_bytes()
        with tempfile.TemporaryDirectory() as scratch:
            run = subprocess.run([str(worker.NATIVE_PYTHON), '-I', str(OPS / 'research_native_role.py')],
                input=(json.dumps({'role': 'research', 'packet': packet}) + '\n').encode(),
                env=env, cwd=scratch, capture_output=True, timeout=20)
        lines = run.stdout.splitlines()
        self.assertEqual(run.returncode, 0)
        self.assertEqual(len(lines), 2, run.stdout[:300])
        ready, refused = map(json.loads, lines)
        self.assertTrue(ready['bounded'])
        self.assertEqual(ready['sdk_retries'], 0)
        self.assertEqual(refused['http_request_count'], 0)
        self.assertEqual(refused['refusal_code'], 'role_not_admitted')
        self.assertEqual(sentinel.read_bytes(), before)

    def test_native_rejection_fixture_is_exercised_without_model_or_network(self):
        interpreter = Path('/Users/nav/.hermes/tools/python-3.14.9+20261021-darwin-arm64/bin/python3')
        if not interpreter.exists():
            self.fail('Native commissioned interpreter missing')
        result = subprocess.run([str(interpreter), '-I', str(OPS / 'research_native_role.py'), '--self-test'],
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr[:200])
        proof = json.loads(result.stdout)
        self.assertTrue(proof['all_passed'])
        self.assertEqual(proof['executor_calls'], 0)
        self.assertEqual(proof['models_called'], 0)


if __name__ == '__main__':
    unittest.main()
