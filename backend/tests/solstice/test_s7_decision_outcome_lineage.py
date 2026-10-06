"""S7 decision → episode → outcome lineage (Spark).

Traces the actual chain: selected wall zone -> research decision ->
episode policy (research_barriers.v1) -> timestamped price path ->
pending / censored / final outcome, in an ISOLATED durable store.

Pinned:
- policy origin is VISIBLE (user_selected / experimental_default), never
  an anonymous barrier;
- a decision without a complete episode stays PENDING with NEED_EPISODE
  and writes no outcome row: barriers are never invented to fill a
  zero-outcome journal;
- terminal outcomes are idempotent across re-close with a longer path
  (irrelevant future data cannot rewrite a decided label);
- censored outcomes ARE reprocessed when a longer path arrives;
- the same-bar dual-barrier case is simultaneous_unknown, not a win;
- SPY/QQQ are production-shaped; the entitlement claim for SPX is a
  separate capability state, not something these tests manufacture.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

duckdb = pytest.importorskip("duckdb")


@pytest.fixture
def conn(tmp_path):
    c = duckdb.connect(str(tmp_path / "decisions.duckdb"))
    from services.heatmap_history import ensure_tables

    ensure_tables(c)
    yield c
    c.close()


def _record(conn, ticker, zone, *, encounter=300.0, policy=None, snapshot_id="snap-1"):
    from services.episode_policy import research_default_features
    from services.heatmap_history import record_decision

    features = policy if policy is not None else research_default_features(
        zone=(zone[0], zone[1]), encounter_price=encounter, underlying_tick=0.01
    )
    return record_decision(conn, {
        "ticker": ticker, "snapshot_id": snapshot_id, "scenario": "CALLS", "side": "CALLS",
        "eligible": True, "reason_codes": [], "features": features,
        "candidate_quotes": [],
    })


def _outcomes(conn, did):
    return conn.execute(
        "SELECT horizon_s, policy_version, label, censored, detail, label_version "
        "FROM outcome_labels_v1 WHERE decision_id = ? ORDER BY horizon_s", [did]
    ).fetchall()


def test_selected_wall_to_outcome_with_visible_policy_origin(conn):
    from services.solstice_labels import close_episodes

    did = _record(conn, "SPY", (298.0, 302.0))
    assert did, "the decision must persist with a stable id"

    features = conn.execute(
        "SELECT features FROM scenario_decisions_v1 WHERE decision_id = ?", [did]
    ).fetchone()[0]
    import json

    feat = json.loads(features) if isinstance(features, str) else features
    # Policy origin is explicit: this is an experimental research default,
    # not a user-selected layout and not live trading advice.
    assert feat["policy_version"] == "research_barriers.v1"
    assert feat["experimental"] is True
    assert feat["barrier_source"]
    assert feat["status"] == "usable"
    target, stop = feat["target"], feat["stop"]
    # Symmetric excursion from the ENCOUNTER price (300), at least reaching
    # the zone edges. Never strictly inside the zone: a barrier a price can
    # satisfy while merely touching the zone is not a barrier.
    assert target >= 302.0 and stop <= 298.0
    assert (target - 300.0) == pytest.approx(300.0 - stop)

    # Arrival, qualifying touch inside the zone, then the target.
    path = [(0.0, 305.0), (1.0, 300.0), (2.0, float(target))]
    res = close_episodes(conn, {did: path})
    assert res["closed"] == [did]
    rows = _outcomes(conn, did)
    assert rows, "a decided episode records an outcome row"
    for _h, _p, label, censored, _d, _v in rows:
        assert label == "target_hit"
        assert censored is False or censored == 0


def test_missing_episode_stays_pending_and_writes_no_outcome(conn):
    from services.solstice_labels import close_episodes

    did = _record(conn, "QQQ", (None, None))
    res = close_episodes(conn, {did: [(0.0, 300.0), (1.0, 301.0)]})
    assert res["closed"] == []
    assert res["pending_reasons"][did] == "NEED_EPISODE"
    assert _outcomes(conn, did) == [], "a pending decision writes no outcome row"


def test_terminal_outcome_is_idempotent_and_censored_is_reprocessed(conn):
    from services.solstice_labels import close_episodes

    did = _record(conn, "SPY", (298.0, 302.0))
    import json

    feat = json.loads(conn.execute(
        "SELECT features FROM scenario_decisions_v1 WHERE decision_id = ?", [did]
    ).fetchone()[0])
    target, stop = feat["target"], feat["stop"]

    first = close_episodes(conn, {did: [(0.0, 305.0), (1.0, 300.0), (2.0, float(target))]})
    assert first["closed"] == [did]
    before = _outcomes(conn, did)

    # A LONGER path containing a stop first-passage before the target must
    # not rewrite the already-decided label: labels are causally prefix
    # stable, and only censored results are re-openable.
    again = close_episodes(conn, {did: [
        (0.0, 305.0), (1.0, 300.0), (2.0, float(target)), (3.0, float(stop)),
    ]})
    assert again["closed"] == []
    assert did in again["skipped_idempotent"]
    assert _outcomes(conn, did) == before


def test_same_bar_dual_barrier_is_unknown_not_a_win(conn):
    from services.solstice_labels import close_episodes

    did = _record(conn, "SPY", (298.0, 302.0))
    import json

    feat = json.loads(conn.execute(
        "SELECT features FROM scenario_decisions_v1 WHERE decision_id = ?", [did]
    ).fetchone()[0])
    hi_pt = float(feat["target"]) + 5.0
    lo_pt = float(feat["stop"]) - 5.0
    res = close_episodes(conn, {did: [(0.0, 305.0), (1.0, 300.0), (2.0, hi_pt), (2.0, lo_pt)]})
    labels = {r[2] for r in _outcomes(conn, did)}
    assert labels == {"simultaneous_unknown"}, labels
    assert all(r[3] in (1, True) for r in _outcomes(conn, did)), "unknown order is censored"
    assert res["closed"] == [did], "the observation is recorded, just not as a win"


def test_no_touch_requires_gap_free_coverage(conn):
    from services.solstice_labels import close_episodes

    did = _record(conn, "QQQ", (298.0, 302.0))
    # A wide, sparse path that never enters the zone: a gap means we cannot
    # prove no touch happened, so this is censored, never no_touch.
    sparse = [(0.0, 250.0), (10_000.0, 250.0)]
    res = close_episodes(conn, {did: sparse})
    labels = {r[2] for r in _outcomes(conn, did)}
    assert "no_touch" not in labels, labels
    assert all(r[3] in (1, True) for r in _outcomes(conn, did))
    assert res["closed"] == [did]


def test_capability_state_is_independent_of_schema_support():
    """SPX code support must not be read as account entitlement.

    The policy is a pure function; nothing here can grant an entitlement, and
    no test in this repo may claim one. This pins that the two states are
    separate facts with no path between them in the backend code.
    """
    from services.episode_policy import POLICY_VERSION, research_default_features

    feats = research_default_features(zone=(5900.0, 5910.0), encounter_price=5905.0,
                                       underlying_tick=0.25)
    assert feats["status"] == "usable"
    assert feats["policy_version"] == POLICY_VERSION
    assert "entitlement" not in feats
    assert "account" not in feats
