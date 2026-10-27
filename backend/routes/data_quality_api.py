"""Data quality endpoints — GSD Phase 3.4.

Exposes the cross-source GEX consistency check as a read-only API.
Fetches the same ticker from cvserver and yfinance, compares net GEX,
returns OK/WARNING/CRITICAL with rel_err. History accumulates per-process
for spot-checking drift.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Query

from services.data_quality import DataQualityChecker

log = logging.getLogger("routes.data_quality")

router = APIRouter()

_checker = DataQualityChecker()


async def _fetch_chain_yfinance(ticker: str, max_expiries: int) -> list[dict[str, Any]]:
    """Fetch chain via the yfinance+Databento legacy path."""
    from server import fetch_spot_and_chains
    raw = await asyncio.to_thread(
        fetch_spot_and_chains, ticker, max_expiries=max_expiries
    )
    return (raw or {}).get("contracts", [])


async def _fetch_chain_cvserver(ticker: str, max_expiries: int) -> list[dict[str, Any]]:
    """Fetch chain via cvserver (CVForge)."""
    from services.cvserver_client import fetch_chain_from_cvserver
    data = await fetch_chain_from_cvserver(ticker, max_expiries=max_expiries)
    return (data or {}).get("contracts", [])


@router.get("/data-quality/history")
async def data_quality_history(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    """Recent cross-source consistency checks (per-process).

    Registered BEFORE /data-quality/{ticker}: FastAPI matches routes in
    registration order, so the literal path must be declared first or the
    word "history" is captured as a ticker (root-reproduced 2026-10-26).
    """
    return {"history": _checker.get_history(limit=limit),
            "metrics": _checker.get_metrics()}


@router.get("/data-quality/{ticker}")
async def data_quality(
    ticker: str,
    max_expiries: int = Query(2, ge=1, le=6),
) -> dict[str, Any]:
    """Cross-source GEX consistency for a ticker (cvserver vs yfinance).

    Read-only monitoring; does not gate any data path. Repeated calls
    build a per-process history queryable via /data-quality/history.
    """
    t = ticker.strip().upper()
    try:
        cv_task = _fetch_chain_cvserver(t, max_expiries)
        yf_task = _fetch_chain_yfinance(t, max_expiries)
        cv_chain, yf_chain = await asyncio.gather(cv_task, yf_task, return_exceptions=True)

        if isinstance(cv_chain, BaseException):
            log.warning(f"data-quality: cvserver fetch failed for {t}: {cv_chain}")
            cv_chain = []
        if isinstance(yf_chain, BaseException):
            log.warning(f"data-quality: yfinance fetch failed for {t}: {yf_chain}")
            yf_chain = []

        # A single-sided comparison is meaningless: an empty source yields
        # gex=0 on that side, which reads as a false "OK" (rel_err can even be
        # 1.0 or 0.0 by accident). Require both sides populated.
        if not cv_chain or not yf_chain:
            return {"ticker": t, "status": "INSUFFICIENT_DATA", "rel_err": None,
                    "cv_contracts": len(cv_chain), "yf_contracts": len(yf_chain),
                    "detail": "cross-source check needs both sources populated"}

        result = await _checker.check_gex_consistency(cv_chain, yf_chain, t)
        result["cv_contracts"] = len(cv_chain)
        result["yf_contracts"] = len(yf_chain)
        return result
    except Exception as e:
        log.error(f"data-quality check failed for {t}: {e}", exc_info=True)
        return {"ticker": t, "status": "ERROR", "error": str(e)}

