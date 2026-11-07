"""Actual saved endpoint data, embedded for portable offline tests."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_intake as intake

# Exact three-row saved endpoint fixture; no account information.
ACTUAL_SAVED = json.loads(r'''{
  "rows": [
    [
      "SPY",
      "SPY261110C00655000",
      "call",
      655.0,
      "2026-11-10",
      255,
      1,
      0.7421,
      0.9581,
      736.51
    ],
    [
      "SPY",
      "SPY261110C00660000",
      "call",
      660.0,
      "2026-11-10",
      215,
      1,
      0.7043,
      0.9556,
      736.51
    ],
    [
      "SPY",
      "SPY261110C00706000",
      "call",
      706.0,
      "2026-11-10",
      261,
      2,
      0.3694,
      0.8889,
      736.51
    ]
  ],
  "quote_truth": {
    "SPY|call|655|2026-11-10": {
      "premium_true": 2075317.5000000002,
      "premium_basis": "snapshot_volume_x_quote",
      "premium_is_estimate": true,
      "activity_basis": "cumulative_snapshot",
      "side": "FLOW",
      "last_trade_side": null,
      "nbbo_side": null,
      "signed_side": null,
      "sign_method": null,
      "bias": null,
      "mid": 81.385,
      "last": 83.17,
      "rel_spread": 0.03305277385267552,
      "snapshot_volume_change": null,
      "snapshot_elapsed_seconds": null,
      "volume_change_basis": null,
      "vol_delta": null,
      "velocity_per_min": null,
      "volume_data_received_at": 1794077218.180702,
      "volume_source_time": null,
      "bid_source_time": 1793999698.0,
      "ask_source_time": 1793999699.0,
      "last_source_time": 1793994539.0,
      "quote_source_time": 1793999698.0,
      "oi_source_time": null,
      "bid": 80.04,
      "ask": 82.73
    },
    "SPY|call|660|2026-11-10": {
      "premium_true": 1642600.0000000002,
      "premium_basis": "snapshot_volume_x_quote",
      "premium_is_estimate": true,
      "activity_basis": "cumulative_snapshot",
      "side": "FLOW",
      "last_trade_side": null,
      "nbbo_side": null,
      "signed_side": null,
      "sign_method": null,
      "bias": null,
      "mid": 76.4,
      "last": 79.01,
      "rel_spread": 0.03507853403141351,
      "snapshot_volume_change": null,
      "snapshot_elapsed_seconds": null,
      "volume_change_basis": null,
      "vol_delta": null,
      "velocity_per_min": null,
      "volume_data_received_at": 1794077218.180702,
      "volume_source_time": null,
      "bid_source_time": 1793999699.0,
      "ask_source_time": 1793999699.0,
      "last_source_time": 1793990984.0,
      "quote_source_time": 1793999699.0,
      "oi_source_time": null,
      "bid": 75.06,
      "ask": 77.74
    },
    "SPY|call|706|2026-11-10": {
      "premium_true": 806229.0,
      "premium_basis": "snapshot_volume_x_quote",
      "premium_is_estimate": true,
      "activity_basis": "cumulative_snapshot",
      "side": "FLOW",
      "last_trade_side": null,
      "nbbo_side": null,
      "signed_side": null,
      "sign_method": null,
      "bias": null,
      "mid": 30.89,
      "last": 31.42,
      "rel_spread": 0.034315312398834646,
      "snapshot_volume_change": null,
      "snapshot_elapsed_seconds": null,
      "volume_change_basis": null,
      "vol_delta": null,
      "velocity_per_min": null,
      "volume_data_received_at": 1794077218.180702,
      "volume_source_time": null,
      "bid_source_time": 1793999700.0,
      "ask_source_time": 1793999700.0,
      "last_source_time": 1793998247.0,
      "quote_source_time": 1793999700.0,
      "oi_source_time": null,
      "bid": 30.36,
      "ask": 31.42
    }
  },
  "row_observations": {
    "SPY|call|655|2026-11-10": {
      "received_at": 1794077218.180702,
      "event_time": null,
      "receipt_age_seconds": 8604.708111047745,
      "scope": "custom-options:2:7c91526f870ccea33d2e7d9a",
      "source": "public_api",
      "volume_source_time": null,
      "volume_source_age_seconds": null,
      "volume_clock_status": "unknown",
      "quote_source_time": 1793999698.0,
      "quote_source_age_seconds": 86124.8888130188,
      "quote_clock_status": "known",
      "bid_source_time": 1793999698.0,
      "ask_source_time": 1793999699.0,
      "last_source_time": 1793994539.0,
      "oi_source_time": null,
      "quote_extras_available": true,
      "data_status": "partial",
      "live": false,
      "trade_eligible": false
    },
    "SPY|call|660|2026-11-10": {
      "received_at": 1794077218.180702,
      "event_time": null,
      "receipt_age_seconds": 8604.708111047745,
      "scope": "custom-options:2:7c91526f870ccea33d2e7d9a",
      "source": "public_api",
      "volume_source_time": null,
      "volume_source_age_seconds": null,
      "volume_clock_status": "unknown",
      "quote_source_time": 1793999699.0,
      "quote_source_age_seconds": 86123.8888130188,
      "quote_clock_status": "known",
      "bid_source_time": 1793999699.0,
      "ask_source_time": 1793999699.0,
      "last_source_time": 1793990984.0,
      "oi_source_time": null,
      "quote_extras_available": true,
      "data_status": "partial",
      "live": false,
      "trade_eligible": false
    },
    "SPY|call|706|2026-11-10": {
      "received_at": 1794077218.180702,
      "event_time": null,
      "receipt_age_seconds": 8604.708111047745,
      "scope": "custom-options:2:7c91526f870ccea33d2e7d9a",
      "source": "public_api",
      "volume_source_time": null,
      "volume_source_age_seconds": null,
      "volume_clock_status": "unknown",
      "quote_source_time": 1793999700.0,
      "quote_source_age_seconds": 86122.8888130188,
      "quote_clock_status": "known",
      "bid_source_time": 1793999700.0,
      "ask_source_time": 1793999700.0,
      "last_source_time": 1793998247.0,
      "oi_source_time": null,
      "quote_extras_available": true,
      "data_status": "partial",
      "live": false,
      "trade_eligible": false
    }
  },
  "observations_by_ticker": {
    "SPY": {
      "received_at": 1794077218.180702,
      "event_time": null,
      "scope": "custom-options:2:7c91526f870ccea33d2e7d9a",
      "source": "public_api",
      "expiries_checked": 2,
      "expiries": [
        "2026-11-09",
        "2026-11-10"
      ],
      "max_expiries": 2,
      "selection": {
        "eligible_rows": 231,
        "retained_rows": 87,
        "rows_truncated": true,
        "ratio_leaders_limit": 60,
        "volume_leaders_limit": 60,
        "rows_per_ticker_cap": 120
      },
      "retained_rows": 87,
      "rows_per_ticker_cap": 120,
      "history_status": "available",
      "history_capped": true,
      "contract_conflicts": 0,
      "missing_quote_extras": 0,
      "missing_volume_source_clocks": 87,
      "data_status": "partial",
      "live": false,
      "trade_eligible": false,
      "receipt_age_seconds": 8604.708111047745,
      "receipt_clock_status": "known",
      "source_age_seconds": null,
      "source_clock_status": "unknown",
      "latest_attempt_at": 1794077219.172566,
      "latest_attempt_status": "ok",
      "latest_attempt_reason": null
    }
  },
  "total": 87,
  "count": 3,
  "offset": 0,
  "limit": 3,
  "order": "stocks",
  "next_offset": 3,
  "coverage": {
    "universe": 40,
    "observed_tickers": 40,
    "missing_tickers": 0,
    "available_tickers": 1,
    "stale_tickers": 40,
    "expired_tickers": 0,
    "source_clock_unknown_tickers": 40,
    "receipt_clock_unknown_tickers": 0,
    "source_stale_tickers": 0,
    "partial_tickers": 40,
    "legacy_limited_tickers": 0,
    "legacy_retention_ticker_limit": 500,
    "legacy_examples_per_ticker_limit": 3,
    "legacy_pruned_names_recoverable": false,
    "zero_result_tickers": 0,
    "latest_failed_tickers": 0,
    "deferred_tickers": 2,
    "storage_capacity_tickers": 0,
    "symbol_limit": 20000,
    "stored_tickers": 5450,
    "payload_bytes": 5974537,
    "payload_limit_bytes": 536870912,
    "rows_per_ticker_cap": 120,
    "capacity_covers_current_universe": true,
    "full_contract_chains": false,
    "complete_realtime_market": false,
    "max_age_seconds": 604800,
    "recent_receipt_window_seconds": 60,
    "retention": "latest_successful_bounded_snapshot_per_ticker",
    "legacy_status": "available",
    "catalog_available": true,
    "catalog_stale": false,
    "catalog_asof": "2026-11-07T20:02:30.005675+00:00",
    "scope_kind": "explicit_symbols",
    "scope_note": "Latest recorded bounded option checks; not a full contract chain, live flow, or historical tape."
  },
  "checked_at": 1794085822.888813,
  "source": "public-scan-observations",
  "live": false,
  "trade_eligible": false,
  "pagination_consistency": "latest snapshots may change between page reads",
  "legacy_examples_included": false,
  "truncated": true,
  "columns": [
    "underlying_ticker",
    "ticker",
    "contract_type",
    "strike_price",
    "expiration_date",
    "day_volume",
    "open_interest",
    "implied_volatility",
    "delta",
    "underlying_price"
  ],
  "status": "partial"
}''')
DECISION = 1794085822.888813
KEY = 'SPY|call|655|2026-11-10'


def response_for(packet, field='bid', value='80.04', unit='unspecified_source_units'):
    observation = next(item for item in packet['observations'] if item['contract_id'] == 'SPY261110C00655000')
    return {'packet_id': packet['packet_id'], 'status': 'review_only', 'executable': False,
            'scope': 'internal_research', 'claims': [
                {'observation_id': observation['observation_id'], 'field': field,
                 'value': value, 'unit': unit, 'citations': [
                     {'observation_id': observation['observation_id'], 'field': field}]}]}


class CompilationTests(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(ACTUAL_SAVED)

    def compile(self):
        return intake.compile_snapshot(self.saved, DECISION)

    def test_actual_saved_shape_becomes_review_only_without_invented_clocks(self):
        packet = self.compile()
        self.assertEqual(packet.get('status'), 'review_only')
        self.assertIs(packet['executable'], False)
        self.assertEqual(packet['scope'], 'internal_research')
        self.assertEqual(len(packet['observations']), 3)
        first = next(item for item in packet['observations'] if item['contract_id'] == 'SPY261110C00655000')
        self.assertEqual(first['fields']['strike_price']['value'], '655')
        self.assertEqual(first['fields']['bid']['value'], '80.04')
        self.assertEqual(first['fields']['bid']['unit'], 'unspecified_source_units')
        self.assertIsNone(first['currency'])
        self.assertIsNone(first['contract_multiplier'])
        self.assertEqual(first['fields']['day_volume']['value'], '255')
        self.assertEqual(first['fields']['day_volume']['unit'], 'unspecified_source_units')
        self.assertEqual(first['fields']['implied_volatility']['unit'], 'unspecified_source_units')
        self.assertIsNone(first['fields']['bid_size']['value'])
        self.assertEqual(first['clocks']['quote_source_time']['freshness'], 'stale')
        self.assertEqual(first['clocks']['volume_source_time']['knowledge'], 'unknown')
        self.assertIsNone(first['clocks']['volume_source_time']['value'])
        self.assertEqual(packet['page']['total'], 87)
        self.assertFalse(packet['complete_history'])
        self.assertFalse(packet['trade_eligible'])

    def test_polling_clock_and_precomputed_ages_do_not_change_identity(self):
        before = self.compile()
        self.saved['checked_at'] += 300
        for metadata in self.saved['row_observations'].values():
            metadata['receipt_age_seconds'] += 300
            metadata['quote_source_age_seconds'] += 300
        after = self.compile()
        self.assertEqual(before['packet_id'], after['packet_id'])
        self.assertEqual(before['observations'], after['observations'])

    def test_zero_size_is_distinct_from_missing_size_and_unknown_units(self):
        self.saved['quote_truth'][KEY].update(bid_size=0, ask_size=None, size_unit='contracts')
        first = next(item for item in self.compile()['observations'] if item['contract_id'] == 'SPY261110C00655000')
        self.assertEqual(first['fields']['bid_size'], {'value': '0', 'unit': 'contracts', 'status': 'zero'})
        self.assertEqual(first['fields']['ask_size']['status'], 'missing')
        original = intake.compile_snapshot(ACTUAL_SAVED, DECISION)
        self.assertEqual(original['observations'][0]['fields']['bid_size']['unit'], 'unknown')

    def test_future_source_clock_is_excluded_without_using_poll_time(self):
        self.saved['row_observations'][KEY]['quote_source_time'] = DECISION + 1
        self.saved['quote_truth'][KEY]['quote_source_time'] = DECISION + 1
        packet = self.compile()
        self.assertEqual(len(packet['observations']), 2)
        self.assertEqual(packet['excluded'][0]['reason'], 'future_quote_source_time')

    def test_future_receipt_is_excluded(self):
        self.saved['row_observations'][KEY]['received_at'] = DECISION + 1
        packet = self.compile()
        self.assertEqual(len(packet['observations']), 2)
        self.assertEqual(packet['excluded'][0]['reason'], 'future_received_at')

    def test_source_clock_after_its_saved_receipt_is_excluded(self):
        later = self.saved['row_observations'][KEY]['received_at'] + 1
        self.saved['row_observations'][KEY]['bid_source_time'] = later
        self.saved['quote_truth'][KEY]['bid_source_time'] = later
        packet = self.compile()
        self.assertEqual(len(packet['observations']), 2)
        self.assertEqual(packet['excluded'][0]['reason'], 'source_after_receipt')

    def test_extras_only_source_clocks_cannot_hide_future_or_invalid_data(self):
        received = self.saved['row_observations'][KEY]['received_at']
        for stamp, reason in [(DECISION + 1, 'future_bid_source_time'),
                              (received + 1, 'source_after_receipt'),
                              ('invalid', 'invalid_bid_source_time')]:
            with self.subTest(reason=reason):
                self.saved = copy.deepcopy(ACTUAL_SAVED)
                del self.saved['row_observations'][KEY]['bid_source_time']
                self.saved['quote_truth'][KEY]['bid_source_time'] = stamp
                packet = self.compile()
                self.assertEqual(len(packet['observations']), 2)
                self.assertEqual(packet['excluded'][0]['reason'], reason)

    def test_valid_extras_only_clock_is_preserved_as_known(self):
        del self.saved['row_observations'][KEY]['bid_source_time']
        packet = self.compile()
        first = next(item for item in packet['observations'] if item['contract_id'] == 'SPY261110C00655000')
        self.assertEqual(first['clocks']['bid_source_time']['value'], '1793999698')
        self.assertEqual(first['clocks']['bid_source_time']['knowledge'], 'known')

    def test_extreme_timezone_conversion_is_a_row_refusal(self):
        for stamp in ['0001-01-01T00:00:00+14:00', '9999-12-31T23:59:59-14:00']:
            with self.subTest(stamp=stamp):
                self.saved = copy.deepcopy(ACTUAL_SAVED)
                self.saved['row_observations'][KEY]['event_time'] = stamp
                packet = self.compile()
                self.assertEqual(len(packet['observations']), 2)
                self.assertEqual(packet['excluded'][0]['reason'], 'invalid_event_time')

    def test_missing_strike_and_wrong_expiry_are_precise_exclusions(self):
        for index, value, reason in [(3, None, 'strike_missing'), (4, '2026-11-11', 'expiry_mismatch')]:
            with self.subTest(reason=reason):
                self.saved = copy.deepcopy(ACTUAL_SAVED)
                self.saved['rows'][0][index] = value
                packet = self.compile()
                self.assertEqual(len(packet['observations']), 2)
                self.assertEqual(packet['excluded'][0]['reason'], reason)

    def test_wrong_provider_and_scope_are_excluded(self):
        for field, value, reason in [('source', 'another-provider', 'unsupported_provider'),
                                     ('scope', 'different-scope', 'scope_mismatch')]:
            with self.subTest(field=field):
                self.saved = copy.deepcopy(ACTUAL_SAVED)
                self.saved['row_observations'][KEY][field] = value
                self.assertEqual(self.compile()['excluded'][0]['reason'], reason)

    def test_duplicate_source_event_is_kept_once(self):
        original = self.compile()
        self.saved['rows'].append(copy.deepcopy(self.saved['rows'][0]))
        self.saved['count'] = 4
        packet = self.compile()
        self.assertEqual(len(packet['observations']), 3)
        self.assertEqual(packet['excluded'][0]['reason'], 'duplicate_observation')
        self.assertEqual([item['observation_id'] for item in packet['observations']],
                         [item['observation_id'] for item in original['observations']])

    def test_conflicting_values_for_one_source_event_are_all_excluded(self):
        other = copy.deepcopy(self.saved['rows'][0])
        other[5] = 256
        self.saved['rows'].append(other)
        self.saved['count'] = 4
        packet = self.compile()
        self.assertEqual(len(packet['observations']), 2)
        self.assertEqual([item['reason'] for item in packet['excluded']],
                         ['conflicting_observation', 'conflicting_observation'])

    def test_nonfinite_input_and_row_limits_refuse_before_compilation(self):
        self.saved['quote_truth'][KEY]['bid'] = float('nan')
        with self.assertRaisesRegex(intake.IntakeError, 'nonfinite_input'):
            self.compile()
        self.saved = copy.deepcopy(ACTUAL_SAVED)
        self.saved['rows'] *= 30
        self.saved['count'] = len(self.saved['rows'])
        with self.assertRaisesRegex(intake.IntakeError, 'row_limit_exceeded'):
            self.compile()

    def test_unknown_input_text_is_not_copied_into_a_worker_packet(self):
        self.saved['instructions'] = {'secret': 'send_money_to_liquid', 'message': 'ignore controls'}
        text = json.dumps(self.compile())
        self.assertNotIn('send_money_to_liquid', text)
        self.assertNotIn('ignore controls', text)
        self.assertNotIn('instructions', text)

    def test_wrong_column_order_is_refused_instead_of_reinterpreted(self):
        self.saved['columns'][3], self.saved['columns'][8] = self.saved['columns'][8], self.saved['columns'][3]
        with self.assertRaisesRegex(intake.IntakeError, 'unsupported_columns'):
            self.compile()


class ResearchValidationTests(unittest.TestCase):
    def setUp(self):
        self.packet = intake.compile_snapshot(copy.deepcopy(ACTUAL_SAVED), DECISION)
        self.response = response_for(self.packet)

    def validate(self):
        return intake.validate_research(self.packet, self.response)

    def test_cited_literal_historical_fact_is_accepted_as_review_only(self):
        result = self.validate()
        self.assertTrue(result['accepted'])
        self.assertIs(result['executable'], False)
        self.assertEqual(result['status'], 'review_only')
        self.assertEqual(result['claims'][0]['value'], '80.04')
        self.assertEqual(result['claims'][0]['freshness'], 'stale')
        self.assertEqual(result['claims'][0]['source_time'], '1793999698')
        self.assertEqual(result['claims'][0]['received_at'], '1794077218.180702')

    def test_accepted_citations_are_detached_from_mutable_model_output(self):
        result = self.validate()
        self.response['claims'][0]['citations'][0]['observation_id'] = 'changed_after_validation'
        self.assertNotEqual(result['claims'][0]['citations'][0]['observation_id'], 'changed_after_validation')

    def test_missing_or_invented_citations_refuse(self):
        self.response['claims'][0]['citations'] = []
        self.assertEqual(self.validate()['reason'], 'citations_required')
        self.response['claims'][0]['citations'] = [{'observation_id': 'obs_invented', 'field': 'bid'}]
        self.assertEqual(self.validate()['reason'], 'unknown_observation_id')

    def test_invented_observation_id_refuses(self):
        self.response['claims'][0]['observation_id'] = 'obs_invented'
        self.assertEqual(self.validate()['reason'], 'unknown_observation_id')

    def test_numeric_value_or_units_cannot_change(self):
        self.response['claims'][0]['value'] = 80.05
        self.assertEqual(self.validate()['reason'], 'numeric_mismatch')
        self.response = response_for(self.packet, unit='USD_notional')
        self.assertEqual(self.validate()['reason'], 'unit_mismatch')

    def test_missing_value_cannot_be_promoted_to_zero(self):
        self.response = response_for(self.packet, field='bid_size', value=0, unit='unknown')
        self.assertEqual(self.validate()['reason'], 'value_mismatch')
        self.response['claims'][0]['value'] = None
        self.assertTrue(self.validate()['accepted'])

    def test_expiry_and_provider_and_scope_claims_must_equal_supplied_metadata(self):
        for field, value, unit in [('expiry', '2026-11-11', 'calendar_date'),
                                   ('provider', 'other', 'identifier'),
                                   ('scope', 'whole_market', 'identifier')]:
            with self.subTest(field=field):
                self.response = response_for(self.packet, field, value, unit)
                self.assertEqual(self.validate()['reason'], 'value_mismatch')

    def test_nonfinite_float_and_string_values_refuse(self):
        for value in [float('nan'), float('inf'), 'NaN', 'Infinity']:
            with self.subTest(value=value):
                self.response['claims'][0]['value'] = value
                self.assertEqual(self.validate()['reason'], 'nonfinite_response')

    def test_extreme_numeric_exponents_are_bounded_before_formatting(self):
        self.response['claims'][0]['value'] = '1e-1000'
        self.assertEqual(self.validate()['reason'], 'numeric_range_exceeded')

    def test_model_cannot_invent_currency_or_contract_multiplier(self):
        for field, value in [('currency', 'USD'), ('contract_multiplier', 100)]:
            with self.subTest(field=field):
                self.response = response_for(self.packet, field, value, 'identifier')
                self.assertEqual(self.validate()['reason'], 'value_mismatch')

    def test_finite_response_budget_and_claim_limit_are_enforced(self):
        original = copy.deepcopy(self.response['claims'][0])
        self.response['claims'] = [original for _ in range(65)]
        self.assertEqual(self.validate()['reason'], 'claims_required_or_limit_exceeded')
        self.response = response_for(self.packet)
        self.response['claims'][0]['value'] = 'x' * 65536
        self.assertEqual(self.validate()['reason'], 'response_byte_limit')

    def test_unsupported_action_liquid_product_venue_and_confidence_claims_refuse(self):
        for key, value, reason in [('execution', True, 'unsupported_execution_claim'),
                                   ('liquid', True, 'unsupported_liquid_claim'),
                                   ('product', 'perpetual', 'unsupported_product_claim'),
                                   ('venue', 'Liquid', 'unsupported_venue_claim'),
                                   ('confidence', .99, 'unsupported_confidence_claim')]:
            with self.subTest(key=key):
                self.response = response_for(self.packet)
                self.response[key] = value
                result = self.validate()
                self.assertFalse(result['accepted'])
                self.assertEqual(result['reason'], reason)
                self.assertIs(result['executable'], False)

    def test_executable_flag_and_free_prose_cannot_enter_accepted_output(self):
        self.response['executable'] = True
        self.assertEqual(self.validate()['reason'], 'unsupported_execution_claim')
        self.response = response_for(self.packet)
        self.response['summary'] = 'certain profit, trade now'
        self.assertEqual(self.validate()['reason'], 'unsupported_response_fields')

    def test_unit_and_citation_fields_are_mandatory(self):
        del self.response['claims'][0]['unit']
        self.assertEqual(self.validate()['reason'], 'claim_fields_required')

    def test_packet_tampering_and_wrong_packet_reference_refuse(self):
        self.response['packet_id'] = 'research_wrong'
        self.assertEqual(self.validate()['reason'], 'packet_id_mismatch')
        self.response = response_for(self.packet)
        self.packet['observations'][0]['fields']['bid']['value'] = '9'
        self.assertEqual(self.validate()['reason'], 'packet_digest_mismatch')

    def test_duplicate_claim_is_not_an_additional_observation(self):
        self.response['claims'].append(copy.deepcopy(self.response['claims'][0]))
        self.assertEqual(self.validate()['reason'], 'duplicate_claim')


if __name__ == '__main__':
    unittest.main()
