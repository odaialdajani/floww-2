"""R8-05: outcome worker lifecycle — producer/store/closure over ticks.

Synthetic paths through the REAL store + close_episodes + attach:
pending→final across ticks (restart catch-up), policy-versioned reruns,
duplicate-tick idempotency, multi-horizon expansion, disabled-by-default
scheduler hook. No network, no scheduler loop, no activation.
"""

import sys

sys.path.insert(0, "backend")

import duckdb

from services.heatmap_history import (
    ensure_tables,
    list_decisions,
    outcome_close_tick,
    price_paths_since,
    record_decision,
    record_price_path,
)
from services.solstice_labels import close_episodes

EP = {"spot": 500.0, "zone": [498, 502], "target": 505.0, "stop": 495.0,
      "horizon_s": 60, "policy_version": "research_barriers.v1"}


def _dec(conn, **kw):
    d = {"ticker": "SPY", "snapshot_id": "s-w", "scenario": "CALLS",
         "side": "CALLS", "eligible": True, "reason_codes": [],
         "features": dict(EP)}
    d.update(kw)
    return record_decision(conn, d)


def _feed(conn, pts, ticker="SPY", source="synthetic"):
    before = len(price_paths_since(conn, ticker))
    for t, p in pts:
        assert record_price_path(conn, ticker, t, p, source) is True
    assert record_price_path(conn, ticker, float("nan"), 500.0) is False
    after = price_paths_since(conn, ticker)
    assert len(after) == before + len(pts)
    assert after[before:] == [(float(t), float(p)) for t, p in pts]
    return after


def test_r8_05_tick_closes_open_decision_and_journal_shows_it():
    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    did = _dec(conn)
    _feed(conn, [(0, 490.0), (50, 500.0), (70, 505.0)])
    out = outcome_close_tick(conn, "SPY")
    assert out["decisions_seen"] == 1 and out["closed"] == [did]
    assert out["results"][did]["label"] == "target_hit"
    rows = list_decisions(conn, "SPY")
    assert len(rows) == 1
    assert rows[0]["features"]["outcome_label"] == "target_hit"
    n = conn.execute("SELECT COUNT(*) FROM outcome_labels_v1 WHERE decision_id = "
                     f"'{did}'").fetchone()[0]
    assert n == 1


def test_r8_05_pending_then_final_across_ticks_restart_catchup():
    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    # Horizon 300 anchored at the t=30 encounter → window [30, 330], so the
    # t=150 target contact below is inside the episode (a 60s window would
    # end at t=90 and honestly exclude it).
    feats = dict(EP, horizon_s=300)
    did = _dec(conn, features=feats)
    # Tick 1: path ends mid-window (last t=60 < window end 330) → censored,
    # honestly incomplete — NOT sealed as final.
    _feed(conn, [(0, 490.0), (30, 500.0), (60, 501.0)])
    out1 = outcome_close_tick(conn, "SPY")
    assert out1["closed"] == [did]
    assert out1["results"][did]["censored"] is True
    # Tick 2 (restart catch-up): longer path hits the target → terminal.
    _feed(conn, [(90, 501.0), (120, 503.0), (150, 506.0)])
    out2 = outcome_close_tick(conn, "SPY")
    assert out2["closed"] == [did]
    assert out2["results"][did]["label"] == "target_hit"
    assert out2["results"][did]["censored"] is False
    # Tick 3: duplicate — terminal row stands, nothing rewritten.
    out3 = outcome_close_tick(conn, "SPY")
    assert out3["closed"] == [] and out3["skipped_idempotent"] == [did]
    n = conn.execute("SELECT COUNT(*) FROM outcome_labels_v1 WHERE decision_id = "
                     f"'{did}'").fetchone()[0]
    assert n == 1


def test_r8_05_policy_rerun_writes_separate_row():
    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    did = _dec(conn)
    _feed(conn, [(0, 490.0), (50, 500.0), (70, 505.0)])
    out1 = outcome_close_tick(conn, "SPY")
    assert out1["closed"] == [did]
    # Same episode under a new policy version is a different experiment:
    # it closes separately; the old row is untouched.
    conn.execute("UPDATE scenario_decisions_v1 SET features = "
                 "'{\"spot\": 500.0, \"zone\": [498, 502], \"target\": 505.0, "
                 "\"stop\": 495.0, \"horizon_s\": 60, "
                 "\"policy_version\": \"research_barriers.v2\"}' "
                 f"WHERE decision_id = '{did}'")
    out2 = outcome_close_tick(conn, "SPY")
    assert out2["closed"] == [did]
    rows = conn.execute("SELECT policy_version, label FROM outcome_labels_v1 "
                        f"WHERE decision_id = '{did}' ORDER BY policy_version").fetchall()
    assert [r[0] for r in rows] == ["research_barriers.v1", "research_barriers.v2"]
    assert [r[1] for r in rows] == ["target_hit", "target_hit"]


def test_r8_05_multi_horizon_list_expands_per_horizon():
    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    feats = dict(EP, horizon_s=[60, 300])
    did = _dec(conn, features=feats)
    _feed(conn, [(0, 490.0), (50, 500.0), (70, 505.0)])
    out = close_episodes(conn, {did: [(0, 490.0), (50, 500.0), (70, 505.0)]})
    assert out["closed"] == [did]
    assert set(out["results"][did].keys()) == {"60.0", "300.0"}
    n = conn.execute("SELECT COUNT(*) FROM outcome_labels_v1 WHERE decision_id = "
                     f"'{did}'").fetchone()[0]
    assert n == 2
    # Scalar episodes keep the flat results shape (backward compatible).
    did2 = _dec(conn)
    out2 = close_episodes(conn, {did2: [(0, 490.0), (50, 500.0), (70, 505.0)]})
    assert out2["results"][did2]["label"] == "target_hit"


def test_r8_05_worker_is_default_disabled_at_scheduler():
    import os
    # The scheduler hook only fires on explicit opt-in; default env off.
    assert os.environ.get("SOLSTICE_OUTCOME_WORKER") != "1"
    import inspect

    import server
    src = inspect.getsource(server._scheduler_loop)
    assert 'os.environ.get("SOLSTICE_OUTCOME_WORKER") == "1"' in src
    assert "outcome_close_tick" in src
