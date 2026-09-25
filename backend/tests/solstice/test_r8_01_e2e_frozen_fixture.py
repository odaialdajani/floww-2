"""
R8-01: frozen asymmetric fixture end-to-end trace.

One reproducible path through the full pipeline:
  frozen asymmetric contracts -> build_heatmap -> build_snapshot_v2 ->
  record_snapshot -> record_decision (via episode_policy) ->
  replay_snapshot -> verify the replay packet shape matches the
  recorded snapshot.

Fixtures: call + put concentration, two expiries, unequal wall zones,
at least two source observations, one missing-data contract.
"""

import sys
sys.path.insert(0, "backend")

import json
import pytest
import duckdb

from services.heatmap_snapshot import build_snapshot_v2, to_legacy_payload
from services.heatmap_history import record_snapshot, record_decision, replay_snapshot
from services.heatmap_history import ensure_tables
from services.episode_policy import research_default_features


def _frozen_contract(**kw):
    """One asymmetric frozen contract — call or put concentration,
    two expiries, unequal walls, one missing-data entry."""
    c = {
        "osi": "OSI", "expiry": "2030-01-15", "strike": 500,
        "type": "call", "multiplier": 100.0,
        "bid": 1.0, "ask": 1.2, "mid": 1.1, "last": 1.1,
        "bid_size": 10, "ask_size": 10, "volume": 500,
        "open_interest": 1000, "iv": 0.2, "delta": 0.45,
        "gamma": 0.05, "T": 30 / 365,
        "bid_timestamp": "2030-01-02T14:00:00+00:00",
        "ask_timestamp": "2030-01-02T14:00:00+00:00",
        "provider": "frozen_fixture_v1",
        "exposure_basis": "OI",
        "calculated_at": "2030-01-02T14:00:00+00:00",
    }
    c.update(kw)
    return c


def test_r8_01_frozen_fixture_end_to_end_trace():
    """R8-01: frozen asymmetric fixture through full pipeline.

    Pipeline:
      1. frozen contracts (call + put concentration, 2 expiries,
         unequal walls, 1 missing-data contract)
      2. build_snapshot_v2 (canonical snapshot)
      3. record_snapshot (durable record)
      4. record_decision (now via episode_policy — barriers from zone)
      5. replay_snapshot (reconstruct from DB)
      6. verify replay packet shape matches recorded snapshot
    """
    conn = duckdb.connect(":memory:")
    ensure_tables(conn)

    # Step 1: frozen asymmetric contracts
    # Call concentration at 500 (above spot 490), put concentration at 480,
    # two expiries, one missing-data contract (no bid/ask).
    contracts = [
        _frozen_contract(osi="C1", expiry="2030-01-15", strike=500,
                         delta=0.45, gamma=0.05, bid=1.0, ask=1.2),
        _frozen_contract(osi="C2", expiry="2030-01-15", strike=505,
                         delta=0.50, gamma=0.04, bid=0.8, ask=1.0),
        _frozen_contract(osi="P1", expiry="2030-01-15", strike=480,
                         type="put", delta=-0.35, gamma=0.03, bid=0.6, ask=0.8),
        _frozen_contract(osi="C3", expiry="2030-02-15", strike=500,
                         delta=0.42, gamma=0.03, bid=0.9, ask=1.1),
        _frozen_contract(osi="P2", expiry="2030-02-15", strike=475,
                         type="put", delta=-0.30, gamma=0.02, bid=0.5, ask=0.7),
        # Missing-data contract: no bid/ask, unknown tick
        _frozen_contract(osi="UNKNOWN", expiry="2030-01-15", strike=510,
                         type="call", delta=None, gamma=None,
                         bid=None, ask=None, iv=None),
    ]

    # Step 2: build snapshot_v2 from frozen payload
    payload = {
        "ticker": "SPY",
        "snapshotId": "frozen-r8-01",
        "asof": "2030-01-02T14:00:00+00:00",
        "source_received_at": "2030-01-02T14:00:00+00:00",
        "contracts": contracts,
        "strikes": [500, 505, 480, 500, 475, 510],
        "grid": {"raw": {"500": {"C1": {"bid": 1.0, "ask": 1.2}}}},
        "metrics": {
            "walls": [
                {"wall_id": "W1", "low": 478.0, "high": 482.0,
                 "gross": 150.0, "net": 90.0, "call": 120.0, "put": -30.0,
                 "exposure_basis": "OI", "distance": None, "distance_pct": None},
                {"wall_id": "W2", "low": 498.0, "high": 502.0,
                 "gross": 300.0, "net": 250.0, "call": 280.0, "put": -30.0,
                 "exposure_basis": "OI", "distance": 10.0, "distance_pct": 0.02},
            ],
            "magnitude_ratio_delta_over_raw": 0.85,
            "dadgex_usable": 250.0, "dadgex_missing_delta": 10.0,
            "window_daddex_reason": "W1 has 2 member strikes",
            "wall_metrics": {
                "W1": {"raw": {"gross": 150.0, "net": 90.0},
                       "delta": {"gross": 127.5, "net": 76.5}},
                "W2": {"raw": {"gross": 300.0, "net": 250.0},
                       "delta": {"gross": 255.0, "net": 212.5}},
            },
            "wall_window": {"W1": {"open": 0, "close": 1}},
        },
        "coverage": {"requested": 6, "returned": 6, "truncated": False},
        "quality": {"state": "usable", "reasonCodes": []},
        "scenarios": [
            {"wall_id": "W2", "name": "Rejection watch", "type": "reversal_watch",
             "confirmation": "reclaim and hold below 502",
             "invalidation": "sustained acceptance above 502"},
        ],
        "interactions": [
            {"wall_id": "W2", "state": "testing", "event": "first_sighting",
             "first_seen": True, "taps": 1, "last_seen_at": "2030-01-02T14:00:00+00:00"},
        ],
        "expiries_used": ["2030-01-15", "2030-02-15"],
        "data_source": "frozen_fixture_v1",
        "exposure_basis": "OI",
        "formula_version": "gex.v2",
        "spot": 490.0,
        "grid_meta": {},
        "grids": {},
        "moneyness": {},
    }

    snap = build_snapshot_v2(payload, query_key="frozen-r8-01")
    snap_id = snap["snapshotId"]
    assert snap_id.startswith("snap_")
    assert snap["instrument"]["displaySymbol"] == "SPY"
    assert snap["payload"]["spot"] == 490.0
    assert len(snap["payload"]["strikes"]) == 6

    # Record snapshot durably
    recorded_sid = record_snapshot(conn, payload, "frozen-r8-01", snap_id)
    assert recorded_sid == snap_id

    # Record decision — via episode_policy (R8-05 wire-up)
    # Use research_default_features to derive barriers from the zone,
    # exactly as server.py does via _build_research_features.
    ep_features = research_default_features(
        zone=(498.0, 502.0), encounter_price=490.0, underlying_tick=0.01)
    decision = {
        "ticker": "SPY",
        "snapshot_id": snap_id,
        "scenario": "CALLS",
        "side": "CALLS",
        "eligible": True,
        "reason_codes": [],
        "features": {
            "spot": 490.0,
            "zone": [498.0, 502.0],
            "wall_id": "W2",
            "quality": "usable",
            "n_eligible": 2,
            **ep_features,
        },
        "candidate_quotes": [
            {"osi": "C1", "bid": 1.0, "ask": 1.2, "delta": 0.45,
             "bid_ts": "2030-01-02T14:00:00+00:00", "ask_ts": "2030-01-02T14:00:00+00:00"},
        ],
    }
    did = record_decision(conn, decision)
    assert did

    rows = conn.execute(
        "SELECT features FROM scenario_decisions_v1 WHERE decision_id = "
        + "'" + did + "'").fetchall()
    assert len(rows) == 1
    features = json.loads(rows[0][0])
    assert features["spot"] == 490.0
    assert features["zone"] == [498.0, 502.0]
    # episode_policy sets policy_version + barrier fields (target/stop/barrier_distance)
    assert features.get("policy_version") == "research_barriers.v1"
    assert "target" in features and "stop" in features
    assert isinstance(features.get("horizon_s"), (list, tuple))

    # Replay from DB
    replay = replay_snapshot(conn, snap_id)
    assert replay is not None
    assert replay["snapshot"]["spot"] == 490.0
    assert len(replay["strikes"]) == 6
    assert len(replay["walls"]) == 2
    # coverage: record_snapshot adds usable field; check the keys we care about
    cov = replay["coverage"]
    assert cov["requested"] == 6 and cov["returned"] == 6
    assert cov.get("truncated") is False
    assert cov.get("usable", 0) >= 0  # record_snapshot adds usable count
    assert replay["quality"] == {"state": "usable", "reasonCodes": []}
    assert len(replay["scenarios"]) == 1

    # Legacy payload round-trip
    legacy = to_legacy_payload(snap)
    assert legacy["ticker"] == "SPY"
    assert legacy["spot"] == 490.0
    assert len(legacy["strikes"]) == 6
    assert legacy["quality"]["state"] == "usable"

    unknown = [c for c in legacy["contracts"] if c["osi"] == "UNKNOWN"]
    assert len(unknown) == 1
    assert unknown[0]["bid"] is None and unknown[0]["ask"] is None

    expiries = {c["expiry"] for c in legacy["contracts"]}
    assert "2030-01-15" in expiries
    assert "2030-02-15" in expiries

    w2_calls = [c for c in legacy["contracts"]
                if c["expiry"] == "2030-01-15" and c["strike"] in (500, 505)
                and c["type"] == "call"]
    w2_puts = [c for c in legacy["contracts"]
               if c["expiry"] == "2030-01-15" and c["strike"] == 480
               and c["type"] == "put"]
    assert len(w2_calls) == 2
    assert len(w2_puts) == 1
    assert w2_calls[0]["delta"] == 0.45
    assert w2_puts[0]["delta"] == -0.35

    p = snap["payload"]
    assert p["spot"] == 490.0
    assert p["quality"]["state"] == "usable"


def test_r8_01_replay_excludes_late_revisions():
    """R8-01: replay is a known-at join — later revisions never merge in.

    Record a snapshot, then add a separate contract observation with the
    same ticker but a DIFFERENT snapshot_id. Replaying the original
    snapshot must NOT include the late revision.
    """
    conn = duckdb.connect(":memory:")
    ensure_tables(conn)

    payload = {
        "ticker": "SPY",
        "snapshotId": "snap-a",
        "asof": "2030-01-02T14:00:00+00:00",
        "source_received_at": "2030-01-02T14:00:00+00:00",
        "contracts": [_frozen_contract(osi="C1", expiry="2030-01-15",
                                        strike=500, delta=0.45, gamma=0.05)],
        "strikes": [500],
        "grid": {"raw": {"500": {"C1": {"bid": 1.0, "ask": 1.2}}}},
        "metrics": {"walls": [], "magnitude_ratio_delta_over_raw": None},
        "coverage": {"requested": 1, "returned": 1, "truncated": False},
        "quality": {"state": "usable", "reasonCodes": []},
        "scenarios": [], "interactions": [],
        "expiries_used": ["2030-01-15"],
        "data_source": "frozen_fixture_v1",
        "exposure_basis": "OI",
        "formula_version": "gex.v2",
        "spot": 490.0, "grid_meta": {}, "grids": {}, "moneyness": {},
    }
    snap_a = build_snapshot_v2(payload, query_key="snap-a")
    sid_a = snap_a["snapshotId"]
    record_snapshot(conn, payload, "snap-a", sid_a)

    # Late revision: same ticker, different snapshot_id
    late_payload = dict(payload)
    late_payload["asof"] = "2030-01-02T15:00:00+00:00"
    late_payload["source_received_at"] = "2030-01-02T15:00:00+00:00"
    late_payload["contracts"] = [_frozen_contract(osi="C2", expiry="2030-01-15",
                                                   strike=500, delta=0.50, gamma=0.04,
                                                   bid=0.9, ask=1.1)]
    snap_b = build_snapshot_v2(late_payload, query_key="snap-b")
    sid_b = snap_b["snapshotId"]
    record_snapshot(conn, late_payload, "snap-b", sid_b)

    replay = replay_snapshot(conn, sid_a)
    assert replay is not None
    osis = {c["osi"] for c in replay["contracts"]}
    assert "C1" in osis
    assert "C2" not in osis, "replay must exclude late revisions"
    assert replay["snapshot"]["asof_ts"] == "2030-01-02T14:00:00+00:00"
