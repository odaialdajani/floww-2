"""Reconciliation: charm uses the existing dollar/year convention, never raw Greeks."""
import json

import pytest

from bs_greeks import bs_charm, dollar_charm_per_contract
from services.gex_core import compute_charm_grid_local


def row(**kw):
    return dict(strike=500, expiry="2030-01-18", type="call", oi=100, gamma=.02, **kw)


def test_vendor_charm_has_same_units_and_wire_keys_as_other_surfaces():
    result = compute_charm_grid_local(500, [row(charm=.01, charm_unit="per_year")])
    wire = json.loads(json.dumps(result))
    assert wire["grid"]["2030-01-18"]["500"] == pytest.approx(.01 * 100 * 100 * 500 * .01)


def test_vendor_charm_without_time_unit_is_not_a_dollar_reading():
    result = compute_charm_grid_local(500, [row(charm=.01)])
    assert result["status"] == "unavailable"


def test_local_charm_remains_available_on_vendor_gamma_path():
    import server
    contract = row(iv=.2, T=.1)
    _, _, _, grid = server._display_surfaces(500, [contract], "SPY", False)
    expected = dollar_charm_per_contract(bs_charm(500, 500, .1, .2, q=.013), 100, 500)
    assert grid["charm_grid"]["2030-01-18"]["500"] == pytest.approx(expected)
    assert "local-bs" in grid["charm_meta"]["model"]


def test_missing_member_prevents_partial_sum_looking_complete():
    result = compute_charm_grid_local(500, [row(charm=.01, charm_unit="per_year"), row()])
    assert "500" not in result["grid"].get("2030-01-18", {})
    assert result["status"] != "ok"


def test_charm_metadata_survives_snapshot_serialization():
    from services.heatmap_history import _full_grids
    metadata = {"status": "partial", "model": "local-bs-charm.v1"}
    saved = _full_grids({"grid": {"charm_grid": {"2030-01-18": {"500": 3}}, "charm_meta": metadata}})
    assert saved["grid"]["charm_meta"] == metadata


@pytest.mark.parametrize("flag", ["adjusted", "nonstandard"])
def test_charm_quarantines_unsupported_contracts(flag):
    result = compute_charm_grid_local(500, [row(charm=.01, charm_unit="per_year", **{flag: True})])
    assert result["grid"] == {}
    assert result["quarantined"] == 1


def test_charm_respects_contract_size_and_open_interest_alias():
    contract = row(charm=.01, charm_unit="per_year", multiplier=10)
    contract["open_interest"] = contract.pop("oi")
    assert compute_charm_grid_local(500, [contract])["grid"]["2030-01-18"]["500"] == 50
