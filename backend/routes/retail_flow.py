"""
backend/routes/retail_flow.py

Retail Flow Toxicity API routes.
Exposes CPR, OI change detection, IV skew, and composite retail flow score.

Endpoints:
  GET  /api/retail-flow/{ticker}           — Full retail flow snapshot
  GET  /api/retail-flow/{ticker}/cpr        — Call/Put Volume Ratio per expiry
  GET  /api/retail-flow/{ticker}/oi-change  — Open Interest day-over-day change
  GET  /api/retail-flow/{ticker}/score      — Composite retail flow score
  POST /api/retail-flow/{ticker}/compute    — Compute from raw option chain data
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/retail-flow", tags=["retail-flow"])


# ── In-memory stores (replace with DuckDB/MongoDB persistence later) ──

_cpr_calculators: Dict[str, Any] = {}
_oi_detectors: Dict[str, Any] = {}
_flow_scorers: Dict[str, Any] = {}

# Cached snapshots
_latest_snapshot: Dict[str, Dict[str, Any]] = {}


def _get_cpr_calc(ticker: str):
    if ticker not in _cpr_calculators:
        from services.cpr_calculator import CprCalculator
        _cpr_calculators[ticker] = CprCalculator()
    return _cpr_calculators[ticker]


def _get_oi_detector(ticker: str):
    if ticker not in _oi_detectors:
        from services.oi_change_detector import OiChangeDetector
        _oi_detectors[ticker] = OiChangeDetector()
    return _oi_detectors[ticker]


def _get_scorer(ticker: str):
    if ticker not in _flow_scorers:
        from services.retail_flow_score import RetailFlowScore
        _flow_scorers[ticker] = RetailFlowScore()
    return _flow_scorers[ticker]


# ── Helpers ──

def _serialize_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Make snapshot JSON-safe (convert numpy types, dataclasses, etc.)."""
    result: Dict[str, Any] = {}
    for key, val in snapshot.items():
        if isinstance(val, dict):
            result[key] = _serialize_snapshot(val)
        elif isinstance(val, (np.floating,)):
            result[key] = float(val)
        elif isinstance(val, (np.integer,)):
            result[key] = int(val)
        elif isinstance(val, (np.ndarray,)):
            result[key] = val.tolist()
        elif hasattr(val, "__dataclass_fields__"):
            result[key] = _serialize_snapshot(val.__dict__)
        elif isinstance(val, list):
            result[key] = [
                _serialize_snapshot(item) if isinstance(item, dict) else
                float(item) if isinstance(item, (np.floating,)) else
                int(item) if isinstance(item, (np.integer,)) else
                item.__dict__ if hasattr(item, "__dataclass_fields__") else
                item
                for item in val
            ]
        else:
            result[key] = val
    return result


# ── Routes ──

@router.get("/{ticker}")
async def get_retail_flow_snapshot(ticker: str):
    """Return the latest retail flow snapshot for a ticker."""
    t = ticker.upper()
    if t in _latest_snapshot:
        return _latest_snapshot[t]
    return {
        "ticker": t,
        "status": "no_data",
        "message": "No retail flow data yet. POST to /api/retail-flow/{ticker}/compute first.",
    }


@router.get("/{ticker}/cpr")
async def get_cpr(ticker: str):
    """Return the latest CPR values per expiry."""
    t = ticker.upper()
    snap = _latest_snapshot.get(t, {})
    cpr_data = snap.get("cpr", {})
    return {"ticker": t, "cpr": cpr_data}


@router.get("/{ticker}/oi-change")
async def get_oi_change(ticker: str):
    """Return the latest OI change data per strike."""
    t = ticker.upper()
    snap = _latest_snapshot.get(t, {})
    oi_data = snap.get("oi_change", {})
    return {"ticker": t, "oi_change": oi_data}


@router.get("/{ticker}/score")
async def get_flow_score(ticker: str):
    """Return the composite retail flow score."""
    t = ticker.upper()
    snap = _latest_snapshot.get(t, {})
    score_data = snap.get("flow_score", {})
    return {"ticker": t, "flow_score": score_data}


@router.post("/{ticker}/compute")
async def compute_retail_flow(
    ticker: str,
    call_volumes: Dict[str, float],
    put_volumes: Dict[str, float],
    current_oi: Dict[str, float],
    previous_oi: Dict[str, float],
    iv_skew: float = 0.0,
    expiries: Optional[List[str]] = None,
):
    """Compute retail flow metrics from raw option chain data.

    Args:
        ticker: Ticker symbol.
        call_volumes: Dict mapping expiry -> total call volume.
        put_volumes: Dict mapping expiry -> total put volume.
        current_oi: Dict mapping strike -> current open interest.
        previous_oi: Dict mapping strike -> previous-day open interest.
        iv_skew: Put IV minus Call IV (scalar, e.g. 0.02 = put IV 2pts higher).
        expiries: Optional explicit expiry list.

    Returns:
        Full retail flow snapshot with CPR, OI change, and composite score.
    """
    t = ticker.upper()

    try:
        # CPR
        cpr_calc = _get_cpr_calc(t)
        cpr_result = cpr_calc.compute(call_volumes, put_volumes, expiries)

        # Use the first expiry for OI change (most active)
        active_expiry = expiries[0] if expiries else (
            sorted(set(list(call_volumes.keys()) + list(put_volumes.keys())))[0]
            if call_volumes or put_volumes else "unknown"
        )

        # OI Change
        oi_det = _get_oi_detector(t)
        oi_result = oi_det.detect(
            current_oi={float(k): v for k, v in current_oi.items()},
            previous_oi={float(k): v for k, v in previous_oi.items()},
            expiry=active_expiry,
        )

        # Composite score — use average CPR across expiries
        avg_cpr = 1.0
        if cpr_result.current:
            cpr_vals = [
                r.cpr for r in cpr_result.current.values()
                if r.cpr != float("inf") and r.cpr > 0
            ]
            if cpr_vals:
                avg_cpr = float(np.mean(cpr_vals))

        # Average OI change (absolute)
        avg_oi_change = 0.0
        if oi_result.changes:
            oi_vals = [
                c.pct_change for c in oi_result.changes.values()
                if c.pct_change != float("inf")
            ]
            if oi_vals:
                avg_oi_change = float(np.mean(oi_vals))

        scorer = _get_scorer(t)
        flow_result = scorer.compute(
            cpr=avg_cpr,
            oi_change_pct=avg_oi_change,
            iv_skew=iv_skew,
        )

        snapshot = {
            "ticker": t,
            "status": "ok",
            "timestamp": str(np.datetime64("now")),
            "cpr": {
                exp: {
                    "cpr": r.cpr if r.cpr != float("inf") else "inf",
                    "call_volume": r.call_volume,
                    "put_volume": r.put_volume,
                    "label": r.label,
                }
                for exp, r in cpr_result.current.items()
            },
            "cpr_anomalies": cpr_result.anomalies,
            "cpr_rolling_avg": cpr_result.rolling_avg,
            "oi_change": {
                str(strike): {
                    "current_oi": c.current_oi,
                    "previous_oi": c.previous_oi,
                    "pct_change": c.pct_change if c.pct_change != float("inf") else "inf",
                    "flag": c.flag,
                }
                for strike, c in oi_result.changes.items()
            },
            "oi_significant": oi_result.significant,
            "flow_score": {
                "value": flow_result.value,
                "label": flow_result.label,
                "cpr_subscore": flow_result.cpr_score,
                "oi_subscore": flow_result.oi_score,
                "iv_skew_subscore": flow_result.iv_skew_score,
            },
        }

        _latest_snapshot[t] = snapshot
        return snapshot

    except Exception as e:
        logger.error(f"Retail flow compute error for {t}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
