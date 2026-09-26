"""Independent cash examples; offline proposed math, no account/order creation."""

import sys
import unittest
import uuid
from decimal import Decimal, localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.agent.paper.accounting import equity, exact, fill_cash_change, marked_value, simulated_fill
from services.agent.paper.repository import operation_id, operation_version, validate_json


class PaperArithmeticTests(unittest.TestCase):
    def test_equity_accepts_an_exact_derived_cash_balance(self):
        with localcontext() as context:
            context.prec = 256
            cash = Decimal("1e24") - Decimal("1e-24")
        self.assertEqual(equity(str(cash), [{"quantity": 1, "premium_factor": 1, "mark": "1e-24"}]),
                         Decimal("1e24"))

    def test_wide_derived_range_refuses_inexact_fee_instead_of_dropping_it(self):
        with self.assertRaisesRegex(ValueError, "exact supported precision"):
            fill_cash_change("1e24", "1e24", "1e24", "1e-200")

    def test_derived_slippage_price_keeps_all_accepted_digits(self):
        arguments = (1, 100, "1.234567890123456789012345678", "0")
        price = simulated_fill(*arguments, slippage_enabled=True, slippage_method="price", price_increment="10")
        cash = simulated_fill(*arguments, slippage_enabled=True, slippage_method="cash", price_increment="10")
        self.assertEqual(price["cash_change"], cash["cash_change"])
        self.assertEqual(price["fill_price"], "11.234567890123456789012345678")

    def test_all_slippage_choices_count_cost_once(self):
        for method in ("price", "cash"):
            opened = simulated_fill(1, 100, "2.00", "0.65", slippage_enabled=True,
                                    slippage_method=method, price_increment="0.05")
            closed = simulated_fill(-1, 100, "2.50", "0.65", slippage_enabled=True,
                                    slippage_method=method, price_increment="0.05")
            self.assertEqual(Decimal(opened["cash_change"]), Decimal("-205.65"))
            self.assertEqual(Decimal(closed["cash_change"]), Decimal("244.35"))
            self.assertEqual(Decimal(opened["cash_change"]) + Decimal(closed["cash_change"]),
                             Decimal("38.70"))
            self.assertEqual(Decimal(opened["fill_price"]), Decimal("2.05" if method == "price" else "2.00"))
            self.assertEqual(Decimal(opened["slippage_cash_charge"]), Decimal("0" if method == "price" else "5.00"))

    def test_off_keeps_method_but_removes_only_slippage(self):
        for method in ("price", "cash"):
            off = simulated_fill(1, 100, "2.00", "0.65", slippage_enabled=False,
                                 slippage_method=method, price_increment="0.05")
            self.assertEqual(Decimal(off["cash_change"]), Decimal("-200.65"))
            self.assertEqual(off["effective_slippage_mode"], "off")
            self.assertEqual(off["slippage_method"], method)
            self.assertEqual(Decimal(off["slippage_cash_charge"]), 0)

    def test_unknown_or_double_slippage_method_refused(self):
        for method in (None, "both", "midpoint", ""):
            with self.assertRaises(ValueError):
                simulated_fill(1, 100, 2, 0, slippage_enabled=True,
                               slippage_method=method, price_increment="0.05")
        for method in ("price", "cash"):
            with self.assertRaises(ValueError):
                simulated_fill(-1, 100, "0.01", 0, slippage_enabled=True,
                               slippage_method=method, price_increment="0.02")

    def test_long_entry_exit_fees_once(self):
        opened = Decimal("1000.00") + fill_cash_change(1, 100, "2.05", "0.65")
        self.assertEqual(opened, Decimal("794.35"))
        self.assertEqual(equity(opened, [{"quantity": 1, "premium_factor": 100, "mark": "2.05"}]),
                         Decimal("999.35"))
        closed = opened + fill_cash_change(-1, 100, "2.45", "0.65")
        self.assertEqual(closed, Decimal("1038.70"))

    def test_short_partial_close_and_reopen(self):
        cash = Decimal("1000") + fill_cash_change(-2, 100, "3.00", "1.30")
        self.assertEqual(cash, Decimal("1598.70"))
        self.assertEqual(equity(cash, [{"quantity": -2, "premium_factor": 100, "mark": "3.00"}]),
                         Decimal("998.70"))
        cash += fill_cash_change(1, 100, "2.00", "0.65")
        self.assertEqual(cash, Decimal("1398.05"))
        cash += fill_cash_change(1, 100, "1.00", "0.65")
        self.assertEqual(cash, Decimal("1297.40"))
        cash += fill_cash_change(1, 100, "1.50", "0.65")
        self.assertEqual(cash, Decimal("1146.75"))
        self.assertEqual(equity(cash, [{"quantity": 1, "premium_factor": 100, "mark": "1.50"}]),
                         Decimal("1296.75"))

    def test_fractional_shares_do_not_use_option_factor(self):
        self.assertEqual(fill_cash_change("0.125", 1, "400.08", "0.01"), Decimal("-50.02000"))
        self.assertEqual(marked_value("0.125", 1, "401.08"), Decimal("50.13500"))

    def test_factor_is_required_not_assumed(self):
        self.assertEqual(fill_cash_change(1, 10, "2.05", 0), Decimal("-20.50"))
        for factor in (None, 0, -100, "NaN", "Infinity", 100.0, True):
            with self.subTest(factor=factor), self.assertRaises(ValueError):
                fill_cash_change(1, factor, "2.05", 0)

    def test_unknown_mark_never_becomes_zero(self):
        with self.assertRaises(ValueError):
            equity("100", [{"quantity": 1, "premium_factor": 100, "mark": None}])

    def test_bad_money_refused(self):
        for value in (True, 0.1, "NaN", "Infinity", "1e1000000", "1e-1000000", "not-a-price"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                exact(value)
        for price, fee in (("-1", "0"), ("1", "-1")):
            with self.assertRaises(ValueError):
                fill_cash_change(1, 100, price, fee)
        with self.assertRaises(ValueError):
            fill_cash_change(0, 100, "1", "0")

    def test_zero_fee_and_worthless_mark_valid(self):
        self.assertEqual(marked_value(-1, 100, "0"), 0)
        self.assertEqual(fill_cash_change(-1, 100, "0", "0"), 0)

    def test_accepted_extreme_scales_remain_exact(self):
        value = Decimal("1.234567890123456789012345678E-24")
        with localcontext() as context:
            context.prec = 300
            expected = -value * value * value - Decimal("1E24")
        self.assertEqual(fill_cash_change(value, value, value, "1E24"), expected)
        with self.assertRaises(ValueError):
            equity(0, [{"quantity": 1, "premium_factor": 1, "mark": 1}] * 129)

    def test_version_bound_identity_and_json_limits(self):
        self.assertEqual(operation_version(operation_id(12, epoch=str(uuid.uuid4()))), 12)
        for version in (-1, True, 1.5, 2**63 - 1):
            with self.assertRaises(ValueError):
                operation_id(version, epoch=str(uuid.uuid4()))
        for value in ({"cash": 1.0}, {"$set": 1}, {"bad.key": 1}, {"large": 2**63}):
            with self.assertRaises(ValueError):
                validate_json(value)
        original = {"cash": "1.00", "positions": []}
        detached = validate_json(original)
        detached["positions"].append("new")
        self.assertEqual(original["positions"], [])


if __name__ == "__main__":
    unittest.main()
