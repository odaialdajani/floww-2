"""R5-A red tests: mounted observation contract (G1/R01-R04)."""

import sys

sys.path.insert(0, "backend")


def _base_payload(**kw):
    p = {"ticker": "SPY", "expiries_used": ["2030-01-15"], "spot": 500.0,
         "mode": "day", "dte": None, "scalp": False,
         "data_source": "public_api", "exposure_basis": "OI",
         "formula_version": "gex.v2",
         "asof": "2030-01-02T14:00:00+00:00",
         "source_received_at": "2030-01-02T14:00:01+00:00",
         "strikes": [{"strike": 500, "gex": 1e6, "call_gex": 8e5, "put_gex": 2e5}],
         "quality": {"state": "usable", "reasonCodes": [],
                     "setupEligible": True, "executionEligible": False,
                     "tradeSideCapability": "none"}}
    p.update(kw)
    return p


def test_r01_quality_normalization_idempotent():
    from services.heatmap_snapshot import normalize_quality
    canon = {"state": "usable", "reasonCodes": [],
             "setupEligible": True, "executionEligible": False,
             "tradeSideCapability": "none"}
    assert normalize_quality(canon) == canon
    assert normalize_quality({"setup_eligible": True})["setupEligible"] is True


def test_r02_unknown_source_time_stays_null():
    from services.heatmap_snapshot import build_snapshot_v2
    snap = build_snapshot_v2(_base_payload())
    assert snap["times"]["sourceMinAt"] is None
    assert snap["times"]["sourceMaxAt"] is None


def test_r03_volume_only_observation_retained():
    import duckdb

    from services.heatmap_history import record_snapshot, replay_snapshot
    from services.heatmap_snapshot import content_digest, snapshot_id_for
    p1 = _base_payload()
    p2 = _base_payload()
    assert content_digest(p1) == content_digest(p2)
    assert snapshot_id_for(p1) == snapshot_id_for(p1)
    p2["asof"] = "2030-01-02T14:01:00+00:00"
    assert snapshot_id_for(p1) != snapshot_id_for(p2)
    conn = duckdb.connect(":memory:")
    s1 = record_snapshot(conn, p1, "q")
    s2 = record_snapshot(conn, p2, "q")
    assert s1 != s2
    assert replay_snapshot(conn, s1) is not None
    assert replay_snapshot(conn, s2) is not None


def test_r04_mounted_payload_carries_scope_identity_quality():
    from services.heatmap_snapshot import content_digest, normalize_quality
    p = _base_payload()
    # DTE/scalp participate in identity.
    assert content_digest(p) != content_digest(dict(p, dte=0))
    assert content_digest(p) != content_digest(dict(p, scalp=True))
    # Canonical quality survives the shared adapter unchanged.
    assert normalize_quality(p["quality"]) == p["quality"]
