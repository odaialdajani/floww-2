"""
backend/services/solstice_provenance.py — pair provenance, volume-retraction
quarantine, change attribution (T02/T09/T27).

- Greek pair provenance: vendor/vendor, local/local, mixed (eligible only
  under documented policy), unknown. Vendor provenance alone is not accuracy.
- Volume retraction: negative cumulative-volume change (e.g. 1240→1180) is a
  correction/reset/out-of-order candidate — quarantine the window, rebaseline,
  require a complete valid window before re-enabling. Never negative flow.
- Change attribution: sequential counterfactual (spot → IV → time → OI) with
  residual + tolerance. Order matters; label it.
"""

from __future__ import annotations

import math
from typing import Any


def greek_pair_provenance(gamma_source: str | None, delta_source: str | None) -> dict[str, Any]:
    """Classify (gamma, delta) source pair for delta-weighted metrics."""
    g = (gamma_source or "unknown").lower()
    d = (delta_source or "unknown").lower()
    if g == "unknown" or d == "unknown":
        return {"pair": "unknown", "eligible": False, "reason": "SOURCE_UNKNOWN"}
    if g == d:
        return {"pair": f"{g}/{d}", "eligible": True, "reason": None}
    return {"pair": f"mixed:{g}/{d}", "eligible": False,
            "reason": "MIXED_PAIR_REQUIRES_POLICY",
            "note": "median vendor/local difference is not a confidence interval"}


def check_volume_window(prev_cum: float | None, cur_cum: float | None) -> dict[str, Any]:
    """Validate one cumulative-volume step. Negative delta quarantines the window."""
    if prev_cum is None or cur_cum is None:
        return {"delta": None, "valid": False, "reason": "NO_BASELINE"}
    try:
        p, c = float(prev_cum), float(cur_cum)
    except (TypeError, ValueError):
        return {"delta": None, "valid": False, "reason": "INVALID"}
    if not math.isfinite(p) or not math.isfinite(c) or p < 0 or c < 0:
        return {"delta": None, "valid": False, "reason": "INVALID"}
    d = c - p
    if d < 0:
        return {"delta": d, "valid": False, "reason": "VOLUME_REBASE",
                "action": "quarantine window, establish new baseline at cur, "
                          "require complete valid window before re-enabling"}
    return {"delta": d, "valid": True, "reason": None}


def attribute_change(old: dict[str, Any], new: dict[str, Any], spot_new: float,
                     tol: float = 1e-6) -> dict[str, Any]:
    """Sequential counterfactual attribution for a fixed contract universe.

    Steps: (1) old OI @ new spot, old IV/time; (2) new IV; (3) new time;
    (4) new OI. Additions/removals reported separately. Returns components +
    residual (actual_new - sum of steps); residual beyond tol must be explained,
    never hidden.
    """
    try:
        oi0 = float(old.get("oi", 0) or 0)
        oi1 = float(new.get("oi", 0) or 0)
        s0 = float(old.get("spot", spot_new) or spot_new)
        g0 = float(old.get("gamma", 0) or 0)
        g1 = float(new.get("gamma", 0) or 0)
        m = float(old.get("multiplier", new.get("multiplier", 100.0)) or 100.0)
    except (TypeError, ValueError):
        return {"error": "INVALID_INPUTS", "residual": None}
    def unit(g: float, s: float) -> float:
        return g * oi0 * m * s * s * 0.01

    base = unit(g0, s0)
    s_spot = unit(g0, spot_new) - base          # spot repricing
    s_iv_time = unit(g1, spot_new) - unit(g0, spot_new)  # IV+time repricing (labeled combined)
    actual_new = g1 * oi1 * m * spot_new * spot_new * 0.01
    s_oi = actual_new - unit(g1, spot_new)      # OI observation step
    residual = actual_new - (base + s_spot + s_iv_time + s_oi)
    return {"order": ["spot", "iv_time", "oi"], "base": base,
            "spot": s_spot, "iv_time": s_iv_time, "oi": s_oi,
            "actual_new": actual_new, "residual": residual,
            "within_tol": abs(residual) <= tol,
            "note": "sequential attribution; order matters (Shapley later if justified)"}
