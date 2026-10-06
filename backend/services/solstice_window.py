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

import json
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
# Fail-closed: an identity field that is absent on either side is UNDECLARED,
# not equal. "Unknown scope" was previously treated as "matching scope",
# which let an undeclared window through.
REASON_IDENTITY_UNDECLARED = "IDENTITY_UNDECLARED"

# The full comparability identity. Every field must be declared on BOTH
# sides and must match. Order matters: an undeclared field is reported
# before any mismatch, because a mismatch cannot be evaluated without it.
IDENTITY_FIELDS = (
    ("ticker", REASON_TICKER_MISMATCH),
    ("data_source", REASON_PROVIDER_MISMATCH),
    ("scope_key", REASON_SCOPE_MISMATCH),
    ("formula_version", REASON_FORMULA_MISMATCH),
    ("session_date", REASON_SESSION_ROLL),
)


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

    FAIL-CLOSED. Every identity field must be DECLARED on both sides and
    must match. An absent field is not a match: the previous version skipped
    the check whenever either side was falsy, so a window with no declared
    ticker, provider, scope, formula or session sailed through and produced
    a number. Undeclared is now `IDENTITY_UNDECLARED` naming the field.

    This is the gate; the arithmetic only runs when it returns None.
    """
    prev_meta = prev_meta or {}
    cur_meta = cur_meta or {}
    for field, mismatch_reason in IDENTITY_FIELDS:
        pv, cv = prev_meta.get(field), cur_meta.get(field)
        if pv is None or not str(pv).strip() or cv is None or not str(cv).strip():
            return REASON_IDENTITY_UNDECLARED, f"{field} is undeclared on one or both sides"
        if field == "ticker":
            same = str(pv).upper() == str(cv).upper()
        else:
            same = str(pv) == str(cv)
        if not same:
            return mismatch_reason, f"{field}: {pv} != {cv}"
    pa, ca = _asof(prev_meta.get("asof")), _asof(cur_meta.get("asof"))
    if pa is None or ca is None:
        return REASON_IDENTITY_UNDECLARED, "asof is unparseable or absent on one side"
    if not pa < ca:
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
                                      "n_no_baseline": int(kernel.get("no_baseline") or 0),
                                      "n_missing_volume": int(kernel.get("missing_volume") or 0),
                                      "n_invalid_delta": int(kernel.get("invalid_delta") or 0),
                                      "n_mixed_pair": int(kernel.get("mixed_pair") or 0)})

    rows = kernel.get("contracts") or []
    if not rows:
        return _unavailable("NO_COMPARABLE_OBSERVATIONS", interval=interval,
                            coverage={"n_current_contracts": len(cur_contracts or []),
                                      "n_comparable_contracts": 0,
                                      "n_missing_delta": int(kernel.get("missing_delta") or 0),
                                      "n_no_baseline": int(kernel.get("no_baseline") or 0),
                                      "n_missing_volume": int(kernel.get("missing_volume") or 0),
                                      "n_invalid_delta": int(kernel.get("invalid_delta") or 0),
                                      "n_mixed_pair": int(kernel.get("mixed_pair") or 0),
                                      "n_invalid": int(kernel.get("invalid") or 0),
                                      "n_invalid_type": int(kernel.get("invalid_type") or 0)})

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
        "exclusions": kernel.get("exclusions") or [],
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
            "n_no_baseline": int(kernel.get("no_baseline") or 0),
            "n_missing_volume": int(kernel.get("missing_volume") or 0),
            "n_invalid_delta": int(kernel.get("invalid_delta") or 0),
            "n_mixed_pair": int(kernel.get("mixed_pair") or 0),
            # R11-H01: typed/nonfinite exclusions are counted, not dropped.
            "n_invalid": int(kernel.get("invalid") or 0),
            "n_invalid_type": int(kernel.get("invalid_type") or 0),
            "note": "surface is complete only over the comparable population",
        },
    }


def window_observation(payload):
    """Declared source clock/scope identity, not a build-time replacement clock."""
    from zoneinfo import ZoneInfo

    from services.agent.contracts import instant
    from services.agent.display_map import map_cache_key

    try:
        ticker, query = payload.get("ticker"), payload.get("map_query")
        key = map_cache_key(ticker, query)
        event, received, available = (instant(payload.get(k)) for k in ("event_time", "fetched_at", "asof"))
        if not all((event, received, available)):
            return None, "IDENTITY_UNDECLARED"
        if _asof(event) > _asof(received) or _asof(received) > _asof(available):
            return None, "SOURCE_CLOCK_INVALID"
        return dict(ticker=ticker, data_source=payload.get("data_source"), scope_key=key,
                    formula_version=payload.get("formula_version"), map_query=query,
                    session_date=_asof(event).astimezone(ZoneInfo("America/New_York")).date().isoformat(),
                    asof=event, received_at=received, available_at=available), None
    except (TypeError, ValueError):
        return None, "IDENTITY_UNDECLARED"


def recorded_window_activity(previous, current, spot):
    """One stored baseline plus current producer inputs, frozen by its recorder."""
    if not previous or not previous.get("snapshot"):
        return _unavailable("NO_BASELINE")
    snap = previous["snapshot"]
    display = (previous.get("context") or {}).get("display") or {}
    before = {**display, "ticker": snap.get("ticker"), "data_source": snap.get("data_source"),
              "formula_version": snap.get("formula_version"), "asof": snap.get("asof_ts")}
    pmeta, preason = window_observation(before)
    cmeta, creason = window_observation(current)
    if preason or creason:
        return _unavailable(preason or creason)
    reason, detail = check_window_comparability(pmeta, cmeta)
    if reason:
        return _unavailable(reason, reason_detail=detail)
    if not _asof(pmeta["available_at"]) < _asof(cmeta["available_at"]):
        return _unavailable("AVAILABLE_AT_CONFLICT")
    coverage = previous.get("coverage") or {}
    stored = previous.get("contracts") or []
    try:
        rows = [json.loads(r.get("window_inputs_json")) for r in stored]
    except (TypeError, ValueError):
        return _unavailable("WINDOW_CONTRACT_INPUTS_UNAVAILABLE")
    if (coverage.get("truncated") is not False or coverage.get("returned") != coverage.get("requested")
            or coverage.get("returned") != len(rows)):
        return _unavailable("BASELINE_POPULATION_PARTIAL")
    if not rows or any(not isinstance(r, dict) for r in rows):
        return _unavailable("WINDOW_CONTRACT_INPUTS_UNAVAILABLE")
    packet = window_activity_surface(pmeta, cmeta, rows, current.get("contracts"), spot)
    packet["comparison"] = {"previous_snapshot_id": snap.get("snapshot_id"), "previous": pmeta, "current": cmeta,
                            "volume_correction_policy": "refuse-retraction"}
    return packet


__all__ = [
    "WINDOW_SURFACE_VERSION",
    "WINDOW_METRIC_ID",
    "GREEK_CONVENTION",
    "NOT_FLOW_NOTE",
    "check_window_comparability",
    "window_activity_surface",
]
