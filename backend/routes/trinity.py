"""
backend/routes/trinity.py

Trinity Alignment Index API routes.
Cross-correlates Zero-Gamma strike levels across SPX, SPY, and QQQ.

Endpoints:
  GET /api/trinity/{ticker}          — Trinity alignment for a single ticker
  GET /api/trinity/align             — Full SPX/SPY/QQQ alignment score
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trinity", tags=["trinity"])


async def _fetch_chain(ticker: str, expiries: int = 4):
    """Fetch option chain with lazy import."""
    from server import fetch_spot_and_chains_merged
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    return await fetch_spot_and_chains_merged(t, expiries)


def _extract_zero_gamma_levels(spot: float, contracts: list[dict]) -> list[float]:
    """Extract zero-gamma (flip) levels from computed GEX data."""
    from services.gex_core import compute_gex_by_strike
    strikes_data = compute_gex_by_strike(spot, contracts)
    if not strikes_data:
        return []

    # Find zero crossings
    levels = []
    for i in range(len(strikes_data) - 1):
        gex_a = strikes_data[i]["gex"]
        gex_b = strikes_data[i + 1]["gex"]
        if (gex_a > 0 and gex_b < 0) or (gex_a < 0 and gex_b > 0):
            # Linear interpolation
            denom = gex_a - gex_b
            if denom != 0:
                t_frac = gex_a / denom
                crossing = strikes_data[i]["strike"] + t_frac * (
                    strikes_data[i + 1]["strike"] - strikes_data[i]["strike"]
                )
                levels.append(round(crossing, 2))
    return levels


@router.get("/align")
async def get_trinity_alignment(
    expiries: int = Query(4, ge=1, le=12),
):
    """Compute Trinity Alignment Index across SPX, SPY, and QQQ."""
    from services.trinity_alignment import TrinityAlignmentIndex

    tickers = ["SPY", "QQQ", "^SPX"]
    spots = {}
    flip_levels = {}

    for tk in tickers:
        try:
            raw = await _fetch_chain(tk, expiries)
            spot = raw.get("spot", 0)
            contracts = raw.get("contracts", [])
            spots[tk] = spot
            flip_levels[tk] = _extract_zero_gamma_levels(spot, contracts)
        except Exception as e:
            logger.warning(f"Trinity fetch failed for {tk}: {e}")
            spots[tk] = 0
            flip_levels[tk] = []

    trinity = TrinityAlignmentIndex(tolerance_pct=0.005)
    result = trinity.compute(
        spy_flip_levels=flip_levels.get("SPY", []),
        qqq_flip_levels=flip_levels.get("QQQ", []),
        spx_flip_levels=flip_levels.get("^SPX", []),
        spy_spot=spots.get("SPY", 0),
        qqq_spot=spots.get("QQQ", 0),
        spx_spot=spots.get("^SPX", 0),
    )

    # Emit Prometheus metric
    from services.observability import metrics as obs_metrics
    obs_metrics.trinity_score.set(result.get("score", 0.0))

    return result


def _qualified_adv_shares(ticker: str, raw: dict) -> tuple[float | None, dict]:
    """Return (adv_shares, provenance) only from independently qualified evidence.

    A qualified ADV is a rolling per-session share-volume average computed from
    stored, validated daily bars that carry explicit share volume with clocks.
    No admitted store persists per-session volume today (the Related daily
    store keeps close-only bars), so this refuses rather than emitting a
    constant substitute. When such a store is admitted, qualify it here with
    its source, session count and as-of date.
    """
    return None, {
        "status": "unavailable",
        "reason": "no_qualified_adv",
        "detail": "no admitted per-session share-volume store for ticker ADV",
    }


@router.get("/{ticker}")
async def get_trinity_for_ticker(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    """Get zero-gamma levels and GEX data for a single ticker."""
    t = ticker.upper()
    raw = await _fetch_chain(t, expiries)
    spot = raw.get("spot", 0)
    contracts = raw.get("contracts", [])
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {t}")

    from services.gex_core import compute_gex_by_strike
    strikes_data = compute_gex_by_strike(spot, contracts, t)
    flip_levels = _extract_zero_gamma_levels(spot, contracts)

    # ── Compute net GEX for paper-accurate metrics ──
    net_gex = sum(s.get("gex", 0.0) for s in strikes_data)

    response: dict = {
        "ticker": t,
        "spot": spot,
        "zero_gamma_levels": flip_levels,
        "strikes": strikes_data,
        "net_gex": round(net_gex, 2),
    }

    # ── Paper-accurate Gamma Imbalance (Barbon-Buraschi) ──
    if spot > 0 and flip_levels:
        from services.gex_paper_accurate import (
            compute_flip_metrics,
            compute_gamma_imbalance,
        )
        try:
            response["flip_metrics"] = compute_flip_metrics(
                spot, flip_levels[0] if flip_levels else None, net_gex
            )
        except Exception:
            logger.warning("Trinity flip-metrics compute failed for %s", t, exc_info=True)
            response["flip_metrics"] = {"status": "partial", "reason": "compute_failed"}
        # ADV must be independently qualified per ticker (rolling share volume
        # with provenance). No admitted store carries per-session share volume
        # today; a constant substitute is refused instead of displayed.
        adv_shares, adv_prov = _qualified_adv_shares(t, raw)
        if adv_shares is None:
            response["gamma_imbalance"] = {
                "status": "unavailable",
                "reason": adv_prov.get("reason", "no_qualified_adv"),
                "gamma_imbalance_pct": None,
                "gamma_imbalance_dollars_per_share": None,
                "regime": None,
                "interpretation": (
                    "Gamma imbalance withheld: no independently qualified "
                    "per-ticker average daily share volume in stored evidence; "
                    "a constant substitute is not emitted."
                ),
            }
        else:
            try:
                gi = compute_gamma_imbalance(net_gex, spot, adv_shares=adv_shares)
                gi["status"] = "ok"
                gi["adv_shares"] = adv_shares
                gi["adv_provenance"] = adv_prov
                response["gamma_imbalance"] = gi
            except Exception:
                logger.warning("Trinity gamma-imbalance compute failed for %s", t, exc_info=True)
                response["gamma_imbalance"] = {
                    "status": "partial",
                    "reason": "compute_failed",
                    "gamma_imbalance_pct": None,
                    "gamma_imbalance_dollars_per_share": None,
                    "regime": None,
                }
        # Cross-asset spillover needs a separately timestamped SPX gamma
        # measurement. Reusing this ticker's own imbalance as the SPX input is
        # self-substitution and is refused; report a typed unavailability.
        response["cross_asset_spillover"] = {
            "status": "unavailable",
            "reason": "no_separate_spx_measurement",
            "spillover_risk": None,
            "effective_gamma": None,
            "index_driver_pct": None,
            "interpretation": (
                "Spillover withheld: no separately measured SPX gamma "
                "imbalance is available as evidence; the selected ticker's "
                "own value is never substituted for SPX."
            ),
        }

    return response
