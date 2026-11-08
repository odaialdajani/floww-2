"""Frozen real evidence and closed role contracts; no provider or model calls."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS))
try:
    import heatmap_research as heatmap
except ImportError:
    heatmap = None


class ContractTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(heatmap, 'closed registered heatmap task is missing')
        return heatmap

    def test_registered_source_is_fixed_and_contains_actual_heatmap_facts(self):
        h = self.module()
        packet = h.request_for('research')
        self.assertEqual(packet['task_id'], 'retained-heatmap-v1')
        self.assertEqual(packet['scope']['snapshot_id'], 'snap_496ef8db776ca7c6')
        self.assertEqual(packet['scope']['mode'], 'retained')
        self.assertEqual(packet['scope']['expiries'], ['2026-11-09', '2026-11-10', '2026-11-11', '2026-11-12'])
        facts = {f['id']: f for f in packet['facts']}
        self.assertEqual(facts['cluster.raw']['value'], '-185569755.77475974')
        self.assertEqual(facts['divergence.turnover']['value'], '175414009.78159466')
        self.assertIn('stale_saturday', packet['limitations'])
        self.assertIn('greek_clock_unknown', packet['limitations'])
        self.assertIn('oi_effective_unknown', packet['limitations'])
        self.assertIn('qqq_gap_nov6_nov7', packet['limitations'])
        self.assertNotIn('observations', packet)
        self.assertFalse(packet['executable'])

    def test_normative_limitations_follow_pinned_source_despite_historical_usable_flags(self):
        h = self.module()
        source = json.loads(h.SOURCE_FILE.read_bytes())
        self.assertTrue(source['spy']['stored_quality']['setupEligible'])
        self.assertFalse(source['spy']['stored_display_stale'])
        self.assertIsNone(source['spy']['greek_source_time'])
        self.assertEqual(source['spy']['source_clock_profile']['oi_effective_date']['missing'], 640)
        self.assertEqual(source['qqq']['snapshot_count'], 0)
        packet = h.request_for('research')
        self.assertEqual(packet['clocks']['bid_event_range'], ['2026-11-06T21:01:00Z', '2026-11-06T21:15:00Z'])
        self.assertEqual(packet['coverage']['vex_missing_inputs'], 107)
        self.assertEqual(packet['coverage']['window'], 'IDENTITY_UNDECLARED')
        self.assertEqual(packet['limitations'], h.LIMITATIONS)
        self.assertEqual(packet['required_evidence'], h.REQUIRED_EVIDENCE)

    def test_source_file_tamper_is_refused_without_patching_accepted_source_globals(self):
        h = self.module()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            shutil.copyfile(h.__file__, root / 'heatmap_research.py')
            (root / 'fixtures').mkdir()
            source = h.SOURCE_FILE.read_bytes()
            (root / 'fixtures' / h.SOURCE_FILE.name).write_bytes(source.replace(b'736.51', b'999.51'))
            spec = importlib.util.spec_from_file_location('tampered_heatmap', root / 'heatmap_research.py')
            altered = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(altered)
            with self.assertRaisesRegex(altered.HeatmapError, '^source_digest_mismatch$'):
                altered.request_for('research')

    def test_caller_cannot_mint_role_facts_or_change_source_identity(self):
        h = self.module()
        for field in ('source_sha256', 'packet_id', 'task_id'):
            packet = h.request_for('research')
            packet[field] = 'forged'
            with self.subTest(field=field), self.assertRaises(h.HeatmapError):
                h.role_view(packet)
        packet = h.request_for('research')
        packet['facts'][0]['value'] = '999'
        with self.assertRaisesRegex(h.HeatmapError, '^untrusted_task_packet$'):
            h.role_view(packet)

    def test_literal_facts_units_citations_scope_and_expiry_are_closed(self):
        h = self.module()
        response = h.fixture_response(h.request_for('research'), 'research')
        self.assertTrue(h.validate_investigator(response)['accepted'])
        mutations = [lambda r: r['claims'][0].update(value='-185569755'),
                     lambda r: r['claims'][0].update(unit='USD'),
                     lambda r: r['claims'][0].update(citation='/spy/spot'),
                     lambda r: r['claims'][0].update(fact_id='unknown'),
                     lambda r: r['scope'].update(snapshot_id='other'),
                     lambda r: r['scope'].update(mode='live'),
                     lambda r: r['scope'].update(query_key='SPY:6:day'),
                     lambda r: r['scope'].update(expiries=['2026-11-09']),
                     lambda r: r.update(executable=True),
                     lambda r: r.update(order={'side': 'buy'}),
                     lambda r: r.update(confidence=.9),
                     lambda r: r.update(root_review_required=False)]
        for mutation in mutations:
            altered = copy.deepcopy(response)
            mutation(altered)
            with self.subTest(altered=altered):
                self.assertFalse(h.validate_investigator(altered)['accepted'])

    def test_question_population_wall_facts_and_fresh_requirements_cannot_drift(self):
        h = self.module()
        response = h.fixture_response(h.request_for('research'), 'research')
        mutations = [lambda r: r['questions'][0].update(type='buy_breakout'),
                     lambda r: r['questions'][0].update(wall_id='w_5ac6d95aa9dd'),
                     lambda r: r['questions'][0].update(fact_ids=['divergence.raw']),
                     lambda r: r['questions'].append(copy.deepcopy(r['questions'][0])),
                     lambda r: r['required_evidence'].pop(),
                     lambda r: r['limitations'].pop(),
                     lambda r: r['claims'].pop(),
                     lambda r: r['questions'][0].update(rationale='Buy the next breakout for a profit'),
                     lambda r: r['questions'][0].update(rationale='Spot will reach 999 tomorrow'),
                     lambda r: r['questions'][0].update(rationale='x' * 241)]
        for mutation in mutations:
            altered = copy.deepcopy(response)
            mutation(altered)
            with self.subTest(altered=altered):
                self.assertFalse(h.validate_investigator(altered)['accepted'])
        response['claims'][1] = copy.deepcopy(response['claims'][0])
        self.assertFalse(h.validate_investigator(response)['accepted'])

    def test_auditor_requires_completed_validated_exact_investigator_output(self):
        h = self.module()
        with self.assertRaisesRegex(h.HeatmapError, '^missing_investigator_output$'):
            h.request_for('audit')
        investigator = h.fixture_response(h.request_for('research'), 'research')
        request = h.request_for('audit', investigator)
        self.assertEqual(request['investigator'], investigator)
        self.assertEqual(request['investigator_sha256'], hashlib.sha256(h.canonical(investigator).encode()).hexdigest())
        self.assertEqual(request['facts'], h.request_for('research')['facts'])
        request['investigator']['claims'][0]['value'] = '0'
        with self.assertRaises(h.HeatmapError):
            h.role_view(request)
        investigator['executable'] = True
        with self.assertRaisesRegex(h.HeatmapError, '^invalid_investigator_output$'):
            h.request_for('audit', investigator)

    def test_audit_is_complete_digest_bound_and_never_actionable(self):
        h = self.module()
        investigator = h.fixture_response(h.request_for('research'), 'research')
        response = h.fixture_response(h.request_for('audit', investigator), 'audit')
        self.assertTrue(h.validate_audit(investigator, response)['accepted'])
        mutations = [lambda r: r.update(investigator_sha256='0' * 64),
                     lambda r: r['verdicts'].pop(),
                     lambda r: r['verdicts'][0].update(verdict='approved_trade'),
                     lambda r: r['verdicts'][0].update(reason='looks_profitable'),
                     lambda r: r['verdicts'][0].update(citations=['unknown']),
                     lambda r: r.update(executable=True),
                     lambda r: r.update(status='live'),
                     lambda r: r.update(root_review_required=False)]
        for mutation in mutations:
            altered = copy.deepcopy(response)
            mutation(altered)
            self.assertFalse(h.validate_audit(investigator, altered)['accepted'])
        response['verdicts'][0].update(verdict='reject', reason='unsupported_narrative')
        result = h.validate_audit(investigator, response)
        self.assertTrue(result['valid'])
        self.assertFalse(result['accepted'])
        self.assertEqual(result['reason'], 'audit_rejected')

    def test_duplicate_json_nonfinite_and_oversize_responses_are_refused(self):
        h = self.module()
        for text in ('{"status":"review_only","status":"live"}', '{"value":NaN}', 'x' * 20000):
            with self.subTest(text=text[:60]), self.assertRaises(h.HeatmapError):
                h.parse_response(text)

    def test_native_helper_routes_only_the_closed_task_and_preserves_original_audit_input(self):
        h = self.module()
        import research_native_role as native
        request = h.request_for('research')
        self.assertEqual(native.role_view(request), request)
        prompt = native.prompt_for(request, 'research')
        self.assertIn('cluster_retest', prompt)
        self.assertIn('weighting_divergence', prompt)
        self.assertIn('USD/1% spot move', prompt)
        investigator = h.fixture_response(request, 'research')
        audit = h.request_for('audit', investigator)
        self.assertIn(h.canonical(investigator), native.prompt_for(audit, 'audit'))
        self.assertEqual(native.system_for(request), h.SYSTEM)
        request['task_id'] = 'arbitrary-other-task'
        with self.assertRaises(native.NativeError):
            native.role_view(request)


class SharedAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(heatmap, 'closed registered heatmap task is missing')
        import research_worker
        self.worker = research_worker
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name).resolve() / 'heatmap'
        self.admission = self.state.parent / 'shared'
        patch = mock.patch.object(self.worker, 'ADMISSION_STATE', self.admission)
        patch.start()
        self.addCleanup(patch.stop)
        self.worker.set_paused(self.state, False)
        self.calls = []

    def runner(self, role, packet, state):
        self.calls.append((role, copy.deepcopy(packet)))
        return {'success': True, 'native_failed': False, 'response': heatmap.fixture_response(packet, role),
                'http_request_count': 1, 'blocked_http_attempt_count': 0, 'native_valid_tool_names': [],
                'cost_usd': None, 'cost_status': 'unknown', 'offline_replay': False,
                'stream_done': True, 'finish_reason': 'stop'}

    def test_real_heatmap_roles_share_fixed_ledger_and_audit_sees_completed_answer(self):
        result = heatmap.run_once(self.state, role_runner=self.runner, now=1794104651)
        self.assertEqual(result['status'], 'validated_research_pending_root_review')
        self.assertFalse(result['executable'])
        self.assertTrue(result['root_review_required'])
        self.assertEqual([r for r, _ in self.calls], ['research', 'audit'])
        self.assertNotIn('investigator', self.calls[0][1])
        self.assertEqual(self.calls[1][1]['investigator'], result['roles']['research']['response'])
        other = self.state.parent / 'alias'
        self.worker.set_paused(other, False)
        again = heatmap.run_once(other, role_runner=self.runner, now=1794104661)
        self.assertEqual(again['status'], 'duplicate_no_call')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.worker.admission_ledger()['attempts']), 1)

    def test_existing_saved_task_circuit_budget_and_shared_lease_prevent_new_calls(self):
        for kind in ('circuit', 'budget', 'unfinished', 'lease'):
            with self.subTest(kind=kind):
                ledger = {'schema': 'floww-research-admission.v1', 'daily_pair_limit': 4,
                          'circuit_parked': kind == 'circuit', 'attempts': {}}
                if kind == 'budget':
                    ledger['attempts'] = {str(i) * 64: {'day_utc': '2026-11-08', 'status': 'accepted'} for i in range(4)}
                if kind == 'unfinished':
                    ledger['attempts']['9' * 64] = {'day_utc': '2026-11-08', 'status': 'started'}
                self.worker.atomic_json(self.admission / 'admission.json', ledger)
                if kind == 'lease':
                    with self.worker.Lease(self.admission):
                        result = heatmap.run_once(self.state, role_runner=self.runner, now=1794104651)
                    self.assertEqual(result['status'], 'busy')
                else:
                    result = heatmap.run_once(self.state, role_runner=self.runner, now=1794104651)
                    self.assertIn(result['reason'], ('native_circuit_parked', 'daily_pair_budget_exhausted'))
                self.assertEqual(self.calls, [])

    def test_invalid_or_failed_investigator_prevents_audit_and_parks_global_circuit(self):
        def altered(role, packet, state):
            result = self.runner(role, packet, state)
            result['response']['claims'][0]['value'] = '0'
            return result
        result = heatmap.run_once(self.state, role_runner=altered, now=1794104651)
        self.assertEqual(result['status'], 'parked')
        self.assertEqual([r for r, _ in self.calls], ['research'])
        self.assertTrue(self.worker.admission_ledger()['circuit_parked'])
        self.assertEqual(heatmap.run_once(self.state, role_runner=self.runner, now=1794104652)['status'], 'duplicate_no_call')

    def test_offline_or_unfinished_native_envelope_never_accepts(self):
        def offline(role, packet, state):
            result = self.runner(role, packet, state)
            result['offline_replay'] = True
            return result
        result = heatmap.run_once(self.state, role_runner=offline, now=1794104651)
        self.assertEqual(result['status'], 'parked')
        self.assertEqual(len(self.calls), 1)

    def test_missing_audit_response_has_no_default_or_investigator_substitute(self):
        def missing(role, packet, state):
            result = self.runner(role, packet, state)
            if role == 'audit':
                result.pop('response')
            return result
        result = heatmap.run_once(self.state, role_runner=missing, now=1794104651)
        self.assertEqual(result['status'], 'parked')
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(result['roles']['audit']['validation']['accepted'])
        self.assertNotIn('response', result['roles']['audit'])

    def test_cli_rejects_caller_source_and_unknown_task_before_any_role(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = self.worker.main(['run-once', '--task', heatmap.TASK_ID,
                                      '--saved-input', '/never-read-caller-source.json'])
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(output.getvalue())['reason'], 'registered_task_source_is_fixed')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.worker.main(['run-once', '--task', 'arbitrary-helper'])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.calls, [])

    def test_cli_heatmap_default_state_is_separate_while_admission_remains_shared(self):
        output = io.StringIO()
        with mock.patch.object(self.worker, 'DEFAULT_STATE', self.state.parent / 'saved-research'), \
                mock.patch.object(heatmap, 'status', return_value={'status': 'paused'}) as status, \
                contextlib.redirect_stdout(output):
            self.assertEqual(self.worker.main(['status', '--task', heatmap.TASK_ID]), 0)
        status.assert_called_once_with(self.state.parent / 'heatmap-research')
        self.assertEqual(self.worker.ADMISSION_STATE, self.admission)

    def test_pause_and_shared_lease_replacement_stop_before_audit(self):
        def pause(role, packet, state):
            result = self.runner(role, packet, state)
            self.worker.set_paused(state, True)
            return result
        result = heatmap.run_once(self.state, role_runner=pause, now=1794104651)
        self.assertEqual(result['status'], 'parked')
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__':
    unittest.main()
