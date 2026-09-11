"""
backend/routes/flowseeker.py

API routes for Skylit-parity Flowseeker — live options flow + drilldown + chain + screen.
Uses CVForge's cvserver API for real-time options data (32 expirations, 171 strikes).
Falls back to yfinance when CVForge is unavailable.
"""

import asyncio
import json
import logging
import math
import os
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Query
from pymongo import UpdateOne

from services.flowseeker import contract_drilldown, fetch_live_flow_with_meta

logger = logging.getLogger(__name__)

# ── CVForge cvserver config ──
# Use the remote cvserver endpoint (same as screener project)
CVFORGE_URL = os.environ.get("CVSERVER_URL", "https://tap.convexvalue.com/api/data/mcp")
CVFORGE_API_KEY = os.environ.get("CVSERVER_API_KEY", "")
CVFORGE_TIMEOUT = 15.0  # seconds

# ── Cache ──
_chain_cache: dict[str, tuple[float, dict]] = {}
# Long-lived-process guard: unbounded per-symbol caches leak memory. Oldest
# entries evicted first (insertion-ordered dict).
_CHAIN_CACHE_MAX = int(os.environ.get("FLOWW_CHAIN_CACHE_MAX", "500"))


def _remember_chain(sym: str, data: dict) -> None:
    """Insert into _chain_cache with LRU-ish eviction at _CHAIN_CACHE_MAX."""
    _chain_cache[sym] = (time.time(), data)
    while len(_chain_cache) > _CHAIN_CACHE_MAX:
        oldest = next(iter(_chain_cache))
        del _chain_cache[oldest]


# 10 min — per-ticker chains share a ~5-call/hour budget slice with a free
# yfinance fallback; a 2-min TTL would let one open chart tab spend it all.
CACHE_TTL = 600


def _safe_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


# ── CVForge → frontend format transformation ──

# Frontend expects these params and order:
_FRONTEND_PARAMS = ["strike", "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility"]

def _transform_cvforge_response(raw: dict, symbol: str) -> dict:
    """
    Transform CVForge cvserver response to the format the FlowseekerProTab expects.
    CVForge:  params [expiration_date, strike_price, contract_type, iv, delta, gamma, theta, vega,
                       bid, ask, midpoint, open_interest, day_volume, underlying_price]
              strikes [strike, [call_vals(14)], [put_vals(14)]]
    Frontend: params [strike, bid, ask, lastPrice, volume, openInterest, impliedVolatility]
              strikes [strike, [call_vals(7)], [put_vals(7)]]
    """
    cv_params = raw.get("params", [])

    # Build cv_param_name → index mapping
    cv_idx = {name: i for i, name in enumerate(cv_params)}

    # Map frontend field names to CVForge param names and default indices
    # Frontend expects: strike, bid, ask, lastPrice, volume, openInterest, impliedVolatility
    # CVForge has:      strike_price, bid, ask, midpoint(bid+ask)/2, open_interest, implied_volatility
    field_map = {
        "bid": "bid",
        "ask": "ask",
        "lastPrice": "midpoint",  # Use midpoint as last price
        "volume": "day_volume",
        "openInterest": "open_interest",
        "impliedVolatility": "implied_volatility",
    }

    def extract_vals(call_or_put_vals: list) -> list:
        """Extract 7 frontend fields from a 14-element CVForge values array."""
        result = []
        for front_name in _FRONTEND_PARAMS:
            if front_name == "strike":
                continue  # strike is s[0], not in vals
            cv_name = field_map.get(front_name, front_name)
            idx = cv_idx.get(cv_name)
            if idx is not None and idx < len(call_or_put_vals):
                result.append(_safe_float(call_or_put_vals[idx]))
            else:
                result.append(None)
        return result

    transformed_chain = []
    for exp in raw.get("chain", []):
        exp_strikes = []
        for strike_data in exp.get("strikes", []):
            if not strike_data or len(strike_data) < 3:
                continue
            strike_price = strike_data[0]
            call_vals = extract_vals(strike_data[1]) if len(strike_data) > 1 else []
            put_vals = extract_vals(strike_data[2]) if len(strike_data) > 2 else []
            exp_strikes.append([strike_price, call_vals, put_vals])
        transformed_chain.append({
            "expiration": exp.get("expiration", ""),
            "strikes": exp_strikes,
        })

    return {
        "symbol": symbol.upper(),
        "params": _FRONTEND_PARAMS,
        "chain": transformed_chain,
    }


async def _cvforge_chain(symbol: str, fields: list[str] | None = None) -> dict | None:
    """
    Fetch options chain from CVForge's cvserver API via MCP JSON-RPC.
    Transforms response to match frontend's expected format:
      params: ["strike", "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility"]
      strikes: [strike, [call_vals], [put_vals]]
    Returns None on failure (caller should fallback to yfinance).
    """
    if not fields:
        fields = [
            "expiration_date", "strike_price", "contract_type",
            "implied_volatility", "open_interest", "underlying_price",
        ]
    if not CVFORGE_API_KEY:
        logger.debug("cvforge: no API key, skipping")
        return None

    # Map yfinance-style index symbols to cvserver format
    _sym_map = {"^SPX": "I:SPX", "^NDX": "I:NDX", "^RUT": "I:RUT", "^VIX": "I:VIX"}
    cv_symbol = _sym_map.get(symbol.upper(), symbol.upper())

    # Budget gate — chains have a free yfinance fallback, so when the chain
    # slice of the hourly cvforge budget is spent we degrade instead of
    # burning calls the market-wide scan needs.
    if not _budget_take("chain"):
        logger.info("cvforge chain %s skipped — hourly budget slice spent", symbol)
        return None

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CVFORGE_API_KEY}",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "get_chain",
            "arguments": {
                "symbol": cv_symbol,
                "params": fields,
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(CVFORGE_URL, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"cvforge chain: HTTP {resp.status_code} for {symbol}")
                return None
            result = resp.json()
            if "error" in result:
                logger.warning(f"cvforge chain: error for {symbol}: {result['error']}")
                return None
            # Extract text content from MCP response
            content = result.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                raw = json.loads(content[0]["text"])
            else:
                raw = result.get("result", {})

            # Transform CVForge format → frontend-expected format
            return _transform_cvforge_response(raw, symbol)
    except Exception as e:
        logger.warning(f"cvforge chain: error for {symbol}: {e}")
        return None


def _yfinance_chain_sync(sym: str, fields: list[str]) -> dict:
    """Synchronous yfinance fallback."""
    import yfinance as yf
    t = yf.Ticker(sym)
    exps = list(t.options)[:6]
    if not exps:
        return {"symbol": sym, "params": ["strike"] + fields, "chain": []}
    result = []
    for exp in exps:
        try:
            oc = t.option_chain(exp)
            # Strike-index the puts ONCE per expiry — the old code ran a full
            # DataFrame boolean scan per field per strike (O(strikes²·fields)).
            # 2026-08-22: to_dict('index') replaces per-row iterrows —
            # builds the strike→row map in one vectorized C pass.
            puts_by_strike = oc.puts.set_index("strike").to_dict("index") if not oc.puts.empty else {}
            strikes_out = []
            for row in oc.calls.itertuples(index=False):
                strike = float(getattr(row, "strike", 0) or 0)
                cv, pv = [], []
                pr = puts_by_strike.get(strike)
                for f in fields:
                    v1 = getattr(row, f, None)
                    v2 = pr.get(f) if pr is not None else None
                    cv.append(_safe_float(v1))
                    pv.append(_safe_float(v2))
                strikes_out.append([strike, cv, pv])
            result.append({"expiration": exp, "strikes": strikes_out})
        except Exception:
            continue
    return {"symbol": sym, "params": ["strike"] + fields, "chain": result}


# ── Router ──
router = APIRouter(prefix="/api/flowseeker", tags=["flowseeker"])


@router.get("/live")
async def live_flow(
    ticker: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    min_premium: float = Query(0.0, ge=0.0),
):
    """Live institutional options flow with classification. Surfaces
    degraded=true + reason when the provider is down — the frontend can
    distinguish 'no flow today' from 'feed broken'."""
    meta = await fetch_live_flow_with_meta(ticker=ticker, limit=limit, min_premium=min_premium)
    return {
        "ticker": (ticker.strip().upper() if ticker else None),
        "count": len(meta["prints"]),
        "prints": meta["prints"],
        "degraded": meta["degraded"],
        "degraded_reason": meta["degraded_reason"],
    }


@router.get("/drilldown/{symbol}")
async def drilldown(symbol: str):
    """Contract-level drilldown."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")
    return await contract_drilldown(sym)


@router.get("/chain/{symbol}")
async def options_chain(symbol: str):
    """
    Options chain — Public Advanced API first (paid, real quotes/greeks),
    CVForge second, yfinance last resort. Cached for 600s.

    OWNERSHIP (institutional loop firewall): this file is split —
    B-REGION = chain/scan/budget/baseline sections (Agent B);
    C-REGION = alerts pipeline below (_run_institutional_alerts,
    _cached/_merged_gex_context, /alerts/*, journal/outcomes) (Agent C).
    No cross-region edits without owner sign-off in LEDGER.md.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")

    # Cache check
    if sym in _chain_cache:
        ts, data = _chain_cache[sym]
        if time.time() - ts < CACHE_TTL:
            return data

    # Try Public Advanced API first (paid primary — real NBBO + greeks).
    # Budget exhaustion degrades to cvserver, never to an error: chains have
    # free fallbacks, and the paid budget is reserved for flow-critical paths.
    try:
        from services.public_api_adapter import (
            fetch_chain_from_public_api,
            public_to_nested,
        )
        from services.public_budget import BudgetExhausted
        from services.public_budget import budget as _pub_budget

        try:
            await _pub_budget.acquire("api.public.com")
        except BudgetExhausted:
            pub_nested = None
        else:
            try:
                pub = await fetch_chain_from_public_api(sym, max_expiries=6)
                pub_nested = public_to_nested(pub)
            finally:
                _pub_budget.release()
        if pub_nested and pub_nested.get("chain"):
            _remember_chain(sym, pub_nested)
            return pub_nested
    except Exception as e:
        logger.debug(f"flowseeker chain: public path failed for {sym}: {e}")

    # Try CVForge (fast, rich data)
    data = await _cvforge_chain(sym)
    if data and data.get("chain"):
        _remember_chain(sym, data)
        return data

    # Fallback to yfinance (slow but reliable)
    try:
        loop = asyncio.get_event_loop()
        fields = [
            "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility",
        ]
        data = await asyncio.wait_for(
            loop.run_in_executor(None, _yfinance_chain_sync, sym, fields),
            timeout=60.0,
        )
        _remember_chain(sym, data)
        return data
    except TimeoutError:
        return {
            "symbol": sym,
            "params": ["strike", "bid", "ask", "lastPrice", "volume", "openInterest"],
            "chain": [],
            "error": "timeout",
        }
    except Exception as e:
        logger.warning(f"flowseeker chain: {sym}: {e}")
        return {"symbol": sym, "params": [], "chain": [], "error": str(e)}


@router.get("/public/chain/{ticker}")
async def public_chain_flat(
    ticker: str,
    expirations: int = Query(default=4, ge=1, le=12),
    expiration: str | None = Query(default=None),
    fields: str | None = Query(default=None),
):
    """Smart-Order-Flow chain from the paid Public Advanced API (flat shape).

    This is the route the Tidehunter Pro flow tab polls first
    (`/api/flowseeker/public/chain/{t}?expirations=4&fields=...`); without it
    every poll 404s and the tab silently degrades to the 20/hour cvserver
    budget. Flat contract list with TRUE bid/ask/last/volume/OI/IV/greeks —
    no BS premium estimates, no vol/OI side proxy.

    Budget-gated via services.public_budget (60/min token bucket); on
    exhaustion returns 503 with retry_after so the tab falls through to
    cvserver instead of hammering upstream. The adapter's 60s cache +
    coalescing means steady-state polling costs ~1 token/ticker/min.
    """
    from services.public_api_adapter import fetch_chain_from_public_api
    from services.public_budget import BudgetExhausted
    from services.public_budget import budget as _pub_budget

    sym = (ticker or "").strip().upper()
    if not sym:
        raise HTTPException(400, "ticker required")

    try:
        await _pub_budget.acquire("api.public.com")
    except BudgetExhausted as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "public budget exhausted", "retry_after": e.retry_after},
        ) from e
    try:
        result = await fetch_chain_from_public_api(sym, max_expiries=expirations)
    finally:
        _pub_budget.release()

    if result is None:
        raise HTTPException(
            status_code=502,
            detail=f"Public API unavailable for {sym} — key may be missing or API call failed",
        )

    contracts = result.get("contracts", [])
    if expiration:
        contracts = [c for c in contracts if c.get("expiry") == expiration]

    flat = [
        {
            "strike": c.get("strike"),
            "type": c.get("type"),
            "expiry": c.get("expiry"),
            "expiration": c.get("expiry"),
            "volume": c.get("volume") or 0,
            "openInterest": c.get("oi") or 0,
            "oi": c.get("oi") or 0,
            "impliedVolatility": c.get("iv") or 0,
            "iv": c.get("iv") or 0,
            "delta": c.get("delta"),
            "gamma": c.get("gamma"),
            "theta": c.get("theta"),
            "vega": c.get("vega"),
            "bid": c.get("bid"),
            "ask": c.get("ask"),
            "mid": c.get("mid"),
            "last": c.get("last"),
            "lastPrice": c.get("last"),
            "bidSize": c.get("bid_size"),
            "askSize": c.get("ask_size"),
            "osi": c.get("osi"),
        }
        for c in contracts
    ]
    return {
        "ok": True,
        "ticker": sym,
        "spot": result.get("spot", 0),
        "expiries": result.get("expiries", []),
        "n_contracts": len(flat),
        "data_source": "public_api",
        "stale": result.get("stale", False),
        "contracts": flat,
    }


@router.get("/screen")
async def screen_options(
    ticker: str = Query(...),
    min_premium: float = Query(0.0, ge=0.0),
    min_oi: int = Query(0, ge=0),
    option_type: str = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Screen options — uses CVForge screen API if available, else cached chain."""
    sym = (ticker or "").strip().upper()

    # Try CVForge screen API first
    cvforge_data = await _cvforge_screen(sym, min_premium, min_oi, option_type, limit)
    if cvforge_data:
        return cvforge_data

    # Fallback: use cached chain data
    if sym not in _chain_cache:
        await options_chain(sym)

    chain = _chain_cache.get(sym, (0, {}))[1].get("chain", [])
    contracts = []
    for exp in chain:
        for strike_data in exp.get("strikes", []):
            strike, cv, pv = strike_data[0], strike_data[1] or [], strike_data[2] or []
            for ctype, vals in [("CALL", cv), ("PUT", pv)]:
                prem = (vals[2] or 0) * 100 if len(vals) > 2 else 0
                oi = int(vals[4] or 0) if len(vals) > 4 else 0
                if prem >= min_premium and oi >= min_oi:
                    if not option_type or option_type.upper() == ctype:
                        contracts.append({
                            "ticker": sym, "strike": strike,
                            "expiration": exp.get("expiration", ""),
                            "type": ctype,
                            "bid": vals[0] if len(vals) > 0 else None,
                            "ask": vals[1] if len(vals) > 1 else None,
                            "lastPrice": vals[2] if len(vals) > 2 else None,
                            "volume": int(vals[3] or 0) if len(vals) > 3 else 0,
                            "openInterest": oi,
                            "premium": prem,
                        })

    contracts.sort(key=lambda c: c.get("premium", 0), reverse=True)
    return {"ticker": sym, "count": len(contracts), "results": contracts[:limit]}


async def _cvforge_screen(
    symbol: str,
    min_premium: float,
    min_oi: int,
    option_type: str | None,
    limit: int,
) -> dict | None:
    """Try CVForge screen API. Returns None on failure."""
    columns = [
        "ticker", "strike_price", "expiration_date", "contract_type",
        "trade_size", "trade_price", "open_interest", "implied_volatility",
        "delta", "gamma", "theta", "vega", "bid", "ask",
    ]
    filters = [{"field": "underlying_ticker", "op": "eq", "value": symbol}]
    if not CVFORGE_API_KEY:
        return None
    # Per-ticker screen shares the chain slice of the hourly budget — the
    # caller falls back to the cached chain when it's spent.
    if not _budget_take("chain"):
        logger.info("cvforge screen %s skipped — hourly budget slice spent", symbol)
        return None
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CVFORGE_API_KEY}",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "screen",
            "arguments": {
                "columns": columns,
                "filters": filters,
                "sort": [{"field": "trade_price", "direction": "desc"}],
                "limit": limit,
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(CVFORGE_URL, json=payload, headers=headers)
            if resp.status_code != 200:
                return None
            result = resp.json()
            content = result.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                import json
                d = json.loads(content[0]["text"])
            else:
                d = result.get("result", {})
            rows = d.get("rows", [])
            return {
                "ticker": symbol,
                "count": len(rows),
                "results": [
                    {
                        "ticker": r[0], "strike": r[1], "expiration": r[2],
                        "type": r[3], "size": r[4], "price": r[5],
                        "oi": r[6], "iv": r[7], "delta": r[8],
                        "gamma": r[9], "theta": r[10], "vega": r[11],
                        "bid": r[12], "ask": r[13],
                    }
                    for r in rows
                ],
            }
    except Exception as e:
        logger.warning(f"cvforge screen: {symbol}: {e}")
    return None


# ── Market-wide cross-symbol scan (BladeMap scanner grid) ──
# Powers the FlowSeeker Pro tab: ONE cvforge screen across ALL underlyings
# ranked by day_volume, so the hottest flow in the whole market surfaces
# (SPY, NVDA, TSLA, ENPH… whatever is active — not a fixed watchlist).
# Returns raw {columns, rows}; the frontend computes Flow Score / flow-type /
# lean exactly like the scenner34 build. Only live cvserver fields are used
# (day_volume vs OI) — there is no per-trade tape on this feed.
# ── cvforge hourly request budget ──
# The plan allows ~20 upstream requests/hour (429: "hourly request limit
# reached"). One market-wide /scan screen is the highest-value call — 300
# contracts across every scanned ticker, all the alert engine needs — so it
# gets most of the budget; per-ticker chains/screens share the remainder and
# degrade to yfinance/cache when their slice is spent. Rolling 1h window.
CV_HOURLY_BUDGET = int(os.environ.get("CV_HOURLY_BUDGET", "20"))
CV_SCAN_BUDGET = int(os.environ.get("CV_SCAN_BUDGET", str(max(1, (CV_HOURLY_BUDGET * 7) // 10))))
_cv_calls: dict[str, list[float]] = {"scan": [], "chain": []}


def _budget_state(now: float | None = None) -> dict:
    now = time.time() if now is None else now
    cutoff = now - 3600.0
    for k in _cv_calls:
        _cv_calls[k] = [t for t in _cv_calls[k] if t > cutoff]
    scan_used, chain_used = len(_cv_calls["scan"]), len(_cv_calls["chain"])
    all_calls = _cv_calls["scan"] + _cv_calls["chain"]
    return {
        "hourly_cap": CV_HOURLY_BUDGET, "used": scan_used + chain_used,
        "scan_used": scan_used, "scan_cap": CV_SCAN_BUDGET,
        "chain_used": chain_used, "chain_cap": max(0, CV_HOURLY_BUDGET - CV_SCAN_BUDGET - 1),
        "frees_in": int(min(all_calls) + 3600 - now) if all_calls else 0,
    }


def _budget_take(kind: str, now: float | None = None) -> bool:
    """Reserve one upstream cvforge call. False = that slice (or the whole
    hourly cap, 1 call held in reserve) is spent — caller must serve
    cache/stale/yfinance instead of going upstream."""
    now = time.time() if now is None else now
    st = _budget_state(now)
    if st["used"] >= CV_HOURLY_BUDGET:
        return False
    if kind == "scan" and st["scan_used"] >= CV_SCAN_BUDGET:
        return False
    if kind == "chain" and st["chain_used"] >= st["chain_cap"]:
        return False
    _cv_calls[kind].append(now)
    return True


def _hourly_backoff_until(now: float) -> float:
    """cvforge's limit is per clock hour — after an hourly-limit 429 there is
    no point retrying before the next hour boundary (+2min grace)."""
    return min((int(now // 3600) + 1) * 3600 + 120.0, now + 3900.0)


def _register_scan_429(now: float, resp_text: str) -> None:
    """Classify a cvforge scan 429 and set the matching backoff.

    The full-hour lockout is only justified when OUR OWN budget tracker shows
    the hourly window actually spent — a spurious 'hourly' 429 with slots
    still free must fall back to the exponential path (was: any 'hourly'
    body text froze scanning for ~47 min even at 1/20 used)."""
    st = _budget_state(now)
    if "hourly" in (resp_text or "").lower() and st["used"] >= CV_HOURLY_BUDGET - 1:
        _scan_backoff["until"] = _hourly_backoff_until(now)
    else:
        _scan_backoff["until"] = now + _scan_backoff["delay"]
        _scan_backoff["delay"] = min(_scan_backoff["delay"] * 2, 600.0)


# ── unusual-activity pure helpers (extracted from /alerts/unusual loop) ──

# Thresholds pinned by tests/routes/test_unusual_activity.py. The endpoint
# docstring previously claimed $500K/|Δ|>0.7 while the code used 250K/0.6 —
# resolved to the code values (the tuned, battle-tested ones).
PREMIUM_CONCENTRATION_MIN = 250_000
DELTA_EXTREME_ABS = 0.6


def per_side_premiums(d: dict) -> dict:
    """Mid-based notional per side: mid × THAT side's OI × 100.

    The historical bug priced call premium over COMBINED call+put OI,
    doubling every call-side concentration estimate."""
    call_mid = (d["call_bid"] + d["call_ask"]) / 2 if d["call_bid"] > 0 and d["call_ask"] > 0 else 0
    put_mid = (d["put_bid"] + d["put_ask"]) / 2 if d["put_bid"] > 0 and d["put_ask"] > 0 else 0
    return {
        "call_mid": call_mid,
        "put_mid": put_mid,
        "call_premium": call_mid * d["call_oi"] * 100 if call_mid > 0 else 0,
        "put_premium": put_mid * d["put_oi"] * 100 if put_mid > 0 else 0,
    }


def strike_unusual_flags(d: dict, peers: list[dict],
                         min_vol_oi_ratio: float = 0.05) -> list[str]:
    """Pure flag engine for one strike row against its near-money peers.

    Emits any of: high_volume, high_iv, oi_spike, delta_extreme,
    premium_concentration. Both sides examined (the historical bug only
    ever looked at calls for IV and delta)."""
    flags: list[str] = []
    total_oi = d["call_oi"] + d["put_oi"]
    total_vol = d["call_vol"] + d["put_vol"]

    avg_oi = sum(p["call_oi"] + p["put_oi"] for p in peers) / max(len(peers), 1)
    iv_values = sorted(
        v for p in peers for v in (p["call_iv"], p["put_iv"]) if v > 0.01)
    iv_p75 = iv_values[int(len(iv_values) * 0.75)] if iv_values else 0

    # volume/OI
    if total_oi > 100:
        vol_oi = total_vol / total_oi
        if vol_oi >= min_vol_oi_ratio and total_vol > 100:
            flags.append("high_volume")

    # IV spike — either side, min 500 OI on combined OI
    if iv_p75 > 0 and total_oi >= 500 and (
            (d["call_iv"] > 0 and d["call_iv"] >= iv_p75)
            or (d["put_iv"] > 0 and d["put_iv"] >= iv_p75)):
        flags.append("high_iv")

    # OI spike (min 500 OI, >2x average)
    if total_oi > avg_oi * 2 and total_oi >= 500:
        flags.append("oi_spike")

    # delta extreme — deep ITM either side with that side's OI > 200
    call_extreme = abs(d["call_delta"]) > DELTA_EXTREME_ABS and d["call_oi"] > 200
    put_extreme = abs(d["put_delta"]) > DELTA_EXTREME_ABS and d["put_oi"] > 200
    if call_extreme or put_extreme:
        flags.append("delta_extreme")

    # premium concentration — per-side OI now
    prem = per_side_premiums(d)
    if max(prem["call_premium"], prem["put_premium"]) > PREMIUM_CONCENTRATION_MIN \
            and total_oi >= 500:
        flags.append("premium_concentration")

    return flags


# ── /scan cache + 429 backoff ──
_scan_cache: dict[str, dict] = {}                # "min_volume:limit" → {ts, data, asof}
# ~4-minute cadence spends ≤15 scan calls/hour — alerts stay minutes-fresh
# without ever exhausting the plan mid-hour.
_SCAN_TTL = float(os.environ.get("CV_SCAN_TTL", "240"))
_scan_backoff = {"until": 0.0, "delay": 30.0}    # exponential, capped at 600s

# 2026-08-22: _scan_cache/_baselines_cache/_contract_oi_cache/_history_cache had
# writes with no eviction — unbounded growth over long-lived sessions. Trim to
# a bounded size on each write (same pattern as morning_briefing._trim_prior_cache).
_FLOWSEEKER_CACHE_MAX = 200


def _trim_cache(cache: dict, max_size: int = _FLOWSEEKER_CACHE_MAX) -> None:
    if len(cache) > max_size:
        excess = len(cache) - max_size
        for key in list(cache.keys())[:excess]:
            cache.pop(key, None)


_scan_lock = asyncio.Lock()                       # single-flight for upstream screen calls
_last_force_refresh = 0.0                         # debounce force refresh
# Strong refs to fire-and-forget tasks — unreferenced tasks can be GC'd
# mid-flight (CPython docs), nondeterministically dropping baseline/alert writes.
_flow_bg_tasks: set[asyncio.Task] = set()


def _spawn_bg(coro) -> None:
    """create_task + strong-ref bookkeeping (the server.py pattern)."""
    t = asyncio.get_running_loop().create_task(coro)
    _flow_bg_tasks.add(t)
    t.add_done_callback(_flow_bg_tasks.discard)


def _cached_regimes() -> dict[str, str]:
    """Per-ticker gamma regime from the heatmap cache — cache-only, no fetches."""
    try:
        import server  # deferred: circular import

        out: dict[str, str] = {}
        now = time.time()
        for key, entry in list(getattr(server, "_BUILD_HEATMAP_CACHE", {}).items()):
            if now - entry.get("ts", 0) > 900:
                continue
            reg = ((entry.get("data") or {}).get("nodes") or {}).get("regime")
            if reg:
                out[key.split(":", 1)[0]] = reg
        return out
    except Exception:
        return {}


# Trading-day identity is Eastern regardless of host TZ — a UTC-deployed
# backend writing evening rows under tomorrow's date would corrupt the daily
# volume/OI history ($max merges today's EOD totals into tomorrow's doc) and
# desync from the frontend's local sessionDay.
_ET = ZoneInfo("America/New_York")


def _today_et() -> str:
    return datetime.now(_ET).strftime("%Y-%m-%d")


# ── Volume baseline store (σ-spike detection) ──
# Each successful upstream scan upserts today's per-ticker MAX cumulative
# volume (day_volume is cumulative, so $max converges to the EOD total). The
# baseline is mean/std of PRIOR days' EOD volumes; /scan exposes it as
# "baselines" once a ticker has ≥2 prior days. Cf. OptionScannerTWS: 4-5σ
# volume spikes with little price movement often precede underlying moves.
_baselines_cache = {"ts": 0.0, "data": {}}
# Per-contract prior-day open interest — next-day OI change is the one
# "was this real opening flow?" confirmation a print-less feed can give:
# a FRESH (vol≥3×OI) contract whose OI then RISES held as new positioning;
# one whose OI falls back was intraday churn. Keyed by OCC contract ticker.
_contract_oi_cache = {"ts": 0.0, "data": {}}


async def _record_scan_baseline(rows: list) -> None:
    """Fire-and-forget — never raises into the scan path."""
    try:
        from server import db  # deferred: circular import

        today = _today_et()
        per: dict[str, dict] = {}
        oi_ops: list = []
        seen_contracts: set = set()
        for r in rows:
            t = r[0]
            e = per.setdefault(t, {"call_vol": 0, "put_vol": 0, "contracts": 0})
            vol = int(r[5] or 0)
            if str(r[2] or "").lower().startswith("c"):
                e["call_vol"] += vol
            else:
                e["put_vol"] += vol
            e["contracts"] += 1
            # Per-contract OI (static intraday, so $max == the value). One doc
            # per contract per day; the OCC ticker r[1] is the exact join key.
            ckey = r[1]
            oi = int(r[6] or 0)
            if ckey and ckey not in seen_contracts:
                seen_contracts.add(ckey)
                oi_ops.append(UpdateOne(
                    {"ticker": ckey, "date": today},
                    {"$max": {"oi": oi},
                     "$set": {"under": t, "updated_at": time.time()}},
                    upsert=True,
                ))
        for t, e in per.items():
            # IVR piggyback (2026-09-02, zero extra upstream calls): today's
            # standardized ATM IV = median row IV over |K/S−1| ≤ 5% from THIS
            # scan snapshot. Scan-row layout (SCAN_COLUMNS): 3=strike, 6=OI,
            # 7=IV, 9=underlying price. IV > 3 is the percent convention →
            # normalize to decimal so cross-source medians stay comparable.
            # The nightly cron turns these into RICH/CHEAP-able IVR series;
            # alerts consume derived tags, never raw snapshot IV.
            trows = [r for r in rows if r[0] == t and r[7] and r[3] and r[9]]
            atm_ivs = sorted(
                (lambda iv: iv / 100.0 if iv > 3.0 else iv)(float(r[7]))
                for r in trows
                if abs(float(r[3]) / float(r[9]) - 1.0) <= 0.05
            ) if trows else []
            atm_iv = round(atm_ivs[len(atm_ivs) // 2], 4) if atm_ivs else None
            max_ops = {"total_vol": e["call_vol"] + e["put_vol"],
                       "call_vol": e["call_vol"], "put_vol": e["put_vol"]}
            if atm_iv is not None:
                max_ops["atm_iv"] = atm_iv   # intraday $max = the day's best
            update = {
                "$max": max_ops,
                "$set": {"updated_at": time.time()},
            }
            if atm_iv is not None:
                update["$inc"] = {"iv_obs": 1}
            await db.flow_scan_daily.update_one(
                {"ticker": t, "date": today}, update, upsert=True,
            )
        if oi_ops:
            await db.flow_scan_contract_oi.bulk_write(oi_ops, ordered=False)
    except Exception as e:
        logger.debug(f"scan baseline record skipped: {e}")


async def _run_institutional_alerts(
    rows: list,
    extras: dict | None = None,
    dealer: dict | None = None,
) -> None:
    """Server-side institutional alert pass over a FRESH scan result.
    (C-REGION — Agent C domain; see ownership note on options_chain.)

    Fires on every cache fill (normal + force-refresh), so alerts exist and
    persist even with no Scanner tab open — the browser engine only ever saw
    what a live tab happened to witness. Zero extra cvforge calls: it reuses
    the rows, baselines, prev-OI and regime cache the scan already has.

    extras (paid-scanner quote truth) overlays true premiums/NBBO/velocity
    onto rows before eval; dealer (per-ticker gamma walls/regime from the
    same chains) fills GEX context for tickers the heatmap cache doesn't
    cover — regime propagates to key levels + WHY, without a fabricated
    magnitude (confluence still needs measured ΓIB).
    """
    try:
        from services import flow_alerts as fa
        from services import flow_desk as fd
        from services.duckdb_engine import db as duckdb_engine

        normed = fa.norm_rows(rows)
        if extras:
            fa.apply_quote_truth(normed, extras)
        if not normed:
            return
        baselines = await _volume_baselines()
        await load_earnings_dates()
        prev_occ = await _prev_contract_oi()
        # prev-OI store is keyed by OCC symbol (r[1]); the engine keys by
        # contract identity — re-key here at the boundary.
        prev = {
            r["ckey"]: prev_occ[r["occ"]]
            for r in normed
            if r.get("occ") and prev_occ.get(r["occ"]) is not None
        }
        oi_tags = _compute_oi_tags(normed, prev)
        alerts = fa.eval_institutional(
            normed, baselines=baselines, prev_oi=prev, regimes=_cached_regimes(),
            gex_context=_merged_gex_context(
                sorted({r["under"] for r in normed}), dealer),
            oi_tags=oi_tags,
            **({"opts": {"calibration": cal}} if (cal := await _load_calibration()) else {}),
        )
        # DuckDB calls are synchronous — run them off the event loop so a
        # slow query never stalls concurrent requests (this runs in a
        # fire-and-forget task, but that task still shares the loop).
        loop = asyncio.get_running_loop()

        def _duck_pass() -> list:
            # init before desk_pass so the campaign 10-day lookback in
            # flow_alerts_daily has its target table on every fresh deploy.
            fa.init_flow_alert_tables(duckdb_engine)
            # Desk pass (Conviction v2.2): fresh-interest gate, campaign
            # promotion, IV context. Fails open. See
            # docs/handoff/FABLE-desk-pass.md for the contract.
            passed = fd.desk_pass(duckdb_engine, normed, alerts, oi_tags=oi_tags)
            fresh = fa.dedup_filter(duckdb_engine, passed)
            if fresh:
                fa.persist_alerts(duckdb_engine, fresh)
            fa.update_moves(duckdb_engine, spots)
            # Blademap v3 lifecycle: close open journal cards against their
            # own key levels (stop/target) using this scan's spot stamps.
            try:
                from services.journal_store import (
                    get_engine,
                    init_journal_tables,
                    journal_lifecycle,
                )
                jeng = get_engine()
                init_journal_tables(jeng)
                closed = journal_lifecycle(jeng, spots)
                if closed:
                    logger.info("journal lifecycle pass closed %d card(s)", closed)
            except Exception as le:
                logger.warning("journal lifecycle pass failed (non-fatal): %s", le)
            # P1-7 whale tracker (Agent C): bookmark WHALE-rule fires, then
            # update all open tracks from this scan's per-contract rows.
            # Fail-open — tracking must never break the alert persist above.
            try:
                from services.journal_store import (
                    bookmark_whale,
                    get_engine,
                    init_whale_tables,
                    update_whales,
                )
                weng = get_engine()
                init_whale_tables(weng)
                rows_by_ckey = {r.get("ckey"): r for r in normed if r.get("ckey")}
                for a in fresh or []:
                    if a.get("rule") == "WHALE":
                        r0 = rows_by_ckey.get(a.get("ckey")) or {}
                        bookmark_whale(weng, a, spot=r0.get("spot") or 0,
                                       oi=r0.get("oi") or 0, vol=r0.get("vol") or 0)
                snaps = {c: {"spot": r.get("spot"), "oi": r.get("oi"),
                             "vol": r.get("vol"), "dte": r.get("dte")}
                         for c, r in rows_by_ckey.items()}
                if snaps:
                    update_whales(weng, snaps)
            except Exception as we:
                logger.warning("whale tracker pass failed (non-fatal): %s", we)
            return fresh

        spots = {r["under"]: r["spot"] for r in normed if r.get("spot")}
        fresh = await loop.run_in_executor(None, _duck_pass)
        if fresh:
            logger.info(
                "institutional alerts: %d fired (%s) [pid=%d]",
                len(fresh), ",".join(sorted({a["under"] for a in fresh})),
                os.getpid(),
            )
            # Discord webhook fan-out (fail-open, never breaks the scan path;
            # no-op when DISCORD_WEBHOOK_URL is unset; tier/rule-gated).
            try:
                from services import discord_ops as _discord

                posted = await _discord.post_alerts(fresh)
                if posted:
                    logger.info("discord webhook: %d alert(s) posted", posted)
            except Exception as e:
                logger.warning(f"discord notify failed (non-fatal): {e}")
    except Exception as e:
        logger.warning(f"institutional alert eval failed: {e}")


def _cached_gex_context(tickers: list[str]) -> dict[str, dict]:
    """Per-ticker paper-accurate GEX context (Barbon-Buraschi ΓIB) from the
    heatmap cache — cache-only, no fetches (mirrors _cached_regimes)."""
    try:
        import server  # deferred: circular import
        from services.gex_paper_accurate import (
            DEFAULT_ADV_SHARES,
            compute_gamma_imbalance,
        )

        out: dict[str, dict] = {}
        now = time.time()
        wanted = set(tickers)
        for key, entry in list(getattr(server, "_BUILD_HEATMAP_CACHE", {}).items()):
            sym = key.split(":", 1)[0]
            if sym not in wanted or now - entry.get("ts", 0) > 900:
                continue
            gf = ((entry.get("data") or {}).get("gamma_flip")) or {}
            total_gex = gf.get("total_gex")
            spot = gf.get("spot")
            if not total_gex or not spot or spot <= 0:
                continue
            out[sym] = {
                "gamma_imbalance": compute_gamma_imbalance(
                    total_gex, spot, adv_shares=DEFAULT_ADV_SHARES),
            }
        return out
    except Exception:
        return {}


def _merged_gex_context(
    tickers: list[str],
    dealer: dict | None,
) -> dict[str, dict]:
    """Heatmap ΓIB where available, Public-scanner dealer regime elsewhere.

    The paper-accurate cache entry wins whenever present (it carries a real
    ADV-normalized magnitude, which the confluence boolean needs). Dealer
    entries carry regime + walls; pct passes through ONLY when the scanner
    measured it against real ADV (B2) — otherwise None (unknown), regime
    propagates to key levels + the WHY block, and confluence stays False
    until measured ΓIB arrives. Never fabricate a pct.
    """
    out = _cached_gex_context(tickers)
    for t, d in (dealer or {}).items():
        if t in out or not isinstance(d, dict):
            continue
        if d.get("regime") not in ("negative", "positive"):
            continue
        # pct None = UNKNOWN magnitude (dealer walls without ADV normalization).
        # Regime propagates to key levels + WHY; confluence stays False until
        # measured ΓIB arrives. Never 0.0 — zero is a measurement, not unknown.
        pct = d.get("gamma_imbalance_pct")
        try:
            pct = float(pct) if pct is not None else None
        except (TypeError, ValueError):
            pct = None
        out[t] = {
            "gamma_imbalance": {
                "gamma_imbalance_pct": pct,
                "regime": d["regime"],
                "dealer_walls": {
                    "call": d.get("call_wall"),
                    "put": d.get("put_wall"),
                },
            },
        }
    return out


_earnings_cache: dict[str, tuple[float, dict[str, str]]] = {"ts": 0.0, "data": {}}


async def load_earnings_dates() -> dict[str, str]:
    """{underlying: ISO report date} for names in today's scan, 6h cached.

    Reads the flow_earnings Mongo store (populated by record_earnings_dates;
    yfinance calendar on the fetch side). Fails soft to {} — callers then
    surface 'earnings window unknown' tags instead of silently skipping.
    """
    if time.time() - _earnings_cache["ts"] < 6 * 3600:
        return _earnings_cache["data"]
    out: dict[str, str] = {}
    try:
        from server import db  # deferred: circular import

        today = _today_et()
        async for doc in db.flow_earnings.find(
            {"date": {"$gte": today}}, {"ticker": 1, "date": 1}
        ).limit(2000):
            out[doc["ticker"]] = doc["date"]
    except Exception as e:
        logger.debug(f"earnings dates unavailable: {e}")
    _earnings_cache["ts"] = time.time()
    _earnings_cache["data"] = out
    return out


def record_earnings_dates(dates: dict[str, str]) -> int:
    """Upsert {ticker: 'YYYY-MM-DD'} into Mongo flow_earnings. Called by the
    ops script scripts/fetch_earnings.py (yfinance calendar, cached in
    flow_earnings_fetch); never on the hot path."""
    import asyncio

    from pymongo import UpdateOne

    from server import db

    ops = [UpdateOne({"ticker": t}, {"$set": {"date": d, "updated_at": time.time()}},
                     upsert=True) for t, d in (dates or {}).items()]
    if not ops:
        return 0
    n = asyncio.get_event_loop().run_until_complete(
        db.flow_earnings.bulk_write(ops, ordered=False)).modified_count
    _earnings_cache["ts"] = 0.0   # invalidate
    return int(n or len(ops))


def _compute_oi_tags(normed: list[dict], prev: dict[str, int]) -> dict[str, dict]:
    """ΔOI hygiene tags for one scan — computed ONCE on the server, consumed
    identically by the server engine (gating) and the client tape (labels).
    Earnings dates are scope-limited to today's underlyings."""
    from services.oi_hygiene import oi_hygiene_tags

    try:
        earnings = {t: d for t, d in _earnings_cache.get("data", {}).items()
                    if any(r.get("under") == t for r in normed[:400])} or None
        return oi_hygiene_tags(normed, prev, earnings_dates=earnings)
    except Exception as e:
        logger.debug(f"oi_hygiene tags skipped: {e}")
        return {}


async def _prev_contract_oi() -> dict[str, int]:
    """{contract_ticker: oi} from the most recent PRIOR scan day. 60s cached.
    A single prior date (the last day we scanned) keeps this to two indexed
    queries — exactly the 'vs last session' read a daily checker wants."""
    nowt = time.time()
    if nowt - _contract_oi_cache["ts"] < 60:
        return _contract_oi_cache["data"]
    out: dict[str, int] = {}
    try:
        from server import db  # deferred: circular import

        today = _today_et()
        prior = await db.flow_scan_contract_oi.find(
            {"date": {"$lt": today}}, {"date": 1}
        ).sort("date", -1).limit(1).to_list(1)
        if prior:
            pdate = prior[0]["date"]
            async for doc in db.flow_scan_contract_oi.find(
                {"date": pdate}, {"ticker": 1, "oi": 1}
            ).limit(20000):
                out[doc["ticker"]] = doc.get("oi") or 0
    except Exception as e:
        logger.debug(f"prev contract OI unavailable: {e}")
    _contract_oi_cache["ts"] = nowt
    _contract_oi_cache["data"] = out
    return out


async def _volume_baselines() -> dict[str, dict]:
    """{ticker: {avg, std, days}} over prior days' EOD volumes. 60s cached."""
    nowt = time.time()
    if nowt - _baselines_cache["ts"] < 60:
        return _baselines_cache["data"]
    out: dict[str, dict] = {}
    try:
        from server import db  # deferred: circular import

        today = _today_et()
        agg: dict[str, list] = {}
        async for doc in db.flow_scan_daily.find(
            {"date": {"$ne": today}}, {"ticker": 1, "total_vol": 1}
        ).limit(20000):
            agg.setdefault(doc["ticker"], []).append(doc.get("total_vol") or 0)
        for t, vols in agg.items():
            if len(vols) < 2:
                continue
            n = len(vols)
            avg = sum(vols) / n
            var = sum((v - avg) ** 2 for v in vols) / (n - 1)
            std = var ** 0.5
            if std > 0:
                out[t] = {"avg": round(avg), "std": round(std), "days": n}
    except Exception as e:
        logger.debug(f"volume baselines unavailable: {e}")
    _baselines_cache["ts"] = nowt
    _baselines_cache["data"] = out
    return out


def _scan_payload(rows: list, stale: bool, asof: str, columns: list, cache_age: float = 0, retry_after: float | None = None, limit: int | None = None) -> dict:
    source = "cvserver-screen"
    if stale:
        source = "cvserver-stale"
    elif cache_age > 0 and cache_age < 60:
        source = "cvserver-cached"
    try:
        tickers = len({r[0] for r in rows}) if rows else 0
    except (TypeError, IndexError):
        tickers = 0
    return {
        "columns": columns, "rows": rows, "count": len(rows),
        "source": source, "stale": stale, "asof": asof,
        "cache_age_seconds": round(cache_age) if cache_age else None,
        "retry_after_seconds": round(retry_after) if retry_after else None,
        "scan_ttl": int(_SCAN_TTL),
        "budget": _budget_state(),
        "regimes": _cached_regimes(),
        # Coverage honesty: the screen is top-N by raw day_volume — when the
        # payload fills the limit, mid-cap building below the cutoff is cut
        # (the SNDK gap). The UI reads `truncated` to badge partial coverage
        # instead of implying the whole market is shown.
        "truncated": bool(limit is not None and len(rows) >= limit),
        "coverage": {"tickers": tickers, "limit": limit},
    }


@router.get("/scan")
async def market_scan(
    # Paid-Public era (2026-09-05): floor 2500→1000, limit 300→500. Same ONE
    # upstream call — wider net for mid-cap building at zero budget cost.
    # /scan-public (paid chains, fixed universe) is the structural fix for
    # the top-N-by-volume cutoff; this keeps the cvserver path as wide as
    # the wire cost allows while it remains the default Scanner source.
    min_volume: int = Query(1000, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    force: bool = Query(False),
):
    """
    Cross-symbol options flow scan (day_volume vs OI).
    60s-cached; on upstream 429 backs off exponentially and serves the last
    good result marked stale=true rather than collapsing to a client fallback.
    Use ?force=true to bypass cache and backoff (debounced server-side).
    """
    columns = [
        "underlying_ticker", "ticker", "contract_type", "strike_price",
        "expiration_date", "day_volume", "open_interest",
        "implied_volatility", "delta", "underlying_price",
    ]
    if not CVFORGE_API_KEY:
        raise HTTPException(503, "cvserver API key not configured")

    cache_key = f"{min_volume}:{limit}"

    def _fresh(now: float):
        cached = _scan_cache.get(cache_key)
        if cached and not force and now - cached["ts"] < _SCAN_TTL:
            return _scan_payload(cached["data"], False, cached["asof"], columns, cache_age=now - cached["ts"], limit=limit)
        return None

    def _stale_or(now: float, status: int, detail: str, retry_after: float | None = None):
        cached = _scan_cache.get(cache_key)
        best = cached or (max(_scan_cache.values(), key=lambda e: e["ts"]) if _scan_cache else None)
        if best:
            cache_age = now - best["ts"]
            return _scan_payload(best["data"], True, best["asof"], columns, cache_age=cache_age, retry_after=retry_after, limit=limit)
        # No cached data — return empty payload with stale marker + retry hint
        # instead of 503, so the frontend can show "waiting for first scan"
        # rather than an error state. cvserver hits its 20/hour budget and
        # backs off ~13min; the frontend polls every 60s and will pick up
        # the cache within ~1-2 backoff cycles.
        return _scan_payload(
            [], stale=True, asof=datetime.now().isoformat(),
            columns=columns, cache_age=0, retry_after=retry_after,
        )

    def _backing_off(now: float):
        if not force and now < _scan_backoff["until"]:
            retry_after = _scan_backoff["until"] - now
            return _stale_or(now, 503, f"cvserver rate-limited; retrying after {int(retry_after)}s", retry_after=retry_after)
        return None

    now = time.time()
    hit = _fresh(now)
    if hit:
        hit["baselines"] = await _volume_baselines()
        hit["prev_oi"] = await _prev_contract_oi()
        from services import flow_alerts as _fa_local  # local import: cached-hit path has no fa binding

        _normed_hit = _fa_local.norm_rows(hit.get("data") or [], hit.get("columns"))
        _prev_hit = {
            r["ckey"]: hit["prev_oi"][r["occ"]]
            for r in _normed_hit
            if r.get("occ") and hit["prev_oi"].get(r["occ"]) is not None
        }
        hit["oi_tags"] = _compute_oi_tags(_normed_hit, _prev_hit)
        return hit
    limited = _backing_off(now)
    if limited:
        return limited

    # Single-flight: concurrent cache misses queue here; the winner fills the
    # cache and everyone else is served by the re-check instead of stampeding
    # upstream (which also compounded the 429 backoff bump per concurrent miss).
    async with _scan_lock:
        now = time.time()
        hit = _fresh(now)
        if hit:
            return hit
        limited = _backing_off(now)
        if limited:
            return limited

        # Hourly budget gate — when the scan slice is spent, serve the last
        # good result until a slot frees instead of burning the plan's cap.
        if not _budget_take("scan"):
            frees = _budget_state(now)["frees_in"]
            return _stale_or(now, 503, f"cvforge hourly budget spent; next slot in ~{frees}s", retry_after=float(frees or 60))

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CVFORGE_API_KEY}",
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "screen",
                "arguments": {
                    "columns": columns,
                    "filters": [{"field": "day_volume", "op": "gt", "value": min_volume}],
                    "sort": [{"field": "day_volume", "direction": "desc"}],
                    "limit": limit,
                },
            },
        }
        try:
            async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
                resp = await client.post(CVFORGE_URL, json=payload, headers=headers)
                if resp.status_code == 429:
                    _register_scan_429(now, resp.text)
                    logger.warning("cvforge scan 429 — backing off %ss", int(_scan_backoff["until"] - now))
                    retry_after = _scan_backoff["until"] - now
                    return _stale_or(now, 503, "cvserver rate-limited (429), no cached scan yet", retry_after=retry_after)
                if resp.status_code != 200:
                    return _stale_or(now, 502, f"cvserver returned {resp.status_code}")
                result = resp.json()
                content = result.get("result", {}).get("content", [])
                if content and content[0].get("type") == "text":
                    d = json.loads(content[0]["text"])
                else:
                    d = result.get("result", {})
                rows = d.get("rows", [])
                _scan_backoff["delay"] = 30.0
                _scan_backoff["until"] = 0.0
                asof = datetime.now().isoformat()
                _scan_cache[cache_key] = {"ts": now, "data": rows, "asof": asof}
                _trim_cache(_scan_cache)
                _spawn_bg(_record_scan_baseline(rows))
                _spawn_bg(_run_institutional_alerts(rows))
                out = _scan_payload(rows, False, asof, columns, cache_age=0, limit=limit)
                out["baselines"] = await _volume_baselines()
                out["prev_oi"] = await _prev_contract_oi()
                from services import flow_alerts as _fa_local2  # local import: scan path scope

                _normed_now = _fa_local2.norm_rows(rows, columns)
                _prev_rekey = {
                    r["ckey"]: out["prev_oi"][r["occ"]]
                    for r in _normed_now
                    if r.get("occ") and out["prev_oi"].get(r["occ"]) is not None
                }
                out["oi_tags"] = _compute_oi_tags(_normed_now, _prev_rekey)
                return out
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"cvforge scan failed: {e}")
            return _stale_or(now, 502, f"scan failed: {e}")


@router.post("/scan/refresh")
async def force_refresh_scan(
    min_volume: int = Query(1000, ge=0),
    limit: int = Query(500, ge=1, le=1000),
):
    """
    Force refresh the market scan — bypasses cache and backoff.
    Debounced: ignores if last force refresh was < 10s ago.
    """
    global _last_force_refresh, _scan_backoff
    now = time.time()
    if now - _last_force_refresh < 10.0:
        return {"status": "debounced", "retry_after_seconds": int(10 - (now - _last_force_refresh))}
    _last_force_refresh = now
    # NOTE: backoff is NOT reset here — only a successful upstream call may
    # clear it, otherwise a force-refresh during rate limiting would defeat
    # the exponential backoff and let the 20s poll hammer a 429ing upstream.

    columns = [
        "underlying_ticker", "ticker", "contract_type", "strike_price",
        "expiration_date", "day_volume", "open_interest",
        "implied_volatility", "delta", "underlying_price",
    ]
    if not CVFORGE_API_KEY:
        raise HTTPException(503, "cvserver API key not configured")

    cache_key = f"{min_volume}:{limit}"
    # Force refresh spends a real scan slot — when the hourly slice is spent
    # it must say so instead of silently burning the cap.
    if not _budget_take("scan"):
        frees = _budget_state(now)["frees_in"]
        raise HTTPException(503, f"cvforge hourly budget spent — next slot in ~{frees}s")

    # Single-flight: a force refresh must serialize against market_scan —
    # both mutate _scan_backoff/_scan_cache/budget; concurrent runs meant two
    # upstream calls for one slot and last-writer-wins on the cache.
    async with _scan_lock:
        return await _force_refresh_locked(min_volume, limit, columns, cache_key)


async def _force_refresh_locked(min_volume: int, limit: int,
                                columns: list[str], cache_key: str):
    """Upstream body of force_refresh_scan — caller holds _scan_lock."""
    now = time.time()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CVFORGE_API_KEY}",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "screen",
            "arguments": {
                "columns": columns,
                "filters": [{"field": "day_volume", "op": "gt", "value": min_volume}],
                "sort": [{"field": "day_volume", "direction": "desc"}],
                "limit": limit,
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(CVFORGE_URL, json=payload, headers=headers)
            if resp.status_code == 429:
                _register_scan_429(now, resp.text)
                raise HTTPException(503, "cvserver rate-limited (429) — force refresh backed off")
            if resp.status_code != 200:
                raise HTTPException(502, f"cvserver returned {resp.status_code}")
            result = resp.json()
            content = result.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                d = json.loads(content[0]["text"])
            else:
                d = result.get("result", {})
            rows = d.get("rows", [])
            _scan_backoff["delay"] = 30.0
            _scan_backoff["until"] = 0.0
            asof = datetime.now().isoformat()
            _scan_cache[cache_key] = {"ts": now, "data": rows, "asof": asof}
            _trim_cache(_scan_cache)
            _spawn_bg(_record_scan_baseline(rows))
            _spawn_bg(_run_institutional_alerts(rows))
            return _scan_payload(rows, False, asof, columns, cache_age=0, limit=limit)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"cvforge force-refresh failed: {e}")
        raise HTTPException(502, f"force refresh failed: {e}") from e


# Per-ticker daily history cache — the collection only changes once per scan
# upsert, and the frontend polls every 15 min; 60s is plenty.
_history_cache = {"ts": 0.0, "days": 0, "data": None}


@router.get("/scan/history")
async def scan_history(days: int = Query(14, ge=2, le=60)):
    """
    Per-ticker daily options-volume history from the scan baseline collector
    (flow_scan_daily: total/call/put volume per ticker per day). Powers the
    scanner's rollup sparklines and multi-day persistence streaks — the
    "what are they following across sessions" read. Mongo-only, no upstream.
    """
    nowt = time.time()
    if (
        _history_cache["data"] is not None
        and _history_cache["days"] == days
        and nowt - _history_cache["ts"] < 60
    ):
        return _history_cache["data"]
    out: dict[str, list] = {}
    try:
        from server import db  # deferred: circular import

        cutoff = (datetime.now(_ET) - timedelta(days=days)).strftime("%Y-%m-%d")
        cur = db.flow_scan_daily.find(
            {"date": {"$gte": cutoff}},
            {"_id": 0, "ticker": 1, "date": 1, "total_vol": 1, "call_vol": 1, "put_vol": 1},
        ).sort("date", 1).limit(40000)
        async for doc in cur:
            out.setdefault(doc["ticker"], []).append({
                "date": doc["date"],
                "total_vol": doc.get("total_vol") or 0,
                "call_vol": doc.get("call_vol") or 0,
                "put_vol": doc.get("put_vol") or 0,
            })
    except Exception as e:
        # A transient Mongo hiccup must not become a cached-for-60s empty
        # payload that wipes the frontend's sparklines/streaks — serve the
        # last good result instead, and never cache the failure.
        logger.debug(f"scan history unavailable: {e}")
        if _history_cache["data"] is not None:
            return _history_cache["data"]
        return {"days": days, "tickers": {}, "asof": datetime.now(_ET).isoformat(), "stale": True}
    payload = {"days": days, "tickers": out, "asof": datetime.now(_ET).isoformat()}
    _history_cache.update(ts=nowt, days=days, data=payload)
    return payload


@router.get("/scan-public")
async def public_market_scan(
    slice_size: int = Query(default=8, ge=1, le=20),
    max_expiries: int = Query(default=2, ge=1, le=6),
):
    """Market-wide unusual-flow scan over the PAID Public Advanced API.

    Rotating-cursor sweep of a fixed 40-name universe (index ETFs + megas +
    high-beta mid-caps like SNDK/DVN): each call scans the next slice and
    returns the merged universe view. No hourly cap (60/min Public budget),
    no top-300-by-volume cutoff — mid-cap laddered building is included by
    construction, not crowded out by SPY/QQQ churn.

    Row/column shape is IDENTICAL to /scan so the frontend scanner and
    eval_institutional consume it unchanged. Fresh slices also feed the
    institutional alert pipeline (same _record_scan_baseline +
    _run_institutional_alerts background tasks as /scan).
    """
    import services.public_scanner as ps
    from services.public_budget import BudgetExhausted
    from services.public_budget import budget as _pub_budget

    try:
        await _pub_budget.acquire("api.public.com")
    except BudgetExhausted as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "public budget exhausted", "retry_after": e.retry_after},
        ) from e
    try:
        view = await ps.scan_next(slice_size=slice_size, max_expiries=max_expiries)
    except BudgetExhausted as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "public slice unaffordable", "retry_after": e.retry_after},
        ) from e
    finally:
        _pub_budget.release()

    rows = view["rows"]
    extras = view.get("quote_truth", {})
    dealer = view.get("dealer", {})
    asof = datetime.now().isoformat()
    _spawn_bg(_record_scan_baseline(rows))
    _spawn_bg(_run_institutional_alerts(rows, extras=extras, dealer=dealer))
    cov = view.get("coverage", {})
    # Honest freshness: slices carry their own ages — a merged view with
    # dropped or aging slices must not claim stale:false.
    is_stale = bool(cov.get("stale_dropped")) or (cov.get("max_age_s") or 0) > 300
    return {
        "columns": view["columns"],
        "rows": rows,
        "count": view["count"],
        "source": "public-scan",
        "stale": is_stale,
        "asof": asof,
        "scan_ttl": 60,
        "budget": _budget_state(),
        "public_budget": _pub_budget.status(),
        "coverage": view["coverage"],
        "tickers": view["tickers"],
        "quote_truth": extras,
        "dealer": dealer,
        "regimes": _cached_regimes(),
        "baselines": await _volume_baselines(),
        "prev_oi": await _prev_contract_oi(),
    }


@router.get("/alerts/quality")
async def institutional_alert_quality(
    days: str = Query(
        "7,14,30",
        description=(
            "Comma-separated window sizes in days; e.g. '7,14,30'. A single "
            "value keeps the legacy response shape; multiple values return "
            "a per-window map for trend sparklines."
        ),
    ),
):
    """Per rule × tier precision from realized moves (Conviction v2's
    calibration loop). Declared before the /alerts/{symbol} catch-all.

    One DuckDB query per window — the underlying /scan baseline table is
    much smaller than the FULL unfiltered feed, so a single batched call
    that aggregates 3 windows still costs one DB connection and is cheap
    vs. 3 separate frontend fetches (each would carry its own poll slot
    and cache key)."""
    from services import flow_alerts as fa
    from services import tier_lock as tl
    from services.duckdb_engine import db as duckdb_engine

    raw = (days or "").strip()
    if not raw:
        return {"quality_windows": {}, "days": [], "error": "empty days"}
    try:
        window_list = sorted({int(p.strip()) for p in raw.split(",") if p.strip()})
    except ValueError:
        return {"quality_windows": {}, "days": [], "error": f"days must be ints, got {raw!r}"}
    window_list = [d for d in window_list if 1 <= d <= 180]
    if not window_list:
        return {"quality_windows": {}, "days": [], "error": "no valid window specified"}
    try:
        fa.init_flow_alert_tables(duckdb_engine)
        # Back-compat: a single window keeps the original response shape so
        # callers on the legacy contract don't break.
        if len(window_list) == 1:
            return {"quality": fa.alert_quality(duckdb_engine, days=window_list[0]),
                    "days": window_list[0],
                    # Blademap v3 — conviction calibration rides every shape
                    "conviction_calibration": fa.conviction_calibration(
                        duckdb_engine, days=window_list[0])}
        out = {w: fa.alert_quality(duckdb_engine, days=w) for w in window_list}
        # v2.5 — per-tier per-day series for the sparkline. Always uses the
        # MAX window (a desk's full-history read) regardless of which 7/14/30
        # windows the caller requested for the headline strip — the sparkline
        # needs raw day-level resolution, not aggregated windows. Group-by
        # is (date, tier) so each tier carries its own N<=182 point series.
        daily_max = max(window_list)
        daily_rows = fa.alert_quality_daily(duckdb_engine, days=daily_max)
        daily_by_tier: dict[str, list] = {"GOLD": [], "SILVER": [], "BRONZE": []}
        for r in daily_rows:
            t = str(r.get("tier") or "").upper()
            if t in daily_by_tier:
                daily_by_tier[t].append({
                    "date": r.get("date"),
                    "n": r.get("n", 0),
                    "n_measured": r.get("n_measured", 0),
                    "wins": r.get("wins", 0),
                    "hit_rate": r.get("hit_rate"),
                    "avg_move_pct": r.get("avg_move_pct"),
                })
        return {
            "quality_windows": out,
            "days": window_list,
            "daily_series": daily_by_tier,
            "daily_series_days": daily_max,
            # Blademap v3 — conviction-band calibration: hit-rate per
            # 50-59 / 60-74 / 75+ bucket. Monotonic curve = the score
            # predicts; flat curve = sizing-by-conviction is decoration.
            "conviction_calibration": fa.conviction_calibration(
                duckdb_engine, days=daily_max),
            # v3.x tier-lock hysteresis: per-tier lock state surfaced
            # alongside quality. The retuner consults tier_lock.is_locked()
            # before proposing new thresholds; the frontend reads
            # tier_locks[tier].engaged + locked_hit_rate to render the
            # "Lock engaged: GOLD 75%" sigil on the Conviction strip.
            # Read-only on /alerts/quality; full state transitions happen
            # in /scan (which calls update_locks on each fresh ingest).
            "tier_locks": tl.get_all_locks(duckdb_engine),
        }
    except Exception as e:
        logger.warning(f"alert quality failed: {e}")
        return {"quality_windows": {}, "days": window_list, "daily_series": {},
                "daily_series_days": max(window_list) if window_list else 30,
                "tier_locks": {t: {"engaged": False, "locked_hit_rate": None,
                                    "locked_at": None}
                                for t in ("GOLD", "SILVER", "BRONZE")},
                "error": str(e)}


@router.get("/alerts/feed")
async def institutional_alert_feed(
    days: int = Query(7, ge=1, le=60),
    tier: str | None = Query(None, pattern="^(?i)(gold|silver|bronze)$"),
    ticker: str | None = Query(None),
    min_conviction: int | None = Query(None, ge=0, le=100),
    sort_by: str = Query("tier", pattern="^(tier|conviction)$"),
):
    """Persisted institutional alert feed from the server-side engine.

    Declared BEFORE the /alerts/{symbol} catch-all (route-ordering
    convention, cf. /api/news/article). Tier filter is a minimum:
    tier=silver returns GOLD + SILVER. Rows carry side/bias, BS entry
    price, conviction tier, and move-since-alert.

    Blademap v3: sort_by=conviction ranks by weighted score DESC (a
    92-conviction SILVER above a 61-conviction GOLD); min_conviction is
    the hard floor (Blademap alerts at >75).
    """
    from services import flow_alerts as fa
    from services.duckdb_engine import db as duckdb_engine

    try:
        fa.init_flow_alert_tables(duckdb_engine)
        rows = fa.read_alert_feed(duckdb_engine, days=days, min_tier=tier,
                                  ticker=ticker,
                                  min_conviction=min_conviction,
                                  sort_by=sort_by)
        return {"alerts": rows, "count": len(rows), "days": days,
                "sort_by": sort_by, "min_conviction": min_conviction}
    except Exception as e:
        logger.warning(f"alert feed failed: {e}")
        return {"alerts": [], "count": 0, "days": days, "error": str(e)}


@router.get("/alerts/stream")
async def institutional_alert_stream(
    days: int = Query(7, ge=1, le=60),
    min_conviction: int | None = Query(None, ge=0, le=100),
    max_seconds: int = Query(300, ge=10, le=1800),
):
    """SSE push for the Blademap v3 conviction feed — replaces frontend
    polling. Emits an `alerts` event whenever the top-of-book conviction
    changes (new alert or conviction re-rank), plus heartbeats. Auto-ends
    after max_seconds so connections don't leak; the client EventSource
    auto-reconnects."""
    import asyncio as _aio

    from fastapi.responses import StreamingResponse

    from services import flow_alerts as fa
    from services.duckdb_engine import db as duckdb_engine

    async def _alert_stream():
        import json as _json

        fa.init_flow_alert_tables(duckdb_engine)
        last_fingerprint = None
        deadline = time.time() + max_seconds
        while time.time() < deadline:
            try:
                alerts = await _aio.to_thread(
                    fa.read_alert_feed,
                    duckdb_engine, days=days,
                    min_conviction=min_conviction,
                    sort_by="conviction",
                )
                # fingerprint = top alert keys + count — cheap change detector
                fp = (len(alerts), tuple(a.get("key") for a in alerts[:25]))
                if fp != last_fingerprint:
                    last_fingerprint = fp
                    msg = _json.dumps({
                        "count": len(alerts),
                        "alerts": alerts[:50],
                        "ts": datetime.now(_ET).isoformat(),
                    })
                    yield f"event: alerts\ndata: {msg}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {_json.dumps({'error': str(e)})}\n\n"
                break
            hb = _json.dumps({"ts": datetime.now(_ET).isoformat()})
            yield f"event: heartbeat\ndata: {hb}\n\n"
            await _aio.sleep(5)

    return StreamingResponse(_alert_stream(), media_type="text/event-stream")


@router.get("/alerts/{symbol}")
async def unusual_activity_alerts(
    symbol: str,
    min_oi: int = Query(100, ge=0),
    min_vol_oi_ratio: float = Query(0.05, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """
    Unusual activity alerts for a symbol's options chain.

    Identifies unusual activity based on option chain snapshots:
    - **high_volume**: day_volume / open_interest ratio above threshold (near money only)
    - **high_iv**: IV in top 25% for near-money options, EITHER side (min OI 500)
    - **oi_spike**: open interest > 2x average for near-money options (min OI 500)
    - **delta_extreme**: deep ITM (|delta| > 0.6) with high OI (>200), either side
    - **premium_concentration**: per-side mid × that side's OI × 100 > $250K (min total OI 500)

    Each alert includes confidence scoring and human-readable factors.
    """
    sym = (symbol or "").strip().upper()

    columns = [
        "ticker", "strike_price", "expiration_date", "contract_type",
        "open_interest", "implied_volatility", "delta", "gamma",
        "bid", "ask", "midpoint", "day_volume", "underlying_price",
    ]
    if not CVFORGE_API_KEY:
        return {"alerts": [], "total": 0, "page": page, "page_size": page_size,
                "has_next": False, "error": "no API key"}

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CVFORGE_API_KEY}"}
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {
            "name": "get_chain",
            "arguments": {"symbol": sym.upper(), "params": columns},
        },
    }
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(CVFORGE_URL, json=payload, headers=headers)
            if resp.status_code != 200:
                return {"alerts": [], "total": 0, "page": page, "page_size": page_size,
                        "has_next": False, "error": f"HTTP {resp.status_code}"}
            result = resp.json()
            if "error" in result:
                return {"alerts": [], "total": 0, "page": page, "page_size": page_size,
                        "has_next": False, "error": str(result["error"])}
            content = result.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                raw = json.loads(content[0]["text"])
            else:
                raw = result.get("result", {})

            chain_data = raw.get("chain", [])
            spot = float(raw.get("underlying_price", 0) or 0)
            # Fallback: extract spot from first strike's underlying_price field
            if spot == 0 and chain_data and chain_data[0].get("strikes"):
                first_strike = chain_data[0]["strikes"][0]
                if first_strike and len(first_strike) > 1:
                    cv = first_strike[1] if len(first_strike) > 1 else []
                    # underlying_price is at index 12 in the requested columns
                    if cv and len(cv) > 12:
                        spot = float(cv[12] or 0)

            # Analyze each expiry for unusual activity
            all_alerts = []
            for exp in chain_data:
                expiry = exp.get("expiration", "")
                strikes = exp.get("strikes", [])
                if not strikes:
                    continue

                # Calculate per-expiry statistics
                call_data = []
                for s in strikes:
                    if not s or len(s) < 3:
                        continue
                    strike = float(s[0]) or 0
                    cv = s[1] if len(s) > 1 else []
                    pv = s[2] if len(s) > 2 else []

                    def safe_float(arr, idx):
                        try:
                            return float(arr[idx]) if arr and idx < len(arr) and arr[idx] is not None else 0.0
                        except (TypeError, ValueError):
                            return 0.0

                    # Column indices matching the requested columns array:
                    # 0:ticker 1:strike_price 2:expiration_date 3:contract_type
                    # 4:open_interest 5:implied_volatility 6:delta 7:gamma
                    # 8:bid 9:ask 10:midpoint 11:day_volume 12:underlying_price
                    call_oi = safe_float(cv, 4)
                    put_oi = safe_float(pv, 4)
                    call_vol = safe_float(cv, 11)
                    put_vol = safe_float(pv, 11)
                    call_iv = safe_float(cv, 5)
                    put_iv = safe_float(pv, 5)
                    call_delta = safe_float(cv, 6)
                    put_delta = safe_float(pv, 6)
                    call_bid = safe_float(cv, 8)
                    call_ask = safe_float(cv, 9)
                    put_bid = safe_float(pv, 8)
                    put_ask = safe_float(pv, 9)

                    call_data.append({
                        "strike": strike, "call_oi": call_oi, "put_oi": put_oi,
                        "call_vol": call_vol, "put_vol": put_vol,
                        "call_iv": call_iv, "put_iv": put_iv,
                        "call_delta": call_delta, "put_delta": put_delta,
                        "call_bid": call_bid, "call_ask": call_ask,
                        "put_bid": put_bid, "put_ask": put_ask,
                    })

                # Only analyze strikes near spot price (within 25%)
                if spot > 0:
                    near_money = [d for d in call_data if abs(d["strike"] - spot) / spot <= 0.25]
                else:
                    near_money = call_data

                if not near_money:
                    continue

                # Calculate statistics on near-money options only
                avg_oi = sum(d["call_oi"] + d["put_oi"] for d in near_money) / max(len(near_money), 1)
                iv_values = sorted(
                    v for p in near_money for v in (p["call_iv"], p["put_iv"]) if v > 0.01)

                for d in near_money:
                    alerts_for_strike = strike_unusual_flags(d, near_money, min_vol_oi_ratio)
                    confidence_score = 50
                    factors = []
                    total_oi = d["call_oi"] + d["put_oi"]
                    total_vol = d["call_vol"] + d["put_vol"]

                    if "high_volume" in alerts_for_strike:
                        vol_oi = total_vol / total_oi if total_oi else 0
                        confidence_score += 10
                        factors.append(f"Vol/OI ratio: {vol_oi * 100:.1f}% (threshold: {min_vol_oi_ratio * 100:.0f}%)")
                        factors.append(f"Day volume: {total_vol:.0f} contracts")

                    prem = per_side_premiums(d)
                    if "high_iv" in alerts_for_strike:
                        iv_used = d["call_iv"] if d["call_iv"] > 0.01 and d["call_iv"] >= d["put_iv"] else d["put_iv"]
                        side = "call" if d["call_iv"] >= d["put_iv"] else "put"
                        confidence_score += 10
                        factors.append(f"{side} IV: {iv_used * 100:.1f}% (75th percentile across both sides: {max(iv_values or [0]) * 100:.1f}%)")

                    if "oi_spike" in alerts_for_strike:
                        confidence_score += 10
                        factors.append(f"OI: {total_oi:.0f} (avg: {avg_oi:.0f}, {total_oi / max(avg_oi, 1):.1f}x average)")

                    # Check delta extreme with high OI (min 200)
                    if "delta_extreme" in alerts_for_strike:
                        confidence_score += 8
                        if abs(d["call_delta"]) > DELTA_EXTREME_ABS:
                            factors.append("Deep ITM call (delta: {:.2f}, OI: {:.0f})".format(d["call_delta"], d["call_oi"]))
                        else:
                            factors.append("Deep ITM put (delta: {:.2f}, OI: {:.0f})".format(abs(d["put_delta"]), d["put_oi"]))

                    # Premium concentration — per-side notional (was call_mid ×
                    # COMBINED OI, doubling call-side estimates)
                    if "premium_concentration" in alerts_for_strike:
                        confidence_score += 12
                        if prem["call_premium"] >= prem["put_premium"]:
                            factors.append("Est. call premium: ${:.0f}K concentrated at strike {:.0f}".format(prem["call_premium"] / 1000, d["strike"]))
                        else:
                            factors.append("Est. put premium: ${:.0f}K concentrated at strike {:.0f}".format(prem["put_premium"] / 1000, d["strike"]))

                    if alerts_for_strike:
                        classification = alerts_for_strike[0]  # Primary classification
                        confidence_score = min(100, confidence_score)

                        # Determine tier
                        if confidence_score >= 80:
                            tier = 1
                        elif confidence_score >= 65:
                            tier = 2
                        elif confidence_score >= 50:
                            tier = 3
                        elif confidence_score >= 35:
                            tier = 4
                        else:
                            tier = 5

                        # DTE calculation — ET-aware (expiry is a UTC calendar
                        # date; naive local now() mislabels DTE by a day)
                        try:
                            exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
                            dte = (exp_date - datetime.now(_ET).date()).days
                        except Exception:
                            dte = None

                        all_alerts.append({
                            "alert_id": "{}-{}-{}-{:.0f}".format(sym, expiry, classification, d["strike"]),
                            "ticker": sym,
                            "classification": classification,
                            "strike": d["strike"],
                            "expiration": expiry,
                            "dte": dte,
                            "underlying_price": spot,
                            "oi": total_oi,
                            "call_oi": d["call_oi"],
                            "put_oi": d["put_oi"],
                            "iv": d["call_iv"] if d["call_iv"] > 0 else d["put_iv"],
                            "delta": d["call_delta"],
                            "day_volume": total_vol,
                            "vol_oi_ratio": (total_vol / total_oi) if total_oi > 0 else 0,
                            "confidence_score": confidence_score,
                            "confidence_factors": factors,
                            "tier": tier,
                            "created_at": datetime.now().isoformat(),
                        })

            # Sort by confidence score descending
            all_alerts.sort(key=lambda a: a["confidence_score"], reverse=True)
            total = len(all_alerts)

            # Paginate
            start = (page - 1) * page_size
            end = start + page_size
            page_alerts = all_alerts[start:end]

            return {
                "alerts": page_alerts,
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_next": end < total,
                "data_source": "cvserver",
                "spot_price": spot,
                "fetched_at": datetime.now().isoformat(),
            }
    except Exception as e:
        logger.warning(f"unusual activity alerts: {sym}: {e}")
        return {"alerts": [], "total": 0, "page": page, "page_size": page_size,
                "has_next": False, "error": str(e)}


# ── Regime (GEX-derived, TV-enriched) ──
# The Blademap pill polls this every 6s and reads current_state / confidence /
# is_warming. current_state strings must respect the frontend classifier:
# "trend"/"bull" → green, "mean"/"bear"/"rever" → red, anything else → chop.
_TV_DEMO_TICKERS = {"AAPL", "AMZN", "GM", "KO", "MCD", "META", "VIX", "XOM"}
_tv_signal_cache: dict[str, tuple[float, dict | None]] = {}
_TV_CACHE_TTL = 60


async def _fetch_tv_signal(sym: str) -> dict | None:
    """Optional trading-volatility enrichment. Never raises, never blocks >2.5s."""
    key = os.environ.get("TRADING_VOLATILITY_API_KEY", "")
    if not key and sym not in _TV_DEMO_TICKERS:
        return None
    cached = _tv_signal_cache.get(sym)
    if cached and time.time() - cached[0] < _TV_CACHE_TTL:
        return cached[1]
    result = None
    try:
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        async with httpx.AsyncClient(timeout=2.5) as client:
            resp = await client.get(
                "https://stocks.tradingvolatility.net/api/v2/signals",
                params={"ticker": sym}, headers=headers,
            )
            if resp.status_code == 200:
                result = resp.json()
    except Exception as e:
        logger.debug(f"tv signal unavailable for {sym}: {e}")
    _tv_signal_cache[sym] = (time.time(), result)
    while len(_tv_signal_cache) > 200:
        oldest = next(iter(_tv_signal_cache))
        del _tv_signal_cache[oldest]
    return result


@router.get("/regime/{ticker}")
async def regime(ticker: str):
    """
    Live market regime for the Blademap pill, derived from the same GEX
    structure the heatmap already computes (60s-cached build_heatmap — the
    argument tuple matches the frontend's own /api/heatmap call, so at the 6s
    poll this is a cache hit, no extra chain fetches).
    """
    sym = (ticker or "").strip().upper()
    if not sym:
        raise HTTPException(400, "ticker required")
    try:
        from server import build_heatmap  # deferred: avoids circular import

        hm = await build_heatmap(sym, 6, True, "day", None, False, 80)
        gf = (hm or {}).get("gamma_flip") or {}
        mr = (hm or {}).get("market_regime") or {}
        gex_regime = gf.get("regime")
        spot = gf.get("spot") or (hm or {}).get("spot")
        flip = gf.get("gamma_flip")
        dist = gf.get("dist_to_flip")
        total_gex = gf.get("total_gex")
        vol_env = mr.get("regime")

        dist_pct = None
        if dist is not None and spot:
            dist_pct = dist / spot * 100.0
        elif flip is not None and spot:
            dist_pct = (spot - flip) / spot * 100.0

        if gex_regime == "negative_gamma":
            state = "TRENDING_BEAR"
        elif gex_regime == "positive_gamma":
            if (
                dist_pct is not None and dist_pct >= 1.5
                and (total_gex or 0) > 0
                and vol_env in ("calm", "normal", None)
            ):
                state = "TRENDING_BULL"
            elif dist_pct is not None and abs(dist_pct) >= 0.5:
                state = "MEAN_REVERTING"
            else:
                state = "RANGING"
        else:
            # No usable chain/GEX data — stay alive but honest.
            return {
                "ticker": sym, "current_state": "RANGING", "confidence": 0.0,
                "is_warming": True, "gex_regime": gex_regime,
                "asof": (hm or {}).get("asof"),
            }

        confidence = min(abs(dist_pct) / 5.0, 1.0) if dist_pct is not None else 0.0
        out = {
            "ticker": sym,
            "current_state": state,
            "confidence": round(confidence, 3),
            "is_warming": False,
            "gex_regime": gex_regime,
            "gamma_flip": flip,
            "dist_to_flip_pct": round(dist_pct, 3) if dist_pct is not None else None,
            "total_gex": total_gex,
            "vol_env": vol_env,
            "atm_iv": mr.get("atm_iv"),
            "asof": (hm or {}).get("asof"),
        }
        tv = await _fetch_tv_signal(sym)
        if tv:
            out["tv_signal"] = tv
        # Paper-accurate GEX metrics (Barbon-Buraschi ΓIB + flip metrics)
        try:
            from services.gex_paper_accurate import DEFAULT_ADV_SHARES, compute_flip_metrics, compute_gamma_imbalance
            if total_gex and spot and spot > 0:
                out["paper_metrics"] = {
                    "gamma_imbalance": compute_gamma_imbalance(total_gex, spot, adv_shares=DEFAULT_ADV_SHARES),
                    "flip_metrics": compute_flip_metrics(spot, flip, total_gex),
                }
        except Exception:
            pass  # silent by design: flip_metrics omitted from card; outer handler at L1675 logs
        return out
    except Exception as e:
        logger.warning(f"regime failed for {sym}: {e}")
        return {"ticker": sym, "current_state": "RANGING", "confidence": 0.0,
                "is_warming": True, "error": str(e)}


# ── Signal-to-trade bridge: alerts → paper trades + journal seeds ──

@router.get("/journal/trades")
async def journal_trades(status: str = Query("all", pattern="^(all|open|closed)$"),
                         days: int = Query(365, ge=1, le=3650)):
    """Server-persisted auto-journal entries (survives localStorage clears).
    Shaped as floww_trades_v2 entries + provenance so the frontend can
    merge them into its offline store."""
    from services.journal_store import get_engine, init_journal_tables, read_trades
    init_journal_tables(get_engine())
    trades = read_trades(get_engine(), status=status, days=days)
    return {"trades": trades, "count": len(trades)}


@router.get("/journal/stats")
async def journal_stats(days: int = Query(90, ge=1, le=3650)):
    """Per-setup win-rate stats over closed journaled trades: overall,
    grouped by setup label, and split by GEX regime."""
    from services.journal_store import get_engine, init_journal_tables, setup_stats
    init_journal_tables(get_engine())
    return setup_stats(get_engine(), days=days)


@router.post("/journal/close")
async def journal_close(request: dict):
    """Close a journaled trade: body {key, exit_price, exit_date} where key
    is the journalSeedKey() composite. Used by the paper-engine close-out
    sync and by the journal UI when the server store is the source."""
    from services.journal_store import close_trade, get_engine, init_journal_tables
    init_journal_tables(get_engine())
    key = str(request.get("key") or "")
    try:
        exit_price = float(request.get("exit_price"))
    except (TypeError, ValueError) as err:
        raise HTTPException(400, "exit_price must be a number") from err
    exit_date = str(request.get("exit_date") or "")
    ok = close_trade(get_engine(), key, exit_price=exit_price, exit_date=exit_date)
    if not ok:
        raise HTTPException(404, f"no journaled trade for key {key}")
    return {"closed": True, "key": key}


@router.get("/auto-trade/preview")
async def auto_trade_preview(
    tier: str = Query("SILVER", pattern="^(GOLD|SILVER|BRONZE)$"),
    min_dte: int = Query(2, ge=0, le=180),
    equity: float = Query(100000.0, gt=0),
    days: int = Query(2, ge=1, le=30),
):
    """Preview which current institutional alerts would become paper trades.
    Read-only — no orders placed. Gates: tier floor, BUY-side directional
    claims only, DTE >= min_dte (skips 0DTE), one trade per contract."""
    from services import flow_alerts as fa
    from services.duckdb_engine import db as duckdb_engine
    from services.flow_trade_bridge import build_auto_trades

    fa.init_flow_alert_tables(duckdb_engine)
    alerts = fa.read_alert_feed(duckdb_engine, days=days)
    trades = build_auto_trades(alerts, account_equity=equity,
                               min_tier=tier, min_dte=min_dte)

    # Kill-switch visibility on the preview (GSD risk wiring) — advisory
    # only here; the hard gate lives in /auto-trade/execute.
    from services import auto_trade_risk
    kill_switch_status = auto_trade_risk.status(equity)

    return {"trades": trades, "count": len(trades),
            "gates": {"min_tier": tier, "min_dte": min_dte, "equity": equity,
                      "kill_switch": kill_switch_status}}


@router.post("/auto-trade/execute")
async def auto_trade_execute(
    confirm: bool = Query(False),
    tier: str = Query("SILVER", pattern="^(GOLD|SILVER|BRONZE)$"),
    min_dte: int = Query(2, ge=0, le=180),
    equity: float = Query(100000.0, gt=0),
    days: int = Query(2, ge=1, le=30),
):
    """Execute the previewed trades through the paper-trading engine and
    return journal seed entries for the frontend to persist into
    floww_trades_v2. Requires ?confirm=true (two-step arm/fire)."""
    if not confirm:
        raise HTTPException(400, "execute requires ?confirm=true — preview first with GET /auto-trade/preview")

    from services import flow_alerts as fa
    from services.duckdb_engine import db as duckdb_engine
    from services.flow_trade_bridge import build_auto_trades

    fa.init_flow_alert_tables(duckdb_engine)
    alerts = fa.read_alert_feed(duckdb_engine, days=days)
    trades = build_auto_trades(alerts, account_equity=equity,
                               min_tier=tier, min_dte=min_dte)

    # ── Kill-switch gate (GSD risk wiring) ──────────────────────────────
    # Tripped switch (-2% daily loss / -5% drawdown from peak) blocks ALL
    # new auto-trades for the day. Manual reset via /auto-trade/risk-reset.
    from services import auto_trade_risk
    allowed, risk_reason = auto_trade_risk.ensure_trading_allowed(equity)
    if not allowed:
        return {
            "executed": [], "rejected": [
                {"ckey": t["ckey"], "error": risk_reason} for t in trades],
            "journal_seeds": [], "journal_added_server": 0,
            "count": 0, "accepted": 0,
            "kill_switch": auto_trade_risk.status(equity),
        }

    executed, rejected, journal_seeds = [], [], []
    # Server-side journal persistence — file-backed (data/journal.duckdb),
    # survives restarts and localStorage clears. Written BEFORE the engine
    # loop so a paper-engine failure never loses the journal record.
    try:
        from services.journal_store import get_engine, init_journal_tables, save_seeds
        jeng = get_engine()
        init_journal_tables(jeng)
        seeds = [t["journal_entry"] | {"ckey": t["ckey"]} for t in trades]
        journal_added = save_seeds(jeng, seeds)
    except Exception as e:
        logger.warning("server journal persistence failed (continuing): %s", e)
        journal_added = 0

    try:
        from server import _paper_engine
        engine = _paper_engine
    except Exception:
        engine = None

    for t in trades:
        order_payload = t["order"]
        journal_seeds.append(t["journal_entry"])
        if engine is None:
            executed.append({"ckey": t["ckey"], "status": "no_paper_engine",
                             "reason": "paper trading engine not initialized"})
            continue
        try:
            result = engine.submit_order(
                symbol=order_payload["symbol"],
                side=order_payload["side"],
                quantity=order_payload["quantity"],
                order_type=order_payload.get("order_type", "market"),
            )
            result["ckey"] = t["ckey"]
            executed.append(result)
            # Feed post-trade equity into the kill switch so a losing
            # streak trips it mid-batch, stopping the remaining orders.
            if result.get("status") == "accepted":
                if auto_trade_risk.record_fill(equity):
                    rejected.append({"ckey": None,
                                     "error": "kill switch tripped mid-batch — remaining orders cancelled"})
                    break
        except Exception as e:
            logger.warning("auto-trade submit failed for %s: %s", t["ckey"], e)
            rejected.append({"ckey": t["ckey"], "error": str(e)})

    ok = sum(1 for r in executed if r.get("status") == "accepted")
    return {
        "executed": executed, "rejected": rejected,
        "journal_seeds": journal_seeds,
        "journal_added_server": journal_added,
        "count": len(trades), "accepted": ok,
        "kill_switch": auto_trade_risk.status(equity),
    }


@router.post("/auto-trade/risk-reset")
async def auto_trade_risk_reset():
    """Manually reset the auto-trade kill switch (requires human review
    per risk policy — this endpoint IS the manual reset)."""
    from services import auto_trade_risk
    return {"reset": True, "kill_switch": auto_trade_risk.reset()}


# ── Dedicated risk/killswitch endpoint ──────────────────────────────────────────
# Standalone read/write endpoints for the kill switch, separate from the
# auto-trade pipeline (which already gates via auto_trade_risk internally).
# The frontend uses these for a risk-status card + manual reset button.

@router.get("/risk/killswitch")
async def risk_killswitch_status(equity: float = Query(100000.0, gt=0)):
    """Current kill-switch status. equity is the current account equity used
    to seed start_day() on first call of a new day."""
    from services import auto_trade_risk
    return auto_trade_risk.status(equity)


@router.post("/risk/killswitch/reset")
async def risk_killswitch_reset():
    """Manual reset (human review required per risk policy)."""
    from services import auto_trade_risk
    return {"reset": True, "kill_switch": auto_trade_risk.reset()}


@router.post("/risk/killswitch/trip")
async def risk_killswitch_trip(equity: float = Query(100000.0, gt=0)):
    """Manually trip the kill switch for testing. Returns the new status."""
    from services import auto_trade_risk
    ks = auto_trade_risk.get_kill_switch(equity=equity)
    ks._trip("manual_trip_via_api")
    return ks.get_status()


# ── Outcome ledger: measured alert quality ──────────────────────────

_outcome_cache: dict[str, tuple[float, dict]] = {}   # key -> (ts, payload)
_OUTCOME_TTL = 6 * 3600   # nightly cron refreshes Mongo; in-process cache is a courtesy

_calibration_blob: tuple[float, dict] | None = None  # (ts, blob) — cron's fit
_CALIBRATION_TTL = 1 * 3600  # refresh writes rarely; 1h courtesy window


async def _load_calibration() -> dict | None:
    """Cached stage blob from the cron's /outcomes/refresh fit (Mongo
    calibration_latest). Fail-open: Mongo down / no fit yet → None, and the
    live path fires exactly as before (p_move=None, "uncalibrated").

    (C-REGION — Agent C. Closes the C2 loop: fit→cache existed, consume
    did not — _run_institutional_alerts never loaded this.)
    """
    import time as _time

    global _calibration_blob
    hit = _calibration_blob
    if hit and _time.time() - hit[0] < _CALIBRATION_TTL:
        return hit[1]
    try:
        from server import db as mongo_db  # deferred: circular import
        doc = await mongo_db.flow_outcome_cache.find_one({"_id": "calibration_latest"})
        if doc and isinstance(doc.get("stage"), int) and doc.get("stage") >= 1 and doc.get("model"):
            blob = {k: v for k, v in doc.items() if k != "_id"}
            _calibration_blob = (_time.time(), blob)
            return blob
    except Exception:
        pass  # Mongo down — fire uncalibrated, never crash the scan
    return None


def get_calibration_status() -> dict:
    """Explicit staged-calibration status for D's C11 health section.

    Fail-open: no blob yet → stage 0 + uncalibrated note (unknown, never
    fabricated). Replaces health's lazy read of the private _calibration_blob.
    """
    import time as _time

    hit = _calibration_blob
    if not hit:
        return {"stage": 0, "n": 0, "method_note": "uncalibrated: no fit cached yet",
                "model_kind": None, "age_s": None}
    ts, blob = hit
    blob = blob if isinstance(blob, dict) else {}
    model = blob.get("model") if isinstance(blob.get("model"), dict) else {}
    try:
        age = round(_time.time() - float(ts), 1)
    except (TypeError, ValueError):
        age = None
    return {"stage": blob.get("stage", 0), "n": blob.get("n", 0),
            "method_note": blob.get("method_note", ""),
            "model_kind": model.get("kind"), "age_s": age}


async def _load_outcomes(days: int, horizon: int) -> dict | None:
    """Precomputed stats from the nightly cron (Mongo flow_outcome_cache);
    falls back to computing live when the cron hasn't run yet."""
    import time as _time

    from services import flow_outcomes as fo
    from services.duckdb_engine import db as duckdb_engine

    key = f"{days}:{horizon}"
    hit = _outcome_cache.get(key)
    if hit and _time.time() - hit[0] < _OUTCOME_TTL:
        return hit[1]
    # 1. nightly cron's precomputed snapshot
    try:
        from server import db as mongo_db  # deferred: circular import
        doc = await mongo_db.flow_outcome_cache.find_one({"_id": f"outcomes_h{horizon}"})
        if doc and doc.get("status") == "ok":
            stats = {k: v for k, v in doc.items() if k != "_id"}
            stats.setdefault("source", "cron")
            _outcome_cache[key] = (_time.time(), stats)
            return stats
    except Exception:
        pass  # Mongo down — fall through to live compute
    # 2. live compute fallback (cron cold — e.g. fresh deploy)
    try:
        alerts = fo.read_alert_history(duckdb_engine, days=days)
        if not alerts:
            return None
        tickers = sorted({a.get("under") for a in alerts if a.get("under")})
        bars = await asyncio.get_running_loop().run_in_executor(None, fo.fetch_bars_yfinance, tickers)
        vix = await asyncio.get_running_loop().run_in_executor(None, fo.fetch_bars_yfinance, ["^VIX"])
        stats = fo.compute_outcomes(alerts, bars, vix.get("^VIX"), horizon=horizon)
        stats["ok"] = True
        stats["lookback_days"] = days
        stats["source"] = "live"
        _outcome_cache[key] = (_time.time(), stats)
        return stats
    except Exception:
        return None


@router.post("/outcomes/refresh")
async def alert_outcomes_refresh(
    days: int = Query(60, ge=7, le=180),
    horizon: int = Query(2, ge=1, le=10),
):
    """In-process outcome recompute — the nightly cron's actual workhorse.

    Why in-process: DuckDBEngine is a per-process :memory: singleton, so the
    ledger (flow_alerts_daily) only exists inside THIS server process — a
    separate cron process reads its own empty DB and can never see the
    alerts. The cron therefore triggers this endpoint (fail-closed behind
    X-API-Key) and the result is written to Mongo flow_outcome_cache, where
    the brief's outcome section reads it.

    Always 200 with a status field: cold ledger (no_alerts) and missing
    bars (no_bars) are normal nightly states, not errors.
    """
    import time as _time

    from services import flow_calibration as fc
    from services import flow_outcomes as fo
    from services.duckdb_engine import db as duckdb_engine

    alerts = fo.read_alert_history(duckdb_engine, days=days)
    if not alerts:
        _outcome_cache.clear()
        return {"ok": True, "status": "no_alerts", "days": days,
                "message": "ledger cold — nothing to refresh"}

    tickers = sorted({a.get("under") for a in alerts if a.get("under")})
    loop = asyncio.get_running_loop()
    bars = await loop.run_in_executor(None, fo.fetch_bars_yfinance, tickers)
    vix = await loop.run_in_executor(None, fo.fetch_bars_yfinance, ["^VIX"])
    if not bars:
        return {"ok": True, "status": "no_bars", "days": days,
                "message": "yfinance bars unavailable — last good cache stays"}

    stats = fo.compute_outcomes(alerts, bars, vix.get("^VIX"), horizon=horizon)
    stats["ok"] = True
    stats["lookback_days"] = days
    stats["computed_at"] = datetime.now(UTC).isoformat()
    stats["status"] = "ok"
    stats.setdefault("source", "recompute")

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "floww")
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    try:
        mdb = client[db_name]
        await mdb.flow_outcome_cache.update_one(
            {"_id": f"outcomes_h{horizon}"}, {"$set": stats}, upsert=True)
        # Calibration snapshot — same labeling pass feeds the stage ladder.
        try:
            labeled = fo.label_alerts(alerts, bars, vix.get("^VIX"), horizon=horizon)
            cal = fc.fit_calibration(labeled)
            cal_doc = {"ok": True, "computed_at": stats["computed_at"], **cal}
            await mdb.flow_outcome_cache.update_one(
                {"_id": "calibration_latest"}, {"$set": cal_doc}, upsert=True)
            try:  # C7 value table rides the same pass (Sync-3 kill/keep read)
                stats["rule_value"] = fo.rule_value_table(labeled)
            except Exception as ve:
                logger.warning("outcomes/refresh: rule value skipped: %s", ve)
        except Exception as e:  # calibration fit is additive, never fatal
            logger.warning("outcomes/refresh: calibration fit skipped: %s", e)
    finally:
        client.close()

    # Refresh this process's view immediately (don't wait for TTL).
    _outcome_cache[f"{days}:{horizon}"] = (_time.time(), stats)
    return {"ok": True, "status": "ok", "days": days, "horizon": horizon,
            "alerts": len(alerts), "computed_at": stats["computed_at"],
            "rules": sorted((stats.get("per_rule") or {}).keys())}


@router.get("/model")
async def calibration_model():
    """Calibrated P(move) status + coefficients.

    The server computes p_move and attaches it to rows/alerts — this endpoint
    exposes WHICH model, its stage ladder position, and its provenance so the
    desk can see whether the probability on the tape is measured or honest-
    uncalibrated. Structural parity: the frontend never recomputes p.
    """
    from services import flow_calibration as fc
    from services import flow_outcomes as fo
    from services.duckdb_engine import db as duckdb_engine

    alerts = fo.read_alert_history(duckdb_engine, days=90)
    if not alerts:
        return {
            "ok": True, "stage": 0, "n": 0,
            "method_note": "no alerts in ledger — calibration has nothing to fit",
            "p_move": None,
        }
    tickers = sorted({a.get("under") for a in alerts if a.get("under")})
    bars = await asyncio.get_running_loop().run_in_executor(None, fo.fetch_bars_yfinance, tickers)
    vix = await asyncio.get_running_loop().run_in_executor(None, fo.fetch_bars_yfinance, ["^VIX"])
    labeled = fo.label_alerts(alerts, bars, vix.get("^VIX"))
    cal = fc.fit_calibration(labeled)
    out = {"ok": True, **fc.calibration_status_blob(cal)}
    try:  # C7: per-rule value rides the live report too (Sync-3 kill/keep)
        out["rule_value"] = fo.rule_value_table(labeled)
    except Exception as ve:
        logger.warning("model: rule value skipped: %s", ve)
    # Sample the p semantics on one row so consumers see the shape honestly.
    if labeled:
        out["p_move_sample"] = fc.predict_p_move(cal, labeled[0])
    return out


@router.get("/outcomes")
async def alert_outcomes(
    days: int = Query(60, ge=7, le=180, description="Alert-history lookback window"),
    horizon: int = Query(2, ge=1, le=10, description="Forward sessions to measure each alert over"),
    sigma_k: float = Query(0.75, gt=0, le=5, description="Hit threshold: |side-signed cum return| ≥ k·σ20"),
    min_alerts: int = Query(5, ge=1, le=50, description="Below this many measured alerts a rule reports precision=null (uncalibrated)"),
):
    """Control-matched per-rule precision/lift for the alert ledger.

    Joins flow_alerts_daily (DuckDB, read-only) to yfinance daily bars and
    VIX (free — zero cvforge budget), labels each alert hit/miss against the
    vol-scaled forward move, builds a matched control cohort from non-alert
    ticker-days, and reports precision, control rate, lift, Wilson CI,
    cluster-bootstrap lift CI, and MFE/MAE payoff stats per rule.

    Rules below min_alerts measured alerts report precision=null +
    uncalibrated=true — the dashboard shows 'uncalibrated: n=k', never a
    fabricated small-n number. Serves the nightly cron's precomputed snapshot
    (Mongo flow_outcome_cache) when present; falls back to live compute.
    This endpoint is the source of truth the alert thresholds eventually get
    tuned from (replaces hand-picked defaults with measured hit rates).
    """
    stats = await _load_outcomes(days, horizon)
    if stats is None:
        return {
            "ok": True, "status": "no_alerts",
            "message": "No alerts in flow_alerts_daily within the lookback — "
                       "the ledger fills as the institutional engine fires.",
            "lookback_days": days, "per_rule": {}, "overall": {"n_measured": 0, "precision": None},
        }
    stats = dict(stats)
    stats.setdefault("sigma_k", sigma_k)
    stats["ok"] = True
    return stats
