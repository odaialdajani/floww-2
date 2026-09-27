"""Recovered pure Greek surface contracts; no platform-specific binary required."""

import numpy as np
import pytest

from services.numba_greeks import compute_all_greeks

GREEKS = {"delta", "gamma", "theta", "vega", "vanna", "charm", "vomma", "zomma"}


@pytest.mark.parametrize("size", [0, 1, 1000])
def test_surface_shape_finite_values_and_signs(size):
    rng = np.random.default_rng(42)
    strikes = rng.uniform(50, 150, size)
    times = rng.uniform(0.001, 5, size)
    ivs = rng.uniform(0.05, 1, size)
    kinds = rng.integers(0, 2, size, dtype=np.int32)
    result = compute_all_greeks(100.0, strikes, times, ivs, kinds)
    assert set(result) == GREEKS
    for values in result.values():
        assert values.shape == (size,)
        assert values.dtype == np.float64
        assert np.isfinite(values).all()
    assert ((result["delta"][kinds == 0] >= 0) & (result["delta"][kinds == 0] <= 1)).all()
    assert ((result["delta"][kinds == 1] >= -1) & (result["delta"][kinds == 1] <= 0)).all()
    assert (result["gamma"] >= 0).all()
    assert (result["vega"] >= 0).all()


@pytest.mark.parametrize("field", ["spot", "strike", "expiry", "iv"])
@pytest.mark.parametrize("invalid", [0.0, -1.0])
def test_nonpositive_inputs_are_zero_without_changing_valid_neighbors(field, invalid):
    spot = 100.0
    strikes = np.array([95.0, 100.0, 105.0])
    times = np.full(3, 0.25)
    ivs = np.full(3, 0.2)
    kinds = np.array([0, 1, 0])
    expected = compute_all_greeks(spot, strikes, times, ivs, kinds)
    if field == "spot":
        spot = invalid
    else:
        {"strike": strikes, "expiry": times, "iv": ivs}[field][1] = invalid
    actual = compute_all_greeks(spot, strikes, times, ivs, kinds)
    for name in GREEKS:
        if field == "spot":
            np.testing.assert_array_equal(actual[name], np.zeros(3))
        else:
            assert actual[name][1] == 0.0
            np.testing.assert_array_equal(actual[name][[0, 2]], expected[name][[0, 2]])


def test_call_put_delta_parity_with_dividends_and_shared_gamma_vega():
    strikes = np.array([80.0, 100.0, 120.0])
    times = np.array([0.01, 0.25, 2.0])
    ivs = np.array([0.1, 0.2, 0.4])
    calls = compute_all_greeks(100.0, strikes, times, ivs, np.zeros(3), r=0.05, q=0.02)
    puts = compute_all_greeks(100.0, strikes, times, ivs, np.ones(3), r=0.05, q=0.02)
    np.testing.assert_allclose(calls["delta"] - puts["delta"], np.exp(-0.02 * times), atol=1e-12)
    for name in ("gamma", "vega", "vanna", "vomma", "zomma"):
        np.testing.assert_array_equal(calls[name], puts[name])


def test_noncontiguous_inputs_match_contiguous_inputs_without_mutation():
    source = np.linspace(80.0, 120.0, 12)
    strikes = source[::2]
    before = source.copy()
    times = np.full(12, 0.25)[::2]
    ivs = np.full(12, 0.2)[::2]
    kinds = np.array([0, 1, 1, 0, 0, 1])
    actual = compute_all_greeks(100.0, strikes, times, ivs, kinds)
    expected = compute_all_greeks(100.0, strikes.copy(), times.copy(), ivs.copy(), kinds.copy())
    for name in GREEKS:
        np.testing.assert_array_equal(actual[name], expected[name])
    np.testing.assert_array_equal(source, before)
