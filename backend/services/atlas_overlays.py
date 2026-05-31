"""
backend/services/atlas_overlays.py

Computes overlay data for the Atlas candlestick chart.
Each function returns plotly-compatible overlay specs that the Dash UI
can render as horizontal lines, shaded regions, markers, or sub-charts.

All functions are pure (no side effects) and return deterministic output
for given input.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def compute_king_nodes(spot: float, contracts: List[Dict]) -> List[Dict]:
    """Compute King Node overlay data: top-3 |GEX| strikes.

    Returns list of {strike, magnitude, label} dicts, sorted by |magnitude| desc.
    """
    if not contracts or spot <= 0:
        return []
    try:
        from services.heatseeker import calc_node_lifecycle
        result = calc_node_lifecycle(spot, contracts, history=[])
        nodes = result.get("nodes", [])
        nodes_sorted = sorted(nodes, key=lambda n: abs(n.get("structural_weight", 0)), reverse=True)
        king_nodes = []
        for n in nodes_sorted[:3]:
            strike = n.get("strike", 0)
            weight = n.get("structural_weight", 0)
            if strike > 0:
                king_nodes.append({
                    "strike": strike,
                    "magnitude": abs(weight),
                    "label": f"KN {strike:.0f} ({abs(weight):.2f})",
                })
        return king_nodes
    except Exception as e:
        logger.warning(f"King node computation failed: {e}")
        return []


def compute_zero_gamma(spot: float, contracts: List[Dict]) -> Optional[float]:
    """Compute the zero-gamma level from GEX aggregation.

    Returns the strike where total GEX crosses zero, or None.
    """
    if not contracts or spot <= 0:
        return None
    try:
        from services.gex_aggregator import GexAggregator
        agg = GexAggregator()
        result = agg.compute(spot, contracts)
        crossings = result.get("zero_crossings", [])
        if crossings:
            closest = min(crossings, key=lambda c: abs(c - spot))
            return closest
        return None
    except Exception as e:
        logger.warning(f"Zero-gamma computation failed: {e}")
        return None


def compute_air_pockets(spot: float, contracts: List[Dict]) -> List[Dict]:
    """Compute Air Pocket regions: zones where |GEX| < 0.2 x median.

    Returns list of {lo, hi, label} dicts.
    """
    if not contracts or spot <= 0:
        return []
    try:
        from services.heatseeker import calc_air_pockets
        result = calc_air_pockets(spot, contracts)
        pockets = result.get("pockets", [])
        out = []
        for p in pockets:
            lo = p.get("lo", 0)
            hi = p.get("hi", 0)
            if hi > lo:
                out.append({
                    "lo": lo, "hi": hi,
                    "label": f"Air Pocket {lo:.0f}-{hi:.0f}",
                })
        return out
    except Exception as e:
        logger.warning(f"Air pocket computation failed: {e}")
        return []


def compute_anomaly_markers(
    timestamps: List[str],
    vpin_series: Optional[List[float]] = None,
    qi_series: Optional[List[float]] = None,
) -> List[Dict]:
    """Compute anomaly markers from the anomaly detector.

    Returns list of {timestamp, severity, score, label} dicts.
    """
    markers: List[Dict] = []
    if not timestamps:
        return markers
    vpin_series = vpin_series or []
    qi_series = qi_series or []
    try:
        from services.anomaly_detector import FlowAnomalyDetector
        detector = FlowAnomalyDetector()
        for i, ts in enumerate(timestamps):
            vpin = vpin_series[i] if i < len(vpin_series) else 0.0
            qi = qi_series[i] if i < len(qi_series) else 0.0
            result = detector.update(vpin, qi)
            if result.get("is_anomaly", False):
                markers.append({
                    "timestamp": ts,
                    "severity": result.get("severity", "medium"),
                    "score": result.get("anomaly_score", 0),
                    "label": f"Anomaly: {result.get('type', 'unknown')}",
                })
    except Exception as e:
        logger.warning(f"Anomaly marker computation failed: {e}")
    return markers


def _compute_alignment_score(spy_vals: List[float], qqq_vals: List[float], spx_vals: List[float]) -> float:
    """Compute a 0-100 alignment score from three ZG series."""
    if not spy_vals or not qqq_vals or not spx_vals:
        return 0.0
    try:
        def direction(vals: List[float]) -> int:
            if len(vals) < 2:
                return 0
            return 1 if vals[-1] > vals[0] else (-1 if vals[-1] < vals[0] else 0)
        dirs = [direction(spy_vals), direction(qqq_vals), direction(spx_vals)]
        if all(d == dirs[0] and d != 0 for d in dirs):
            return 85.0
        non_zero = [d for d in dirs if d != 0]
        if len(non_zero) >= 2 and len(set(non_zero)) <= 1:
            return 60.0
        return 25.0
    except Exception:
        return 0.0


def compute_trinity_sparkline(
    spy_zg: Optional[List[Dict]] = None,
    qqq_zg: Optional[List[Dict]] = None,
    spx_zg: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Compute Trinity alignment sparkline data.

    Returns {timestamps, spy_vals, qqq_vals, spx_vals, score}.
    """
    result: Dict[str, Any] = {"timestamps": [], "spy_vals": [], "qqq_vals": [], "spx_vals": [], "score": 0}
    try:
        series = spy_zg or qqq_zg or spx_zg or []
        if not series:
            return result
        result["timestamps"] = [d.get("ts", d.get("timestamp", "")) for d in series]
        if spy_zg:
            result["spy_vals"] = [d.get("level", d.get("value", 0)) for d in spy_zg]
        if qqq_zg:
            result["qqq_vals"] = [d.get("level", d.get("value", 0)) for d in qqq_zg]
        if spx_zg:
            result["spx_vals"] = [d.get("level", d.get("value", 0)) for d in spx_zg]
        result["score"] = _compute_alignment_score(
            result["spy_vals"], result["qqq_vals"], result["spx_vals"]
        )
    except Exception as e:
        logger.warning(f"Trinity sparkline computation failed: {e}")
    return result


def build_all_overlays(
    spot: float = 0,
    contracts: Optional[List[Dict]] = None,
    timestamps: Optional[List[str]] = None,
    vpin_series: Optional[List[float]] = None,
    qi_series: Optional[List[float]] = None,
    spy_zg: Optional[List[Dict]] = None,
    qqq_zg: Optional[List[Dict]] = None,
    spx_zg: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Build all overlay data in one call.

    Returns dict with keys: king_nodes, zero_gamma, air_pockets,
    anomaly_markers, trinity_sparkline.
    """
    contracts = contracts or []
    timestamps = timestamps or []
    return {
        "king_nodes": compute_king_nodes(spot, contracts),
        "zero_gamma": compute_zero_gamma(spot, contracts),
        "air_pockets": compute_air_pockets(spot, contracts),
        "anomaly_markers": compute_anomaly_markers(timestamps, vpin_series, qi_series),
        "trinity_sparkline": compute_trinity_sparkline(spy_zg, qqq_zg, spx_zg),
    }
