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
    assert clock.last_trading_utc("2026-09-25", ticker="SPY", option_root="SPY") == datetime(2026, 9, 25, 20, 15, tzinfo=UTC)


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


def test_analytical_etf_time_does_not_open_entry_window():
    from services.solstice_session import session_state
    for at in (datetime(2026, 9, 25, 20, 5, tzinfo=UTC), datetime(2026, 9, 25, 20, 15, tzinfo=UTC)):
        state = session_state(now=at, quality={"state": "usable", "reasonCodes": []})
        assert state["entry_allowed"] is False
        assert state["management_allowed"] is True
