"""
Quantitative analytics service for Confluence Decoder.

Provides:
- GEX surface computation (strike × expiry)
- Historical GEX analysis
- Multi-ticker comparison
- Regime statistics
"""

import logging
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)


class GexSurfaceComputer:
    """Computes GEX surface (strike × expiry matrix)."""

    @staticmethod
    def compute_surface(
        spot: float,
        contracts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compute GEX surface from option chain."""
        strikes = sorted(set(c["strike"] for c in contracts))
        expiries = sorted(set(c["expiry"] for c in contracts))

        surface = np.zeros((len(strikes), len(expiries)))

        for i, strike in enumerate(strikes):
            for j, expiry in enumerate(expiries):
                # Sum GEX for all contracts at this strike/expiry
                gex = 0.0
                for c in contracts:
                    if c["strike"] == strike and c["expiry"] == expiry:
                        gamma = c.get("gamma", 0)
                        oi = c.get("oi", 0)
                        sign = 1 if c["type"] == "call" else -1
                        gex += gamma * oi * 100 * spot * spot * 0.01 * sign
                surface[i][j] = gex

        return {
            "strikes": strikes,
            "expiries": expiries,
            "surface": surface.tolist(),
            "spot": spot,
            "total_gex": float(np.sum(surface)),
            "max_gex_strike": strikes[int(np.argmax(np.sum(surface, axis=1)))] if strikes else 0,
            "min_gex_strike": strikes[int(np.argmin(np.sum(surface, axis=1)))] if strikes else 0,
        }


class HistoricalGexAnalyzer:
    """Analyzes historical GEX data."""

    @staticmethod
    def compute_regime_statistics(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute regime statistics from historical snapshots."""
        if not snapshots:
            return {"status": "no_data"}

        regimes = [s.get("regime", "unknown") for s in snapshots]
        spots = [s.get("spot", 0) for s in snapshots]
        total_gex = [s.get("total_gex", 0) for s in snapshots]
        net_gex = [s.get("net_gex", 0) for s in snapshots]

        # Regime distribution
        positive_count = sum(1 for r in regimes if r == "POSITIVE")
        negative_count = sum(1 for r in regimes if r == "NEGATIVE")
        total = len(regimes)

        # Regime changes
        changes = sum(1 for i in range(1, len(regimes)) if regimes[i] != regimes[i-1])

        # Price performance by regime
        positive_returns = []
        negative_returns = []

        for i in range(1, len(snapshots)):
            if spots[i-1] > 0:
                ret = (spots[i] - spots[i-1]) / spots[i-1] * 100
                if regimes[i-1] == "POSITIVE":
                    positive_returns.append(ret)
                elif regimes[i-1] == "NEGATIVE":
                    negative_returns.append(ret)

        return {
            "total_snapshots": total,
            "positive_pct": round(positive_count / total * 100, 1) if total > 0 else 0,
            "negative_pct": round(negative_count / total * 100, 1) if total > 0 else 0,
            "regime_changes": changes,
            "avg_return_positive_regime": round(float(np.mean(positive_returns)), 4) if positive_returns else 0,
            "avg_return_negative_regime": round(float(np.mean(negative_returns)), 4) if negative_returns else 0,
            "max_gex": max(total_gex) if total_gex else 0,
            "min_gex": min(total_gex) if total_gex else 0,
            "avg_net_gex": round(float(np.mean(net_gex)), 0) if net_gex else 0,
        }

    @staticmethod
    def compute_gex_correlation(
        ticker1_snapshots: List[Dict[str, Any]],
        ticker2_snapshots: List[Dict[str, Any]],
    ) -> float:
        """Compute GEX correlation between two tickers."""
        if not ticker1_snapshots or not ticker2_snapshots:
            return 0.0

        # Align by timestamp
        ts1 = {s.get("ts", ""): s.get("net_gex", 0) for s in ticker1_snapshots}
        ts2 = {s.get("ts", ""): s.get("net_gex", 0) for s in ticker2_snapshots}

        common_ts = sorted(set(ts1.keys()) & set(ts2.keys()))

        if len(common_ts) < 2:
            return 0.0

        vals1 = [ts1[ts] for ts in common_ts]
        vals2 = [ts2[ts] for ts in common_ts]

        if np.std(vals1) == 0 or np.std(vals2) == 0:
            return 0.0

        correlation = float(np.corrcoef(vals1, vals2)[0, 1])
        return round(correlation, 4)


class MultiTickerComparator:
    """Compares GEX across multiple tickers."""

    @staticmethod
    def compare_regimes(
        snapshots_by_ticker: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Compare current regimes across tickers."""
        result = {}

        for ticker, snapshots in snapshots_by_ticker.items():
            if not snapshots:
                continue

            latest = max(snapshots, key=lambda s: s.get("ts", ""))
            result[ticker] = {
                "regime": latest.get("regime", "unknown"),
                "spot": latest.get("spot", 0),
                "net_gex": latest.get("net_gex", 0),
                "total_gex": latest.get("total_gex", 0),
                "king_strike": latest.get("king_strike", 0),
            }

        # Count regimes
        positive = [t for t, d in result.items() if d["regime"] == "POSITIVE"]
        negative = [t for t, d in result.items() if d["regime"] == "NEGATIVE"]

        return {
            "tickers": result,
            "summary": {
                "positive": positive,
                "negative": negative,
                "consensus": "BULLISH" if len(positive) > len(negative) else "BEARISH" if len(negative) > len(positive) else "MIXED",
            },
        }
