"""S1+S2 canonical measurement boundary (Spark).

S1: explicit invalid multipliers must never fall back to 100; booleans are
never measurements; alias disagreement is surfaced, not first-wins.
S2: session_delta_volume_gamma_v1 is the DISTINCT fourth activity formula
(Σ c u V |δ|), backward compatible with volume_gamma_v1 (Σ c u V).

Every test here fails on the pre-fix kernel (R10-02/R10-04/R10-01) and
passes after. Protected Tide paths do not import these computeds
(routes/flowseeker.py uses conviction_rank only), so this direct strict
repair is Solstice-owned.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.exposure_metrics import (  # noqa: E402
    METRIC_REGISTRY,
    abs_delta,
    compute_delta_weighted_oi,
    compute_raw_oi,
    compute_session_delta_volume_gamma,
    compute_volume_gamma,
    decimal_strike,
    dollar_gamma_unit,
    is_valid_measurement,
    resolve_multiplier,
)

SPOT = 100.0


def _c(**kw):
    base = {
        "type": "call", "strike": 100, "gamma": 0.01, "oi": 1000,
        "delta": 0.5, "volume": 100, "multiplier": 100, "expiry": "2030-01-15",
    }
    base.update(kw)
    return base


# ---- S1: multiplier provenance ----

def test_explicit_invalid_multiplier_rejected_not_defaulted():
    for bad in (0, -100, float("nan"), float("inf"), True, "xyz"):
        r = compute_raw_oi([_c(multiplier=bad)], SPOT)
        assert (r.usable, r.invalid, r.gross) == (0, 1, 0.0), bad


def test_absent_multiplier_uses_documented_default():
    c = _c()
    del c["multiplier"]
    value, reason = resolve_multiplier(c)
    assert (value, reason) == (100.0, "DEFAULT_STANDARD")
    assert compute_raw_oi([c], SPOT).gross == 100_000.0


def test_explicit_none_multiplier_is_unknown_not_default():
    value, reason = resolve_multiplier(_c(multiplier=None))
    assert (value, reason) == (None, "MULTIPLIER_UNKNOWN")
    r = compute_raw_oi([_c(multiplier=None)], SPOT)
    assert (r.usable, r.invalid) == (0, 1)


def test_alias_agreement_usable_disagreement_surfaced():
    ok = _c(multiplier=100, contractMultiplier=100)
    assert resolve_multiplier(ok) == (100.0, None)
    assert compute_raw_oi([ok], SPOT).usable == 1
    bad = _c(multiplier=100, contractMultiplier=200)
    assert resolve_multiplier(bad) == (None, "MULTIPLIER_ALIAS_DISAGREE")
    assert compute_raw_oi([bad], SPOT).invalid == 1


def test_adjusted_contract_quarantined_despite_default():
    c = _c(adjusted=True)
    del c["multiplier"]
    assert resolve_multiplier(c)[1] == "CONTRACT_QUARANTINED"
    assert compute_raw_oi([c], SPOT).invalid == 1


# ---- S1: boolean / nonfinite / sign rejection ----

def test_booleans_are_never_measurements():
    assert is_valid_measurement(True) is None
    assert is_valid_measurement(False) is None
    assert is_valid_measurement(float("nan")) is None
    assert is_valid_measurement(float("inf")) is None
    assert compute_raw_oi([_c(gamma=True)], SPOT).invalid == 1
    assert compute_raw_oi([_c(oi=True)], SPOT).missing_oi == 1
    assert compute_delta_weighted_oi([_c(delta=True)], SPOT).missing_delta == 1
    assert compute_volume_gamma([_c(volume=True)], SPOT).missing_oi == 1
    assert dollar_gamma_unit(0.01, 100, True) is None
    assert dollar_gamma_unit(0.01, 100, 0.0) is None
    v, reason = abs_delta(True)
    assert (v, reason) == (None, "DELTA_INVALID")


def test_measured_zero_vs_missing_vs_negative():
    assert compute_raw_oi([_c(oi=0)], SPOT).usable == 0  # measured zero: skipped, not invalid
    assert compute_raw_oi([_c(oi=0)], SPOT).invalid == 0
    assert compute_raw_oi([_c(oi=None)], SPOT).missing_oi == 1
    assert compute_raw_oi([_c(oi=-5)], SPOT).invalid == 1
    assert compute_raw_oi([_c(gamma=-0.01)], SPOT).invalid == 1


def test_exact_strike_identity_and_delta_bounds():
    assert decimal_strike("100.25") == Decimal("100.25")
    assert decimal_strike(100.75) == Decimal("100.75")
    assert decimal_strike(True) is None
    v, r = abs_delta(1.0000000001)
    assert (v, r) == (1.0, "DELTA_ROUNDED")
    assert abs_delta(1.5) == (None, "DELTA_OUT_OF_RANGE")


# ---- S2: distinct activity family ----

def test_session_volume_is_not_session_volume_times_delta():
    one = _c()
    assert compute_volume_gamma([one], SPOT).net == 10_000.0  # Σ c u V
    assert compute_session_delta_volume_gamma([one], SPOT).net == 5_000.0  # Σ c u V |δ|


def test_equal_raw_cancellation_can_produce_nonzero_delta_net():
    call = _c(type="call", delta=0.8)
    put = _c(type="put", delta=-0.2)
    raw = compute_raw_oi([call, put], SPOT)
    dw = compute_delta_weighted_oi([call, put], SPOT)
    assert raw.net == 0.0 and raw.gross == 200_000.0
    assert dw.net == 60_000.0  # 80k - 20k: asymmetry survives cancellation
    assert abs(dw.net) <= dw.gross <= raw.gross


def test_missing_delta_excluded_and_reported_not_zeroed():
    ok = _c()
    nod = _c()
    del nod["delta"]
    r = compute_session_delta_volume_gamma([ok, nod], SPOT)
    assert (r.usable, r.missing_delta, r.gross) == (1, 1, 5_000.0)


def test_registry_registers_distinct_fourth_metric():
    entry = METRIC_REGISTRY["session_delta_volume_gamma_v1"]
    assert entry["formula"] == "Σ c u V |δ|"
    assert entry["basis"] == "VOLUME_DELTA_WEIGHTED"
    assert METRIC_REGISTRY["volume_gamma_v1"]["formula"] == "Σ c u V"
