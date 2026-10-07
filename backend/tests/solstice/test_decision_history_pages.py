"""Older saved decisions remain reachable without replaying any action."""
from types import SimpleNamespace

import duckdb
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def conn():
    connection = duckdb.connect(":memory:")
    from services.heatmap_history import ensure_tables
    ensure_tables(connection)
    yield connection
    connection.close()


def add(connection, identity, at="2026-10-06T14:00:00+00:00", ticker="SPY",
        features='{"spot": 500, "reason_codes": ["FEATURE_ONLY"]}', reasons='["SOURCE_REASON"]'):
    connection.execute(
        "INSERT INTO scenario_decisions_v1 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [identity, ticker, at, "saved-snapshot", "CALLS", "CALLS", False, reasons, features],
    )


def page(connection, ticker="SPY", **kwargs):
    from services.solstice_decision_history import decision_page
    return decision_page(connection, ticker, **kwargs)


def ids(result):
    return [row["decision_id"] for row in result["decisions"]]


def test_pages_reach_every_old_record_beyond_previous_cap(conn):
    for index in range(241):
        add(conn, f"decision-{index:03}")
    cursor = None
    seen = []
    for _ in range(10):
        result = page(conn, limit=67, cursor=cursor)
        seen.extend(ids(result))
        if not result["has_more"]:
            assert result["next_cursor"] is None
            break
        cursor = result["next_cursor"]
        assert isinstance(cursor, str) and 1 <= len(cursor) <= 1024
    assert seen == [f"decision-{index:03}" for index in range(240, -1, -1)]
    assert len(set(seen)) == 241


def test_clock_order_uses_actual_utc_and_identity_breaks_ties(conn):
    add(conn, "utc-new", "2026-10-06T13:30:00+00:00")
    add(conn, "utc-old", "2026-10-06T09:00:00-04:00")
    add(conn, "tie-b", "2026-10-06T13:15:00Z")
    add(conn, "tie-a", "2026-10-06T09:15:00-04:00")
    first = page(conn, limit=2)
    second = page(conn, limit=2, cursor=first["next_cursor"])
    assert ids(first) == ["utc-new", "tie-b"]
    assert ids(second) == ["tie-a", "utc-old"]
    assert second["decisions"][0]["at_ts"] == "2026-10-06T09:15:00-04:00"


def test_newer_insert_does_not_shift_or_repeat_the_next_page(conn):
    for identity in ("d", "c", "b", "a"):
        add(conn, identity)
    first = page(conn, limit=2)
    add(conn, "new-later", "2026-10-06T15:00:00Z")
    second = page(conn, limit=2, cursor=first["next_cursor"])
    assert ids(first) == ["d", "c"]
    assert ids(second) == ["b", "a"]
    assert second["has_more"] is False


def test_state_filter_precedes_page_size_and_cursor_cannot_change_scope(conn):
    for identity in ("d", "c", "b", "a"):
        add(conn, identity)
    for identity in ("c", "a"):
        conn.execute("INSERT INTO decision_reviews_v1 VALUES (?, ?, ?, ?, ?)",
                     [identity, "reviewed", "original reason", "original note", "2026-10-06T16:00:00Z"])
    first = page(conn, state="reviewed", limit=1)
    second = page(conn, state="reviewed", limit=1, cursor=first["next_cursor"])
    assert ids(first) == ["c"]
    assert ids(second) == ["a"]
    with pytest.raises(ValueError):
        page(conn, "QQQ", state="reviewed", cursor=first["next_cursor"])
    with pytest.raises(ValueError):
        page(conn, "SPY", state="waiting", cursor=first["next_cursor"])
    assert page(conn, state="pending")["count"] == 0  # absent review is not a saved pending state


@pytest.mark.parametrize("cursor", ["not-a-cursor", "a" * 1025, "e30", "", 123, True])
def test_malformed_or_oversized_cursor_is_refused(conn, cursor):
    with pytest.raises(ValueError):
        page(conn, cursor=cursor)


def test_modified_signed_cursor_is_refused(conn):
    add(conn, "b")
    add(conn, "a")
    cursor = page(conn, limit=1)["next_cursor"]
    replacement = "A" if cursor[5] != "A" else "B"
    with pytest.raises(ValueError):
        page(conn, cursor=cursor[:5] + replacement + cursor[6:])


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 101}, {"limit": True},
                                     {"state": "not-known"}, {"state": "reviewed' OR TRUE --"}])
def test_page_size_and_state_are_strictly_bounded(conn, kwargs):
    with pytest.raises(ValueError):
        page(conn, **kwargs)


def test_unknown_and_naive_clocks_remain_explicit_gaps(conn):
    add(conn, "known", "2026-10-06T14:00:00Z")
    add(conn, "missing", None)
    add(conn, "naive", "2026-10-06T14:00:00")
    add(conn, "bad-date", "2026-02-30T14:00:00Z")
    result = page(conn)
    assert ids(result) == ["known"]
    assert result["excluded_unknown_time"] == 3
    assert result["status"] == "partial"
    assert result["has_more"] is False
    result = page(conn, "QQQ")
    assert result["status"] == "available"
    assert result["count"] == 0 and result["excluded_unknown_time"] == 0


def test_saved_features_reason_codes_and_quote_counts_survive_without_writes(conn):
    original = '{"spot": 432.1, "reason_codes": ["FEATURE_ONLY"], "zone": [430, 435]}'
    add(conn, "saved", "2026-09-27T22:53:26.867301+00:00", features=original)
    for identity in ("first", "first", "second"):
        conn.execute("INSERT INTO candidate_quotes_v1 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ["saved", identity, 1, 1.1, None, None, .5, 10, False, None, "2026-09-27T22:53:26.9Z"])
    conn.execute("INSERT INTO outcome_labels_v1 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 ["saved", "SPY", 300, "censored", "original", "2026-09-27T23:00:00Z", True, "{}", "original"])
    before = conn.execute("SELECT * FROM scenario_decisions_v1").fetchall()
    row = page(conn)["decisions"][0]
    assert row["at_ts"] == "2026-09-27T22:53:26.867301+00:00"
    assert row["features"] == {"spot": 432.1, "reason_codes": ["FEATURE_ONLY"], "zone": [430, 435]}
    assert row["reason_codes"] == ["SOURCE_REASON"]
    assert row["n_quotes"] == 2
    assert row["outcome_labels"] == "censored"
    assert row["review_state"] is None
    assert conn.execute("SELECT * FROM scenario_decisions_v1").fetchall() == before


def test_corrupt_features_are_reported_without_replacing_them_with_empty_values(conn):
    add(conn, "bad-json", features="not json", reasons="also not json")
    result = page(conn)
    row = result["decisions"][0]
    assert row["features"] is None and row["features_status"] == "unavailable"
    assert row["reason_codes"] is None
    assert result["status"] == "partial"


def test_missing_storage_is_unavailable_not_an_empty_success():
    from services.solstice_decision_history import DecisionHistoryUnavailable
    with pytest.raises(DecisionHistoryUnavailable):
        page(None)
    connection = duckdb.connect(":memory:")
    try:
        with pytest.raises(DecisionHistoryUnavailable):
            page(connection)
        assert connection.execute("SHOW TABLES").fetchall() == []  # a read never creates tables
    finally:
        connection.close()


def test_ticker_cannot_become_a_query_or_cross_to_another_symbol(conn):
    add(conn, "spy", ticker="SPY")
    add(conn, "qqq", ticker="QQQ")
    assert ids(page(conn, "spy")) == ["spy"]
    assert ids(page(conn, "QQQ")) == ["qqq"]
    with pytest.raises(ValueError):
        page(conn, "SPY' OR TRUE --")


@pytest.fixture
def route_client(conn, monkeypatch):
    import sys

    from routes.solstice_review import register_review_routes
    monkeypatch.setitem(sys.modules, "services.duckdb_engine", SimpleNamespace(db=SimpleNamespace(conn=conn)))
    router = APIRouter(prefix="/api/solstice")
    register_review_routes(router)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client


def test_real_page_route_reaches_older_records_and_leaves_legacy_list_unchanged(conn, route_client):
    for index in range(201):
        add(conn, f"d-{index:03}")
    first = route_client.get("/api/solstice/SPY/decisions/page", params={"limit": 100})
    assert first.status_code == 200, first.text
    second = route_client.get("/api/solstice/SPY/decisions/page", params={"limit": 100, "cursor": first.json()["next_cursor"]})
    third = route_client.get("/api/solstice/SPY/decisions/page", params={"limit": 100, "cursor": second.json()["next_cursor"]})
    assert ids(third.json()) == ["d-000"]
    assert third.json()["has_more"] is False
    legacy = route_client.get("/api/solstice/SPY/decisions", params={"limit": 200})
    assert legacy.status_code == 200
    assert legacy.json()["count"] == 200


def test_route_returns_explicit_errors_for_bad_input_or_failed_storage(conn, route_client):
    for params in ({"limit": 101}, {"state": "unknown"}, {"cursor": "broken"}):
        response = route_client.get("/api/solstice/SPY/decisions/page", params=params)
        assert response.status_code == 422, response.text
    conn.execute("DROP TABLE candidate_quotes_v1")
    response = route_client.get("/api/solstice/SPY/decisions/page")
    assert response.status_code == 503, response.text
    assert "unavailable" in response.text.lower()


def test_oldest_pages_reach_every_saved_record_in_ascending_order(conn):
    for index in range(241):
        add(conn, f"decision-{index:03}")
    cursor = None
    seen = []
    for _ in range(10):
        result = page(conn, limit=67, order="oldest", cursor=cursor)
        seen.extend(ids(result))
        if not result["has_more"]:
            assert result["next_cursor"] is None
            break
        cursor = result["next_cursor"]
    assert seen == [f"decision-{index:03}" for index in range(241)]
    assert len(set(seen)) == 241


def test_oldest_uses_actual_utc_clock_then_ascending_identity_for_ties(conn):
    add(conn, "utc-new", "2026-10-06T13:30:00+00:00")
    add(conn, "utc-old", "2026-10-06T09:00:00-04:00")
    add(conn, "tie-b", "2026-10-06T13:15:00Z")
    add(conn, "tie-a", "2026-10-06T09:15:00-04:00")
    first = page(conn, limit=2, order="oldest")
    add(conn, "inserted-earlier", "2026-10-06T12:00:00Z")
    second = page(conn, limit=2, order="oldest", cursor=first["next_cursor"])
    assert ids(first) == ["utc-old", "tie-a"]
    assert ids(second) == ["tie-b", "utc-new"]
    assert second["has_more"] is False


def test_cursor_is_bound_to_order_and_unknown_order_is_rejected(conn):
    add(conn, "b")
    add(conn, "a")
    newest = page(conn, limit=1)
    oldest = page(conn, limit=1, order="oldest")
    with pytest.raises(ValueError):
        page(conn, order="oldest", cursor=newest["next_cursor"])
    with pytest.raises(ValueError):
        page(conn, cursor=oldest["next_cursor"])
    with pytest.raises(ValueError):
        page(conn, order="oldest' OR TRUE --")
    assert ids(page(conn)) == ["b", "a"]  # default stays newest


def test_real_route_can_open_the_first_saved_reading_directly(conn, route_client):
    add(conn, "oldest", "2026-09-27T22:53:26.867301+00:00")
    add(conn, "middle", "2026-10-06T14:00:00Z")
    add(conn, "latest", "2026-10-07T04:00:00Z")
    response = route_client.get("/api/solstice/SPY/decisions/page", params={"limit": 1, "order": "oldest"})
    assert response.status_code == 200, response.text
    assert ids(response.json()) == ["oldest"]
    assert response.json()["decisions"][0]["at_ts"] == "2026-09-27T22:53:26.867301+00:00"
    next_page = route_client.get("/api/solstice/SPY/decisions/page", params={
        "limit": 1, "order": "oldest", "cursor": response.json()["next_cursor"],
    })
    assert ids(next_page.json()) == ["middle"]
    assert ids(route_client.get("/api/solstice/SPY/decisions/page", params={"limit": 1}).json()) == ["latest"]
