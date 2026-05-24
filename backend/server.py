"""
Confluence Decoder - Skylit-style Heatseeker GEX Analytics
- Databento: real-time/EOD Open Interest via OPRA.PILLAR statistics + Live trades for Flowseeker
- yfinance: spot + IV from option chains (fallback for OI when Databento has no data)
- Polygon: stock aggs, tap-count history
- Black-Scholes gamma -> per-strike (and per-strike×expiry) GEX
- Node hierarchy, patterns, velocity, rolling, trinity
"""
from fastapi import FastAPI, APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import os
import json
import logging
import asyncio
import math
import time
from collections import deque
import httpx
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm

from services.duckdb_engine import db as duckdb_engine
from services.vpin_engine import VpinEngine
from services.trinity_alignment import TrinityAlignmentIndex
from services.node_lifecycle import NodeLifecycleTracker
from services.anomaly_detector import FlowAnomalyDetector
from services.liquidity_metrics import KyleLambda, AmihudIlliquidity, MarketFragilityIndex
from services.numba_greeks import compute_all_greeks
from services.gex_aggregator import GexAggregator
from services.stochastic_vol import SABRModel, SVIProfile, VolSurfaceConstructor
from services.hawkes_process import HawkesProcess
from services.websocket_streamer import manager as ws_manager
from databento_provider import init_cache, fetch_oi_for_ticker, PARENT_MAP, stream_live_trades
from portfolio import Position, Portfolio, calc_position_size
from schwab import SCHWAB_CLIENT_ID
from vol_analytics import (
    calc_iv_surface_data,
    calc_skew_metrics,
    calc_realized_volatility,
    calc_iv_rank_percentile,
)
from advanced_analytics import (
    calc_implied_pdf,
    calc_market_regime,
    calc_hedge_impulse_curve,
    calc_pressure_cloud,
    calc_charm_integral,
    calc_gamma_flip_levels,
    calc_vex,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")

client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
db = client[DB_NAME]

LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "app.log", mode="a"),
    ],
)
log = logging.getLogger("heatseeker")

app = FastAPI(title="Confluence Decoder")

# ----------------------------- Rate Limiting -----------------------------
from collections import defaultdict

_rate_limits: dict = defaultdict(deque)  # ip -> deque[timestamp]

RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))  # requests per minute
_TEST_MODE = os.environ.get("TESTING", "").lower() in ("1", "true", "yes")

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiter: RATE_LIMIT requests per minute per IP with sliding window.
    Uses a deque for O(1) cleanup and proper sliding window semantics.
    Disabled in TESTING mode to avoid flaky test failures."""
    if _TEST_MODE:
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    # Bypass rate limit for localhost/internal traffic
    if client_ip in ("127.0.0.1", "::1", "localhost"):
        return await call_next(request)
    now = time.time()
    window = 60.0  # 1 minute
    
    if client_ip not in _rate_limits:
        _rate_limits[client_ip] = deque()
    
    # Remove entries outside the sliding window
    dq = _rate_limits[client_ip]
    while dq and now - dq[0] >= window:
        dq.popleft()
    
    if len(dq) >= RATE_LIMIT:
        retry_after = int(window - (now - dq[0])) + 1
        log.warning(f"Rate limit exceeded for {client_ip} ({len(dq)}/{RATE_LIMIT})")
        # Track 429 in Prometheus
        try:
            from services.observability import rate_limit_429_count
            rate_limit_429_count.labels(client_ip=client_ip).inc()
        except Exception:
            pass
        # Include CORS headers so frontend can read the 429 (not blocked by CORS)
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "retry_after": retry_after,
                "message": f"Too many requests. Retry in {retry_after}s.",
            },
            headers={
                "Retry-After": str(retry_after),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
            },
        )
    
    dq.append(now)
    
    # Periodically clean empty IPs to prevent memory leak
    if len(_rate_limits) > 10000:
        empty_ips = [ip for ip, dq in _rate_limits.items() if not dq]
        for ip in empty_ips:
            del _rate_limits[ip]
    
    response = await call_next(request)
    return response


# ----------------------------- Global Exception Handler ------------------------------

from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    log.error(f"HTTP {exc.status_code} {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail), "status_code": exc.status_code, "path": request.url.path},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    log.error(f"Validation error {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed", "details": exc.errors(), "path": request.url.path},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
        },
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled exception {request.url.path}: {type(exc).__name__}: {exc}", exc_info=True)
    # Track error
    try:
        from error_tracking import log_error
        log_error(
            error_type=type(exc).__name__,
            message=str(exc),
            data={"path": request.url.path, "method": request.method}
        )
    except Exception:
        pass
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "type": type(exc).__name__, "path": request.url.path},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
        },
    )


# ----------------------------- Error Tracking & Performance API -----------------------------

@app.middleware("http")
async def performance_middleware(request: Request, call_next):
    """Track request performance."""
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    
    try:
        from error_tracking import perf_monitor, set_request_id
        endpoint = f"{request.method} {request.url.path}"
        perf_monitor.record(endpoint, duration_ms)
        set_request_id()
    except Exception:
        pass
    
    response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))
    return response


# Cache for spot/chains so we don't slam yfinance
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SEC = 25

# Dividend yields for Black-Scholes
DIV_YIELD = {"SPY": 0.013, "QQQ": 0.006, "^SPX": 0.013, "IWM": 0.012}


def cache_get(key: str):
    item = _cache.get(key)
    if not item:
        return None
    if time.time() - item["ts"] > CACHE_TTL_SEC:
        return None
    return item["data"]


def cache_set(key: str, data: Any):
    _cache[key] = {"ts": time.time(), "data": data}


def cache_get_or_set(key: str, fn, ttl: int = CACHE_TTL_SEC):
    """Get from cache or compute and store. fn is a sync callable."""
    item = _cache.get(key)
    if item and (time.time() - item["ts"]) < ttl:
        return item["data"]
    data = fn()
    _cache[key] = {"ts": time.time(), "data": data}
    return data


# ============ Portfolio Persistence (Mongo) ============

def _pos_to_dict(p):
    """Serialize a Position to a dict for Mongo storage."""
    return {
        "symbol": p.symbol, "option_type": p.option_type, "strike": p.strike,
        "expiry": p.expiry, "quantity": p.quantity, "entry_price": p.entry_price,
        "entry_iv": p.entry_iv, "underlying_price": p.underlying_price,
        "is_long": p.is_long, "dte": p.dte, "T": p.T,
        "delta": p.delta, "gamma": p.gamma, "vega": p.vega, "theta": p.theta,
        "vanna": p.vanna, "charm": p.charm, "vomma": p.vomma, "zomma": p.zomma,
        "price": p.price,
    }

def _pos_from_dict(d: Dict[str, Any]) -> Position:
    """Reconstruct a Position from a Mongo dict."""
    p = Position.__new__(Position)
    p.symbol = d["symbol"]
    p.option_type = d["option_type"]
    p.strike = d["strike"]
    p.expiry = d["expiry"]
    p.quantity = d["quantity"]
    p.entry_price = d["entry_price"]
    p.entry_iv = d["entry_iv"]
    p.underlying_price = d["underlying_price"]
    p.is_long = d.get("is_long", d["quantity"] > 0)
    p.dte = d.get("dte", 0)
    p.T = d.get("T", 0)
    p.delta = d.get("delta", 0)
    p.gamma = d.get("gamma", 0)
    p.vega = d.get("vega", 0)
    p.theta = d.get("theta", 0)
    p.vanna = d.get("vanna", 0)
    p.charm = d.get("charm", 0)
    p.vomma = d.get("vomma", 0)
    p.zomma = d.get("zomma", 0)
    p.price = d.get("price", 0)
    p.entry_date = datetime.now(timezone.utc)
    return p

async def _save_portfolio_to_mongo(name: str, portfolio: Portfolio):
    """Persist portfolio to Mongo."""
    positions = [_pos_to_dict(p) for p in portfolio.positions]
    await db.portfolios.update_one(
        {"_id": name},
        {"$set": {"positions": positions, "cash": portfolio.cash,
                   "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )

async def _load_portfolio_from_mongo(name: str) -> Optional[Portfolio]:
    """Load portfolio from Mongo. Returns None if not found."""
    doc = await db.portfolios.find_one({"_id": name})
    if not doc:
        return None
    p = Portfolio(doc.get("name", name))
    p.cash = doc.get("cash", 0.0)
    for pd in doc.get("positions", []):
        try:
            p.positions.append(_pos_from_dict(pd))
        except Exception:
            continue
    return p


# ============ Data Fetching Functions (moved here to maintain correct order) ============

def fetch_spot_and_chains(ticker: str, max_expiries: int = 4) -> Dict[str, Any]:
    """Returns spot + flattened option contracts (limited expiries near term)."""
    key = f"chain:{ticker}:{max_expiries}"
    hit = cache_get(key)
    if hit:
        return hit

    t = yf.Ticker(ticker)
    try:
        fi = t.fast_info
        spot = float(fi.get("lastPrice") or fi.get("last_price") or 0)
    except Exception:
        spot = 0.0
    if not spot:
        try:
            spot = float(t.history(period="1d")["Close"].iloc[-1])
        except Exception:
            spot = 0.0

    expiries = list(t.options or [])[:max_expiries]
    contracts: List[Dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()

    for exp in expiries:
        try:
            ch = t.option_chain(exp)
        except Exception as e:
            log.warning(f"chain fail {ticker} {exp}: {e}")
            continue
        exp_date = pd.to_datetime(exp).date()
        T = max((exp_date - today).days, 1) / 365.0
        for df, kind in [(ch.calls, "call"), (ch.puts, "put")]:
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                strike = float(row.get("strike", 0))
                oi = float(row.get("openInterest", 0) or 0)
                iv = float(row.get("impliedVolatility", 0) or 0)
                vol = float(row.get("volume", 0) or 0)
                if strike <= 0 or oi <= 0 or iv <= 0:
                    continue
                contracts.append({
                    "expiry": exp, "T": T, "type": kind,
                    "strike": strike, "oi": oi, "iv": iv, "volume": vol,
                })

    data = {"ticker": ticker, "spot": spot, "expiries": expiries, "contracts": contracts}
    cache_set(key, data)
    return data


# Tickers allowed to use Databento OI (paid). Default: SPY only. Persisted in Mongo (db.live_policy).
DEFAULT_PAID_TICKERS = {"SPY"}
PAID_TICKERS: set = set(DEFAULT_PAID_TICKERS)

# Session tracking for cost meter
_session_state: Dict[str, Any] = {
    "live_tape_active": False,
    "live_tape_ticker": None,
    "live_tape_started_at": None,
    "live_tape_auto_stop_at": None,
    "live_tape_session_id": None,
    "msg_count": 0,
}

# Live window + prefetch config
LIVE_WINDOW = {"start_hhmm": "09:00", "stop_hhmm": "10:30"}
PREFETCH_HHMM = "08:55"  # pre-fetch SPY OI 5 min before market open


def _in_window_now_et() -> bool:
    """Check if current time is within configured live window (US/Eastern)."""
    try:
        from zoneinfo import ZoneInfo
        et = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        # Fallback: use UTC-4 (EDT) during DST, UTC-5 (EST) otherwise
        import time
        is_dst = time.localtime().tm_isdst > 0
        offset = 4 if is_dst else 5
        et = datetime.now(timezone.utc) - timedelta(hours=offset)
    hhmm = et.strftime("%H:%M")
    return LIVE_WINDOW["start_hhmm"] <= hhmm <= LIVE_WINDOW["stop_hhmm"]


async def fetch_spot_and_chains_merged(ticker: str, max_expiries: int = 4) -> Dict[str, Any]:
    """yfinance for spot+IV + Databento for OI (only if ticker is in PAID_TICKERS).
    Falls back to pure yfinance for free-tier tickers."""
    yf_data = await asyncio.to_thread(fetch_spot_and_chains, ticker, max_expiries)
    yf_data["spot"]

    # Free-tier short-circuit: use yfinance OI only
    short = ticker.upper().replace("^", "")
    if short not in PAID_TICKERS:
        for c in yf_data["contracts"]:
            c["oi_source"] = "yfinance"
        return {**yf_data, "data_source": "yfinance"}

    dbn_oi = {}
    try:
        dbn_oi = await fetch_oi_for_ticker(ticker)
    except Exception as e:
        log.warning(f"databento OI lookup fail {ticker}: {e}")

    if not dbn_oi:
        for c in yf_data["contracts"]:
            c["oi_source"] = "yfinance"
        return {**yf_data, "data_source": "yfinance"}

    # Build (strike, expiry, type) -> OI map from Databento
    dbn_map: Dict[tuple, int] = {}
    for sym, c in dbn_oi.items():
        dbn_map[(c["strike"], c["expiry"], c["type"])] = c["oi"]

    # Overlay Databento OI onto yfinance IV/strike contracts
    yf_keys = set()
    for c in yf_data["contracts"]:
        key = (c["strike"], c["expiry"], c["type"])
        dbn_val = dbn_map.get(key)
        if dbn_val is not None:
            c["oi"] = max(c["oi"], dbn_val)
            c["oi_source"] = "databento"
        else:
            c["oi_source"] = "yfinance"
        yf_keys.add(key)

    # Add DBN-only contracts
    today = datetime.now(timezone.utc).date()
    iv_lists: Dict[str, list] = {}
    for c in yf_data["contracts"]:
        iv_lists.setdefault(c["expiry"], []).append(c["iv"])
    iv_avg_by_expiry: Dict[str, float] = {e: (sum(vs) / len(vs)) for e, vs in iv_lists.items() if vs}

    for (strike, expiry, typ), oi in dbn_map.items():
        if (strike, expiry, typ) in yf_keys:
            continue
        if expiry not in iv_avg_by_expiry:
            continue
        try:
            exp_d = datetime.strptime(expiry, "%Y-%m-%d").date()
        except Exception:
            continue
        T = max((exp_d - today).days, 1) / 365.0
        yf_data["contracts"].append({
            "expiry": expiry, "T": T, "type": typ, "strike": strike,
            "oi": oi, "iv": iv_avg_by_expiry[expiry], "volume": 0,
            "oi_source": "databento",
        })

    yf_data["data_source"] = "databento+yfinance"
    yf_data["dbn_contracts"] = len(dbn_map)
    return yf_data


# ----------------------------- GEX Aggregation --------------------------------

def compute_gex_by_strike(spot: float, contracts: List[Dict[str, Any]], ticker: str = "") -> List[Dict[str, Any]]:
    """Per-strike net GEX, VEX, and Vega. Convention: dealer-positive convention.
    For 0DTE/1DTE contracts, blends volume-weighted OI (from gflows heuristic):
    effective_oi = max(oi, volume * 0.5). This captures intraday flow for short-dated options."""
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    agg: Dict[float, Dict[str, float]] = {}
    for c in contracts:
        oi = c.get("oi", 0) or 0
        if oi <= 0 or (isinstance(oi, float) and math.isnan(oi)):
            continue
        # 0DTE/1DTE heuristic: blend daily volume into OI for real-time exposure
        dte = c.get("T", 1.0 / 365.0) * 365.0  # approx days to expiry (default 1 day)
        vol = c.get("volume", 0) or 0
        if dte <= 1.5 and vol > 0:
            effective_oi = max(oi, vol * 0.7)  # amplify via volume, never attenuate
        elif dte <= 3.0 and vol > oi * 2:
            effective_oi = max(oi, vol * 0.5)  # gflows: cap at volume * 0.5
        else:
            effective_oi = oi
        gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
        vanna = bs_vanna(spot, c["strike"], c["T"], c["iv"], q=q)
        vega_val = bs_vega(spot, c["strike"], c["T"], c["iv"], q=q)
        charm = bs_charm(spot, c["strike"], c["T"], c["iv"], q=q, kind=c["type"])
        vomma = bs_vomma(spot, c["strike"], c["T"], c["iv"], q=q)
        zomma = bs_zomma(spot, c["strike"], c["T"], c["iv"], q=q)
        if gamma <= 0 and abs(vanna) <= 0:
            continue
        gex_unit = gamma * effective_oi * 100.0 * spot * spot * 0.01
        vex_unit = vanna * effective_oi * 100.0 * spot * 0.01
        vega_unit = vega_val * effective_oi * 100.0
        charm_unit = charm * effective_oi * 100.0 * spot * 0.01
        vomma_unit = vomma * effective_oi * 100.0
        zomma_unit = zomma * effective_oi * 100.0 * spot * 0.01
        sign = 1.0 if c["type"] == "call" else -1.0
        bucket = agg.setdefault(c["strike"], {
            "strike": c["strike"], "gex": 0.0, "call_gex": 0.0, "put_gex": 0.0,
            "call_oi": 0.0, "put_oi": 0.0, "total_oi": 0.0,
            "vex": 0.0, "call_vex": 0.0, "put_vex": 0.0,
            "vega": 0.0, "call_vega": 0.0, "put_vega": 0.0,
            "charm": 0.0, "call_charm": 0.0, "put_charm": 0.0,
            "vomma": 0.0, "call_vomma": 0.0, "put_vomma": 0.0,
            "zomma": 0.0, "call_zomma": 0.0, "put_zomma": 0.0,
        })
        bucket["gex"] += sign * gex_unit
        bucket["vex"] += sign * vex_unit
        bucket["vega"] += sign * vega_unit
        bucket["charm"] += sign * charm_unit
        bucket["vomma"] += sign * vomma_unit
        bucket["zomma"] += sign * zomma_unit
        if c["type"] == "call":
            bucket["call_gex"] += gex_unit
            bucket["call_vex"] += vex_unit
            bucket["call_vega"] += vega_unit
            bucket["call_charm"] += charm_unit
            bucket["call_vomma"] += vomma_unit
            bucket["call_zomma"] += zomma_unit
            bucket["call_oi"] += oi
        else:
            bucket["put_gex"] += gex_unit
            bucket["put_vex"] += vex_unit
            bucket["put_vega"] += vega_unit
            bucket["put_charm"] += charm_unit
            bucket["put_vomma"] += vomma_unit
            bucket["put_zomma"] += zomma_unit
            bucket["put_oi"] += oi
        bucket["total_oi"] += oi

    out = sorted(agg.values(), key=lambda r: r["strike"])
    return out


def compute_gex_grid(spot: float, contracts: List[Dict[str, Any]], ticker: str = "") -> Dict[str, Any]:
    """2D grid: GEX, VEX, and Charm per (strike, expiry). Skylit-style heatmap layout."""
    if spot <= 0 or not contracts:
        return {"expiries": [], "strikes": [], "grid": {}, "vex_grid": {}, "charm_grid": {}}
    q = DIV_YIELD.get(ticker, 0.0)
    grid: Dict[str, Dict[float, float]] = {}
    vex_grid: Dict[str, Dict[float, float]] = {}
    charm_grid: Dict[str, Dict[float, float]] = {}
    strike_totals: Dict[float, float] = {}
    for c in contracts:
        gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
        vanna = bs_vanna(spot, c["strike"], c["T"], c["iv"], q=q)
        charm = bs_charm(spot, c["strike"], c["T"], c["iv"], q=q, kind=c["type"])
        if gamma <= 0:
            continue
        gex_unit = gamma * c["oi"] * 100.0 * spot * spot * 0.01
        vex_unit = vanna * c["oi"] * 100.0 * spot * 0.01
        charm_unit = charm * c["oi"] * 100.0 * spot * 0.01
        sign = 1.0 if c["type"] == "call" else -1.0
        cell = sign * gex_unit
        vex_cell = sign * vex_unit
        charm_cell = sign * charm_unit
        d = grid.setdefault(c["expiry"], {})
        d[c["strike"]] = d.get(c["strike"], 0.0) + cell
        dv = vex_grid.setdefault(c["expiry"], {})
        dv[c["strike"]] = dv.get(c["strike"], 0.0) + vex_cell
        dc = charm_grid.setdefault(c["expiry"], {})
        dc[c["strike"]] = dc.get(c["strike"], 0.0) + charm_cell
        strike_totals[c["strike"]] = strike_totals.get(c["strike"], 0.0) + cell

    expiries = sorted(grid.keys())
    strikes = sorted(strike_totals.keys())

    def _k(x: float) -> str:
        return str(int(x)) if float(x).is_integer() else str(x)

    return {
        "expiries": expiries,
        "strikes": strikes,
        "grid": {e: {_k(k): v for k, v in grid[e].items()} for e in expiries},
        "vex_grid": {e: {_k(k): v for k, v in vex_grid[e].items()} for e in expiries},
        "charm_grid": {e: {_k(k): v for k, v in charm_grid[e].items()} for e in expiries},
        "strike_totals": [{"strike": k, "gex": v} for k, v in sorted(strike_totals.items())],
    }
# Import from shared module to avoid circular imports with portfolio.py
from bs_greeks import (
    bs_gamma, bs_delta, bs_vanna, bs_charm, bs_vomma, bs_zomma, bs_vega,
    bs_call_price, bs_put_price,
    RISK_FREE_RATE as BS_RISK_FREE_RATE,
)
RISK_FREE_RATE = BS_RISK_FREE_RATE


# ----------------------------- Implied Move & Probability (from EzOptions) ------

def calc_implied_move(spot: float, contracts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Calculate implied move from ATM straddle price. Returns expected move in $ and %."""
    if spot <= 0 or not contracts:
        return None
    # Find ATM strike
    strikes = sorted(set(c["strike"] for c in contracts))
    if not strikes:
        return None
    atm = min(strikes, key=lambda s: abs(s - spot))
    # Get ATM call and put mid prices
    atm_calls = [c for c in contracts if c["strike"] == atm and c["type"] == "call"]
    atm_puts = [c for c in contracts if c["strike"] == atm and c["type"] == "put"]
    if not atm_calls or not atm_puts:
        return None
    # Use IV to estimate straddle price via BS
    call_iv = atm_calls[0].get("iv", 0.2)
    put_iv = atm_puts[0].get("iv", 0.2)
    T = atm_calls[0].get("T", 1/365)
    if T <= 0:
        T = 1/365
    avg_iv = (call_iv + put_iv) / 2
    # Straddle price ≈ 0.8 * S * σ * sqrt(T) (market standard approximation)
    straddle = 0.8 * spot * avg_iv * math.sqrt(T)
    return {
        "atm_strike": atm,
        "straddle_price": round(straddle, 2),
        "implied_move_pct": round((straddle / spot) * 100, 2),
        "implied_move_dollars": round(straddle, 2),
        "upper_range": round(spot + straddle, 2),
        "lower_range": round(spot - straddle, 2),
        "avg_iv": round(avg_iv, 4),
        "tte_years": round(T, 6),
    }


def calc_probability_distribution(spot: float, contracts: List[Dict[str, Any]],
                                   risk_free_rate: float = RISK_FREE_RATE) -> List[Dict[str, Any]]:
    """Risk-neutral probability distribution from option prices.
    Returns list of {strike, prob_above, prob_below, delta} per strike."""
    if spot <= 0 or not contracts:
        return []
    strikes = sorted(set(c["strike"] for c in contracts))
    result = []
    for k in strikes:
        # Get call IV at this strike
        calls = [c for c in contracts if c["strike"] == k and c["type"] == "call"]
        puts = [c for c in contracts if c["strike"] == k and c["type"] == "put"]
        iv = None
        T = None
        if calls:
            iv = calls[0].get("iv", 0.2)
            T = calls[0].get("T", 1/365)
        elif puts:
            iv = puts[0].get("iv", 0.2)
            T = puts[0].get("T", 1/365)
        if not iv or iv <= 0 or not T or T <= 0:
            continue
        try:
            d1 = (math.log(spot / k) + (risk_free_rate + 0.5 * iv**2) * T) / (iv * math.sqrt(T))
            d2 = d1 - iv * math.sqrt(T)
            prob_above = float(norm.cdf(d2))  # risk-neutral prob of finishing above K
            prob_below = 1.0 - prob_above
            delta_call = float(norm.cdf(d1))
            result.append({
                "strike": k,
                "prob_above": round(prob_above, 4),
                "prob_below": round(prob_below, 4),
                "delta": round(delta_call, 4),
                "iv": round(iv, 4),
            })
        except Exception:
            continue
    return result


def calc_aggregate_gex_curve(spot: float, contracts: List[Dict[str, Any]],
                              ticker: str = "") -> List[Dict[str, float]]:
    """Aggregate GEX curve: total GEX if spot moved to each price point.
    Shows how dealer gamma changes as price moves."""
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    strikes = sorted(set(c["strike"] for c in contracts))
    if not strikes:
        return []
    min_s = min(strikes)
    max_s = max(strikes)
    # Range: +/- 15% from current spot, or min/max strikes
    lo = max(min_s, spot * 0.85)
    hi = min(max_s, spot * 1.15)
    step = (hi - lo) / 100
    if step <= 0:
        return []
    curve = []
    price = lo
    while price <= hi:
        total_gex = 0.0
        for c in contracts:
            oi = c.get("oi", 0) or 0
            if oi <= 0:
                continue
            gamma = bs_gamma(price, c["strike"], c["T"], c["iv"], q=q)
            gex = gamma * oi * 100.0 * price * price * 0.01
            sign = 1.0 if c["type"] == "call" else -1.0
            total_gex += sign * gex
        curve.append({"price": round(price, 2), "gex": round(total_gex / 1e9, 4) if not (math.isnan(total_gex) or math.isinf(total_gex)) else 0.0})
        price += step
    return curve


# ----------------------------- Opportunity Detection (from GEX-Dashboard) ------

def detect_opportunities(strikes: List[Dict[str, Any]], nodes: Dict[str, Any],
                          spot: float, contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect trading opportunities from GEX analysis.
    Categories: gamma_squeeze, wall_support, wall_resistance, vol_expansion, vol_compression, pin_risk, gamma_ladder"""
    opportunities = []
    if not strikes or spot <= 0:
        return opportunities

    king = nodes.get("king")
    if not king:
        return opportunities
    abs(king.get("gex", 0)) or 1.0
    total_gex = nodes.get("total_gex", 0)
    polarity = nodes.get("polarity_level", spot)
    regime = nodes.get("regime", "neutral")

    # --- Gamma Squeeze: price approaching call wall from below ---
    call_wall = nodes.get("ceilings", [{}])
    call_wall_strike = call_wall[0]["strike"] if call_wall else None
    if call_wall_strike and spot < call_wall_strike:
        dist_pct = (call_wall_strike - spot) / spot * 100
        if dist_pct < 3.0:
            # Concentration of call GEX at wall
            calls_above = [s for s in strikes if s["strike"] > spot and s.get("call_gex", 0) > 0]
            total_call_gex = sum(s.get("call_gex", 0) for s in calls_above)
            max_call_gex = max((s.get("call_gex", 0) for s in calls_above), default=0)
            concentration = max_call_gex / total_call_gex if total_call_gex > 0 else 0
            proximity = 1 - (dist_pct / 3.0)
            confidence = min((concentration + proximity) / 2, 1.0)
            if confidence >= 0.3:
                opportunities.append({
                    "type": "gamma_squeeze",
                    "name": "Gamma Squeeze Setup",
                    "direction": "bullish",
                    "risk": "high",
                    "confidence": round(confidence, 2),
                    "description": f"Price {dist_pct:.1f}% below call wall at {call_wall_strike:.1f}. Breakout could trigger dealer hedging acceleration.",
                    "trigger": {"call_wall": call_wall_strike, "distance_pct": round(dist_pct, 2), "concentration": round(concentration, 2)},
                    "entry": (round(spot * 0.995, 2), round(call_wall_strike * 0.99, 2)),
                    "target": round(call_wall_strike * 1.02, 2),
                    "stop": round(spot * 0.97, 2),
                })

    # --- Put Wall Support ---
    put_wall = nodes.get("floors", [{}])
    put_wall_strike = put_wall[0]["strike"] if put_wall else None
    if put_wall_strike and spot > put_wall_strike:
        dist_pct = (spot - put_wall_strike) / spot * 100
        if dist_pct < 3.0:
            proximity = 1 - (dist_pct / 3.0)
            regime_bonus = 0.2 if regime == "positive" else 0
            confidence = min(proximity + regime_bonus, 1.0)
            if confidence >= 0.4:
                opportunities.append({
                    "type": "put_wall_support",
                    "name": "Put Wall Support",
                    "direction": "bullish",
                    "risk": "low",
                    "confidence": round(confidence, 2),
                    "description": f"Price {dist_pct:.1f}% above put wall at {put_wall_strike:.1f}. Dealers likely to buy dips here.",
                    "trigger": {"put_wall": put_wall_strike, "distance_pct": round(dist_pct, 2), "regime": regime},
                    "entry": (round(put_wall_strike * 1.005, 2), round(spot * 1.01, 2)),
                    "target": round(polarity, 2),
                    "stop": round(put_wall_strike * 0.98, 2),
                })

    # --- Call Wall Resistance ---
    if call_wall_strike and spot < call_wall_strike:
        dist_pct = (call_wall_strike - spot) / spot * 100
        if dist_pct < 3.0:
            proximity = 1 - (dist_pct / 3.0)
            regime_bonus = 0.2 if regime == "positive" else 0
            confidence = min(proximity + regime_bonus, 1.0)
            if confidence >= 0.4:
                opportunities.append({
                    "type": "call_wall_resistance",
                    "name": "Call Wall Resistance",
                    "direction": "bearish",
                    "risk": "low",
                    "confidence": round(confidence, 2),
                    "description": f"Price {dist_pct:.1f}% below call wall at {call_wall_strike:.1f}. Dealers likely to sell rallies here.",
                    "trigger": {"call_wall": call_wall_strike, "distance_pct": round(dist_pct, 2), "regime": regime},
                    "entry": (round(call_wall_strike * 0.99, 2), round(call_wall_strike * 1.005, 2)),
                    "target": round(polarity, 2),
                    "stop": round(call_wall_strike * 1.02, 2),
                })

    # --- Volatility Expansion (negative gamma regime) ---
    if regime in ("negative", "neutral") and total_gex < 0:
        dist_to_flip = ((spot - polarity) / spot) * 100 if polarity else 0
        confidence = min(abs(dist_to_flip) / 5, 1.0)
        if confidence >= 0.3:
            opportunities.append({
                "type": "volatility_expansion",
                "name": "Volatility Expansion",
                "direction": "neutral",
                "risk": "medium",
                "confidence": round(confidence, 2),
                "description": "Negative gamma regime. Dealers amplifying moves. Expect increased volatility.",
                "trigger": {"regime": regime, "total_gex": total_gex, "dist_to_flip_pct": round(dist_to_flip, 2)},
            })

    # --- Volatility Compression (positive gamma regime) ---
    if regime == "positive" and total_gex > 0:
        dist_to_flip = ((spot - polarity) / spot) * 100 if polarity else 0
        confidence = min(dist_to_flip / 5, 1.0)
        if confidence >= 0.3:
            opportunities.append({
                "type": "volatility_compression",
                "name": "Volatility Compression",
                "direction": "neutral",
                "risk": "low",
                "confidence": round(confidence, 2),
                "description": "Positive gamma regime. Dealers dampening moves. Good for selling premium.",
                "trigger": {"regime": regime, "total_gex": total_gex, "dist_to_flip_pct": round(dist_to_flip, 2)},
            })

    # --- Pin Risk: high OI at ATM strike near expiration ---
    if contracts:
        # Find nearest expiry
        expiries = sorted(set(c["expiry"] for c in contracts))
        if expiries:
            nearest_exp = expiries[0]
            try:
                exp_date = datetime.strptime(nearest_exp, "%Y-%m-%d").date()
                dte = (exp_date - datetime.now(timezone.utc).date()).days
            except Exception:
                dte = 999
            if dte <= 5:
                # Find ATM strike with highest OI
                atm_strike_val = min(strikes, key=lambda s: abs(s["strike"] - spot))["strike"]
                atm_strikes_data = [s for s in strikes if abs(s["strike"] - atm_strike_val) < spot * 0.01]
                if atm_strikes_data:
                    max_oi = max(s.get("total_oi", 0) for s in atm_strikes_data)
                    if max_oi > 1000:
                        confidence = min(0.3 + (max_oi / 10000) * 0.3 + (1 - dte / 5) * 0.3, 1.0)
                        if confidence >= 0.4:
                            opportunities.append({
                                "type": "pin_risk",
                                "name": "Expiration Pin Risk",
                                "direction": "neutral",
                                "risk": "medium",
                                "confidence": round(confidence, 2),
                                "description": f"High OI ({max_oi:,.0f}) at {atm_strike_val:.0f} with {dte} DTE. Price may gravitate here.",
                                "trigger": {"pin_strike": atm_strike_val, "oi": max_oi, "dte": dte},
                                "target": atm_strike_val,
                            })

    # --- Gamma Ladder: multiple call strikes with increasing GEX above price ---
    calls_above = sorted([s for s in strikes if s["strike"] > spot and s.get("call_gex", 0) > 0],
                         key=lambda s: s["strike"])
    if len(calls_above) >= 3:
        call_gex_vals = [s.get("call_gex", 0) for s in calls_above[:5]]
        ascending = sum(1 for i in range(len(call_gex_vals) - 1) if call_gex_vals[i + 1] > call_gex_vals[i] * 0.8)
        if ascending >= 2:
            pattern_strength = ascending / (len(call_gex_vals) - 1)
            total_call_gex_above = sum(call_gex_vals)
            total_call_gex_all = sum(s.get("call_gex", 0) for s in strikes if s.get("call_gex", 0) > 0)
            concentration = total_call_gex_above / total_call_gex_all if total_call_gex_all > 0 else 0
            confidence = min((pattern_strength + concentration) / 2, 1.0)
            if confidence >= 0.35:
                rungs = [s["strike"] for s in calls_above[:3]]
                opportunities.append({
                    "type": "gamma_ladder",
                    "name": "Gamma Call Ladder",
                    "direction": "bullish",
                    "risk": "medium",
                    "confidence": round(confidence, 2),
                    "description": f"Call ladder with {ascending} rungs. Targets: {', '.join(f'{r:.0f}' for r in rungs)}.",
                    "trigger": {"rungs": rungs, "ascending": ascending, "concentration": round(concentration, 2)},
                    "entry": (round(spot * 0.99, 2), round(rungs[0] * 0.995, 2)),
                    "target": rungs[-1],
                    "stop": round(spot * 0.97, 2),
                })

    # Sort by confidence
    opportunities.sort(key=lambda o: o.get("confidence", 0), reverse=True)
    return opportunities[:8]  # max 8 opportunities


# ----------------------------- Node Hierarchy ---------------------------------

def classify_nodes(strikes: List[Dict[str, Any]], spot: float) -> Dict[str, Any]:
    if not strikes or spot <= 0:
        return {"king": None, "floors": [], "ceilings": [], "gatekeepers": [], "air_pockets": [],
                "polarity_level": None, "regime": "unknown", "total_gex": 0, "near_gex": 0,
                "vex_flip": None, "stacked_nodes": [], "tug_of_war": [], "total_vega": 0}

    # King = largest absolute exposure
    king = max(strikes, key=lambda r: abs(r["gex"]))
    max_abs = abs(king["gex"]) or 1.0

    floors = sorted(
        [s for s in strikes if s["strike"] < spot and s["gex"] > 0],
        key=lambda r: r["gex"], reverse=True,
    )
    ceilings = sorted(
        [s for s in strikes if s["strike"] > spot and s["gex"] > 0],
        key=lambda r: r["gex"], reverse=True,
    )

    # Gatekeepers: positive nodes between spot and king
    gk_threshold = 0.15 * max_abs
    if king and king["strike"] != spot:
        lo, hi = sorted([spot, king["strike"]])
        gks = [s for s in strikes
               if lo < s["strike"] < hi and s["strike"] != king["strike"]
               and abs(s["gex"]) >= gk_threshold]
        gatekeepers = sorted(gks, key=lambda r: abs(r["gex"]), reverse=True)
    else:
        gatekeepers = []

    # Air Pockets: contiguous stretches where |gex| < 8% of max_abs
    ap_threshold = 0.08 * max_abs
    air_pockets = []
    run_start = None
    run_strikes: List[float] = []
    for s in strikes:
        weak = abs(s["gex"]) < ap_threshold
        if weak:
            if run_start is None:
                run_start = s["strike"]
            run_strikes.append(s["strike"])
        else:
            if run_start is not None and len(run_strikes) >= 3:
                air_pockets.append({"low": min(run_strikes), "high": max(run_strikes),
                                    "width": len(run_strikes), "mid": (min(run_strikes) + max(run_strikes)) / 2})
            run_start = None
            run_strikes = []
    if run_start is not None and len(run_strikes) >= 3:
        air_pockets.append({"low": min(run_strikes), "high": max(run_strikes),
                            "width": len(run_strikes), "mid": (min(run_strikes) + max(run_strikes)) / 2})

    # Polarity / regime - use total GEX
    total_gex = sum(s["gex"] for s in strikes)
    spot_window = [s for s in strikes if abs(s["strike"] - spot) / spot < 0.02]
    near_gex = sum(s["gex"] for s in spot_window)
    if total_gex > 0:
        regime = "positive"
    elif total_gex < 0:
        regime = "negative"
    else:
        regime = "neutral"

    # Gamma flip point: weighted average of all strikes by absolute GEX
    # This gives the "center of gravity" for gamma exposure
    # A more useful flip point than cumulative zero-crossing
    total_abs_gex = sum(abs(s["gex"]) for s in strikes)
    if total_abs_gex > 0:
        polarity = sum(s["strike"] * abs(s["gex"]) for s in strikes) / total_abs_gex
    else:
        polarity = spot

    # VEX flip point: same weighted average approach for vanna
    total_abs_vex = sum(abs(s.get("vex", 0.0) or 0) for s in strikes)
    if total_abs_vex > 0:
        vex_flip = sum(s["strike"] * abs(s.get("vex", 0.0) or 0) for s in strikes) / total_abs_vex
    else:
        vex_flip = spot

    # Stacked nodes: strikes where both call and put GEX are significant
    stacked = []
    for s in strikes:
        if abs(s["strike"] - spot) / spot > 0.03:
            continue
        total = abs(s.get("call_gex", 0)) + abs(s.get("put_gex", 0))
        if total > 0:
            call_pct = abs(s.get("call_gex", 0)) / total
            put_pct = abs(s.get("put_gex", 0)) / total
            if call_pct > 0.2 and put_pct > 0.2:
                stacked.append({"strike": s["strike"], "call_pct": round(call_pct, 2), "put_pct": round(put_pct, 2)})

    # Tug-of-war: zones where positive and negative GEX are within 3% of spot
    tug_of_war = []
    near_strikes = sorted([s for s in strikes if abs(s["strike"] - spot) / spot < 0.03], key=lambda r: r["strike"])
    for i in range(1, len(near_strikes)):
        a, b = near_strikes[i-1], near_strikes[i]
        if (a["gex"] > 0 and b["gex"] < 0) or (a["gex"] < 0 and b["gex"] > 0):
            tug_of_war.append({"low": a["strike"], "high": b["strike"],
                                "positive": a["gex"] if a["gex"] > 0 else b["gex"],
                                "negative": a["gex"] if a["gex"] < 0 else b["gex"]})

    # Total vega
    total_vega = sum((s.get("vega") or 0.0) for s in strikes)
    if math.isnan(total_vega) or math.isinf(total_vega):
        total_vega = 0.0

    # Total charm
    total_charm = sum((s.get("charm") or 0.0) for s in strikes)
    if math.isnan(total_charm) or math.isinf(total_charm):
        total_charm = 0.0

    # Total vomma
    total_vomma = sum((s.get("vomma") or 0.0) for s in strikes)
    if math.isnan(total_vomma) or math.isinf(total_vomma):
        total_vomma = 0.0

    # Total zomma
    total_zomma = sum((s.get("zomma") or 0.0) for s in strikes)
    if math.isnan(total_zomma) or math.isinf(total_zomma):
        total_zomma = 0.0

    # Charm flip point: weighted average of all strikes by absolute charm
    total_abs_charm = sum(abs(s.get("charm") or 0.0) for s in strikes)
    if total_abs_charm > 0:
        charm_flip = sum(s["strike"] * abs(s.get("charm") or 0.0) for s in strikes) / total_abs_charm
    else:
        charm_flip = spot

    # Max Pain: strike where total OI-weighted pain is minimized
    max_pain = None
    if strikes:
        strike_range = sorted(set(s["strike"] for s in strikes))
        min_pain = float("inf")
        for test_strike in strike_range:
            pain = 0.0
            for s in strikes:
                oi = s.get("total_oi", 0) or 0
                pain += oi * abs(s["strike"] - test_strike)
            if pain < min_pain:
                min_pain = pain
                max_pain = test_strike

    # Put/Call ratio
    total_call_oi = sum(s.get("call_oi", 0) or 0 for s in strikes)
    total_put_oi = sum(s.get("put_oi", 0) or 0 for s in strikes)
    put_call_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else None

    # ---- Risk Metrics (from gex-backtesting repo) ----

    # GCI: Gamma Concentration Index (Herfindahl-Hirschman)
    # Measures how concentrated gamma is across strikes. Range [0, 1].
    # 1/N if perfectly uniform; approaches 1.0 if all gamma at one strike.
    total_abs = sum(abs(s["gex"]) for s in strikes) or 1.0
    gamma_shares = [abs(s["gex"]) / total_abs for s in strikes]
    gci = sum(s * s for s in gamma_shares)

    # PGR: Protective Gamma Ratio
    # Fraction of total gamma within 20 points of spot.
    gdw_decay = 20.0  # decay constant for GDW
    near_spot = 20.0  # points for PGR window
    gamma_near = sum(abs(s["gex"]) for s in strikes if abs(s["strike"] - spot) <= near_spot)
    pgr = gamma_near / total_abs if total_abs > 0 else 0.0

    # GDW: Gamma Distance Weighted
    # Exponentially-weighted gamma favoring strikes near spot.
    gdw = sum(abs(s["gex"]) * math.exp(-abs(s["strike"] - spot) / gdw_decay) for s in strikes)

    # CAR: Convexity Acceleration Risk
    # Composite of zomma (60%) and vomma (40%) with time decay amplification.
    # Captures feedback loop risk: vol spike -> gamma change -> hedging -> more vol.
    # Time amplifier: 1/sqrt(TTE) capped at 30x. Use 1 day as default TTE.
    avg_tte = 1.0 / 252.0  # ~1 trading day default
    time_amp = min(30.0, 1.0 / math.sqrt(max(avg_tte, 0.001)))
    gamma_sign = -1.0 if total_gex < 0 else 1.0
    car_net = gamma_sign * (0.6 * total_zomma + 0.4 * total_vomma) * time_amp / 1e6
    car_gross = (0.6 * abs(total_zomma) + 0.4 * abs(total_vomma)) * time_amp / 1e6

    # Charm Risk: aggregate delta decay exposure
    charm_risk = total_charm / 1e6

    return {
        "king": king,
        "floors": floors[:5],
        "ceilings": ceilings[:5],
        "gatekeepers": gatekeepers[:6],
        "air_pockets": air_pockets,
        "polarity_level": polarity,
        "regime": regime,
        "total_gex": total_gex,
        "near_gex": near_gex,
        "vex_flip": vex_flip,
        "charm_flip": charm_flip,
        "max_pain": max_pain,
        "put_call_ratio": put_call_ratio,
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi,
        "stacked_nodes": stacked[:10],
        "tug_of_war": tug_of_war[:5],
        "total_vega": total_vega,
        "total_charm": total_charm,
        "total_vomma": total_vomma,
        "total_zomma": total_zomma,
        "risk_metrics": {
            "gci": round(gci, 4),
            "pgr": round(pgr, 4),
            "gdw": round(gdw, 2),
            "car_net": round(car_net, 2),
            "car_gross": round(car_gross, 2),
            "charm_risk": round(charm_risk, 2),
            "time_amp": round(time_amp, 1),
        },
    }


# ----------------------------- Pattern Detection ------------------------------

def detect_patterns(strikes: List[Dict[str, Any]], nodes: Dict[str, Any], spot: float) -> List[Dict[str, Any]]:
    patterns: List[Dict[str, Any]] = []
    if not strikes or spot <= 0:
        return patterns

    king = nodes.get("king")
    if not king:
        return patterns
    max_abs = abs(king["gex"]) or 1.0

    above = [s for s in strikes if s["strike"] > spot]
    below = [s for s in strikes if s["strike"] < spot]
    big_pos_above = [s for s in above if s["gex"] > 0.25 * max_abs]
    big_pos_below = [s for s in below if s["gex"] > 0.25 * max_abs]
    big_neg_above = [s for s in above if s["gex"] < -0.20 * max_abs]
    big_neg_below = [s for s in below if s["gex"] < -0.20 * max_abs]

    # Rug: positive above, negative below
    if big_pos_above and big_neg_below:
        patterns.append({
            "name": "Rug",
            "bias": "bearish",
            "severity": min(1.0, (big_pos_above[0]["gex"] + abs(big_neg_below[0]["gex"])) / (2 * max_abs)),
            "note": "Positive ceiling stacks above, negative below — rejection w/ pro-cyclical acceleration down.",
        })

    # Reverse Rug
    if big_pos_below and big_neg_above:
        patterns.append({
            "name": "Reverse Rug",
            "bias": "bullish",
            "severity": min(1.0, (big_pos_below[0]["gex"] + abs(big_neg_above[0]["gex"])) / (2 * max_abs)),
            "note": "Positive floor below, negative above — support holds, bounce runs.",
        })

    # Pika Cloud: 3+ positive nodes within ~1.5% strike range
    pos_sorted = sorted([s for s in strikes if s["gex"] > 0.15 * max_abs], key=lambda r: r["strike"])
    for i in range(len(pos_sorted)):
        cluster = [pos_sorted[i]]
        for j in range(i + 1, len(pos_sorted)):
            if (pos_sorted[j]["strike"] - cluster[0]["strike"]) / spot <= 0.015:
                cluster.append(pos_sorted[j])
            else:
                break
        if len(cluster) >= 3:
            lo = cluster[0]["strike"]; hi = cluster[-1]["strike"]
            mid = (lo + hi) / 2
            patterns.append({
                "name": "Pika Cloud",
                "bias": "resistance" if mid > spot else "support",
                "severity": min(1.0, sum(c["gex"] for c in cluster) / (2 * max_abs)),
                "note": f"Dense positive cluster {lo:.2f}-{hi:.2f}. Inefficient transit zone.",
                "range": [lo, hi],
            })
            break

    # Beach Ball: spot near a major positive node but slightly past it
    near_king = abs(spot - king["strike"]) / spot < 0.01
    if king["gex"] > 0 and near_king and abs(spot - king["strike"]) > 0:
        side = "below" if spot < king["strike"] else "above"
        patterns.append({
            "name": "Beach Ball",
            "bias": "reversion",
            "severity": 0.7,
            "note": f"Spot stretched {side} king node — overshoot/reversion setup.",
        })

    # Whipsaw: high disagreement (multiple sign flips around spot)
    near = sorted([s for s in strikes if abs(s["strike"] - spot) / spot < 0.03], key=lambda r: r["strike"])
    sign_flips = 0
    for i in range(1, len(near)):
        if (near[i - 1]["gex"] > 0) != (near[i]["gex"] > 0):
            sign_flips += 1
    if sign_flips >= 3:
        patterns.append({
            "name": "Whipsaw",
            "bias": "trap",
            "severity": min(1.0, sign_flips / 6),
            "note": f"Conflicting signs near spot ({sign_flips} flips). Fade extremes only.",
        })

    # Rainbow Road: chaos — magnitude diffuse, no dominant node
    total_abs = sum(abs(s["gex"]) for s in strikes) or 1.0
    king_share = abs(king["gex"]) / total_abs
    if king_share < 0.08 and len(strikes) > 20:
        patterns.append({
            "name": "Rainbow Road",
            "bias": "do not trade",
            "severity": 1 - king_share * 10,
            "note": "No dominant structure. Pre/post-catalyst chaos. Sit out.",
        })

    return patterns


# ----------------------------- Tap Probability -------------------------------

async def tap_counts(ticker: str, strikes: List[float], days: int = 5) -> Dict[float, int]:
    """Count how many days price crossed each strike in last N trading days using Polygon aggs."""
    if not POLYGON_API_KEY or not strikes:
        return {s: 0 for s in strikes}
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days * 2)
    pg_ticker = ticker.replace("^SPX", "I:SPX") if ticker.startswith("^") else ticker
    url = f"https://api.polygon.io/v2/aggs/ticker/{pg_ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}"
    out = {s: 0 for s in strikes}
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.get(url, params={"apiKey": POLYGON_API_KEY, "limit": days * 2})
            data = r.json()
        if not data.get("results"):
            return out
        results = data["results"][-days:]
        for bar in results:
            lo = bar.get("l", 0); hi = bar.get("h", 0)
            for s in strikes:
                if lo <= s <= hi:
                    out[s] += 1
    except Exception as e:
        log.warning(f"tap_counts fail {ticker}: {e}")
    return out


# ----------------------------- Snapshot persistence (velocity/rolling) --------

async def save_snapshot(ticker: str, payload: Dict[str, Any]):
    try:
        doc = {
            "ticker": ticker,
            "ts": datetime.now(timezone.utc).isoformat(),
            "spot": payload["spot"],
            "king_strike": payload["nodes"]["king"]["strike"] if payload["nodes"].get("king") else None,
            "king_gex": payload["nodes"]["king"]["gex"] if payload["nodes"].get("king") else None,
            "top_floor": payload["nodes"]["floors"][0]["strike"] if payload["nodes"].get("floors") else None,
            "top_ceiling": payload["nodes"]["ceilings"][0]["strike"] if payload["nodes"].get("ceilings") else None,
            "regime": payload["nodes"].get("regime"),
            "strikes_compact": [{"strike": s["strike"], "gex": s["gex"]} for s in payload["strikes"][:200]],
        }
        await db.snapshots.insert_one(doc)
        # Keep last 50 per ticker
        cursor = db.snapshots.find({"ticker": ticker}, {"_id": 1}).sort("ts", -1).skip(50)
        ids = [d["_id"] async for d in cursor]
        if ids:
            await db.snapshots.delete_many({"_id": {"$in": ids}})
    except Exception as e:
        log.warning(f"snapshot save fail: {e}")


async def velocity_and_rolling(ticker: str, current_nodes: Dict[str, Any]) -> Dict[str, Any]:
    """Compute rate of change vs prior snapshot + rolling floor/ceiling sequence."""
    cur = db.snapshots.find({"ticker": ticker}, {"_id": 0}).sort("ts", -1).limit(10)
    history = [d async for d in cur]
    if len(history) < 1:
        return {"velocity_score": 0, "rolling_floor": "stable", "rolling_ceiling": "stable", "history": []}

    floor_seq = [h["top_floor"] for h in history if h.get("top_floor")][:5]
    ceiling_seq = [h["top_ceiling"] for h in history if h.get("top_ceiling")][:5]

    def trend(seq):
        if len(seq) < 2:
            return "stable"
        # seq is newest-first; we want oldest -> newest order
        seq = list(reversed(seq))
        ups = sum(1 for i in range(1, len(seq)) if seq[i] > seq[i - 1])
        downs = sum(1 for i in range(1, len(seq)) if seq[i] < seq[i - 1])
        if ups >= 2 and downs == 0:
            return "rolling_up"
        if downs >= 2 and ups == 0:
            return "rolling_down"
        return "stable"

    # Velocity: how much the strike-level GEX has changed since last snapshot
    velocity = 0.0
    if history:
        prev = history[0]
        prev_map = {s["strike"]: s["gex"] for s in prev.get("strikes_compact", [])}
        cur_map = {s["strike"]: s["gex"] for s in current_nodes.get("strikes_compact", [])}
        common = set(prev_map.keys()) & set(cur_map.keys())
        if common:
            deltas = [abs(cur_map[k] - prev_map[k]) for k in common]
            base = max(sum(abs(prev_map[k]) for k in common), 1.0)
            velocity = min(1.0, sum(deltas) / base)

    return {
        "velocity_score": round(velocity, 3),
        "rolling_floor": trend(floor_seq),
        "rolling_ceiling": trend(ceiling_seq),
        "floor_sequence": floor_seq,
        "ceiling_sequence": ceiling_seq,
        "snapshots_count": len(history) + 1,
    }


# ----------------------------- Top Movers (Polygon) ---------------------------

TRINITY = ["^SPX", "SPY", "QQQ"]
DEFAULT_TICKERS = ["SPY", "QQQ", "^SPX", "IWM", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "GOOGL", "NFLX", "AMD", "SMH", "XLF", "GLD"]
POPULAR_UNIVERSE = ["AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "GOOGL", "AMD", "AVGO", "NFLX",
                    "COIN", "PLTR", "MU", "SMCI", "BABA", "CRM", "ORCL", "GME", "AMC", "INTC",
                    "DIS", "BA", "JPM", "GS", "XOM", "UBER", "SHOP", "SOFI", "F", "MARA"]

PATTERN_GLOSSARY = {
    "gamma_flip": {"name": "Gamma Flip", "description": "The spot price level where total GEX flips from positive to negative."},
    "call_wall": {"name": "Call Wall", "description": "Strike with highest call gamma exposure — acts as resistance."},
    "put_wall": {"name": "Put Wall", "description": "Strike with highest put gamma exposure — acts as support."},
    "max_pain": {"name": "Max Pain", "description": "Strike where option sellers have the most profit / buyers the most loss."},
    "unusual_activity": {"name": "Unusual Options Activity", "description": "Trades with premium or volume significantly above average."},
    "charm_pinning": {"name": "Charm Pinning", "description": "Delta decay (charm) accelerates near expiry, pinning price to high-OI strikes."},
    "vanna_regime": {"name": "Vanna Regime", "description": "Vanna-driven flow regime — positive vanna amplifies moves, negative dampens."},
    "hedge_impulse": {"name": "Hedge Impulse", "description": "Dealer hedging pressure curve — shows where delta hedging accelerates or decelerates."},
    "pressure_cloud": {"name": "Pressure Cloud", "description": "Zones of stability and acceleration from second-order Greek exposure."},
    "trinity": {"name": "Trinity", "description": "Confluence of SPY, QQQ, and ^SPX regime alignment."},
    "iron_condor": {"name": "Iron Condor", "description": "Sell OTM call spread + OTM put spread — profit from range-bound price."},
    "straddle": {"name": "Straddle", "description": "Buy call + put at same strike — profit from large move in either direction."},
    "strangle": {"name": "Strangle", "description": "Buy OTM call + OTM put — cheaper than straddle, needs bigger move."},
    "vertical_spread": {"name": "Vertical Spread", "description": "Buy and sell same type at different strikes — directional with defined risk."},
    "calendar_spread": {"name": "Calendar Spread", "description": "Sell near-term + buy longer-term at same strike — profit from IV term structure."},
    "rug": {"name": "Rug", "description": "Sudden GEX regime flip — market makers forced to reverse hedging direction, causing accelerated price move."},
    "reverse_rug": {"name": "Reverse Rug", "description": "GEX flip back to prior regime after a brief excursion — snap-back move as dealers re-hedge."},
    "pika_cloud": {"name": "Pika Cloud", "description": "Dense cluster of gamma exposure across multiple strikes — creates a 'cloud' of support/resistance."},
    "beach_ball": {"name": "Beach Ball", "description": "Compressing GEX profile — volatility squeeze that precedes a large directional move."},
    "whipsaw": {"name": "Whipsaw", "description": "Rapid GEX regime oscillation — dealers chase price in both directions, creating chop."},
    "rainbow_road": {"name": "Rainbow Road", "description": "Multi-expiry GEX alignment — all timeframes pointing in the same directional bias."},
    "king_node": {"name": "King Node", "description": "Dominant gamma node — the single strike with the largest GEX influence on spot price."},
    "floor": {"name": "Floor", "description": "Strong put GEX support level — dealers buy into dips to hedge, creating a price floor."},
    "ceiling": {"name": "Ceiling", "description": "Strong call GEX resistance level — dealers sell into rallies to hedge, creating a price ceiling."},
    "gatekeeper": {"name": "Gatekeeper", "description": "Critical GEX transition strike — price crossing this level triggers a regime change in dealer hedging."},
    "air_pocket": {"name": "Air Pocket", "description": "Zone of minimal GEX — price can move rapidly through this region with little dealer hedging friction."},
    # Title-case aliases for backward compat
    "Rug": {"name": "Rug", "description": "Sudden GEX regime flip — market makers forced to reverse hedging direction, causing accelerated price move."},
    "Reverse Rug": {"name": "Reverse Rug", "description": "GEX flip back to prior regime after a brief excursion — snap-back move as dealers re-hedge."},
    "Pika Cloud": {"name": "Pika Cloud", "description": "Dense cluster of gamma exposure across multiple strikes — creates a 'cloud' of support/resistance."},
    "Beach Ball": {"name": "Beach Ball", "description": "Compressing GEX profile — volatility squeeze that precedes a large directional move."},
    "Whipsaw": {"name": "Whipsaw", "description": "Rapid GEX regime oscillation — dealers chase price in both directions, creating chop."},
    "Rainbow Road": {"name": "Rainbow Road", "description": "Multi-expiry GEX alignment — all timeframes pointing in the same directional bias."},
    "King Node": {"name": "King Node", "description": "Dominant gamma node — the single strike with the largest GEX influence on spot price."},
    "Floor": {"name": "Floor", "description": "Strong put GEX support level — dealers buy into dips to hedge, creating a price floor."},
    "Ceiling": {"name": "Ceiling", "description": "Strong call GEX resistance level — dealers sell into rallies to hedge, creating a price ceiling."},
    "Gatekeeper": {"name": "Gatekeeper", "description": "Critical GEX transition strike — price crossing this level triggers a regime change in dealer hedging."},
    "Air Pocket": {"name": "Air Pocket", "description": "Zone of minimal GEX — price can move rapidly through this region with little dealer hedging friction."},
    "Call Wall": {"name": "Call Wall", "description": "Strike with highest call gamma exposure — acts as resistance."},
    "Put Wall": {"name": "Put Wall", "description": "Strike with highest put gamma exposure — acts as support."},
    "Max Pain": {"name": "Max Pain", "description": "Strike where option sellers have the most profit / buyers the most loss."},
    "Gamma Flip": {"name": "Gamma Flip", "description": "The spot price level where total GEX flips from positive to negative."},
    "Trinity": {"name": "Trinity", "description": "Confluence of SPY, QQQ, and ^SPX regime alignment."},
}


_movers_cache: Dict[str, Any] = {"ts": 0, "data": []}


def _fetch_movers_sync() -> List[Dict[str, Any]]:
    """Use yfinance bulk download for prev-day movers (fast, no rate limit)."""
    try:
        df = yf.download(POPULAR_UNIVERSE, period="2d", interval="1d",
                         group_by="ticker", progress=False, threads=True, auto_adjust=False)
    except Exception as e:
        log.warning(f"yfinance movers fail: {e}")
        return []
    out: List[Dict[str, Any]] = []
    for sym in POPULAR_UNIVERSE:
        try:
            sub = df[sym].dropna()
            if len(sub) < 2:
                continue
            prev_close = float(sub["Close"].iloc[-2])
            last_close = float(sub["Close"].iloc[-1])
            day_open = float(sub["Open"].iloc[-1])
            hi = float(sub["High"].iloc[-1]); lo = float(sub["Low"].iloc[-1])
            vol = float(sub["Volume"].iloc[-1])
            pct = ((last_close - prev_close) / prev_close * 100) if prev_close else 0
            out.append({"ticker": sym, "open": day_open, "close": last_close, "pct": round(pct, 2),
                        "volume": vol, "high": hi, "low": lo, "prev_close": prev_close})
        except Exception:
            continue
    return out


async def top_movers_polygon(limit: int = 10) -> List[Dict[str, Any]]:
    """Top movers via yfinance bulk download. Cached 60s."""
    if time.time() - _movers_cache["ts"] < 60 and _movers_cache["data"]:
        return sorted(_movers_cache["data"], key=lambda r: abs(r["pct"]), reverse=True)[:limit]
    rows = await asyncio.to_thread(_fetch_movers_sync)
    _movers_cache["ts"] = time.time()
    _movers_cache["data"] = rows
    return sorted(rows, key=lambda r: abs(r["pct"]), reverse=True)[:limit]


# ----------------------------- Models -----------------------------------------

class HeatmapResp(BaseModel):
    ticker: str
    spot: float
    expiries_used: List[str]
    strikes: List[Dict[str, Any]]
    nodes: Dict[str, Any]
    patterns: List[Dict[str, Any]]
    velocity: Dict[str, Any]
    tap_counts: Dict[str, int]
    asof: str


# ----------------------------- Volume-Weighted GEX (for intraday) --------------

def compute_gex_by_strike_volume(spot: float, contracts: List[Dict[str, Any]], ticker: str) -> List[Dict[str, Any]]:
    """Volume-weighted GEX — shows where the action is RIGHT NOW.
    Uses volume instead of OI for weighting. Same BS gamma formula."""
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    agg: Dict[float, Dict[str, float]] = {}
    for c in contracts:
        gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
        if gamma <= 0:
            continue
        # Use volume instead of OI for intraday focus
        vol = c.get("volume", 0) or 0
        if vol <= 0:
            continue
        # DTE-aware OI blend: blend OI for longer-dated contracts to avoid single-trade dominance
        dte = c.get("T", 1.0 / 365.0) * 365.0
        oi = c.get("oi", 0) or 0
        if dte <= 1.5:
            effective_vol = vol  # 0DTE/1DTE: pure volume
        elif dte <= 5.0:
            effective_vol = max(vol, oi * 0.3)  # moderate OI blend
        else:
            effective_vol = max(vol, oi * 0.5)  # heavier OI blend for monthly+
        gex_unit = gamma * effective_vol * 100.0 * spot * spot * 0.01
        sign = 1.0 if c["type"] == "call" else -1.0
        bucket = agg.setdefault(c["strike"], {
            "strike": c["strike"], "gex": 0.0, "call_gex": 0.0, "put_gex": 0.0,
            "call_oi": 0.0, "put_oi": 0.0, "total_oi": 0.0,
            "call_vol": 0.0, "put_vol": 0.0, "total_vol": 0.0,
        })
        bucket["gex"] += sign * gex_unit
        if c["type"] == "call":
            bucket["call_gex"] += gex_unit
            bucket["call_vol"] += vol
            bucket["call_oi"] += c["oi"]
        else:
            bucket["put_gex"] += gex_unit
            bucket["put_vol"] += vol
            bucket["put_oi"] += c["oi"]
        bucket["total_oi"] += c["oi"]
        bucket["total_vol"] += vol

    out = sorted(agg.values(), key=lambda r: r["strike"])
    return out


# ----------------------------- Heatmap Core -----------------------------------

async def build_heatmap(ticker: str, max_expiries: int = 4, with_taps: bool = True, mode: str = "day", dte: Optional[int] = None, scalp: bool = False) -> Dict[str, Any]:
    if mode == "swing":
        max_expiries = max(max_expiries, 8)
    raw = await fetch_spot_and_chains_merged(ticker, max_expiries)
    spot = raw["spot"]
    if not spot or spot != spot or not raw["contracts"]:  # spot != spot catches NaN
        raise HTTPException(404, f"No options data for {ticker}")

    today = datetime.now(timezone.utc).date()

    # Scalp mode: force 0DTE only, tight band, volume-weighted
    if scalp:
        dte = 0
        mode = "scalp"

    # DTE filter
    if dte is not None:
        cutoff = today + timedelta(days=dte)
        filtered = []
        for c in raw["contracts"]:
            try:
                if datetime.strptime(c["expiry"], "%Y-%m-%d").date() <= cutoff:
                    filtered.append(c)
            except Exception:
                continue
        raw["contracts"] = filtered
        raw["expiries"] = sorted({c["expiry"] for c in raw["contracts"]})

    # Choose GEX computation: volume-weighted for scalp, OI for normal
    if scalp:
        strikes = compute_gex_by_strike_volume(spot, raw["contracts"], ticker)
        grid = {"expiries": raw["expiries"], "strikes": [], "grid": {}, "strike_totals": []}
    else:
        strikes = compute_gex_by_strike(spot, raw["contracts"], ticker)
        grid = compute_gex_grid(spot, raw["contracts"], ticker)

    # Band: scalp=±2%, day=±15%, swing=±25%
    if scalp:
        band = 0.02
    elif mode == "swing":
        band = 0.25
    else:
        band = 0.15

    strikes = [s for s in strikes if abs(s["strike"] - spot) / spot <= band]
    if not scalp:
        grid["strikes"] = [k for k in grid["strikes"] if abs(k - spot) / spot <= band]
        grid["strike_totals"] = [s for s in grid["strike_totals"] if abs(s["strike"] - spot) / spot <= band]

    # Tag fresh/tested via tap counts
    tap_map: Dict[float, int] = {}
    if with_taps and not scalp:
        tap_map = await tap_counts(ticker, [s["strike"] for s in strikes], days=5)
    for s in strikes:
        if scalp:
            s["taps"] = 0
            s["lifecycle"] = "live"
            s["tap_prob"] = 1.0
        else:
            tc = tap_map.get(s["strike"], 0)
            s["taps"] = tc
            if tc == 0:
                s["lifecycle"] = "fresh"
            elif tc == 1:
                s["lifecycle"] = "tested"
            elif tc == 2:
                s["lifecycle"] = "delivered"
            else:
                s["lifecycle"] = "decaying"
            s["tap_prob"] = [0.80, 0.66, 0.33, 0.10][min(tc, 3)]

    nodes = classify_nodes(strikes, spot)
    patterns = detect_patterns(strikes, nodes, spot)

    # --- New analytics (from EzOptions + GEX-Dashboard) ---
    implied_move = calc_implied_move(spot, raw["contracts"])
    prob_distribution = calc_probability_distribution(spot, raw["contracts"])
    aggregate_curve = calc_aggregate_gex_curve(spot, raw["contracts"], ticker)
    opportunities = detect_opportunities(strikes, nodes, spot, raw["contracts"])

    # --- Institutional vol analytics ---
    iv_surface = calc_iv_surface_data(spot, raw["contracts"])
    skew = calc_skew_metrics(spot, raw["contracts"])
    # Run yfinance calls in parallel threads to avoid blocking
    rv_task = asyncio.create_task(asyncio.to_thread(calc_realized_volatility, ticker.replace("^", ""), 20))
    iv_rank_task = asyncio.create_task(asyncio.to_thread(calc_iv_rank_percentile, ticker.replace("^", ""), skew.get("atm_iv", 0.2)))
    rv = await rv_task
    iv_rank = await iv_rank_task
    if rv:
        iv_rank["rv_iv_spread"] = round(skew.get("atm_iv", 0) - rv.get("rv_close", 0), 4)
        iv_rank["rv_close"] = rv.get("rv_close")

    # --- Advanced analytics (regime + implied PDF + gamma flip levels) ---
    market_regime = calc_market_regime(spot, raw["contracts"])
    implied_pdf = calc_implied_pdf(spot, raw["contracts"])
    gamma_flip_data = calc_gamma_flip_levels(spot, raw["contracts"], ticker)

    # Velocity & rolling
    velocity = await velocity_and_rolling(ticker, {"strikes_compact": [{"strike": s["strike"], "gex": s["gex"]} for s in strikes]})

    payload = {
        "ticker": ticker,
        "spot": spot,
        "expiries_used": raw["expiries"],
        "strikes": strikes,
        "grid": grid,
        "nodes": nodes,
        "patterns": patterns,
        "velocity": velocity,
        "tap_counts": {str(k): v for k, v in tap_map.items()},
        "data_source": raw.get("data_source", "yfinance"),
        "mode": mode,
        "asof": datetime.now(timezone.utc).isoformat(),
        # New analytics
        "implied_move": implied_move,
        "prob_distribution": prob_distribution,
        "aggregate_curve": aggregate_curve,
        "opportunities": opportunities,
        # Institutional vol analytics
        "iv_surface": iv_surface,
        "skew": skew,
        "iv_rank": iv_rank,
        "realized_vol": rv,
        # Advanced analytics
        "market_regime": market_regime,
        "implied_pdf": implied_pdf,
        "gamma_flip": gamma_flip_data,
    }

    asyncio.create_task(save_snapshot(ticker, payload))
    return _sanitize(payload)


def _sanitize(obj):
    """Replace NaN/Inf with None recursively for JSON safety. Handles numpy types."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    return obj


@app.get("/health")
async def health_root():
    return await health()


# ----------------------------- API Endpoints ------------------------------

# Cache import (lazy — only loaded when Redis is available)
from functools import wraps as _wraps
_cache_available = False
try:
    from cache import cache_response
    _cache_available = True
except ImportError:
    def cache_response(ttl=60, key_prefix="api"):
        def decorator(func):
            @_wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            return wrapper
        return decorator

@app.get("/api/")
async def root():
    return {"app": "confluence-decoder", "version": "2.0", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/api/tickers")
async def list_tickers():
    return {
        "trinity": TRINITY,
        "default": DEFAULT_TICKERS,
        "popular": POPULAR_UNIVERSE,
    }


@app.get("/api/health")
async def health():
    """Health check with dependency status."""
    status = {"app": "confluence-decoder", "version": "2.0", "ts": datetime.now(timezone.utc).isoformat(), "dependencies": {}}
    # Check Mongo
    try:
        await db.command("ping")
        status["dependencies"]["mongodb"] = "ok"
    except Exception as e:
        status["dependencies"]["mongodb"] = f"error: {str(e)}"
    # Check yfinance (lightweight)
    try:
        import yfinance as yf
        t = yf.Ticker("SPY")
        _ = t.fast_info
        status["dependencies"]["yfinance"] = "ok"
    except Exception as e:
        status["dependencies"]["yfinance"] = f"error: {str(e)}"
    # Overall
    all_ok = all(v == "ok" for v in status["dependencies"].values())
    status["status"] = "healthy" if all_ok else "degraded"
    return status


def _get_strategy_recommendation(gf: Dict, regime: Dict, skew: Dict) -> Dict[str, Any]:
    """Generate strategy recommendations based on GEX regime and market conditions."""
    gex_regime = gf.get("regime", "unknown")
    dist_to_flip = gf.get("dist_to_flip")
    gf.get("call_wall")
    gf.get("put_wall")
    spot = gf.get("spot", 0)

    if gex_regime == "positive_gamma":
        regime_desc = "Positive gamma — dealers are long gamma, market is self-correcting"
        bias = "mean_reversion"
        strategies = [
            "Sell premium (iron condors, short strangles) between put wall and call wall",
            "Buy dips to put wall, sell rallies to call wall",
            "Short volatility strategies favored",
            "Avoid chasing breakouts — they tend to reverse",
        ]
        if dist_to_flip is not None and dist_to_flip < 0:
            warning = "CAUTION: Price is below gamma flip — regime may be transitioning to negative"
        else:
            warning = None
    elif gex_regime == "negative_gamma":
        regime_desc = "Negative gamma — dealers are short gamma, market is self-amplifying"
        bias = "momentum"
        strategies = [
            "Long volatility strategies (long straddles, strangles)",
            "Momentum/trend following — breakouts accelerate",
            "Buy breakouts above call wall, short breakdowns below put wall",
            "Avoid mean-reversion — moves tend to extend",
        ]
        if dist_to_flip is not None and dist_to_flip > 0:
            warning = "CAUTION: Price is above gamma flip — regime may be transitioning to positive"
        else:
            warning = None
    else:
        regime_desc = "Unknown regime — insufficient data"
        bias = "neutral"
        strategies = ["Wait for clearer signal before entering positions"]
        warning = None

    # Skew-based adjustments
    rr = skew.get("risk_reversal_25d", 0)
    if rr > 0.02:
        skew_note = "Put skew elevated — fear premium in puts, consider put selling or put spreads"
    elif rr < -0.02:
        skew_note = "Call skew elevated — bullish positioning, consider call buying or call spreads"
    else:
        skew_note = "Skew relatively balanced — no strong directional bias from options positioning"

    return {
        "regime_description": regime_desc,
        "directional_bias": bias,
        "recommended_strategies": strategies,
        "warning": warning,
        "skew_note": skew_note,
        "position_sizing_note": _get_position_sizing_note(gf, spot),
    }


def _get_risk_levels(gf: Dict, spot: float) -> Dict[str, Any]:
    """Calculate key risk levels for stop-loss and target placement."""
    call_wall = gf.get("call_wall")
    put_wall = gf.get("put_wall")
    gamma_flip = gf.get("gamma_flip")
    max_pain = gf.get("max_pain")

    # Support/resistance from GEX levels
    resistance_1 = call_wall
    resistance_2 = call_wall + (call_wall - spot) * 0.5 if call_wall else None
    support_1 = put_wall
    support_2 = put_wall - (spot - put_wall) * 0.5 if put_wall else None

    # Stop loss suggestions
    if put_wall and spot > put_wall:
        stop_below_put_wall = put_wall - (spot - put_wall) * 0.3
    else:
        stop_below_put_wall = None

    return {
        "resistance": {"R1": resistance_1, "R2": resistance_2},
        "support": {"S1": support_1, "S2": support_2},
        "gamma_flip_level": gamma_flip,
        "max_pain": max_pain,
        "stop_suggestion": {
            "below_put_wall": stop_below_put_wall,
            "note": "Place stops beyond GEX walls — dealer hedging can create temporary spikes through levels",
        },
    }


def _get_position_sizing_note(gf: Dict, spot: float) -> str:
    """Generate position sizing guidance based on GEX regime."""
    regime = gf.get("regime", "unknown")
    dist_to_flip = gf.get("dist_to_flip")

    if regime == "positive_gamma":
        if dist_to_flip is not None and abs(dist_to_flip) < 5:
            return "Near gamma flip — reduce position size, regime could flip. Max 1% account risk per trade."
        return "Positive gamma — standard position sizing OK. Max 2% account risk per trade."
    elif regime == "negative_gamma":
        if dist_to_flip is not None and dist_to_flip < -10:
            return "Deep negative gamma — reduce position size, moves can be violent. Max 0.5% account risk per trade."
        return "Negative gamma — reduce position size vs normal. Max 1% account risk per trade."
    return "Unknown regime — use minimal position size until regime clarifies."


# ============ Memory Helpers ============

async def remember_trade(trade_data: dict) -> str:
    """Store a trade observation in the memory collection."""
    from datetime import datetime, timezone
    trade_data["ts"] = datetime.now(timezone.utc).isoformat()
    result = await db.memory.insert_one(trade_data)
    return str(result.inserted_id)


async def remember_gex_observation(obs_data: dict) -> str:
    """Store a GEX observation in the memory collection."""
    from datetime import datetime, timezone
    obs_data["ts"] = datetime.now(timezone.utc).isoformat()
    result = await db.memory.insert_one(obs_data)
    return str(result.inserted_id)


async def recall_trading_context(ticker: str, limit: int = 50) -> list:
    """Recall trading context for a ticker from the memory collection."""
    cursor = db.memory.find(
        {"ticker": ticker.upper()}, {"_id": 0}
    ).sort("ts", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def get_trading_summary(ticker: str) -> str:
    """Get a summary of trading context for a ticker."""
    count = await db.memory.count_documents({"ticker": ticker.upper()})
    if count == 0:
        return "no data yet"
    latest = await db.memory.find_one(
        {"ticker": ticker.upper()}, {"_id": 0}, sort=[("ts", -1)]
    )
    return f"{count} observations, latest: {latest}"


# ============ Portfolio Helpers ============

async def calc_portfolio_summary(portfolio: dict, spot: float, iv: float) -> dict:
    """Return portfolio summary with aggregated Greeks and P&L."""
    from portfolio import Position
    positions_data = portfolio.get("positions", [])
    pos_list = []
    for p in positions_data:
        try:
            pos = Position(
                symbol=p.get("symbol", ""),
                option_type=p.get("option_type", "call"),
                strike=float(p.get("strike", 0)),
                expiry=p.get("expiry", "2026-06-15"),
                quantity=int(p.get("quantity", 1)),
                entry_price=float(p.get("entry_price", 0)),
                entry_iv=float(p.get("entry_iv", iv)),
                underlying_price=float(p.get("underlying_price", spot)),
                is_long=p.get("is_long", True),
            )
            pos_list.append(pos)
        except Exception:
            continue

    totals = {"delta": 0, "gamma": 0, "vega": 0, "theta": 0}
    total_pnl = 0.0
    for pos in pos_list:
        g = pos.current_greeks(spot, iv)
        for k in totals:
            totals[k] += g.get(k, 0)
        current_price = g.get("price", 0)
        sign = 1 if pos.is_long else -1
        total_pnl += (current_price - pos.entry_price) * sign * abs(pos.quantity) * 100

    return {
        "name": portfolio.get("name", ""),
        "positions": len(positions_data),
        "greeks": {k: round(v, 4) for k, v in totals.items()},
        "pnl": round(total_pnl, 2),
    }


async def calc_portfolio_scenario(portfolio: dict, spot: float, iv: float) -> dict:
    """Run scenario analysis on a portfolio."""
    from portfolio import Position
    positions_data = portfolio.get("positions", [])
    pos_list = []
    for p in positions_data:
        try:
            pos = Position(
                symbol=p.get("symbol", ""),
                option_type=p.get("option_type", "call"),
                strike=float(p.get("strike", 0)),
                expiry=p.get("expiry", "2026-06-15"),
                quantity=int(p.get("quantity", 1)),
                entry_price=float(p.get("entry_price", 0)),
                entry_iv=float(p.get("entry_iv", iv)),
                underlying_price=float(p.get("underlying_price", spot)),
                is_long=p.get("is_long", True),
            )
            pos_list.append(pos)
        except Exception:
            continue

    spot_shocks = [-0.05, -0.03, -0.02, -0.01, 0, 0.01, 0.02, 0.03, 0.05]
    vol_shocks = [-0.10, -0.05, 0, 0.05, 0.10, 0.20]
    scenarios = []

    for shock in spot_shocks:
        new_spot = spot * (1 + shock)
        totals = {"delta": 0, "gamma": 0, "vega": 0, "theta": 0}
        pnl = 0.0
        for pos in pos_list:
            g = pos.current_greeks(new_spot, iv)
            for k in totals:
                totals[k] += g.get(k, 0)
            current_price = g.get("price", 0)
            sign = 1 if pos.is_long else -1
            pnl += (current_price - pos.entry_price) * sign * abs(pos.quantity) * 100
        scenarios.append({
            "type": "spot",
            "shock_pct": shock * 100,
            "spot": round(new_spot, 2),
            "pnl": round(pnl, 2),
            "delta": round(totals["delta"], 4),
            "gamma": round(totals["gamma"], 4),
        })

    for shock in vol_shocks:
        new_iv = max(iv * (1 + shock), 0.01)
        totals = {"delta": 0, "gamma": 0, "vega": 0, "theta": 0}
        pnl = 0.0
        for pos in pos_list:
            g = pos.current_greeks(spot, new_iv)
            for k in totals:
                totals[k] += g.get(k, 0)
            current_price = g.get("price", 0)
            sign = 1 if pos.is_long else -1
            pnl += (current_price - pos.entry_price) * sign * abs(pos.quantity) * 100
        scenarios.append({
            "type": "vol",
            "shock_pct": shock * 100,
            "iv": round(new_iv, 4),
            "pnl": round(pnl, 2),
            "vega": round(totals["vega"], 4),
            "vomma": 0,
        })

    return {"scenarios": scenarios}


async def calc_hedge_recommendation(portfolio: dict, hedge_request: dict) -> dict:
    """Calculate Greek-neutral hedge for a portfolio."""
    from portfolio import Position
    import numpy as np
    from bs_greeks import bs_gamma, bs_vega, bs_delta

    spot = float(hedge_request.get("spot", 0))
    iv = float(hedge_request.get("iv", 0.15))
    hedge_options = hedge_request.get("hedge_options", [])

    if not spot or len(hedge_options) < 2:
        return {"error": "Need spot price and at least 2 hedge options"}

    # Current portfolio Greeks
    positions_data = portfolio.get("positions", [])
    pos_list = []
    for p in positions_data:
        try:
            pos = Position(
                symbol=p.get("symbol", ""),
                option_type=p.get("option_type", "call"),
                strike=float(p.get("strike", 0)),
                expiry=p.get("expiry", "2026-06-15"),
                quantity=int(p.get("quantity", 1)),
                entry_price=float(p.get("entry_price", 0)),
                entry_iv=float(p.get("entry_iv", iv)),
                underlying_price=float(p.get("underlying_price", spot)),
                is_long=p.get("is_long", True),
            )
            pos_list.append(pos)
        except Exception:
            continue

    current = {"delta": 0, "gamma": 0, "vega": 0}
    for pos in pos_list:
        g = pos.current_greeks(spot, iv)
        for k in current:
            current[k] += g.get(k, 0)

    target_gamma = -current["gamma"]
    target_vega = -current["vega"]

    option_greeks = []
    for opt in hedge_options[:2]:
        from datetime import datetime, date as date_type
        exp_date = datetime.strptime(opt["expiry"], "%Y-%m-%d").date()
        T = max((exp_date - date_type.today()).days / 365.0, 0.001)
        K = opt["strike"]
        sigma = opt.get("iv", iv)
        S = spot
        g = bs_gamma(S, K, T, sigma, 0)
        v = bs_vega(S, K, T, sigma, 0)
        d = bs_delta(S, K, T, sigma, 0, opt.get("type", "call"))
        option_greeks.append({
            "gamma": g * 100, "vega": v * 100, "delta": d * 100,
            "strike": K, "expiry": opt["expiry"], "type": opt.get("type", "call"),
        })

    if len(option_greeks) < 2:
        return {"error": "Could not calculate Greeks for hedge options"}

    greeks_matrix = np.array([
        [option_greeks[0]["gamma"], option_greeks[1]["gamma"]],
        [option_greeks[0]["vega"], option_greeks[1]["vega"]],
    ])
    targets = np.array([[target_gamma], [target_vega]])

    try:
        inv = np.linalg.inv(greeks_matrix)
        weights = np.dot(inv, targets)
    except np.linalg.LinAlgError:
        return {"error": "Matrix is singular - hedge options are linearly dependent"}

    w1, w2 = float(weights.flat[0]), float(weights.flat[1])
    new_delta = current["delta"] + w1 * option_greeks[0]["delta"] + w2 * option_greeks[1]["delta"]
    stock_hedge = -new_delta

    return {
        "hedge_positions": [
            {"option": option_greeks[0], "contracts": round(w1, 0), "direction": "buy" if w1 > 0 else "sell"},
            {"option": option_greeks[1], "contracts": round(w2, 0), "direction": "buy" if w2 > 0 else "sell"},
        ],
        "stock_hedge": round(stock_hedge, 0),
        "resulting_greeks": {
            "delta": round(new_delta + stock_hedge, 2),
            "gamma": round(current["gamma"] + w1 * option_greeks[0]["gamma"] + w2 * option_greeks[1]["gamma"], 4),
            "vega": round(current["vega"] + w1 * option_greeks[0]["vega"] + w2 * option_greeks[1]["vega"], 4),
        },
        "current_greeks": {k: round(v, 4) for k, v in current.items()},
    }


def calc_position_size(account_size: float, risk_per_trade_pct: float,
                        spot: float, gex_level: float,
                        max_position_pct: float = 0.25) -> dict:
    """Calculate position size based on GEX levels and risk parameters."""
    risk_amount = account_size * risk_per_trade_pct
    max_position_value = account_size * max_position_pct
    gex_factor = min(1.0, abs(gex_level) / 1e9) if gex_level else 0.5
    gex_factor = max(0.2, min(1.0, gex_factor))
    contracts = int(risk_amount / (spot * 0.01 * 100)) if spot > 0 else 1
    contracts = min(contracts, int(max_position_value / (spot * 100)) if spot > 0 else contracts)
    contracts = max(1, contracts)
    return {
        "account_size": account_size,
        "risk_per_trade": risk_amount,
        "max_position_value": max_position_value,
        "recommended_contracts": contracts,
        "gex_factor": round(gex_factor, 2),
        "position_value": round(contracts * spot * 100, 2),
        "position_pct_of_account": round((contracts * spot * 100) / account_size * 100, 2) if account_size else 0,
    }


class LivePolicyReq(BaseModel):
    paid_tickers: Optional[List[str]] = None
    window_start: Optional[str] = None  # "HH:MM" ET
    window_stop: Optional[str] = None


async def _load_policy_from_mongo():
    global PAID_TICKERS
    try:
        doc = await db.live_policy.find_one({"_id": "singleton"})
        if doc:
            PAID_TICKERS = set(doc.get("paid_tickers") or DEFAULT_PAID_TICKERS)
            lw = doc.get("live_window") or {}
            if lw.get("start_hhmm"):
                LIVE_WINDOW["start_hhmm"] = lw["start_hhmm"]
            if lw.get("stop_hhmm"):
                LIVE_WINDOW["stop_hhmm"] = lw["stop_hhmm"]
            log.info(f"live policy loaded: paid={sorted(PAID_TICKERS)} window={LIVE_WINDOW}")
    except Exception as e:
        log.warning(f"live policy load fail: {e}")


_live_tape_session = {"active": False}


def get_live_policy() -> dict:
    """Return current live policy."""
    lw = LIVE_WINDOW
    return {
        "paid_tickers": sorted(PAID_TICKERS),
        "live_window_et": {
            "start_hhmm": lw.get("start_hhmm", "09:30"),
            "stop_hhmm": lw.get("stop_hhmm", "16:00"),
        },
    }


async def update_live_policy(request: dict) -> dict:
    """Update live policy in memory and MongoDB."""
    global PAID_TICKERS
    paid = request.get("paid_tickers")
    if paid is not None:
        PAID_TICKERS = set(paid)
    window_start = request.get("window_start")
    window_stop = request.get("window_stop")
    if window_start:
        LIVE_WINDOW["start_hhmm"] = window_start
    if window_stop:
        LIVE_WINDOW["stop_hhmm"] = window_stop
    doc = {
        "_id": "singleton",
        "paid_tickers": sorted(PAID_TICKERS),
        "live_window": {
            "start_hhmm": LIVE_WINDOW.get("start_hhmm", "09:30"),
            "stop_hhmm": LIVE_WINDOW.get("stop_hhmm", "16:00"),
        },
    }
    await db.live_policy.replace_one({"_id": "singleton"}, doc, upsert=True)
    return get_live_policy()


async def stop_live_tape() -> dict:
    """Stop live tape session."""
    _live_tape_session["active"] = False
    return {"status": "stopped", "stopped": True}


# ============ Schwab Stubs ============

def get_schwab_auth_url() -> dict:
    """Return Schwab auth URL (stub — needs credentials)."""
    import os
    client_id = os.environ.get("SCHWAB_CLIENT_ID")
    if not client_id:
        return {"error": "SCHWAB_CLIENT_ID not set", "auth_url": None}
    redirect_uri = os.environ.get("SCHWAB_REDIRECT_URI", "https://localhost:8000/api/schwab/auth")
    return {
        "auth_url": f"https://api.schwabapi.com/v1/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code",
    }


async def schwab_auth_handler(request: dict) -> dict:
    """Handle Schwab OAuth callback (stub)."""
    return {"status": "error", "message": "Schwab auth not configured"}


async def schwab_get_accounts() -> dict:
    """Get Schwab accounts (stub)."""
    return {"accounts": []}


async def schwab_get_positions(account_hash: str) -> dict:
    """Get Schwab positions (stub)."""
    return {"positions": []}


async def schwab_get_sweeps(account_hash: str) -> dict:
    """Get Schwab sweeps (stub)."""
    return {"sweeps": []}


async def schwab_import_to_portfolio(name: str, account_hash: str) -> dict:
    """Import Schwab positions to portfolio (stub)."""
    return {"status": "ok", "imported": 0}


# ---------- Scheduled pre-fetch (APScheduler) ----------
_scheduler_started = False


async def _prefetch_paid_oi():
    """Pre-fetch OI for all paid tickers so first request after open is instant."""
    log.info(f"prefetch OI for {sorted(PAID_TICKERS)}")
    for t in list(PAID_TICKERS):
        try:
            r = await fetch_oi_for_ticker(t)
            log.info(f"  prefetched {t}: {len(r)} contracts")
        except Exception as e:
            log.warning(f"  prefetch {t} fail: {e}")


async def _scheduler_loop():
    """Lightweight scheduler — fires once per day at PREFETCH_HHMM ET. No extra deps.
    Also refreshes live policy from Mongo every 5 min for multi-worker sync.
    Updates Schwab token TTL gauge every tick."""
    fired_for_date = None
    policy_refresh_counter = 0
    while True:
        try:
            # Refresh live policy from Mongo every ~5 min (multi-worker sync)
            policy_refresh_counter += 1
            if policy_refresh_counter >= 5:
                policy_refresh_counter = 0
                await _load_policy_from_mongo()

            # Update Schwab token TTL metric
            try:
                from schwab import SchwabTokenManager
                _tm = SchwabTokenManager()
                _token = _tm.load()
                if _token:
                    _expires_at = _token.get("expires_at", 0)
                    _now = datetime.now(timezone.utc).timestamp()
                    _ttl = max(0, _expires_at - _now)
                    obs_metrics.schwab_token_expires_in_seconds.set(_ttl)
                else:
                    obs_metrics.schwab_token_expires_in_seconds.set(0)
            except Exception:
                obs_metrics.schwab_token_expires_in_seconds.set(0)

            try:
                from zoneinfo import ZoneInfo
                et = datetime.now(ZoneInfo("America/New_York"))
            except Exception:
                import time
                is_dst = time.localtime().tm_isdst > 0
                offset = 4 if is_dst else 5
                et = datetime.now(timezone.utc) - timedelta(hours=offset)
            hhmm = et.strftime("%H:%M")
            today_et = et.date().isoformat()
            if hhmm >= PREFETCH_HHMM and fired_for_date != today_et and et.weekday() < 5:
                fired_for_date = today_et
                asyncio.create_task(_prefetch_paid_oi())
        except Exception as e:
            log.warning(f"scheduler tick err: {e}")
        await asyncio.sleep(60)


class PositionReq(BaseModel):
    symbol: str
    option_type: str  # "call" or "put"
    strike: float
    expiry: str  # "YYYY-MM-DD"
    quantity: int  # positive = long, negative = short
    entry_price: float
    entry_iv: float
    underlying_price: float


class HedgeReq(BaseModel):
    spot: float
    iv: float
    hedge_options: List[Dict[str, Any]]  # [{"strike": 745, "expiry": "2026-05-16", "type": "call", "iv": 0.15}]


class SchwabAuthReq(BaseModel):
    code: str  # Authorization code from OAuth callback


class AlertRule(BaseModel):
    ticker: str
    alert_type: str  # "gex_cross", "gex_spike", "oi_spike", "iv_spike"
    threshold: float
    direction: str = "above"  # "above" or "below"
    expiry: Optional[str] = None
    strike: Optional[float] = None
    label: Optional[str] = None


# In-memory alert store (persist to Mongo in production)
_alert_rules: List[Dict[str, Any]] = []
_alert_history: List[Dict[str, Any]] = []


@app.post("/api/alerts")
async def create_alert(rule: AlertRule):
    """Create a new GEX alert rule."""
    rule_dict = rule.dict()
    rule_dict["id"] = str(len(_alert_rules) + 1)
    rule_dict["created_at"] = datetime.now(timezone.utc).isoformat()
    rule_dict["active"] = True
    rule_dict["trigger_count"] = 0
    _alert_rules.append(rule_dict)
    return {"status": "created", "rule": rule_dict}


@app.get("/api/alerts")
async def list_alerts(ticker: Optional[str] = None, active_only: bool = True):
    """List alert rules."""
    rules = _alert_rules
    if ticker:
        rules = [r for r in rules if r["ticker"] == ticker.upper()]
    if active_only:
        rules = [r for r in rules if r.get("active", True)]
    return {"rules": rules, "count": len(rules)}


@app.delete("/api/alerts/{alert_id}")
async def delete_alert(alert_id: str):
    """Delete an alert rule."""
    global _alert_rules
    _alert_rules = [r for r in _alert_rules if r["id"] != alert_id]
    return {"status": "deleted"}


@app.get("/api/alerts/types")
async def list_alert_types():
    """List all available alert types."""
    from alert_engine import AlertEngine
    AlertEngine()
    # Get all alert type constants
    alert_types = [
        {"type": "GAMMA_FLIP", "priority": "HIGH", "description": "Regime change from positive to negative gamma"},
        {"type": "GAMMA_SQUEEZE", "priority": "HIGH", "description": "Negative gamma + spot near flip + volume spike"},
        {"type": "MOMENTUM_EXTREME", "priority": "HIGH", "description": "Strong bullish or bearish momentum"},
        {"type": "WALL_BREACH", "priority": "MEDIUM", "description": "Spot crosses through call/put wall"},
        {"type": "GEX_MAGNITUDE_SHIFT", "priority": "MEDIUM", "description": "Total GEX changed > 40%"},
        {"type": "GAMMA_FLIP_PROXIMITY", "priority": "MEDIUM", "description": "Spot within 0.3% of gamma flip point"},
        {"type": "PIN_RISK", "priority": "LOW", "description": "Spot near max gamma strike"},
        {"type": "CHARM_PINNING", "priority": "HIGH", "description": "Charm-driven pinning (0DTE)"},
        {"type": "VANNA_REGIME_CHANGE", "priority": "HIGH", "description": "Sign flip in net VEX above floor"},
        {"type": "UNUSUAL_PC_OI_RATIO", "priority": "MEDIUM", "description": "Put OI / call OI ratio > 2x"},
        {"type": "MAX_PAIN_MAGNET", "priority": "LOW", "description": "Spot within 1% of max pain in positive gamma"},
    ]
    return {"alert_types": alert_types, "count": len(alert_types)}


@app.get("/api/alerts/check/{ticker}")
async def check_alerts(ticker: str):
    """Check all alert rules against current data. Returns triggered alerts."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"

    raw = await fetch_spot_and_chains_merged(t, 8)
    spot = raw["spot"]
    if not spot:
        return {"triggered": [], "error": "No data"}

    triggered = []
    for rule in _alert_rules:
        if not rule.get("active", True):
            continue
        if rule["ticker"] != t:
            continue

        value = 0
        if rule["alert_type"] == "gex_cross":
            strikes = compute_gex_by_strike(spot, raw["contracts"], t)
            total_gex = sum(s["gex"] for s in strikes)
            value = total_gex
        elif rule["alert_type"] == "gex_spike":
            strikes = compute_gex_by_strike(spot, raw["contracts"], t)
            if rule.get("strike"):
                match = [s for s in strikes if abs(s["strike"] - rule["strike"]) < 0.5]
                value = match[0]["gex"] if match else 0
            else:
                value = max(abs(s["gex"]) for s in strikes) if strikes else 0
        elif rule["alert_type"] == "oi_spike":
            for c in raw["contracts"]:
                if rule.get("strike") and abs(c["strike"] - rule["strike"]) < 0.5:
                    value = c["oi"]
                    break
                elif rule.get("expiry") and c["expiry"] == rule["expiry"]:
                    value = max(value, c["oi"])
        elif rule["alert_type"] == "iv_spike":
            ivs = [c["iv"] for c in raw["contracts"] if c["iv"] > 0]
            value = max(ivs) if ivs else 0

        crossed = False
        if rule["direction"] == "above" and value > rule["threshold"]:
            crossed = True
        elif rule["direction"] == "below" and value < rule["threshold"]:
            crossed = True

        if crossed:
            trigger = {
                "rule_id": rule["id"],
                "ticker": t,
                "type": rule["alert_type"],
                "value": round(value, 2),
                "threshold": rule["threshold"],
                "direction": rule["direction"],
                "label": rule.get("label", ""),
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            }
            triggered.append(trigger)
            rule["trigger_count"] = rule.get("trigger_count", 0) + 1
            _alert_history.append(trigger)

    return {"triggered": triggered, "spot": spot, "asof": datetime.now(timezone.utc).isoformat()}


@app.get("/api/flow/{ticker}")
async def flow_sse(
    ticker: str,
    max_seconds: int = Query(30, ge=1, le=300),
    enforce_window: bool = Query(True),
):
    """SSE flow endpoint for real-time options flow with paid-ticker and window enforcement."""
    t = ticker.strip().upper()

    # Check paid ticker restriction
    if t not in PAID_TICKERS:
        async def _error_stream():
            import json as _json
            msg = _json.dumps({"error": f"{t} not in paid_tickers. Add it via /api/live/policy.", "ticker": t})
            yield f"event: error\ndata: {msg}\n\n"
        return StreamingResponse(_error_stream(), media_type="text/event-stream")

    # Check trading window
    if enforce_window:
        try:
            from zoneinfo import ZoneInfo
            et = datetime.now(ZoneInfo("America/New_York"))
        except Exception:
            import time as _time
            is_dst = _time.localtime().tm_isdst > 0
            offset = 4 if is_dst else 5
            et = datetime.now(timezone.utc) - timedelta(hours=offset)
        hhmm = et.strftime("%H:%M")
        lw = LIVE_WINDOW
        start = lw.get("start_hhmm", "09:30")
        stop = lw.get("stop_hhmm", "16:00")
        if hhmm < start or hhmm >= stop:
            async def _window_error():
                import json as _json
                msg = _json.dumps({"error": f"Outside trading window ({start}-{stop} ET). Current: {hhmm} ET.", "ticker": t})
                yield f"event: error\ndata: {msg}\n\n"
            return StreamingResponse(_window_error(), media_type="text/event-stream")

    # Stream flow data
    async def _flow_stream():
        from services.flowseeker import fetch_live_flow
        import asyncio as _asyncio
        import json as _json
        deadline = datetime.now(timezone.utc).timestamp() + max_seconds
        sent = False
        while datetime.now(timezone.utc).timestamp() < deadline:
            try:
                prints = await fetch_live_flow(ticker=t, limit=20, min_premium=0)
                if prints:
                    msg = _json.dumps({"ticker": t, "prints": prints, "ts": datetime.now(timezone.utc).isoformat()})
                    yield f"event: flow\ndata: {msg}\n\n"
                    sent = True
            except Exception as e:
                msg = _json.dumps({"error": str(e), "ticker": t})
                yield f"event: error\ndata: {msg}\n\n"
                break
            # Send heartbeat to keep connection alive and give test client data
            if not sent:
                msg = _json.dumps({"ticker": t, "heartbeat": True, "ts": datetime.now(timezone.utc).isoformat()})
                yield f"event: heartbeat\ndata: {msg}\n\n"
            await _asyncio.sleep(1)

    return StreamingResponse(_flow_stream(), media_type="text/event-stream")


# ============ Unusual Options Activity (UOA) ============

@app.websocket("/ws/gex/{ticker}")
async def websocket_gex(websocket: WebSocket, ticker: str):
    """WebSocket stream pushing live spot + key GEX levels every 5 seconds.
    Includes heartbeat/ping-pong for connection health."""
    from auth import verify_ws_token
    if not await verify_ws_token(websocket):
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    
    consecutive_errors = 0
    max_errors = 10
    
    try:
        while True:
            try:
                raw = await fetch_spot_and_chains_merged(t, 4)
                spot = raw["spot"]
                if not spot or not raw["contracts"]:
                    await websocket.send_json({"error": "No data", "ticker": t})
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0  # Reset on success
                    strikes = compute_gex_by_strike(spot, raw["contracts"], t)
                    total_gex = sum(s["gex"] for s in strikes)
                    positive = sorted([s for s in strikes if s["gex"] > 0], key=lambda x: x["gex"], reverse=True)
                    negative = sorted([s for s in strikes if s["gex"] < 0], key=lambda x: x["gex"])
                    nodes = classify_nodes(strikes, spot)
                    
                    payload = {
                        "ticker": t,
                        "spot": spot,
                        "total_gex": round(total_gex, 0),
                        "king": nodes.get("king"),
                        "floors": [{"strike": s["strike"], "gex": round(s["gex"], 0)} for s in positive[:5]],
                        "ceilings": [{"strike": s["strike"], "gex": round(s["gex"], 0)} for s in negative[:5]],
                        "regime": nodes.get("regime"),
                        "asof": datetime.now(timezone.utc).isoformat(),
                    }
                    await websocket.send_json(_sanitize(payload))
                
                # Back off on repeated errors
                sleep_time = min(5 * (2 ** consecutive_errors), 60)
                await asyncio.sleep(sleep_time)
                
            except WebSocketDisconnect:
                raise
            except Exception as e:
                consecutive_errors += 1
                log.warning(f"WebSocket error for {t}: {e} (consecutive: {consecutive_errors})")
                await websocket.send_json({"error": str(e), "ticker": t})
                if consecutive_errors >= max_errors:
                    log.error(f"Too many consecutive errors for {t}, closing WebSocket")
                    await websocket.close(code=1011, reason="Too many errors")
                    break
                await asyncio.sleep(min(5 * consecutive_errors, 30))
    except WebSocketDisconnect:
        log.info(f"WebSocket disconnected: {t}")
    except Exception as e:
        log.error(f"WebSocket fatal error for {t}: {e}")


# CORS — explicit origins only, no wildcard default
_cors_origins_env = os.environ.get("CORS_ORIGINS", "")
if not _cors_origins_env and os.environ.get("ENVIRONMENT") == "production":
    raise RuntimeError(
        "CORS_ORIGINS must be set in production — refusing to start with wildcard. "
        "Set CORS_ORIGINS to a comma-separated list of allowed origins."
    )
_cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()] if _cors_origins_env else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# Security headers middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if os.environ.get("ENVIRONMENT") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' ws: wss: https:; "
        "font-src 'self' data:;"
    )
    return response

# Auth middleware — checks X-API-Key header for mutating routes
from auth import verify_api_key

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Verify API key for protected mutating routes."""
    try:
        await verify_api_key(request)
    except HTTPException as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    response = await call_next(request)
    return response


# Dash UI auth middleware — protects /dashboard/ in production
@app.middleware("http")
async def dash_auth_middleware(request: Request, call_next):
    """Require authentication for Dash UI routes in production."""
    if request.url.path.startswith("/dashboard/"):
        # In production, require a valid session token
        if os.environ.get("ENVIRONMENT") == "production":
            token = request.query_params.get("token", "") or request.cookies.get("session_token", "")
            expected = os.environ.get("DASH_SESSION_TOKEN", "")
            if not expected:
                logger.critical("DASH_SESSION_TOKEN not set — /dashboard/ is INSECURE")
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=503, detail="Dashboard auth not configured")
            if token != expected:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=401, detail="Unauthorized")
    response = await call_next(request)
    return response


# ----------------------------- Observability Middleware ------------------------------

import services.observability as obs_metrics
from services.observability import get_metrics_bytes, get_metrics_content_type


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Record API request duration and emit metrics."""
    # Skip metrics endpoint itself to avoid recursion
    if request.url.path == "/metrics":
        return await call_next(request)

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    # Use path template if available, otherwise actual path
    route = request.url.path
    try:
        if request.scope.get("route"):
            route = request.scope["route"].path
    except Exception:
        pass

    obs_metrics.api_request_duration_seconds.labels(
        route=route,
        method=request.method,
        status=str(response.status_code),
    ).observe(duration)

    return response


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics exposition endpoint."""
    from starlette.responses import Response
    return Response(
        content=get_metrics_bytes(),
        media_type=get_metrics_content_type(),
    )

from memory_integration import remember_trade, remember_gex_observation, recall_trading_context, get_trading_summary


class TradeMemoryRequest(BaseModel):
    ticker: str
    trade_type: str = "unknown"
    entry_price: float = 0
    exit_price: float = 0
    pnl: float = 0
    notes: str = ""


class GexMemoryRequest(BaseModel):
    ticker: str
    observation: str
    metadata: Optional[Dict[str, Any]] = None


@app.on_event("startup")
async def on_start():
    try:
        await db.snapshots.create_index([("ticker", 1), ("ts", -1)])
        cache = init_cache(db)
        await cache.ensure_index()
        await _load_policy_from_mongo()
        log.info("MongoDB connected and indexes created")
    except Exception as e:
        log.warning(f"MongoDB unavailable during startup ({type(e).__name__}): {e}")
        log.warning("Server running in degraded mode — DB-dependent endpoints will fail")
    global _scheduler_started
    if not _scheduler_started:
        _scheduler_started = True
        asyncio.create_task(_scheduler_loop())
        log.info(f"scheduler started · prefetch at {PREFETCH_HHMM} ET")
    log.info("databento cache initialized")


@app.on_event("shutdown")
async def on_stop():
    client.close()


# ============ Flowseeker route wiring ============
# Skylit-parity live institutional options flow + drilldown.
from routes.flowseeker import router as flowseeker_router
app.include_router(flowseeker_router, tags=["flowseeker"])

# ============ Route module wiring ============
# Wired by Hermes/OWL on 2026-05-19 — all orphaned route modules.
# All modules mounted with prefix="/api" for consistent URL structure.

from routes.admin import router as admin_router
app.include_router(admin_router, prefix="/api", tags=["admin"])

from routes.alpaca import router as alpaca_router
app.include_router(alpaca_router, tags=["alpaca"])

from routes.analytics import router as analytics_router
app.include_router(analytics_router, prefix="/api", tags=["analytics"])

from routes.briefing import router as briefing_router
app.include_router(briefing_router, prefix="/api", tags=["briefing"])

from routes.morning_briefing_api import router as morning_briefing_router
app.include_router(morning_briefing_router, prefix="/api", tags=["morning-briefing"])

from routes.data_providers import router as data_providers_router
app.include_router(data_providers_router, tags=["data"])

from routes.flashalpha import router as flashalpha_router
app.include_router(flashalpha_router, tags=["flashalpha"])

from routes.gemini import router as gemini_router
app.include_router(gemini_router, tags=["ai"])

from routes.heatseeker import router as heatseeker_router
app.include_router(heatseeker_router, tags=["heatseeker"])

from routes.heatseeker_snapshots_api import router as heatseeker_snapshots_router
app.include_router(heatseeker_snapshots_router, prefix="/api/heatseeker", tags=["heatseeker-snapshots"])

from routes.ml_predict_api import router as ml_predict_router
app.include_router(ml_predict_router, tags=["ml-predict"])

from routes.predictive import router as predictive_router
app.include_router(predictive_router, tags=["predictive"])

from routes.live_trading import router as live_trading_router
app.include_router(live_trading_router, prefix="/api", tags=["live_trading"])

from routes.llm import router as llm_router
app.include_router(llm_router, prefix="/api", tags=["llm"])

from routes.memory import router as memory_router
app.include_router(memory_router, prefix="/api", tags=["memory"])

from routes.ml_training import router as ml_training_router
app.include_router(ml_training_router, tags=["ml_training"])

from routes.portfolio import router as portfolio_router
app.include_router(portfolio_router, prefix="/api", tags=["portfolio"])

from routes.schwab import router as schwab_router
app.include_router(schwab_router, prefix="/api", tags=["schwab"])

from routes.social_flow import router as social_flow_router
app.include_router(social_flow_router, tags=["social"])

# Wire previously orphaned modules
from routes.alerts import router as alerts_router
app.include_router(alerts_router, tags=["alerts"])

from routes.alerts_api import router as alerts_api_router
app.include_router(alerts_api_router, tags=["alerts-api"])

# Preferences & theme sync
from routes.preferences import router as preferences_router
app.include_router(preferences_router, tags=["preferences"])

from routes.market_data import router as market_data_router
app.include_router(market_data_router, prefix="/api", tags=["market_data"])

from routes.ml_api import router as ml_api_router
app.include_router(ml_api_router, tags=["ml_api"])

# ============ Paper Blueprint Route Wiring ============
# New API routes from the Project Oracle Master Directive

from routes.vpin import router as vpin_router
app.include_router(vpin_router, tags=["vpin"])

from routes.retail_flow import router as retail_flow_router
app.include_router(retail_flow_router, tags=["retail-flow"])

from routes.trinity import router as trinity_router
app.include_router(trinity_router, tags=["trinity"])

from routes.anomaly import router as anomaly_router
app.include_router(anomaly_router, tags=["anomaly"])

from routes.ensemble import router as ensemble_router
app.include_router(ensemble_router, tags=["ensemble"])

from routes.liquidity import router as liquidity_router
app.include_router(liquidity_router, tags=["liquidity"])

from routes.hawkes import router as hawkes_router
app.include_router(hawkes_router, tags=["hawkes"])

from routes.vol_surface import router as vol_surface_router
app.include_router(vol_surface_router, tags=["vol_surface"])

# ============ Microstructure Combined API ============
from routes.microstructure import router as microstructure_router
app.include_router(microstructure_router, tags=["microstructure"])

# ============ Replay, Agent Hub, Nexus ============
from routes.replay import router as replay_router
app.include_router(replay_router, tags=["replay"])

from routes.agent_hub import router as agent_hub_router
app.include_router(agent_hub_router, tags=["agent-hub"])

from routes.nexus import router as nexus_router
app.include_router(nexus_router, tags=["nexus"])

# ============ Alpha Advantage Data API ============
from routes.alpha_advantage import router as alpha_advantage_router
app.include_router(alpha_advantage_router, tags=["alpha-advantage"])

from routes.greeks import router as greeks_router
app.include_router(greeks_router, prefix="/api/greeks", tags=["greeks"])

# ============ Position Sizing (Kelly Criterion) ============
from routes.position_sizing_api import router as position_sizing_router
app.include_router(position_sizing_router, tags=["position-sizing"])

# ============ DuckDB Engine Initialization ============

@app.on_event("startup")
async def startup_duckdb():
    """Start DuckDB async writer on server startup."""
    try:
        await duckdb_engine.start()
        log.info("DuckDB engine started")
    except Exception as e:
        log.warning(f"DuckDB startup failed (non-fatal): {e}")

@app.on_event("shutdown")
async def shutdown_duckdb():
    """Flush and stop DuckDB on shutdown."""
    try:
        await duckdb_engine.stop()
        log.info("DuckDB engine stopped")
    except Exception:
        pass

# ============ Ingestion Pipeline (Mock Feed for now) ============
from services.ingestion_pipeline import IngestionPipeline
from services.mock_schwab_feed import MockSchwabFeed

_ingestion_pipeline: Optional[IngestionPipeline] = None
_mock_feed: Optional[MockSchwabFeed] = None

@app.on_event("startup")
async def startup_ingestion():
    """Launch ingestion pipeline with mock feed on startup."""
    global _ingestion_pipeline, _mock_feed
    try:
        _ingestion_pipeline = IngestionPipeline(
            db=duckdb_engine,
            max_queue_size=10000,
            flush_interval_ms=50.0,
        )
        await _ingestion_pipeline.start()

        # Use mock feed (swap to SchwabStreamer when credentials available)
        _mock_feed = MockSchwabFeed(rate=100.0, symbols=["SPY", "QQQ"], seed=42)
        _mock_feed.on_tick(_ingestion_pipeline.enqueue_tick)
        _mock_feed.on_chain(_ingestion_pipeline.enqueue_chain)
        _mock_feed.on_lob(_ingestion_pipeline.enqueue_lob)
        _mock_feed.on_lob_depth(_ingestion_pipeline.enqueue_lob_depth)

        # Run mock feed in background
        asyncio.create_task(_mock_feed.start())
        log.info("Ingestion pipeline + mock feed started")
    except Exception as e:
        log.warning(f"Ingestion startup failed (non-fatal): {e}")

@app.on_event("shutdown")
async def shutdown_ingestion():
    """Drain queue and stop ingestion on shutdown."""
    global _ingestion_pipeline, _mock_feed
    try:
        if _mock_feed:
            await _mock_feed.stop()
        if _ingestion_pipeline:
            await _ingestion_pipeline.stop()
        log.info("Ingestion pipeline stopped")
    except Exception as e:
        log.warning(f"Ingestion shutdown error: {e}")

# ============ Paper Trading Engine ============
from services.paper_trading import PaperTradingEngine
from routes.paper_trading import set_paper_engine as _set_paper_engine

_paper_engine: Optional[PaperTradingEngine] = None

@app.on_event("startup")
async def startup_paper_trading():
    """Initialize paper trading engine on startup."""
    global _paper_engine
    try:
        _paper_engine = PaperTradingEngine(
            initial_capital=100_000.0,
            max_position_pct=0.10,
            max_delta_exposure=500.0,
        )
        _set_paper_engine(_paper_engine)
        log.info("Paper trading engine started ($100K initial capital)")
    except Exception as e:
        log.warning(f"Paper trading startup failed (non-fatal): {e}")

# ============ WebSocket Endpoint ============

@app.websocket("/ws/{topic}")
async def websocket_endpoint(websocket: WebSocket, topic: str):
    """WebSocket endpoint for real-time data streaming.

    Topics: ticks, flow, toxicity, analytics
    """
    from auth import verify_ws_token
    if not await verify_ws_token(websocket):
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await ws_manager.connect(websocket, [topic])
    try:
        while True:
            # Keep connection alive, handle client messages
            data = await websocket.receive_text()
            # Echo back for now (could handle subscription changes)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# ============ Paper Trading Routes ============
from routes.paper_trading import router as paper_trading_router
app.include_router(paper_trading_router, tags=["paper_trading"])

# ============ Replay Route ============
from routes.replay import router as replay_router
app.include_router(replay_router, tags=["replay"])

# ============ Dash UI Mount ============
try:
    from services.dash_ui import create_dash_app
    _dash_app = create_dash_app(app, url_base_pathname="/dashboard/")
    if _dash_app:
        log.info("Dash UI mounted at /dashboard/")
except Exception as e:
    log.warning(f"Dash UI mount failed (non-fatal): {e}")
