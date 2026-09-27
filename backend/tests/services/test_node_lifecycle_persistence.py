"""Node/wall lifecycle persistence tests (maximization build #1).

The lifecycle state machines exist but live in process memory; a restart
wipes node tap history and wall last-state. These tests pin the durable
round-trip through DuckDB (same conn pattern as heatmap_history) plus the
deterministic tap-probability heuristic bands.
"""
from __future__ import annotations

import duckdb

from services.heatmap_history import ensure_tables
from services.node_lifecycle import Node, NodeLifecycleTracker


def _conn():
    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    return conn


def test_node_dict_round_trip():
    n = Node(strike=500.0, gex_value=1.5e6, spot_at_formation=498.0)
    n.update(spot=500.1)  # within 0.3% tap threshold -> tap
    assert n.tap_count == 1
    d2 = Node.from_dict(n.to_dict())
    assert d2.strike == 500.0
    assert d2.tap_count == 1
    assert d2.state == n.state
    # to_dict rounds weight/opacity to 4dp; the restore is exact at that precision.
    assert d2.structural_weight == round(n.structural_weight, 4)
    assert d2.last_tap_time is not None


def test_tap_probability_bands_are_labeled_heuristic():
    fresh = Node(strike=500.0, gex_value=1.0, spot_at_formation=490.0)
    assert fresh.tap_probability == 0.80
    assert fresh.tap_probability_basis == "heuristic"
    one = Node(strike=500.0, gex_value=1.0, spot_at_formation=490.0)
    one.update(spot=500.1)
    assert one.tap_count == 1 and one.tap_probability == 0.66
    two = Node(strike=500.0, gex_value=1.0, spot_at_formation=490.0)
    two.update(spot=500.1)
    two.update(spot=500.1)
    assert two.tap_count == 2 and two.tap_probability == 0.50
    decaying = Node(strike=500.0, gex_value=1.0, spot_at_formation=490.0)
    for _ in range(3):
        decaying.tap()
    assert decaying.tap_probability == 0.33
    for _ in range(3):
        decaying.tap()
    assert decaying.state.value == "expired"
    assert decaying.tap_probability == 0.10


def test_tracker_dict_round_trip():
    t = NodeLifecycleTracker()
    t.update(spot=500.0, king_nodes=[(500.0, 2e6), (510.0, 1e6)])
    t.update(spot=500.1, king_nodes=[(500.0, 2e6), (510.0, 1e6)])
    d2 = NodeLifecycleTracker.from_dict(t.to_dict())
    assert d2.to_dict()["nodes"] == t.to_dict()["nodes"]
    assert d2.tap_threshold_pct == t.tap_threshold_pct


def test_record_and_latest_node_lifecycle():
    from services.heatmap_history import (
        latest_node_lifecycle,
        record_node_lifecycle,
    )
    conn = _conn()
    assert latest_node_lifecycle(conn, "SPY", "default") is None
    t = NodeLifecycleTracker()
    t.update(spot=500.0, king_nodes=[(500.0, 2e6)])
    record_node_lifecycle(conn, "SPY", "default", t.to_dict())
    got = latest_node_lifecycle(conn, "SPY", "default")
    assert got is not None
    assert got["nodes"][0]["strike"] == 500.0
    # Overwrite path (upsert, one row per ticker+scope); taps accumulate.
    t.update(spot=500.1, king_nodes=[(500.0, 2e6)])
    record_node_lifecycle(conn, "SPY", "default", t.to_dict())
    got2 = latest_node_lifecycle(conn, "SPY", "default")
    assert got2["nodes"][0]["tap_count"] == 2
    rows = conn.execute(
        "SELECT COUNT(*) FROM node_lifecycle_v1 WHERE ticker='SPY'"
    ).fetchone()
    assert rows[0] == 1


def test_wall_last_state_round_trip():
    from services.heatmap_history import latest_wall_last_state, record_wall_last_state
    conn = _conn()
    assert latest_wall_last_state(conn, "SPY", "day", "w1") is None
    record_wall_last_state(conn, "SPY", "day", "w1",
                           {"state": "testing", "spot": 500.0})
    got = latest_wall_last_state(conn, "SPY", "day", "w1")
    assert got == {"state": "testing", "spot": 500.0}


def test_wall_last_state_preserves_dwell_continuity():
    """Restart recovery: inside_since/beyond dwell clocks survive via DB.

    Maximization build #1 wiring: server.py joins wall_last_state_v1
    (full dwell state) ahead of the event-only wall_events_v1 row, and
    newest-wins against in-memory so a restart restores continuity.
    """
    from services.heatmap_history import latest_wall_last_state, record_wall_last_state
    from services.wall_interaction import is_newer_state, transition
    conn = _conn()
    wall = {"low": 495.0, "high": 505.0}
    first = transition("unobserved", 500.0, wall,
                       last={"gap": False})
    assert first["state"] == "testing"
    full = {"state": first["state"], "at": first["at"],
            "approach_side": first.get("approach_side"),
            "inside_since": first.get("inside_since"),
            "beyond_since": first.get("beyond_since"),
            "beyond_side": first.get("beyond_side"),
            "adverse_side": first.get("adverse_side"),
            "reclaim_state": first.get("reclaim_state"),
            "wall_position": first.get("wall_position"),
            "data_source": "yfinance"}
    record_wall_last_state(conn, "SPY", "scope-a", "w_hist", full)
    # Simulate a restart: in-memory is empty, DB row is strictly newer.
    restored = latest_wall_last_state(conn, "SPY", "scope-a", "w_hist")
    assert restored is not None
    assert is_newer_state(restored, None) is True
    assert restored["inside_since"] == full["inside_since"]
    # The restored state continues the dwell clock instead of restarting
    # at unobserved.
    nxt = transition(restored["state"], 500.0, wall, last=restored)
    assert nxt["state"] in ("testing", "holding")
