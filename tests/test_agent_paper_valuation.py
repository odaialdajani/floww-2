"""Independent prepared valuation examples; no provider, model or order calls."""

import copy
import sys
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.agent.paper.execution import new_book
from services.agent.paper.repository import PaperConflict
from services.agent.paper.valuation import current_observation, observe

NOW = datetime(2026, 9, 25, 14, tzinfo=UTC)
OPEN = NOW - timedelta(minutes=30)
BINDING = dict(owner="00000000-0000-4000-8000-000000000001", account_id="00000000-0000-4000-8000-000000000002",
               venue="internal", epoch="00000000-0000-4000-8000-000000000003")


def book():
    result = new_book("1000", currency="USD")
    result["cash"] = "698"
    result["positions"] = {
        "first": dict(contract_id="TEST", product_kind="equity", premium_factor="1",
                      lots=[dict(quantity=1, cost_per_unit="101"), dict(quantity=1, cost_per_unit="100")]),
        "second": dict(contract_id="TEST", product_kind="equity", premium_factor="1",
                       lots=[dict(quantity=1, cost_per_unit="101")]),
    }
    return result


def frame():
    return dict(
        marks=[dict(contract_id="TEST", currency="USD", source_id="quote-one", bid="109", ask="111",
                    observed_at=NOW.isoformat(), received_at=NOW.isoformat())],
        metadata=[dict(contract_id="TEST", product_kind="equity", currency="USD", premium_factor="1",
                       source_id="contract-one", verified_at=OPEN.isoformat())],
        policy=dict(policy_id="explicit-test-settings", mark_method="midpoint", max_mark_age_seconds=60,
                    max_spread="2", daily_loss_limit="50", drawdown_limit="40", max_gross_exposure="1000"),
        session=dict(session_id="test-2026-09-25", calendar_version="synthetic-test-calendar", source_id="calendar-one",
                     opened_at=OPEN.isoformat(), closed_at=(NOW + timedelta(hours=6)).isoformat()),
        session_open=dict(session_id="test-2026-09-25", source_id="verified-open", observed_at=OPEN.isoformat(), equity="1000"),
    )


def observed(state=None, inputs=None, previous=None, now=NOW):
    return observe(state or book(), inputs or frame(), now=now, binding=BINDING, previous=previous)


def option_inputs():
    state, inputs = book(), frame()
    for position in state["positions"].values():
        position["product_kind"] = "option"
    inputs["metadata"][0].update(product_kind="option", adjusted=False, right="call", strike="100", underlying="TEST",
                                  exercise_style="american", settlement_style="physical",
                                  deliverable=dict(kind="shares", quantity="1", symbol="TEST", currency="USD"),
                                  last_trade_at=(NOW+timedelta(seconds=10)).isoformat(),
                                  expiry_at=(NOW+timedelta(seconds=20)).isoformat(),
                                  exercise_cutoff_at=(NOW+timedelta(seconds=30)).isoformat(),
                                  settlement_at=(NOW+timedelta(days=1)).isoformat())
    return state, inputs


class ValuationTests(unittest.TestCase):
    def test_corrupt_short_fractional_or_negative_basis_lots_refuse(self):
        for quantity in (-1, 0, True, "1", 1.5):
            state = book()
            state["positions"]["first"]["lots"][0]["quantity"] = quantity
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                observed(state)
        state = book()
        state["positions"]["first"]["lots"][0]["cost_per_unit"] = "-1"
        with self.assertRaises(ValueError):
            observed(state)

    def test_foreign_prior_cannot_supply_opening_equity_or_price_history(self):
        prior = observed()
        prior["binding"]["owner"] = "00000000-0000-4000-8000-000000000099"
        inputs = frame()
        del inputs["session_open"]
        with self.assertRaises(PaperConflict):
            observed(inputs=inputs, previous=prior)

    def test_option_deadline_expires_saved_value_before_price_age_does(self):
        state, inputs = option_inputs()
        first = observed(state, inputs)
        self.assertEqual(first["unknown_positions"], 0)
        first["saved_version"] = 1
        state["valuation"] = first
        account = dict(**BINDING, version=1, state=state)
        self.assertEqual(current_observation(account, now=NOW+timedelta(seconds=10))["status"], "stale")
        second = observed(state, inputs, first, NOW+timedelta(seconds=11))
        self.assertIsNone(second["equity"])
        self.assertNotEqual(second["effective_digest"], first["effective_digest"])
        self.assertEqual(len(state["positions"]), 2)

    def test_session_close_expires_saved_risk_before_price_age_does(self):
        inputs, state = frame(), book()
        inputs["session"]["closed_at"] = (NOW+timedelta(seconds=10)).isoformat()
        first = observed(state, inputs)
        first["saved_version"] = 1
        state["valuation"] = first
        account = dict(**BINDING, version=1, state=state)
        self.assertEqual(current_observation(account, now=NOW+timedelta(seconds=11))["status"], "stale")
        second = observed(state, inputs, first, NOW+timedelta(seconds=11))
        self.assertIsNone(second["risk"]["limits_passed"])
        self.assertNotEqual(second["effective_digest"], first["effective_digest"])

    def test_settlement_deliverable_and_currency_must_agree(self):
        for mutation in ("kind", "currency"):
            state, inputs = option_inputs()
            if mutation == "kind":
                inputs["metadata"][0]["settlement_style"] = "cash"
            else:
                inputs["metadata"][0]["deliverable"]["currency"] = "EUR"
            self.assertIsNone(observed(state, inputs)["equity"])

    def test_exact_hand_values_keep_structures_and_execution_costs(self):
        state, inputs = book(), frame()
        before = copy.deepcopy(state)
        result = observed(state, inputs)
        self.assertEqual(state, before)
        self.assertEqual(Decimal(result["equity"]), Decimal("1028"))
        self.assertEqual(Decimal(result["known_holdings_value"]), Decimal("330"))
        self.assertEqual(Decimal(result["unrealized_result"]), Decimal("28"))
        self.assertEqual([Decimal(item["unrealized_result"]) for item in result["positions"]], [Decimal(19), Decimal(9)])
        self.assertFalse(result["entry_allowed"])
        self.assertTrue(result["risk"]["limits_passed"])
        self.assertEqual(result["risk"]["observation_coverage"], "sampled_only")

    def test_missing_one_contract_does_not_label_subtotal_as_account_equity(self):
        state = book()
        state["positions"]["second"]["contract_id"] = "OTHER"
        result = observed(state)
        self.assertEqual(result["unknown_positions"], 1)
        self.assertIsNone(result["equity"])
        self.assertIsNone(result["unrealized_result"])
        self.assertEqual(Decimal(result["known_holdings_value"]), Decimal(220))
        self.assertIsNone(result["risk"]["limits_passed"])

    def test_stale_future_crossed_wrong_identity_marks_are_unknown(self):
        variants = [dict(observed_at=(NOW-timedelta(seconds=61)).isoformat()),
                    dict(received_at=(NOW+timedelta(seconds=1)).isoformat()),
                    dict(bid="112", ask="111"), dict(currency="EUR"), dict(bid=None),
                    dict(observed_at=(NOW+timedelta(seconds=1)).isoformat())]
        for changes in variants:
            with self.subTest(changes=changes):
                inputs = frame()
                inputs["marks"][0].update(changes)
                result = observed(inputs=inputs)
                self.assertEqual(result["unknown_positions"], 2)
                self.assertIsNone(result["equity"])

    def test_known_zero_does_not_expire_or_delete_positions(self):
        inputs, state = frame(), book()
        inputs["marks"][0].update(bid="0", ask="0")
        result = observed(state, inputs)
        self.assertEqual(Decimal(result["equity"]), Decimal(698))
        self.assertEqual(len(state["positions"]), 2)
        self.assertFalse(result["risk"]["limits_passed"])

    def test_missing_policy_or_open_equity_never_uses_first_request_as_open(self):
        inputs = frame()
        del inputs["session_open"]
        result = observed(inputs=inputs)
        self.assertIsNone(result["risk"]["baseline_equity"])
        self.assertIsNone(result["risk"]["limits_passed"])
        inputs = frame()
        del inputs["policy"]
        self.assertIsNone(observed(inputs=inputs)["equity"])

    def test_peak_survives_unknown_input_restart_and_recovers(self):
        first = observed()
        broken = frame()
        broken["marks"] = []
        broken["session"] = None
        second = observed(inputs=broken, previous=copy.deepcopy(first), now=NOW+timedelta(seconds=1))
        self.assertIsNone(second["equity"])
        self.assertEqual(second["last_complete"]["observed_at"], first["observed_at"])
        self.assertTrue(second["last_complete"]["stale"])
        third_inputs = frame()
        third_inputs["marks"][0].update(source_id="quote-two", bid="99", ask="101",
                                         observed_at=(NOW+timedelta(seconds=2)).isoformat(),
                                         received_at=(NOW+timedelta(seconds=2)).isoformat())
        third = observed(inputs=third_inputs, previous=second, now=NOW+timedelta(seconds=2))
        self.assertEqual(Decimal(third["risk"]["observed_peak_equity"]), Decimal(1028))
        self.assertEqual(Decimal(third["risk"]["observed_drawdown"]), Decimal(30))

    def test_session_rollover_keeps_positions_and_requires_actual_new_open(self):
        state, inputs = book(), frame()
        first = observed(state, inputs)
        inputs["session"].update(session_id="next", opened_at=(NOW+timedelta(days=1)-timedelta(minutes=30)).isoformat(),
                                  closed_at=(NOW+timedelta(days=1,hours=6)).isoformat())
        next_result = observed(state, inputs, first, NOW+timedelta(days=1))
        self.assertEqual(len(next_result["positions"]), 2)
        self.assertIsNone(next_result["risk"]["baseline_equity"])
        self.assertIsNone(next_result["equity"])

    def test_changed_baseline_settings_and_capital_do_not_reset_loss_checks(self):
        first = observed()
        for key in ("session_open", "policy", "capital"):
            with self.subTest(key=key):
                state, inputs = book(), frame()
                if key == "session_open":
                    inputs[key]["equity"] = "2000"
                elif key == "policy":
                    inputs[key]["daily_loss_limit"] = "1000"
                else:
                    state["initial_cash"] = "2000"
                result = observed(state, inputs, first)
                self.assertIsNone(result["risk"]["limits_passed"])
                self.assertEqual(result["risk_anchor"]["baseline_equity"], "1000")

    def test_mark_source_cannot_rewind_or_change_identity(self):
        first = observed()
        for changes in (dict(bid="99", ask="101"), dict(source_id="older", observed_at=(NOW-timedelta(seconds=1)).isoformat())):
            inputs = frame()
            inputs["marks"][0].update(changes)
            result = observed(inputs=inputs, previous=first, now=NOW+timedelta(seconds=1))
            self.assertIsNone(result["equity"])
            self.assertEqual(result["mark_watermarks"], first["mark_watermarks"])

    def test_binding_clock_and_duplicate_source_inputs_refuse(self):
        with self.assertRaises(PaperConflict):
            observed(previous=observed(), now=NOW-timedelta(seconds=1))
        inputs = frame()
        inputs["marks"].append(dict(inputs["marks"][0]))
        with self.assertRaises(ValueError):
            observed(inputs=inputs)
        state = book()
        state["epoch"] = "00000000-0000-4000-8000-000000000009"
        with self.assertRaises(PaperConflict):
            observed(state)

    def test_wrong_factor_or_option_lifecycle_unknown_retains_holdings(self):
        for changes in (dict(premium_factor="100"), dict(product_kind="option"), dict(verified_at=(NOW+timedelta(days=1)).isoformat())):
            inputs = frame()
            inputs["metadata"][0].update(changes)
            self.assertIsNone(observed(inputs=inputs)["equity"])
        state, inputs = book(), frame()
        for position in state["positions"].values():
            position["product_kind"] = "option"
        inputs["metadata"][0]["product_kind"] = "option"
        result = observed(state, inputs)
        self.assertIsNone(result["equity"])
        self.assertEqual(len(state["positions"]), 2)

    def test_exact_loss_boundary_blocks_and_reservations_stay_separate(self):
        state, inputs = book(), frame()
        state["orders"]["pending"] = dict(status="working", reserved_cash="675")
        result = observed(state, inputs)
        self.assertEqual(result["reserved_cash"], "675")
        self.assertEqual(result["available_cash"], "23")
        self.assertEqual(Decimal(result["equity"]), Decimal(1028))
        self.assertFalse(result["risk"]["limits_passed"])
        inputs["policy"]["max_gross_exposure"] = "2000"
        inputs["policy"]["daily_loss_limit"] = "302"
        inputs["marks"][0].update(bid="0", ask="0")
        inputs["policy"]["drawdown_limit"] = "1000"
        self.assertFalse(observed(state, inputs)["risk"]["limits_passed"])

    def test_any_later_book_change_or_elapsed_price_makes_saved_view_stale(self):
        state = book()
        result = observed(state)
        result["saved_version"] = 1
        state["valuation"] = result
        account = dict(**BINDING, version=1, state=state)
        self.assertEqual(current_observation(account, now=NOW)["status"], "current")
        self.assertEqual(current_observation(account, now=NOW+timedelta(seconds=61))["status"], "stale")
        account["version"] += 1
        self.assertEqual(current_observation(account, now=NOW)["status"], "stale")
        account["version"] = 1
        account["state"]["cash"] = "699"
        self.assertEqual(current_observation(account, now=NOW)["status"], "stale")


if __name__ == "__main__":
    unittest.main()
