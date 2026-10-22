"""B20 flow. Synthetic only."""
from datetime import datetime
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")


def _ny_ts(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=_NY).timestamp()


def test_buckets():
    from services.chart_flow import bucket_hash, bucketize
    assert bucket_hash("b", "w", {"x": 1}) == bucket_hash("b", "w", {"x": 1})
    out = bucketize([{"side": "call", "premium": 100}, {"side": "put", "premium": 40}, {"side": "?", "premium": 5}])
    assert out["call_premium"] == 100
    assert out["put_premium"] == -40
    assert out["unknown"] == 1
    assert out["top"][0]["premium"] == 100


# ---- R21-03 admission contract: buckets are derived, never claimed ----


def test_admit_flow_bucket_derives_owning_interval_window_and_bucket_index():
    from services.chart_flow import admit_flow_bucket
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    rows = [
        {"ticker": "SPY", "side": "call", "premium": 120.0,
         "event_time": cursor + 20, "received_at": cursor - 30},
        {"ticker": "SPY", "side": "put", "premium": 40.0,
         "event_time": cursor + 40, "received_at": cursor - 25},
    ]
    env = admit_flow_bucket(rows, ticker="spy", cursor=cursor, bar_seconds=60)
    assert env["status"] == "available"
    assert env["window"] == {"start": cursor, "end": cursor + 60}
    assert env["bucket_index"] == 61
    assert env["session"]["date"] == "2026-10-21"
    assert env["totals"]["call_premium"] == 120.0
    assert env["totals"]["put_premium"] == -40.0
    assert env["totals"]["count"] == 2
    assert env["totals"]["unknown"] == 0
    assert env["gaps"]["foreign_instrument"] == 0
    assert env["certification"]["certified_by_hash"] is False
    assert env["certification"]["basis"].startswith("row-level")


def test_admit_flow_bucket_reports_foreign_future_previous_sessions_late_rows():
    from services.chart_flow import admit_flow_bucket
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    rows = [
        {"ticker": "QQQ", "side": "call", "premium": 999.0,
         "event_time": cursor + 20, "received_at": cursor - 30},
        {"ticker": "SPY", "side": "put", "premium": 11.0,
         "event_time": _ny_ts(2026, 10, 20, 15, 0), "received_at": cursor - 30},
        {"ticker": "SPY", "side": "put", "premium": 12.0,
         "event_time": cursor + 300, "received_at": cursor - 30},
        {"ticker": "SPY", "side": "call", "premium": 13.0,
         "event_time": cursor - 30, "received_at": cursor - 60},
        {"ticker": "SPY", "side": "call", "premium": 14.0,
         "event_time": cursor + 20, "received_at": cursor + 5},
    ]
    env = admit_flow_bucket(rows, ticker="SPY", cursor=cursor, bar_seconds=60)
    assert env["status"] == "unavailable"
    assert env["totals"] is None
    assert env["admitted_count"] == 0
    gaps = env["gaps"]
    assert gaps["foreign_instrument"] == 1
    assert gaps["previous_session"] == 1
    assert gaps["future_event"] == 1
    assert gaps["stale_event"] == 1
    assert gaps["late_receipt"] == 1
    assert env["filters_applied"] == {}


def test_admit_flow_bucket_filters_actually_select_admitted_rows():
    from services.chart_flow import admit_flow_bucket
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    rows = [
        {"ticker": "SPY", "side": "call", "premium": 100.0,
         "event_time": cursor + 10, "received_at": cursor - 30},
        {"ticker": "SPY", "side": "call", "premium": 5.0,
         "event_time": cursor + 20, "received_at": cursor - 30},
        {"ticker": "SPY", "side": "put", "premium": 80.0,
         "event_time": cursor + 30, "received_at": cursor - 30},
    ]
    env = admit_flow_bucket(rows, ticker="SPY", cursor=cursor, bar_seconds=60,
                            filters={"min_premium": 50})
    assert env["status"] == "available"
    assert env["totals"]["call_premium"] == 100.0
    assert env["totals"]["count"] == 2
    assert env["gaps"]["filtered_out"] == 1
    assert env["filters_applied"] == {"min_premium": 50.0}

    env_side = admit_flow_bucket(rows, ticker="SPY", cursor=cursor, bar_seconds=60,
                                 filters={"side": "call"})
    assert env_side["totals"]["count"] == 2
    assert env_side["totals"]["call_premium"] == 105.0
    assert env_side["gaps"]["filtered_out"] == 1
    assert env_side["filters_applied"] == {"side": "call"}


def test_admit_flow_bucket_refuses_unsupported_filters_and_intervals():
    from services.chart_flow import admit_flow_bucket
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    rows = [{"ticker": "SPY", "side": "call", "premium": 1.0,
             "event_time": cursor + 10, "received_at": cursor - 30}]
    assert admit_flow_bucket(rows, ticker="SPY", cursor=cursor, bar_seconds=60,
                             filters={"bogus": 1}) == {"status": "refused",
                                                       "reason": "unsupported-filter"}
    assert admit_flow_bucket(rows, ticker="SPY", cursor=cursor, bar_seconds=90) == \
        {"status": "refused", "reason": "unsupported-bar-seconds"}
    assert admit_flow_bucket(rows, ticker="SPY", cursor=_ny_ts(2026, 10, 21, 17, 0),
                             bar_seconds=60) == {"status": "refused",
                                                 "reason": "cursor-not-in-regular-session"}
    assert admit_flow_bucket(rows, ticker="SPY", cursor=_ny_ts(2026, 10, 24, 11, 0),
                             bar_seconds=60) == {"status": "refused",
                                                 "reason": "cursor-not-in-regular-session"}
    assert admit_flow_bucket(rows, ticker="", cursor=cursor, bar_seconds=60) == \
        {"status": "refused", "reason": "instrument-not-explicit"}


def test_matching_locally_generated_hash_alone_cannot_certify_a_bucket():
    from services.chart_flow import admit_flow_bucket, bucket_hash
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    identity = bucket_hash(61, "1m", {})
    env = admit_flow_bucket(None, ticker="SPY", cursor=cursor, bar_seconds=60,
                            caller_scope_hash=identity)
    assert env["status"] == "unavailable"
    assert env["totals"] is None
    assert env["certification"]["certified_by_hash"] is False
    assert env["certification"]["basis"].startswith("row-level")
    assert env["certification"]["caller_scope_hash"] == identity


def test_admit_flow_bucket_scope_hash_tracks_exact_filter_identity():
    from services.chart_flow import admit_flow_bucket
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    row = {"ticker": "SPY", "side": "call", "premium": 3.0,
           "event_time": cursor + 15, "received_at": cursor - 30}
    env = admit_flow_bucket([row], ticker="SPY", cursor=cursor, bar_seconds=60)
    same = admit_flow_bucket([row], ticker="SPY", cursor=cursor, bar_seconds=60)
    other = admit_flow_bucket([row], ticker="SPY", cursor=cursor, bar_seconds=60,
                              filters={"side": "call"})
    assert env["scope_hash"] == same["scope_hash"]
    assert env["scope_hash"] != other["scope_hash"]


def test_admit_flow_bucket_reports_malformed_and_receiptless_rows():
    from services.chart_flow import admit_flow_bucket
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    rows = [
        None,
        {"event_time": cursor + 10, "received_at": cursor - 30},
        {"ticker": "SPY", "received_at": cursor - 30},
        {"ticker": "SPY", "event_time": cursor + 10},
    ]
    env = admit_flow_bucket(rows, ticker="SPY", cursor=cursor, bar_seconds=60)
    assert env["status"] == "unavailable"
    assert env["gaps"]["malformed_row"] == 3
    assert env["gaps"]["missing_receipt"] == 1


# ---- schedule honesty: published NYSE holidays and early closes (2025-2026) ----


def test_session_bounds_refuse_published_holidays():
    from services.chart_flow import session_bounds
    assert session_bounds(_ny_ts(2026, 11, 26, 10, 31)) is None      # Thanksgiving 2026
    assert session_bounds(_ny_ts(2025, 11, 27, 10, 31)) is None      # Thanksgiving 2025
    assert session_bounds(_ny_ts(2025, 1, 9, 10, 31)) is None        # Carter national mourning
    assert session_bounds(_ny_ts(2026, 7, 3, 10, 31)) is None        # Independence (observed)
    assert session_bounds(_ny_ts(2026, 6, 19, 10, 31)) is None       # Juneteenth 2026
    assert session_bounds(_ny_ts(2027, 11, 25, 10, 31)) is None      # Thanksgiving 2027
    assert session_bounds(_ny_ts(2027, 6, 18, 10, 31)) is None       # Juneteenth observed 2027
    assert session_bounds(_ny_ts(2027, 7, 5, 10, 31)) is None        # Independence observed 2027
    assert session_bounds(_ny_ts(2027, 12, 24, 10, 31)) is None      # Christmas observed 2027
    assert session_bounds(_ny_ts(2028, 4, 14, 10, 31)) is None       # Good Friday 2028
    assert session_bounds(_ny_ts(2028, 7, 4, 10, 31)) is None        # Independence Day 2028


def test_schedule_covers_regular_in_table_weekdays():
    from services.chart_flow import session_bounds
    good_2027 = session_bounds(_ny_ts(2027, 1, 5, 10, 31))
    assert good_2027 is not None
    assert good_2027["end"] == _ny_ts(2027, 1, 5, 16, 0)
    good_2028 = session_bounds(_ny_ts(2028, 10, 2, 10, 31))
    assert good_2028 is not None
    assert session_bounds(_ny_ts(2028, 1, 1, 10, 31)) is None        # Saturday


def test_session_bounds_use_early_close_days():
    from services.chart_flow import session_bounds
    bounds = session_bounds(_ny_ts(2025, 12, 24, 12, 55))
    assert bounds is not None
    assert bounds["end"] == _ny_ts(2025, 12, 24, 13, 0)
    assert session_bounds(_ny_ts(2025, 12, 24, 13, 5)) is None
    assert session_bounds(_ny_ts(2026, 11, 27, 11, 0)) is not None   # early close day is a session
    early_2027 = session_bounds(_ny_ts(2027, 11, 26, 12, 55))
    assert early_2027 is not None
    assert early_2027["end"] == _ny_ts(2027, 11, 26, 13, 0)
    assert session_bounds(_ny_ts(2027, 11, 26, 13, 5)) is None
    early_2028 = session_bounds(_ny_ts(2028, 7, 3, 11, 0))
    assert early_2028 is not None and early_2028["end"] == _ny_ts(2028, 7, 3, 13, 0)
    assert session_bounds(_ny_ts(2028, 11, 24, 13, 5)) is None
    regular = session_bounds(_ny_ts(2026, 10, 21, 10, 31))
    assert regular["end"] == _ny_ts(2026, 10, 21, 16, 0)


def test_admit_flow_bucket_holiday_cursor_refuses():
    from services.chart_flow import admit_flow_bucket
    row = {"ticker": "SPY", "side": "call", "premium": 5.0,
           "event_time": _ny_ts(2026, 11, 26, 10, 31, 10),
           "received_at": _ny_ts(2026, 11, 26, 10, 30, 30)}
    env = admit_flow_bucket([row], ticker="SPY",
                            cursor=_ny_ts(2026, 11, 26, 10, 31), bar_seconds=60)
    assert env == {"status": "refused", "reason": "cursor-not-in-regular-session"}


def test_admit_flow_bucket_excludes_anomalous_premiums():
    from services.chart_flow import admit_flow_bucket
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    rows = [
        {"ticker": "SPY", "side": "put", "premium": -50.0,
         "event_time": cursor + 10, "received_at": cursor - 30},
        {"ticker": "SPY", "side": "call", "premium": 2e12,
         "event_time": cursor + 20, "received_at": cursor - 30},
        {"ticker": "SPY", "side": "call", "premium": 25.0,
         "event_time": cursor + 40, "received_at": cursor - 30},
    ]
    env = admit_flow_bucket(rows, ticker="SPY", cursor=cursor, bar_seconds=60)
    assert env["status"] == "available"
    assert env["totals"]["count"] == 1
    assert env["totals"]["call_premium"] == 25.0
    assert env["gaps"]["anomalous_premium"] == 2


# ---- clock parsing and window boundary pins ----


def test_gate_accepts_iso_clocks_and_naive_as_utc():
    from services.chart_flow import admit_flow_bucket
    cursor = _ny_ts(2026, 10, 21, 10, 31)  # 2026-10-21T14:31:00Z
    rows = [
        {"ticker": "SPY", "side": "call", "premium": 30.0,
         "event_time": "2026-10-21T14:31:10+00:00",
         "received_at": "2026-10-21T14:30:31+00:00"},
        {"ticker": "SPY", "side": "put", "premium": 12.0,
         "event_time": "2026-10-21T14:31:40Z",
         "received_at": "2026-10-21T14:30:32Z"},
        {"ticker": "SPY", "side": "call", "premium": 3.0,
         "event_time": "2026-10-21T14:31:50",       # naive ISO is treated as UTC
         "received_at": "2026-10-21T14:30:33"},
    ]
    env = admit_flow_bucket(rows, ticker="SPY", cursor=cursor, bar_seconds=60)
    assert env["status"] == "available"
    assert env["totals"]["count"] == 3
    assert env["totals"]["call_premium"] == 33.0
    assert env["totals"]["put_premium"] == -12.0


def test_gate_rejects_unparseable_clocks():
    from services.chart_flow import admit_flow_bucket
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    rows = [{"ticker": "SPY", "side": "call", "premium": 5.0,
             "event_time": "not-a-clock", "received_at": cursor - 30}]
    env = admit_flow_bucket(rows, ticker="SPY", cursor=cursor, bar_seconds=60)
    assert env["status"] == "unavailable"
    assert env["gaps"]["malformed_row"] == 1


def test_window_and_receipt_boundaries_exact():
    from services.chart_flow import admit_flow_bucket
    cursor = _ny_ts(2026, 10, 21, 10, 31)
    rows = [
        {"ticker": "SPY", "side": "call", "premium": 1.0,
         "event_time": cursor, "received_at": cursor},          # window start + receipt == cursor
        {"ticker": "SPY", "side": "put", "premium": 2.0,
         "event_time": cursor + 60, "received_at": cursor - 30},  # event == window end excluded
    ]
    env = admit_flow_bucket(rows, ticker="SPY", cursor=cursor, bar_seconds=60)
    assert env["status"] == "available"
    assert env["totals"]["count"] == 1
    assert env["totals"]["call_premium"] == 1.0
    assert env["gaps"]["future_event"] == 1


# ---- whole-session walk invariants: buckets partition the session exactly ----


def test_flow_buckets_partition_session_without_double_count_or_loss():
    from services.chart_flow import admit_flow_bucket, session_bounds
    bar = 300
    session = session_bounds(_ny_ts(2026, 10, 6, 10, 0))           # regular Tuesday
    rows = []
    cursor_epoch = session["start"]
    n_buckets = 0
    while cursor_epoch + bar <= session["end"]:
        rows.append({"ticker": "SPY", "side": "call", "premium": 10.0 + n_buckets,
                     "event_time": cursor_epoch + 120, "received_at": cursor_epoch})
        rows.append({"ticker": "SPY", "side": "put", "premium": 5.0 + n_buckets,
                     "event_time": cursor_epoch + 240, "received_at": cursor_epoch})
        n_buckets += 1
        cursor_epoch += bar
    rows.append({"ticker": "QQQ", "side": "call", "premium": 50.0,
                 "event_time": session["start"] + 10, "received_at": session["start"] + 5})
    total_calls = 10.0 * n_buckets + (n_buckets * (n_buckets - 1)) // 2
    total_puts = 5.0 * n_buckets + (n_buckets * (n_buckets - 1)) // 2
    admitted = {"count": 0, "call": 0.0, "put": 0.0}
    for i in range(n_buckets):
        env = admit_flow_bucket(rows, ticker="SPY", cursor=session["start"] + i * bar,
                                bar_seconds=bar)
        assert env["status"] == "available"
        assert env["bucket_index"] == i
        admitted["count"] += env["totals"]["count"]
        admitted["call"] += env["totals"]["call_premium"]
        admitted["put"] += env["totals"]["put_premium"]
        assert env["gaps"]["foreign_instrument"] == 1
        assert sum(env["gaps"].values()) == env["excluded_count"]
    assert admitted["count"] == 2 * n_buckets
    assert abs(admitted["call"] - total_calls) < 1e-9
    assert abs(admitted["put"] + total_puts) < 1e-9
    empty = admit_flow_bucket([], ticker="SPY", cursor=session["start"], bar_seconds=bar)
    assert empty["status"] == "unavailable"
    assert empty["totals"] is None


def test_flow_buckets_walk_early_close_session():
    from services.chart_flow import admit_flow_bucket, session_bounds
    bar = 1800
    session = session_bounds(_ny_ts(2025, 12, 24, 10, 0))          # early-close day
    expected_buckets = 0
    cursor_epoch = session["start"]
    while cursor_epoch + bar <= session["end"]:
        expected_buckets += 1
        cursor_epoch += bar
    assert expected_buckets == 7                                   # 09:30 -> 13:00
    events = []
    for i in range(expected_buckets):
        events.append({"ticker": "SPY", "side": "call", "premium": 2.0,
                       "event_time": session["start"] + i * bar + bar - 1,
                       "received_at": session["start"] + i * bar})
    for i in range(expected_buckets):
        env = admit_flow_bucket(events, ticker="SPY", cursor=session["start"] + i * bar,
                                bar_seconds=bar)
        assert env["status"] == "available"
        assert env["session"]["end"] == _ny_ts(2025, 12, 24, 13, 0)
        assert env["totals"]["count"] == 1
