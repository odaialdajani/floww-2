"""Exact ETF analytical expiry deadlines; entry policy remains XNYS based."""

import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime


def _calendar(day):
    if day == "2026-11-27":
        return {"is_open": True, "close_et": "13:00"}
    if day in {"2026-09-25", "2026-09-18", "2026-11-16"}:
        return {"is_open": True, "close_et": "16:00"}
    return {"is_open": False, "close_et": None}


def test_exact_etf_root_deadline_and_boundaries(monkeypatch):
    from services import solstice_time as clock
    monkeypatch.setattr(clock, "_open_day_info", _calendar)
    # EDT: 16:05 ET = 20:05 UTC, ten minutes remain to 16:15.
    t, floored, reason = clock.time_to_expiry_years(
        "2026-09-25", datetime(2026, 9, 25, 20, 5, tzinfo=UTC),
        series="EQUITY", ticker="SPY", option_root="SPY")
    assert t == 10 / (365 * 24 * 60) and not floored and reason is None
    assert clock.time_to_expiry_years(
        "2026-09-25", datetime(2026, 9, 25, 20, 15, tzinfo=UTC),
        ticker="SPY", option_root="SPY") == (None, False, "EXPIRED")
    t, floored, reason = clock.time_to_expiry_years(
        "2026-09-25", datetime(2026, 9, 25, 20, 14, 59, tzinfo=UTC),
        ticker="SPY", option_root="SPY")
    assert t == 1 / (365 * 24 * 60) and floored and reason is None
    assert clock.last_trading_utc("2026-09-25", ticker="SPY", option_root="SPY") == datetime(2026, 9, 25, 20, 15, tzinfo=UTC)


def test_qqq_exact_root_and_est_transition(monkeypatch):
    from services import solstice_time as clock
    monkeypatch.setattr(clock, "_open_day_info", _calendar)
    # EST after the November DST transition: 16:05 ET is 21:05 UTC.
    t, _, reason = clock.time_to_expiry_years(
        "2026-11-16", datetime(2026, 11, 16, 21, 5, tzinfo=UTC),
        ticker="QQQ", option_root="QQQ")
    assert t == 10 / (365 * 24 * 60) and reason is None
    assert clock.last_trading_utc("2026-11-16", ticker="QQQ", option_root="QQQ") == datetime(2026, 11, 16, 21, 15, tzinfo=UTC)


def test_early_close_rule_is_date_bounded(monkeypatch):
    from services import solstice_time as clock
    monkeypatch.setattr(clock, "_open_day_info", _calendar)
    assert clock.last_trading_utc("2026-11-27", ticker="SPY", option_root="SPY") == datetime(2026, 11, 27, 18, 15, tzinfo=UTC)
    # Before the FAQ effective date the XNYS half-day close remains 13:00.
    assert clock.last_trading_utc("2026-11-27", ticker="SPY") == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)


def test_non_etf_contracts_keep_existing_close(monkeypatch):
    from services import solstice_time as clock
    monkeypatch.setattr(clock, "_open_day_info", _calendar)
    assert clock.last_trading_utc("2026-09-25", ticker="AAPL", option_root="AAPL") == datetime(2026, 9, 25, 20, 0, tzinfo=UTC)
    assert clock.last_trading_utc("2026-09-25", series="SPXW", ticker="SPXW", option_root="SPXW") == datetime(2026, 9, 25, 20, 0, tzinfo=UTC)
    # Wrong root/display pair cannot inherit the ETF extension.
    assert clock.last_trading_utc("2026-09-25", ticker="SPY", option_root="SPY1") == datetime(2026, 9, 25, 20, 0, tzinfo=UTC)
    # Legacy callers without canonical option-root identity retain clock.v2 behavior.
    assert clock.last_trading_utc("2026-09-25", ticker="SPY") == datetime(2026, 9, 25, 20, 0, tzinfo=UTC)


def test_weekend_expiry_uses_previous_open_etf_deadline(monkeypatch):
    from services import solstice_time as clock
    monkeypatch.setattr(clock, "_open_day_info", _calendar)
    assert clock.last_trading_utc("2026-09-26", ticker="SPY", option_root="SPY") == datetime(2026, 9, 25, 20, 15, tzinfo=UTC)


def test_unknown_calendar_does_not_gain_etf_extension(monkeypatch):
    from services import solstice_time as clock
    monkeypatch.setattr(clock, "_open_day_info", lambda _day: None)
    assert clock.last_trading_utc("2026-09-25", ticker="SPY", option_root="SPY") == datetime(2026, 9, 25, 20, 0, tzinfo=UTC)
    assert clock.expiry_clock_lineage("2026-09-25", ticker="SPY", option_root="SPY") is None


def test_analytical_etf_time_does_not_open_entry_window():
    from services.solstice_session import session_state
    for at in (datetime(2026, 9, 25, 20, 5, tzinfo=UTC), datetime(2026, 9, 25, 20, 15, tzinfo=UTC)):
        state = session_state(now=at, quality={"state": "usable", "reasonCodes": []})
        assert state["entry_allowed"] is False
        assert state["management_allowed"] is True


def test_adapter_adds_clock_lineage_only_for_exact_supported_etf(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from services import public_api_adapter as adapter
    from services import solstice_time as clock

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 25, 19, 55, tzinfo=UTC)

    monkeypatch.setattr(adapter, "datetime", FixedDateTime)
    monkeypatch.setattr(clock, "_open_day_info", _calendar)

    def contract(symbol):
        return SimpleNamespace(symbol=symbol, expiration="2026-09-25", strike=530.0,
                               mid=1.1, open_interest=100, iv=.2, delta=.5, gamma=.01,
                               theta=None, vega=None, bid=1.0, ask=1.2, last=1.1,
                               bid_size=None, ask_size=None, volume=10)

    async def run(symbol, ticker="SPY"):
        pb = SimpleNamespace(get_option_chain_parsed=AsyncMock(
            return_value={"calls": [contract(symbol)], "puts": []}))
        return await adapter._assemble_chain(pb, ticker, ticker, "fixture", "EQUITY",
                                             ["2026-09-25"], 1, {"price": 530})

    etf = asyncio.run(run("SPY260925C00530000"))["contracts"][0]
    assert etf["clock_version"] == "clock.v3"
    assert etf["clock_deadline_utc"] == "2026-09-25T20:15:00+00:00"
    assert etf["clock_authority"]["version"] == "etf-expiry-authority.v1"
    assert etf["clock_authority"]["status"] == "authoritative"
    assert etf["clock_authority"]["sources"]

    legacy = asyncio.run(run("SPY1260925C00530000"))["contracts"][0]
    assert "clock_version" not in legacy
    assert legacy["T_model"] == "actual/365-exact"

    mismatched = asyncio.run(run("SPY1260925C00530000", ticker="QQQ"))["contracts"][0]
    assert "clock_version" not in mismatched

    qqq = asyncio.run(run("QQQ260925C00530000", ticker="QQQ"))["contracts"][0]
    assert qqq["clock_version"] == "clock.v3"
    assert qqq["clock_deadline_utc"] == "2026-09-25T20:15:00+00:00"
