"""API routes for data providers (public-API-only since 2026-09-03)."""

import logging
import os

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("/status")
async def get_data_status():
    """Get status of all data providers."""
    try:
        from data_providers import FINNHUB_API_KEY, POLYGON_API_KEY, DataAggregator
        agg = DataAggregator()
        status = agg.get_status()
        return {
            "providers": status,
            "primary": "public_api",
            "retired": ["schwab", "alphavantage"],
            "env_vars_set": {
                "PUBLIC_API_KEY": bool(os.environ.get("PUBLIC_API_KEY", "")),
                "FINNHUB_API_KEY": bool(FINNHUB_API_KEY),
                "POLYGON_API_KEY": bool(POLYGON_API_KEY),
            }
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/health")
async def get_data_health():
    """Get detailed health metrics for all data providers including success rates and alerts."""
    try:
        from services.meta_observability import provider_monitor

        health = provider_monitor.get_health()

        # Update Prometheus gauges
        provider_monitor.update_prometheus()

        # Public-path budget gate status (rate-limit shield observability)
        try:
            from services.public_budget import budget as _pub_budget
            health["public_budget"] = _pub_budget.status()
        except Exception:
            pass

        return health
    except Exception as e:
        return {"error": str(e)}


@router.get("/{ticker}")
async def get_ticker_data(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
    taps: bool = True,
    mode: str = Query("day", pattern="^(day|swing|scalp)$"),
    dte: int | None = Query(None, ge=0, le=30),
    scalp: bool = Query(False),
    max_strikes: int = Query(80, ge=20, le=200),
):
    """Get full heatmap data for a ticker (compatible with frontend data fetch)."""
    from server import build_heatmap
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    payload = await build_heatmap(t, expiries, taps, mode, dte, scalp, max_strikes)
    # Exposure-change alerts (VEX walls / charm pins vs last grid snapshot).
    # Fail-open: evaluation or persist must never break the heatmap response.
    # Grids live nested (payload["grid"]["vex_grid"]) — top-level accepted too.
    try:
        from services import exposure_alerts as _ea
        from services import flow_alerts as _fa
        from services.duckdb_engine import db as _duckdb

        nested = payload.get("grid", {}) if isinstance(payload.get("grid"), dict) else {}
        grids = {
            "vex_grid": nested.get("vex_grid") or payload.get("vex_grid") or {},
            "charm_grid": nested.get("charm_grid") or payload.get("charm_grid") or {},
        }
        if grids["vex_grid"] or grids["charm_grid"]:
            _fa.init_flow_alert_tables(_duckdb)
            try:
                from routes.vpin import snapshot_vpin_state
                _vpin_state = snapshot_vpin_state(t)
            except Exception:
                _vpin_state = None
            events = _ea.evaluate_ticker(
                t, {"vex_grid": grids["vex_grid"], "charm_grid": grids["charm_grid"]},
                float(payload.get("spot") or 0), vpin_state=_vpin_state)
            if events:
                kept = _fa.dedup_filter(_duckdb, events)
                if kept:
                    _fa.persist_alerts(_duckdb, kept)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("exposure alerts skipped for %s: %s", t, e)
    return payload


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """Get spot price — Public API first, emergency fallbacks after."""
    try:
        from services.public_api_adapter import fetch_spot_from_public_api
        spot = await fetch_spot_from_public_api(ticker.upper())
        if spot and spot > 0:
            return {"ticker": ticker.upper(), "price": spot, "source": "public_api"}
        from data_providers import DataAggregator
        agg = DataAggregator()
        spot_data = await agg.get_spot_price(ticker.upper())
        if spot_data:
            return {"ticker": ticker.upper(), **spot_data}
        return {"ticker": ticker.upper(), "error": "No data available", "price": None}
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e), "price": None}


@router.get("/full/{ticker}")
async def get_full_data(
    ticker: str,
    include_news: bool = True,
    include_technicals: bool = False,
):
    """Get full aggregated data for a ticker (spot + news + earnings + technicals)."""
    try:
        from data_providers import DataAggregator
        agg = DataAggregator()
        result = await agg.get_full_quote(ticker.upper())

        if not include_news:
            result["news"] = []
        if not include_technicals:
            result["technicals"] = {}

        return result
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e)}


@router.get("/news/{ticker}")
async def get_news(ticker: str, count: int = Query(10, ge=1, le=50)):
    """Get news for a ticker from Finnhub."""
    try:
        from data_providers import FinnhubProvider
        provider = FinnhubProvider()
        news = await provider.get_news(ticker.upper(), count=count)
        return {"ticker": ticker.upper(), "news": news, "count": len(news)}
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e), "news": []}
