"""Focused regression — PaperTradingEngine duplicate-execution guard (paper-recovery B1).

Same defect class as frozen D1: ``execute_order`` mutated cash, positions and
trade_history with NO order-status guard, so replaying the same order_id
executed the order twice. RED on base 56f218ed; GREEN after the pending-status
guard. Refusal shape mirrors the engine's existing missing-order refusal
(ValueError) and the route layer (B6) maps it to HTTP 400.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.execution_engine import MarketState  # noqa: E402
from services.paper_trading import PaperTradingEngine  # noqa: E402


def _market(bid=100.0, ask=100.1):
    return MarketState(symbol="SPY", bid=bid, ask=ask, last=(bid + ask) / 2,
                       bid_size=100, ask_size=100, volume=1_000_000, volatility=0.2)


def _engine():
    return PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.65)


def test_duplicate_buy_execute_moves_cash_once():
    engine = _engine()
    market = _market()
    order_id = engine.submit_order(symbol="SPY", side="buy", quantity=2, market=market)["order_id"]
    engine.execute_order(order_id, market)
    cash_after_first = engine.cash
    trades_after_first = len(engine.trade_history)

    with pytest.raises(ValueError, match="already"):
        engine.execute_order(order_id, market)  # lost reply / operator retry

    assert engine.cash == cash_after_first, "cash moved twice for one order"
    assert len(engine.trade_history) == trades_after_first, "trade history gained a second row"


def test_duplicate_sell_execute_moves_cash_once():
    engine = _engine()
    market = _market()
    buy_id = engine.submit_order(symbol="SPY", side="buy", quantity=2, market=market)["order_id"]
    engine.execute_order(buy_id, market)
    sell_id = engine.submit_order(symbol="SPY", side="sell", quantity=2, market=market)["order_id"]
    engine.execute_order(sell_id, market)
    cash_after_first = engine.cash
    trades_after_first = len(engine.trade_history)

    with pytest.raises(ValueError, match="already"):
        engine.execute_order(sell_id, market)

    assert engine.cash == cash_after_first
    assert len(engine.trade_history) == trades_after_first


def test_guard_does_not_block_fresh_orders():
    """Distinct orders must keep executing normally after a duplicate refusal."""
    engine = _engine()
    market = _market()
    o1 = engine.submit_order(symbol="SPY", side="buy", quantity=1, market=market)["order_id"]
    engine.execute_order(o1, market)
    with pytest.raises(ValueError):
        engine.execute_order(o1, market)

    o2 = engine.submit_order(symbol="QQQ", side="buy", quantity=1, market=_market(200, 200.2))["order_id"]
    result = engine.execute_order(o2, _market(200, 200.2))
    assert result.filled_qty == 1


def test_missing_order_still_raises_value_error():
    engine = _engine()
    with pytest.raises(ValueError, match="not found"):
        engine.execute_order("PAPER-999999", _market())
