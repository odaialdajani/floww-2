"""Backend Triad projection — canonical exposure onto the Public chain (C3).

WHY THIS EXISTS
===============
`/api/public/chain/{ticker}` returns contracts that carry `gamma`, `delta`,
`oi`, `volume`, `strike`, `expiry` and `type` — and NOT a computed `gex`.
The Triad view, on both the old inline transform and the new pure projection,
reads `c.gex`. So with real adapter input every cell's exposure is unknown, the
projection yields zero renderable rows, and the view silently falls through to
its `/api/data` fallback. Real Public-shaped input therefore never reached
visible Triad values on the primary path. That is the defect named in the C3
audit, and it is still live.

The fix is NOT a third Greek engine. Every formula here is delegated to
`domain/exposure_metrics`, which is the canonical registry (gex.v2):

    u_i  = Γ_i · m · S² · 0.01          -> dollar_gamma_unit()
    gex_i = sign(type_i) · u_i · N_i     -> sign from option_type_sign()

so a contract's `gex` here is exactly the `gex_net_v1` term
`Σ c u N` in METRIC_REGISTRY, and the aggregate equals `compute_raw_oi(...).net`.
That equality is asserted in the tests, which is what makes this a projection
rather than a fourth engine.

MISSINGNESS
===========
A contract whose gamma, oi, or option type is unknown gets `gex: None` plus a
reason code. It is never zero-filled. A partially-observed cell reports a
labelled observed subtotal AND its coverage counts; it never looks complete.
Zero OI is a real measurement of zero and is reported as such; missing OI is
unknown and is not.

ROUTE LEASE
===========
`annotate_contract_exposure` is the single seam a route owner needs. Wiring it
is a shared route/server mutation, which is Hermes's lease, so this module
ships the function and the tests without touching `routes/` or `server.py`.
"""

from __future__ import annotations

import math
from typing import Any

from domain.exposure_metrics import (
    FORMULA_VERSION,
    METRIC_REGISTRY,
    compute_raw_oi,
    decimal_strike,
    option_type_sign,
)

TRIAD_PROJECTION_VERSION = "triad-projection.backend.v1"

# Reason codes. These travel with the data; a consumer can tell "unknown" from
# "measured zero" without guessing.
REASON_OI_MISSING = "OI_MISSING"
REASON_GAMMA_MISSING = "GAMMA_MISSING"
REASON_TYPE_UNKNOWN = "TYPE_UNKNOWN"
REASON_STRIKE_INVALID = "STRIKE_INVALID"
REASON_EXPIRY_MISSING = "EXPIRY_MISSING"


def _finite(value: Any) -> float | None:
    """A finite float, or None. Booleans are not numbers here."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _strike_key(value: Any) -> str | None:
    """Exact strike identity for grid keys (R10-08 repair).

    100.25 and 100.75 are different strikes and must never collapse to
    "100" via int(). Integral strikes keep their legacy "450" form so
    existing consumers see no change; fractional strikes render exactly
    ("100.25"). None when the strike is not a valid positive number.
    """
    d = decimal_strike(value)
    if d is None:
        return None
    if d == d.to_integral_value():
        return str(int(d))
    return str(d.normalize())


def _strike_num(value: Any) -> float | None:
    d = decimal_strike(value)
    return float(d) if d is not None else None


def annotate_contract_exposure(
    contracts: list[dict[str, Any]] | None,
    spot: float,
) -> list[dict[str, Any]]:
    """Return the contracts with a canonical signed `gex` attached per row.

    The VALUE is not re-derived here. Each row's exposure is obtained by
    evaluating the canonical aggregate over that row alone
    (`compute_raw_oi([row], spot).net`), so the per-contract number is by
    construction the `gex_net_v1` term and cannot drift from the registry. An
    earlier version of this function re-implemented the formula with a
    hardcoded multiplier of 100; that silently disagreed with the canonical
    resolver, which honours an explicit per-contract multiplier and QUARANTINES
    adjusted/nonstandard contracts. Deriving instead of re-deriving removes
    that whole class of drift, and the reason codes below stay diagnostics
    rather than part of the arithmetic.

    The input rows are not mutated. Each returned row carries:
      gex          float | None   signed canonical contribution (gex_net_v1 term)
      gex_basis    str            "OI" when measured, "OI_UNKNOWN" when not
      gex_reason   str | None     why it is null, when it is null

    Zero OI is a measurement: it yields gex == 0.0, not None. That distinction
    is the whole point — a contract nobody has open in is genuinely neutral,
    while a contract whose OI the vendor did not report is unknown.
    """
    spot_f = _finite(spot)
    out: list[dict[str, Any]] = []
    for row in contracts or []:
        if not isinstance(row, dict):
            continue
        enriched = dict(row)
        oi = _finite(row.get("oi", row.get("open_interest")))
        gamma = _finite(row.get("gamma", row.get("Γ")))
        sign = option_type_sign(row.get("type"))

        gex: float | None = None
        reason: str | None = None

        if oi is None:
            reason = REASON_OI_MISSING
        elif oi < 0:
            reason = "OI_NEGATIVE"
        elif oi == 0:
            # Measured zero. Real, and different from unknown. The canonical
            # aggregate skips zero-OI rows without counting them as invalid,
            # which is exactly this case.
            gex = 0.0
        else:
            result = compute_raw_oi([row], spot_f if spot_f is not None else 0.0)
            if result.usable == 1:
                gex = result.net
            else:
                # Diagnostics only. The value, when there is one, came from the
                # canonical aggregate above.
                if gamma is None:
                    reason = REASON_GAMMA_MISSING
                elif gamma < 0:
                    reason = "GAMMA_NEGATIVE"
                elif sign is None:
                    reason = REASON_TYPE_UNKNOWN
                elif spot_f is None or spot_f <= 0:
                    reason = "SPOT_UNKNOWN"
                elif result.invalid:
                    reason = "CONTRACT_QUARANTINED"
                else:
                    reason = "EXPOSURE_UNDEFINED"

        enriched["gex"] = gex
        enriched["gex_basis"] = "OI" if gex is not None else "OI_UNKNOWN"
        enriched["gex_reason"] = reason
        enriched["gex_formula_version"] = FORMULA_VERSION
        out.append(enriched)
    return out


def project_triad_from_chain(
    payload: dict[str, Any] | None,
    *,
    expiry_count: int | None = None,
) -> dict[str, Any]:
    """Project an adapter-shaped chain payload into the Triad data packet.

    Mirrors the frontend projection's contract (`frontend/src/lib/triadProjection.js`)
    so both sides describe the same packet. Backend owns the aggregation and the
    metric; the renderer only selects and draws.
    """
    payload = payload or {}
    raw_contracts = payload.get("contracts")
    contracts_in = raw_contracts if isinstance(raw_contracts, list) else []
    spot = _finite(payload.get("spot"))

    dropped = {"no_expiry": 0, "bad_strike": 0, "unknown_side": 0}
    placeable: list[dict[str, Any]] = []
    for row in contracts_in:
        if not isinstance(row, dict):
            dropped["bad_strike"] += 1
            continue
        expiry = row.get("expiry")
        if not isinstance(expiry, str) or not expiry.strip():
            dropped["no_expiry"] += 1
            continue
        strike = _finite(row.get("strike"))
        if strike is None or strike <= 0:
            dropped["bad_strike"] += 1
            continue
        if option_type_sign(row.get("type")) is None:
            dropped["unknown_side"] += 1
            continue
        placeable.append(row)

    annotated = annotate_contract_exposure(placeable, spot if spot is not None else 0.0)

    all_expiries = sorted({r["expiry"].strip() for r in placeable if r.get("expiry")})
    cap = _finite(expiry_count)
    cap_i = int(cap) if cap is not None and cap > 0 else None
    capped = cap_i is not None and len(all_expiries) > cap_i
    expiries = all_expiries[:cap_i] if capped else all_expiries
    used = set(expiries)

    # (expiry, strike) -> aggregated cell. Side is a dimension of the SUM, not
    # of the key: a call and a put at one strike net rather than overwrite.
    grid: dict[str, dict[str, dict[str, Any]]] = {exp: {} for exp in expiries}
    for row in annotated:
        if row["expiry"].strip() not in used:
            continue
        key = _strike_key(row["strike"])
        if key is None:
            continue
        bucket = grid[row["expiry"].strip()]
        cell = bucket.setdefault(
            key,
            {
                "gex": None,
                "call_gex": None,
                "put_gex": None,
                "oi": None,
                "volume": None,
                "sides_present": 0,
                "missing_gex": 0,
            },
        )
        gex = row.get("gex")
        if gex is None:
            cell["missing_gex"] += 1
        else:
            cell["gex"] = (cell["gex"] or 0.0) + gex
            side_key = "call_gex" if option_type_sign(row.get("type")) > 0 else "put_gex"
            cell[side_key] = (cell[side_key] or 0.0) + gex
        oi = _finite(row.get("oi"))
        if oi is not None:
            cell["oi"] = (cell["oi"] or 0.0) + oi
        vol = _finite(row.get("volume"))
        if vol is not None:
            cell["volume"] = (cell["volume"] or 0.0) + vol
        cell["sides_present"] += 1

    # Per-strike rows across the expiries actually shown. Keyed by exact
    # decimal strike identity (R10-08): 100.25 and 100.75 stay distinct.
    by_strike: dict[str, dict[str, Any]] = {}
    for row in annotated:
        if row["expiry"].strip() not in used:
            continue
        strike_key = _strike_key(row["strike"])
        if strike_key is None:
            continue
        strike_num = _strike_num(row["strike"])
        rec = by_strike.setdefault(
            strike_key,
            {
                "strike": strike_num,
                "gex": None,
                "call_gex": None,
                "put_gex": None,
                "oi": None,
                "volume": None,
                "expiries": [],
            },
        )
        if row["expiry"].strip() not in rec["expiries"]:
            rec["expiries"].append(row["expiry"].strip())
        gex = row.get("gex")
        if gex is not None:
            rec["gex"] = (rec["gex"] or 0.0) + gex
            side_key = "call_gex" if option_type_sign(row.get("type")) > 0 else "put_gex"
            rec[side_key] = (rec[side_key] or 0.0) + gex
        oi = _finite(row.get("oi"))
        if oi is not None:
            rec["oi"] = (rec["oi"] or 0.0) + oi
        vol = _finite(row.get("volume"))
        if vol is not None:
            rec["volume"] = (rec["volume"] or 0.0) + vol

    strikes = sorted(by_strike.values(), key=lambda r: (r["strike"] is None, r["strike"] or 0.0),
                     reverse=True)

    # King is a STRIKE chosen from aggregated rows, not a single contract.
    king = None
    for rec in strikes:
        if rec["gex"] is None:
            continue
        if king is None or abs(rec["gex"]) > abs(king["gex"]):
            king = {"strike": rec["strike"], "gex": rec["gex"]}

    measured_rows = [r for r in strikes if r["gex"] is not None]
    net_gex = sum(r["gex"] for r in measured_rows) if measured_rows else None

    return {
        "projection_version": TRIAD_PROJECTION_VERSION,
        "formula_version": FORMULA_VERSION,
        "metric_ids": sorted(METRIC_REGISTRY),
        "ticker": payload.get("ticker"),
        "spot": spot,
        # Not carried by this input. Unknown, never defaulted to a number.
        "change_pct": None,
        "vix": None,
        "nodes": {
            "regime": (
                "positive" if net_gex > 0 else "negative" if net_gex < 0 else "neutral"
            )
            if net_gex is not None
            else "unknown",
            "king": king,
            # The zero-gamma root is a backend root solve, not a sign change
            # between adjacent strike buckets. Not inferred here.
            "gamma_flip": None,
            "floors": [],
            "ceilings": [],
            "gatekeepers": [],
            "air_pockets": [],
            # Not |exposure| / spot. Reported unknown rather than invented.
            "polarity_level": None,
            "net_gex": net_gex,
        },
        "strikes": strikes,
        "grid": {"grid": grid},
        "expiries_used": expiries,
        "coverage": {
            "returned": len(contracts_in),
            "usable": len(measured_rows),
            "dropped_no_expiry": dropped["no_expiry"],
            "dropped_bad_strike": dropped["bad_strike"],
            "dropped_unknown_side": dropped["unknown_side"],
            "contracts_without_gex": sum(c["missing_gex"] for bucket in grid.values() for c in bucket.values()),
            "expiries_available": len(all_expiries),
            "expiries_requested": cap_i,
            "expiries_used": len(expiries),
            "expiry_cap_applied": capped,
            "expiries_dropped_by_cap": (len(all_expiries) - cap_i) if capped else 0,
            "truncated": capped,
        },
        "data_source": payload.get("data_source") or "public_api",
        "stale": payload.get("stale") is True,
    }


def exposure_parity(contracts: list[dict[str, Any]], spot: float) -> dict[str, Any]:
    """Assert-level helper: the projection's net must equal the canonical net.

    Returns both values so a caller (or a test) can compare them. If this ever
    diverges, the projection has become a fourth engine and is wrong.
    """
    canonical = compute_raw_oi(contracts, spot)
    annotated = annotate_contract_exposure(contracts, spot)
    projected = sum(r["gex"] for r in annotated if r.get("gex") is not None)
    return {
        "canonical_net": canonical.net,
        "canonical_usable": canonical.usable,
        "projected_net": projected,
        "agrees": math.isclose(projected, canonical.net, rel_tol=1e-9, abs_tol=1e-9),
    }


__all__ = [
    "TRIAD_PROJECTION_VERSION",
    "REASON_OI_MISSING",
    "REASON_GAMMA_MISSING",
    "REASON_TYPE_UNKNOWN",
    "annotate_contract_exposure",
    "exposure_parity",
    "project_triad_from_chain",
]
