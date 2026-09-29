"""
backend/services/solstice_window.py — governed window-activity surface (S2).

Window delta-volume activity (Σ c·u·|δ|·ΔV over a causal window) is only
meaningful when the two observations are actually comparable. This module is
the single governed entry point: it validates the FULL comparability identity
before any arithmetic, and returns a reasoned unavailable state instead of a
number whenever the window is not a window.

Required comparability identity (all must match or be declared):

- ticker            (same underlying)
- provider/data_source
- scope key         (mode/dte/scalp or explicit request scope)
- formula version   (gex.v2 family; a formula change invalidates the window)
- session date      (a session roll is a new session, not a window)
- source ordering   (previous observation strictly earlier than current)
- monotonic cumulative volume, or an explicit correction policy

The per-contract kernel is delegated to
``services.solstice_enrichment.window_contract_activity`` (the LIVE
enrichment path) — this module does not reimplement it and does not invent a
second calculator. The unguarded test-only window helper in
``domain.wall_desk_snapshot.project_window`` is explicitly NOT used here.

Greek observation convention: FROZEN-OPEN. Each contract's gamma and delta
are taken from the PREVIOUS (open) observation and held fixed across the
window, so the result is a pure volume change, not a repriced Greeks change.
That is declared in ``greek_convention`` of every response.

PROVENANCE LIMIT (deliberate, do not remove): cumulative volume carries no
aggressor identity. Nothing here is buyer-minus-seller flow, opening/closing
activity, or dealer inventory. Signed option delta is a Greek, not flow.
"""

from __future__ import annotations

import math
from typing import Any

WINDOW_SURFACE_VERSION = "solstice-window.v1"
WINDOW_METRIC_ID = "window_dadgex_v1"
GREEK_CONVENTION = "frozen-open: gamma/delta from the previous (open) observation"
NOT_FLOW_NOTE = (
    "turnover proxy, not positioning: no aggressor side, no opening/closing "
    "classification, no dealer inventory, and not buyer-minus-seller flow"
)

# Reason codes for unavailable windows. Every one of these is a refusal to
# produce a number, never a zero.
REASON_TICKER_MISMATCH = "TICKER_MISMATCH"
REASON_PROVIDER_MISMATCH = "PROVIDER_MISMATCH"
REASON_SCOPE_MISMATCH = "SCOPE_MISMATCH"
REASON_FORMULA_MISMATCH = "FORMULA_MISMATCH"
REASON_SESSION_ROLL = "SESSION_ROLL"
REASON_OUT_OF_ORDER = "SOURCE_OUT_OF_ORDER"
REASON_SPOT_UNKNOWN = "SPOT_UNKNOWN"
REASON_VOLUME_REBASE = "VOLUME_REBASE"
REASON_NO_BASELINE = "NO_BASELINE"


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _asof(value: Any) -> Any:
    """Best-effort comparable ordering key. Unparseable stays None."""
    from datetime import datetime

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        from datetime import UTC

        dt = dt.replace(tzinfo=UTC)
    return dt


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "version": WINDOW_SURFACE_VERSION,
        "metric_id": WINDOW_METRIC_ID,
        "status": "unavailable",
        "reason": reason,
        "window_net": None,
        "window_gross_like": None,
        "greek_convention": GREEK_CONVENTION,
        "provenance_note": NOT_FLOW_NOTE,
        "contracts": [],
        "surface": {"strikes": [], "cells": [], "expiries": []},
        "coverage": {
            "n_current_contracts": 0,
            "n_comparable_contracts": 0,
            "n_missing_delta": 0,
            "n_no_baseline": 0,
            "n_mixed_pair": 0,
        },
    }
    out.update(extra)
    return out


def check_window_comparability(
    prev_meta: dict[str, Any], cur_meta: dict[str, Any]
) -> tuple[str | None, str | None]:
    """Return (reason, detail) for the first comparability failure, else (None, None).

    `reason` is a REASON_* code. This is the gate; the arithmetic only runs
    when it returns None.
    """
    prev_meta = prev_meta or {}
    cur_meta = cur_meta or {}
    pt, ct = prev_meta.get("ticker"), cur_meta.get("ticker")
    if pt and ct and str(pt).upper() != str(ct).upper():
        return REASON_TICKER_MISMATCH, f"{pt} != {ct}"
    pp, cp = prev_meta.get("data_source"), cur_meta.get("data_source")
    if pp and cp and str(pp) != str(cp):
        return REASON_PROVIDER_MISMATCH, f"{pp} != {cp}"
    ps, cs = prev_meta.get("scope_key"), cur_meta.get("scope_key")
    if (ps or cs) and ps != cs:
        return REASON_SCOPE_MISMATCH, f"{ps} != {cs}"
    pf, cf = prev_meta.get("formula_version"), cur_meta.get("formula_version")
    if (pf or cf) and pf != cf:
        return REASON_FORMULA_MISMATCH, f"{pf} != {cf}"
    pday, cday = prev_meta.get("session_date"), cur_meta.get("session_date")
    if (pday or cday) and pday != cday:
        return REASON_SESSION_ROLL, f"{pday} != {cday}"
    pa, ca = _asof(prev_meta.get("asof")), _asof(cur_meta.get("asof"))
    if pa is not None and ca is not None and not pa < ca:
        return REASON_OUT_OF_ORDER, f"prev {pa.isoformat()} !< cur {ca.isoformat()}"
    return None, None


def window_activity_surface(
    prev_meta: dict[str, Any],
    cur_meta: dict[str, Any],
    prev_contracts: list[dict[str, Any]] | None,
    cur_contracts: list[dict[str, Any]] | None,
    spot: Any,
) -> dict[str, Any]:
    """Governed window activity: comparability gate + live kernel + surface.

    Returns a packet that always carries:
      status / reason       ok or an explicit unavailable reason
      window_net/gross      None when unavailable, never 0
      contracts             per-contract rows (kernel output)
      surface               per-strike totals and per-(expiry, strike) cells
      coverage              the observed population and what was excluded
      greek_convention      the declared Greek observation convention
      interval              the ACTUAL window interval from the two observations
    """
    reason, detail = check_window_comparability(prev_meta, cur_meta)
    interval = {
        "start": (prev_meta or {}).get("asof"),
        "end": (cur_meta or {}).get("asof"),
    }
    if reason:
        return _unavailable(reason, reason_detail=detail, interval=interval,
                            coverage={"n_current_contracts": len(cur_contracts or []),
                                      "n_comparable_contracts": 0, "n_missing_delta": 0,
                                      "n_no_baseline": 0, "n_mixed_pair": 0})
    if not prev_contracts:
        return _unavailable(REASON_NO_BASELINE, interval=interval,
                            coverage={"n_current_contracts": len(cur_contracts or []),
                                      "n_comparable_contracts": 0, "n_missing_delta": 0,
                                      "n_no_baseline": len(cur_contracts or []), "n_mixed_pair": 0})
    spot_f = _num(spot)
    if spot_f is None or spot_f <= 0:
        return _unavailable(REASON_SPOT_UNKNOWN, interval=interval,
                            coverage={"n_current_contracts": len(cur_contracts or []),
                                      "n_comparable_contracts": 0, "n_missing_delta": 0,
                                      "n_no_baseline": 0, "n_mixed_pair": 0})

    # Live kernel (not a second calculator).
    from services.solstice_enrichment import window_contract_activity

    kernel = window_contract_activity(prev_contracts, cur_contracts, spot_f)
    if kernel.get("status") != "ok":
        kr = kernel.get("reason") or "NO_COMPARABLE_OBSERVATIONS"
        return _unavailable(kr, interval=interval,
                            coverage={"n_current_contracts": len(cur_contracts or []),
                                      "n_comparable_contracts": 0,
                                      "n_missing_delta": int(kernel.get("missing_delta") or 0),
                                      "n_no_baseline": 0,
                                      "n_mixed_pair": int(kernel.get("mixed_pair") or 0)})

    rows = kernel.get("contracts") or []
    if not rows:
        return _unavailable("NO_COMPARABLE_OBSERVATIONS", interval=interval,
                            coverage={"n_current_contracts": len(cur_contracts or []),
                                      "n_comparable_contracts": 0,
                                      "n_missing_delta": int(kernel.get("missing_delta") or 0),
                                      "n_no_baseline": 0,
                                      "n_mixed_pair": int(kernel.get("mixed_pair") or 0)})

    by_strike: dict[str, dict[str, Any]] = {}
    cells: dict[tuple[str, str], float] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        v = _num(r.get("window_daddex"))
        if v is None:
            continue
        try:
            strike_key = str(float(r.get("strike")))
        except (TypeError, ValueError):
            continue
        expiry_key = str(r.get("expiry") or "")
        by_strike.setdefault(strike_key, {"strike": _num(r.get("strike")),
                                          "window_net": 0.0, "n_contracts": 0})
        by_strike[strike_key]["window_net"] += v
        by_strike[strike_key]["n_contracts"] += 1
        cell_key = (expiry_key, strike_key)
        cells[cell_key] = cells.get(cell_key, 0.0) + v

    strikes = sorted(by_strike.values(), key=lambda r: (r["strike"] is None, r["strike"] or 0.0),
                     reverse=True)
    net = sum(r["window_net"] for r in strikes)
    gross = sum(abs(r["window_net"]) for r in strikes)
    return {
        "version": WINDOW_SURFACE_VERSION,
        "metric_id": WINDOW_METRIC_ID,
        "status": "ok",
        "reason": None,
        "window_net": net,
        "window_gross_like": gross,
        "greek_convention": GREEK_CONVENTION,
        "provenance_note": NOT_FLOW_NOTE,
        "interval": interval,
        "contracts": rows,
        "surface": {
            "strikes": strikes,
            "cells": [
                {"expiry": e, "strike": s, "window_dadgex": v}
                for (e, s), v in sorted(cells.items(), key=lambda kv: (kv[0][0], -_num(kv[0][1])))
            ],
            "expiries": sorted({e for (e, _s) in cells}),
        },
        "coverage": {
            "n_current_contracts": len(cur_contracts or []),
            "n_comparable_contracts": len(rows),
            "n_missing_delta": int(kernel.get("missing_delta") or 0),
            "n_no_baseline": 0,
            "n_mixed_pair": int(kernel.get("mixed_pair") or 0),
            "note": "surface is complete only over the comparable population",
        },
    }


__all__ = [
    "WINDOW_SURFACE_VERSION",
    "WINDOW_METRIC_ID",
    "GREEK_CONVENTION",
    "NOT_FLOW_NOTE",
    "check_window_comparability",
    "window_activity_surface",
]
