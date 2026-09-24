"""R5 holes-batch red tests: scout strictness, validator staleness, storage truth."""

import sys

sys.path.insert(0, "backend")


def _c(**kw):
    base = {"osi": "X", "type": "call", "strike": 500, "bid": 1.0, "ask": 1.2,
            "bid_timestamp": "2030-01-02T14:00:00+00:00",
            "ask_timestamp": "2030-01-02T14:00:00+00:00",
            "delta": 0.5, "gamma": 0.05, "volume": 500, "T": 0.5 / 365,
            "expiry": "2030-01-02"}
    base.update(kw)
    return base


def _now(s):
    from datetime import UTC, datetime
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.timestamp() if dt.tzinfo else dt.replace(tzinfo=UTC).timestamp()


def test_hole_scout_rejects_adjusted_and_unknown_side():
    from services.contract_scout import REJECT_REASONS, scout_candidates
    now = _now("2030-01-02T14:00:10+00:00")
    r = scout_candidates([_c(adjusted=True)], "CALLS", 500.0, now_s=now,
                         session_date="2030-01-02")
    assert r["n_eligible"] == 0
    assert r["rejected"].get("UNSUPPORTED_SERIES") == 1
    r2 = scout_candidates([_c()], "MAYBE", 500.0, now_s=now,
                          session_date="2030-01-02")
    assert r2["n_eligible"] == 0 and r2["no_candidate_is_valid"]
    assert "UNKNOWN_SIDE" in REJECT_REASONS


def test_hole_validator_rejects_stale_wall():
    from services.solstice_ai_eval import _packet_for
    from services.solstice_evidence import validate_explainer_output
    pkt = _packet_for({"id": "stale_ask",
                       "quality": {"setupEligible": False, "reasonCodes": ["STALE_ASK"]}})
    out = {"snapshot_id": pkt["snapshot_id"], "query_id": pkt["query_id"],
           "status": "Wait", "headline": "waiting", "observations": [],
           "hypotheses": [], "conflicts": [], "next_condition": "x",
           "invalidation": "y", "candidate_refs": [], "evidence_refs": ["fact-spot"],
           "wall_id": "w_different"}
    assert any("wall" in e for e in validate_explainer_output(out, pkt))


def test_hole_broken_storage_returns_none():
    import duckdb

    from services.heatmap_history import record_snapshot
    conn = duckdb.connect(":memory:")
    conn.close()
    assert record_snapshot(conn, {"ticker": "SPY"}, "q") is None


def test_hole_window_end_to_end_from_recorded_baseline():
    import duckdb

    from services.heatmap_history import (
        normalize_stored_contract,
        record_snapshot,
        replay_snapshot,
    )
    from services.solstice_enrichment import window_contract_activity
    conn = duckdb.connect(":memory:")
    base = {"ticker": "SPY", "expiries_used": ["2030-01-15"], "spot": 500.0,
            "data_source": "public_api", "exposure_basis": "OI",
            "formula_version": "gex.v2", "asof": "2030-01-02T14:00:00+00:00",
            "contracts": [_c(volume=100)], "strikes": [], "metrics": {"walls": []}}
    sid = record_snapshot(conn, base, "q")
    prev = [normalize_stored_contract(c) for c in replay_snapshot(conn, sid)["contracts"]]
    cur = [_c(volume=140)]
    out = window_contract_activity(prev, cur, 500.0)
    assert out["status"] == "ok" and out["contracts"][0]["window_daddex"] > 0


def test_hole_gap_unknown_time_and_dst():
    from datetime import UTC, datetime

    from services.solstice_session import session_state
    from services.wall_interaction import detect_wall_gap
    assert detect_wall_gap({"state": "testing"}, datetime(2030, 1, 2, 12, 0, tzinfo=UTC),
                           "public_api") is True
    july_pre = datetime(2030, 7, 2, 11, 0, tzinfo=UTC)  # 07:00 EDT pre-open
    s = session_state(now=july_pre, quality={"state": "usable", "reasonCodes": [],
                                             "setupEligible": True})
    assert s["entry_allowed"] is False
    july_open = datetime(2030, 7, 2, 14, 0, tzinfo=UTC)  # 10:00 EDT
    s2 = session_state(now=july_open, quality={"state": "usable", "reasonCodes": [],
                                               "setupEligible": True})
    assert s2["entry_allowed"] is True
