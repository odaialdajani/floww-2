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
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


# ── DuckDB fallback helper ───────────────────────────────────────────

async def _duckdb_fallback(ticker: str) -> dict[str, Any] | None:
    """
    Serve last known data from DuckDB when live fetch fails.
    Returns a minimal response dict or None if nothing cached.
    """
    try:
        from services.duckdb_engine import db as duckdb_engine
        rows = await duckdb_engine.query_async(
            """SELECT symbol, bid, ask, last, volume, oi, timestamp, data_source
               FROM ticks
               WHERE symbol = ? AND data_source = 'public_api'
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
        # DuckDB TIMESTAMP columns come back as NAIVE datetimes; subtracting them
        # from a tz-aware now() raises TypeError, which the broad except below
        # swallowed → the fallback silently returned None even with cached data.
        if ts is not None and getattr(ts, "tzinfo", None) is None:
            ts = ts.replace(tzinfo=UTC)
        age_s = (datetime.now(UTC) - ts).total_seconds() if ts else None
        return {
            "ticker": row.get("symbol", ticker),
            "spot": row.get("last") or row.get("bid") or 0,
            "bid": row.get("bid", 0),
            "ask": row.get("ask", 0),
            "volume": row.get("volume", 0),
            "oi": row.get("oi", 0),
            "ts": ts.isoformat() if ts else None,
            "data_source": row.get("data_source", "public_api"),
            "storage_source": "duckdb",
            "data_fallback": True,
            "stale_age_s": round(age_s, 1) if age_s is not None else None,
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

# NOTE: GET /tickers lived here too, but server.py registers /api/tickers
# first (line ~1919 executes before this router is included), so this copy
# was dead. Removed 2026-09-27; the live handler is server.list_tickers.


@router.get("/tickers/all", response_model=None)
async def list_all_tickers(
    limit: int = Query(12000, ge=100, le=40000),
    page: int = Query(1, ge=1, le=1000),
    refresh: bool = Query(False),
):
    """Provider stock/fund catalog; custom scan lists do not restrict browsing."""
    from services.market_catalog import get_catalog

    catalog = await get_catalog(refresh=refresh)
    symbols = [row["symbol"] for row in catalog["instruments"]]
    start = (page - 1) * limit
    return {**{k: v for k, v in catalog.items() if k != "instruments"},
            "tickers": symbols[start:start + limit], "page": page, "limit": limit,
            "has_more": start + limit < len(symbols), "cached": True}


@router.get("/heatmap/{ticker}")
async def heatmap(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
    taps: bool = True,
    mode: str = Query("day", pattern="^(day|swing|scalp)$"),
    dte: int | None = Query(None, ge=0, le=30),
    scalp: bool = Query(False),
    max_strikes: int = Query(80, ge=20, le=200),
    expiry_scope: str = Query("loaded", pattern="^(loaded|next)$"),
):
    from server import build_heatmap
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    if expiry_scope == "next":
        if dte is not None or scalp or mode != "day":
            raise HTTPException(422, "Next listed cannot be combined with DTE, scalp or swing")
        return await build_heatmap(t, expiries, taps, mode, dte, scalp, max_strikes, expiry_scope="next")
    return await build_heatmap(t, expiries, taps, mode, dte, scalp, max_strikes)


@router.get("/trinity")
async def trinity(
    tickers: str = Query(None),
    mode: str = Query("day", pattern="^(day|swing)$"),
    dte: int | None = Query(None, ge=0, le=30),
):
    from server import TRINITY, build_heatmap
    if tickers is None:
        tickers = ",".join(TRINITY)
    syms = [t.strip() for t in tickers.split(",") if t.strip()]
    out: dict[str, Any] = {}
    results = await asyncio.gather(
        *[build_heatmap(s, 3, True, mode, dte) for s in syms],
        return_exceptions=True,
    )
    for sym, res in zip(syms, results, strict=False):
        if isinstance(res, Exception):
            out[sym] = {"error": str(res)}
        else:
            out[sym] = res

    regimes = [r["nodes"]["regime"] for r in out.values() if isinstance(r, dict) and r.get("nodes")]
    biases = []
    for r in out.values():
        if isinstance(r, dict) and r.get("patterns"):
            # Pattern dicts come from services.gex_core.detect_patterns whose
            # schema carries "direction"/"confidence"; older
            # gex_server_utils entries carried "bias". Read defensively so a
            # pattern without either key never 500s the alignment block.
            biases.extend(
                b for b in (
                    p.get("bias") or p.get("direction")
                    for p in r["patterns"] if isinstance(p, dict)
                ) if b
            )

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
        "asof": datetime.now(UTC).isoformat(),
    }


@router.get("/spot/{ticker}")
async def spot(ticker: str):
    from server import fetch_spot_and_chains_merged
    from services.market_provenance import spot_provenance
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
        raise HTTPException(503, f"Live data unavailable for {ticker} and no cache") from None
    observation = spot_provenance(raw, datetime.now(UTC))
    return {"ticker": t, "spot": raw.get("spot"), "ts": observation["event_time"],
            "fetched_at": observation["received_at"], "data_source": observation["source"],
            "status": observation["status"], "stale": observation["status"] == "stale",
            "data_fallback": bool(raw.get("stale") or observation["source"] in ("yfinance-fallback", "public-session-close"))}


@router.get("/chain/{ticker}")
async def chain(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
    min_oi: int = Query(0, ge=0),
    expiry: str | None = None,
    dte_max: int | None = Query(None, ge=0, le=365),
):
    from server import _sanitize, fetch_spot_and_chains_merged
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
    from services.chain_readings import chain_readings
    rows = chain_readings(contracts, spot, t)
    # Same canonical exposure as /api/public/chain (C3 wiring): identical
    # values for standard contracts, quarantine+basis for the rest, so the
    # two chain routes never disagree on a row.
    from services.triad_projection import annotate_contract_exposure
    rows = annotate_contract_exposure(rows, spot)
    # Apply DTE filter if specified
    if dte_max is not None:
        rows = [r for r in rows if r.get("dte") is not None and r["dte"] <= dte_max]
    return _sanitize({"ticker": t, "spot": raw["spot"], "expiries": raw.get("expiries", []), "rows": rows, "count": len(rows),
                      "gex_unit": "USD per 1% spot move (sign*gamma*OI*100*spot^2*0.01; +call/-put)",
                      **{key: raw.get(key) for key in ("data_source", "event_time", "fetched_at", "spot_source",
                                                      "spot_event_time", "spot_fetched_at", "stale", "cache_age_s")}})


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


@router.get("/heatmap/{ticker}/range-analytics", response_model=None)
async def heatmap_range_analytics(
    ticker: str,
    min_dte: int = Query(14, ge=0, le=365),
    max_dte: int = Query(60, ge=0, le=365),
    as_of: str | None = Query(
        None, description="Owning NY date; must equal today — a current fetch "
                          "can never recreate a historical observation"),
    persist: bool = Query(
        False, description="Opt-in: persist the admitted owning envelope in the "
                           "recorder store. Default False — reads never write."),
):
    """Owning 14–60 DTE analytical range map (contract range-analytics.v1).

    ADDITIVE and distinct from coverage-read.v1 (an expiry LISTING verdict)
    and from the existing `dte le=30` display envelope on /heatmap. Returns
    the owned axes/cells/basis/units/coverage/clocks envelope from
    services.solstice_range_analytics. Refusals stay machine-readable:
    REVERSED_WINDOW → 422; vendor/listing unavailable → 502; zero admitted
    expiries → 200 with status "refused" (an honest empty window answer).
    Execution policy is unchanged — this is research data, not entry
    permission. A partial map is research only and never execution-eligible.
    """
    from fastapi.responses import JSONResponse

    from services.solstice_range_analytics import CONTRACT_VERSION, fetch_range_analytics

    t = ticker.strip().upper()
    if min_dte > max_dte:
        # Structured JSONResponse, same reason as coverage-read.v1: the global
        # handler stringifies dict details, burying the refusal code.
        return JSONResponse(status_code=422, content={
            "error": "REVERSED_WINDOW",
            "message": f"min_dte {min_dte} is above max_dte {max_dte} — "
                       "no expiry can satisfy a reversed window.",
            "version": CONTRACT_VERSION,
        })
    conn = None
    if persist:
        try:
            from services.duckdb_engine import db as eng
            conn = eng.conn if hasattr(eng, "conn") else None
        except Exception:
            conn = None
        if conn is None:
            return JSONResponse(status_code=503, content={
                "error": "recorder_unavailable",
                "message": "persist=true requires the owning recorder store; "
                           "it is not connected.",
                "version": CONTRACT_VERSION,
            })
    envelope = await fetch_range_analytics(t, min_dte, max_dte, as_of=as_of,
                                           persist_conn=conn)
    if envelope.get("status") == "refused" and \
            "VENDOR_UNAVAILABLE" in (envelope.get("refusals") or []):
        return JSONResponse(status_code=502, content=envelope)
    return envelope

