"""Gamma/vanna vec wiring: numba bs_gamma_vec/bs_vanna_vec must match scalars.

RED on main: test_wiring_uses_vecs (vec names unused pre-swap).
Equivalence + degenerate tests pin behavior so the swap is provably
a no-op numerically.
"""
import math

import numpy as np
import pytest

from bs_greeks import bs_gamma, bs_vanna


def _rows(rng, n):
    rows = []
    for _ in range(n):
        r = rng.random()
        if r < 0.08:
            rows.append({"strike": 100.0, "T": 0.0, "iv": 0.0, "oi": 100.0})
        elif r < 0.12:
            rows.append({"strike": -5.0, "T": -0.1, "iv": float("nan"),
                         "oi": 50.0})
        else:
            rows.append({"strike": float(rng.uniform(50, 500)),
                         "T": float(rng.uniform(0.002, 2.0)),
                         "iv": float(rng.uniform(0.05, 1.2)),
                         "oi": 100.0})
    return rows


def _vec_values(spot, rows, q=0.0):
    from services.numba_greeks import bs_gamma_vec, bs_vanna_vec
    K = np.array([r["strike"] for r in rows], dtype=np.float64)
    T = np.array([r["T"] for r in rows], dtype=np.float64)
    V = np.array([r["iv"] for r in rows], dtype=np.float64)
    g = bs_gamma_vec(spot, K, T, V, q)
    v = bs_vanna_vec(spot, K, T, V, q)
    return g, v


def test_equivalence_random():
    rng = np.random.default_rng(11)
    spot, q = 100.0, 0.013
    rows = _rows(rng, 300)
    for r in rows:
        e_g = bs_gamma(spot, r["strike"], r["T"], r["iv"], q=q)
        e_v = bs_vanna(spot, r["strike"], r["T"], r["iv"], q=q)
        K = np.array([r["strike"]])
        T = np.array([r["T"]])
        V = np.array([r["iv"]])
        from services.numba_greeks import bs_gamma_vec, bs_vanna_vec
        g = float(bs_gamma_vec(spot, K, T, V, q)[0])
        v = float(bs_vanna_vec(spot, K, T, V, q)[0])
        assert abs(e_g - g) <= 1e-9 * max(1.0, abs(e_g)), (e_g, g)
        assert abs(e_v - v) <= 1e-9 * max(1.0, abs(e_v)), (e_v, v)


def test_degenerate_rows_zero_both_paths():
    rows = [{"strike": 0.0, "T": 0.25, "iv": 0.25, "oi": 1.0},
            {"strike": 100.0, "T": 0.0, "iv": 0.25, "oi": 1.0},
            {"strike": 100.0, "T": 0.25, "iv": 0.0, "oi": 1.0}]
    g, v = _vec_values(100.0, rows)
    assert list(g) == [0.0, 0.0, 0.0]
    assert list(v) == [0.0, 0.0, 0.0]
    for r in rows:
        assert bs_gamma(100.0, r["strike"], r["T"], r["iv"]) == 0.0
        assert bs_vanna(100.0, r["strike"], r["T"], r["iv"]) == 0.0


def test_wiring_uses_vecs(monkeypatch):
    """calc_hedge_impulse_curve must route through bs_gamma_vec/bs_vanna_vec.

    Pre-swap the names don't exist on the module (AttributeError = RED).
    Post-swap the spies record real calls (GREEN only when actually wired).
    """
    import advanced_analytics as aa_mod

    real_g = aa_mod.bs_gamma_vec  # AttributeError pre-swap
    real_v = aa_mod.bs_vanna_vec  # AttributeError pre-swap
    calls = {}

    def spy_g(*a, **k):
        calls["g"] = calls.get("g", 0) + 1
        return real_g(*a, **k)

    def spy_v(*a, **k):
        calls["v"] = calls.get("v", 0) + 1
        return real_v(*a, **k)

    monkeypatch.setattr(aa_mod, "bs_gamma_vec", spy_g)
    monkeypatch.setattr(aa_mod, "bs_vanna_vec", spy_v)
    contracts = [{"strike": 100.0, "T": 0.25, "iv": 0.25, "oi": 100.0,
                  "type": "call"}]
    aa_mod.calc_hedge_impulse_curve(100.0, contracts, "SPY")
    assert calls.get("g", 0) >= 1
    assert calls.get("v", 0) >= 1
