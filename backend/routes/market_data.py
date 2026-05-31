"""
backend/routes/market_data.py

Market data routes: tickers, heatmap, trinity, spot, chain, gex-timeframes, uoa.
Uses lazy imports from server.py to avoid circular dependencies.

Fallback strategy:
  - Live fetch (yfinance/Databento) is tried first.
  - On failure, DuckDB cached ticks are served with a data_fallback flag.
  - Frontend reads the flag and shows "Stale Data" badge.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


# ── DuckDB fallback helper ───────────────────────────────────────────

async def _duckdb_fallback(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Serve last known data from DuckDB when live fetch fails.
    Returns a minimal response dict or None if nothing cached.
    """
    try:
        from services.duckdb_engine import db as duckdb_engine
        rows = await duckdb_engine.query_async(
            """SELECT symbol, bid, ask, last, volume, oi, timestamp
               FROM ticks
               WHERE symbol = ?
               ORDER BY timestamp DESC
               LIMIT 1""",
            [ticker],
        )
        if not rows:
            return None
        row = rows[0]
        ts = row.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        age_s = (datetime.now(timezone.utc) - ts).total_seconds() if ts else None
        return {
            "ticker": row.get("symbol", ticker),
            "spot": row.get("last") or row.get("bid") or 0,
            "bid": row.get("bid", 0),
            "ask": row.get("ask", 0),
            "volume": row.get("volume", 0),
            "oi": row.get("oi", 0),
            "ts": ts.isoformat() if ts else None,
            "data_source": "duckdb_fallback",
            "data_fallback": True,
            "stale_age_s": round(age_s, 1) if age_s else None,
        }
    except Exception:
        return None


# ── Tick cache endpoint (for offline-first frontend) ─────────────────

@router.get("/tick-cache/{ticker}")
async def tick_cache(ticker: str):
    """
    Lightweight endpoint for the offline-first data layer.
    Returns the latest tick from DuckDB (fast, always available).
    Frontend uses this as fallback when live endpoints fail.
    """
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    result = await _duckdb_fallback(t)
    if result is None:
        raise HTTPException(404, f"No cached tick data for {ticker}")
    return result


# ── Existing routes (with DuckDB fallback on spot) ──────────────────

@router.get("/tickers")
async def list_tickers():
    from server import DEFAULT_TICKERS, POPULAR_UNIVERSE, TRINITY
    return {
        "trinity": TRINITY,
        "default": DEFAULT_TICKERS,
        "popular": POPULAR_UNIVERSE,
    }


@router.get("/heatmap/{ticker}")
async def heatmap(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
    taps: bool = True,
    mode: str = Query("day", pattern="^(day|swing|scalp)$"),
    dte: Optional[int] = Query(None, ge=0, le=30),
    scalp: bool = Query(False),
):
    from server import build_heatmap
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    return await build_heatmap(t, expiries, taps, mode, dte, scalp)


@router.get("/trinity")
async def trinity(
    tickers: str = Query(None),
    mode: str = Query("day", pattern="^(day|swing)$"),
    dte: Optional[int] = Query(None, ge=0, le=30),
):
    from server import TRINITY, build_heatmap
    if tickers is None:
        tickers = ",".join(TRINITY)
    syms = [t.strip() for t in tickers.split(",") if t.strip()]
    out: Dict[str, Any] = {}
    results = await asyncio.gather(
        *[build_heatmap(s, 3, True, mode, dte) for s in syms],
        return_exceptions=True,
    )
    for sym, res in zip(syms, results):
        if isinstance(res, Exception):
            out[sym] = {"error": str(res)}
        else:
            out[sym] = res

    regimes = [r["nodes"]["regime"] for r in out.values() if isinstance(r, dict) and r.get("nodes")]
    biases = []
    for r in out.values():
        if isinstance(r, dict) and r.get("patterns"):
            biases.extend(p["bias"] for p in r["patterns"])

    if regimes:
        most_regime = max(set(regimes), key=regimes.count)
        confluence = regimes.count(most_regime) / len(regimes)
    else:
        most_regime = "unknown"
        confluence = 0

    return {
        "tickers": out,
        "alignment": {
            "regime": most_regime,
            "confluence": round(confluence, 2),
            "biases": list(set(biases)),
            "verdict": (
                "full_alignment" if confluence == 1 and regimes else
                "partial_alignment" if confluence >= 0.66 else
                "divergence"
            ),
        },
        "asof": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/spot/{ticker}")
async def spot(ticker: str):
    from datetime import datetime, timezone

    from server import fetch_spot_and_chains_merged
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    try:
        raw = await fetch_spot_and_chains_merged(t, 1)
    except Exception:
        # Live fetch failed — try DuckDB fallback
        fallback = await _duckdb_fallback(t)
        if fallback:
            return fallback
        raise HTTPException(503, f"Live data unavailable for {ticker} and no cache")
    return {"ticker": t, "spot": raw.get("spot", 0), "ts": datetime.now(timezone.utc).isoformat(), "data_source": "live"}


@router.get("/chain/{ticker}")
async def chain(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
    min_oi: int = Query(0, ge=0),
    expiry: Optional[str] = None,
    dte_max: Optional[int] = Query(None, ge=0, le=365),
):
    from bs_greeks import bs_charm, bs_vanna
    from server import DIV_YIELD, _sanitize, fetch_spot_and_chains_merged
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    if not raw.get("contracts"):
        raise HTTPException(404, f"No options data for {ticker}")
    contracts = raw["contracts"]
    if expiry:
        contracts = [c for c in contracts if c.get("expiry") == expiry]
    if min_oi:
        contracts = [c for c in contracts if (c.get("oi", 0) or c.get("open_interest", 0)) >= min_oi]
    spot = raw["spot"]
    rows = []
    for c in contracts:
        gamma = c.get("gamma", 0)
        oi = c.get("oi", c.get("open_interest", 0))
        gex = gamma * oi * 100 * spot * (1 if c["type"] == "call" else -1)
        # Compute T (time to expiry in years) from expiry date string
        expiry_str = c.get("expiry", "")
        T = 0.0
        if expiry_str and spot > 0:
            try:
                exp_date = datetime.strptime(expiry_str, "%Y-%m-%d")
                T = max(0.0, (exp_date - datetime.now()).total_seconds() / (365.25 * 86400))
            except (ValueError, TypeError):
                T = 0.0
        strike = c["strike"]
        iv = c.get("iv", 0)
        q = DIV_YIELD.get(t, 0.0)
        vanna = bs_vanna(spot, strike, T, iv, q=q) if spot > 0 and iv > 0 and T > 0 else 0
        charm = bs_charm(spot, strike, T, iv, q=q, kind=c["type"]) if spot > 0 and iv > 0 and T > 0 else 0
        moneyness_pct = ((spot - strike) / spot * 100) if spot > 0 else 0
        dte_val = max(1, int(T * 365.25)) if T > 0 else 0
        rows.append({
            "type": c["type"],
            "strike": c["strike"],
            "expiry": c["expiry"],
            "iv": c.get("iv", 0),
            "delta": c.get("delta", 0),
            "gamma": c.get("gamma", 0),
            "vega": c.get("vega", 0),
            "theta": c.get("theta", 0),
            "vanna": vanna,
            "charm": charm,
            "moneyness_pct": moneyness_pct,
            "dte": dte_val,
            "oi": c.get("oi", c.get("open_interest", 0)),
            "volume": c.get("volume", 0),
            "bid": c.get("bid", 0),
            "ask": c.get("ask", 0),
            "gex": gex,
        })
    # Apply DTE filter if specified
    if dte_max is not None:
        rows = [r for r in rows if r.get("dte", 0) <= dte_max]
    return _sanitize({"ticker": t, "spot": raw["spot"], "expiries": raw.get("expiries", []), "rows": rows, "count": len(rows)})


@router.get("/gex-timeframes/{ticker}")
async def gex_timeframes(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
):
    from server import _sanitize, fetch_spot_and_chains_merged
    from services.gex_history import calc_gex_timeframes
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    spot = raw.get("spot", 0)
    if not spot or not raw.get("contracts"):
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_gex_timeframes(spot, raw["contracts"], t)
    return _sanitize(result)


@router.get("/uoa/{ticker}")
async def uoa(
    ticker: str,
    min_premium: float = Query(100000, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    from server import _sanitize, fetch_spot_and_chains_merged
    from services.uoa import calc_uoa
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, 4)
    spot = raw.get("spot", 0)
    if not spot or not raw.get("contracts"):
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_uoa(spot, raw["contracts"], t, min_premium, limit)
    return _sanitize(result)
