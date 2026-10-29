"""Counterexamples found in independent review of the overnight candidate."""
import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import duckdb

from services.chart_delta import admit_delta
from services.chart_flow import admit_flow_bucket
from services.chart_profiles import admit_initial_balance, naked_levels_claim


def clock(hour, minute, second=0):
    return datetime(2026, 10, 21, hour, minute, second, tzinfo=ZoneInfo("America/New_York")).timestamp()


def test_future_event_inside_selected_bucket_is_not_known_at_cursor():
    cursor = clock(10, 31, 20)
    out = admit_flow_bucket([{"ticker": "SPY", "side": "call", "premium": 1000,
                              "event_time": cursor + 10, "received_at": cursor - 1}],
                            ticker="SPY", cursor=cursor, bar_seconds=60)
    assert out["status"] == "unavailable"
    assert out["gaps"]["future_event"] == 1


def test_latest_known_correction_replaces_all_earlier_versions():
    cursor = clock(10, 31)
    rows = [{"ticker": "SPY", "event_time": cursor - 60, "received_at": cursor - 30 + i,
             "buy": buy, "sell": 2, "corrected": i > 0}
            for i, buy in enumerate([10, 20, 30])]
    out = admit_delta(rows, ticker="SPY", cursor=cursor, bar_seconds=60,
                      capabilities={"classified_sizes": True}, tick_size=.01,
                      units="shares", entitlement="recorded")
    assert len(out["rows"]) == 1
    assert out["rows"][0]["delta"] == 28
    assert out["gaps"]["superseded_by_correction"] == 2


def test_foreign_opening_bars_cannot_certify_selected_instrument():
    rows = [{"ticker": "QQQ", "time": clock(9, 30) + i * 1800,
             "high": 999, "low": 998, "received_at": clock(10, 31)} for i in range(2)]
    out = admit_initial_balance(rows, ticker="SPY", cursor=clock(10, 32),
                                bar_seconds=1800, session_date="2026-10-21", opening_minutes=60,
                                tick_size=.01, units="usd", entitlement="recorded")
    assert out["status"] == "unavailable"
    assert out["gaps"]["foreign_instrument"] == 2


def test_touch_before_level_creation_cannot_end_that_level():
    out = naked_levels_claim([{"price": 100, "session_start": clock(10, 30)}],
                             [{"time": clock(10, 0), "high": 101, "low": 99,
                               "received_at": clock(10, 1)},
                              {"time": clock(10, 31), "high": 105, "low": 104,
                               "received_at": clock(10, 32)}],
                             cursor=clock(10, 33), coverage={"low": 90, "high": 110})
    assert out["claims"][0]["visible_until"] is None
    assert out["claims"][0]["naked"] is None
    assert out["claims"][0]["reason"] == "temporal-coverage-unproven"


def test_actual_server_chart_callback_reads_duckdb_not_agent_mongo():
    # Execute the actual nested startup callback without starting services,
    # background tasks or providers. Its SQL runs against an isolated store.
    tree = ast.parse((Path(__file__).parents[2] / "server.py").read_text())
    callback = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    and n.name == "read_recorded_chart")
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("""CREATE TABLE heatmap_snapshots_v2
          (snapshot_id VARCHAR, ticker VARCHAR, query_key VARCHAR, expiries VARCHAR,
           formula_version VARCHAR, exposure_basis VARCHAR, asof_ts VARCHAR,
           received_at VARCHAR, walls_json VARCHAR, strikes_json VARCHAR)""")
        connection.execute("INSERT INTO heatmap_snapshots_v2 VALUES ('record-1','SPY','scope','[]','v1','OI',"
                           "'2026-10-21T14:00:00Z','2026-10-21T14:00:01Z','[]','[]')")

        def query(sql, params):
            result = connection.execute(sql, params)
            names = [column[0] for column in result.description]
            return [dict(zip(names, row, strict=True)) for row in result.fetchall()]

        scope = {"db": object(), "duckdb_engine": SimpleNamespace(query_strict=query)}
        exec(compile(ast.Module(body=[callback], type_ignores=[]), "server callback", "exec"), scope)
        rows = scope["read_recorded_chart"]("SPY", "2026-10-21T13:00:00Z", "2026-10-21T15:00:00Z")
        assert [row["snapshot_id"] for row in rows] == ["record-1"]
    finally:
        connection.close()


def test_malformed_stored_clock_is_a_gap_not_an_answer_exception():
    from services.chart_context import resolve_focused_chart
    out = resolve_focused_chart([{"ticker": "SPY", "query_key": "scope", "expiries": [],
                                  "asof_ts": "broken", "received_at": "2026-10-21T14:00:00Z"}],
                                focus="SPY", scope="scope", cursor=clock(10, 1))
    assert out["status"] == "unavailable"
    assert out["reason"] == "recorded scope has no valid observation clocks"


def test_malformed_provider_bar_does_not_break_other_envelopes():
    from routes.price_history import _recorded_envelopes
    out = _recorded_envelopes("SPY", [{"t": "bad", "h": 999, "l": 998},
                                     {"t": clock(9, 30), "o": 100, "h": 102, "l": 99, "c": 101}],
                              clock(10, 35), 1800, 60, .01, "usd", "recorded", 900)
    assert out["initial_balance"]["status"] != "available"
    assert out["source_gaps"]["malformed_bar_clock"] == 1


def test_equal_receipt_conflicting_corrections_are_unavailable_in_either_order():
    cursor = clock(10, 31)
    rows = [{"ticker": "SPY", "event_time": cursor - 60, "received_at": cursor - 1,
             "buy": buy, "sell": 2, "corrected": True} for buy in [20, 30]]
    for stream in [rows, rows[::-1]]:
        out = admit_delta(stream, ticker="SPY", cursor=cursor, bar_seconds=60,
                          capabilities={"classified_sizes": True}, tick_size=.01,
                          units="shares", entitlement="recorded")
        assert out["status"] == "unavailable"
        assert out["gaps"]["ambiguous_correction"] == 2


def test_initial_balance_uses_only_bars_the_actual_chart_can_render():
    from routes.price_history import _recorded_envelopes
    out = _recorded_envelopes("SPY", [{"t": clock(9, 30), "o": 100, "h": 102, "l": 99, "c": 101},
                                     {"t": clock(10, 0), "o": 1000, "h": 102, "l": 99, "c": 101}],
                              clock(10, 35), 1800, 60, .01, "usd", "recorded", 900)
    assert out["initial_balance"]["status"] != "available"
    assert out["source_gaps"]["invalid_or_duplicate_bars"] == 1


def test_naked_claim_requires_contiguous_known_closed_bar_coverage():
    start, cursor = clock(10, 30), clock(10, 33)
    bars = [{"time": start + i * 60, "end_time": start + (i + 1) * 60,
             "received_at": start + (i + 1) * 60, "low": 104, "high": 105} for i in range(3)]
    coverage = {"low": 90, "high": 110, "start": start, "end": cursor, "bar_seconds": 60}
    complete = naked_levels_claim([{"price": 100, "session_start": start}], bars,
                                  cursor=cursor, coverage=coverage)
    assert complete["claims"][0]["naked"] is True
    missing = naked_levels_claim([{"price": 100, "session_start": start}], bars[1:],
                                 cursor=cursor, coverage=coverage)
    assert missing["claims"][0]["naked"] is None
    assert missing["claims"][0]["reason"] == "temporal-coverage-unproven"
