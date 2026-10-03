"""backend/services/solstice_range_analytics.py — C1 bounded analytical range producer.

Contract ``range-analytics.v1`` (docs/solstice/r18/CLINE_RANGE_ANALYTICS_V1.md).
This is the OWNING 14–60 DTE analytical map: a bounded request selects the
listed expiries inside the requested min/max DTE window as of the owning
America/New_York date, then reuses the registered analytical kernels
(services.gex_core grids — display-GEX S² default, OI_DELTA_WEIGHTED and
VOLUME surfaces stay distinct; the window surface needs a recorded baseline
and is unavailable until then, never zero-filled).

Truthfulness rules enforced here (r18 rejection criteria):
  * The existing coverage-read.v1 listing is a LISTING verdict, not this map;
    that route is untouched.
  * Reversed windows refuse REVERSED_WINDOW. Expired/unparseable/unlisted
    expiries are never admitted; zero admitted expiries refuse
    NO_ADMITTED_EXPIRY.
  * A caller-supplied historical/future ``as_of`` refuses SESSION_DATE_MISMATCH
    — a current quote/Greeks fetch can never recreate a past observation.
  * Coverage is "complete" ONLY when the actual vendor listing observed BOTH
    window edges and every admitted expiry returned without skips. A count cap,
    a first-N listing or an edge heuristic alone never proves completeness.
  * Missing OI/Greeks stay missing: cells are explicit nulls, excluded
    populations are counted, never zero-filled, never volume-substituted.
  * Record identity (symbol, window, owning NY date, source clocks, canonical
    content digest) binds cache and persistence; another ticker/date/window/
    basis cannot reuse a mismatched grid.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

CONTRACT_VERSION = "range-analytics.v1"
ET = ZoneInfo("America/New_York")

# Additive analytical window bounds for THIS producer only. They do not alter
# the existing optional analytical routes' `dte le=30` display envelope (a
# separate, deliberate constraint that stays untouched).
MIN_DTE_LIMIT = 0
MAX_DTE_LIMIT = 365

# Registered metric identities (solstice_metric_contract / gex.v2). The raw
# display surface is the S² default grid (BS gamma from IV); the delta/volume
# surfaces are vendor-gamma grids — different bases, never interchangeable.
_UNIT_S2 = "USD per 1% spot move (S^2 dealer-positive convention)"

__all__ = [
    "CONTRACT_VERSION",
    "MIN_DTE_LIMIT",
    "MAX_DTE_LIMIT",
    "build_range_envelope",
    "fetch_range_analytics",
    "select_window_expiries",
    "ny_today",
]


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _strike_key(strike: Any) -> str | None:
    """Same encoding as gex_core._k / solstice_metric_contract._strike_key."""
    if strike is None or isinstance(strike, bool):
        return None
    try:
        f = float(strike)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or f <= 0:
        return None
    return str(int(f)) if f.is_integer() else str(f)


def ny_today(now_utc: datetime | None = None) -> date:
    """Owning America/New_York session date for the window arithmetic."""
    return (now_utc or datetime.now(UTC)).astimezone(ET).date()


def select_window_expiries(
    listed: list[Any] | None,
    min_dte: int,
    max_dte: int,
    asof: date,
) -> dict[str, Any]:
    """Pure bounded selection over the ACTUAL vendor listing (no first-N slice).

    Verdict vocabulary matches coverage-read.v1 so the two surfaces stay
    compatible and distinct: EXPIRED / BELOW_WINDOW / ABOVE_WINDOW /
    UNPARSEABLE_EXPIRY / ADMITTED.
    """
    rows: list[dict[str, Any]] = []
    for raw in listed or []:
        text = str(raw)
        try:
            exp_date = datetime.strptime(text[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            rows.append({"expiry": text, "dte": None, "admitted": False,
                         "reason": "UNPARSEABLE_EXPIRY"})
            continue
        dte = (exp_date - asof).days
        if dte < 0:
            verdict, reason = False, "EXPIRED"
        elif dte < min_dte:
            verdict, reason = False, "BELOW_WINDOW"
        elif dte > max_dte:
            verdict, reason = False, "ABOVE_WINDOW"
        else:
            verdict, reason = True, "ADMITTED"
        rows.append({"expiry": exp_date.isoformat(), "dte": dte,
                     "admitted": verdict, "reason": reason})
    admitted = sorted((r for r in rows if r["admitted"] and r["dte"] is not None),
                      key=lambda r: r["dte"])
    return {
        "rows": rows,
        "admitted": [{"expiry": r["expiry"], "dte": r["dte"]} for r in admitted],
        "n_listed": len(rows),
        "n_admitted": len(admitted),
        "n_expired": sum(1 for r in rows if r["reason"] == "EXPIRED"),
        "n_unparseable": sum(1 for r in rows if r["reason"] == "UNPARSEABLE_EXPIRY"),
        "lower_edge_observed": any(r["dte"] is not None and r["dte"] < min_dte for r in rows),
        "upper_edge_observed": any(r["dte"] is not None and r["dte"] > max_dte for r in rows),
    }


def _dense_section(
    name: str,
    metric_id: str,
    kernel: dict[str, Any],
    model: str,
    admitted_expiries: list[str],
    strike_keys: list[str],
) -> dict[str, Any]:
    """Dense {expiry: {strike_key: value|null}} cells over the OWNING axes.

    An admitted expiry with zero kernel cells still gets a full null row —
    unavailable values are explicit, never absent and never zero.
    """
    grid = kernel.get("grid") or {}
    cells: dict[str, dict[str, Any]] = {}
    n_available = 0
    for exp in admitted_expiries:
        row = grid.get(exp) or {}
        dense_row: dict[str, Any] = {}
        for key in strike_keys:
            v = row.get(key)
            ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            dense_row[key] = float(v) if ok else None
            n_available += 1 if ok else 0
        cells[exp] = dense_row
    n_cells = len(admitted_expiries) * len(strike_keys)
    if n_available == 0:
        status = "unavailable"
        reason = kernel.get("reason") or "NO_COVERAGE"
    elif kernel.get("status") == "unavailable":
        status = "unavailable"
        reason = kernel.get("reason")
    elif n_available < n_cells:
        status = "partial"
        reason = None
    else:
        status = "ok"
        reason = None
    section: dict[str, Any] = {
        "metric_id": metric_id,
        "basis": kernel.get("exposure_basis"),
        "formula_version": kernel.get("formula_version") or "gex.v2",
        "model": model,
        "unit": _UNIT_S2,
        "status": status,
        "reason": reason,
        "usable": kernel.get("usable", n_available if status != "unavailable" else 0),
        "n_cells": n_cells,
        "n_available": n_available,
        "cells": cells,
    }
    # Registered exclusion populations pass through verbatim — missing
    # (unknown) stays distinct from invalid (unusable), quarantined, or
    # invalid-multiplier populations.
    for key in ("missing_delta", "invalid_delta", "invalid_mult", "quarantined",
                "invalid_type", "cell_missing_delta", "cell_invalid_delta",
                "missing_volume"):
        if key in kernel:
            section[key] = kernel[key]
    return section


def _refusal(symbol: str, min_dte: int, max_dte: int, asof: date,
             reasons: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "version": CONTRACT_VERSION,
        "status": "refused",
        "refusals": reasons,
        "symbol": symbol,
        "record_id": None,
        "content_digest": None,
        "query": {"min_dte": min_dte, "max_dte": max_dte, "as_of_ny": asof.isoformat()},
        **extra,
    }



def build_range_envelope(
    *,
    symbol: str,
    min_dte: int,
    max_dte: int,
    asof: date,
    listing: dict[str, Any],
    selection: dict[str, Any],
    chain: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the owning range-analytics.v1 envelope from a bounded chain.

    Pure function of its arguments — every deterministic fixture drives it
    without network. Kernels are the registered services.gex_core surfaces;
    nothing here recomputes or relabels an exposure.
    """
    from services.gex_core import (
        compute_gex_grid,
        compute_gex_grid_delta_weighted,
        compute_gex_grid_volume_vendor,
    )

    admitted = [a["expiry"] for a in selection["admitted"]]
    contracts = [c for c in (chain.get("contracts") or []) if isinstance(c, dict)]
    spot = chain.get("spot")
    spot_ok = isinstance(spot, (int, float)) and not isinstance(spot, bool) \
        and math.isfinite(spot) and spot > 0

    strike_keys: list[str] = []
    if spot_ok:
        seen: set[str] = set()
        for c in contracts:
            k = _strike_key(c.get("strike"))
            if k is not None:
                seen.add(k)
        strike_keys = sorted(seen, key=float)

    if spot_ok and contracts:
        kernels: dict[str, tuple[str, dict[str, Any], str]] = {
            "raw_oi": ("gex_net_v1",
                       {**compute_gex_grid(spot, contracts, symbol),
                        "exposure_basis": "OI"},  # registered display basis
                       "black_scholes_gamma(display S^2)"),
            "delta_weighted": ("dadgex_net_v1",
                               compute_gex_grid_delta_weighted(spot, contracts),
                               "vendor_gamma(|delta|)"),
            "volume": ("volume_gamma_v1",
                       compute_gex_grid_volume_vendor(spot, contracts),
                       "vendor_gamma(session volume)"),
        }
    else:
        empty = {"expiries": [], "strikes": [], "grid": {}, "formula_version": "gex.v2",
                 "status": "unavailable", "reason": "NO_SPOT_OR_CONTRACTS"}
        kernels = {
            "raw_oi": ("gex_net_v1", {**empty, "exposure_basis": "OI"},
                       "black_scholes_gamma(display S^2)"),
            "delta_weighted": ("dadgex_net_v1",
                               {**empty, "exposure_basis": "OI_DELTA_WEIGHTED"},
                               "vendor_gamma(|delta|)"),
            "volume": ("volume_gamma_v1", {**empty, "exposure_basis": "VOLUME"},
                       "vendor_gamma(session volume)"),
        }
    # Window (session/window volume-adjusted) needs a comparable RECORDED
    # baseline; without it the surface is explicitly unavailable, never raw
    # and never zero — same rule as the display payload's governed section.
    kernels["window"] = ("window_dadgex_v1", {
        "expiries": [], "strikes": [], "grid": {}, "exposure_basis": "VOLUME_WINDOW",
        "formula_version": "gex.v2", "status": "unavailable",
        "reason": "HISTORY_NOT_YET_RECORDED"}, "recorded baseline required")

    grids = {name: _dense_section(name, metric_id, kernel, model, admitted, strike_keys)
             for name, (metric_id, kernel, model) in kernels.items()}
    metric_registry = {name: {"metric_id": metric_id,
                              "basis": grids[name]["basis"],
                              "formula_version": grids[name]["formula_version"],
                              "model": model,
                              "unit": _UNIT_S2}
                       for name, (metric_id, _kernel, model) in kernels.items()}

    skipped = [s for s in (chain.get("skipped") or []) if isinstance(s, dict)]
    n_returned = len([e for e in (chain.get("expiries") or []) if e in admitted])
    edges_ok = selection["lower_edge_observed"] and selection["upper_edge_observed"]
    listing_capped = bool(listing.get("listing_capped"))
    complete = bool(
        admitted
        and not skipped
        and not listing_capped
        and edges_ok
        and n_returned == len(admitted)
    )
    coverage = {
        "requested_window": {"min_dte": min_dte, "max_dte": max_dte},
        "n_listed": selection["n_listed"],
        "n_admitted": selection["n_admitted"],
        "n_returned_expiries": n_returned,
        "n_skipped_expiries": len(skipped),
        "skipped": skipped,
        "n_contracts": len(contracts),
        "n_expired_dropped": chain.get("n_expired_dropped"),
        "attempt_cap": chain.get("attempt_cap"),
        "budget": {"pre_debit": chain.get("budget_pre_debit"),
                   "note": "2 + admitted-expiry shared Public request envelope "
                           "(adapter C8 all-or-nothing debit)"},
        "listing_verdicts": selection["rows"],
        "listing_capped": listing_capped,
        "lower_edge_observed": selection["lower_edge_observed"],
        "upper_edge_observed": selection["upper_edge_observed"],
        # Completeness requires BOTH listing edges observed AND every admitted
        # expiry returned. Anything less is exposed as partial, never implied.
        "complete": complete,
        "complete_reason": (None if complete else
                            "SKIPPED_EXPIRIES" if skipped else
                            "LISTING_CAPPED_WINDOW_MAY_EXTEND" if listing_capped else
                            "WINDOW_EDGE_NOT_OBSERVED" if not edges_ok else
                            "RETURNED_LT_ADMITTED"),
    }

    oi_dates = sorted({str(c["oi_effective_date"]) for c in contracts
                       if c.get("oi_effective_date")})
    greeks_sources = sorted({str(c["greeks_source"]) for c in contracts
                             if c.get("greeks_source")})
    clocks = {
        "received_at": chain.get("received_at"),
        "fetched_at": chain.get("fetched_at"),
        # Public supplies no whole-chain OI/Greeks observation timestamp.
        "chain_event_time": chain.get("event_time"),
        "spot": {"price": spot if spot_ok else None,
                 "source": chain.get("spot_source"),
                 "event_time": chain.get("spot_event_time"),
                 "fetched_at": chain.get("spot_fetched_at")},
        "bid_timestamps_present": sum(1 for c in contracts if c.get("bid_timestamp")),
        "ask_timestamps_present": sum(1 for c in contracts if c.get("ask_timestamp")),
        "oi_effective_dates": oi_dates or None,
        "oi_date_note": "per-contract vendor OI effective dates; absent means unknown",
    }
    provenance = {
        "data_source": chain.get("data_source"),
        "stale": bool(chain.get("stale", False)),
        "adapter": "public_api_adapter.fetch_chain_for_expiries",
        "greeks_sources": greeks_sources or None,
        "chain_instrument_type": chain.get("chain_instrument_type"),
    }

    refusals: list[str] = []
    if provenance["stale"]:
        refusals.append("STALE_CACHE")
    if skipped or not complete:
        refusals.append("PARTIAL_COVERAGE")
    status = "ok" if complete and not provenance["stale"] else "partial"

    # Owning record identity binds symbol, window, owning NY date, source
    # clocks and the canonical grid content — a different ticker/date/window/
    # basis can never reuse this grid.
    identity = {
        "version": CONTRACT_VERSION,
        "symbol": symbol,
        "window": {"min_dte": min_dte, "max_dte": max_dte},
        "as_of_ny": asof.isoformat(),
        "received_at": clocks["received_at"],
        "axes": {"expiries": admitted, "strike_keys": strike_keys},
        "grids_digest": _sha(_canonical({
            name: {"metric_id": sec["metric_id"], "basis": sec["basis"],
                   "formula_version": sec["formula_version"], "cells": sec["cells"]}
            for name, sec in grids.items()})),
    }
    content_digest = _sha(_canonical(identity))
    record_id = "rga1-" + content_digest[:24]

    return {
        "version": CONTRACT_VERSION,
        "status": status,
        "refusals": refusals,
        "symbol": symbol,
        "record_id": record_id,
        "content_digest": content_digest,
        "query": {"min_dte": min_dte, "max_dte": max_dte, "as_of_ny": asof.isoformat()},
        "axes": {"expiries": selection["admitted"], "strike_keys": strike_keys,
                 "n_strikes": len(strike_keys)},
        "grids": grids,
        "metric_registry": metric_registry,
        "clocks": clocks,
        "coverage": coverage,
        "provenance": provenance,
        "synthetic": bool(chain.get("synthetic")),
    }


async def fetch_range_analytics(
    ticker: str,
    min_dte: int = 14,
    max_dte: int = 60,
    *,
    as_of: str | None = None,
    listing_fetcher: Callable[[str], Awaitable[dict[str, Any] | None]] | None = None,
    window_fetcher: Callable[[str, list[str]], Awaitable[dict[str, Any] | None]] | None = None,
    now_utc: datetime | None = None,
    persist_conn: Any | None = None,
) -> dict[str, Any]:
    """Bounded owning analytical range request (range-analytics.v1).

    Default fetchers are the additive adapter seams; tests inject deterministic
    fakes. ``persist_conn`` is explicit opt-in — the read path performs no
    recorder writes unless a store is supplied.
    """
    symbol = str(ticker or "").strip().upper()
    if symbol == "SPX":
        symbol = "^SPX"
    if min_dte > max_dte:
        return _refusal(symbol, min_dte, max_dte, ny_today(now_utc),
                        ["REVERSED_WINDOW"])
    if min_dte < MIN_DTE_LIMIT or max_dte > MAX_DTE_LIMIT:
        return _refusal(symbol, min_dte, max_dte, ny_today(now_utc),
                        ["WINDOW_OUT_OF_RANGE"])
    today = ny_today(now_utc)
    if as_of is not None:
        try:
            requested = datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return _refusal(symbol, min_dte, max_dte, today, ["UNPARSEABLE_AS_OF"])
        if requested != today:
            # A current chain fetch can never recreate a historical observation.
            return _refusal(symbol, min_dte, max_dte, today,
                            ["SESSION_DATE_MISMATCH"],
                            requested_as_of=requested.isoformat())

    if listing_fetcher is None:
        from services.public_api_adapter import fetch_option_expiry_listing
        listing_fetcher = fetch_option_expiry_listing
    listing = await listing_fetcher(symbol)
    if not isinstance(listing, dict) or not listing.get("expiries"):
        return _refusal(symbol, min_dte, max_dte, today, ["VENDOR_UNAVAILABLE"],
                        detail="expiry listing unavailable — key missing or vendor call failed")
    selection = select_window_expiries(listing.get("expiries"), min_dte, max_dte, today)
    if not selection["admitted"]:
        return _refusal(symbol, min_dte, max_dte, today, ["NO_ADMITTED_EXPIRY"],
                        coverage={"n_listed": selection["n_listed"],
                                  "listing_verdicts": selection["rows"]})

    if window_fetcher is None:
        from services.public_api_adapter import fetch_chain_for_expiries
        window_fetcher = fetch_chain_for_expiries
    admitted_dates = [a["expiry"] for a in selection["admitted"]]
    chain = await window_fetcher(symbol, admitted_dates)
    if not isinstance(chain, dict):
        return _refusal(symbol, min_dte, max_dte, today, ["CHAIN_UNAVAILABLE"],
                        coverage={"n_listed": selection["n_listed"],
                                  "n_admitted": selection["n_admitted"],
                                  "listing_verdicts": selection["rows"]})
    if not chain.get("contracts"):
        return _refusal(symbol, min_dte, max_dte, today, ["NO_CONTRACTS"],
                        coverage={"n_listed": selection["n_listed"],
                                  "n_admitted": selection["n_admitted"],
                                  "skipped": chain.get("skipped") or [],
                                  "listing_verdicts": selection["rows"]})

    envelope = build_range_envelope(
        symbol=symbol, min_dte=min_dte, max_dte=max_dte, asof=today,
        listing=listing, selection=selection, chain=chain)

    if persist_conn is not None:
        from services.heatmap_history import record_range_envelope
        try:
            envelope["persistence"] = record_range_envelope(persist_conn, envelope)
        except Exception as exc:  # required write failure stays visible
            log.warning("range envelope persist failed: %s", exc)
            envelope["persistence"] = {"status": "refused",
                                       "reason": "STORE_WRITE_FAILED",
                                       "detail": str(exc)}
    return envelope
