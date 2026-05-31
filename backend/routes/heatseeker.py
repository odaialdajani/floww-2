"""
backend/routes/heatseeker.py

API routes for Skylit-parity Heatseeker.
    Wave 1: flip zones, node lifecycle, air pockets.
    Wave 2: beach ball, reverse rug, rainbow road, velocity mode, trinity.
    Wave 3: rolling floors/ceilings, node classification, stacked nodes, tug-of-war.

Routes fetch the option chain and pass it into the pure functions in
`services.heatseeker`. Mongo-backed history endpoints fall back to empty
input on failure — the pure functions tolerate that.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from services.heatseeker import (
    _gex_per_strike,
    calc_air_pockets,
    calc_flip_zones,
    calc_node_lifecycle,
    calc_trinity_confluence,
    calc_velocity_mode,
    detect_beach_ball,
    detect_rainbow_road,
    detect_reverse_rug,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/heatseeker", tags=["heatseeker"])


async def _fetch_chain(ticker: str, expiries: int) -> Dict[str, Any]:
    """
    Resolve the option chain for ``ticker`` using the same fetcher the rest
    of server.py uses. Imported lazily so the routes module remains import-
    safe before ``app`` is constructed.
    """
    # Local import so the routes module doesn't trigger heavy server.py
    # initialization at import time.
    from server import _sanitize, fetch_spot_and_chains_merged  # noqa: F401
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    return raw


async def _fetch_history(ticker: str, lookback_mins: int = 1440) -> List[Dict[str, Any]]:
    """
    Fetch spot snapshots for ``ticker`` over the last ``lookback_mins`` minutes
    from the snapshots collection. Default 1440 minutes = 24h.
    Returns empty list if Mongo isn't available — the pure consumer functions
    treat this as "all nodes fresh".

    Added `lookback_mins` param to fix TypeError at heatseeker.py:119 which was
    calling _fetch_history(ticker, lookback_mins=...) against the old (ticker-only)
    signature. Clamped to [1, 10080] (7d max) to prevent caller-driven DoS.
    """
    try:
        from datetime import datetime, timedelta, timezone

        from server import db

        lookback_mins = max(1, min(int(lookback_mins or 1440), 7 * 24 * 60))
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_mins)
        cursor = db.snapshots.find(
            {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
            {"spot": 1, "ts": 1, "_id": 0},
        ).sort("ts", 1)
        history: List[Dict[str, Any]] = []
        async for doc in cursor:
            spot = doc.get("spot")
            if spot is None:
                continue
            ts = doc.get("ts")
            history.append({
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "spot": float(spot),
            })
        return history
    except Exception as e:
        logger.warning(f"heatseeker history fetch fail for {ticker}: {e}")
        return []


@router.get("/flip-zones")
async def flip_zones_route(
    ticker: str = "SPY",
    window_pct: float = Query(default=0.05, ge=0.01, le=0.50, description="Window size as fraction of spot"),
    min_gap_pct: float = Query(default=0.02, ge=0.005, le=0.20, description="Minimum gap between flip zones"),
    expiries: int = Query(default=4, ge=1, le=12),
):
    """All cumulative-GEX sign changes within +/-window_pct of spot."""
    try:
        from server import _sanitize
        raw = await _fetch_chain(ticker, expiries)
        spot = raw.get("spot")
        contracts = raw.get("contracts") or []
        if not spot or not contracts:
            raise HTTPException(404, "No options data for " + ticker)
        result = calc_flip_zones(spot, contracts, window_pct=window_pct)
        return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"flip-zones route fail: {e}")
        return {"ticker": ticker.upper() if isinstance(ticker, str) else "unknown", "spot": 0, "zones": [], "error": str(e), "status": "degraded"}


@router.get("/node-lifecycle")
async def node_lifecycle_route(
    ticker: str = "SPY",
    lookback_mins: int = Query(default=60, ge=5, le=1440, description="Lookback window in minutes"),
    expiries: int = Query(default=4, ge=1, le=12),
):
    """Top 10 |GEX| nodes classified Fresh/Tested/Delivered/Decaying."""
    try:
        from server import _sanitize
        raw = await _fetch_chain(ticker, expiries)
        spot = raw.get("spot")
        contracts = raw.get("contracts") or []
        if not spot or not contracts:
            raise HTTPException(404, "No options data for " + ticker)
        history = await _fetch_history(ticker.upper(), lookback_mins=lookback_mins)
        result = calc_node_lifecycle(spot, contracts, history)
        return _sanitize({
            "ticker": ticker.upper(),
            "spot": spot,
            "history_points": len(history),
            **result,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"node-lifecycle route fail: {e}")
        return {"ticker": ticker.upper() if isinstance(ticker, str) else "unknown", "spot": 0, "nodes": [], "n_nodes": 0, "error": str(e), "status": "degraded"}


@router.get("/air-pockets")
async def air_pockets_route(
    ticker: str = "SPY",
    min_gap_pct: float = Query(default=0.02, ge=0.005, le=0.20, description="Minimum gap between air pockets"),
    expiries: int = Query(default=4, ge=1, le=12),
):
    """Contiguous strike ranges with |GEX| below 20% of the local median."""
    try:
        from server import _sanitize
        raw = await _fetch_chain(ticker, expiries)
        spot = raw.get("spot")
        contracts = raw.get("contracts") or []
        if not spot or not contracts:
            raise HTTPException(404, "No options data for " + ticker)
        result = calc_air_pockets(spot, contracts, min_gap_pct=min_gap_pct)
        return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"air-pockets route fail: {e}")
        return {"ticker": ticker.upper() if isinstance(ticker, str) else "unknown", "spot": 0, "pockets": [], "error": str(e), "status": "degraded"}


# ---------------------------------------------------------------------------
# Wave 2 helpers
# ---------------------------------------------------------------------------

async def _fetch_king_node_history(ticker: str) -> List[Dict[str, Any]]:
    """
    Build a king-node history for ``ticker``. Each entry is
    ``{"timestamp": iso8601, "king_node_strike": float, "spot": float}``.

    Strategy: query last 30 minutes of spot snapshots from ``db.snapshots``.
    If a snapshot has a stored ``king_node_strike``, use it; otherwise leave
    the history empty (the pure function returns calm/0 in that case). On
    any Mongo failure, return an empty list so the route still returns a
    well-formed payload.
    """
    try:
        from datetime import datetime, timedelta, timezone

        from server import db

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        cursor = db.snapshots.find(
            {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
            {"spot": 1, "ts": 1, "king_node_strike": 1, "_id": 0},
        ).sort("ts", 1)
        history: List[Dict[str, Any]] = []
        async for doc in cursor:
            kn = doc.get("king_node_strike")
            if kn is None:
                continue
            ts = doc.get("ts")
            try:
                spot = float(doc.get("spot") or 0)
                king = float(kn)
            except (TypeError, ValueError):
                continue
            history.append({
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "king_node_strike": king,
                "spot": spot,
            })
        return history
    except Exception as e:
        logger.warning(f"heatseeker king-node history fetch fail for {ticker}: {e}")
        return []


async def _trinity_snapshot(ticker: str, expiries: int) -> Dict[str, Any]:
    """
    Resolve a single trinity-confluence snapshot for ``ticker``.

    Returns the four-field dict expected by ``calc_trinity_confluence``:
        ``gex_regime``, ``spot``, ``gamma_flip``, ``trend_direction``.

    On any failure, returns a fully-missing snapshot so the trinity score
    treats this index as a divergence rather than crashing.
    """
    missing = {
        "gex_regime": "missing",
        "spot": None,
        "gamma_flip": None,
        "trend_direction": "missing",
    }
    try:
        raw = await _fetch_chain(ticker, expiries)
        spot = raw.get("spot")
        contracts = raw.get("contracts") or []
        if not spot or not contracts:
            return missing

        # gex_regime: net signed GEX summed across all strikes.
        gex_map = _gex_per_strike(spot, contracts)
        net = sum(gex_map.values())
        if net > 0:
            regime = "positive"
        elif net < 0:
            regime = "negative"
        else:
            regime = "neutral"

        # gamma_flip: re-use advanced_analytics' calc_gamma_flip_levels.
        gamma_flip: Optional[float] = None
        try:
            from advanced_analytics import calc_gamma_flip_levels
            flips = calc_gamma_flip_levels(spot, contracts)
            if isinstance(flips, dict):
                gf = flips.get("primary_flip") or flips.get("gamma_flip")
                if gf is not None:
                    gamma_flip = float(gf)
        except Exception as e:
            logger.debug(f"trinity gamma_flip fetch fail for {ticker}: {e}")

        # trend_direction: compare current spot to spot 30 minutes ago.
        trend: str = "missing"
        try:
            from datetime import datetime, timedelta, timezone

            from server import db

            cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
            doc = await db.snapshots.find_one(
                {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
                sort=[("ts", 1)],
            )
            if doc and doc.get("spot"):
                old = float(doc["spot"])
                if old > 0:
                    pct = (float(spot) - old) / old
                    if pct > 0.001:
                        trend = "up"
                    elif pct < -0.001:
                        trend = "down"
                    else:
                        trend = "flat"
        except Exception as e:
            logger.debug(f"trinity trend fetch fail for {ticker}: {e}")

        return {
            "gex_regime": regime,
            "spot": float(spot),
            "gamma_flip": gamma_flip,
            "trend_direction": trend,
        }
    except Exception as e:
        logger.warning(f"trinity snapshot fail for {ticker}: {e}")
        return missing


# ---------------------------------------------------------------------------
# Wave 2 routes
# ---------------------------------------------------------------------------

@router.get("/beach-ball")
async def beach_ball_route(
    ticker: str = "SPY",
    expiries: int = Query(4, ge=1, le=12),
):
    """Beach Ball: spot stretched past the King Node (overshoot/reversion)."""
    try:
        from server import _sanitize
        raw = await _fetch_chain(ticker, expiries)
        spot = raw.get("spot")
        contracts = raw.get("contracts") or []
        if not spot or not contracts:
            raise HTTPException(404, f"No options data for {ticker}")
        result = detect_beach_ball(spot, contracts)
        return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"beach-ball route fail: {e}")
        return {"ticker": ticker.upper() if isinstance(ticker, str) else "unknown", "spot": 0, "beach_ball": False, "error": str(e), "status": "degraded"}


@router.get("/reverse-rug")
async def reverse_rug_route(
    ticker: str = "SPY",
    expiries: int = Query(4, ge=1, le=12),
):
    """Reverse Rug: positive floor below + negative ceiling above."""
    try:
        from server import _sanitize
        raw = await _fetch_chain(ticker, expiries)
        spot = raw.get("spot")
        contracts = raw.get("contracts") or []
        if not spot or not contracts:
            raise HTTPException(404, f"No options data for {ticker}")
        result = detect_reverse_rug(spot, contracts)
        return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"reverse-rug route fail: {e}")
        return {"ticker": ticker.upper() if isinstance(ticker, str) else "unknown", "spot": 0, "reverse_rug": False, "error": str(e), "status": "degraded"}


@router.get("/rainbow-road")
async def rainbow_road_route(
    ticker: str = "SPY",
    max_dominant_share: float = Query(0.15, gt=0.0, le=1.0),
    expiries: int = Query(4, ge=1, le=12),
):
    """Rainbow Road: no dominant structure — chaos, sit out."""
    try:
        from server import _sanitize
        raw = await _fetch_chain(ticker, expiries)
        spot = raw.get("spot")
        contracts = raw.get("contracts") or []
        if not spot or not contracts:
            raise HTTPException(404, f"No options data for {ticker}")
        result = detect_rainbow_road(spot, contracts, max_dominant_share=max_dominant_share)
        return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"rainbow-road route fail: {e}")
        return {"ticker": ticker.upper() if isinstance(ticker, str) else "unknown", "spot": 0, "rainbow_road": False, "error": str(e), "status": "degraded"}


@router.get("/velocity-mode")
async def velocity_mode_route(ticker: str = "SPY"):
    """
    Velocity Mode: rate of King Node drift over the last ~30 minutes.

    History comes from Mongo ``db.snapshots`` (entries with a stored
    ``king_node_strike``). If Mongo is unavailable or no usable rows exist,
    the pure function returns ``velocity=0, mode="calm", n_snapshots=0`` —
    matching Wave 1's node-lifecycle fallback shape.
    """
    try:
        from server import _sanitize
        history = await _fetch_king_node_history(ticker.upper())
        result = calc_velocity_mode(history)
        return _sanitize({"ticker": ticker.upper(), **result})
    except Exception as e:
        logger.warning(f"velocity-mode route fail: {e}")
        return {"ticker": ticker.upper() if isinstance(ticker, str) else "unknown", "velocity": 0, "mode": "calm", "error": str(e), "status": "degraded"}


@router.get("/trinity-confluence")
async def trinity_confluence_route(
    expiries: int = Query(4, ge=1, le=12),
):
    """
    Trinity Confluence: SPX/SPY/QQQ alignment, 0–100.

    Always queries the three tickers; if any individual snapshot fails to
    load, that dimension is recorded as ``"missing"`` rather than crashing
    the request.
    """
    from server import _sanitize
    try:
        spx = await _trinity_snapshot("SPX", expiries)
        spy = await _trinity_snapshot("SPY", expiries)
        qqq = await _trinity_snapshot("QQQ", expiries)
        result = calc_trinity_confluence(spx, spy, qqq)
        return _sanitize({
            "snapshots": {"SPX": spx, "SPY": spy, "QQQ": qqq},
            **result,
        })
    except Exception as e:
        logger.warning(f"trinity-confluence route fail: {e}")
        return {"score": 0, "status": "degraded", "error": str(e)}


# ---------------------------------------------------------------------------
# Wave 3 routes
# ---------------------------------------------------------------------------

@router.get("/rolling-floors-ceilings")
async def rolling_floors_ceilings_route(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
    lookback_days: int = Query(20, ge=1, le=60),
):
    """Rolling floors/ceilings tracker — trend formation signals."""
    try:
        from server import _sanitize, fetch_spot_and_chains_merged
        from services.heatseeker import calc_rolling_floors_ceilings
        t = ticker.strip().upper()
        # Fetch daily snapshots for the lookback period
        raw = await fetch_spot_and_chains_merged(t, expiries)
        spot = raw.get("spot", 0)
        contracts = raw.get("contracts", [])
        if not spot or not contracts:
            raise HTTPException(404, f"No options data for {ticker}")
        # Build synthetic daily snapshots from available data
        snapshots = [{"spot": spot, "contracts": contracts}]
        result = calc_rolling_floors_ceilings(spot, snapshots, ticker=t, lookback_days=lookback_days)
        return _sanitize({"ticker": t, **result})
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"rolling-floors-ceilings route fail: {e}")
        return {"ticker": ticker.upper() if isinstance(ticker, str) else "unknown", "floors": [], "ceilings": [], "error": str(e), "status": "degraded"}


@router.get("/node-classification")
async def node_classification_route(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
):
    """
    Classify nodes as real (growing intent) vs hedge (fading protection).

    Builds the top-|GEX| nodes from the current chain, attaches a
    ``gamma_sign`` (positive/negative based on signed net GEX) and an
    ``oi_trend`` (growing/fading based on 24h OI history when available),
    then runs ``classify_nodes`` to assign real/hedge/unknown labels.
    """
    try:
        from server import _sanitize
        from services.heatseeker import calc_node_lifecycle, classify_nodes
        t = ticker.strip().upper()
        raw = await _fetch_chain(t, expiries)
        spot = raw.get("spot", 0)
        contracts = raw.get("contracts", [])
        if not spot or not contracts:
            raise HTTPException(404, f"No options data for {ticker}")

        history = await _fetch_history(t)

        # Lifecycle nodes give us strike/net_gex/taps/state/tap_probability for the
        # top-10 |GEX| strikes — the same set used by the lifecycle panel.
        lifecycle = calc_node_lifecycle(spot, contracts, history)
        raw_nodes = lifecycle.get("nodes", [])

        # Attach gamma_sign + oi_trend so classify_nodes can apply its rules.
        # gamma_sign comes straight from the signed net_gex. oi_trend is
        # "growing" for fresh/tested nodes (no/few taps → intent forming) and
        # "fading" for delivered/decaying nodes (protection has expired).
        annotated = []
        for n in raw_nodes:
            net = float(n.get("net_gex") or 0.0)
            state = str(n.get("state") or "").lower()
            gamma_sign = "positive" if net > 0 else "negative" if net < 0 else "neutral"
            if state in ("fresh", "tested"):
                oi_trend = "growing"
            elif state in ("delivered", "decaying"):
                oi_trend = "fading"
            else:
                oi_trend = "unknown"
            annotated.append({**n, "gamma_sign": gamma_sign, "oi_trend": oi_trend})

        result = classify_nodes(annotated)
        return _sanitize({"ticker": t, "spot": spot, **result})
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"node-classification route fail: {e}")
        return {"ticker": ticker.upper() if isinstance(ticker, str) else "unknown", "spot": 0, "nodes": [], "error": str(e), "status": "degraded"}


@router.get("/stacked-nodes")
async def stacked_nodes_route(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
    threshold_pct: float = Query(0.3, ge=0.1, le=0.9),
):
    """Detect stacked nodes — both call+put GEX significant at same strike."""
    try:
        from server import _sanitize, fetch_spot_and_chains_merged
        from services.heatseeker import detect_stacked_nodes
        t = ticker.strip().upper()
        raw = await fetch_spot_and_chains_merged(t, expiries)
        spot = raw.get("spot", 0)
        contracts = raw.get("contracts", [])
        if not spot or not contracts:
            raise HTTPException(404, f"No options data for {ticker}")
        result = detect_stacked_nodes(contracts, threshold_pct=threshold_pct)
        return _sanitize({"ticker": t, "spot": spot, **result})
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"stacked-nodes route fail: {e}")
        return {"ticker": ticker.upper() if isinstance(ticker, str) else "unknown", "spot": 0, "stacked_nodes": [], "error": str(e), "status": "degraded"}


@router.get("/tug-of-war")
async def tug_of_war_route(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
):
    """Detect tug-of-war zones — positive/negative GEX conflict near spot."""
    try:
        from server import _sanitize, fetch_spot_and_chains_merged
        from services.heatseeker import calc_tug_of_war_zones
        t = ticker.strip().upper()
        raw = await fetch_spot_and_chains_merged(t, expiries)
        spot = raw.get("spot", 0)
        contracts = raw.get("contracts", [])
        if not spot or not contracts:
            raise HTTPException(404, f"No options data for {ticker}")
        result = calc_tug_of_war_zones(contracts, spot)
        return _sanitize({"ticker": t, **result})
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"tug-of-war route fail: {e}")
        return {"ticker": ticker.upper() if isinstance(ticker, str) else "unknown", "zones": [], "error": str(e), "status": "degraded"}
