"""
backend/services/solstice_enrichment.py — attached-research enrichment (T08).

Capability-aware: moneyness buckets, OI-change ranking (effective-date gated),
relative volume vs matched DTE/moneyness cohort baselines, multi-horizon
context. Never infers opening/closing, buyer direction, sweeps, or premium
VWAP from snapshots.
"""

from __future__ import annotations

import math
from typing import Any


def moneyness_buckets(contracts: list[dict], spot: float) -> dict[str, Any]:
    """Call/put × delta-band concentration + activity distribution (no speculation labels)."""
    buckets: dict[str, dict[str, float]] = {}
    for c in contracts or []:
        try:
            d = abs(float(c.get("delta"))) if c.get("delta") is not None else None
            oi = float(c.get("oi", 0) or 0)
            vol = float(c.get("volume", 0) or 0)
        except (TypeError, ValueError):
            continue
        if d is None or not math.isfinite(d):
            band = "delta_unknown"
        elif d < 0.2:
            band = "far_otm"
        elif d < 0.4:
            band = "otm"
        elif d <= 0.6:
            band = "atm"
        elif d <= 0.8:
            band = "itm"
        else:
            band = "deep_itm"
        side = "call" if str(c.get("type", "")).lower().startswith("c") else "put"
        key = f"{side}_{band}"
        b = buckets.setdefault(key, {"oi": 0.0, "volume": 0.0, "n": 0})
        b["oi"] += oi if math.isfinite(oi) and oi > 0 else 0.0
        b["volume"] += vol if math.isfinite(vol) and vol > 0 else 0.0
        b["n"] += 1
    return {"buckets": buckets, "note": "distribution only; OTM activity is not directional speculation evidence"}


def oi_changes(current: list[dict], previous: list[dict]) -> dict[str, Any]:
    """Effective-date OI comparisons; ranked changes. Net change classifies nothing.

    R4-10/P03 contract: identity is matched on (expiry, strike, type) AND
    both sides must carry an effective date. An absent previous
    contract is an unknown baseline (NO_PRIOR_OI_BASELINE) — never zero OI,
    never ranked as new positioning. A date on only one side is
    date-unknown, not a comparable epoch. Two present dates (even across
    aligned/adjacent epochs) remain comparable with both dates recorded;
    a provider correction creates a new comparable epoch via the new
    observation (never fabricated from request time).
    """
    def key(c):
        return (str(c.get("expiry")), str(c.get("strike")), str(c.get("type")).lower())
    prev = {key(c): c for c in (previous or []) if isinstance(c, dict)}
    rows = []
    n_unknown_baseline = 0
    n_date_unknown = 0
    for c in current or []:
        if not isinstance(c, dict):
            continue
        p = prev.get(key(c))
        if p is None:
            n_unknown_baseline += 1
            continue
        try:
            co = float(c.get("oi", 0) or 0)
            po = float(p.get("oi", 0) or 0)
        except (TypeError, ValueError):
            continue
        ceff, peff = c.get("oi_effective_date"), p.get("oi_effective_date")
        if ceff is None or peff is None:
            n_date_unknown += 1
            continue
        rows.append({"key": key(c), "oi": co, "prev_oi": po, "delta": co - po,
                     "oi_effective_date": ceff, "prev_oi_effective_date": peff})
    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return {"changes": rows[:20], "n_compared": len(rows),
            "n_unknown_baseline": n_unknown_baseline,
            "n_date_unknown": n_date_unknown,
            "note": "net OI change does not classify opening/closing or buyer direction"}


def _contract_key(c: dict) -> tuple:
    return (str(c.get("osi") or ""),
            str(c.get("expiry") or ""),
            str(c.get("strike") or ""),
            str(c.get("type") or "").lower())


def window_contract_activity(prev: list[dict], cur: list[dict],
                             spot: float) -> dict[str, Any]:
    """Same-contract, same-epoch window delta-weighted activity (R4-14/P03).

    Matches contracts by (OSI, expiry, strike, type) across two cumulative
    snapshots from one provider epoch, using frozen-open Greeks:
      window_daddex = c · u(open) · |δ(open)| · ΔV,  u = Γ·m·S²×0.01
    with conventional call-minus-put sign c. Missing delta (either side)
    skips the contract with counts BEFORE volume validation — a
    delta-unknown contract is outside the activity population, so its
    volume step cannot quarantine the window (never zero-fill). Remaining
    volume steps validated by check_volume_window: a negative cumulative
    change quarantines the whole window (VOLUME_REBASE), never negative
    flow. Mixed gamma/delta provenance pairs are blocked without policy.
    OI turnover is turnover, never inventory-erosion evidence.
    """
    import math as _math

    from services.solstice_provenance import check_volume_window

    before = {_contract_key(c): c for c in (prev or []) if isinstance(c, dict)}
    rows = []
    missing_delta = 0
    mixed_pair = 0
    for c in cur or []:
        if not isinstance(c, dict):
            continue
        p = before.get(_contract_key(c))
        if p is None:
            continue  # NO_PRIOR baseline: not comparable, not ranked
        if p.get("delta") is None or c.get("delta") is None:
            missing_delta += 1
            continue
        chk = check_volume_window(p.get("volume"), c.get("volume"))
        if not chk["valid"]:
            if chk["reason"] == "VOLUME_REBASE":
                return {"status": "unavailable", "reason": "VOLUME_REBASE",
                        "contracts": [], "missing_delta": missing_delta,
                        "mixed_pair": mixed_pair,
                        "note": "cumulative-volume correction invalidated the window; "
                                "new baseline required before re-enabling"}
            continue
        dv = chk["delta"]
        if not dv or dv <= 0:
            continue
        gsrc = p.get("greeks_source") or "vendor"
        dsrc = p.get("delta_source", gsrc) or "vendor"
        if gsrc != dsrc:
            mixed_pair += 1
            continue
        try:
            g = float(p.get("gamma"))
            d = abs(float(p.get("delta")))
            m = float(p.get("multiplier", 100.0) or 100.0)
        except (TypeError, ValueError):
            continue
        if not all(_math.isfinite(x) for x in (g, d, m, dv)) or g < 0 or m <= 0:
            continue
        if d > 1.0 + 1e-9:
            continue
        sign = 1.0 if str(p.get("type", "")).lower().startswith("c") else -1.0
        u = g * m * spot * spot * 0.01
        rows.append({"osi": c.get("osi"), "expiry": c.get("expiry"),
                     "strike": c.get("strike"), "delta_volume": dv,
                     "window_daddex": sign * u * min(d, 1.0) * dv,
                     "pair": f"{gsrc}/{dsrc}"})
    rows.sort(key=lambda r: abs(r["window_daddex"]), reverse=True)
    return {"status": "ok", "contracts": rows,
            "missing_delta": missing_delta, "mixed_pair": mixed_pair,
            "note": "turnover, not positioning"}


def relative_volume(contracts: list[dict], baselines: dict[str, float]) -> dict[str, Any]:
    """Relative activity vs matched DTE/moneyness cohort baselines.

    baselines: {(expiry, band): median_volume} with cohort sizes. 0DTE series
    without 10 prior sessions use smaller cohorts + report baseline size.
    """
    rows = []
    for c in contracts or []:
        band = str(c.get("band", "atm"))
        key = f"{c.get('expiry')}|{band}"
        base = baselines.get(key)
        try:
            v = float(c.get("volume", 0) or 0)
        except (TypeError, ValueError):
            continue
        if base is None or base <= 0:
            rows.append({"osi": c.get("osi"), "rvol": None, "reason": "NO_BASELINE"})
        else:
            rows.append({"osi": c.get("osi"), "rvol": round(v / base, 2), "baseline": base})
    rows.sort(key=lambda r: (r.get("rvol") or -1), reverse=True)
    return {"relative": rows[:20], "note": "matched cohorts; baseline size reported by caller"}
