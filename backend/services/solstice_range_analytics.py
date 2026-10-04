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
    "CONTENT_SCHEMA",
    "EXCLUDED_FROM_CONTENT",
    "MIN_DTE_LIMIT",
    "MAX_DTE_LIMIT",
    "build_range_envelope",
    "canonical_content",
    "compute_content_digest",
    "fetch_range_analytics",
    "record_id_for_digest",
    "select_window_expiries",
    "ny_today",
]


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── R18-C6: canonical content contract ──────────────────────────────
# The evidence content digest covers the COMPLETE analytical evidence:
# axes, dense cells, metric identity (basis/formula/unit/model/status/
# population), the derived metrics summary, clocks, coverage, provenance,
# synthetic flag, query and status. Explicitly EXCLUDED transport/storage
# fields (never part of content identity): the record id/digest themselves,
# the persistence receipt block, and remarks written after capture.
#
# rga-content.v3 (R18-C11, consumer review): the top-level `metrics`
# admitted/partial/unavailable summary joined the digest subject — under
# v2 a tampered summary (e.g. a partial metric relabeled admitted) kept
# a valid digest. v2 payloads are refused INCOMPATIBLE_CONTENT_SCHEMA,
# never silently upgraded; v2 fixture digests are recorded superseded.
CONTENT_SCHEMA = "rga-content.v3"
_CONTENT_KEYS = (
    "version", "status", "refusals", "symbol", "query", "axes", "grids",
    "metric_registry", "metrics", "clocks", "coverage", "provenance",
    "synthetic", "grounding", "content_schema",
)
EXCLUDED_FROM_CONTENT = ("record_id", "content_digest", "persistence")


def canonical_content(envelope: dict[str, Any]) -> dict[str, Any]:
    """Canonical content projection (rga-content.v2) — the digest subject."""
    if not isinstance(envelope, dict):
        return {}
    return {k: envelope.get(k) for k in _CONTENT_KEYS}


def compute_content_digest(envelope: dict[str, Any]) -> str:
    return _sha(_canonical(canonical_content(envelope)))


def record_id_for_digest(digest: str) -> str:
    return f"rga1-{digest[:24]}"


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
    population: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dense {expiry: {strike_key: value|null}} cells over the OWNING axes,
    with genuine GOVERNED population accounting (R18-C7).

    ``population`` comes from the registered kernels/aggregates — raw input
    contract counts and per-reason exclusions, NOT a finite-cell recount.
    Sections with exclusions or excluded-cell gaps are ``partial``; a surface
    with zero usable inputs is ``unavailable`` with a reason. ``metric_admitted``
    is true only for a clean ``ok`` section: a finite aggregate is never
    sufficient on its own to admit a metric.
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

    pop = dict(population or {})
    # Exclusion populations only — `usable`/`input_contracts` are legitimate
    # counts, never exclusions.
    n_exclusions = sum(v for k, v in pop.items()
                       if k not in ("usable", "input_contracts", "input_known")
                       and isinstance(v, int) and not isinstance(v, bool) and v > 0)
    usable = pop.get("usable", kernel.get("usable"))
    kernel_status = kernel.get("status")
    if usable == 0 and not admitted_expiries:
        status = "unavailable"
        reason = kernel.get("reason") or "NO_COVERAGE"
    elif usable == 0 and kernel_status == "unavailable" or usable is not None and usable == 0:
        status = "unavailable"
        reason = kernel.get("reason") or "NO_USABLE_INPUTS"
    elif n_exclusions > 0 or n_available < n_cells:
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
        # R18-C7: a metric is admitted only when its own surface is clean;
        # the overall map status never overrides this.
        "metric_admitted": status == "ok",
        "population": pop,
        "usable": usable if usable is not None else n_available,
        "n_cells": n_cells,
        "n_available": n_available,
        "cell_gaps": n_cells - n_available,
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



def _bs_population(contracts: list[dict[str, Any]], spot: float,
                  ticker: str) -> dict[str, Any]:
    """R18-C11: kernel-CORRESPONDING population for the raw_oi surface.

    The raw surface's cells come from ``gex_core.compute_gex_grid`` — a
    Black-Scholes gamma grid computed from per-contract iv/T (vendor gamma
    is NOT an input to it, and it neither quarantines adjusted contracts
    nor uses a multiplier). This mirror walks the SAME per-contract filter
    order as that kernel's canonical Python path, counting only the first
    failing reason, so the population reports exactly the contract set
    that produced the cells. In particular: a contract missing IV is an
    EXCLUSION here (the kernel drops it — never "admitted"), and a
    contract with IV/T but no vendor gamma is USABLE here (the BS grid
    admits it — finite BS cells never say "unavailable").
    """
    from services.gex_core import DIV_YIELD, bs_gamma, option_type_sign, safe_float

    q = DIV_YIELD.get(ticker, 0.0)
    pop: dict[str, Any] = {
        "input_contracts": len(contracts or []),
        "usable": 0,
        "oi_missing_or_nonpositive": 0,
        "iv_missing_or_nonpositive": 0,
        "t_missing_or_nonpositive": 0,
        "strike_invalid": 0,
        "expiry_missing": 0,
        "type_unknown": 0,
        "gamma_nonpositive": 0,
    }
    for c in contracts or []:
        if not isinstance(c, dict):
            pop["type_unknown"] += 1
            continue
        if safe_float(c.get("oi")) <= 0:
            pop["oi_missing_or_nonpositive"] += 1
            continue
        if safe_float(c.get("iv")) <= 0:
            pop["iv_missing_or_nonpositive"] += 1
            continue
        if safe_float(c.get("T")) <= 0:
            pop["t_missing_or_nonpositive"] += 1
            continue
        strike = safe_float(c.get("strike"))
        if strike <= 0:
            pop["strike_invalid"] += 1
            continue
        t, iv = safe_float(c.get("T")), safe_float(c.get("iv"))
        if not (c.get("expiry") or ""):
            pop["expiry_missing"] += 1
            continue
        if option_type_sign(c.get("type")) is None:
            pop["type_unknown"] += 1
            continue
        try:
            g = bs_gamma(spot, strike, t, iv, q=q)
        except Exception:  # defensive: count as excluded, never crash the map
            pop["gamma_nonpositive"] += 1
            continue
        if g <= 0:
            pop["gamma_nonpositive"] += 1
            continue
        pop["usable"] += 1
    return pop


def _volume_missing_population(contracts: list[dict[str, Any]]) -> dict[str, int]:
    """R18-C11: mirror of the volume kernel's silent first skip.

    ``compute_gex_grid_volume_vendor`` drops contracts with no usable
    session volume without a kernel counter; count them here so the
    exclusion is visible and drives partiality instead of hiding in a
    cell gap. Quarantined contracts are already counted by the kernel.
    """
    from services.gex_core import safe_float_or_none

    missing = 0
    for c in contracts or []:
        if not isinstance(c, dict) or c.get("adjusted") or c.get("nonstandard"):
            continue
        vol = safe_float_or_none(c.get("volume", c.get("V")))
        if vol is None or vol <= 0:
            missing += 1
    return {"missing_volume": missing}


def _delta_vendor_population(contracts: list[dict[str, Any]]) -> dict[str, int]:
    """R18-C12 (C06): kernel-CORRESPONDING population for delta_weighted.

    Mirrors ``compute_gex_grid_delta_weighted``'s EXACT per-contract
    filter order — quarantined -> oi -> vendor gamma -> delta -> strike ->
    expiry -> multiplier -> type — counting only the first failing
    reason. The kernel itself reports missing/invalid delta, multiplier,
    quarantine and type counters but silently drops missing OI, missing
    vendor gamma, invalid strikes and absent expiries; those exclusions
    stay VISIBLE here (and drive partiality) even when sibling cells are
    finite (review 5979463755: 'exclusions hidden behind sibling finite
    cells/status ok').
    """
    from services.gex_core import (
        _grid_abs_delta,
        _resolve_mult,
        _vendor_gamma,
        option_type_sign,
        safe_float_or_none,
    )

    pop = {"input_contracts": len(contracts or []), "usable": 0,
           "quarantined": 0, "oi_missing_or_nonpositive": 0,
           "gamma_missing": 0, "missing_delta": 0, "invalid_delta": 0,
           "strike_invalid": 0, "expiry_missing": 0, "invalid_mult": 0,
           "invalid_type": 0}
    for c in contracts or []:
        if not isinstance(c, dict):
            pop["invalid_type"] += 1
            continue
        if c.get("adjusted") or c.get("nonstandard"):
            pop["quarantined"] += 1
            continue
        oi = safe_float_or_none(c.get("oi", c.get("open_interest")))
        if oi is None or oi <= 0:
            pop["oi_missing_or_nonpositive"] += 1
            continue
        if _vendor_gamma(c) is None:
            pop["gamma_missing"] += 1
            continue
        ad, exclusion = _grid_abs_delta(c.get("delta"))
        if ad is None:
            pop["invalid_delta" if exclusion == "invalid" else
                "missing_delta"] += 1
            continue
        strike = safe_float_or_none(c.get("strike"))
        if strike is None or strike <= 0:
            pop["strike_invalid"] += 1
            continue
        if not (c.get("expiry") or ""):
            pop["expiry_missing"] += 1
            continue
        if _resolve_mult(c) is None:
            pop["invalid_mult"] += 1
            continue
        if option_type_sign(c.get("type")) is None:
            pop["invalid_type"] += 1
            continue
        pop["usable"] += 1
    return pop


def _volume_vendor_population(contracts: list[dict[str, Any]]) -> dict[str, int]:
    """R18-C12 (C06): kernel-CORRESPONDING population for the volume grid.

    Mirrors ``compute_gex_grid_volume_vendor``'s EXACT per-contract filter
    order — quarantined -> session volume -> vendor gamma -> strike ->
    expiry -> multiplier -> type. The kernel silently drops missing-volume
    (mirrored since C11), missing-gamma, invalid-strike and absent-expiry
    contracts; every exclusion stays visible beside finite sibling cells.
    The volume kernel has no OI requirement — ``oi_missing`` never appears.
    """
    from services.gex_core import (
        _resolve_mult,
        _vendor_gamma,
        option_type_sign,
        safe_float_or_none,
    )

    pop = {"input_contracts": len(contracts or []), "usable": 0,
           "quarantined": 0, "missing_volume": 0, "gamma_missing": 0,
           "strike_invalid": 0, "expiry_missing": 0, "invalid_mult": 0,
           "invalid_type": 0}
    for c in contracts or []:
        if not isinstance(c, dict):
            pop["invalid_type"] += 1
            continue
        if c.get("adjusted") or c.get("nonstandard"):
            pop["quarantined"] += 1
            continue
        vol = safe_float_or_none(c.get("volume", c.get("V")))
        if vol is None or vol <= 0:
            pop["missing_volume"] += 1
            continue
        if _vendor_gamma(c) is None:
            pop["gamma_missing"] += 1
            continue
        strike = safe_float_or_none(c.get("strike"))
        if strike is None or strike <= 0:
            pop["strike_invalid"] += 1
            continue
        if not (c.get("expiry") or ""):
            pop["expiry_missing"] += 1
            continue
        if _resolve_mult(c) is None:
            pop["invalid_mult"] += 1
            continue
        if option_type_sign(c.get("type")) is None:
            pop["invalid_type"] += 1
            continue
        pop["usable"] += 1
    return pop


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
        # R18-C11 (consumer review): kernel-CORRESPONDING populations. Each
        # surface's population reports the counters of the kernel that
        # actually produced its cells — or, where a kernel reports none (the
        # BS grid) or skips silently (the volume kernel's missing-volume
        # drop), a mirror of that kernel's exact per-contract filter order.
        # The previous borrowed domain aggregates carried vendor-gamma
        # semantics and mis-stated the BS surface twice: a missing-IV
        # contract counted as admitted, and absent vendor gamma could zero
        # `usable` against finite BS cells. input_contracts stays the RAW
        # contract count; unknown counts remain unknown, never cell counts.
        populations: dict[str, dict[str, Any]] = {
            "raw_oi": _bs_population(contracts, spot, symbol),
            # R18-C12 (C06): kernel-order mirrors — every silent skip of
            # the vendor-gamma kernels (missing OI/gamma/strike/expiry/
            # volume) stays visible and drives partiality even when
            # sibling cells are finite; the kernel-reported counters
            # reproduce exactly (test_r6_mirror_matches_kernel_counters).
            "delta_weighted": _delta_vendor_population(contracts),
            "volume": _volume_vendor_population(contracts),
            "window": {"input_contracts": 0, "usable": 0},
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
        populations = {name: {"input_contracts": len(contracts), "usable": 0}
                       for name in kernels}
    # Window (session/window volume-adjusted) needs a comparable RECORDED
    # baseline; without it the surface is explicitly unavailable, never raw
    # and never zero — same rule as the display payload's governed section.
    kernels["window"] = ("window_dadgex_v1", {
        "expiries": [], "strikes": [], "grid": {}, "exposure_basis": "VOLUME_WINDOW",
        "formula_version": "gex.v2", "status": "unavailable",
        "reason": "HISTORY_NOT_YET_RECORDED"}, "recorded baseline required")
    if "window" not in populations:
        populations["window"] = {"input_contracts": 0, "usable": 0}

    grids = {name: _dense_section(name, metric_id, kernel, model, admitted,
                                  strike_keys, populations.get(name))
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

    # R18-C10: stable resolver/query identity + explicit contract capability.
    # Range records carry contract POPULATION and an identity digest of the
    # captured option contracts (OSI/strike/type/bid/ask/timestamps), never
    # replayable tradable quotes — historical playback is research only.
    contracts_digest = _sha(_canonical([
        {k: c.get(k) for k in ("osi", "expiry", "type", "strike", "bid", "ask",
                               "mid", "bid_timestamp", "ask_timestamp")}
        for c in contracts]))
    per_expiry: dict[str, dict[str, Any]] = {}
    for c in contracts:
        e = str(c.get("expiry") or "")
        if not e:
            continue
        row = per_expiry.setdefault(e, {"n_contracts": 0, "n_call": 0, "n_put": 0})
        row["n_contracts"] += 1
        if c.get("type") == "call":
            row["n_call"] += 1
        elif c.get("type") == "put":
            row["n_put"] += 1
    grounding = {
        "resolver": "range-resolver.v1",
        "record_query_identity": {"symbol": symbol, "min_dte": min_dte,
                                  "max_dte": max_dte, "as_of_ny": asof.isoformat()},
        "contract_population": per_expiry,
        "contracts_digest": contracts_digest,
        # Honest capability: drafting an executable contract needs OSI + live
        # quotes; this record carries reference identity only.
        "contract_drafting": {"admitted": False,
                              "reason": "RANGE_RECORD_REFERENCE_ONLY"},
    }

    # Owning record identity (rga-content.v2): the digest covers the FULL
    # canonical evidence content — axes/cells/metric identity+populations/
    # clocks/coverage/provenance/synthetic/query/status — with transport and
    # storage fields explicitly excluded. Recomputed on write and replay.
    envelope: dict[str, Any] = {
        "version": CONTRACT_VERSION,
        "content_schema": CONTENT_SCHEMA,
        "status": status,
        "refusals": refusals,
        "symbol": symbol,
        "query": {"min_dte": min_dte, "max_dte": max_dte, "as_of_ny": asof.isoformat()},
        "axes": {"expiries": selection["admitted"], "strike_keys": strike_keys,
                 "n_strikes": len(strike_keys)},
        "grids": grids,
        "metric_registry": metric_registry,
        # C7: overall map status never overrides a section's own admission.
        "metrics": {"admitted": sorted(n for n, s in grids.items()
                                       if s["metric_admitted"]),
                    "partial": sorted(n for n, s in grids.items()
                                      if s["status"] == "partial"),
                    "unavailable": sorted(n for n, s in grids.items()
                                          if s["status"] == "unavailable")},
        "clocks": clocks,
        "coverage": coverage,
        "provenance": provenance,
        "grounding": grounding,
        "synthetic": bool(chain.get("synthetic")),
    }
    content_digest = compute_content_digest(envelope)
    envelope["content_digest"] = content_digest
    envelope["record_id"] = record_id_for_digest(content_digest)
    return envelope


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
