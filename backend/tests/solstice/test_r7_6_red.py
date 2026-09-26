"""R7-06 red tests: series clocks (half-day/AM/weekend) + series plumbing."""

import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime


def test_resolve_series_monthly_vs_weekly():
    from services.solstice_time import resolve_series
    # Sep 2026: Fridays 4/11/18 → monthly expiry is the 18th.
    assert resolve_series("SPX", "2026-09-18") == "SPX"
    assert resolve_series("^SPX", "2026-09-18") == "SPX"
    assert resolve_series("SPX", "2026-09-19") == "SPXW"
    assert resolve_series("SPXW", "2026-09-18") == "SPXW"
    assert resolve_series("SPY", "2026-09-18") == "EQUITY"
    assert resolve_series("QQQ", "2026-09-19") == "EQUITY"


def test_half_day_close_not_1600():
    from services.solstice_time import last_trading_utc
    # Fri 2026-11-27 is a half-day (13:00 ET close), not 16:00.
    end = last_trading_utc("2026-11-27", ticker="SPY")
    assert end == datetime(2026, 11, 27, 18, 0, tzinfo=UTC), end
    # Regular Friday keeps 16:00 ET.
    assert last_trading_utc("2026-09-25", ticker="SPY") == datetime(2026, 9, 25, 20, 0, tzinfo=UTC)


def test_am_spx_uses_preceding_session_not_settlement_open():
    from services.solstice_time import last_trading_utc
    # Monthly AM expiry Fri 2026-09-18: last trade Thu 09-17 17:00 ET.
    # Settlement-day 09:30 is valuation, never the trading deadline.
    end = last_trading_utc("2026-09-18", series="SPX", ticker="SPX")
    assert end == datetime(2026, 9, 17, 21, 0, tzinfo=UTC), end
    assert end != datetime(2026, 9, 18, 13, 30, tzinfo=UTC)


def test_closed_expiry_day_falls_back_to_last_open_close():
    from services.solstice_time import last_trading_utc, time_to_expiry_years
    # Saturday expiry: last trading is Friday's close, not Saturday 16:00.
    end = last_trading_utc("2026-09-19", ticker="SPY")
    assert end == datetime(2026, 9, 18, 20, 0, tzinfo=UTC), end
    # A Saturday expiry is already untradable on Sunday morning ET.
    t, _, reason = time_to_expiry_years("2026-09-19", now=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
                                        ticker="SPY")
    assert t is None and reason == "EXPIRED"
    assert time_to_expiry_years("not-a-date", ticker="SPY")[0] is None


def _mock_contract(**kw):
    from unittest.mock import MagicMock
    c = MagicMock()
    c.symbol = kw.get("symbol", "SPY261231C00530000")
    c.expiration = kw.get("expiration", "2030-12-31")
    c.strike = kw.get("strike", 530.0)
    c.iv = kw.get("iv", 0.15)
    c.delta = kw.get("delta", 0.45)
    c.gamma = kw.get("gamma", 0.01)
    c.bid = kw.get("bid", 1.0)
    c.ask = kw.get("ask", 1.2)
    c.mid = kw.get("mid", 1.1)
    c.last = kw.get("last", 1.1)
    c.volume = kw.get("volume", 500)
    c.open_interest = kw.get("open_interest", 1000)
    return c


def test_adapter_carries_series_to_contracts_and_clock():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from services import public_api_adapter as adapter
    from services.public_budget import PublicBudget
    adapter._CHAIN_CACHE.clear()
    broker = MagicMock()
    trading = MagicMock()
    trading.account_id = "acc-123"
    broker.get_trading_account.return_value = trading
    broker.get_option_expirations = AsyncMock(return_value=["2030-12-31"])
    quote = MagicMock()
    quote.mid_price = 520.50
    quote.last = 520.50
    quote.symbol = "SPY"
    broker.get_quotes = AsyncMock(return_value=[quote])
    oc = _mock_contract(expiration="2030-12-31")
    broker.get_option_chain_parsed = AsyncMock(
        return_value={"calls": [oc], "puts": []})
    budget = PublicBudget(capacity=60, refill_per_sec=60.0, max_inflight=99)
    with patch.object(adapter, "_get_broker", new=AsyncMock(return_value=broker)), \
         patch("services.public_budget.budget", budget):
        result = asyncio.run(adapter.fetch_chain_from_public_api("SPY", max_expiries=1))
    adapter._CHAIN_CACHE.clear()
    assert result is not None and result["contracts"]
    c0 = result["contracts"][0]
    assert c0["series"] == "EQUITY"
    assert c0["T"] > 0 and c0["T_model"] == "actual/365-exact"


def test_symbol_matrix_groups_observations_without_inventing():
    from services.public_capability import symbol_matrix
    rows = [
        {"ticker": "SPY", "operation": "get_option_chain", "requested": 10,
         "returned": 10, "usable": 9, "at": "2030-01-02T14:00:00+00:00"},
        {"ticker": "SPY", "operation": "get_quotes", "requested": 1,
         "returned": 1, "usable": 1, "at": "2030-01-02T15:00:00+00:00"},
        {"ticker": "^SPX", "operation": "get_option_expirations", "requested": 1,
         "returned": 0, "usable": 0, "at": "2030-01-02T15:00:00+00:00"},
    ]
    m = symbol_matrix(rows)
    assert m["n_symbols"] == 2
    spy = m["symbols"]["SPY"]
    assert spy["operations"]["get_option_chain"]["usable"] == 9
    assert spy["last_seen"] == "2030-01-02T15:00:00+00:00"
    assert spy["vex_inputs"] == "derivable-if-iv"
    spx = m["symbols"]["^SPX"]
    # Failed probe stays unusable + unobserved entitlement — never denied
    # without evidence, never substituted with SPY data.
    assert spx["operations"]["get_option_expirations"]["usable"] == 0
    assert spx["entitlement"] == "unobserved"
    assert spx["vex_inputs"] == "unknown"
    assert symbol_matrix([])["n_symbols"] == 0
