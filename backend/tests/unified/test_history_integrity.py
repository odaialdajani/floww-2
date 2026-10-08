"""U08: recorded-history clocks, stable keyset paging, gaps stay gaps.

Isolated: in-memory DuckDB for decision pages, pure-function history builds.
No active store, no provider, no reconstruction from current chains.
"""
import duckdb
import pytest

from services.price_node_history import MAX_NODE_AGE_SECONDS, build_history, recorded_nodes
from services.solstice_decision_history import DecisionHistoryUnavailable, decision_page

T1 = "2026-09-04T14:00:00+00:00"
T2 = "2026-09-04T15:00:00+00:00"
T3 = "2026-09-04T16:00:00+00:00"


def _conn():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE scenario_decisions_v1 (decision_id VARCHAR, ticker VARCHAR, "
                 "at_ts VARCHAR, snapshot_id VARCHAR, scenario VARCHAR, side VARCHAR, "
                 "eligible BOOLEAN, reason_codes VARCHAR, features VARCHAR)")
    conn.execute("CREATE TABLE decision_reviews_v1 (decision_id VARCHAR, state VARCHAR)")
    conn.execute("CREATE TABLE candidate_quotes_v1 (decision_id VARCHAR, osi VARCHAR)")
    conn.execute("CREATE TABLE outcome_labels_v1 (decision_id VARCHAR, label VARCHAR)")
    conn.execute("CREATE TABLE heatmap_snapshots_v2 (snapshot_id VARCHAR, ticker VARCHAR)")
    return conn


def _insert(conn, did, at, ticker="AAA", state=None):
    conn.execute("INSERT INTO scenario_decisions_v1 VALUES (?,?,?,?,?,?,?,?,?)",
                 [did, ticker, at, "snap-" + did, "s", "buy", True, '["x"]', '{"k": 1}'])
    if state:
        conn.execute("INSERT INTO decision_reviews_v1 VALUES (?,?)", [did, state])


def test_keyset_pages_stable_under_new_inserts():
    conn = _conn()
    for did, at in (("d1", T1), ("d2", T2), ("d3", T3)):
        _insert(conn, did, at)
    first = decision_page(conn, "AAA", limit=2, order="newest")
    assert [d["decision_id"] for d in first["decisions"]] == ["d3", "d2"]
    assert first["has_more"] is True and first["next_cursor"]
    conn.execute("INSERT INTO scenario_decisions_v1 VALUES ('d4','AAA','2026-09-04T17:00:00+00:00','snap-d4','s','buy',TRUE,'[\"x\"]','{}')")
    second = decision_page(conn, "AAA", limit=2, order="newest", cursor=first["next_cursor"])
    assert [d["decision_id"] for d in second["decisions"]] == ["d1"]  # insert did not shift the page
    assert second["has_more"] is False


def test_foreign_cursor_and_bad_state_refused():
    conn = _conn()
    _insert(conn, "d1", T1)
    _insert(conn, "d2", T2)
    first = decision_page(conn, "AAA", limit=1)
    assert first["next_cursor"]
    with pytest.raises(ValueError):
        decision_page(conn, "BBB", cursor=first["next_cursor"])  # cursor bound to ticker
    with pytest.raises(ValueError):
        decision_page(conn, "AAA", state="mysterious")
    with pytest.raises(ValueError):
        decision_page(conn, "AAA", limit=0)
    with pytest.raises(DecisionHistoryUnavailable):  # missing storage is typed unavailable
        decision_page(None, "AAA")


def test_unknown_clock_and_invalid_identity_are_counted_gaps():
    conn = _conn()
    _insert(conn, "good-1", T1)
    _insert(conn, "good-2", T2)
    _insert(conn, "bad-clock", "not-a-timestamp")
    conn.execute("INSERT INTO scenario_decisions_v1 VALUES ('bad id!','AAA',?, 'snap-x','s','buy',TRUE,'[]','{}')", [T2])
    page = decision_page(conn, "AAA", limit=10)
    assert [d["decision_id"] for d in page["decisions"]] == ["good-2", "good-1"]
    assert page["excluded_unknown_time"] == 1
    assert page["excluded_invalid_identity"] == 1
    assert page["status"] == "partial"  # exclusions are reported, gaps stay gaps


def _bar(ts, o=100.0, h=101.0, low=99.0, c=100.5):
    return {"t": ts, "o": o, "h": h, "l": low, "c": c}


def _snap(asof, received, snapshot_id="s1", level=100.0, query_key="k1"):
    return {"ticker": "AAA", "asof_ts": asof, "received_at": received,
            "snapshot_id": snapshot_id, "query_key": query_key,
            "walls_json": [{"mid": level, "wall_id": "w1"}]}


def test_nodes_only_when_known_at_bar_time():
    t_bar = "2026-09-04T15:30:00+00:00"
    early = _snap("2026-09-04T15:25:00+00:00", "2026-09-04T15:25:30+00:00", level=101.0)
    late = _snap("2026-09-04T15:31:00+00:00", "2026-09-04T15:31:05+00:00", level=102.0, snapshot_id="s2")
    hist = build_history("AAA", [_bar(t_bar)], [early, late])
    frame = hist["frames"][0]
    # only the snapshot known BEFORE the bar can attach; later readings stay future
    assert frame["snapshot_id"] == "s1"
    assert frame["nodes"] and frame["nodes"][0]["level"] == 101.0
    assert frame["node_age_seconds"] == 300


def test_delayed_arrival_never_refreshes_old_observation():
    t_bar = "2026-09-04T15:30:00+00:00"
    # asof is 2h before the bar (stale observation), received just now:
    old = _snap("2026-09-04T13:00:00+00:00", "2026-09-04T15:29:00+00:00")
    hist = build_history("AAA", [_bar(t_bar)], [old])
    frame = hist["frames"][0]
    assert frame["nodes"] == []
    assert frame["node_age_seconds"] is None  # age > MAX_NODE_AGE_SECONDS withholds nodes
    assert MAX_NODE_AGE_SECONDS == 900


def test_malformed_bars_and_ambiguous_clocks_dropped():
    good = _bar("2026-09-04T15:30:00+00:00")
    bad_ohlc = _bar("2026-09-04T15:31:00+00:00", o=100.0, h=98.0, low=99.0, c=100.5)  # high < open
    naive = _bar("2026-09-04 15:32:00")  # no timezone: cannot support a known-at join
    hist = build_history("AAA", [bad_ohlc, naive, good], [])
    assert len(hist["frames"]) == 1
    assert hist["frames"][0]["time"] == "2026-09-04T15:30:00+00:00"


def test_scope_binding_and_malformed_walls():
    t_bar = "2026-09-04T15:30:00+00:00"
    owned = _snap("2026-09-04T15:25:00+00:00", "2026-09-04T15:25:30+00:00", query_key="k1", level=100.0)
    foreign = _snap("2026-09-04T15:26:00+00:00", "2026-09-04T15:26:30+00:00",
                    query_key="other", level=200.0, snapshot_id="s9")
    hist = build_history("AAA", [_bar(t_bar)], [owned, foreign], query_key="other")
    assert hist["query_key"] == "other"
    assert hist["frames"][0]["snapshot_id"] == "s9"  # requested scope wins
    scoped = build_history("AAA", [_bar(t_bar)], [owned, foreign], query_key="k1")
    assert scoped["frames"][0]["snapshot_id"] == "s1"
    # malformed wall levels are dropped, never shown as zero
    walls = recorded_nodes({"walls_json": [{"mid": 0}, {"mid": -5}, {"mid": 42.0}]})
    assert [w["level"] for w in walls] == [42.0]
