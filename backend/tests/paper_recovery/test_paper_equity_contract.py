"""Focused regression — corrected paper EQUITY contract (root 2026-10-27 correction).

These cash ledgers DEBIT long buys and CREDIT short sells, so complete marked
equity is cash + Σ signed_quantity × observed_mark — NEVER cash + unrealized.
Marks come only from the caller; an entry price is NOT a mark. If ANY held
position lacks an eligible mark, the full aggregate (total_value/equity,
total_pnl, total_unrealized) is None — never a fabricated subset sum — while
an explicitly-partial known_marked_subtotal may stay numeric. A FLAT book
knows its equity: cash, unrealized 0. Unknown cost basis blocks
unrealized/total PnL independently of equity. Observed zero marks are real
data (worthless position → signed market value 0).

Pins (mandated by the root correction): long, short, mixed, flat, partial
close, real zero, the PaperTrader entry-price fallback, the mounted engine's
historical-cost labeling, and the engine attribution aggregate. RED on the
pre-fix tree; GREEN after the four lease fixes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.execution_engine import MarketState  # noqa: E402
from services.paper_broker import PaperBroker, PaperBrokerConfig  # noqa: E402
from services.paper_trader import PaperTrader  # noqa: E402
from services.paper_trading import PaperTradingEngine  # noqa: E402
from services.trading_signals import Signal  # noqa: E402


def _trader():
    return PaperTrader(initial_capital=1000.0, position_size_pct=0.05,
                       max_positions=5, commission_per_share=0.0)


class TestPaperTraderEquityPins:
    def test_long_equity_is_cash_plus_market_value(self):
        t = _trader()                       # 1000 cash
        t.execute_signal(Signal.BUY, "SPY", 100.0)   # buy 1 @100 -> cash 900
        assert t.cash == pytest.approx(900.0)
        s = t.get_portfolio_summary({"SPY": 100.0})
        assert s["total_value"] == pytest.approx(1000.0), \
            "equity must be cash + signed market value, not cash + unrealized"
        assert s["unrealized_pnl"] == pytest.approx(0.0)
        assert s["unknown_positions"] == 0

    def test_short_equity_is_cash_minus_market_value(self):
        t = _trader()
        t.execute_signal(Signal.SELL, "SPY", 100.0)  # short 1 @100 -> cash 1100
        assert t.cash == pytest.approx(1100.0)
        s = t.get_portfolio_summary({"SPY": 100.0})
        assert s["total_value"] == pytest.approx(1000.0), \
            "a short credits cash; equity must subtract its market value"
        assert s["unrealized_pnl"] == pytest.approx(0.0)

    def test_mixed_book_equity(self):
        t = _trader()
        t.execute_signal(Signal.BUY, "SPY", 100.0)   # long 1, cash 900
        t.execute_signal(Signal.SELL, "QQQ", 50.0)   # short 1, cash 950
        s = t.get_portfolio_summary({"SPY": 100.0, "QQQ": 50.0})
        assert s["total_value"] == pytest.approx(1000.0)  # 950 + 100 - 50
        assert s["unrealized_pnl"] == pytest.approx(0.0)

    def test_flat_book_equity_is_cash(self):
        t = _trader()
        s = t.get_portfolio_summary()
        assert s["total_value"] == pytest.approx(1000.0)
        assert s["unrealized_pnl"] == pytest.approx(0.0)
        assert s["unknown_positions"] == 0

    def test_missing_mark_is_never_the_entry_price(self):
        t = _trader()
        t.execute_signal(Signal.BUY, "SPY", 100.0)
        s = t.get_portfolio_summary()  # no marks supplied
        assert s["positions"][0]["current_price"] is None, \
            "entry price must never substitute for a missing observed mark"
        assert s["unknown_positions"] == 1
        assert s["total_value"] is None, "aggregate equity is unknown, not fabricated"
        assert s["total_pnl"] is None
        assert s["unrealized_pnl"] is None
        assert s["known_marked_subtotal"] == pytest.approx(0.0)  # explicit partial
        assert s["cash"] == pytest.approx(900.0)  # cash ledger stays known

    def test_partial_mark_coverage_keeps_named_subtotal_only(self):
        t = _trader()
        t.execute_signal(Signal.BUY, "SPY", 100.0)
        t.execute_signal(Signal.SELL, "QQQ", 50.0)
        s = t.get_portfolio_summary({"SPY": 120.0})  # QQQ unmarked
        assert s["total_value"] is None
        assert s["unrealized_pnl"] is None
        assert s["unknown_positions"] == 1
        # The marked symbol's contribution stays visible, explicitly partial.
        assert s["known_marked_subtotal"] == pytest.approx(20.0)

    def test_real_zero_mark_is_known_not_unknown(self):
        t = _trader()
        t.execute_signal(Signal.BUY, "SPY", 100.0)
        s = t.get_portfolio_summary({"SPY": 0.0})  # worthless
        assert s["total_value"] == pytest.approx(900.0)  # cash + 0 market value
        assert s["unrealized_pnl"] == pytest.approx(-100.0)
        assert s["unknown_positions"] == 0


class TestPaperBrokerEquityPins:
    def test_unmarked_open_position_reports_unknown_not_zero(self):
        b = PaperBroker(config=PaperBrokerConfig(initial_capital=1000.0))
        b.execute_fill(b.submit_order("SPY", "buy", 1), 100.0)
        pnl = b.get_pnl()
        assert pnl["unrealized_pnl"] is None, "unmarked is unknown, never 0.0"
        assert pnl["equity"] is None
        assert pnl["total_pnl"] is None
        assert pnl["unknown_positions"] == 1
        assert pnl["cash"] == pytest.approx(1000.0 - 100.11, abs=0.01)
        assert pnl["realized_pnl"] == pytest.approx(0.0)

    def test_marked_long_equity(self):
        b = PaperBroker(config=PaperBrokerConfig(initial_capital=1000.0))
        b.execute_fill(b.submit_order("SPY", "buy", 2), 100.0)
        pnl = b.get_pnl({"SPY": 110.0})
        assert pnl["equity"] == pytest.approx(b.cash + 220.0)
        assert pnl["unrealized_pnl"] == pytest.approx(
            (110.0 - b.get_position("SPY").avg_cost) * 2, abs=0.01)
        assert pnl["unknown_positions"] == 0

    def test_marked_short_equity(self):
        b = PaperBroker(config=PaperBrokerConfig(initial_capital=1000.0))
        b.execute_fill(b.submit_order("SPY", "sell", 2), 50.0)  # short -> cash+
        pnl = b.get_pnl({"SPY": 40.0})
        pos = b.get_position("SPY")
        assert pnl["equity"] == pytest.approx(b.cash + 40.0 * pos.quantity)
        assert pnl["unrealized_pnl"] == pytest.approx((40.0 - pos.avg_cost) * pos.quantity, abs=0.01)

    def test_flat_book_stays_numeric(self):
        b = PaperBroker(config=PaperBrokerConfig(initial_capital=1000.0))
        b.execute_fill(b.submit_order("SPY", "buy", 1), 100.0)
        b.close_position("SPY", 110.0)
        pnl = b.get_pnl()
        assert pnl["equity"] == pytest.approx(b.cash)
        assert pnl["unrealized_pnl"] == pytest.approx(0.0)
        assert pnl["total_pnl"] == pytest.approx(pnl["realized_pnl"], abs=0.01)


class TestEngineSummaryAndAttribution:
    def _engine_with_long(self):
        engine = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
        m = MarketState(symbol="SPY", bid=100.0, ask=100.0, last=100.0, bid_size=100,
                        ask_size=100, volume=1_000_000, volatility=0.2)
        oid = engine.submit_order(symbol="SPY", side="buy", quantity=1, market=m)["order_id"]
        engine.execute_order(oid, m)
        return engine

    def test_summary_labels_historical_cost_not_observed_equity(self):
        s = self._engine_with_long().get_portfolio_summary()
        assert s["valuation_basis"] == "historical_cost", \
            "cost-carrying value must be labeled, never promoted to observed equity"
        assert s["cost_basis_value"] == pytest.approx(s["total_value"])
        assert "observed" not in s["valuation_basis"]

    def test_attribution_aggregate_unknown_when_any_held_mark_missing(self):
        engine = self._engine_with_long()
        out = engine.get_pnl_attribution()  # no marks
        spy = out["symbols"][0]
        assert spy["unrealized_pnl"] is None
        assert out["total_unrealized_pnl"] is None, \
            "aggregate must not silently sum only the marked subset"
        assert out["unmarked_symbols"] == ["SPY"]
        assert out["known_marked_subtotal"] == pytest.approx(0.0)  # explicit partial

    def test_attribution_aggregate_numeric_when_fully_marked(self):
        engine = self._engine_with_long()
        # The engine's deterministic slippage is part of the recorded fill, so
        # derive the expected unrealized from the journal, not a naked 100.
        fill = engine.trade_history[0]["fill_price"]
        out = engine.get_pnl_attribution({"SPY": 105.0})
        # Attribution reports cents (its existing display convention).
        assert out["total_unrealized_pnl"] == pytest.approx(round((105.0 - fill) * 1, 2))
        assert out["unmarked_symbols"] == []

    def test_attribution_flat_book_is_known_zero(self):
        engine = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
        out = engine.get_pnl_attribution()
        assert out["total_unrealized_pnl"] == pytest.approx(0.0)
        assert out["unmarked_symbols"] == []
