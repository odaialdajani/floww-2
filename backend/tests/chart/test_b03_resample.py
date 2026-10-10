"""B03 calendar-aware bars: independent interval/range/session.

Synthetic only. RED before chart_resample.py exists.
"""
from datetime import UTC, datetime, timedelta


def _bar(t, o=100.0, h=101.0, low=99.0, c=100.5):
    return {"time": t, "open": o, "high": h, "low": low, "close": c}


def test_old_days_mapping_preserved():
    from services.chart_resample import days_to_interval

    assert days_to_interval(1) == (60, "1m")
    assert days_to_interval(5) == (300, "5m")
    assert days_to_interval(20) == (3600, "1h")


def test_monday_week_and_session_bounds():
    from services.chart_resample import bucket_start, is_rth

    # Monday 2026-10-05 09:30 ET = 13:30 UTC (EDT).
    monday_open = datetime(2026, 10, 5, 13, 30, tzinfo=UTC)
    assert bucket_start(monday_open.isoformat(), 60) <= monday_open
    # RTH 9:30-16:00 ET; pre-open 8:00 ET is not RTH.
    assert is_rth(datetime(2026, 10, 6, 13, 30, tzinfo=UTC).isoformat()) is True
    assert is_rth(datetime(2026, 10, 6, 12, 0, tzinfo=UTC).isoformat()) is False


def test_monday_week_anchor():
    from services.chart_resample import week_start

    # Wednesday 2026-10-07 belongs to the Monday 2026-10-05 week.
    assert week_start("2026-10-07T15:30:00+00:00").isoformat() == "2026-10-05T04:00:00+00:00"
    assert week_start("not-a-time") is None


def test_custom_bins_need_complete_base():
    from services.chart_resample import resample_bars

    base = "2026-10-06T13:30:00+00:00"
    bars = [
        {**_bar((datetime.fromisoformat(base) + timedelta(minutes=i)).isoformat()), "volume": 10}
        for i in range(7)
    ]
    out7 = resample_bars(bars, interval_minutes=7, session="rth")
    assert len(out7) == 1 and out7[0]["complete"] is True
    out7_gap = resample_bars(bars[:6], interval_minutes=7, session="rth")
    assert out7_gap == [] or out7_gap[0]["complete"] is False
    # Never interpolate: missing base minutes yield no bucket, not filler.
    out90 = resample_bars(bars, interval_minutes=90, session="rth")
    assert out90 == [] or all(b["complete"] is False for b in out90)
