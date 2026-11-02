"""Paper mark provenance (`paper-mark-provenance.v1`).

The paper book priced positions from a bare `dict[str, float]` of prices and
reported `mark_source: None` / `mark_time: None`. Nothing said where a mark
came from, how old it was, or whether it was stale. This slice adds an
additive provenance envelope:

* every mark states its provider, source, receipt clock, event clock,
  staleness and unit;
* a missing mark, an invalid mark (zero/negative/non-finite), an undeclared
  source and a stale mark stay distinct states;
* a mark is never invented: no mark means unknown, not zero.

No provider call is added here: the route reuses the fetch it already made.
"""

from __future__ import annotations

import pytest

from services.paper_mark_provenance import (
    MARK_INVALID,
    MARK_OK,
    MARK_UNAVAILABLE,
    build_mark_envelope,
    mark_from_chain_payload,
    mark_record,
)
from services.paper_trading import PaperTradingEngine


def _trade(symbol: str, side: str, qty: float, px: float) -> dict:
    return {"symbol": symbol, "side": side, "quantity": qty,
            "fill_price": px, "commission": 0.0}


def _engine_with(trades: list[dict]) -> PaperTradingEngine:
    eng = PaperTradingEngine()
    eng.trade_history = list(trades)
    return eng


def _declared_mark(symbol: str = "QQQ", price: float = 70.0) -> dict:
    return mark_record(
        symbol, price,
        provider="public_api",
        source="public-mid",
        fetched_at="2026-11-02T15:00:05+00:00",
        event_time="2026-11-02T15:00:00+00:00",
    )


def test_mark_record_states_its_source_and_clocks():
    record = _declared_mark()
    assert record["status"] == MARK_OK
    assert record["price"] == pytest.approx(70.0)
    assert record["provider"] == "public_api"
    assert record["source"] == "public-mid"
    assert record["fetched_at"] == "2026-11-02T15:00:05+00:00"
    assert record["event_time"] == "2026-11-02T15:00:00+00:00"
    assert record["source_declared"] is True
    assert record["stale"] is False
    assert record["unit"] == "share"
    assert record["contract_multiplier"] == {"value": 1, "source": "share_quantity"}


def test_observed_zero_mark_is_a_measured_mark():
    record = mark_record("SPY", 0.0, provider="public_api", source="public-mid")
    assert record["status"] == MARK_OK
    assert record["price"] == 0.0
    assert record["measured_zero"] is True
    assert record["reason"] is None


def test_negative_or_non_numeric_mark_is_invalid():
    negative = mark_record("SPY", -1.0)
    assert negative["status"] == MARK_INVALID
    assert negative["price"] is None
    assert negative["reason"] == "NEGATIVE_PRICE"
    text = mark_record("SPY", "not-a-price")
    assert text["status"] == MARK_INVALID
    assert text["reason"] == "NOT_A_NUMBER"


def test_missing_mark_is_unavailable_not_zero():
    record = mark_record("SPY", None, reason="MARK_FETCH_FAILED")
    assert record["status"] == MARK_UNAVAILABLE
    assert record["price"] is None
    assert record["reason"] == "MARK_FETCH_FAILED"


def test_undeclared_source_is_not_claimed_fresh():
    record = mark_record("SPY", 500.0)
    assert record["status"] == MARK_OK
    assert record["source_declared"] is False
    assert record["source"] is None
    assert record["fetched_at"] is None


def test_chain_payload_mark_carries_provider_and_clocks():
    record = mark_from_chain_payload("SPY", {
        "spot": 757.09,
        "spot_source": "public-mid",
        "spot_fetched_at": "2026-11-02T15:00:05+00:00",
        "spot_event_time": "2026-11-02T15:00:00+00:00",
        "fetched_at": "2026-11-02T15:00:06+00:00",
        "data_source": "public_api",
    })
    assert record["status"] == MARK_OK
    assert record["price"] == pytest.approx(757.09)
    assert record["provider"] == "public_api"
    assert record["source"] == "public-mid"
    assert record["fetched_at"] == "2026-11-02T15:00:05+00:00"
    assert record["event_time"] == "2026-11-02T15:00:00+00:00"


def test_chain_payload_without_a_spot_is_unavailable():
    record = mark_from_chain_payload("SPY", {"data_source": "public_api", "spot": 0})
    assert record["status"] == MARK_UNAVAILABLE
    assert record["price"] is None
    assert record["reason"]


def test_envelope_separates_priced_stale_and_unavailable():
    envelope = build_mark_envelope({
        "SPY": _declared_mark("SPY", 757.09),
        "QQQ": mark_record("QQQ", 600.0, provider="public_api", source="public-mid",
                           fetched_at="2026-11-02T14:00:00+00:00", stale=True),
        "AAPL": mark_record("AAPL", None, reason="MARK_FETCH_FAILED"),
    }, requested=["SPY", "QQQ", "AAPL"])
    assert envelope["version"] == "paper-mark-provenance.v1"
    assert envelope["priced"] == ["QQQ", "SPY"]
    assert envelope["unavailable"] == [{"symbol": "AAPL", "reason": "MARK_FETCH_FAILED"}]
    assert envelope["stale_symbols"] == ["QQQ"]
    assert envelope["source"] == "public_api"
    assert envelope["as_of"] == "2026-11-02T15:00:05+00:00"
    assert set(envelope["items"]) == {"SPY", "QQQ", "AAPL"}


def test_attribution_without_marks_reports_unknown_not_zero():
    eng = _engine_with([_trade("IWM", "buy", 5, 20.0)])
    out = eng.get_pnl_attribution()
    iwm = next(s for s in out["symbols"] if s["symbol"] == "IWM")
    assert iwm["unrealized_pnl"] is None
    assert iwm["mark"]["status"] == MARK_UNAVAILABLE
    assert iwm["mark"]["reason"] == "NO_MARK_SUPPLIED"
    assert iwm["mark"]["price"] is None
    assert out["total_unrealized_pnl"] is None
    assert out["marks"]["status"] == "unavailable"
    assert out["marks"]["reason"] == "NO_MARKS"


def test_attribution_marks_carry_provenance():
    eng = _engine_with([_trade("QQQ", "buy", 10, 50.0)])
    out = eng.get_pnl_attribution(marks={"QQQ": _declared_mark()})
    qqq = next(s for s in out["symbols"] if s["symbol"] == "QQQ")
    assert qqq["unrealized_pnl"] == pytest.approx(200.0)
    assert qqq["mark"]["price"] == pytest.approx(70.0)
    assert qqq["mark"]["provider"] == "public_api"
    assert qqq["mark"]["source"] == "public-mid"
    assert qqq["mark"]["fetched_at"] == "2026-11-02T15:00:05+00:00"
    assert out["marks"]["status"] == "ok"
    assert out["marks"]["priced"] == ["QQQ"]
    assert out["marks"]["items"]["QQQ"]["event_time"] == "2026-11-02T15:00:00+00:00"


def test_invalid_mark_leaves_unrealized_unknown():
    eng = _engine_with([_trade("QQQ", "buy", 10, 50.0)])
    out = eng.get_pnl_attribution(marks={"QQQ": mark_record("QQQ", -1.0)})
    qqq = next(s for s in out["symbols"] if s["symbol"] == "QQQ")
    assert qqq["unrealized_pnl"] is None
    assert qqq["mark"]["status"] == MARK_INVALID
    assert out["total_unrealized_pnl"] is None
    assert out["unmarked_symbols"] == ["QQQ"]


def test_legacy_price_map_is_not_claimed_fresh():
    eng = _engine_with([_trade("QQQ", "buy", 10, 50.0)])
    out = eng.get_pnl_attribution({"QQQ": 70.0})
    qqq = next(s for s in out["symbols"] if s["symbol"] == "QQQ")
    assert qqq["unrealized_pnl"] == pytest.approx(200.0)
    assert qqq["mark"]["price"] == pytest.approx(70.0)
    assert qqq["mark"]["source_declared"] is False
    assert qqq["mark"]["source"] is None
    assert qqq["mark"]["fetched_at"] is None
    assert out["marks"]["provenance"] == "undeclared"


def test_portfolio_summary_exposes_mark_provenance():
    eng = PaperTradingEngine()
    eng.positions["SPY_buy"] = {"symbol": "SPY", "side": "buy", "quantity": 10,
                                "avg_cost": 100.0, "realized_pnl": 0.0}
    eng.trade_history = [_trade("SPY", "buy", 10, 100.0)]
    out = eng.get_portfolio_summary(marks={"SPY": _declared_mark("SPY", 110.0)})
    position = out["positions"][0]
    assert position["mark_price"] == pytest.approx(110.0)
    assert position["mark_source"] == "public-mid"
    assert position["mark_time"] == "2026-11-02T15:00:00+00:00"
    assert position["mark"]["provider"] == "public_api"
    assert position["mark"]["fetched_at"] == "2026-11-02T15:00:05+00:00"
    assert out["marks"]["status"] == "ok"


def test_route_serves_mark_provenance_without_extra_provider_calls():
    from fastapi.testclient import TestClient

    import server
    from routes.paper_trading import set_paper_engine

    eng = _engine_with([_trade("SPY", "buy", 10, 100.0)])
    set_paper_engine(eng)
    calls: list[str] = []

    async def fake_fetch(ticker: str, max_expiries: int = 4):
        calls.append(ticker)
        return {
            "spot": 110.0,
            "spot_source": "public-mid",
            "spot_fetched_at": "2026-11-02T15:00:05+00:00",
            "spot_event_time": "2026-11-02T15:00:00+00:00",
            "fetched_at": "2026-11-02T15:00:06+00:00",
            "data_source": "public_api",
        }

    original = server.fetch_spot_and_chains_merged
    server.fetch_spot_and_chains_merged = fake_fetch
    try:
        client = TestClient(server.app)
        r = client.get("/api/paper-trading/attribution", params={"tickers": "SPY"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert calls == ["SPY"], "the route must not add a provider call"
        marks = body["marks"]
        assert marks["status"] == "ok"
        assert marks["priced"] == ["SPY"]
        item = marks["items"]["SPY"]
        assert item["price"] == pytest.approx(110.0)
        assert item["provider"] == "public_api"
        assert item["source"] == "public-mid"
        assert item["fetched_at"] == "2026-11-02T15:00:05+00:00"
        assert item["event_time"] == "2026-11-02T15:00:00+00:00"
        spy = next(s for s in body["symbols"] if s["symbol"] == "SPY")
        assert spy["unrealized_pnl"] == pytest.approx(100.0)
        assert spy["mark"]["source"] == "public-mid"
    finally:
        server.fetch_spot_and_chains_merged = original
        set_paper_engine(None)


def test_route_reports_a_failed_mark_fetch_as_unavailable():
    from fastapi.testclient import TestClient

    import server
    from routes.paper_trading import set_paper_engine

    eng = _engine_with([_trade("SPY", "buy", 10, 100.0)])
    set_paper_engine(eng)

    async def fake_fetch(ticker: str, max_expiries: int = 4):
        raise RuntimeError("upstream down")

    original = server.fetch_spot_and_chains_merged
    server.fetch_spot_and_chains_merged = fake_fetch
    try:
        client = TestClient(server.app)
        r = client.get("/api/paper-trading/attribution", params={"tickers": "SPY"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["marks"]["status"] == "unavailable"
        assert body["marks"]["unavailable"] == [
            {"symbol": "SPY", "reason": "MARK_FETCH_FAILED"}]
        spy = next(s for s in body["symbols"] if s["symbol"] == "SPY")
        assert spy["unrealized_pnl"] is None
        assert spy["mark"]["status"] == MARK_UNAVAILABLE
        assert body["total_unrealized_pnl"] is None
    finally:
        server.fetch_spot_and_chains_merged = original
        set_paper_engine(None)
