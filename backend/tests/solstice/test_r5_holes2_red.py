"""R5 holes-batch-2 red tests: per-wall OI dates, scorer robustness."""

import sys

sys.path.insert(0, "backend")


def _contracts():
    return [
        {"strike": 500, "type": "call", "gamma": 0.05, "oi": 100,
         "oi_effective_date": "2030-01-01", "multiplier": 100.0},
        {"strike": 500, "type": "put", "gamma": 0.05, "oi": 100,
         "oi_effective_date": "2030-01-02", "multiplier": 100.0},
        {"strike": 510, "type": "call", "gamma": 0.05, "oi": 100,
         "multiplier": 100.0},  # no date
    ]


def test_oi_dates_flow_rows_to_walls():
    from services.gex_core import compute_gex_by_strike_vendor
    from services.wall_structure import discover_walls
    rows = compute_gex_by_strike_vendor(500.0, _contracts())
    by_strike = {r["strike"]: r for r in rows}
    assert by_strike[500.0]["oi_dates"] == ["2030-01-01", "2030-01-02"]
    assert by_strike[510.0].get("oi_dates") in (None, [])
    walls = discover_walls(rows, 505.0, pct_threshold=0.0)
    assert len(walls) == 1
    assert walls[0]["oi_effective_dates"] == ["2030-01-01", "2030-01-02"]


def test_oi_dates_absent_without_metadata():
    from services.wall_structure import discover_walls
    rows = [{"strike": 500.0, "gex": 1e6, "call_gex": 1e6, "put_gex": 0.0}]
    assert discover_walls(rows, 500.0)[0].get("oi_effective_dates") in (None, [])


def test_scorer_reads_canonical_and_snake_quality():
    sys.path.insert(0, ".")
    from scripts.solstice_comprehension import expected
    sc = {"nearest_below": {"low": 1, "high": 2}, "quality": {"setup_eligible": 0,
                                                              "reason_codes": ["STALE_ASK"]}}
    key = expected(sc)
    assert key["blocker"] == ["stale ask"]
    sc2 = {"nearest_below": {"low": 1, "high": 2}, "quality": {"setupEligible": False,
                                                               "reasonCodes": ["STALE_ASK"]}}
    assert expected(sc2)["blocker"] == ["stale ask"]
