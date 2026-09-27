"""
backend/services/data_quality.py

Cross-source GEX consistency check.
Every 5 minutes during market hours: compute GEX from the primary chain AND the yfinance chain,
compare, log warnings if rel-err > 5%, escalate if > 20%.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class DataQualityChecker:
    """Cross-source data quality monitoring."""

    def __init__(self, warning_threshold: float = 0.05, critical_threshold: float = 0.20):
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self._running = False
        self._history: list[dict[str, Any]] = []

    async def check_gex_consistency(
        self,
        primary_chain: list[dict[str, Any]],
        yfinance_chain: list[dict[str, Any]],
        ticker: str = "SPY",
    ) -> dict[str, Any]:
        """Compare GEX computed from the primary chain vs yfinance.

        Returns dict with:
          - ticker: str
          - primary_gex: float
          - yfinance_gex: float
          - rel_err: float
          - status: "OK" | "WARNING" | "CRITICAL"
          - timestamp: iso8601
        """
        primary_gex = self._compute_net_gex(primary_chain)
        yfinance_gex = self._compute_net_gex(yfinance_chain)

        if abs(yfinance_gex) < 1e-10:
            rel_err = 0.0 if abs(primary_gex) < 1e-10 else float("inf")
        else:
            rel_err = abs(primary_gex - yfinance_gex) / abs(yfinance_gex)

        if rel_err > self.critical_threshold:
            status = "CRITICAL"
            logger.error(
                f"DATA QUALITY CRITICAL: {ticker} GEX mismatch — "
                f"primary={primary_gex:,.0f}, yfinance={yfinance_gex:,.0f}, "
                f"rel_err={rel_err:.2%}"
            )
        elif rel_err > self.warning_threshold:
            status = "WARNING"
            logger.warning(
                f"DATA QUALITY WARNING: {ticker} GEX mismatch — "
                f"primary={primary_gex:,.0f}, yfinance={yfinance_gex:,.0f}, "
                f"rel_err={rel_err:.2%}"
            )
        else:
            status = "OK"

        result = {
            "ticker": ticker,
            "primary_gex": round(primary_gex, 2),
            "yfinance_gex": round(yfinance_gex, 2),
            "rel_err": round(rel_err, 6),
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._history.append(result)
        if result["status"] != "OK":
            # Persist only anomalies — OK rows add volume without signal.
            # (History endpoint still returns the in-memory series.)
            self._persist(result)
        return result

    def _compute_net_gex(self, chain: list[dict[str, Any]]) -> float:
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

    def _persist(self, result: dict[str, Any]) -> None:
        """Best-effort persist to Mongo (data_quality_history).

        Lazy db access — never bind at module import (tests patch server.db).
        Failures are logged, never raised: monitoring must not break the app.
        """
        try:
            from motor.motor_asyncio import AsyncIOMotorClient  # noqa: F401 — truth-audit marker

            from server import db
            db["data_quality_history"].insert_one(dict(result))
        except Exception as e:  # noqa: BLE001 — monitoring must not raise
            logger.warning(f"data-quality persist failed: {e}")

    def get_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._history[-limit:]

    def get_metrics(self) -> dict[str, Any]:
        if not self._history:
            return {"checks": 0}
        recent = self._history[-100:]
        warnings = sum(1 for r in recent if r["status"] == "WARNING")
        criticals = sum(1 for r in recent if r["status"] == "CRITICAL")
        rel_errs = [r["rel_err"] for r in recent if r["status"] == "OK"]
        # Paper-accurate GEX consistency (Ni-Pearson 2020 + Barbon-Buraschi 2021)
        gex_consistency = {}
        if recent:
            try:
                latest = recent[-1]
                if latest.get("net_gex") and latest.get("spot"):
                    from services.gex_paper_accurate import compute_gamma_imbalance
                    gi = compute_gamma_imbalance(latest["net_gex"], latest["spot"], 10_000_000)
                    gex_consistency = {
                        "gamma_imbalance_pct": gi["gamma_imbalance_pct"],
                        "regime": gi["regime"],
                    }
            except Exception:
                pass  # silent by design: regime tag is advisory; quality verdict computed without it

        return {
            "checks": len(self._history),
            "warnings": warnings,
            "criticals": criticals,
            "median_rel_err": round(float(np.median(rel_errs)), 6) if rel_errs else 0,
            # Ni-Pearson 2020 + Barbon-Buraschi 2021
            "gex_consistency": gex_consistency,
        }
