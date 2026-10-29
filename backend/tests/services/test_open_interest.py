import copy

import pytest

from services.open_interest import build_open_interest


def contract(kind="call", oi=10, **extras):
    return {"type": kind, "oi": oi, "strike": 500, "expiry": "2026-10-30", **extras}


def test_counts_are_unsigned_and_independent_of_greeks_spot_and_multiplier():
    out = build_open_interest([contract(oi=12, gamma=None, multiplier=50), contract("put", 7, delta=None)])
    assert out["units"] == "contracts"
    assert out["cells"]["2026-10-30"]["500"]["total"] == 19
    assert out["status"] == "ok"


def test_observed_zero_is_available_and_missing_leg_is_not_zero():
    cell = build_open_interest([contract(oi=0)])["cells"]["2026-10-30"]["500"]
    assert cell["total"] == cell["call"] == 0
    assert cell["put"] is None


@pytest.mark.parametrize("value,kind", [(None, "missing"), (True, "invalid"), (-1, "invalid"),
    (float("inf"), "invalid"), (float("nan"), "invalid"), (1.5, "invalid")])
def test_incomplete_cell_withholds_total(value, kind):
    out = build_open_interest([contract(), contract("put", value)])
    cell = out["cells"]["2026-10-30"]["500"]
    assert cell["total"] is None and cell[kind] == 1
    assert out["status"] == "partial"


def test_own_axes_include_strikes_without_gamma_and_duplicate_side_is_ambiguous():
    rows = [contract(), contract(oi=3), contract("put", 4, strike=501)]
    out = build_open_interest(rows)
    assert out["strikes"] == [500, 501]
    assert out["cells"]["2026-10-30"]["500"]["total"] is None
    assert out["cells"]["2026-10-30"]["501"]["total"] == 4


def test_snapshot_identity_binds_counts_and_recording_preserves_surface():
    from services.heatmap_history import _full_grids
    from services.heatmap_snapshot import content_digest
    payload = {"grid": {"oi_surface": build_open_interest([contract()])}}
    changed = copy.deepcopy(payload)
    changed["grid"]["oi_surface"]["cells"]["2026-10-30"]["500"]["total"] = 11
    assert content_digest(payload) != content_digest(changed)
    assert _full_grids(payload)["grid"]["oi_surface"] == payload["grid"]["oi_surface"]


def test_aggregate_overflow_is_withheld_not_declared_complete():
    out = build_open_interest([contract(oi=2**53-1), contract("put", 1)])
    cell = out["cells"]["2026-10-30"]["500"]
    assert cell["total"] is None and cell["invalid"] == 1
    assert out["status"] == "partial"
