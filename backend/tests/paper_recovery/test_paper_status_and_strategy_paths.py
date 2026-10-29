"""Focused regression — honest status counts and unimplemented strategy path (D3 + B20).

D3 — PaperTradingEngine.get_state (mounted via /api/paper-trading/status)
counted per-LEG rows (``p["quantity"] > 0``), not net positions: a flat
buy->sell round-trip reported TWO open positions while get_portfolio_summary
correctly nets to zero. Status must use the same netting convention.

B20 — backend/paper_trading.py::execute_paper_trade dispatched to
get_options_chain / place_iron_condor / place_call_spread / place_put_spread
— NONE of which exist on AlpacaClient. Every auto_trade=True run therefore
failed, and the broad ``except Exception`` turned the guaranteed
AttributeError into a misleading error message naming a nonexistent method
(no explicit refusal, no statement that nothing was sent). The honest fix is
fail-closed: refuse explicitly ("not implemented; no order was sent") — no
venue path is added.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import paper_trading as pt  # noqa: E402
from services.execution_engine import MarketState  # noqa: E402
from services.paper_trading import PaperTradingEngine  # noqa: E402


def _market(bid=100.0, ask=100.0):
    return MarketState(symbol="SPY", bid=bid, ask=ask, last=(bid + ask) / 2,
                       bid_size=100, ask_size=100, volume=1_000_000, volatility=0.2)


class TestStatusCountsNetPositions:
    def test_flat_round_trip_status_reports_zero(self):
        engine = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
        m = _market()
        b = engine.submit_order(symbol="SPY", side="buy", quantity=10, market=m)["order_id"]
        engine.execute_order(b, m)
        s = engine.submit_order(symbol="SPY", side="sell", quantity=10, market=m)["order_id"]
        engine.execute_order(s, m)
        state = engine.get_state()
        assert state["open_positions"] == 0, \
            "status must net legs per symbol, not count legs"
        assert state["open_positions"] == engine.get_portfolio_summary()["open_positions"]

    def test_open_long_status_reports_one(self):
        engine = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
        m = _market()
        b = engine.submit_order(symbol="SPY", side="buy", quantity=5, market=m)["order_id"]
        engine.execute_order(b, m)
        assert engine.get_state()["open_positions"] == 1

    def test_open_short_status_reports_one(self):
        engine = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
        m = _market()
        s = engine.submit_order(symbol="SPY", side="sell", quantity=5, market=m)["order_id"]
        engine.execute_order(s, m)
        assert engine.get_state()["open_positions"] == 1

    def test_two_symbols_counted_separately(self):
        engine = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
        m = _market()
        b1 = engine.submit_order(symbol="SPY", side="buy", quantity=5, market=m)["order_id"]
        engine.execute_order(b1, m)
        b2 = engine.submit_order(symbol="QQQ", side="buy", quantity=2,
                                 market=_market(200, 200))["order_id"]
        engine.execute_order(b2, _market(200, 200))
        assert engine.get_state()["open_positions"] == 2


class _ClientWithoutStrategyMethods:
    """AlpacaClient stand-in: enabled, but — like the real class — it has NO
    option-chain or multi-leg strategy methods."""
    enabled = True


class TestUnimplementedStrategyPathRefuses:
    @pytest.mark.asyncio
    async def test_execute_paper_trade_refuses_without_crashing(self, monkeypatch):
        monkeypatch.setattr(pt, "get_alpaca_client", lambda: _ClientWithoutStrategyMethods())
        result = await pt.execute_paper_trade(
            {"strategy": "iron_condor", "ticker": "SPY", "spot": 500.0})
        assert result["status"] == "error"
        assert "not implemented" in result["message"].lower()
        assert "no order was sent" in result["message"].lower(), \
            "the refusal must state explicitly that nothing was submitted"

    @pytest.mark.asyncio
    async def test_auto_trade_signal_reports_not_executed(self, monkeypatch):
        monkeypatch.setattr(pt, "get_alpaca_client", lambda: _ClientWithoutStrategyMethods())
        results = await pt.process_signals_for_ticker(
            "SPY", [{"type": "GAMMA_FLIP", "spot": 500.0, "message": "flip"}],
            auto_trade=True)
        assert len(results) == 1
        assert results[0]["executed"] is False
        assert results[0]["trade"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_auto_trade_false_never_touches_the_client(self, monkeypatch):
        def _forbidden():
            raise AssertionError("client must not be constructed when auto_trade=False")

        monkeypatch.setattr(pt, "get_alpaca_client", _forbidden)
        results = await pt.process_signals_for_ticker(
            "SPY", [{"type": "GAMMA_FLIP", "spot": 500.0, "message": "flip"}],
            auto_trade=False)
        assert len(results) == 1
        assert results[0]["executed"] is False
        assert "trade" not in results[0]

    @pytest.mark.asyncio
    async def test_no_client_still_refused_honestly(self, monkeypatch):
        monkeypatch.setattr(pt, "get_alpaca_client", lambda: None)
        result = await pt.execute_paper_trade({"strategy": "iron_condor", "ticker": "SPY"})
        assert result["status"] == "error"
        assert "not available" in result["message"]
