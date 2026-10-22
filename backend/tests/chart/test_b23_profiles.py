"""B23 profiles. Synthetic only."""
from datetime import datetime
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")


def _ny_ts(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=_NY).timestamp()


def test_poc_ties_down_and_va():
    from services.chart_profiles import poc, value_area
    rows = [{"price": 100, "volume": 10}, {"price": 101, "volume": 10}, {"price": 102, "volume": 5}]
    assert poc(rows)["price"] == 100
    va = value_area(rows, pct=0.70)
    assert va["status"] == "ok"
    assert va["low"] <= 100 <= va["high"]
    assert value_area([], 0.7)["status"] == "unavailable"


def test_naked_levels_end_at_revisit():
    from services.chart_profiles import naked_levels
    levels = [{"price": 100.0, "session_start": "2026-10-06"}, {"price": 200.0, "session_start": "2026-10-06"}]
    bars = [{"time": "t1", "low": 90.0, "high": 95.0}, {"time": "t2", "low": 99.0, "high": 101.0}]
    out = naked_levels(levels, bars)
    assert out[0] == {"price": 100.0, "visible_from": "2026-10-06", "visible_until": "t2", "naked": False}
    assert out[1]["naked"] is True and out[1]["visible_until"] is None
    assert naked_levels([{"price": 1.0}], bars) == []


# ---- R21-04 admission contract ----


def test_admit_initial_balance_full_coverage_bounds():
    from services.chart_profiles import admit_initial_balance
    open_ts = _ny_ts(2026, 10, 21, 9, 30)
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    bars = [{"time": open_ts + i * 900, "high": 100 + i, "low": 98 + i,
             "received_at": open_ts + i * 900 + 30} for i in range(4)]
    env = admit_initial_balance(bars, ticker="SPY", cursor=cursor, bar_seconds=900,
                                session_date="2026-10-21", opening_minutes=60,
                                tick_size=0.01, units="usd", entitlement="delayed-15m")
    assert env["status"] == "available"
    assert env["bounds"] == {"low": 98.0, "high": 103.0}
    assert env["coverage"] == {"covered": 4, "expected_total": 4, "complete": True,
                               "opening_minutes": 60}
    assert env["instrument"] == {"ticker": "SPY", "tick_size": 0.01, "units": "usd",
                                 "entitlement": "delayed-15m"}
    assert env["approximation"] == "bar-resolution"
    assert env["certification"]["certified_by_hash"] is False


def test_admit_initial_balance_truncated_history_honest_paths():
    from services.chart_profiles import admit_initial_balance
    open_ts = _ny_ts(2026, 10, 21, 9, 30)
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    bars = [{"time": open_ts + i * 900, "high": 100 + i, "low": 98 + i,
             "received_at": open_ts + i * 900 + 30} for i in range(2)]
    env = admit_initial_balance(bars, ticker="SPY", cursor=cursor, bar_seconds=900,
                                session_date="2026-10-21", opening_minutes=60,
                                tick_size=0.01, units="usd", entitlement="delayed-15m")
    assert env["status"] == "unavailable"
    assert env["reason"] == "opening-history-truncated"
    assert env["coverage"]["complete"] is False

    honest = admit_initial_balance(bars, ticker="SPY", cursor=cursor, bar_seconds=900,
                                   session_date="2026-10-21", opening_minutes=60,
                                   tick_size=0.01, units="usd", entitlement="delayed-15m",
                                   allow_first_loaded_range=True)
    assert honest["status"] == "first-loaded-range"
    assert honest["coverage"]["honest_name"] == "first loaded bars range"
    assert honest["bounds"] == {"low": 98.0, "high": 101.0}
    assert honest["coverage"]["complete"] is False


def test_admit_initial_balance_midday_history_unavailable_even_when_allowed():
    from services.chart_profiles import admit_initial_balance
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    bars = [{"time": _ny_ts(2026, 10, 21, 14, 0) + i * 900, "high": 100 + i, "low": 99 + i,
             "received_at": cursor - 30} for i in range(4)]
    for allowed in (False, True):
        env = admit_initial_balance(bars, ticker="SPY", cursor=cursor, bar_seconds=900,
                                    session_date="2026-10-21", opening_minutes=60,
                                    tick_size=0.01, units="usd", entitlement="delayed-15m",
                                    allow_first_loaded_range=allowed)
        assert env["status"] == "unavailable"
        assert env["reason"] == "opening-history-absent"
        assert env["gaps"]["outside_opening_window"] == 4


def test_admit_initial_balance_incomplete_window_and_gapped_history():
    from services.chart_profiles import admit_initial_balance
    open_ts = _ny_ts(2026, 10, 21, 9, 30)
    cursor = _ny_ts(2026, 10, 21, 10, 0)
    bars = [{"time": open_ts + i * 900, "high": 100 + i, "low": 98 + i,
             "received_at": open_ts + i * 900 + 30} for i in range(2)]
    env = admit_initial_balance(bars, ticker="SPY", cursor=cursor, bar_seconds=900,
                                session_date="2026-10-21", opening_minutes=60,
                                tick_size=0.01, units="usd", entitlement="delayed-15m")
    assert env["status"] == "unavailable"
    assert env["reason"] == "opening-window-incomplete-at-cursor"

    late_cursor = _ny_ts(2026, 10, 21, 10, 31)
    gapped = [
        {"time": open_ts, "high": 100, "low": 98, "received_at": open_ts + 30},
        {"time": open_ts + 2 * 900, "high": 102, "low": 99, "received_at": open_ts + 2 * 900 + 30},
        {"time": open_ts + 3 * 900, "high": 103, "low": 100, "received_at": open_ts + 3 * 900 + 30},
    ]
    gapped_env = admit_initial_balance(gapped, ticker="SPY", cursor=late_cursor, bar_seconds=900,
                                       session_date="2026-10-21", opening_minutes=60,
                                       tick_size=0.01, units="usd", entitlement="delayed-15m",
                                       allow_first_loaded_range=True)
    assert gapped_env["status"] == "unavailable"
    assert gapped_env["reason"] == "opening-history-gapped"


def test_admit_initial_balance_refuses_implicit_selection_and_metadata():
    from services.chart_profiles import admit_initial_balance
    cursor = _ny_ts(2026, 10, 21, 10, 31)

    def _try(**over):
        base = dict(ticker="SPY", cursor=cursor, bar_seconds=900, tick_size=0.01,
                    units="usd", entitlement="delayed-15m", session_date="2026-10-21",
                    opening_minutes=60)
        base.update(over)
        return admit_initial_balance([], **base)

    assert _try(session_date=None)["reason"] == "unsupported-session-date"
    assert _try(session_date="2026-10-24")["reason"] == "unsupported-session-date"
    assert _try(opening_minutes=7)["reason"] == "opening-duration-not-grid-divisible"
    assert _try(opening_minutes=400)["reason"] == "opening-duration-exceeds-session"
    assert _try(tick_size=None)["reason"] == "instrument-tick-not-explicit"
    assert _try(units=None)["reason"] == "instrument-units-not-explicit"
    assert _try(entitlement=None)["reason"] == "entitlement-not-explicit"
    assert _try(cursor=_ny_ts(2026, 10, 22, 10, 31))["reason"] == "cursor-not-in-selected-session"
    assert _try(bar_seconds=90)["reason"] == "unsupported-bar-seconds"


def test_admit_delta_capability_must_be_explicit():
    from services.chart_delta import admit_delta
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    kw = dict(ticker="SPY", cursor=cursor, bar_seconds=60, tick_size=0.01,
              units="usd", entitlement="delayed-15m")
    assert admit_delta([], capabilities=None, **kw)["reason"] == \
        "capability-not-declared: classified_sizes"
    assert admit_delta([], capabilities={"classified_sizes": False}, **kw)["reason"] == \
        "capability-not-declared: classified_sizes"
    assert admit_delta([], capabilities={"classified_sizes": True, **{}}, tick_size=None,
                       units="usd", entitlement="x", cursor=cursor, bar_seconds=60,
                       ticker="SPY")["reason"] == "instrument-tick-not-explicit"


def test_admit_delta_running_rows_correction_supersede_and_gaps():
    from services.chart_delta import admit_delta
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    rows = [
        {"ticker": "SPY", "buy": 10, "sell": 4,
         "event_time": cursor + 10, "received_at": cursor - 30},
        {"ticker": "SPY", "buy": 20, "sell": 4, "corrected": True,
         "event_time": cursor + 10, "received_at": cursor - 10},
        {"ticker": "QQQ", "buy": 99, "sell": 1,
         "event_time": cursor + 20, "received_at": cursor - 20},
        {"ticker": "SPY", "event_time": cursor + 30, "received_at": cursor - 15},
        {"ticker": "SPY", "buy": 50, "sell": 0,
         "event_time": cursor + 40, "received_at": cursor + 5},
        {"ticker": "SPY", "buy": 2, "sell": 1, "unclassified": 7,
         "event_time": _ny_ts(2026, 10, 21, 9, 20), "received_at": cursor - 200},
    ]
    env = admit_delta(rows, ticker="SPY", cursor=cursor, bar_seconds=60,
                      capabilities={"classified_sizes": True}, tick_size=0.01,
                      units="usd", entitlement="delayed-15m")
    assert env["status"] == "available"
    assert env["totals"] == {"delta": 16.0, "classified_volume": 24.0,
                             "unclassified_volume": 0.0}
    assert len(env["rows"]) == 1
    assert env["rows"][0]["open"] == 0
    assert env["rows"][0]["close"] == 16.0
    assert env["rows"][0]["delta"] == 16.0
    gaps = env["gaps"]
    assert gaps["superseded_by_correction"] == 1
    assert gaps["foreign_instrument"] == 1
    assert gaps["unclassified_bar"] == 1
    assert gaps["late_receipt"] == 1
    assert gaps["previous_session"] == 1
    assert env["capabilities"] == {"classified_sizes": True}
    assert env["certification"]["certified_by_hash"] is False


def test_admit_delta_session_reset_and_no_eligible_rows():
    from services.chart_delta import admit_delta
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    kw = dict(ticker="SPY", cursor=cursor, bar_seconds=60,
              capabilities={"classified_sizes": True}, tick_size=0.01,
              units="usd", entitlement="delayed-15m")
    env = admit_delta([], **kw)
    assert env["status"] == "unavailable"
    assert env["reason"] == "no eligible classified bars"
    assert env["totals"] is None

    reset_rows = [
        {"ticker": "SPY", "buy": 10, "sell": 2, "session_reset": True,
         "event_time": cursor + 5, "received_at": cursor - 20},
        {"ticker": "SPY", "buy": 1, "sell": 6, "unclassified": 5,
         "event_time": cursor + 15, "received_at": cursor - 10},
    ]
    env = admit_delta(reset_rows, **kw)
    assert env["rows"][0]["close"] == 8
    assert env["rows"][1]["open"] == 8
    assert env["rows"][1]["close"] == 3
    assert env["rows"][1]["unclassified"] == 5
    assert env["totals"]["delta"] == 3
    assert env["totals"]["unclassified_volume"] == 5.0


def test_admit_darkpool_prints_exact_supersede_and_direction_unknown():
    from services.chart_darkpool import admit_darkpool_prints
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    base = {"ticker": "SPY", "event_time": _ny_ts(2026, 10, 21, 10, 0, 15),
            "received_at": cursor - 45}
    prints = [
        dict(base, price=100.0, size=500, venue="XYZ", print_id=1, delay_seconds=60),
        dict(base, price=99.5, size=500, venue="XYZ", print_id=2, correction_of=1,
             delay_seconds=60),
        dict(base, price=98.0, size=900, venue="ABC", aggregate=True, delay_seconds=60),
        dict(base, price=97.0, size=900, venue="ABC", asset_class="future", delay_seconds=60),
        dict(base, price=96.0, size=900, venue="ABC", received_at=cursor + 5, delay_seconds=60),
        dict(base, price=95.0, size=900, venue="ABC", delay_seconds=9_001),
    ]
    env = admit_darkpool_prints(prints, ticker="SPY", cursor=cursor, bar_seconds=60,
                                tick_size=0.01, units="usd", entitlement="delayed-15m",
                                max_delay_seconds=900)
    assert env["status"] == "available"
    assert len(env["prints"]) == 1
    assert env["prints"][0]["price"] == 99.5
    assert env["prints"][0]["direction"] == "unknown"
    assert env["top"][0]["notional"] == 99.5 * 500
    gaps = env["gaps"]
    assert gaps["superseded_by_correction"] == 1
    assert gaps["aggregated_row"] == 1
    assert gaps["non_equity_row"] == 1
    assert gaps["late_receipt"] == 1
    assert gaps["delay_unknown_or_over_cap"] == 1
    assert env["instrument"]["entitlement"] == "delayed-15m"


def test_admit_darkpool_no_eligible_prints_stays_unavailable():
    from services.chart_darkpool import admit_darkpool_prints
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    env = admit_darkpool_prints([], ticker="SPY", cursor=cursor, bar_seconds=60,
                                tick_size=0.01, units="usd", entitlement="delayed-15m")
    assert env["status"] == "unavailable"
    assert env["reason"] == "no eligible dark-pool prints"
    assert env["prints"] == []


def test_admit_delta_counts_unclassified_only_bar_and_drops_empty_bars():
    from services.chart_delta import admit_delta
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    kw = dict(ticker="SPY", cursor=cursor, bar_seconds=60,
              capabilities={"classified_sizes": True}, tick_size=0.01,
              units="usd", entitlement="delayed-15m")
    env = admit_delta([
        {"ticker": "SPY", "unclassified": 5,
         "event_time": cursor + 10, "received_at": cursor - 30},
        {"ticker": "SPY", "buy": 3, "sell": 1,
         "event_time": cursor + 30, "received_at": cursor - 30},
        {"ticker": "SPY",
         "event_time": cursor + 40, "received_at": cursor - 30},
    ], **kw)
    assert env["status"] == "available"
    assert env["totals"] == {"delta": 2.0, "classified_volume": 4.0,
                             "unclassified_volume": 5.0}
    assert env["gaps"]["unclassified_bar"] == 1
    assert len(env["rows"]) == 2


def test_admit_darkpool_delay_boundary_and_unknown_correction():
    from services.chart_darkpool import admit_darkpool_prints
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    base = {"ticker": "SPY", "price": 100.0, "size": 10, "venue": "XYZ",
            "event_time": _ny_ts(2026, 10, 21, 10, 0, 15), "received_at": cursor - 45}
    # delay exactly at the cap is admitted, one second over is named
    env = admit_darkpool_prints([dict(base, print_id=1, delay_seconds=900)],
                                ticker="SPY", cursor=cursor, bar_seconds=60,
                                tick_size=0.01, units="usd", entitlement="delayed-15m",
                                max_delay_seconds=900)
    assert env["status"] == "available" and len(env["prints"]) == 1
    over = admit_darkpool_prints([dict(base, print_id=1, delay_seconds=901)],
                                 ticker="SPY", cursor=cursor, bar_seconds=60,
                                 tick_size=0.01, units="usd", entitlement="delayed-15m",
                                 max_delay_seconds=900)
    assert over["status"] == "unavailable"
    assert over["gaps"]["delay_unknown_or_over_cap"] == 1
    # a correction whose original is not in the eligible set stays itself
    alone = admit_darkpool_prints(
        [dict(base, print_id=2, correction_of=1)],
        ticker="SPY", cursor=cursor, bar_seconds=60,
        tick_size=0.01, units="usd", entitlement="delayed-15m")
    assert alone["status"] == "available" and len(alone["prints"]) == 1
    assert alone["gaps"]["superseded_by_correction"] == 0


def test_naked_claim_requires_coverage_and_known_range():
    from services.chart_profiles import naked_levels_claim
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    coverage = {"low": 90.0, "high": 110.0}
    levels = [{"price": 100.0, "session_start": "2026-10-20"},
              {"price": 120.0, "session_start": "2026-10-20"}]
    bars = [
        {"time": _ny_ts(2026, 10, 21, 10, 20), "low": 95.0, "high": 101.0,
         "received_at": cursor - 600},
        {"time": _ny_ts(2026, 10, 21, 10, 25), "low": 104.0, "high": 108.0,
         "received_at": cursor - 300},
        {"time": _ny_ts(2026, 10, 21, 10, 45), "low": 99.0, "high": 100.5,
         "received_at": cursor - 60},
    ]
    env = naked_levels_claim(levels, bars, cursor=cursor, coverage=coverage)
    assert env["status"] == "available"
    claims = env["claims"]
    assert claims[0]["naked"] is False
    assert claims[0]["visible_until"] == _ny_ts(2026, 10, 21, 10, 20)
    assert claims[1]["status"] == "not-claimable"
    assert claims[1]["reason"] == "level-outside-known-range"
    assert claims[1]["naked"] is None
    assert env["gaps"]["future_bar"] == 1

    unknown = naked_levels_claim(levels, bars, cursor=cursor, coverage=None)
    assert unknown["status"] == "not-claimable"
    assert unknown["reason"] == "unknown-range-cannot-certify-untouched"
    assert unknown["claims"] == []

    narrow = naked_levels_claim([{"price": 100.0, "session_start": "2026-10-20"}],
                                bars, cursor=cursor, coverage={"low": 102.0, "high": 104.0})
    assert narrow["claims"][0]["status"] == "not-claimable"
    assert narrow["claims"][0]["reason"] == "level-outside-known-range"


# ---- schedule honesty + determinism hardening (2025-2026 published schedule) ----


def test_admit_initial_balance_refuses_holidays_and_uses_early_close():
    from services.chart_profiles import admit_initial_balance
    kw = dict(ticker="SPY", bar_seconds=900, tick_size=0.01, units="usd",
              entitlement="delayed-15m")
    assert admit_initial_balance([], session_date="2026-11-26", opening_minutes=60,
                                 cursor=_ny_ts(2026, 11, 26, 10, 31),
                                 **kw)["reason"] == "unsupported-session-date"
    assert admit_initial_balance([], session_date="2025-01-09", opening_minutes=60,
                                 cursor=_ny_ts(2025, 1, 9, 10, 31),
                                 **kw)["reason"] == "unsupported-session-date"
    assert admit_initial_balance([], session_date="2026-07-03", opening_minutes=60,
                                 cursor=_ny_ts(2026, 7, 3, 10, 31),
                                 **kw)["reason"] == "unsupported-session-date"
    assert admit_initial_balance([], session_date="2027-11-25", opening_minutes=60,
                                 cursor=_ny_ts(2027, 11, 25, 10, 31),
                                 **kw)["reason"] == "unsupported-session-date"
    open_ts = _ny_ts(2025, 12, 24, 9, 30)
    bars = [{"time": open_ts + i * 900, "high": 100 + i, "low": 98 + i,
             "received_at": open_ts + i * 900 + 30} for i in range(4)]
    env = admit_initial_balance(bars, session_date="2025-12-24", opening_minutes=60,
                                cursor=_ny_ts(2025, 12, 24, 10, 31), **kw)
    assert env["status"] == "available"
    assert env["session"]["end"] == _ny_ts(2025, 12, 24, 13, 0)
    bleed = admit_initial_balance([], session_date="2025-12-24", opening_minutes=300,
                                  cursor=_ny_ts(2025, 12, 24, 12, 55), **kw)
    assert bleed["reason"] == "opening-exceeds-session"
    exact = admit_initial_balance([], session_date="2025-12-24", opening_minutes=210,
                                  cursor=_ny_ts(2025, 12, 24, 12, 55), **kw)
    # opening == close passes the structural gate, then meets the honest
    # time gate: no in-session cursor can see that opening complete.
    assert exact["status"] == "unavailable"
    assert exact["reason"] == "opening-window-incomplete-at-cursor"


def test_admit_initial_balance_duplicate_bar_ts_is_deterministic_first_write():
    from services.chart_profiles import admit_initial_balance
    open_ts = _ny_ts(2026, 10, 21, 9, 30)
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    bars = [{"time": open_ts + i * 900, "high": 100 + i, "low": 98 + i,
             "received_at": open_ts + i * 900 + 30} for i in range(4)]
    duplicate = dict(bars[0])
    duplicate["high"] = 999.0
    env = admit_initial_balance(bars + [duplicate], ticker="SPY", cursor=cursor,
                                bar_seconds=900, session_date="2026-10-21",
                                opening_minutes=60, tick_size=0.01, units="usd",
                                entitlement="delayed-15m")
    assert env["status"] == "available"
    assert env["bounds"] == {"low": 98.0, "high": 103.0}
    assert env["gaps"]["duplicate_bar"] == 1


def test_naked_claim_refuses_no_eligible_bars():
    from services.chart_profiles import naked_levels_claim
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    level = [{"price": 100.0, "session_start": "2026-10-20"}]
    future_only = naked_levels_claim(
        level,
        [{"time": _ny_ts(2026, 10, 21, 10, 40), "low": 99.0, "high": 101.0,
          "received_at": cursor - 10}],
        cursor=cursor, coverage={"low": 90.0, "high": 110.0})
    assert future_only["gaps"]["future_bar"] == 1
    assert future_only["claims"][0]["status"] == "not-claimable"
    assert future_only["claims"][0]["reason"] == "no-eligible-bars-known"
    assert future_only["claims"][0]["naked"] is None
    none_at_all = naked_levels_claim(level, [], cursor=cursor,
                                     coverage={"low": 90.0, "high": 110.0})
    assert none_at_all["claims"][0]["reason"] == "no-eligible-bars-known"
    observed = naked_levels_claim(
        level,
        [{"time": _ny_ts(2026, 10, 21, 10, 25), "low": 99.5, "high": 100.5,
          "received_at": cursor - 10}],
        cursor=cursor, coverage={"low": 90.0, "high": 110.0})
    assert observed["claims"][0]["naked"] is False
    unvisited = naked_levels_claim(
        level,
        [{"time": _ny_ts(2026, 10, 21, 10, 25), "low": 101.0, "high": 102.0,
          "received_at": cursor - 10}],
        cursor=cursor, coverage={"low": 90.0, "high": 110.0})
    assert unvisited["claims"][0]["naked"] is True
