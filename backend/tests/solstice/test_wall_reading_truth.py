"""Wall-local coverage must distinguish reported zero from absent data."""
import math

import pytest

from domain.exposure_metrics import wall_metric_breakdown

WALL = {"wall_id": "selected", "members": [100]}
BASE = {"strike": 100, "type": "call", "gamma": .01, "oi": 10,
        "delta": .5, "volume": 0, "expiry": "2030-01-15", "multiplier": 100}

def reading(*contracts):
    return wall_metric_breakdown([WALL], list(contracts), 100)["selected"]

def test_reported_zero_volume_has_coverage_but_missing_volume_does_not():
    zero, absent = reading(BASE), reading(dict(BASE, volume=None))
    assert zero["volume_gross"] == absent["volume_gross"] == 0
    assert zero["volume_n"] == absent["volume_n"] == 0
    assert zero["volume_usable"] == 1 and zero["volume_missing"] == 0
    assert absent["volume_usable"] == 0 and absent["volume_missing"] == 1

@pytest.mark.parametrize("oi", [0, None, "bad", -1])
def test_session_volume_does_not_depend_on_open_interest(oi):
    row = reading(dict(BASE, oi=oi, volume=5, delta=None))
    # .01 gamma *100 shares *100**2 spot *.01 move *5 contracts
    assert row["volume_gross"] == row["volume_net"] == 500
    assert row["volume_n"] == row["volume_usable"] == 1

@pytest.mark.parametrize("volume", [-1, "bad", math.nan, math.inf, False, True])
def test_invalid_volume_does_not_become_measured_zero(volume):
    row = reading(dict(BASE, volume=volume))
    assert row["volume_usable"] == row["volume_missing"] == 0
    assert row["volume_invalid"] == 1
    assert row["daddex_usable"] == 1 and row["daddex_gross"] == 500

def test_partial_counts_and_member_scope_are_preserved():
    row = reading(BASE, dict(BASE, type="put", volume=2, delta=None),
                  dict(BASE, volume=None), dict(BASE, volume=-1),
                  dict(BASE, strike=101, volume=9999))
    assert row["n_contracts"] == 4
    assert row["volume_usable"] == 2 and row["volume_n"] == 1
    assert row["volume_missing"] == row["volume_invalid"] == 1
    assert row["volume_gross"] == 200 and row["volume_net"] == -200
    assert row["daddex_missing"] == 1
    assert row["daddex_usable"] == 3 and row["daddex_gross"] == 1500

@pytest.mark.parametrize("change", [{"gamma": None}, {"type": "unknown"}, {"adjusted": True, "multiplier": None}])
def test_volume_zero_requires_valid_calculation_inputs(change):
    row = reading(dict(BASE, **change))
    assert row["volume_usable"] == 0 and row["volume_invalid"] == 1

def test_valid_zero_delta_remains_a_measured_zero():
    row = reading(dict(BASE, delta=0, volume=0))
    assert row["daddex_usable"] == 1 and row["daddex_gross"] == 0
    assert row["volume_usable"] == 1 and row["volume_gross"] == 0

def test_display_keeps_contract_gross_even_when_same_cell_nets_to_zero():
    from server import _display_surfaces
    from services.gex_core import compute_vex_grid_local
    calls = dict(BASE, iv=.2, T=.1)
    contracts = [calls, dict(calls, type="put")]
    expected = compute_vex_grid_local(100, contracts, "SPY")
    assert expected["grid"]["2030-01-15"]["100"] == 0
    assert expected["strike_gross"][0]["vex_gross"] > 0
    *_, grid = _display_surfaces(100, contracts, "SPY", False)
    assert grid["vex_strike_gross"] == expected["strike_gross"]


def test_live_gross_and_coverage_survive_saved_snapshot_reopen(tmp_path):
    import duckdb

    from server import _display_surfaces
    from services.heatmap_history import record_snapshot, replay_snapshot
    contracts = [dict(BASE, iv=.2, T=.1, osi="C"), dict(BASE, iv=.2, T=.1, type="put", osi="P", volume=None)]
    _, _, strikes, grid = _display_surfaces(100, contracts, "SPY", False)
    metrics = {"walls": [WALL], "wall_metrics": wall_metric_breakdown([WALL], contracts, 100)}
    payload = {"ticker":"SPY", "spot":100, "asof":"2030-01-02T14:00:00+00:00",
               "source_received_at":"2030-01-02T14:00:01+00:00", "data_source":"development_fixture",
               "exposure_basis":"OI", "formula_version":"gex.v2", "expiries_used":["2030-01-15"],
               "strikes":strikes, "grid":grid, "contracts":contracts, "metrics":metrics}
    dbfile=str(tmp_path / "wall.duckdb")
    with duckdb.connect(dbfile) as conn:
        sid=record_snapshot(conn, payload, "wall-truth-development")
        assert sid
    with duckdb.connect(dbfile, read_only=True) as reopened:
        saved=replay_snapshot(reopened, sid)
    assert saved["grids"]["grid"]["vex_strike_gross"] == grid["vex_strike_gross"]
    assert saved["grids"]["grid"]["vex_meta"] == grid["vex_meta"]
    assert saved["metrics_full"]["wall_metrics"] == metrics["wall_metrics"]


@pytest.mark.parametrize("change", [{"gamma":False},{"multiplier":True},{"delta":False},{"oi":True}])
def test_boolean_inputs_do_not_prove_valid_exposure(change):
    row=reading(dict(BASE, **change))
    assert row["daddex_usable"] == 0
    if "gamma" in change or "multiplier" in change:
        assert row["volume_usable"] == 0
    else:
        assert row["volume_usable"] == 1


def test_overflowed_totals_stay_unavailable_and_json_safe():
    import json
    large=dict(BASE, gamma=1e150, volume=1e150, oi=1e150, delta=1)
    row=reading(*[large]*20000)
    assert row["volume_gross"] is None and row["daddex_gross"] is None
    json.dumps(row, allow_nan=False)
