import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import liquid_paper_adapter as adapter


class DestinationChecks(unittest.TestCase):
    def setUp(self):
        wallet = '0x' + 'a1' * 20
        self.inputs = {'endpoint': adapter.ENDPOINT, 'observed_at': 100, 'now': 101,
            'account': {'tradingAccountAddress': wallet, 'addressRole': 'trading-account'},
            'portfolio': {'paper': True, 'wallet': wallet.upper().replace('0X', '0x'),
                'account': {'equity': '10000', 'margin_used': '0', 'available_balance': '10000', 'account_value': '10000'},
                'positions': [], 'status': {'account': 'ok', 'positions': 'ok', 'tpsl': 'skipped'}},
            'orders': {'paper': True, 'wallet': wallet, 'orders': [], 'status': {'orders': 'ok', 'failedScopes': []}}}

    def assert_refused(self, inputs, reason):
        with self.assertRaisesRegex(adapter.PaperAdmissionError, '^' + reason + '$'):
            adapter.attest_destination(**inputs)

    def test_actual_shape_case_insensitive_destination_and_no_authority(self):
        result = adapter.attest_destination(**self.inputs)
        self.assertTrue(result['paper_observed'])
        self.assertFalse(result['submission_enabled'])
        self.assertFalse(result['automation_enabled'])
        self.assertNotIn(self.inputs['account']['tradingAccountAddress'], str(result))

    def test_preserves_existing_positions_and_orders(self):
        self.inputs['portfolio']['positions'] = [{'symbol': 'SYNTHETIC-PERP'}]
        self.inputs['orders']['orders'] = [{'id': 'retained'}]
        before = copy.deepcopy(self.inputs)
        result = adapter.attest_destination(**self.inputs)
        self.assertEqual(before, self.inputs)
        self.assertFalse(result['commissioning_book_clear'])
        self.assertEqual((1, 1), (result['existing_positions'], result['resting_orders']))

    def test_status_banner_cannot_override_structured_live_or_missing_mode(self):
        for field in ('portfolio', 'orders'):
            for mode in (False, None, 'true', 1):
                with self.subTest(field=field, mode=mode):
                    value = copy.deepcopy(self.inputs)
                    value[field]['paper'] = mode
                    self.assert_refused(value, 'paper_mode_unproven')

    def test_stale_future_and_invalid_clocks(self):
        for observed in (90, 102):
            self.inputs['observed_at'] = observed
            self.assert_refused(self.inputs, 'stale_or_future_destination')
        for clock in (float('nan'), float('inf'), True, '100', 0, 10 ** 1000):
            self.inputs['observed_at'] = clock
            self.assert_refused(self.inputs, 'invalid_evidence_clock')

    def test_destination_and_role_binding(self):
        self.inputs['orders']['wallet'] = '0x' + 'b2' * 20
        self.assert_refused(self.inputs, 'destination_mismatch')
        self.inputs['orders']['wallet'] = 'not-an-address'
        self.assert_refused(self.inputs, 'invalid_destination')
        self.inputs['account']['addressRole'] = 'deposit'
        self.assert_refused(self.inputs, 'unverified_account_role')

    def test_failed_fetch_is_not_flat(self):
        for group, name in [('portfolio', 'account'), ('portfolio', 'positions'), ('orders', 'orders')]:
            value = copy.deepcopy(self.inputs)
            value[group]['status'][name] = 'unavailable'
            self.assert_refused(value, 'incomplete_destination_read')
        self.inputs['orders']['status']['failedScopes'] = ['unknown']
        self.assert_refused(self.inputs, 'incomplete_destination_read')

    def test_balance_and_endpoint(self):
        for value in ('NaN', 'Infinity', '', 100, True, None):
            self.inputs['portfolio']['account']['equity'] = value
            self.assert_refused(self.inputs, 'invalid_balance')
        self.inputs['endpoint'] = 'http://arbitrary.invalid'
        self.assert_refused(self.inputs, 'unapproved_endpoint')

    def test_exact_discovered_missing_paper_parameter_is_blocked(self):
        tool = {'name': 'execute_order', 'input_schema': {'type': 'object', 'properties': {
            'symbol': {'type': 'string'}, 'side': {'enum': ['buy', 'sell']}, 'idempotencyKey': {'type': 'string'}}}}
        result = adapter.inspect_order_capability(tool)
        self.assertFalse(result['has_paper_parameter'])
        self.assertFalse(result['submission_enabled'])
        tool['input_schema']['properties']['executionMode'] = {'const': 'paper'}
        self.assertFalse(adapter.inspect_order_capability(tool)['submission_enabled'])

    def test_forged_attestation_duplicate_restart_stop_never_reaches_transport(self):
        for intent in ({}, {'idempotencyKey': 'same'}, {'idempotencyKey': 'same'}, {'stop': True}):
            with self.subTest(intent=intent), self.assertRaisesRegex(adapter.PaperAdmissionError, '^paper_submission_not_commissioned$'):
                adapter.submit_paper(intent, {'submission_enabled': True, 'paper_observed': True})


if __name__ == '__main__':
    unittest.main()
