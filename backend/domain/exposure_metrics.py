"""
backend/domain/exposure_metrics.py — Solstice canonical exposure registry (T01/T27).

Versioned metric definitions for the 2D grid. All metrics share:
  u_i = gamma_i * m_i * S^2 * 0.01   (dollar gamma per 1% move, per contract)

Metrics (formula_version gex.v2):
  gex_gross_v1  = Σ u_i N_i                    gross OI gamma (wall discovery)
  gex_net_v1    = Σ c_i u_i N_i                conventional net (call-minus-put)
  dadgex_gross_v1 = Σ u_i N_i |δ_i|            delta-weighted gross
  dadgex_net_v1   = Σ c_i u_i N_i |δ_i|        delta-weighted net
  volume_gamma_v1 = Σ c_i u_i V_i              session activity proxy
  session_delta_volume_gamma_v1 = Σ c_i u_i V_i |δ_i|   session activity × delta
  window_dadgex_v1 = Σ c_i u_i |δ_i| ΔV_i(W)   window activity proxy

Invariants (same valid contract set, nonneg gamma/OI, |δ|≤1):
  |raw net| ≤ raw gross ; |delta net| ≤ delta gross ≤ raw gross.
  No general bound |delta net| ≤ |raw net| (weighting changes cancellation).

Missing delta → contribution UNAVAILABLE (not zero). Missing OI/volume →
separate unknown states; never silent substitution. Signed put delta must go
through abs() before the conventional put sign — naive double-signing makes
every put positive (+1M trap in T27 fixtures).

Units: USD per 1% spot move. Display scale S²; frozen ML S¹ path untouched.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

FORMULA_VERSION = "gex.v2"
SCHEMA_VERSION = "2"

CALL_SIGN = 1.0
PUT_SIGN = -1.0

# Contract-multiplier alias keys. All three name the same quantity; when more
# than one is present they must agree (see resolve_multiplier).
MULTIPLIER_KEYS = ("multiplier", "contractMultiplier", "m")

# Documented standard-contract default. Applied ONLY when no multiplier key
# carries a value (all keys absent or explicitly None) on a contract that is
# not flagged adjusted/nonstandard. R10-02: an EXPLICIT invalid value
# (0, negative, NaN, bool, unparseable) must never fall back to this — the
# contract is rejected with MULTIPLIER_INVALID instead. A present-but-None
# value is unknown (not absent): the contract is unavailable, never defaulted.
STANDARD_MULTIPLIER = 100.0

REASON_MULTIPLIER_INVALID = "MULTIPLIER_INVALID"
REASON_MULTIPLIER_ALIAS_DISAGREE = "MULTIPLIER_ALIAS_DISAGREE"
REASON_MULTIPLIER_UNKNOWN = "MULTIPLIER_UNKNOWN"
REASON_CONTRACT_QUARANTINED = "CONTRACT_QUARANTINED"


def is_valid_measurement(value: Any) -> float | None:
    """Finite float for a real numeric measurement, else None.

    Booleans are never measurements (True would otherwise read as 1.0).
    Nonfinite (NaN/inf), None and unparseable values are unknown, never zero.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def option_type_sign(opt_type: str | None) -> float | None:
    """Conventional option-type sign c_i: +1 call / -1 put. None when unknown."""
    t = str(opt_type or "").strip().lower()
    if t in ("call", "c", "ce"):
        return CALL_SIGN
    if t in ("put", "p", "pe"):
        return PUT_SIGN
    return None


def dollar_gamma_unit(gamma: float | None, multiplier: float | None, spot: float) -> float | None:
    """u_i = Γ m S² × 0.01. None when any input invalid/unknown."""
    g = is_valid_measurement(gamma)
    m = is_valid_measurement(multiplier)
    s = is_valid_measurement(spot)
    if g is None or m is None or s is None:
        return None
    if s <= 0 or g < 0 or m <= 0:
        return None
    return g * m * s * s * 0.01


def abs_delta(delta: float | None, tol: float = 1e-9) -> tuple[float | None, str | None]:
    """Return |δ| or (None, reason). Raw value retained by caller for provenance.

    Tiny overshoot (|δ| ≤ 1+tol from binary rounding) normalises with flag;
    material violation → invalid, never silently clamped. Booleans are not
    delta readings.
    """
    if delta is None or isinstance(delta, bool):
        return None, "DELTA_MISSING" if delta is None else "DELTA_INVALID"
    try:
        d = float(delta)
    except (TypeError, ValueError):
        return None, "DELTA_INVALID"
    if not math.isfinite(d):
        return None, "DELTA_INVALID"
    a = abs(d)
    if a <= 1.0:
        return a, None
    if a <= 1.0 + tol:
        return 1.0, "DELTA_ROUNDED"
    return None, "DELTA_OUT_OF_RANGE"


def decimal_strike(strike: Any) -> Decimal | None:
    """Exact decimal strike identity. None when unparseable."""
    if strike is None or isinstance(strike, bool):
        return None
    try:
        d = Decimal(str(strike))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not d.is_finite() or d <= 0:
        return None
    return d


@dataclass
class ExposureResult:
    gross: float
    net: float
    call: float
    put: float
    usable: int
    missing_delta: int
    missing_oi: int
    invalid: int
    basis: str
    formula_version: str = FORMULA_VERSION
    # Invalid delta readings (boolean, nonfinite, out-of-range) are NOT
    # missing observations. Canonical delta-weighted calculations count them
    # here so "unknown" and "unusable" never look alike downstream.
    invalid_delta: int = 0


def resolve_multiplier(contract: dict[str, Any]) -> tuple[float | None, str | None]:
    """Resolve the contract multiplier with explicit provenance.

    Returns (value, reason). reason is None when the value is usable.

    - Adjusted/nonstandard contracts → (None, CONTRACT_QUARANTINED).
    - No multiplier key carrying a value (all absent or None):
      (STANDARD_MULTIPLIER, "DEFAULT_STANDARD") — the documented
      standard-contract default. Positive-evidence provenance: exchange
      standard equity/index option deliverables are 100 shares; anything
      flagged adjusted must be quarantined upstream instead of defaulted.
    - A key present with an explicitly invalid value (0, negative, NaN,
      infinite, bool, unparseable) → (None, MULTIPLIER_INVALID). This is
      the R10-02 repair: explicit invalid must never fall back to 100.
    - A key present with None and no other key carrying a value →
      (None, MULTIPLIER_UNKNOWN): unknown, not absent, never defaulted.
    - Several keys present with differing finite positive values →
      (None, MULTIPLIER_ALIAS_DISAGREE): disagreement is surfaced, never
      resolved by whichever field comes first.
    """
    if not isinstance(contract, dict):
        return None, REASON_MULTIPLIER_INVALID
    if contract.get("adjusted") or contract.get("nonstandard"):
        return None, REASON_CONTRACT_QUARANTINED
    seen: dict[str, float] = {}
    for k in MULTIPLIER_KEYS:
        if k not in contract:
            continue
        raw = contract.get(k)
        if raw is None:
            continue
        parsed = is_valid_measurement(raw)
        if parsed is None or parsed <= 0:
            return None, REASON_MULTIPLIER_INVALID
        seen[k] = parsed
    if not seen:
        if any(k in contract for k in MULTIPLIER_KEYS):
            return None, REASON_MULTIPLIER_UNKNOWN
        return STANDARD_MULTIPLIER, "DEFAULT_STANDARD"
    values = set(seen.values())
    if len(values) > 1:
        return None, REASON_MULTIPLIER_ALIAS_DISAGREE
    return next(iter(values)), None


def _resolve_mult(contract: dict[str, Any]) -> float | None:
    """Legacy thin wrapper: usable value or None. Prefer resolve_multiplier."""
    value, _reason = resolve_multiplier(contract)
    return value


def compute_raw_oi(contracts: list[dict[str, Any]], spot: float) -> ExposureResult:
    """gex_gross_v1 / gex_net_v1 from supplied vendor gamma (F02 canonical)."""
    gross = net = call = put = 0.0
    usable = missing_oi = invalid = 0
    missing_delta = 0  # raw path does not need delta; kept for shape parity
    spot_f = is_valid_measurement(spot)
    for c in contracts:
        if not isinstance(c, dict):
            invalid += 1
            continue
        oi = c.get("oi", c.get("open_interest", c.get("N")))
        gamma = c.get("gamma", c.get("Γ"))
        oi_f = is_valid_measurement(oi)
        if oi_f is None:
            missing_oi += 1
            continue
        if oi_f < 0:
            invalid += 1
            continue
        if oi_f == 0:
            continue
        g_f = is_valid_measurement(gamma)
        if g_f is None or g_f < 0:
            invalid += 1
            continue
        sign = option_type_sign(c.get("type"))
        if sign is None:
            invalid += 1
            continue
        mult = _resolve_mult(c)
        if mult is None:
            invalid += 1
            continue
        u = dollar_gamma_unit(g_f, mult, spot_f if spot_f is not None else spot)
        if u is None:
            invalid += 1
            continue
        contrib = u * oi_f
        gross += contrib
        signed = sign * contrib
        net += signed
        if sign > 0:
            call += contrib
        else:
            put += contrib
        usable += 1
    return ExposureResult(gross, net, call, put, usable, missing_delta, missing_oi, invalid, "OI")


def compute_delta_weighted_oi(contracts: list[dict[str, Any]], spot: float) -> ExposureResult:
    """dadgex_gross_v1 / dadgex_net_v1: Σ u N |δ| with conventional sign."""
    gross = net = call = put = 0.0
    usable = missing_delta = missing_oi = invalid = invalid_delta = 0
    spot_f = is_valid_measurement(spot)
    for c in contracts:
        if not isinstance(c, dict):
            invalid += 1
            continue
        oi = c.get("oi", c.get("open_interest", c.get("N")))
        gamma = c.get("gamma", c.get("Γ"))
        delta = c.get("delta", c.get("δ"))
        oi_f = is_valid_measurement(oi)
        if oi_f is None:
            missing_oi += 1
            continue
        if oi_f < 0:
            invalid += 1
            continue
        if oi_f == 0:
            continue
        g_f = is_valid_measurement(gamma)
        if g_f is None or g_f < 0:
            invalid += 1
            continue
        sign = option_type_sign(c.get("type"))
        if sign is None:
            invalid += 1
            continue
        ad, reason = abs_delta(delta)
        if ad is None:
            if reason == "DELTA_MISSING":
                missing_delta += 1
            else:
                invalid_delta += 1
            continue
        mult = _resolve_mult(c)
        if mult is None:
            invalid += 1
            continue
        u = dollar_gamma_unit(g_f, mult, spot_f if spot_f is not None else spot)
        if u is None:
            invalid += 1
            continue
        w = u * ad * oi_f
        gross += w
        signed = sign * w
        net += signed
        if sign > 0:
            call += w
        else:
            put += w
        usable += 1
    return ExposureResult(gross, net, call, put, usable, missing_delta, missing_oi, invalid,
                          "OI_DELTA_WEIGHTED", invalid_delta=invalid_delta)


def compute_volume_gamma(contracts: list[dict[str, Any]], spot: float) -> ExposureResult:
    """volume_gamma_v1 = Σ c u V. Missing volume → skipped, never OI fallback."""
    gross_like = net = call = put = 0.0
    usable = missing_delta = invalid = 0
    missing_vol = 0
    spot_f = is_valid_measurement(spot)
    for c in contracts:
        if not isinstance(c, dict):
            invalid += 1
            continue
        vol = c.get("volume", c.get("V"))
        gamma = c.get("gamma", c.get("Γ"))
        v_f = is_valid_measurement(vol)
        if v_f is None:
            missing_vol += 1
            continue
        if v_f < 0:
            invalid += 1
            continue
        if v_f == 0:
            continue
        g_f = is_valid_measurement(gamma)
        if g_f is None or g_f < 0:
            invalid += 1
            continue
        sign = option_type_sign(c.get("type"))
        if sign is None:
            invalid += 1
            continue
        mult = _resolve_mult(c)
        if mult is None:
            invalid += 1
            continue
        u = dollar_gamma_unit(g_f, mult, spot_f if spot_f is not None else spot)
        if u is None:
            invalid += 1
            continue
        contrib = u * v_f
        gross_like += contrib
        signed = sign * contrib
        net += signed
        if sign > 0:
            call += contrib
        else:
            put += contrib
        usable += 1
    r = ExposureResult(gross_like, net, call, put, usable, missing_delta, missing_vol, invalid, "VOLUME")
    return r


def compute_session_delta_volume_gamma(
    contracts: list[dict[str, Any]], spot: float
) -> ExposureResult:
    """session_delta_volume_gamma_v1 = Σ c u V |δ| (R10-01 repair).

    The DISTINCT fourth activity formula: session volume weighted by
    |delta|, per contract, with the conventional call/put sign. This is
    NOT volume_gamma_v1 (Σ c u V, no delta weighting), which stays
    backward compatible. A contract with missing delta is UNAVAILABLE
    (missing_delta++, never zero-substituted); missing volume is
    unavailable separately. Same units/basis conventions as the family:
    USD per 1% spot move, VOLUME_DELTA_WEIGHTED basis.
    """
    gross = net = call = put = 0.0
    usable = missing_delta = missing_vol = invalid = invalid_delta = 0
    spot_f = is_valid_measurement(spot)
    for c in contracts:
        if not isinstance(c, dict):
            invalid += 1
            continue
        vol = c.get("volume", c.get("V"))
        gamma = c.get("gamma", c.get("Γ"))
        delta = c.get("delta", c.get("δ"))
        v_f = is_valid_measurement(vol)
        if v_f is None:
            missing_vol += 1
            continue
        if v_f < 0:
            invalid += 1
            continue
        if v_f == 0:
            continue
        g_f = is_valid_measurement(gamma)
        if g_f is None or g_f < 0:
            invalid += 1
            continue
        sign = option_type_sign(c.get("type"))
        if sign is None:
            invalid += 1
            continue
        ad, reason = abs_delta(delta)
        if ad is None:
            if reason == "DELTA_MISSING":
                missing_delta += 1
            else:
                invalid_delta += 1
            continue
        mult = _resolve_mult(c)
        if mult is None:
            invalid += 1
            continue
        u = dollar_gamma_unit(g_f, mult, spot_f if spot_f is not None else spot)
        if u is None:
            invalid += 1
            continue
        w = u * ad * v_f
        gross += w
        signed = sign * w
        net += signed
        if sign > 0:
            call += w
        else:
            put += w
        usable += 1
    return ExposureResult(gross, net, call, put, usable, missing_delta, missing_vol, invalid,
                          "VOLUME_DELTA_WEIGHTED", invalid_delta=invalid_delta)


def wall_metric_breakdown(walls: list[dict[str, Any]], contracts: list[dict[str, Any]],
                          spot: float) -> dict[str, dict[str, Any]]:
    """Wall-local delta/OI and session-volume values with separate coverage.

    Volume does not require OI or delta. volume_n retains its legacy count
    of positive-volume rows; volume_usable also counts valid reported zero.
    Missing/invalid inputs never supply evidence for a measured zero.
    """
    out: dict[str, dict[str, Any]] = {}
    for w in walls or []:
        if not isinstance(w, dict) or not w.get("wall_id"):
            continue
        try:
            members = {float(m) for m in (w.get("members") or [])}
        except (TypeError, ValueError):
            members = set()
        dg = dn = vg = vn = 0.0
        usable = missing = invalid = vn_n = 0
        daddex_invalid = 0
        volume_usable = volume_missing = volume_invalid = 0
        session_dv_gross = session_dv_net = 0.0
        session_dv_usable = session_dv_missing = session_dv_invalid = 0
        sdv_missing_delta = 0
        expiries: set = set()
        n_contracts = 0
        # Excluded population (resweep). A contract whose strike cannot be
        # read at all used to be dropped by a bare `continue` with NO count,
        # so a wall whose members all carried an unreadable strike reported
        # n_contracts=0 and looked exactly like a wall with no contracts
        # there. Unreadable and merely non-member are different facts.
        unreadable_strike = 0
        not_a_member = 0
        for c in contracts or []:
            if not isinstance(c, dict):
                unreadable_strike += 1
                continue
            s = is_valid_measurement(c.get("strike"))
            if s is None:
                unreadable_strike += 1
                continue
            if s not in members:
                not_a_member += 1
                continue
            n_contracts += 1
            if c.get("expiry"):
                expiries.add(str(c.get("expiry")))
            sign = option_type_sign(c.get("type"))
            u = dollar_gamma_unit(c.get("gamma"), _resolve_mult(c), spot)
            if sign is None or u is None or not math.isfinite(u):
                invalid += 1
                volume_invalid += 1
                session_dv_invalid += 1
                continue

            volume = c.get("volume", c.get("V"))
            if volume is None:
                volume_missing += 1
                session_dv_missing += 1
            else:
                v_f = is_valid_measurement(volume)
                if v_f is None or v_f < 0:
                    volume_invalid += 1
                    session_dv_invalid += 1
                else:
                    contribution = u * v_f
                    if not math.isfinite(contribution):
                        volume_invalid += 1
                        session_dv_invalid += 1
                    else:
                        vg += contribution
                        vn += sign * contribution
                        volume_usable += 1
                        if v_f > 0:
                            vn_n += 1
                        # Same member contracts as unweighted volume; this
                        # fourth surface needs delta, never an OI substitute.
                        ad_v, reason_v = abs_delta(c.get("delta", c.get("δ")))
                        if ad_v is None:
                            if reason_v == "DELTA_MISSING":
                                session_dv_missing += 1
                                sdv_missing_delta += 1
                            else:
                                session_dv_invalid += 1
                        elif not math.isfinite(contribution * ad_v):
                            session_dv_invalid += 1
                        else:
                            session_dv_gross += contribution * ad_v
                            session_dv_net += sign * contribution * ad_v
                            session_dv_usable += 1

            oi_f = is_valid_measurement(c.get("oi"))
            if oi_f is None or oi_f < 0:
                invalid += 1
                continue
            if oi_f == 0:
                continue
            ad, reason = abs_delta(c.get("delta", c.get("δ")))
            if ad is None:
                if reason == "DELTA_MISSING":
                    missing += 1
                else:
                    daddex_invalid += 1
            elif not math.isfinite(u * ad * oi_f):
                invalid += 1
            else:
                dg += u * ad * oi_f
                dn += sign * u * ad * oi_f
                usable += 1
        out[str(w["wall_id"])] = {
            "daddex_gross": dg if math.isfinite(dg) else None,
            "daddex_net": dn if math.isfinite(dn) else None,
            "daddex_usable": usable, "daddex_missing": missing,
            "daddex_invalid": daddex_invalid,
            "volume_gross": vg if math.isfinite(vg) else None,
            "volume_net": vn if math.isfinite(vn) else None, "volume_n": vn_n,
            "volume_usable": volume_usable, "volume_missing": volume_missing,
            "volume_invalid": volume_invalid,
            "session_delta_volume_gross": session_dv_gross if session_dv_usable and math.isfinite(session_dv_gross) else None,
            "session_delta_volume_net": session_dv_net if session_dv_usable and math.isfinite(session_dv_net) else None,
            "session_delta_volume_usable": session_dv_usable,
            "session_delta_volume_missing": session_dv_missing,
            "session_delta_volume_invalid": session_dv_invalid,
            "n_contracts": n_contracts, "invalid": invalid,
            # The excluded population, so "this wall has no contracts" and
            # "these contracts could not be matched to it" never look alike.
            "unreadable_strike": unreadable_strike,
            "not_a_member": not_a_member,
            "expiries": sorted(expiries),
            # R11 short names are compatibility aliases of the same result.
            "sdv_gross": session_dv_gross if session_dv_usable and math.isfinite(session_dv_gross) else None,
            "sdv_net": session_dv_net if session_dv_usable and math.isfinite(session_dv_net) else None,
            "sdv_usable": session_dv_usable, "sdv_missing_delta": sdv_missing_delta,
            # `basis` is the legacy single label (kept for compatibility); it
            # only ever described the daddex_* fields. `bases` names each family.
            "basis": "OI_DELTA_WEIGHTED", "formula_version": FORMULA_VERSION,
            "bases": {"daddex": "OI_DELTA_WEIGHTED", "volume": "VOLUME",
                      "session_delta_volume": "VOLUME_DELTA_WEIGHTED"},
        }
    return out


METRIC_REGISTRY = {
    "gex_gross_v1": {"formula": "Σ u N", "units": "USD/1% move", "basis": "OI", "version": FORMULA_VERSION},
    "gex_net_v1": {"formula": "Σ c u N", "units": "USD/1% move", "basis": "OI", "version": FORMULA_VERSION},
    "dadgex_gross_v1": {"formula": "Σ u N |δ|", "units": "USD/1% move", "basis": "OI_DELTA_WEIGHTED", "version": FORMULA_VERSION},
    "dadgex_net_v1": {"formula": "Σ c u N |δ|", "units": "USD/1% move", "basis": "OI_DELTA_WEIGHTED", "version": FORMULA_VERSION},
    "volume_gamma_v1": {"formula": "Σ c u V", "units": "USD/1% move", "basis": "VOLUME", "version": FORMULA_VERSION},
    "session_delta_volume_gamma_v1": {"formula": "Σ c u V |δ|", "units": "USD/1% move",
                                      "basis": "VOLUME_DELTA_WEIGHTED", "version": FORMULA_VERSION},
    "window_dadgex_v1": {"formula": "Σ c u |δ| ΔV(W)", "units": "USD/1% move", "basis": "VOLUME_WINDOW", "version": FORMULA_VERSION},
    # Live-assembly alias of window_dadgex_v1 (double-d): same formula, units
    # and basis. R5-B naming resolution — both keys always carry the same
    # state; either may be read, neither silently substituted for raw grids.
    "window_daddex_v1": {"formula": "Σ c u |δ| ΔV(W)", "units": "USD/1% move", "basis": "VOLUME_WINDOW", "version": FORMULA_VERSION,
                         "alias_of": "window_dadgex_v1"},
    # R7-02 canonical VEX (vanna exposure, packet §5.1): local-BS vanna,
    # signed contributions, gross = Σ|.|. Model, not vendor supply.
    "vex_net_1volpt": {"formula": "Σ c m N S vanna 0.01", "units": "USD delta-notional/+1 vol pt",
                       "basis": "VEX_1VOLPT", "version": FORMULA_VERSION, "model": "local-bs-vanna.v1"},
    "vex_gross_1volpt": {"formula": "Σ |m N S vanna 0.01|", "units": "USD delta-notional/+1 vol pt",
                         "basis": "VEX_1VOLPT", "version": FORMULA_VERSION, "model": "local-bs-vanna.v1"},
    "duo_d2gex_dS2_v1": {"formula": "C*(S^2*gamma''+4*S*gamma'+2*gamma)", "units": "USD/(1% move)^2",
                         "basis": "DUO_D2GEX_DS2", "version": FORMULA_VERSION, "model": "local-bs-second-order.v1"},
    "dvo_dvega_dsigma_v1": {"formula": "vomma*OI*100", "units": "USD/unit-sigma",
                            "basis": "DVO_DVEGA_DSIGMA", "version": FORMULA_VERSION, "model": "local-bs-second-order.v1"},
}
