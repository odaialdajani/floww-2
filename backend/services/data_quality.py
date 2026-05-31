"""
backend/services/data_quality.py

Cross-source GEX consistency check.
Every 5 minutes during market hours: compute GEX from Schwab chain AND yfinance chain,
compare, log warnings if rel-err > 5%, escalate if > 20%.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)


class DataQualityChecker:
    """Cross-source data quality monitoring."""

    def __init__(self, warning_threshold: float = 0.05, critical_threshold: float = 0.20):
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self._running = False
        self._history: List[Dict[str, Any]] = []

    async def check_gex_consistency(
        self,
        schwab_chain: List[Dict[str, Any]],
        yfinance_chain: List[Dict[str, Any]],
        ticker: str = "SPY",
    ) -> Dict[str, Any]:
        """Compare GEX computed from Schwab vs yfinance chains.

        Returns dict with:
          - ticker: str
          - schwab_gex: float
          - yfinance_gex: float
          - rel_err: float
          - status: "OK" | "WARNING" | "CRITICAL"
          - timestamp: iso8601
        """
        schwab_gex = self._compute_net_gex(schwab_chain)
        yfinance_gex = self._compute_net_gex(yfinance_chain)

        if abs(yfinance_gex) < 1e-10:
            rel_err = 0.0 if abs(schwab_gex) < 1e-10 else float("inf")
        else:
            rel_err = abs(schwab_gex - yfinance_gex) / abs(yfinance_gex)

        if rel_err > self.critical_threshold:
            status = "CRITICAL"
            logger.error(
                f"DATA QUALITY CRITICAL: {ticker} GEX mismatch — "
                f"Schwab={schwab_gex:,.0f}, yfinance={yfinance_gex:,.0f}, "
                f"rel_err={rel_err:.2%}"
            )
        elif rel_err > self.warning_threshold:
            status = "WARNING"
            logger.warning(
                f"DATA QUALITY WARNING: {ticker} GEX mismatch — "
                f"Schwab={schwab_gex:,.0f}, yfinance={yfinance_gex:,.0f}, "
                f"rel_err={rel_err:.2%}"
            )
        else:
            status = "OK"

        result = {
            "ticker": ticker,
            "schwab_gex": round(schwab_gex, 2),
            "yfinance_gex": round(yfinance_gex, 2),
            "rel_err": round(rel_err, 6),
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(result)
        return result

    def _compute_net_gex(self, chain: List[Dict[str, Any]]) -> float:
        """Compute net GEX from a chain (list of contract dicts)."""
        net_gex = 0.0
        for c in chain:
            gamma = c.get("gamma", 0)
            oi = c.get("oi", c.get("open_interest", 0))
            spot = c.get("spot", c.get("underlying_price", 0))
            is_call = c.get("type", "call") in ("call", "C", "c")
            sign = 1.0 if is_call else -1.0
            gex = sign * gamma * oi * 100 * spot * spot * 0.01
            net_gex += gex
        return net_gex

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._history[-limit:]

    def get_metrics(self) -> Dict[str, Any]:
        if not self._history:
            return {"checks": 0}
        recent = self._history[-100:]
        warnings = sum(1 for r in recent if r["status"] == "WARNING")
        criticals = sum(1 for r in recent if r["status"] == "CRITICAL")
        rel_errs = [r["rel_err"] for r in recent if r["status"] == "OK"]
        return {
            "checks": len(self._history),
            "warnings": warnings,
            "criticals": criticals,
            "median_rel_err": round(float(np.median(rel_errs)), 6) if rel_errs else 0,
        }
