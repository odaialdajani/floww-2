"""Charm vec wiring: numba bs_charm_vec must match scalar bs_charm (×365 scale).

RED on main: test_wiring_uses_vec (vec unused pre-swap). Equivalence +
degenerate tests pin behavior so the swap is provably a no-op numerically.
"""
import math

import numpy as np
import pytest

from bs_greeks import bs_charm


def _rows(rng, n):
    rows = []
    for _ in range(n):
        r = rng.random()
        if r < 0.08:
            rows.append({"strike": 100.0, "T": 0.0, "iv": 0.0,
                         "type": "call", "oi": 100.0})
        elif r < 0.12:
            rows.append({"strike": -5.0, "T": -0.1, "iv": float("nan"),
                         "type": "put", "oi": 50.0})
        else:
            rows.append({"strike": float(rng.uniform(50, 500)),
                         "T": float(rng.uniform(0.002, 2.0)),
                         "iv": float(rng.uniform(0.05, 1.2)),
                         "type": "call" if rng.random() < 0.5 else "put",
                         "oi": 100.0})
    return rows


def _vec_values(spot, rows, q=0.0):
    from services.numba_greeks import bs_charm_vec
    K = np.array([r["strike"] for r in rows], dtype=np.float64)
    T = np.array([r["T"] for r in rows], dtype=np.float64)
    V = np.array([r["iv"] for r in rows], dtype=np.float64)
    out = np.zeros(len(rows))
    for kind_int, want in ((0, "call"), (1, "put")):
        idx = [i for i, r in enumerate(rows) if r["type"] == want]
        if not idx:
            continue
        ii = np.array(idx)
        out[ii] = bs_charm_vec(spot, K[ii], T[ii], V[ii], q,
                               kind_int) * 365.0
    return out


def test_equivalence_random():
    rng = np.random.default_rng(7)
    spot, q = 100.0, 0.013
    rows = _rows(rng, 300)
    expect = [bs_charm(spot, r["strike"], r["T"], r["iv"], q=q, kind=r["type"])
              for r in rows]
    got = _vec_values(spot, rows, q)
    for e, g in zip(expect, got, strict=True):
        assert abs(e - g) <= 1e-9 * max(1.0, abs(e)), (e, g)


def test_degenerate_rows_zero_both_paths():
    rows = [{"strike": 0.0, "T": 0.25, "iv": 0.25, "type": "call", "oi": 1.0},
            {"strike": 100.0, "T": 0.0, "iv": 0.25, "type": "call", "oi": 1.0},
            {"strike": 100.0, "T": 0.25, "iv": 0.0, "type": "put", "oi": 1.0}]
    got = _vec_values(100.0, rows)
    assert list(got) == [0.0, 0.0, 0.0]
    for r in rows:
        assert bs_charm(100.0, r["strike"], r["T"], r["iv"], kind=r["type"]) == 0.0


def test_wiring_uses_vec(monkeypatch):
    """calc_charm_integral must route through bs_charm_vec.

    Pre-swap the name doesn't exist on the module (AttributeError = RED).
    Post-swap the spy records real calls (GREEN only when actually wired).
    """
    import advanced_analytics as aa_mod

    real = aa_mod.bs_charm_vec  # AttributeError pre-swap
    calls = {}

    def spy(*a, **k):
        calls["n"] = calls.get("n", 0) + 1
        return real(*a, **k)

    monkeypatch.setattr(aa_mod, "bs_charm_vec", spy)
    contracts = [{"strike": 100.0, "expiry": "2026-09-18", "T": 0.25,
                  "type": "call", "oi": 100.0, "iv": 0.25, "volume": 10.0}]
    aa_mod.calc_charm_integral(100.0, contracts, "SPY")
    assert calls.get("n", 0) >= 1
