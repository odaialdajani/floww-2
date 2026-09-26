"""P03 red-first tests (R4-07,10,14,15,16). Each fails on baseline behavior."""

import sys

sys.path.insert(0, "backend")


def _row(strike, gex, call=None, put=None):
    return {"strike": strike, "gex": gex,
            "call_gex": gex if (call is None and gex > 0) else (call or 0.0),
            "put_gex": gex if (put is None and gex < 0) else (put or 0.0)}


def test_r4_07_side_specific_nearest():
    from services.wall_structure import discover_walls, nearest_by_side
    rows = [_row(90.0, 5e6), _row(92.0, 6e6), _row(110.0, 7e6), _row(112.0, 8e6)]
    walls = discover_walls(rows, 100.0, pct_threshold=0.0)
    sides = nearest_by_side(walls, 100.0)
    assert sides["below"] is not None and sides["below"]["high"] <= 100.0
    assert sides["above"] is not None and sides["above"]["low"] >= 100.0
    assert sides["below"]["wall_id"] != sides["above"]["wall_id"]


def test_r4_07_zero_mass_never_forms_walls():
    from services.wall_structure import discover_walls
    assert discover_walls([_row(90.0, 0.0), _row(100.0, 0.0)], 95.0) == []
    walls = discover_walls([_row(90.0, 5e6), _row(95.0, 0.0), _row(100.0, 6e6)],
                           92.0, pct_threshold=0.0)
    for w in walls:
        assert 95.0 not in w["members"]


def test_r4_07_gap_breaks_zones_and_ids_are_scoped():
    from services.wall_structure import discover_walls
    rows = [_row(100.0, 5e6), _row(101.0, 5e6), _row(102.0, 5e6),
            _row(200.0, 5e6), _row(201.0, 5e6)]
    walls = discover_walls(rows, 150.0, pct_threshold=0.0)
    assert len(walls) == 2
    a = discover_walls(rows, 150.0, pct_threshold=0.0,
                       scope={"symbol": "SPY", "formula": "gex.v2"})
    b = discover_walls(rows, 150.0, pct_threshold=0.0,
                       scope={"symbol": "QQQ", "formula": "gex.v2"})
    assert {w["wall_id"] for w in a} != {w["wall_id"] for w in b}


def test_r4_10_absent_baseline_is_unknown():
    from services.solstice_enrichment import oi_changes
    cur = [dict(strike=500, type="call", oi=150, oi_effective_date="2030-01-02")]
    out = oi_changes(cur, [])
    assert out["changes"] == []
    assert out["n_unknown_baseline"] == 1


def test_r4_10_one_sided_date_excluded():
    from services.solstice_enrichment import oi_changes
    cur = [dict(strike=500, type="call", oi=150, oi_effective_date="2030-01-02")]
    prev = [dict(strike=500, type="call", oi=100)]  # no date
    out = oi_changes(cur, prev)
    assert out["changes"] == []
    assert out["n_date_unknown"] == 1


def test_r4_14_window_daddex_matched_epoch():
    from services.solstice_enrichment import window_contract_activity
    prev = [{"osi": "A", "expiry": "2030-01-15", "type": "call", "strike": 500,
             "gamma": 0.05, "delta": 0.5, "multiplier": 100, "oi": 100, "volume": 1000,
             "bid_timestamp": "2030-01-02T00:00:00+00:00"}]
    cur = [{"osi": "A", "expiry": "2030-01-15", "type": "call", "strike": 500,
            "gamma": 0.05, "delta": 0.5, "multiplier": 100, "oi": 100, "volume": 1400,
            "bid_timestamp": "2030-01-02T01:00:00+00:00"}]
    out = window_contract_activity(prev, cur, 500.0)
    assert out["status"] == "ok"
    assert len(out["contracts"]) == 1
    c = out["contracts"][0]
    # u=0.05*100*500^2*0.01=12500; dV=400; |δ|=.5 → 12500*400*.5 = 2.5M
    assert abs(c["window_daddex"] - 2_500_000) < 1.0
    assert c["pair"] == "vendor/vendor"


def test_r4_14_window_rebase_and_missing_delta():
    from services.solstice_enrichment import window_contract_activity
    prev = [{"osi": "A", "expiry": "2030-01-15", "type": "call", "strike": 500,
             "gamma": 0.05, "delta": 0.5, "multiplier": 100, "oi": 100, "volume": 1400,
             "bid_timestamp": "2030-01-02T00:00:00+00:00"}]
    cur = [{"osi": "A", "expiry": "2030-01-15", "type": "call", "strike": 500,
            "gamma": 0.05, "delta": 0.5, "multiplier": 100, "oi": 100, "volume": 1180,
            "bid_timestamp": "2030-01-02T01:00:00+00:00"}]
    out = window_contract_activity(prev, cur, 500.0)
    assert out["status"] == "unavailable"
    assert out["reason"] == "VOLUME_REBASE"
    nod = [dict(cur[0], delta=None)]
    out2 = window_contract_activity(prev, nod, 500.0)
    assert out2["contracts"] == [] and out2["missing_delta"] == 1


def test_r4_16_regime_metadata_multiplier_and_zero_curve():
    from services.solstice_regime import regime_at_spot
    adj = [{"strike": 500, "type": "call", "gamma": 0.05, "oi": 100,
            "iv": 0.2, "T": 0.08, "multiplier": 100, "adjusted": True}]
    r = regime_at_spot(500.0, adj, "SPY")
    assert r["quarantined"] == 1 and r["sign"] == "UNKNOWN"
    zero = [{"strike": 500, "type": "call", "gamma": 0.0, "oi": 100,
             "iv": 0.2, "T": 0.08}]
    r2 = regime_at_spot(500.0, zero, "SPY")
    assert r2["sign"] == "ZERO" and r2["reason"] == "ZERO_CURVE"


def test_r4_16_timer_sign_interpretation():
    from services.solstice_research import q2_timer
    growing = q2_timer(5.0, 0.5)   # G>0, dG/dt>0 → moving away from zero
    shrinking = q2_timer(5.0, -0.5)  # G>0, dG/dt<0 → approaching zero
    assert growing["timer"] is not None and shrinking["timer"] is not None
    assert growing["interpretation"] != shrinking["interpretation"]
    assert "away" in growing["interpretation"] and "approach" in shrinking["interpretation"]
