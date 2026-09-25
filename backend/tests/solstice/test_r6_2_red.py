"""R6-2 red tests: wall-local comparison + window aggregation."""

import sys

sys.path.insert(0, "backend")

SPOT = 500.0


def _contracts():
    return [
        {"strike": 480, "type": "call", "gamma": 0.05, "oi": 100, "volume": 400,
         "delta": 0.5, "multiplier": 100.0, "expiry": "2030-01-15"},
        {"strike": 520, "type": "call", "gamma": 0.05, "oi": 100, "volume": 100,
         "delta": 0.1, "multiplier": 100.0, "expiry": "2030-01-15"},
    ]


def _walls():
    return [
        {"wall_id": "w_lo", "low": 478, "high": 482, "mid": 480,
         "members": [480], "gross": 1e6, "net": 1e6},
        {"wall_id": "w_hi", "low": 518, "high": 522, "mid": 520,
         "members": [520], "gross": 1e6, "net": 1e6},
    ]


def test_wall_metric_breakdown_is_local():
    from domain.exposure_metrics import wall_metric_breakdown
    out = wall_metric_breakdown(_walls(), _contracts(), SPOT)
    lo, hi = out["w_lo"], out["w_hi"]
    # Same raw gross, different delta/volume → different local values.
    assert lo["daddex_gross"] > hi["daddex_gross"]
    assert lo["volume_gross"] > hi["volume_gross"]
    assert lo["basis"] == "OI_DELTA_WEIGHTED"
    assert lo["n_contracts"] == 1 and lo["daddex_missing"] == 0


def test_wall_metric_breakdown_counts_missing():
    from domain.exposure_metrics import wall_metric_breakdown
    contracts = [_contracts()[0], dict(_contracts()[1], delta=None)]
    out = wall_metric_breakdown(_walls(), contracts, SPOT)
    assert out["w_hi"]["daddex_missing"] == 1
    assert out["w_hi"]["daddex_gross"] == 0.0


def test_window_aggregates_by_wall_membership():
    from services.solstice_enrichment import aggregate_window_by_wall
    rows = [
        {"osi": "A", "strike": 480, "window_daddex": 1000000.0},
        {"osi": "B", "strike": 520, "window_daddex": 1000.0},
        {"osi": "C", "strike": 999, "window_daddex": 5000000.0},
    ]
    out = aggregate_window_by_wall(_walls(), rows)
    assert out["w_lo"]["window_daddex"] == 1000000.0
    assert out["w_hi"]["window_daddex"] == 1000.0
    assert out["w_lo"]["coverage"] == {"member_strikes": 1, "active_strikes": 1}
    # Strike 999 belongs to no wall: scope total stays separately labeled.
    assert out["scope_total"] == 6001000.0
