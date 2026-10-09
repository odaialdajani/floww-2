"""ADJ is exactly RAW x |delta| per contract (155edea pin, rebuilt for the candidate).

Covers the candidate's `compute_gex_grid_delta_weighted` (gex_core.py):
per-cell adjusted exposure equals the raw cell times |delta|, and every
non-participating contract is classified honestly (missing vs invalid vs
rejected type vs invalid multiplier) — never silently zeroed, defaulted,
or overwritten. A call and a put at one strike net instead of overwriting.
"""

from __future__ import annotations

from services.gex_core import compute_gex_grid_delta_weighted

EXPIRY = "2026-10-09"
SPOT = 500.0


def _c(strike, kind="call", oi=100, gamma=0.02, delta=0.5, **extra):
    c = {"strike": strike, "expiry": EXPIRY, "type": kind, "oi": oi,
         "gamma": gamma, "delta": delta}
    c.update(extra)
    return c


def _raw_cell(sign, gamma, mult, spot, oi):
    return sign * gamma * mult * spot * spot * 0.01 * oi


def test_adj_equals_raw_times_abs_delta_per_contract():
    # Absent multiplier on a standard contract yields the documented 100 default.
    got = compute_gex_grid_delta_weighted(SPOT, [_c(500, "call", oi=100, gamma=0.02, delta=0.5)])
    raw = _raw_cell(+1, 0.02, 100, SPOT, 100)
    assert got["grid"][EXPIRY]["500"] == raw * 0.5 == 250000.0
    assert got["exposure_basis"] == "OI_DELTA_WEIGHTED"
    assert got["status"] == "ok"


def test_missing_delta_skipped_and_counted_not_zeroed():
    got = compute_gex_grid_delta_weighted(SPOT, [_c(500, "call", delta=None)])
    assert got["grid"].get(EXPIRY, {}).get("500") is None
    assert got["missing_delta"] == 1
    assert got["invalid_delta"] == 0


def test_bool_delta_is_invalid_not_one():
    got = compute_gex_grid_delta_weighted(SPOT, [_c(500, "call", delta=True)])
    assert got["grid"].get(EXPIRY, {}).get("500") is None
    assert got["invalid_delta"] == 1
    assert got["missing_delta"] == 0


def test_unknown_option_type_rejected_never_default_put():
    got = compute_gex_grid_delta_weighted(SPOT, [_c(500, "unknown")])
    assert got["grid"].get(EXPIRY, {}).get("500") is None
    assert got["invalid_type"] == 1


def test_explicit_zero_multiplier_invalid_never_defaulted():
    got = compute_gex_grid_delta_weighted(SPOT, [_c(500, "call", multiplier=0)])
    assert got["grid"].get(EXPIRY, {}).get("500") is None
    assert got["invalid_mult"] == 1


def test_call_and_put_net_at_same_strike_no_overwrite():
    contracts = [_c(500, "call", oi=100, gamma=0.02, delta=0.5),
                 _c(500, "put", oi=60, gamma=0.02, delta=0.5)]
    got = compute_gex_grid_delta_weighted(SPOT, contracts)
    unit = _raw_cell(1, 0.02, 100, SPOT, 1) * 0.5
    assert got["grid"][EXPIRY]["500"] == (100 - 60) * unit == 100000.0
