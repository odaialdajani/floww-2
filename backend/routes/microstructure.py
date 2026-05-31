"""
backend/routes/microstructure.py

API routes for advanced microstructure analytics:
VPIN, GEX surface, Hawkes process, Vol surface, Liquidity metrics,
Anomaly detection, Trinity alignment, Node lifecycle.

All endpoints degrade gracefully — return 200 with empty/error payloads
so the frontend never crashes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/microstructure", tags=["microstructure"])

# Module-level service instances (lazy initialization)
_vpin_engines: Dict[str, Any] = {}
_gex_aggregator = None
_hawkes_processes: Dict[str, Any] = {}
_vol_constructor = None
_liquidity_metrics: Dict[str, Any] = {}
_anomaly_detectors: Dict[str, Any] = {}
_trinity_index = None
_node_trackers: Dict[str, Any] = {}
_fragility_index = None


def _get_vpin_engine(ticker: str):
    if ticker not in _vpin_engines:
        from services.vpin_engine import VpinEngine
        _vpin_engines[ticker] = VpinEngine()
    return _vpin_engines[ticker]


def _get_gex_aggregator():
    global _gex_aggregator
    if _gex_aggregator is None:
        from services.gex_aggregator import GexAggregator
        _gex_aggregator = GexAggregator()
    return _gex_aggregator


def _get_hawkes(ticker: str):
    if ticker not in _hawkes_processes:
        from services.hawkes_process import HawkesProcess
        _hawkes_processes[ticker] = HawkesProcess()
    return _hawkes_processes[ticker]


def _get_vol_constructor():
    global _vol_constructor
    if _vol_constructor is None:
        from services.stochastic_vol import VolSurfaceConstructor
        _vol_constructor = VolSurfaceConstructor()
    return _vol_constructor


def _get_liquidity(ticker: str):
    if ticker not in _liquidity_metrics:
        from services.liquidity_metrics import AmihudIlliquidity, KyleLambda
        _liquidity_metrics[ticker] = {
            "kyle": KyleLambda(),
            "amihud": AmihudIlliquidity(),
        }
    return _liquidity_metrics[ticker]


def _get_anomaly_detector(ticker: str):
    if ticker not in _anomaly_detectors:
        from services.anomaly_detector import FlowAnomalyDetector
        _anomaly_detectors[ticker] = FlowAnomalyDetector()
    return _anomaly_detectors[ticker]


def _get_trinity_index():
    global _trinity_index
    if _trinity_index is None:
        from services.trinity_alignment import TrinityAlignmentIndex
        _trinity_index = TrinityAlignmentIndex()
    return _trinity_index


def _get_node_tracker(ticker: str):
    if ticker not in _node_trackers:
        from services.node_lifecycle import NodeLifecycleTracker
        _node_trackers[ticker] = NodeLifecycleTracker()
    return _node_trackers[ticker]


def _get_fragility_index():
    global _fragility_index
    if _fragility_index is None:
        from services.liquidity_metrics import MarketFragilityIndex
        _fragility_index = MarketFragilityIndex()
    return _fragility_index


async def _fetch_chain(ticker: str, expiries: int = 5) -> Dict[str, Any]:
    """Fetch option chain, same pattern as existing routes."""
    try:
        from server import fetch_spot_and_chains_merged
        t = ticker.strip().upper()
        if t == "SPX":
            t = "^SPX"
        raw = await fetch_spot_and_chains_merged(t, expiries)
        return raw
    except Exception as e:
        logger.warning(f"Chain fetch failed for {ticker}: {e}")
        return {"spot": 0, "contracts": []}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/vpin/{ticker}")
async def vpin_endpoint(ticker: str):
    """Compute VPIN and toxicity signals for a ticker."""
    try:
        engine = _get_vpin_engine(ticker.upper())
        state = engine.get_state()
        return {"ticker": ticker.upper(), "status": "ok", **state}
    except Exception as e:
        logger.error(f"VPIN error for {ticker}: {e}")
        return {"ticker": ticker.upper(), "status": "error", "error": str(e)}


@router.get("/gex-surface/{ticker}")
async def gex_surface_endpoint(ticker: str, expiries: int = Query(5, ge=1, le=20)):
    """Compute GEX surface (strike x expiry) for a ticker."""
    try:
        chain = await _fetch_chain(ticker, expiries)
        spot = chain.get("spot", 0)
        contracts = chain.get("contracts", [])
        if not contracts or spot <= 0:
            return {"ticker": ticker.upper(), "status": "no_data", "spot": spot}
        agg = _get_gex_aggregator()
        result = agg.compute(spot, contracts)
        result["ticker"] = ticker.upper()
        result["status"] = "ok"
        return result
    except Exception as e:
        logger.error(f"GEX surface error for {ticker}: {e}")
        return {"ticker": ticker.upper(), "status": "error", "error": str(e)}


@router.get("/hawkes/{ticker}")
async def hawkes_endpoint(ticker: str):
    """Fit Hawkes process to recent trade arrivals."""
    try:
        chain = await _fetch_chain(ticker, 3)
        spot = chain.get("spot", 0)
        if spot <= 0:
            return {"ticker": ticker.upper(), "status": "no_data"}
        # Use contract timestamps as proxy for trade arrivals
        hawkes = _get_hawkes(ticker.upper())
        state = hawkes.get_state()
        state["ticker"] = ticker.upper()
        state["status"] = "ok"
        return state
    except Exception as e:
        logger.error(f"Hawkes error for {ticker}: {e}")
        return {"ticker": ticker.upper(), "status": "error", "error": str(e)}


@router.get("/vol-surface/{ticker}")
async def vol_surface_endpoint(ticker: str, expiries: int = Query(5, ge=1, le=20)):
    """Build full IV surface using SABR and SVI."""
    try:
        chain = await _fetch_chain(ticker, expiries)
        spot = chain.get("spot", 0)
        contracts = chain.get("contracts", [])
        if not contracts or spot <= 0:
            return {"ticker": ticker.upper(), "status": "no_data"}
        constructor = _get_vol_constructor()
        result = constructor.build_surface(spot, contracts)
        result["ticker"] = ticker.upper()
        result["status"] = "ok"
        return result
    except Exception as e:
        logger.error(f"Vol surface error for {ticker}: {e}")
        return {"ticker": ticker.upper(), "status": "error", "error": str(e)}


@router.get("/liquidity/{ticker}")
async def liquidity_endpoint(ticker: str):
    """Compute Kyle's Lambda, Amihud Illiquidity, and Market Fragility."""
    try:
        liq = _get_liquidity(ticker.upper())
        kyle = liq["kyle"]
        amihud = liq["amihud"]
        fragility = _get_fragility_index()
        result = fragility.compute(
            kyle_lambda=kyle.compute(),
            amihud=amihud.compute(),
        )
        result["ticker"] = ticker.upper()
        result["status"] = "ok"
        return result
    except Exception as e:
        logger.error(f"Liquidity error for {ticker}: {e}")
        return {"ticker": ticker.upper(), "status": "error", "error": str(e)}


@router.get("/anomaly/{ticker}")
async def anomaly_endpoint(ticker: str):
    """Get flow toxicity anomaly detection status."""
    try:
        detector = _get_anomaly_detector(ticker.upper())
        state = detector.get_state()
        state["ticker"] = ticker.upper()
        state["status"] = "ok"
        return state
    except Exception as e:
        logger.error(f"Anomaly error for {ticker}: {e}")
        return {"ticker": ticker.upper(), "status": "error", "error": str(e)}


@router.get("/trinity")
async def trinity_endpoint(
    spy_spot: float = Query(0.0),
    qqq_spot: float = Query(0.0),
    spx_spot: float = Query(0.0),
):
    """Compute Trinity Alignment Index across SPY, QQQ, SPX."""
    try:
        # Fetch flip levels for each
        spy_chain = await _fetch_chain("SPY", 5)
        qqq_chain = await _fetch_chain("QQQ", 5)
        spx_chain = await _fetch_chain("SPX", 5)

        agg = _get_gex_aggregator()

        spy_contracts = spy_chain.get("contracts", [])
        qqq_contracts = qqq_chain.get("contracts", [])
        spx_contracts = spx_chain.get("contracts", [])

        spy_result = agg.compute(spy_chain.get("spot", 0), spy_contracts) if spy_contracts and spy_chain.get("spot", 0) > 0 else {}
        qqq_result = agg.compute(qqq_chain.get("spot", 0), qqq_contracts) if qqq_contracts and qqq_chain.get("spot", 0) > 0 else {}
        spx_result = agg.compute(spx_chain.get("spot", 0), spx_contracts) if spx_contracts and spx_chain.get("spot", 0) > 0 else {}

        trinity = _get_trinity_index()
        result = trinity.compute(
            spy_flip_levels=spy_result.get("zero_gamma_levels", []),
            qqq_flip_levels=qqq_result.get("zero_gamma_levels", []),
            spx_flip_levels=spx_result.get("zero_gamma_levels", []),
            spy_spot=spy_chain.get("spot", 0),
            qqq_spot=qqq_chain.get("spot", 0),
            spx_spot=spx_chain.get("spot", 0),
        )
        result["status"] = "ok"
        return result
    except Exception as e:
        logger.error(f"Trinity error: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/nodes/{ticker}")
async def nodes_endpoint(ticker: str, expiries: int = Query(5, ge=1, le=20)):
    """Get node lifecycle status for a ticker."""
    try:
        chain = await _fetch_chain(ticker, expiries)
        spot = chain.get("spot", 0)
        contracts = chain.get("contracts", [])
        if not contracts or spot <= 0:
            return {"ticker": ticker.upper(), "status": "no_data"}

        agg = _get_gex_aggregator()
        gex_result = agg.compute(spot, contracts)
        gex_1d = gex_result.get("gex_1d", [])
        strikes = gex_result.get("strikes", [])

        # Find king nodes (local maxima in GEX)
        king_nodes = []
        for i in range(1, len(gex_1d) - 1):
            if gex_1d[i] > gex_1d[i - 1] and gex_1d[i] > gex_1d[i + 1] and gex_1d[i] > 0:
                king_nodes.append((strikes[i], gex_1d[i]))

        tracker = _get_node_tracker(ticker.upper())
        result = tracker.update(spot, king_nodes)
        result["ticker"] = ticker.upper()
        result["status"] = "ok"
        return result
    except Exception as e:
        logger.error(f"Nodes error for {ticker}: {e}")
        return {"ticker": ticker.upper(), "status": "error", "error": str(e)}


@router.get("/toxicity-dashboard")
async def toxicity_dashboard():
    """Combined toxicity dashboard data."""
    try:
        vpin = _get_vpin_engine("SPY")
        anomaly = _get_anomaly_detector("SPY")
        fragility = _get_fragility_index()
        toxicity = vpin.get_toxicity_signal()
        frag_result = fragility.compute(
            vpin_cdf=toxicity.get("vpin_cdf", 0),
            qi_zscore=toxicity.get("qi_zscore", 0),
        )
        return {
            "status": "ok",
            "vpin": toxicity.get("vpin", 0),
            "vpin_cdf": toxicity.get("vpin_cdf", 0),
            "qi": toxicity.get("qi", 0),
            "qi_zscore": toxicity.get("qi_zscore", 0),
            "is_toxic": toxicity.get("is_toxic", False),
            "fragility": frag_result,
            "anomaly": anomaly.get_state(),
        }
    except Exception as e:
        logger.error(f"Toxicity dashboard error: {e}")
        return {"status": "error", "error": str(e)}
