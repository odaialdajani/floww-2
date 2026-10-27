"""Focused regression — PaperTrader nonpositive/nonfinite price guard (paper-recovery B4).

``_execute_buy``/``_execute_sell`` size positions as ``int(position_value /
price)`` (services/paper_trader.py:250,321). A zero, negative, NaN or infinite
price crashed with ZeroDivisionError / corrupted sizing instead of being
refused. RED on base 56f218ed; GREEN after the entry guard in
``execute_signal``. Refusal shape matches the existing "rejected" dicts
(max-positions / insufficient-cash paths).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.paper_trader import PaperTrader  # noqa: E402
from services.trading_signals import Signal  # noqa: E402


def _trader():
    return PaperTrader(initial_capital=10_000)


def test_zero_price_rejected_not_crash():
    result = _trader().execute_signal(Signal.BUY, "SPY", 0.0)
    assert result["status"] == "rejected"
    assert "price" in result["reason"].lower()


def test_negative_price_rejected():
    result = _trader().execute_signal(Signal.SELL, "SPY", -5.0)
    assert result["status"] == "rejected"
    assert "price" in result["reason"].lower()


def test_nan_price_rejected():
    result = _trader().execute_signal(Signal.BUY, "SPY", float("nan"))
    assert result["status"] == "rejected"
    assert "price" in result["reason"].lower()


def test_infinite_price_rejected():
    result = _trader().execute_signal(Signal.SELL, "SPY", float("inf"))
    assert result["status"] == "rejected"
    assert "price" in result["reason"].lower()


def test_nonnumeric_price_rejected():
    result = _trader().execute_signal(Signal.BUY, "SPY", None)
    assert result["status"] == "rejected"
    assert "price" in result["reason"].lower()


def test_rejection_leaves_book_untouched():
    trader = _trader()
    trader.execute_signal(Signal.BUY, "SPY", 0.0)
    trader.execute_signal(Signal.SELL, "SPY", float("nan"))
    assert trader.cash == trader.initial_capital
    assert trader.positions == {}
    assert trader.order_log == []


def test_hold_and_valid_prices_still_work():
    trader = _trader()
    assert trader.execute_signal(Signal.HOLD, "SPY", 0.0)["status"] == "no_action"
    assert trader.execute_signal(Signal.BUY, "SPY", 500.0)["status"] == "filled"
