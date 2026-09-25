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
    try:
        g = float(gamma) if gamma is not None else None
        m = float(multiplier) if multiplier is not None else None
        s = float(spot)
    except (TypeError, ValueError):
        return None
    if g is None or m is None or not math.isfinite(g) or not math.isfinite(m):
        return None
    if not math.isfinite(s) or s <= 0 or g < 0 or m <= 0:
        return None
    return g * m * s * s * 0.01


def abs_delta(delta: float | None, tol: float = 1e-9) -> tuple[float | None, str | None]:
    """Return |δ| or (None, reason). Raw value retained by caller for provenance.

    Tiny overshoot (|δ| ≤ 1+tol from binary rounding) normalises with flag;
    material violation → invalid, never silently clamped.
    """
    if delta is None:
        return None, "DELTA_MISSING"
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
    if strike is None:
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


def _resolve_mult(contract: dict[str, Any]) -> float | None:
    for k in ("multiplier", "contractMultiplier", "m"):
        v = contract.get(k)
        if v is not None:
            try:
                f = float(v)
                if math.isfinite(f) and f > 0:
                    return f
            except (TypeError, ValueError):
                continue
    # Default 100 only when contract is standard equity/index option without
    # adjusted deliverable flags; adjusted contracts must be quarantined upstream.
    if contract.get("adjusted") or contract.get("nonstandard"):
        return None
    return 100.0


def compute_raw_oi(contracts: list[dict[str, Any]], spot: float) -> ExposureResult:
    """gex_gross_v1 / gex_net_v1 from supplied vendor gamma (F02 canonical)."""
    gross = net = call = put = 0.0
    usable = missing_oi = invalid = 0
    missing_delta = 0  # raw path does not need delta; kept for shape parity
    for c in contracts:
        oi = c.get("oi", c.get("open_interest", c.get("N")))
        gamma = c.get("gamma", c.get("Γ"))
        try:
            oi_f = float(oi) if oi is not None else None
        except (TypeError, ValueError):
            oi_f = None
        if oi_f is None or not math.isfinite(oi_f):
            missing_oi += 1
            continue
        if oi_f < 0:
            invalid += 1
            continue
        if oi_f == 0:
            continue
        try:
            g_f = float(gamma) if gamma is not None else None
        except (TypeError, ValueError):
            g_f = None
        if g_f is None or not math.isfinite(g_f) or g_f < 0:
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
        u = dollar_gamma_unit(g_f, mult, spot)
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
    usable = missing_delta = missing_oi = invalid = 0
    for c in contracts:
        oi = c.get("oi", c.get("open_interest", c.get("N")))
        gamma = c.get("gamma", c.get("Γ"))
        delta = c.get("delta", c.get("δ"))
        try:
            oi_f = float(oi) if oi is not None else None
        except (TypeError, ValueError):
            oi_f = None
        if oi_f is None or not math.isfinite(oi_f):
            missing_oi += 1
            continue
        if oi_f < 0:
            invalid += 1
            continue
        if oi_f == 0:
            continue
        try:
            g_f = float(gamma) if gamma is not None else None
        except (TypeError, ValueError):
            g_f = None
        if g_f is None or not math.isfinite(g_f) or g_f < 0:
            invalid += 1
            continue
        sign = option_type_sign(c.get("type"))
        if sign is None:
            invalid += 1
            continue
        ad, _reason = abs_delta(delta)
        if ad is None:
            missing_delta += 1
            continue
        mult = _resolve_mult(c)
        if mult is None:
            invalid += 1
            continue
        u = dollar_gamma_unit(g_f, mult, spot)
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
    return ExposureResult(gross, net, call, put, usable, missing_delta, missing_oi, invalid, "OI_DELTA_WEIGHTED")


def compute_volume_gamma(contracts: list[dict[str, Any]], spot: float) -> ExposureResult:
    """volume_gamma_v1 = Σ c u V. Missing volume → skipped, never OI fallback."""
    gross_like = net = call = put = 0.0
    usable = missing_delta = invalid = 0
    missing_vol = 0
    for c in contracts:
        vol = c.get("volume", c.get("V"))
        gamma = c.get("gamma", c.get("Γ"))
        try:
            v_f = float(vol) if vol is not None else None
        except (TypeError, ValueError):
            v_f = None
        if v_f is None or not math.isfinite(v_f):
            missing_vol += 1
            continue
        if v_f < 0:
            invalid += 1
            continue
        if v_f == 0:
            continue
        try:
            g_f = float(gamma) if gamma is not None else None
        except (TypeError, ValueError):
            g_f = None
        if g_f is None or not math.isfinite(g_f) or g_f < 0:
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
        u = dollar_gamma_unit(g_f, mult, spot)
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


def wall_metric_breakdown(walls: list[dict[str, Any]], contracts: list[dict[str, Any]],
                          spot: float) -> dict[str, dict[str, Any]]:
    """Per-wall delta-weighted + session-volume breakdown (R6-2).

    Each wall aggregates ONLY its member strikes' contracts over the same
    declared scope: daddex gross/net (Σ u·N·|δ|, Σ c·u·N·|δ|), session volume
    net/gross (Σ c·u·V), usable/missing/invalid counts, member expiries.
    Missing delta is counted per wall (never zero-filled). Scope-wide totals
    stay separate — a wall-local row never shows a whole-scope sum.
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
        expiries: set = set()
        n_contracts = 0
        for c in contracts or []:
            if not isinstance(c, dict):
                continue
            try:
                s = float(c.get("strike"))
            except (TypeError, ValueError):
                continue
            if s not in members:
                continue
            n_contracts += 1
            if c.get("expiry"):
                expiries.add(str(c.get("expiry")))
            sign = option_type_sign(c.get("type"))
            if sign is None:
                invalid += 1
                continue
            mult = _resolve_mult(c)
            if mult is None:
                invalid += 1
                continue
            try:
                g_f = float(c.get("gamma")) if c.get("gamma") is not None else None
                oi_f = float(c.get("oi")) if c.get("oi") is not None else None
            except (TypeError, ValueError):
                g_f, oi_f = None, None
            if g_f is None or oi_f is None or not math.isfinite(g_f) or not math.isfinite(oi_f):
                invalid += 1
                continue
            if g_f < 0 or oi_f < 0:
                invalid += 1
                continue
            if oi_f == 0:
                continue
            u = dollar_gamma_unit(g_f, mult, spot)
            if u is None:
                invalid += 1
                continue
            ad, _reason = abs_delta(c.get("delta", c.get("δ")))
            if ad is None:
                missing += 1
            else:
                dg += u * ad * oi_f
                dn += sign * u * ad * oi_f
                usable += 1
            try:
                v_f = float(c.get("volume", c.get("V"))) if c.get("volume", c.get("V")) is not None else None
            except (TypeError, ValueError):
                v_f = None
            if v_f is not None and math.isfinite(v_f) and v_f > 0:
                vg += u * v_f
                vn += sign * u * v_f
                vn_n += 1
        out[str(w["wall_id"])] = {
            "daddex_gross": dg, "daddex_net": dn,
            "daddex_usable": usable, "daddex_missing": missing,
            "volume_gross": vg, "volume_net": vn, "volume_n": vn_n,
            "n_contracts": n_contracts, "invalid": invalid,
            "expiries": sorted(expiries),
            "basis": "OI_DELTA_WEIGHTED", "formula_version": FORMULA_VERSION,
        }
    return out


METRIC_REGISTRY = {
    "gex_gross_v1": {"formula": "Σ u N", "units": "USD/1% move", "basis": "OI", "version": FORMULA_VERSION},
    "gex_net_v1": {"formula": "Σ c u N", "units": "USD/1% move", "basis": "OI", "version": FORMULA_VERSION},
    "dadgex_gross_v1": {"formula": "Σ u N |δ|", "units": "USD/1% move", "basis": "OI_DELTA_WEIGHTED", "version": FORMULA_VERSION},
    "dadgex_net_v1": {"formula": "Σ c u N |δ|", "units": "USD/1% move", "basis": "OI_DELTA_WEIGHTED", "version": FORMULA_VERSION},
    "volume_gamma_v1": {"formula": "Σ c u V", "units": "USD/1% move", "basis": "VOLUME", "version": FORMULA_VERSION},
    "window_dadgex_v1": {"formula": "Σ c u |δ| ΔV(W)", "units": "USD/1% move", "basis": "VOLUME_WINDOW", "version": FORMULA_VERSION},
    # Live-assembly alias of window_dadgex_v1 (double-d): same formula, units
    # and basis. R5-B naming resolution — both keys always carry the same
    # state; either may be read, neither silently substituted for raw grids.
    "window_daddex_v1": {"formula": "Σ c u |δ| ΔV(W)", "units": "USD/1% move", "basis": "VOLUME_WINDOW", "version": FORMULA_VERSION,
                         "alias_of": "window_dadgex_v1"},
}
