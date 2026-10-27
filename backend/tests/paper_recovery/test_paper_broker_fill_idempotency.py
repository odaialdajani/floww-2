"""Focused regression — PaperBroker duplicate-fill idempotency (paper-recovery D1).

Recovered Oct18 plan requires duplicate-fill/cost counterexamples to be refused
by the ledger, not absorbed: a lost reply or operator retry replaying
``execute_fill`` on the SAME order must never move cash, positions or the fill
list a second time. RED on base 56f218ed (second fill was accepted); GREEN after
the status guard in ``services/paper_broker.py::execute_fill``.
"""
from __future__ import annotations

from services.paper_broker import PaperBroker, PaperBrokerConfig


def _broker() -> PaperBroker:
    return PaperBroker(config=PaperBrokerConfig(initial_capital=10_000.0))


def test_refill_same_order_moves_cash_once():
    broker = _broker()
    order_id = broker.submit_order("SPY", "buy", 5)
    first = broker.execute_fill(order_id, 500.0)
    assert first is not None
    cash_after_first = broker.cash
    fills_after_first = len(broker.fills)

    replay = broker.execute_fill(order_id, 500.0)  # lost reply / operator retry

    assert replay is None, "duplicate fill for one order must be refused"
    assert broker.cash == cash_after_first, "cash moved twice for one order"
    assert len(broker.fills) == fills_after_first, "fill list gained a second row"
    assert broker.orders[order_id]["status"] == "filled"


def test_refill_at_new_price_changes_nothing():
    broker = _broker()
    order_id = broker.submit_order("SPY", "buy", 5)
    broker.execute_fill(order_id, 500.0)
    cash_before = broker.cash
    position_before = broker.get_position("SPY").quantity

    replay = broker.execute_fill(order_id, 505.0)

    assert replay is None
    assert broker.cash == cash_before
    assert broker.get_position("SPY").quantity == position_before


def test_refill_refused_for_sell_side_too():
    broker = _broker()
    order_id = broker.submit_order("SPY", "sell", 4)
    broker.execute_fill(order_id, 500.0)
    cash_before = broker.cash

    replay = broker.execute_fill(order_id, 495.0)

    assert replay is None
    assert broker.cash == cash_before
    assert broker.get_position("SPY").quantity == -4


def test_guard_does_not_block_fresh_orders():
    """close_position and normal flow submit NEW orders; those must still fill."""
    broker = _broker()
    oid = broker.submit_order("SPY", "buy", 5)
    assert broker.execute_fill(oid, 500.0) is not None
    assert broker.execute_fill(oid, 500.0) is None  # replay refused

    close_fill = broker.close_position("SPY", 510.0)
    assert close_fill is not None, "fresh close order must still fill"
    assert broker.get_position("SPY").quantity == 0

    oid2 = broker.submit_order("QQQ", "buy", 1)
    assert broker.execute_fill(oid2, 400.0) is not None


def test_missing_order_still_refused_honestly():
    broker = _broker()
    assert broker.execute_fill("no-such-order", 500.0) is None
