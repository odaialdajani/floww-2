from unittest.mock import AsyncMock

import pytest

from routes import analytics


@pytest.mark.asyncio
async def test_checklist_keeps_volatility_rank_unknown_and_returns_reading_fields(monkeypatch):
    monkeypatch.setattr(analytics._cache, "get_chain", AsyncMock(return_value={
        "spot": 100, "event_time": "2026-09-25T15:00:00Z", "data_source": "public_api",
        "contracts": [{"strike": 100, "type": "call", "iv": .25, "T": .1, "oi": 100, "expiry": "2026-12-18"}],
    }))
    result = await analytics.daily_checklist("SPY", expiries=2, max_age_seconds=300)
    assert result["regime"]["iv_rank"] is None
    assert result["regime"]["atm_iv"] == .25
    assert result["regime"]["skew"] is None
    assert result["regime"]["skew_basis"] is None
    assert result["key_levels"]["call_wall"] == 100
    assert result["key_levels"]["put_wall"] is None
    assert result["key_levels"]["dist_to_put_wall_pct"] is None
    assert result["strategy"]["recommended_strategies"] == []
    assert result["strategy"]["status"] == "unavailable"
    assert result["risk_management"]["expected_daily_move_fraction"] > 0
    assert result["risk_management"]["stop_loss"] is None
    assert result["observed_at"] == "2026-09-25T15:00:00Z"
    assert result["hedging_flow"]["basis"] == "modeled-call-positive-put-negative"


@pytest.mark.asyncio
async def test_missing_iv_is_not_replaced_with_default_volatility(monkeypatch):
    monkeypatch.setattr(analytics._cache, "get_chain", AsyncMock(return_value={
        "spot": 100, "contracts": [{"strike": 100, "type": "call", "iv": None, "T": .1, "oi": 100}],
    }))
    result = await analytics.daily_checklist("SPY", expiries=2, max_age_seconds=300)
    assert result["regime"]["market_regime"] == "unknown"
    assert result["regime"]["atm_iv"] is None
    assert result["regime"]["skew"] is None
    assert result["risk_management"]["expected_daily_move_fraction"] is None
    assert result["observed_at"] is None


@pytest.mark.parametrize("kind,direction", [("call", "sell"), ("put", "buy")])
def test_hedge_scenario_converts_one_percent_gex_once(monkeypatch, kind, direction):
    import advanced_analytics
    monkeypatch.setattr(advanced_analytics, "bs_gamma", lambda *a, **kw: .01)
    result = advanced_analytics.calc_gamma_flip_levels(100, [
        {"strike": 100, "type": kind, "iv": .25, "T": .1, "oi": 100, "expiry": "2026-12-18"},
    ], "SPY")
    assert abs(result["total_gex"]) == 10000
    assert result["hedging_flow"]["up_1pct"]["shares"] == 100
    assert result["hedging_flow"]["up_1pct"]["direction"] == direction


@pytest.mark.asyncio
async def test_skew_needs_two_real_wings_from_the_same_expiry(monkeypatch):
    contracts = [
        {"strike": 101, "type": "call", "iv": .24, "expiry": "2026-12-18"},
        {"strike": 99, "type": "put", "iv": .28, "expiry": "2026-12-18"},
        {"strike": 100, "iv": .99, "expiry": "2026-12-18"},
    ]
    monkeypatch.setattr(analytics._cache, "get_chain", AsyncMock(return_value={"spot": 100, "contracts": contracts}))
    result = await analytics.daily_checklist("SPY", expiries=2, max_age_seconds=300)
    assert result["regime"]["skew"] == pytest.approx(-.04)
    assert result["regime"]["skew_expiry"] == "2026-12-18"
    contracts[1]["expiry"] = "2027-01-15"
    result = await analytics.daily_checklist("SPY", expiries=2, max_age_seconds=300)
    assert result["regime"]["skew"] is None
