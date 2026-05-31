"""Edge cases for heatseeker calc functions."""
import pytest

from services.heatseeker import calc_air_pockets, calc_flip_zones, calc_node_lifecycle


def test_flip_zones_empty_chain_returns_empty_zones():
    result = calc_flip_zones(spot=100, contracts=[], window_pct=0.05)
    assert isinstance(result, dict)
    zones = result.get("zones", [])
    assert zones == [] or zones is None


def test_flip_zones_zero_spot_does_not_crash():
    contracts = [{"strike": 100, "type": "call", "gamma": 0.01, "oi": 1000}]
    try:
        result = calc_flip_zones(spot=0, contracts=contracts, window_pct=0.05)
        assert isinstance(result, dict)
    except (ValueError, ZeroDivisionError):
        pass  # Acceptable: controlled exception


def test_flip_zones_missing_gamma_defaults():
    """Contracts without gamma field should not crash."""
    contracts = [{"strike": 100, "type": "call", "oi": 1000}]
    result = calc_flip_zones(spot=100, contracts=contracts, window_pct=0.05)
    assert isinstance(result, dict)


def test_node_lifecycle_with_no_history_uses_chain_only():
    contracts = [
        {"strike": 100, "type": "call", "gamma": 0.01, "oi": 5000},
        {"strike": 105, "type": "put", "gamma": 0.008, "oi": 4000},
    ]
    result = calc_node_lifecycle(spot=102, contracts=contracts, history=[])
    assert isinstance(result, dict)
    nodes = result.get("nodes", [])
    for n in nodes:
        assert n.get("classification") in {"Fresh", "Tested", "Delivered", "Decaying", "real", "hedge", "unknown", None}


def test_node_lifecycle_empty_contracts():
    result = calc_node_lifecycle(spot=100, contracts=[], history=[])
    assert isinstance(result, dict)


def test_air_pockets_empty_chain():
    result = calc_air_pockets(spot=100, contracts=[], min_gap_pct=0.02)
    assert isinstance(result, dict)


def test_air_pockets_single_contract():
    """Single contract should not crash."""
    contracts = [{"strike": 100, "type": "call", "gamma": 0.01, "oi": 1000}]
    result = calc_air_pockets(spot=100, contracts=contracts, min_gap_pct=0.02)
    assert isinstance(result, dict)
