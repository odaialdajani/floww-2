"""Solstice slice 2: T04 grids, T09 recorder/replay, T10 scout, T15 regime,
T16 patterns, T17 vanna, T19 session, T20 sizing, T22 eval, T25 missed,
T11 labels, T28 research, T18 registry, wall interaction, longevity."""

import sys

sys.path.insert(0, "backend")

SPOT = 500.0


def _c(strike, typ, gamma, oi, delta=0.5, vol=100, expiry="2030-01-15", T=30 / 365, iv=0.2):
    return {"strike": strike, "type": typ, "gamma": gamma, "oi": oi,
            "delta": delta, "volume": vol, "expiry": expiry, "T": T, "iv": iv,
            "osi": f"X{strike}{typ}", "multiplier": 100.0, "bid": 1.0, "ask": 1.2,
            "bid_timestamp": None, "ask_timestamp": None, "last_timestamp": None,
            "greeks_source": "vendor", "oi_source": "public_api",
            "exposure_basis": "OI", "received_at": "2030-01-01T00:00:00+00:00"}


def test_t04_delta_grid_same_scope():
    from services.gex_core import compute_gex_grid_delta_weighted, compute_gex_grid_vendor
    contracts = [_c(500, "call", 0.05, 1000, 0.45), _c(500, "put", 0.05, 1000, -0.45)]
    v = compute_gex_grid_vendor(SPOT, contracts)
    d = compute_gex_grid_delta_weighted(SPOT, contracts)
    assert v["expiries"] == d["expiries"] == ["2030-01-15"]
    assert d["exposure_basis"] == "OI_DELTA_WEIGHTED"
    assert d["missing_delta"] == 0
    # Same scope invariants: |delta net| <= delta gross <= raw gross
    vg = sum(abs(x) for col in v["grid"].values() for x in col.values())
    dg = sum(abs(x) for col in d["grid"].values() for x in col.values())
    assert dg <= vg + 1.0


def test_t04_delta_missing_not_zero():
    from services.gex_core import compute_gex_grid_delta_weighted
    c = _c(500, "call", 0.05, 1000)
    c.pop("delta")
    d = compute_gex_grid_delta_weighted(SPOT, [c])
    assert d["grid"] == {} and d["missing_delta"] == 1


def test_t09_record_replay_available_at():
    import duckdb

    from services.heatmap_history import (
        compare_snapshots,
        record_snapshot,
        replay_snapshot,
        session_manifest,
    )
    conn = duckdb.connect(":memory:")
    payload = {"ticker": "TST", "expiries_used": ["2030-01-15"], "spot": SPOT,
               "data_source": "public_api", "exposure_basis": "OI",
               "formula_version": "gex.v2", "asof": "2030-01-02T00:00:00+00:00",
               "source_received_at": "2030-01-02T00:00:00+00:00",
               "contracts": [_c(500, "call", 0.05, 1000)],
               "strikes": [{"strike": 500, "gex": 1e6}],
               "metrics": {"walls": [{"wall_id": "w_a", "low": 498, "high": 502,
                                      "mid": 500, "gross": 1e6, "members": [500]}]}}
    sid = record_snapshot(conn, payload, "q")
    assert sid
    assert record_snapshot(conn, payload, "q") == sid  # idempotent, no duplicate event
    rep = replay_snapshot(conn, sid)
    assert rep and len(rep["contracts"]) == 1
    assert rep["strikes"][0]["strike"] == 500
    assert rep["walls"][0]["wall_id"] == "w_a"
    man = session_manifest(conn, "TST", "2030-01-02")
    assert man["n_snapshots"] == 1
    # Single snapshot → comparison unavailable (never a one-point trend).
    assert compare_snapshots(conn, "TST", "2030-01-02")["status"] == "history_unavailable"
    payload2 = dict(payload, asof="2030-01-02T01:00:00+00:00",
                    strikes=[{"strike": 500, "gex": 2e6}],
                    metrics={"walls": [{"wall_id": "w_a", "low": 498, "high": 502,
                                        "mid": 500, "gross": 2e6, "members": [500]},
                                       {"wall_id": "w_b", "low": 510, "high": 514,
                                        "mid": 512, "gross": 5e5, "members": [512]}]})
    sid2 = record_snapshot(conn, payload2, "q")
    assert sid2 != sid
    cmp_ = compare_snapshots(conn, "TST", "2030-01-02")
    assert cmp_["status"] == "ok"
    assert cmp_["walls_added"] == ["w_b"] and cmp_["walls_retained"] == ["w_a"]
    assert cmp_["strike_deltas"][0]["delta"] == 1e6


def test_t10_scout_side_first_and_rejections():
    from services.contract_scout import scout_candidates
    contracts = [_c(500, "call", 0.05, 1000, 0.5, 500), _c(500, "put", 0.05, 1000, -0.5, 500)]
    r = scout_candidates(contracts, "CALLS", SPOT)
    assert r["n_eligible"] == 1
    assert r["rejected"].get("WRONG_SIDE") == 1
    empty = scout_candidates([], "CALLS", SPOT)
    assert empty["no_candidate_is_valid"] and empty["n_eligible"] == 0


def test_t15_roots_and_no_permission():
    from services.solstice_regime import regime_at_spot
    contracts = [_c(490, "call", 0.05, 1000, T=30 / 365), _c(510, "put", 0.05, 1000, T=30 / 365)]
    r = regime_at_spot(SPOT, contracts, "SPY")
    assert r["directional_permission"] == "NONE"
    assert isinstance(r["roots"], list)
    assert "model_vendor_residual" in r


def test_t16_patterns_guarded():
    from services.solstice_patterns import detect_patterns_v1, distant_node_relevance
    assert detect_patterns_v1([], SPOT)[0]["state"] == "INSUFFICIENT_DATA"
    rows = [{"strike": 480 + i * 5, "gex": 1e6 if i in (4, 8) else 1e4,
             "call_gex": 5e5 if i in (4, 8) else 5e3, "put_gex": 5e5 if i in (4, 8) else 5e3}
            for i in range(12)]
    pats = detect_patterns_v1(rows, SPOT)
    assert isinstance(pats, list)
    rel = distant_node_relevance(700.0, SPOT, [])
    assert rel["relevance"] == "limited" and rel["z"] is None


def test_t17_vanna_separate_and_removal():
    from services.solstice_vanna import expiry_removal_view, vanna_by_expiry
    contracts = [_c(500, "call", 0.05, 1000, T=30 / 365, expiry="2030-01-15"),
                 _c(500, "call", 0.05, 1000, T=60 / 365, expiry="2030-02-15")]
    v = vanna_by_expiry(contracts, SPOT)
    assert "2030-01-15" in v["by_expiry"] and "vomma" in v["by_expiry"]["2030-01-15"]
    rem = expiry_removal_view(contracts, SPOT, ["2030-01-15"])
    assert 0 <= (rem["expiring_share"] or 0) <= 1


def test_t19_session_permissions():
    from services.solstice_session import playbook_for, session_state
    s = session_state(quality={"state": "usable", "reasonCodes": []})
    assert s["management_allowed"] is True
    pb = playbook_for(None, SPOT, {"state": "stale"})
    assert pb["playbook"] == "no_setup"


def test_t20_sizing_never_rounds_zero_up():
    from services.solstice_strategy import breakeven_win_rate, size_contracts
    assert size_contracts(10.0, {"premium_budget": 5.0})["qty"] == 0
    assert size_contracts(None, {"premium_budget": 100.0})["qty"] == 0
    assert size_contracts(10.0, {"premium_budget": 100.0})["qty"] == 10
    assert abs(breakeven_win_rate(2.0, 1.0) - 1 / 3) < 1e-9


def test_t22_eval_corpus_and_fallback():
    from services.solstice_ai_eval import run_corpus
    rep = run_corpus()
    assert rep["n"] == 8 and rep["passed"] == 8


def test_t25_missed_ledger_causal():
    from services.solstice_missed import record_encounter, resolve_encounter, session_review
    store: list = []
    record_encounter(store, {"wall": "500-505", "rule": "reclaim_hold"})
    assert store[0]["outcome"] is None
    r = resolve_encounter(store[0], {"label": "target_hit", "bottleneck": "fill_quality"})
    rev = session_review([r])
    assert rev["n_encounters"] == 1 and len(rev["research_questions"]) <= 3


def test_t11_labels_first_passage():
    from services.solstice_labels import HORIZONS_S, label_touch, walk_forward_splits
    assert HORIZONS_S == (60, 180, 300, 900)
    path = [(0, 500.0), (10, 505.0), (10, 495.0)]
    assert label_touch(path, (498, 502), 60, 505.0, 495.0)["label"] == "simultaneous_unknown"
    assert label_touch([(0, 500.0), (10, 506.0)], (498, 502), 60, 505.0, 490.0)["label"] == "target_hit"
    assert len(walk_forward_splits(["a", "b", "c", "d", "e", "f"])) == 3


def test_t28_research_units_kept_separate():
    from services.solstice_research import q1_features, q2_timer, q3_discrepancy, sizing_ablation
    assert q1_features(1.0, 0.9, 2.0)["thresholds"]["status"] == "UNVALIDATED_SEARCH_CANDIDATES"
    assert q2_timer(5.0, None)["timer"] is None
    q3 = q3_discrepancy(1.1, 1.0, 0.05, 0.2)
    assert abs(q3["rhat"] - 1.0) < 1e-9  # |rhat|=1 is HALF spread
    assert q3["execution"] == "BLOCKED_public_only_diagnostic"
    assert sizing_ablation([0.1, -0.05, 0.2])["n"] == 3


def test_t18_registry_27_ops():
    from services.public_capability import registry
    reg = registry()
    assert reg["count"] == 27
    assert any(o["op"] == "cancel_order" for o in reg["operations"])


def test_wall_interaction_time_debounced():
    from datetime import UTC, datetime, timedelta

    from services.wall_interaction import scenario_for, transition
    wall = {"low": 498.0, "high": 502.0}
    t0 = datetime(2030, 1, 2, 12, 0, tzinfo=UTC)
    s1 = transition("unobserved", 500.0, wall, now=t0)
    assert s1["state"] == "testing"
    s2 = transition("testing", 500.0, wall, now=t0 + timedelta(seconds=61),
                    last={"state": "testing", "at": t0.isoformat(), "approach_side": "above"})
    assert s2["state"] in ("holding", "rejecting")
    assert len(scenario_for(wall, 500.0)) == 2


def test_t29_migration_additive():
    from services.solstice_longevity import migrate_snapshot_v1_to_v2
    v2 = migrate_snapshot_v1_to_v2({"ticker": "SPY"})
    assert v2["schemaVersion"] == "2" and v2["_migrated_from"] == "1"


def test_t08_enrichment_no_inference():
    from services.solstice_enrichment import moneyness_buckets, oi_changes
    m = moneyness_buckets([_c(500, "call", 0.05, 100, 0.5)], SPOT)
    assert "call_atm" in m["buckets"]
    prev = [dict(_c(500, "call", 0.05, 100), oi_effective_date="2030-01-01")]
    cur = [dict(_c(500, "call", 0.05, 150), oi_effective_date="2030-01-02")]
    oc = oi_changes(cur, prev)
    assert oc["changes"][0]["delta"] == 50
