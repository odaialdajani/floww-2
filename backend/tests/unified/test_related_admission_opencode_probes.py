"""OpenCode probe slice for U06 (claim record in docs/unified/U06/OPENCODE-CLAIM.md).

NEW probes only — no source edits. Pure-function level: correlation pairing,
clocks, registry membership. Warming/cancellation/storage probes are Cline's
deeper slice (store design decisions). Isolated: injected windows, synthetic
bars from the real session calendar, tmp registry files. No provider calls.
"""
import json
from datetime import UTC, datetime, timedelta

import pytest

from routes.related_tickers import registry_related
from services.agent.access.horizon import _calendar
from services.related_correlations import compare_series


def sessions(n):
    # Only sessions whose close is complete: today's session (if any) is
    # excluded because its close lies in the future before 16:00 ET and no
    # observed series can validate against it. Anchor on the last actual
    # session so weekends/holidays never pass a non-session end.
    from datetime import date, timedelta
    cal = _calendar()
    today = datetime.now(UTC).date().isoformat()
    anchor = datetime.now(UTC).date()
    for _ in range(10):
        if cal.is_session(anchor.isoformat()):
            break
        anchor -= timedelta(days=1)
    past = [s.date().isoformat() for s in cal.sessions_window(anchor.isoformat(), -(n + 5)) if s.date().isoformat() < today]
    return past[-n:]


def bars(ticker, days, *, start=100.0, step=0.7, drop=frozenset(), event=None, received=None):
    rows = []
    price = start
    for i, day in enumerate(days):
        if day in drop:
            continue
        price = round(price + (step if i % 2 == 0 else -step * 0.6), 2)
        rows.append({"date": day, "close": price})
    return {"ticker": ticker, "bars": rows, "event_time": event, "received_at": received}


def clocks_for(days, now):
    cal = _calendar()
    last = max(d for d in days)
    event = cal.session_close(last).to_pydatetime().replace(tzinfo=UTC).isoformat() if hasattr(
        cal.session_close(last), "to_pydatetime") else None
    if event is None:
        import datetime as dt
        event = dt.datetime.combine(dt.date.fromisoformat(last),
                                    dt.time(20, 0), tzinfo=UTC).isoformat()
    received = (datetime.fromisoformat(event) + timedelta(hours=1)).isoformat()
    return event, received


def window_for(days, now):
    return days, (datetime.fromisoformat(clocks_for(days, now)[0]) + timedelta(hours=2)).isoformat()


def test_missing_days_are_skipped_never_filled():
    days = sessions(40)
    now = datetime.now(UTC)
    gap = frozenset([days[len(days) // 2]])
    event, received = clocks_for([d for d in days if d not in gap], now)
    left = bars("SPY", days, event=event, received=received)
    right = bars("QQQ", days, start=50.0, step=0.4, event=event, received=received)
    # remove the gap day from both (bars() drops it)
    left = bars("SPY", days, event=event, received=received, drop=gap)
    right = bars("QQQ", days, start=50.0, step=0.4, event=event, received=received, drop=gap)
    # NOTE: the window must carry the FULL calendar including the gap day;
    # only the bars lack it. That is what makes the two gap-touching pairs
    # refuse (both rows present check) instead of bridging the gap.
    result = compare_series(left, right, window=30, now=now, _window=window_for(days, now))
    # 39 calendar adjacencies minus the 2 touching the gap day
    assert result["paired_returns"] == len(days) - 1 - 2
    assert result["status"] in ("available", "partial", "stale")
    assert result["coefficient"] is not None


def test_null_zero_variance_is_typed_not_numeric():
    days = sessions(40)
    now = datetime.now(UTC)
    flat = [{"date": d, "close": 100.0} for d in days]
    event, received = clocks_for(days, now)
    left = {"ticker": "SPY", "bars": flat, "event_time": event, "received_at": received}
    right = {"ticker": "QQQ", "bars": [dict(b) for b in flat], "event_time": event, "received_at": received}
    result = compare_series(left, right, window=30, now=now, _window=window_for(days, now))
    assert result["reason"] == "zero_variance"
    assert result["coefficient"] is None


def test_clock_violations_refuse():
    days = sessions(40)
    now = datetime.now(UTC)
    event, received = clocks_for(days, now)
    good = bars("SPY", days, event=event, received=received)
    # event after receipt
    bad = bars("QQQ", days, event=received, received=event)
    result = compare_series(good, bad, window=30, now=now, _window=window_for(days, now))
    assert result["reason"] == "invalid_series_clock"
    # receipt in the future
    future = (now + timedelta(days=1)).isoformat()
    bad2 = bars("QQQ", days, event=event, received=future)
    result2 = compare_series(good, bad2, window=30, now=now, _window=window_for(days, now))
    assert result2["reason"] == "invalid_series_clock"


def test_self_comparison_excluded():
    days = sessions(40)
    now = datetime.now(UTC)
    event, received = clocks_for(days, now)
    one = bars("SPY", days, event=event, received=received)
    other = bars("SPY", days, event=event, received=received)
    result = compare_series(one, other, window=30, now=now, _window=window_for(days, now))
    assert result["reason"] == "self_comparison_excluded"


def _registry_file(tmp_path, products):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"version": 1, "products": products}), encoding="utf-8")
    return str(path)


def _entry(symbol, **over):
    base = {"symbol": symbol, "underlying": "SPY", "benchmark": None,
            "source_urls": ["https://example.invalid/x"], "verified_at": "2026-10-01"}
    base.update(over)
    return base


def test_registry_membership_is_independent(tmp_path):
    path = _registry_file(tmp_path, [_entry("AAA"), _entry("BBB", underlying="QQQ"),
                                     _entry("CCC", underlying="SPY")])
    products, coverage = registry_related("AAA", {"symbols": [], "available": False}, registry_path=path)
    names = [p["symbol"] for p in products]
    assert "CCC" in names and "BBB" not in names and "AAA" not in names
    assert coverage["available"] is True and coverage["complete"] is False
    assert all(p["provider_listed"] is None for p in products)


def test_registry_skips_malformed_entries_and_missing_file(tmp_path):
    path = _registry_file(tmp_path, [_entry("AAA"), {"symbol": "BAD", "underlying": "SPY"},
                                     _entry("NOURL", source_urls=["http://plain-http.invalid"]),
                                     _entry("NODATE", verified_at="not-a-date")])
    products, _ = registry_related("AAA", {"symbols": ["AAA"], "available": True,
                                            "asof": "x", "stale": False}, registry_path=path)
    # Malformed entries are skipped; the selected symbol's underlying stock is
    # included by design (underlying_stock synthesis, not registry admission).
    assert [p["symbol"] for p in products] == ["SPY"]
    assert products[0]["product_type"] == "underlying_stock"
    missing, coverage = registry_related("AAA", {}, registry_path=str(tmp_path / "absent.json"))
    assert missing == [] and coverage["reason"] == "registry_unavailable"
