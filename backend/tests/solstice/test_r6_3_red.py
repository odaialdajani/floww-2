"""R6-3 red tests: calendar, actual-backed health, writer locks, context UI."""

import sys

sys.path.insert(0, "backend")


def test_calendar_thanksgiving_closed_half_day_early():
    from services.solstice_calendar import exchange_day_info
    closed = exchange_day_info("2026-11-26")
    assert closed["is_open"] is False
    half = exchange_day_info("2026-11-27")
    assert half["is_open"] is True and half["half_day"] is True
    assert half["close_et"] == "13:00"
    full = exchange_day_info("2026-11-25")
    assert full["is_open"] is True and full["half_day"] is False
    assert full["close_et"] == "16:00"


def test_session_blocks_holiday_and_uses_half_day_close():
    from datetime import UTC, datetime

    from services.solstice_session import session_state
    turkey = datetime(2026, 11, 26, 15, 0, tzinfo=UTC)  # Thu 10am ET, holiday
    s = session_state(now=turkey, quality={"state": "usable", "reasonCodes": [],
                                           "setupEligible": True})
    assert s["entry_allowed"] is False
    assert "EXCHANGE_HOLIDAY" in s["reasons"]
    # Nov 27 half-day: 15:30 UTC = 10:30 ET, open with 2.5h left (not late).
    half_morning = datetime(2026, 11, 27, 15, 30, tzinfo=UTC)
    s2 = session_state(now=half_morning, quality={"state": "usable", "reasonCodes": [],
                                                  "setupEligible": True})
    assert s2["entry_allowed"] is True
    assert s2["minutes_to_close"] == 150.0


def test_recorder_status_inspects_actual_backing():
    import duckdb

    from services.heatmap_history import ensure_tables, recorder_status
    mem = duckdb.connect(":memory:")
    assert recorder_status(mem, ":memory:")["mode"] == "memory"
    assert recorder_status(mem, ":memory:")["durable"] is False
    # A file-looking path with a MEMORY connection must not claim durable.
    assert recorder_status(mem, "/tmp/looks-like-a-file.db")["durable"] is False


def test_file_backed_reports_durable(tmp_path):
    import duckdb

    from services.heatmap_history import ensure_tables, recorder_status
    dbfile = str(tmp_path / "solstice.duckdb")
    conn = duckdb.connect(dbfile)
    ensure_tables(conn)
    s = recorder_status(conn, dbfile)
    assert s["durable"] is True and s["mode"] == "file"
    conn.close()
