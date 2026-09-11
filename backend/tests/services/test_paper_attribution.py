"""
Tests for PaperTradingEngine.get_pnl_attribution (Phase 6.5 remainder).

Average-cost matching per symbol, deterministic on recorded fills.
"""
from __future__ import annotations

from services.paper_trading import PaperTradingEngine


def _engine_with(trades: list[dict]) -> PaperTradingEngine:
    eng = PaperTradingEngine()
    eng.trade_history = list(trades)
    return eng


def _t(symbol: str, side: str, qty: float, px: float, fee: float = 0.0) -> dict:
    return {"symbol": symbol, "side": side, "quantity": qty,
            "fill_price": px, "commission": fee}


def test_round_trip_realized():
    eng = _engine_with([
        _t("SPY", "buy", 10, 100.0, fee=1.0),
        _t("SPY", "sell", 10, 110.0, fee=1.0),
    ])
    out = eng.get_pnl_attribution()
    assert out["total_realized_pnl"] == 100.0
    spy = next(s for s in out["symbols"] if s["symbol"] == "SPY")
    assert spy["net_qty"] == 0
    assert spy["realized_pnl"] == 100.0
    assert spy["commissions"] == 2.0
    assert spy["unrealized_pnl"] is None  # flat: nothing to mark


def test_partial_close_and_unrealized_with_marks():
    eng = _engine_with([
        _t("QQQ", "buy", 10, 50.0),
        _t("QQQ", "sell", 4, 60.0),
    ])
    out = eng.get_pnl_attribution({"QQQ": 70.0})
    qqq = next(s for s in out["symbols"] if s["symbol"] == "QQQ")
    assert qqq["realized_pnl"] == 40.0          # 4 × (60 − 50)
    assert qqq["net_qty"] == 6
    assert qqq["unrealized_pnl"] == 120.0       # 6 × (70 − 50)


def test_unrealized_unknown_without_marks():
    eng = _engine_with([_t("IWM", "buy", 5, 20.0)])
    out = eng.get_pnl_attribution()
    iwm = next(s for s in out["symbols"] if s["symbol"] == "IWM")
    assert iwm["unrealized_pnl"] is None  # honest unknown, never mark-to-model
    assert iwm["realized_pnl"] == 0.0


def test_short_flow_mirrors():
    eng = _engine_with([
        _t("DIA", "sell", 10, 100.0),
        _t("DIA", "buy", 10, 90.0),
    ])
    out = eng.get_pnl_attribution()
    assert out["total_realized_pnl"] == 100.0


def test_multi_symbol_totals():
    eng = _engine_with([
        _t("SPY", "buy", 10, 100.0),
        _t("SPY", "sell", 10, 110.0),
        _t("QQQ", "buy", 10, 50.0),
        _t("QQQ", "sell", 10, 45.0),
    ])
    out = eng.get_pnl_attribution()
    assert out["total_realized_pnl"] == 50.0  # +100 − 50
    assert {s["symbol"] for s in out["symbols"]} == {"SPY", "QQQ"}
    assert out["data_source"] == "paper_trading"


def test_attribution_route_uses_engine():
    """GET /api/paper-trading/attribution serves the engine payload."""
    from fastapi.testclient import TestClient

    import server
    from routes.paper_trading import set_paper_engine

    eng = PaperTradingEngine()
    eng.trade_history = [
        {"symbol": "SPY", "side": "buy", "quantity": 10,
         "fill_price": 100.0, "commission": 1.0},
        {"symbol": "SPY", "side": "sell", "quantity": 10,
         "fill_price": 110.0, "commission": 1.0},
    ]
    set_paper_engine(eng)
    try:
        client = TestClient(server.app)
        r = client.get("/api/paper-trading/attribution")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok"
        assert body["total_realized_pnl"] == 100.0
    finally:
        set_paper_engine(None)
