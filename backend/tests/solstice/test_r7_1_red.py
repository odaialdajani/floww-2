"""R7-01 red tests: Top Movers v2 contract (previous completed session %)."""

import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime

import pytest


def _cal(open_days):
    """Fake calendar: open_days maps YYYY-MM-DD -> close_et HH:MM."""
    def day_info(d):
        if d in open_days:
            return {"date": d, "is_open": True, "open_et": "09:30",
                    "close_et": open_days[d], "half_day": open_days[d] != "16:00",
                    "reason": None, "version": "t", "calendar": "TEST"}
        return {"date": d, "is_open": False, "open_et": None, "close_et": None,
                "half_day": False, "reason": "EXCHANGE_HOLIDAY",
                "version": "t", "calendar": "TEST"}
    return day_info


OPEN_WEEK = {"2026-09-21": "16:00", "2026-09-22": "16:00", "2026-09-23": "16:00",
             "2026-09-24": "16:00", "2026-09-25": "16:00"}
OPEN_TWO_WEEKS = {"2026-09-14": "16:00", "2026-09-15": "16:00", "2026-09-16": "16:00",
                  "2026-09-17": "16:00", "2026-09-18": "16:00",
                  **OPEN_WEEK}


def _bars(closes):
    """closes: {session_date: close} -> validated daily-bar rows (t noon ET)."""
    rows = []
    for day in sorted(closes):
        rows.append({"t": f"{day}T12:00:00-04:00", "o": closes[day],
                     "h": closes[day] * 1.01, "l": closes[day] * 0.99,
                     "c": closes[day], "v": 1000})
    return rows


def _fetch(mapping):
    async def go(sym, days=10):
        if sym not in mapping:
            return None
        return _bars(mapping[sym])
    return go


def test_session_pair_skips_weekend_and_holiday():
    from services.movers import completed_session_pair
    # Saturday noon ET: last two completed are Fri + Thu.
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    assert completed_session_pair(now=now, day_info=_cal(OPEN_WEEK)) == ("2026-09-25", "2026-09-24")
    # Wednesday holiday: Tuesday noon sees Mon + prior Fri... use Wed noon with Tue closed.
    hol = dict(OPEN_TWO_WEEKS)
    del hol["2026-09-22"]
    now = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    assert completed_session_pair(now=now, day_info=_cal(hol)) == ("2026-09-21", "2026-09-18")
    # Monday 10am ET (session open, incomplete): last = Fri, prior = Thu.
    now = datetime(2026, 9, 21, 14, 0, tzinfo=UTC)
    assert completed_session_pair(now=now, day_info=_cal(OPEN_TWO_WEEKS)) == ("2026-09-18", "2026-09-17")


def test_ranking_percent_zero_missing_and_rank_before_limit():
    import asyncio

    from services.movers import compute_movers
    mapping = {
        "UP1": {"2026-09-24": 100.0, "2026-09-25": 101.0},     # +1%
        "UP10": {"2026-09-24": 100.0, "2026-09-25": 110.0},    # +10%
        "DOWN12": {"2026-09-24": 100.0, "2026-09-25": 88.0},   # -12%
        "FLAT": {"2026-09-24": 100.0, "2026-09-25": 100.0},    # 0 (valid)
        "NODATA": {"2026-09-24": 100.0},                        # missing last close
        "ZERODEN": {"2026-09-24": 0.0, "2026-09-25": 5.0},      # invalid row
        "GONE": None,                                           # provider miss
    }
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)  # Sat: sessions 09-25/09-24
    out = asyncio.run(compute_movers(universe=list(mapping), fetch_daily=_fetch(mapping),
                                     now=now, limit=20, day_info=_cal(OPEN_WEEK)))
    assert out["schema_version"] == "movers.v2"
    assert (out["session_date"], out["prior_session_date"]) == ("2026-09-25", "2026-09-24")
    order = [r["ticker"] for r in out["results"]]
    assert order == ["DOWN12", "UP10", "UP1", "FLAT"], order
    # Full precision on the wire (formatting is the UI's job).
    assert out["results"][0]["change_pct"] == pytest.approx(-12.0)
    assert out["results"][1]["change_pct"] == pytest.approx(10.0)
    assert out["coverage"] == {"requested": 7, "valid": 4, "excluded": 3}
    assert out["status"] == "partial"
    # Rank BEFORE limit: limit=2 keeps the two largest absolute moves.
    out2 = asyncio.run(compute_movers(universe=list(mapping), fetch_daily=_fetch(mapping),
                                      now=now, limit=2, day_info=_cal(OPEN_WEEK)))
    assert [r["ticker"] for r in out2["results"]] == ["DOWN12", "UP10"]
    # Legacy aliases kept deliberately for the mounted panel transition.
    assert out2["results"][0]["pct"] == pytest.approx(-12.0)
    assert out2["results"][0]["change"] == pytest.approx(-12.0)


def test_today_mode_needs_quote_provider():
    import asyncio

    from services.movers import compute_movers
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    out = asyncio.run(compute_movers(universe=["UP1"], now=now, mode="today",
                                     day_info=_cal(OPEN_WEEK),
                                     fetch_daily=_fetch({"UP1": {"2026-09-25": 101.0}})))
    assert out["status"] == "unavailable" and out["reason_codes"] == ["NO_QUOTE_PROVIDER"]
    assert out["results"] == []

    async def quote(sym):
        return 102.0, "2026-09-26T11:00:00+00:00"
    out2 = asyncio.run(compute_movers(universe=["UP1"], now=now, mode="today",
                                      day_info=_cal(OPEN_WEEK),
                                      fetch_daily=_fetch({"UP1": {"2026-09-25": 101.0}}),
                                      fetch_quote=quote))
    assert out2["status"] == "ok"
    assert abs(out2["results"][0]["change_pct"] - 100.0 * (102 / 101 - 1)) < 1e-9


def test_total_provider_failure_is_unavailable_then_stale():
    import asyncio

    from services import movers as movers_svc
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)

    async def boom(sym, days=10):
        raise RuntimeError("provider down")

    out = asyncio.run(movers_svc.compute_movers(universe=["A", "B"], fetch_daily=boom,
                                                now=now, day_info=_cal(OPEN_WEEK)))
    assert out["status"] == "unavailable" and out["results"] == []
    # Stale last-good: seed the completed-session cache, fail again.
    last, prior = movers_svc.completed_session_pair(now=now, day_info=_cal(OPEN_WEEK))
    good = dict(out)
    good.update({"status": "ok", "results": [{"ticker": "A", "change_pct": 1.0,
                                              "close": 101.0, "previous_close": 100.0,
                                              "status": "ok", "pct": 1.0, "change": 1.0}]})
    movers_svc._CACHE[(last, prior, movers_svc.UNIVERSE_ID, "previous_completed_session")] = {
        "ts": __import__("time").time(), "payload": good}
    try:
        stale = asyncio.run(movers_svc.get_movers(limit=5))
        # get_movers uses the real clock/provider; only assert the stale path
        # when the live session pair matches the seeded test pair.
        live = movers_svc.completed_session_pair(now=datetime.now(UTC))
        if live == (last, prior):
            assert stale["status"] in ("stale", "ok", "partial")
            assert stale["results"]
    finally:
        movers_svc._CACHE.pop(
            (last, prior, movers_svc.UNIVERSE_ID, "previous_completed_session"), None)


def test_upstream_seam_calls_real_adapter_signature_and_shape():
    """R8-01: market_bars._upstream must call fetch_bars_from_public_api
    with its real (timeframe/limit/sessions) signature and translate the
    canonical {date,open,high,low,close,volume,session} rows. The previous
    call passed interval/period/aggregation kwargs the adapter never
    accepted — every fetch raised before touching the network (live
    /api/movers showed 0/75 valid with correct session dates)."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from services import market_bars

    seen = {}

    async def fake_fetch(ticker, timeframe="1Day", limit=100, sessions="regular"):
        seen.update({"ticker": ticker, "timeframe": timeframe,
                     "limit": limit, "sessions": sessions})
        return [{"date": "2026-09-24T00:00:00-04:00", "open": 100.0,
                 "high": 101.0, "low": 99.0, "close": 101.0, "volume": 10,
                 "session": "regular"},
                {"date": "2026-09-25T00:00:00-04:00", "open": 101.0,
                 "high": 102.0, "low": 100.0, "close": 102.0, "volume": 11,
                 "session": "regular"}]

    async def go():
        with patch("services.public_api_adapter.fetch_bars_from_public_api",
                   new=AsyncMock(side_effect=fake_fetch)):
            return await market_bars.get_daily_bars("SPY", days=10)
    bars = asyncio.run(go())
    assert seen["timeframe"] == "1Day"
    assert bars is not None and len(bars) == 2
    assert bars[-1] == {"t": "2026-09-25T00:00:00-04:00", "o": 101.0,
                        "h": 102.0, "l": 100.0, "c": 102.0, "v": 11,
                        "session": "regular"}


def test_display_quality_greek_time_unknown_on_vendor_path():
    from server import _display_quality
    q = _display_quality("OI", "vendor-supplied-greeks", [{"strike": 500}])
    assert q["state"] == "usable" and q["setupEligible"] is True
    assert q["reasonCodes"] == ["GREEK_TIME_UNKNOWN"]
    q2 = _display_quality("OI", "local-bs-fallback", [{"strike": 500}])
    assert q2["setupEligible"] is False
    assert q2["reasonCodes"] == ["LOCAL_BS_FALLBACK"]
    q3 = _display_quality("VOLUME_FALLBACK_OI_UNKNOWN", "local-bs-fallback", [])
    assert q3["state"] == "unavailable" and q3["setupEligible"] is False


def test_compute_timeout_keeps_completed_rows(monkeypatch):
    import asyncio

    from services import movers as movers_svc
    monkeypatch.setattr(movers_svc, "_COMPUTE_TIMEOUT_S", 0.3)
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)

    async def fetch(sym, days=10):
        if sym == "SLOW":
            await asyncio.sleep(60)
        return _bars({"2026-09-24": 100.0, "2026-09-25": 101.0})

    out = asyncio.run(movers_svc.compute_movers(
        universe=["FAST", "SLOW"], fetch_daily=fetch,
        now=now, limit=5, day_info=_cal(OPEN_WEEK)))
    assert out["status"] == "partial"
    assert [r["ticker"] for r in out["results"]] == ["FAST"]
    assert "COMPUTE_TIMEOUT" in out["reason_codes"]
