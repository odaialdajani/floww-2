"""Synthetic ordered-fill mechanics, independent of paper release/admission."""

import copy
import sys
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.agent.paper.execution import (
    EXIT_EVENTS,
    MAX_QUOTES,
    archive_order,
    cancel_order,
    fill_order,
    new_book,
    recovery_events,
    replenish_exit_capacity,
    reserved_cash,
    stage_order,
)
from services.agent.paper.repository import PaperCapacity, PaperConflict

NOW = datetime(2026, 9, 25, 14, tzinfo=UTC)
EPOCH = str(uuid.uuid4())


def staged(state=None, **changes):
    state = state or new_book("1000", currency="USD")
    fields = dict(epoch=EPOCH, contract_id="synthetic-option", product_kind="option", premium_factor="100",
                  side="buy", quantity=2, limit="2.10", fee_per_unit="0.65", slippage_enabled=True,
                  slippage_method="price", price_increment="0.05", max_quote_age_seconds=60,
                  max_spread="0.20", latency_ms=0, now=NOW, order_expires_at=NOW + timedelta(minutes=10),
                  proposal_digest="a" * 64, committed_version=1, currency="USD")
    fields.update(changes)
    result, event = stage_order(state, **fields)
    return result, event["order_id"]


def quote(key="first", **changes):
    values = dict(source_id=key, contract_id="synthetic-option", size_unit="contracts", bid="1.90", ask="2.00",
                  bid_size=10, ask_size=10, observed_at=NOW.isoformat(), received_at=NOW.isoformat())
    values.update(changes)
    return values


class PreparedExecutionTests(unittest.TestCase):
    def test_clock_rollback_cannot_reuse_retired_quote_size(self):
        state, first = staged(quantity=1)
        state, second = staged(state, quantity=1, committed_version=2)
        state, _, _ = fill_order(state, first, quote(ask_size=1), now=NOW, committed_version=3)
        state, _ = replenish_exit_capacity(state, now=NOW + timedelta(seconds=301))
        self.assertFalse(state["quotes"])
        with self.assertRaisesRegex(PaperConflict, "clock moved backwards"):
            fill_order(state, second, quote(ask_size=1), now=NOW, committed_version=4)

    def test_exit_stage_and_fill_consume_prepaid_event_space(self):
        state, opening = staged(quantity=1)
        state, _, _ = fill_order(state, opening, quote(), now=NOW, committed_version=2)
        before = recovery_events(state)
        state, close = staged(state, side="sell", quantity=1, structure_id=opening,
                              limit="1.80", committed_version=3)
        self.assertEqual(recovery_events(state), before - 1)
        state, _, _ = fill_order(state, close, quote("close"), now=NOW, committed_version=4)
        self.assertEqual(recovery_events(state), before - 2)
        self.assertIn(opening, state["exit_capacity"])
        state, _ = archive_order(state, close, projected_version=4)
        self.assertEqual(recovery_events(state), before - 3)
        state, _ = archive_order(state, opening, projected_version=2)
        self.assertEqual(recovery_events(state), 0)

    def test_entries_cannot_consume_protected_exit_quote_rows(self):
        state, opening = staged(quantity=1)
        state, _, _ = fill_order(state, opening, quote(), now=NOW, committed_version=2)
        while len(state["quotes"]) < MAX_QUOTES - 8:
            state["quotes"][str(len(state["quotes"]))] = dict(observed_at=NOW.isoformat())
        with self.assertRaises(PaperCapacity):
            staged(state, quantity=1, committed_version=3)
        state, close = staged(state, side="sell", quantity=1, structure_id=opening,
                              limit="1.80", committed_version=3)
        state, _, changed = fill_order(state, close, quote("protected-close"), now=NOW, committed_version=4)
        self.assertTrue(changed)
        self.assertEqual(len(state["quotes"]), MAX_QUOTES - 7)

    def test_entries_cannot_consume_protected_exit_order_slots(self):
        state = new_book("100000", currency="USD")
        for index in range(12):
            state, _ = staged(state, quantity=1, committed_version=index + 1)
        with self.assertRaises(PaperCapacity):
            staged(state, quantity=1, committed_version=13)

    def test_same_quote_cannot_be_relabelled_as_another_fill(self):
        state, order = staged()
        after, fill, changed = fill_order(state, order, quote(ask_size=1), now=NOW, committed_version=2)
        self.assertTrue(changed)
        self.assertEqual(Decimal(after["cash"]), Decimal("794.35"))
        duplicate, same, changed = fill_order(after, order, quote(ask_size=1), now=NOW, committed_version=99)
        self.assertFalse(changed)
        self.assertEqual(duplicate, after)
        self.assertEqual(same["fill_id"], fill["fill_id"])
        self.assertEqual(after["orders"][order]["filled"], 1)
        self.assertEqual(state["orders"][order]["filled"], 0)
        with self.assertRaises(PaperConflict):
            fill_order(after, order, quote(ask_size=2), now=NOW, committed_version=3)

    def test_displayed_size_is_shared_between_orders(self):
        state, first = staged(quantity=2)
        state, second = staged(state, quantity=2, committed_version=2)
        state, _, _ = fill_order(state, first, quote(ask_size=2), now=NOW, committed_version=3)
        unchanged, fill, changed = fill_order(state, second, quote(ask_size=2), now=NOW, committed_version=4)
        self.assertFalse(changed)
        self.assertIsNone(fill)
        self.assertEqual(unchanged, state)
        state, _, changed = fill_order(state, second, quote("next", ask_size=2), now=NOW, committed_version=4)
        self.assertTrue(changed)
        self.assertEqual(Decimal(state["cash"]), Decimal("177.40"))

    def test_partial_close_preserves_other_trade_with_same_contract(self):
        state, first = staged(quantity=1, slippage_enabled=False, fee_per_unit="0", limit="1.10")
        state, second = staged(state, quantity=1, slippage_enabled=False, fee_per_unit="0", limit="1.10", committed_version=2)
        for version, order in ((3, first), (4, second)):
            state, _, _ = fill_order(state, order, quote(bid="0.90", ask="1.00"), now=NOW, committed_version=version)
        state, close = staged(state, side="sell", quantity=1, structure_id=first, limit="1.40",
                              slippage_enabled=False, fee_per_unit="0", committed_version=5)
        state, _, _ = fill_order(state, close, quote("close", bid="1.50", ask="1.60"), now=NOW, committed_version=6)
        self.assertNotIn(first, state["positions"])
        self.assertIn(second, state["positions"])
        self.assertEqual(Decimal(state["cash"]), Decimal("950.00"))
        self.assertEqual(Decimal(state["realized_result"]), Decimal("50.00"))

    def test_partial_entry_and_two_closes_match_hand_calculated_cash(self):
        state, opening = staged()
        state, _, _ = fill_order(state, opening, quote(ask_size=1), now=NOW, committed_version=2)
        state, _, _ = fill_order(state, opening, quote("entry2", ask_size=1), now=NOW, committed_version=3)
        state, closing = staged(state, side="sell", quantity=2, structure_id=opening, limit="2.30", committed_version=4)
        state, _, _ = fill_order(state, closing, quote("close1", bid="2.50", ask="2.60", bid_size=1), now=NOW, committed_version=5)
        self.assertEqual(Decimal(state["cash"]), Decimal("833.05"))
        state, _, _ = fill_order(state, closing, quote("close2", bid="2.40", ask="2.50", bid_size=1), now=NOW, committed_version=6)
        self.assertEqual(Decimal(state["cash"]), Decimal("1067.40"))
        self.assertEqual(Decimal(state["realized_result"]), Decimal("67.40"))
        self.assertFalse(state["positions"])

    def test_no_midpoint_or_unfilled_limit_is_invented(self):
        state, order = staged(limit="2.01")
        unchanged, fill, changed = fill_order(state, order, quote(), now=NOW, committed_version=2)
        self.assertFalse(changed)  # Ask2.00 plus selected0.05 slippage exceeds2.01.
        self.assertIsNone(fill)
        self.assertEqual(unchanged, state)

    def test_stale_crossed_unknown_size_latency_and_expiry_refuse(self):
        state, order = staged(latency_ms=1000)
        for bad in (quote(observed_at=(NOW - timedelta(seconds=61)).isoformat()),
                    quote(bid="2.10", ask="2.00"), quote(ask_size=None), quote(size_unit="shares")):
            with self.assertRaises(ValueError):
                fill_order(state, order, bad, now=NOW, committed_version=2)
        with self.assertRaises(PaperConflict):
            fill_order(state, order, quote(), now=NOW, committed_version=2)
        with self.assertRaises(PaperConflict):
            fill_order(state, order, quote(observed_at=(NOW + timedelta(minutes=10)).isoformat(),
                                           received_at=(NOW + timedelta(minutes=10)).isoformat()),
                       now=NOW + timedelta(minutes=10), committed_version=2)

    def test_cancel_keeps_partial_position_and_reserved_exit_space(self):
        state, order = staged()
        self.assertEqual(recovery_events(state), EXIT_EVENTS + 9)
        state, _, _ = fill_order(state, order, quote(ask_size=1), now=NOW, committed_version=2)
        self.assertEqual(recovery_events(state), EXIT_EVENTS + 8)
        state, _, changed = cancel_order(state, order, committed_version=3)
        self.assertTrue(changed)
        self.assertEqual(recovery_events(state), EXIT_EVENTS)
        self.assertEqual(reserved_cash(state), 0)
        self.assertEqual(sum(lot["quantity"] for lot in state["positions"][order]["lots"]), 1)
        with self.assertRaises(PaperConflict):
            fill_order(state, order, quote("late"), now=NOW, committed_version=4)

    def test_retirement_cannot_recreate_or_reuse_order_identity(self):
        state, order = staged(quantity=1)
        state, _, _ = fill_order(state, order, quote(), now=NOW, committed_version=2)
        with self.assertRaises(PaperConflict):
            archive_order(state, order, projected_version=1)
        state, _ = archive_order(state, order, projected_version=2)
        with self.assertRaises(PaperConflict):
            fill_order(state, order, quote(), now=NOW, committed_version=3)
        state, next_order = staged(state, quantity=1, committed_version=3)
        self.assertNotEqual(next_order, order)

    def test_eighth_partial_cancels_remainder_without_erasing_holdings(self):
        state, order = staged(new_book("10000", currency="USD"), quantity=10)
        for i in range(8):
            state, _, _ = fill_order(state, order, quote(str(i), ask_size=1), now=NOW, committed_version=i + 2)
        self.assertEqual(state["orders"][order]["status"], "partially_filled_cancelled")
        self.assertEqual(state["orders"][order]["remaining"], 2)
        self.assertEqual(sum(lot["quantity"] for lot in state["positions"][order]["lots"]), 8)
        self.assertEqual(recovery_events(state), EXIT_EVENTS)

    def test_cash_reservations_and_closing_holdings_cannot_be_overbooked(self):
        state, order = staged(quantity=4)
        with self.assertRaises(PaperConflict):
            staged(state, quantity=1)
        state, _, _ = fill_order(state, order, quote(), now=NOW, committed_version=2)
        state, _ = staged(state, side="sell", structure_id=order, quantity=3, limit="2.00", committed_version=3)
        before = copy.deepcopy(state)
        with self.assertRaises(PaperConflict):
            staged(state, side="sell", structure_id=order, quantity=2, limit="2.00", committed_version=4)
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
