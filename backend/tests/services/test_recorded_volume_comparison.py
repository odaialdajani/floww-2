"""Stored cumulative-volume comparisons disclose every strike and refusal.

Pure in-memory history reads; no app startup, provider or active store.
This coarse comparison is distinct from contract-level adjusted activity.
"""
import json

import duckdb
import pytest

from services.heatmap_history import compare_snapshots, ensure_tables


@pytest.fixture
def conn():
    connection = duckdb.connect(":memory:")
    ensure_tables(connection)
    yield connection
    connection.close()


def save(conn, sid, minute, volumes):
    at = f"2030-01-02T10:{minute:02d}:00+00:00"
    strikes = [{"strike": strike, "gex": 100, "volume": volume}
               for strike, volume in volumes.items()]
    conn.execute(
        "INSERT INTO heatmap_snapshots_v2 "
        "(snapshot_id,ticker,query_key,expiries,spot,data_source,exposure_basis,"
        "formula_version,asof_ts,received_at,strikes_json,walls_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [sid, "TST", "q", '["2030-01-15"]', 500, "public_api", "OI", "gex.v2",
         at, at, json.dumps(strikes), "[]"],
    )


def compare(conn, before, after):
    save(conn, "before", 0, before)
    save(conn, "after", 1, after)
    result = compare_snapshots(conn, "TST", "2030-01-02")
    assert result["status"] == "ok"
    assert result["from"]["id"] == "before"
    assert result["to"]["id"] == "after"
    return result


def test_missing_invalid_retracted_and_measured_zero_remain_distinct(conn):
    result = compare(conn, {500: 10, 501: 0, 502: None, 503: True, 504: 20},
                     {500: 15, 501: 0, 502: 10, 503: 10, 504: 19})
    rows = {row["strike"]: row for row in result["volume_comparisons"]}
    assert rows[500]["delta_volume"] == 5
    assert rows[501]["delta_volume"] == 0
    assert rows[501]["status"] == "ok"
    assert rows[502]["reason"] == "NO_BASELINE"
    assert rows[503]["reason"] == "INVALID"
    assert rows[504]["reason"] == "VOLUME_REBASE"
    assert all(rows[strike]["delta_volume"] is None for strike in (502, 503, 504))
    assert result["volume_coverage"] == {
        "status": "partial", "requested": 5, "comparable": 2,
        "missing": 1, "invalid": 1, "rebased": 1, "increased": 1,
        "unchanged": 1, "units": "contracts",
    }
    # Existing positive-only ranking and rebase list stay compatible.
    assert result["volume_deltas"] == [{"strike": 500, "delta_volume": 5}]
    assert result["volume_rebased"] == [504]


def test_added_and_removed_strikes_are_unavailable_comparisons(conn):
    result = compare(conn, {500: 10, 501: 20}, {500: 10, 502: 30})
    rows = {row["strike"]: row for row in result["volume_comparisons"]}
    assert rows[500]["membership"] == "retained"
    assert rows[501]["membership"] == "removed"
    assert rows[502]["membership"] == "added"
    assert rows[501]["reason"] == rows[502]["reason"] == "NO_BASELINE"
    assert result["volume_coverage"]["missing"] == 2
    assert result["volume_coverage"]["unchanged"] == 1


@pytest.mark.parametrize("invalid", [True, -1, "not-volume", float("nan"), float("inf")])
def test_invalid_volume_does_not_become_zero_or_unserializable(conn, invalid):
    result = compare(conn, {500: invalid}, {500: 10})
    row = result["volume_comparisons"][0]
    assert row["reason"] == "INVALID"
    assert row["before_volume"] is None and row["after_volume"] == 10
    assert row["delta_volume"] is None
    assert result["volume_coverage"]["status"] == "unavailable"
    json.dumps(result, allow_nan=False)


def test_complete_population_count_is_not_the_top_twenty_ranking_length(conn):
    result = compare(conn, dict.fromkeys(range(500, 525), 0),
                     dict.fromkeys(range(500, 525), 1))
    assert len(result["volume_deltas"]) == 20
    assert len(result["volume_comparisons"]) == 25
    assert result["volume_coverage"]["increased"] == 25
    assert result["volume_coverage"]["status"] == "complete"
