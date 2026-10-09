"""c3bdf4c: every greek returns a plain float, not a numpy scalar.

scipy's norm.pdf/cdf return np.float64, which leaked straight through the
bs_* helpers. Downstream JSON encoding, strict type checks, and exact-equality
caches must never see numpy scalars from this module. Values are unchanged —
only the container type is normalized via float().
"""

import bs_greeks

CASES = dict(S=500.0, K=500.0, T=0.1, sigma=0.2)


def _calls():
    c = CASES
    return {
        "bs_gamma": bs_greeks.bs_gamma(c["S"], c["K"], c["T"], c["sigma"]),
        "bs_delta_call": bs_greeks.bs_delta(c["S"], c["K"], c["T"], c["sigma"], kind="call"),
        "bs_delta_put": bs_greeks.bs_delta(c["S"], c["K"], c["T"], c["sigma"], kind="put"),
        "bs_vanna": bs_greeks.bs_vanna(c["S"], c["K"], c["T"], c["sigma"]),
        "bs_charm_call": bs_greeks.bs_charm(c["S"], c["K"], c["T"], c["sigma"], kind="call"),
        "bs_charm_put": bs_greeks.bs_charm(c["S"], c["K"], c["T"], c["sigma"], kind="put"),
        "bs_vomma": bs_greeks.bs_vomma(c["S"], c["K"], c["T"], c["sigma"]),
        "bs_zomma": bs_greeks.bs_zomma(c["S"], c["K"], c["T"], c["sigma"]),
        "bs_vega": bs_greeks.bs_vega(c["S"], c["K"], c["T"], c["sigma"]),
        "bs_call_price": bs_greeks.bs_call_price(c["S"], c["K"], c["T"], c["sigma"]),
        "bs_put_price": bs_greeks.bs_put_price(c["S"], c["K"], c["T"], c["sigma"]),
    }


def test_every_greek_returns_plain_float():
    for name, value in _calls().items():
        assert type(value) is float, f"{name} returned {type(value).__name__}: {value!r}"


def test_guard_clauses_still_return_plain_zero():
    assert type(bs_greeks.bs_gamma(0, 500, 0.1, 0.2)) is float
    assert type(bs_greeks.bs_delta(500, 500, 0, 0.2)) is float
    assert type(bs_greeks.bs_vega(500, 500, 0.1, 0)) is float
    assert type(bs_greeks.bs_charm(-1, 500, 0.1, 0.2)) is float
