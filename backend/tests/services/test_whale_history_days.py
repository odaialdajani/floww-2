"""Requested whale-history windows over real SQL with a frozen database date."""
from datetime import datetime

import duckdb
import pytest

from services.journal_store import init_whale_tables, read_whales


@pytest.fixture
def history():
    connection = duckdb.connect(":memory:", config={"threads": "1", "enable_external_access": "false"})
    connection.execute("CREATE MACRO current_date() AS DATE '2026-11-08'")

    class Engine:
        def execute_write(self, sql):
            connection.execute(sql)

        def query(self, sql, params):
            cursor = connection.execute(sql, params)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    engine = Engine()
    init_whale_tables(engine)
    for key, asof, state, hour in [
        ("today", "2026-11-08", "STILL_IN", 9),
        ("one-day", "2026-11-07", "EXITED", 14),
        ("two-days", "2026-11-06", "STILL_IN", 11),
        ("thirty", "2026-10-09", "STILL_IN", 8),
        ("thirty-one", "2026-10-08", "EXITED", 13),
        ("year", "2025-11-08", "STILL_IN", 12),
        ("too-old", "2025-11-07", "STILL_IN", 15),
    ]:
        connection.execute("""
            INSERT INTO whale_tracks VALUES
            (?, ?, ?, 'SPY', 'call', 'BUY', 'BULLISH', 600, '2027-01-15',
             600, 5000, 10000, 610, 5000, 10000, ?, 1.67, 'synthetic history', ?)
        """, [asof, key, "SPY|call|600|2027-01-15", state, datetime(2026, 11, 8, hour)])
    try:
        yield engine
    finally:
        connection.close()


@pytest.mark.parametrize(("days", "expected"), [
    (1, ["one-day", "today"]),
    (30, ["one-day", "two-days", "today", "thirty"]),
    (365, ["one-day", "thirty-one", "year", "two-days", "today", "thirty"]),
])
def test_requested_days_change_history_with_inclusive_cutoff_and_update_order(history, days, expected):
    assert [row["alert_key"] for row in read_whales(history, days=days)] == expected


def test_default_remains_thirty_days(history):
    assert [row["alert_key"] for row in read_whales(history)] == ["one-day", "two-days", "today", "thirty"]


def test_state_filter_combines_with_requested_history_and_preserves_rows(history):
    rows = read_whales(history, state="STILL_IN", days=365)
    assert [row["alert_key"] for row in rows] == ["year", "two-days", "today", "thirty"]
    assert all(row["state"] == "STILL_IN" and row["entry_oi"] == 5000 for row in rows)
    assert read_whales(history, state="STILL_IN' OR TRUE --", days=365) == []


@pytest.mark.parametrize("days", [0, -1, 366, True, None, "30", 1.5])
def test_invalid_service_days_fail_closed_after_route_validation(history, days):
    assert read_whales(history, days=days) == []
