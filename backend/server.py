"""
Confluence Decoder - Skylit-style Heatseeker GEX Analytics
- Databento: real-time/EOD Open Interest via OPRA.PILLAR statistics + Live trades for Flowseeker
- yfinance: spot + IV from option chains (fallback for OI when Databento has no data)
- Polygon: stock aggs, tap-count history
- Black-Scholes gamma -> per-strike (and per-strike×expiry) GEX
- Node hierarchy, patterns, velocity, rolling, trinity
"""
import asyncio
import itertools
import logging
import math
import os
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

from advanced_analytics import (
    calc_charm_integral,
    calc_gamma_flip_levels,
    calc_hedge_impulse_curve,
    calc_implied_pdf,
    calc_market_regime,
    calc_pressure_cloud,
)
from databento_provider import fetch_oi_for_ticker, init_cache
from portfolio import Portfolio, Position, calc_position_size
from services.duckdb_engine import db as duckdb_engine

# Rust-backed implementations (decoder_core delegation with pure-Python fallback,
# bit-exact parity verified 2026-08-22). Was gex_server_utils (pure Python).
from services.gex_core import (
    calc_aggregate_gex_curve,
    calc_implied_move,
    calc_probability_distribution,
    classify_nodes,
    compute_gex_by_strike,
    compute_gex_by_strike_volume,
    compute_gex_grid,
    detect_opportunities,
    detect_patterns,
)
from services.logging_config import CorrelationIdMiddleware, setup_logging
from services.websocket_streamer import manager as ws_manager
from vol_analytics import (
    calc_iv_rank_percentile,
    calc_iv_surface_data,
    calc_realized_volatility,
    calc_skew_metrics,
)

ROOT_DIR = Path(__file__).parent  # backend/
load_dotenv(ROOT_DIR / ".env")

_env = os.getenv("ENVIRONMENT") or os.getenv("ENV") or "development"
_is_prod = bool(_env == "production")  # noqa: F841  (used by exception handlers)
_is_staging = bool(_env == "staging")  # noqa: F841  (used by exception handlers)

def _get_cors_origin_for_handlers() -> str:
    """Return the runtime-effective CORS origin to echo from exception handlers.

    Reads the module-level `_cors_origins` list that the CORS config block
    populates at import time (see the L2500+ block).  Reading at handler-call
    time (not at module-load time) avoids F821 and keeps the handler sites
    from having to repeat the env-var resolution.

    In production/staging with CORS_ORIGINS unset, server.startup aborts with
    RuntimeError before this helper ever gets called (defence-in-depth).
    """
    # _cors_origins is defined by the CORS config block below (~L2507).
    # By the time any request reaches the exception handlers, module import
    # is complete and _cors_origins is in the module namespace.  globals().get
    # does a runtime lookup with default, surviving future refactors of the
    # CORS config block position.
    _origins = globals().get("_cors_origins")
    return _origins[0] if _origins else "*"


MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")  # defence-in-depth env-default (P1 entry #3 in docs/superpowers/plans/2026-06-20-freebuff-decoder-hardening-60h.md)
DB_NAME = os.environ.get("DB_NAME", "floww")
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")

client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
db = client[DB_NAME]

LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

setup_logging(level=logging.INFO)

log = logging.getLogger("heatseeker")

# -- Graceful shutdown infrastructure --
_shutdown_event = asyncio.Event()
_background_tasks: set[asyncio.Task] = set()


async def _logged_task(coro, name: str):
    """Run a coroutine and log any exception. Used to wrap fire-and-forget tasks."""
    try:
        return await coro
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.warning(f"background task {name!r} raised: {type(e).__name__}: {e}", exc_info=True)


app = FastAPI(title="Meridian — GEX Terminal")
app.add_middleware(CorrelationIdMiddleware)

# ----------------------------- Safe Float Helper -----------------------------

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
    # Read-only dashboard GETs are exempt from the per-IP burst limit: the Skylit
    # dashboard fires ~20+ panel reads on load + polling, which blows past a
    # 60/min budget and surfaced as HTTP 429 on nearly every panel. Mutating
    # routes (POST/DELETE: snapshots, portfolio writes, alerts) stay limited.
    if request.method == "GET" and request.url.path.startswith((
        "/api/heatseeker", "/api/analytics", "/api/flowseeker", "/api/heatmap",
        "/api/spot", "/api/data", "/api/tickers", "/api/portfolio", "/api/alerts",
        "/api/dual_gex", "/api/iv_mid", "/api/screener", "/api/wheel_income",
        "/api/max_pain", "/api/contract", "/api/chain",
    )):
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
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
        except Exception as e:
            log.warning(f"server.py: rate_limit_429_count metric raise swallowed (429 response preserved): {e}", exc_info=True)
        # Include CORS headers so frontend can read the 429 (not blocked by CORS)
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "retry_after": retry_after,
                "message": f"Too many requests. Retry in {retry_after}s.",
            },
            # Belt-and-suspenders: some FastAPI exception paths bypass CORSMiddleware;
            # echo explicitly so 5xx/4xx still carry the right CORS origin (P2.5-B).
            headers={
                "Retry-After": str(retry_after),
                "Access-Control-Allow-Origin": _get_cors_origin_for_handlers(),
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

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    log.error(f"HTTP {exc.status_code} {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail), "status_code": exc.status_code, "path": request.url.path},
        headers={
            "Access-Control-Allow-Origin": _get_cors_origin_for_handlers(),
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    log.error(f"Validation error {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
        headers={
            "Access-Control-Allow-Origin": _get_cors_origin_for_handlers(),
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
        },
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled exception {request.url.path}: {type(exc).__name__}: {exc}", exc_info=True)
    # Track error (internal-only; never reaches the wire)
    try:
        from error_tracking import log_error
        log_error(
            error_type=type(exc).__name__,
            message=str(exc),
            data={"path": request.url.path, "method": request.method}
        )
    except Exception as e:
        log.warning(f"server.py: error_tracking.log_error raise swallowed (500 response preserved): {e}", exc_info=True)
    # INTENTIONAL: no path/type/exc in prod to avoid internal-info leak (P2.5-C).
    _redacted = bool(_is_prod or _is_staging)  # single source-of-truth for the env branch
    _payload = (
        {"error": "Internal server error"}
        if _redacted
        else {"error": "Internal server error", "type": type(exc).__name__, "path": request.url.path}
    )
    # INTENTIONAL: track volume of redacted 500s for P2.5-D observability —
    # the wire payload above is already redacted; this only counts how often
    # the redaction branch fires, so dashboards can detect attack / upstream
    # failure spikes originating from prod traffic. The metric never blocks
    # the request (try/except swallows any Prom-client import or .inc() fault).
    if _redacted:
        try:
            from error_tracking import redacted_500_count
            redacted_500_count.labels(env=_env).inc()
        except Exception as e:
            log.warning(f"server.py: redacted_500_count metric raise swallowed (500 response preserved): {e}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=_payload,
        headers={
            "Access-Control-Allow-Origin": _get_cors_origin_for_handlers(),
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
    except Exception as e:
        log.warning(f"server.py: perf_monitor / set_request_id raise swallowed (response+header preserved): {e}", exc_info=True)

    response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))
    # Market-data API responses must never be browser-cached — a stale heatmap
    # is worse than a slow one. Static assets are handled by Caddy's cache headers.
    if request.url.path.startswith(("/api/", "/gex/")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


# Cache for spot/chains so we don't slam yfinance
_cache: dict[str, dict[str, Any]] = {}
CACHE_TTL_SEC = 25



def _pos_to_dict(p):
    """Serialize a Position to a dict for Mongo storage."""
    return {
        "symbol": p.symbol, "option_type": p.option_type, "strike": p.strike,
        "entry_iv": p.entry_iv, "underlying_price": p.underlying_price,
        "is_long": p.is_long, "dte": p.dte, "T": p.T,
        "delta": p.delta, "gamma": p.gamma, "vega": p.vega, "theta": p.theta,
        "vanna": p.vanna, "charm": p.charm, "vomma": p.vomma, "zomma": p.zomma,
        "price": p.price,
    }

def _pos_from_dict(d: dict[str, Any]) -> Position:
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
    p.T = d.get("T") or 0
    p.delta = d.get("delta") or 0
    p.gamma = d.get("gamma") or 0
    p.vega = d.get("vega") or 0
    p.theta = d.get("theta") or 0
    p.vanna = d.get("vanna", 0)
    p.charm = d.get("charm", 0)
    p.vomma = d.get("vomma", 0)
    p.zomma = d.get("zomma", 0)
    p.price = d.get("price", 0)
    p.entry_date = datetime.now(UTC)
    return p

async def _save_portfolio_to_mongo(name: str, portfolio: Portfolio):
    """Persist portfolio to Mongo."""
    positions = [_pos_to_dict(p) for p in portfolio.positions]
    await db.portfolios.update_one(
        {"_id": name},
        {"$set": {"positions": positions, "cash": portfolio.cash,
                   "updated_at": datetime.now(UTC).isoformat()}},
        upsert=True,
    )

async def _load_portfolio_from_mongo(name: str) -> Portfolio | None:
    """Load portfolio from Mongo. Returns None if not found."""
    doc = await db.portfolios.find_one({"_id": name})
    if not doc:
        return None
    p = Portfolio(doc.get("name", name))
    p.cash = doc.get("cash", 0.0)
    for pos in doc.get("positions", []):
        try:
            p.positions.append(_pos_from_dict(pos))
        except Exception:
            continue
    return p


# ============ Data Fetching Functions (moved here to maintain correct order) ============

DEFAULT_PAID_TICKERS = {"SPY", "QQQ", "IWM", "DIA", "TLT", "SPX"}
PAID_TICKERS: set = (
    set()
    if os.environ.get("DISABLE_DATABENTO", "").lower() in ("1", "true", "yes")
    else set(DEFAULT_PAID_TICKERS)
)

# Session tracking for cost meter
_session_state: dict[str, Any] = {
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
        et = datetime.now(UTC) - timedelta(hours=offset)
    hhmm = et.strftime("%H:%M")
    return LIVE_WINDOW["start_hhmm"] <= hhmm <= LIVE_WINDOW["stop_hhmm"]


# ===== RESTORED (7ec433f over-deletion): cache + gex/pdf/opportunity helpers =====

# --- restored: cache_get + cache_set ---
def cache_get(key: str):
    item = _cache.get(key)
    if not item:
        return None
    if time.time() - item["ts"] > CACHE_TTL_SEC:
        return None
    return item["data"]


def cache_set(key: str, data: Any):
    _cache[key] = {"ts": time.time(), "data": data}




async def save_snapshot(ticker: str, payload: dict[str, Any]):
    try:
        doc = {
            "ticker": ticker,
            "ts": datetime.now(UTC).isoformat(),
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


async def velocity_and_rolling(ticker: str, current_nodes: dict[str, Any]) -> dict[str, Any]:
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



# ===== END RESTORED =====


def fetch_spot_and_chains(ticker: str, max_expiries: int = 4) -> dict[str, Any]:
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
    contracts: list[dict[str, Any]] = []
    today = datetime.now(UTC).date()

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
            # 2026-08-22: itertuples replaces iterrows — ~10x faster on
            # wide yfinance frames (iterrows builds a Series per row).
            for row in df.itertuples(index=False):
                strike = float(getattr(row, "strike", 0) or 0)
                oi = float(getattr(row, "openInterest", 0) or 0)
                iv = float(getattr(row, "impliedVolatility", 0) or 0)
                vol = float(getattr(row, "volume", 0) or 0)
                # Require valid strike; relax OI/IV filter for sparse data (e.g. SPX)
                if strike <= 0:
                    continue
                contracts.append({
                    "expiry": exp, "T": T, "type": kind,
                    "strike": strike, "oi": oi, "iv": iv, "volume": vol,
                })

    data = {"ticker": ticker, "spot": spot, "expiries": expiries, "contracts": contracts}
    cache_set(key, data)
    return data


async def fetch_spot_and_chains_merged(ticker: str, max_expiries: int = 4) -> dict[str, Any]:
    """Try Public API first, then cvserver, then yfinance + Databento.

    Priority:
      1. Public API (public.com brokerage) — chain data with full greeks
      2. cvserver (CVForge) — 32 expiries, 171 strikes, all greeks included
      3. yfinance + Databento OI overlay (legacy path)
    """
    # ── 0. Try Public API first (with timeout) ──
    PUBLIC_API_KEY = os.environ.get("PUBLIC_API_KEY", "")
    if PUBLIC_API_KEY:
        try:
            from services.public_api_adapter import fetch_chain_from_public_api
            pub_data = await asyncio.wait_for(
                fetch_chain_from_public_api(ticker, max_expiries=max_expiries),
                timeout=30.0
            )
            if pub_data and pub_data.get("contracts") and pub_data.get("spot", 0) > 0:
                try:
                    from data_providers import _record_provider_call
                    _record_provider_call("public_api", True)
                except Exception:
                    pass
                return pub_data
        except TimeoutError:
            log.info(f"Public API timeout for {ticker}, falling back to cvserver")
            try:
                from data_providers import _record_provider_call
                _record_provider_call("public_api", False)
            except Exception:
                pass
        except Exception as e:
            log.info(f"Public API fetch failed for {ticker}: {e}")
            try:
                from data_providers import _record_provider_call
                _record_provider_call("public_api", False)
            except Exception:
                pass

    # ── 1. Try cvserver first (with timeout) ──
    try:
        from services.cvserver_client import fetch_chain_from_cvserver
        cv_data = await asyncio.wait_for(
            fetch_chain_from_cvserver(ticker, max_expiries=max_expiries),
            timeout=30.0
        )
        if cv_data and cv_data.get("contracts") and cv_data.get("spot", 0) > 0:
            for c in cv_data["contracts"]:
                c["oi_source"] = "cvserver"
            try:
                from data_providers import _record_provider_call
                _record_provider_call("cvserver", True)
            except Exception:
                pass
            return cv_data
    except TimeoutError:
        log.warning(f"cvserver timeout for {ticker}, falling back to yfinance")
        try:
            from data_providers import _record_provider_call
            _record_provider_call("cvserver", False)
        except Exception:
            pass
    except Exception as e:
        log.warning(f"cvserver fetch failed for {ticker}: {e}")
        try:
            from data_providers import _record_provider_call
            _record_provider_call("cvserver", False)
        except Exception:
            pass

    # ── 2. Fallback: yfinance + Databento ──
    yf_success = True
    try:
        yf_data = await asyncio.wait_for(
            asyncio.to_thread(fetch_spot_and_chains, ticker, max_expiries),
            timeout=30.0,
        )
        if not yf_data or not yf_data.get("spot"):
            yf_success = False
    except TimeoutError:
        log.warning(f"yfinance timeout for {ticker}, giving up on chain data")
        yf_success = False
        yf_data = {"spot": 0, "contracts": []}
    except Exception:
        yf_success = False
        yf_data = {"spot": 0, "contracts": []}
    if yf_success:
        try:
            from data_providers import _record_provider_call
            _record_provider_call("yfinance", True)
        except Exception:
            pass
    else:
        try:
            from data_providers import _record_provider_call
            _record_provider_call("yfinance", False)
        except Exception:
            pass
    yf_data["spot"]

    # Open universe (2026-09-03): every ticker attempts the Databento OI
    # overlay via the generic OPRA parent fallback — no PAID_TICKERS gate.
    # Misses fall through to yfinance-only below (unchanged).
    dbn_oi = {}
    dbn_success = False
    try:
        dbn_oi = await fetch_oi_for_ticker(ticker)
        if dbn_oi:
            dbn_success = True
    except Exception as e:
        log.warning(f"databento OI lookup fail {ticker}: {e}")
    try:
        from data_providers import _record_provider_call
        _record_provider_call("databento", dbn_success)
    except Exception:
        pass

    if not dbn_oi:
        for c in yf_data["contracts"]:
            c["oi_source"] = "yfinance"
        return {**yf_data, "data_source": "yfinance"}

    # Build (strike, expiry, type) -> OI map from Databento
    dbn_map: dict[tuple, int] = {}
    for _sym, c in dbn_oi.items():
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
    today = datetime.now(UTC).date()
    iv_lists: dict[str, list] = {}
    for c in yf_data["contracts"]:
        iv = c.get("iv")
        if iv is not None and iv == iv:  # skip None and NaN
            iv_lists.setdefault(c["expiry"], []).append(iv)
    iv_avg_by_expiry: dict[str, float] = {e: (sum(vs) / len(vs)) for e, vs in iv_lists.items() if vs}

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


async def tap_counts(ticker: str, strikes: list[float], days: int = 5) -> dict[float, int]:
    """Count how many days price crossed each strike in last N trading days using Polygon aggs."""
    if not POLYGON_API_KEY or not strikes:
        return {s: 0 for s in strikes}
    end = datetime.now(UTC).date()
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
            lo = bar.get("l", 0)
            hi = bar.get("h", 0)
            for s in strikes:
                if lo <= s <= hi:
                    out[s] += 1
    except Exception as e:
        log.warning(f"tap_counts fail {ticker}: {e}")
    return out


# ----------------------------- Snapshot persistence (velocity/rolling) --------

TRINITY = ["^SPX", "SPY", "QQQ"]
DEFAULT_TICKERS = ["SPY", "QQQ", "^SPX", "IWM", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "GOOGL", "AMD", "KO", "XOM", "GM", "MCD", "^VIX"]

# Full-listed-universe cache for /api/tickers/all (T2). Finnhub US symbols,
# refreshed at most every 30 min; the frontend pages through it.
_TICKER_CACHE: list[str] | None = None
_TICKER_CACHE_TS: float | None = None
CACHE_TTL_S = 1800  # 30 minutes
POPULAR_UNIVERSE = [
    # Mega Cap Tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "AVGO", "NFLX",
    "CRM", "INTC", "ORCL", "TXN", "ADBE", "SNAP", "PANW", "TEAM", "DOCU", "NOW",
    # Growth & AI
    "SMCI", "MU", "PLTR", "COIN", "MARA", "RIVN", "LCID", "HOOD", "SOFI", "UPWK",
    "SQ", "PINS", "SHOP", "TWLO", "DDOG", "OKTA", "PSTG", "NET", "PATH", "VEEV",
    # Financials & Industrials
    "JPM", "GS", "MS", "WFC", "BAC", "C", "BLK", "SPGI", "BA", "LMT", "UNP", "UPS", "FDX",
    # Energy & Materials
    "XOM", "CVX", "COP", "SLB", "VLO", "MPC", "PSX", "APD", "NCLH", "GM", "F", "T",
    # Consumer Staples
    "KO", "PEP", "MCD", "WMT", "COST", "BABA", "MRNA", "BIDU", "JD", "PDD"
]

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


_movers_cache: dict[str, Any] = {"ts": 0, "data": []}


def _fetch_movers_sync() -> list[dict[str, Any]]:
    """Use yfinance bulk download for prev-day movers (fast, no rate limit)."""
    try:
        df = yf.download(POPULAR_UNIVERSE, period="2d", interval="1d",
                         group_by="ticker", progress=False, threads=True, auto_adjust=False)
    except Exception as e:
        log.warning(f"yfinance movers fail: {e}")
        return []
    out: list[dict[str, Any]] = []
    for sym in POPULAR_UNIVERSE:
        try:
            sub = df[sym].dropna()
            if len(sub) < 2:
                continue
            prev_close = float(sub["Close"].iloc[-2])
            last_close = float(sub["Close"].iloc[-1])
            day_open = float(sub["Open"].iloc[-1])
            hi = float(sub["High"].iloc[-1])
            lo = float(sub["Low"].iloc[-1])
            vol = float(sub["Volume"].iloc[-1])
            pct = ((last_close - prev_close) / prev_close * 100) if prev_close else 0
            out.append({"ticker": sym, "open": day_open, "close": last_close, "pct": round(pct, 2),
                        "volume": vol, "high": hi, "low": lo, "prev_close": prev_close})
        except Exception:
            continue
    return out


def _attach_strike_volumes(
    strikes: list[dict[str, Any]], contracts: list[dict[str, Any]]
) -> None:
    """Roll per-strike traded volume onto heatmap strike rows (in place).

    Engine-agnostic: sums raw contract ``volume``/``vol`` per strike into
    ``total_volume`` (+ ``call_volume``/``put_volume``) so the Profile view
    can render a real volume profile regardless of the Rust-vs-python GEX
    path. Contracts without usable strike/volume are skipped.
    """
    vol_by_strike: dict[float, float] = {}
    call_vol: dict[float, float] = {}
    put_vol: dict[float, float] = {}
    for c in contracts or []:
        try:
            k = float(c.get("strike") or 0)
            v = float(c.get("volume") or c.get("vol") or 0)
        except (TypeError, ValueError):
            continue
        if k <= 0 or v <= 0:
            continue
        vol_by_strike[k] = vol_by_strike.get(k, 0.0) + v
        if str(c.get("type", "")).lower() == "call":
            call_vol[k] = call_vol.get(k, 0.0) + v
        else:
            put_vol[k] = put_vol.get(k, 0.0) + v
    for s in strikes or []:
        sk = s.get("strike")
        s["total_volume"] = vol_by_strike.get(sk, 0.0)
        s["call_volume"] = call_vol.get(sk, 0.0)
        s["put_volume"] = put_vol.get(sk, 0.0)


# ----------------------------- Heatmap Core -----------------------------------

_BUILD_HEATMAP_CACHE: dict[str, Any] = {}
_BUILD_HEATMAP_CACHE_TTL = 60# Stale-while-revalidate: serve stale data immediately (up to STALE_TTL) while a
# single background task refreshes it. Cuts cold /api/data from ~4s to <50ms
# for repeat views. In-flight set provides single-flight per cache key.
_BUILD_HEATMAP_STALE_TTL = 900  # 15 min — max age of stale-serveable data
_BUILD_HEATMAP_INFLIGHT: set[str] = set()


async def _revalidate_heatmap(cache_key: str, ticker: str, max_expiries: int,
                              with_taps: bool, mode: str, dte, scalp: bool,
                              max_strikes: int):
    """Background refresh — never raises to the caller."""
    try:
        fresh = await _build_heatmap_impl(ticker, max_expiries, with_taps, mode, dte, scalp, max_strikes)
        if isinstance(fresh, dict) and not fresh.get("error") and (fresh.get("strikes") or fresh.get("grid")):
            _BUILD_HEATMAP_CACHE[cache_key] = {"ts": time.time(), "data": fresh}
    except Exception as e:
        log.warning(f"swr revalidate failed {cache_key}: {e}")
    finally:
        _BUILD_HEATMAP_INFLIGHT.discard(cache_key)

async def build_heatmap(ticker: str, max_expiries: int = 4, with_taps: bool = True, mode: str = "day", dte: int | None = None, scalp: bool = False, max_strikes: int = 200) -> dict[str, Any]:
    """Build heatmap with OOM protection and index symbol fast path.

    Stale-while-revalidate: if the fresh-TTL cache misses but a stale entry
    (< STALE_TTL) exists, serve it immediately and refresh in the background
    (single-flight per key)."""
    cache_key = f"{ticker}:{max_expiries}:{mode}:{dte}:{scalp}:{with_taps}:{max_strikes}"
    cached = _BUILD_HEATMAP_CACHE.get(cache_key)
    age = (time.time() - cached["ts"]) if cached else None
    if cached is not None and age is not None:
        if age < _BUILD_HEATMAP_CACHE_TTL:
            # Contract: frontend StaleDataBadge reads data.stale_age_s (App.js).
            cached["data"]["stale_age_s"] = round(age, 1)
            return cached["data"]  # fresh
        if (
            age < _BUILD_HEATMAP_STALE_TTL
            and cache_key not in _BUILD_HEATMAP_INFLIGHT
            and isinstance(cached.get("data"), dict)
            and not cached["data"].get("error")
        ):
            _BUILD_HEATMAP_INFLIGHT.add(cache_key)
            asyncio.create_task(_revalidate_heatmap(
                cache_key, ticker, max_expiries, with_taps, mode, dte, scalp, max_strikes,
            ))
            cached["data"]["stale_age_s"] = round(age, 1)
            return cached["data"]  # stale-but-serveable, refresh running
    try:
        return await _build_heatmap_impl(ticker, max_expiries, with_taps, mode, dte, scalp, max_strikes)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"build_heatmap failed for {ticker}: {e}", exc_info=True)
        return {"ticker": ticker, "spot": 0, "expiries_used": [], "strikes": [],
                "grid": {}, "nodes": {}, "patterns": [], "data_source": "error",
                "error": str(e)}


MIN_GRID_STRIKES = 8  # sparse-grid floor: thin names keep a usable grid


def _top_up_strike_set(shown: set, full_ordered: list, min_n: int) -> set:
    """Top a band-filtered strike set back up to `min_n` with the nearest-by-
    distance listed strikes (same ordering the max_strikes cap uses). Returns
    a set of strike values already present in the analytics inputs — callers
    filter their rows by it, so every shown row carries full data. Real rows
    only, never fabricated (H1). `full_ordered` is strike values nearest-first."""
    if len(shown) >= min_n:
        return set(shown)
    kept = set(shown)
    for strike in full_ordered:
        if len(kept) >= min_n:
            break
        kept.add(strike)
    return kept


async def _build_heatmap_impl(ticker: str, max_expiries: int = 4, with_taps: bool = True, mode: str = "day", dte: int | None = None, scalp: bool = False, max_strikes: int = 200) -> dict[str, Any]:
    log.info(f"build_heatmap: {ticker} expiries={max_expiries} mode={mode} max_strikes={max_strikes}")
    # Check cache first
    cache_key = f"{ticker}:{max_expiries}:{mode}:{dte}:{scalp}:{with_taps}:{max_strikes}"
    cached = _BUILD_HEATMAP_CACHE.get(cache_key)
    if cached and (time.time() - cached["ts"]) < _BUILD_HEATMAP_CACHE_TTL:
        # Poison-entry guard: a cached payload from a degraded upstream window
        # (e.g. cvserver 429 partial fill) must not pin zeros for the whole TTL.
        _d = cached["data"]
        if _d.get("spot") and (_d.get("strikes") or _d.get("grid")):
            return _d
        _BUILD_HEATMAP_CACHE.pop(cache_key, None)  # fall through to rebuild

    if mode == "swing":
        max_expiries = max(max_expiries, 8)

    # For large symbols (index options), use screen API to avoid timeout
    # Screen API filters server-side by strike range and OI
    is_index = ticker.startswith("^") or ticker.startswith("I:")
    raw = None  # initialize before cvserver fast-path; falls through to merged fetch
    if is_index and not scalp:
        # PUBLIC-FIRST (2026-09-06, Nav directive: Solstice data is 100%
        # Public; cvserver is strict failover). Try the merged (Public-first)
        # fetch on a short leash first — index option chains may not exist
        # on every venue, in which case we fall through to the cvserver
        # screen path below instead of stalling the desk.
        try:
            raw = await asyncio.wait_for(
                fetch_spot_and_chains_merged(ticker, max_expiries),
                timeout=12.0,
            )
            if raw and raw.get("contracts") and (raw.get("spot") or 0) > 0:
                raw["data_source"] = raw.get("data_source", "public_api")
                log.info(f"build_heatmap: Public-first hit for index {ticker} "
                         f"({len(raw['contracts'])} contracts via {raw['data_source']})")
            else:
                raw = None
        except Exception as e:
            log.info(f"build_heatmap: Public-first miss for index {ticker} ({e}); trying cvserver screen")
            raw = None
    if is_index and not scalp and raw is None:
        # First get spot price from a quick chain fetch (just 1 expiry, minimal fields)
        from services.cvserver_client import CVSERVER_API_KEY, fetch_chain_for_heatmap, fetch_chain_from_cvserver
        if CVSERVER_API_KEY:
            log.info(f"build_heatmap: using screen API for index {ticker}")
            try:
                spot_raw = await asyncio.wait_for(
                    fetch_chain_from_cvserver(ticker, max_expiries=1),
                    timeout=10.0
                )
                spot = (spot_raw.get("spot") or 0) if spot_raw else 0
                if spot > 0:
                    heatmap_data = await fetch_chain_for_heatmap(ticker, spot, max_strikes)
                    if heatmap_data and heatmap_data.get("contracts"):
                        # Fast path supplies contracts only — fall through to the
                        # full GEX computation below instead of returning early.
                        # The previous early return served a payload with no
                        # grid/strikes/nodes/patterns whenever cvserver answered
                        # (CI: test_heatmap_spx_via_spxw failed on missing grid).
                        raw = {
                            "spot": heatmap_data["spot"],
                            "contracts": heatmap_data["contracts"],
                            "expiries": heatmap_data["expiries"],
                            "data_source": "cvserver",
                        }
                        log.info(f"build_heatmap: screen API contracts for {ticker} ({len(raw['contracts'])}), computing GEX")
                    else:
                        raw = None
                else:
                    raw = None
            except TimeoutError:
                log.warning(f"cvserver timeout for index {ticker}, falling back to yfinance")
                raw = None
            except Exception as e:
                log.warning(f"cvserver failed for index {ticker}: {e}")
                raw = None
        else:
            raw = None

    if raw is None:
        try:
            raw = await fetch_spot_and_chains_merged(ticker, max_expiries)
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"fetch_spot_and_chains_merged failed for {ticker}: {e}")
            raise HTTPException(404, f"No options data for {ticker}") from e

    # Sparse-chain strategy (Public-first; cvserver strictly budgeted):
    # small caps often return only a handful of strikes per expiry. Deepen
    # with Public (unlimited) first; enrich from cvserver (20/hr cap, 1 call)
    # only if still sparse. Real vendor rows only — never fabricated strikes
    # (H1: test_strike_truth_h1.py bans synthetic row generators on main).
    if max_expiries < 8 and ticker.upper() not in ("^SPX", "^NDX", "^RUT", "^VIX") and raw is not None:
        unique_after = len({c.get("strike") for c in raw.get("contracts", [])})
        if unique_after < 40 and raw.get("spot", 0) > 0:
            log.info(f"build_heatmap: sparse chain ({unique_after} strikes) — re-fetching with 8 expiries")
            try:
                deeper = await asyncio.wait_for(
                    fetch_spot_and_chains_merged(ticker, max_expiries=8),
                    timeout=30.0,
                )
                if deeper and deeper.get("contracts") and deeper.get("spot", 0) > 0:
                    deeper_unique = len({c.get("strike") for c in deeper["contracts"]})
                    if deeper_unique > unique_after:
                        raw = deeper
                        log.info(f"build_heatmap: deepened chain for {ticker} — {deeper_unique} unique strikes (was {unique_after})")
            except Exception as e:
                log.debug(f"build_heatmap: deeper fetch failed for {ticker}: {e}")
    unique_strikes = len({c.get("strike") for c in raw.get("contracts", [])})
    SPARSE_STRIKE_THRESHOLD = 30
    if unique_strikes < SPARSE_STRIKE_THRESHOLD and ticker.upper() not in ("^SPX", "^NDX", "^RUT", "^VIX"):
        from services.cvserver_client import CVSERVER_API_KEY, fetch_chain_from_cvserver
        if CVSERVER_API_KEY and raw.get("spot", 0) > 0:
            log.info(f"build_heatmap: Public chain sparse ({unique_strikes} strikes for {ticker}) — enriching from cvserver full chain")
            try:
                cv_data = await asyncio.wait_for(
                    fetch_chain_from_cvserver(ticker, max_expiries=max_expiries),
                    timeout=15.0,
                )
                if cv_data and cv_data.get("contracts") and cv_data.get("spot", 0) > 0:
                    cv_unique = len({c.get("strike") for c in cv_data["contracts"]})
                    if cv_unique > unique_strikes:
                        raw = {
                            "spot": cv_data["spot"],
                            "contracts": cv_data["contracts"],
                            "expiries": cv_data.get("expiries", raw.get("expiries", [])),
                            "data_source": "cvserver",
                        }
                        log.info(f"build_heatmap: cvserver full-chain enrichment for {ticker} — {len(raw['contracts'])} contracts, {cv_unique} unique strikes")
            except Exception as e:
                log.debug(f"build_heatmap: cvserver enrichment failed for {ticker}: {e}")
    spot = raw["spot"]
    if not spot or spot != spot or not raw["contracts"]:  # spot != spot catches NaN
        raise HTTPException(404, f"No options data for {ticker}")

    # Safety: limit total contracts to prevent OOM
    if len(raw["contracts"]) > 15000:
        sorted_c = sorted(raw["contracts"], key=lambda c: abs((c.get("strike") or 0) - spot))
        raw["contracts"] = sorted_c[:15000]
        raw["expiries"] = sorted({c["expiry"] for c in raw["contracts"]})

    today = datetime.now(UTC).date()

    # Limit strikes to max_strikes unique strikes closest to spot (performance optimization)
    if len(raw["contracts"]) > max_strikes * 2:
        # Get unique strikes, sort by distance from spot
        unique_strikes = sorted(set((c.get("strike") or 0) for c in raw["contracts"]),
                               key=lambda s: abs(s - spot))
        # Keep only max_strikes unique strikes
        kept_strikes = set(unique_strikes[:max_strikes])
        raw["contracts"] = [c for c in raw["contracts"] if (c.get("strike") or 0) in kept_strikes]
        raw["expiries"] = sorted({c["expiry"] for c in raw["contracts"]})

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
        if not strikes and any((c.get("volume") or 0) > 0 for c in raw["contracts"]):
            # Yahoo suppresses OI in certain windows (overnight/throttle) — all OI=0
            # would blank the desk. Volume-weighted GEX keeps it alive; tagged so the
            # UI can show the degraded source honestly.
            from services.gex_core import compute_gex_grid_volume
            strikes = compute_gex_by_strike_volume(spot, raw["contracts"], ticker)
            grid = compute_gex_grid_volume(spot, raw["contracts"], ticker)
            log.warning(f"build_heatmap: OI unavailable for {ticker} — volume-weighted GEX fallback (grid populated)")

    # Band: scalp=±2%, day=±15%, swing=±25%
    # Dynamic band based on price level: wider bands for low-priced stocks
    if scalp:
        band = 0.02
    elif dte == 0:
        # 0DTE auto-tighten: same ±5% focus as scalp-style view without
        # flipping volume-weighting — the expiry IS the trade horizon.
        band = 0.05
    elif mode == "swing":
        band = 0.25
    else:
        base_band = 0.15
        # Widen band for low-priced stocks (under $50)
        if spot < 50:
            band = max(base_band, 0.40)  # At least ±40% for low-priced
        elif spot < 100:
            band = max(base_band, 0.30)  # At least ±30% for mid-priced
        else:
            band = base_band

    # Band + sparse-grid floor. Banding computes SETS (never rebinds the row
    # lists first): rebinding would destroy dropped rows and the floor could
    # never restore them. Floor tops the band set back up to MIN_GRID_STRIKES
    # with the nearest listed strikes (KYTX: band left 3 of 8), then rows are
    # filtered by the topped-up set — every shown row keeps full analytics
    # data. Real rows only, never fabricated (H1).
    band_set = {s["strike"] for s in strikes if abs(s["strike"] - spot) / spot <= band}
    full_ordered = sorted({(c.get("strike") or 0) for c in raw.get("contracts", [])},
                          key=lambda s: abs(s - spot))
    kept = _top_up_strike_set(band_set, full_ordered, MIN_GRID_STRIKES)
    strikes = [s for s in strikes if s["strike"] in kept]
    if not scalp:
        grid["strikes"] = [k for k in grid["strikes"] if k in kept]
        grid["strike_totals"] = [s for s in grid["strike_totals"] if s["strike"] in kept]

    # Tag fresh/tested via tap counts
    tap_map: dict[float, int] = {}
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

    # Per-strike traded volume (2026-09-03): engine-agnostic rollup from the
    # raw contracts so the Profile view can render a real volume profile.
    # Works for every provider (Public/cvserver/yfinance all carry volume)
    # regardless of the Rust-vs-python GEX engine path taken above.
    _attach_strike_volumes(strikes, raw.get("contracts", []))

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
    hedge_impulse = calc_hedge_impulse_curve(spot, raw["contracts"])
    pressure_cloud = calc_pressure_cloud(spot, raw["contracts"], ticker)
    charm_integral = calc_charm_integral(spot, raw["contracts"], ticker)

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
        # Contract fields read by the frontend (App.js / HeatseekerDashboard):
        "stale_age_s": 0.0,
        "data_fallback": False,
        "gex_regime": nodes.get("regime"),
        "data_source": raw.get("data_source", "yfinance"),
        "mode": mode,
        "asof": datetime.now(UTC).isoformat(),
        "fetched_at": raw.get("fetched_at") or datetime.now(UTC).isoformat(),
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
        "hedge_impulse": hedge_impulse,
        "pressure_cloud": pressure_cloud,
        "charm_integral": charm_integral,
    }

    _t = asyncio.create_task(_logged_task(save_snapshot(ticker, payload), f"save_snapshot:{ticker}"))
    _background_tasks.add(_t)
    _t.add_done_callback(_background_tasks.discard)
    sanitized = _sanitize(payload)
    _BUILD_HEATMAP_CACHE[cache_key] = {"ts": time.time(), "data": sanitized}
    if len(_BUILD_HEATMAP_CACHE) > 200:
        oldest = sorted(_BUILD_HEATMAP_CACHE.keys(), key=lambda k: _BUILD_HEATMAP_CACHE[k]["ts"])[:50]
        for k in oldest:
            del _BUILD_HEATMAP_CACHE[k]
    return sanitized


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

@app.api_route("/", methods=["GET", "HEAD"])
async def root_head():
    """Root health probe — responds to HEAD and GET for iframe reachability checks."""
    return {"app": "confluence-decoder", "status": "ok"}

@app.get("/api/")
async def api_root():
    return {"app": "confluence-decoder", "version": "2.0", "ts": datetime.now(UTC).isoformat()}


@app.get("/api/tickers")
async def list_tickers():
    return {
        "trinity": TRINITY,
        "default": DEFAULT_TICKERS,
        "popular": POPULAR_UNIVERSE,
    }


def _get_strategy_recommendation(gf: dict, regime: dict, skew: dict) -> dict[str, Any]:
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


def _get_risk_levels(gf: dict, spot: float) -> dict[str, Any]:
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
    stop_below_put_wall = put_wall - (spot - put_wall) * 0.3 if put_wall and spot > put_wall else None

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


def _get_position_sizing_note(gf: dict, spot: float) -> str:
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
    from datetime import datetime
    trade_data["ts"] = datetime.now(UTC).isoformat()
    result = await db.memory.insert_one(trade_data)
    return str(result.inserted_id)


async def remember_gex_observation(obs_data: dict) -> str:
    """Store a GEX observation in the memory collection."""
    from datetime import datetime
    obs_data["ts"] = datetime.now(UTC).isoformat()
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
    import numpy as np

    from bs_greeks import bs_delta, bs_gamma, bs_vega
    from portfolio import Position

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
        from datetime import date as date_type
        from datetime import datetime
        exp_date = datetime.strptime(opt["expiry"], "%Y-%m-%d").date()
        T = max((exp_date - date_type.today()).days / 365.0, 0.001)
        K = opt["strike"]
        sigma = opt.get("iv") or iv
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


def calc_position_size(account_size: float, risk_per_trade_pct: float,  # noqa: F811
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


# ---------- Scheduled pre-fetch (APScheduler) ----------
_scheduler_started = False
_scheduler_task: asyncio.Task | None = None


async def _warm_default_heatmaps():
    """Fire heatmap builds for default tickers once at startup so the first
    user hit gets SWR-stale data instead of a ~4s cold upstream fetch.
    2026-08-22: pairs with the SWR cache (phase 3) — stale entries serve
    instantly while this populates fresh ones in background."""
    for t in ("SPY", "QQQ", "IWM"):
        try:
            await build_heatmap(t, max_expiries=4, mode="day")
            log.info(f"warm heatmaps {t}: ok")
        except Exception as e:
            log.warning(f"warm heatmaps {t}: {e}")


async def _snapshot_chains():
    """Record a DuckDB chain snapshot per default ticker so the
    heatseeker top-movers/history/latest endpoints have data.
    Calls the insert path directly (no self-HTTP)."""
    from services.heatseeker_snapshots import (
        bulk_insert,
        contracts_to_recordbatch,
        create_snapshot_table,
    )
    conn = duckdb_engine.conn if "duckdb_engine" in globals() else None
    if conn is None:
        try:
            from services.duckdb_engine import db as eng
            conn = eng.conn
        except Exception as e:
            log.warning(f"snapshot: no duckdb conn: {e}")
            return
    create_snapshot_table(conn)
    for t in ("SPY", "QQQ", "IWM"):
        try:
            raw = await fetch_spot_and_chains_merged(t, 4)
            if not raw or raw.get("spot") != raw.get("spot"):
                log.warning(f"chain snapshot {t}: no data")
                continue
            batch = contracts_to_recordbatch(raw)
            n = bulk_insert(conn, batch)
            log.info(f"chain snapshot {t}: {n} rows")
            # Exposure alerts (VEX walls / charm pins vs last grid snapshot).
            # Ported pattern from floww-2 gsd/010 (their repo untouched):
            # scheduled coverage for the big three regardless of heatmap
            # views (the HTTP heatmap route covers viewed tickers). Fail-open.
            try:
                from services import exposure_alerts as _ea
                from services import flow_alerts as _fa
                from services.duckdb_engine import db as _duckdb

                grid = compute_gex_grid(raw.get("spot") or 0,
                                        raw.get("contracts") or [], t)
                _fa.init_flow_alert_tables(_duckdb)
                try:
                    from routes.vpin import snapshot_vpin_state
                    _vpin_state = snapshot_vpin_state(t)
                except Exception:
                    _vpin_state = None
                try:
                    from advanced_analytics import calc_gamma_flip_levels
                    _flip = calc_gamma_flip_levels(
                        float(raw.get("spot") or 0),
                        raw.get("contracts") or [], t).get("gamma_flip")
                except Exception:
                    _flip = None
                try:
                    from services.liquidity_state import feed as _liq_feed
                    from services.liquidity_state import snapshot as _liq_snap
                    _contracts = raw.get("contracts") or []
                    _call_vol = sum(float(c.get("volume") or 0)
                                    for c in _contracts
                                    if str(c.get("type") or "").lower() == "call")
                    _put_vol = sum(float(c.get("volume") or 0)
                                   for c in _contracts
                                   if str(c.get("type") or "").lower() == "put")
                    _liq_feed(t, _call_vol, _put_vol, float(raw.get("spot") or 0))
                    _liq_state = _liq_snap(t)
                except Exception:
                    _liq_state = None
                events = _ea.evaluate_ticker(
                    t,
                    {"vex_grid": grid.get("vex_grid") or {},
                     "charm_grid": grid.get("charm_grid") or {}},
                    float(raw.get("spot") or 0),
                    vpin_state=_vpin_state, flip_level=_flip,
                    liquidity_state=_liq_state)
                if events:
                    kept = _fa.dedup_filter(_duckdb, events)
                    if kept:
                        _fa.persist_alerts(_duckdb, kept)
                        log.info(f"exposure alerts {t}: {len(kept)} events")
            except Exception as e:
                log.warning(f"exposure alert eval {t}: {e}")
        except Exception as e:
            log.warning(f"chain snapshot {t}: {e}")


_last_snapshot_hhmm = ""


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
    Also refreshes live policy from Mongo every 5 min for multi-worker sync."""
    fired_for_date = None
    policy_refresh_counter = 0
    while True:
        try:
            # Refresh live policy from Mongo every ~5 min (multi-worker sync)
            policy_refresh_counter += 1
            if policy_refresh_counter >= 5:
                policy_refresh_counter = 0
                await _load_policy_from_mongo()

            # Update provider health Prometheus gauges from DataProviderMonitor
            try:
                from services.meta_observability import provider_monitor
                provider_monitor.update_prometheus()
            except Exception:
                pass

            try:
                from zoneinfo import ZoneInfo
                et = datetime.now(ZoneInfo("America/New_York"))
            except Exception:
                import time
                is_dst = time.localtime().tm_isdst > 0
                offset = 4 if is_dst else 5
                et = datetime.now(UTC) - timedelta(hours=offset)
            hhmm = et.strftime("%H:%M")
            today_et = et.date().isoformat()
            if hhmm >= PREFETCH_HHMM and fired_for_date != today_et and et.weekday() < 5:
                fired_for_date = today_et
                _t = asyncio.create_task(_logged_task(_prefetch_paid_oi(), "_prefetch_paid_oi"))
                _background_tasks.add(_t)
                _t.add_done_callback(_background_tasks.discard)

            # Periodic DuckDB chain snapshots — feeds heatseeker top-movers /
            # history / latest endpoints (previously nothing wrote to them).
            # 15-min cadence during ET market hours (09:30–16:00, Mon–Fri).
            global _last_snapshot_hhmm
            try:
                # Bucket to quarter-hours so the 60s scheduler loop fires the
                # snapshot at :00/:15/:30/:45 only (comment promised 15-min).
                slot = hhmm[:3] + ("00" if int(hhmm[3:]) < 15 else
                                   "15" if int(hhmm[3:]) < 30 else
                                   "30" if int(hhmm[3:]) < 45 else "45")
                if (
                    et.weekday() < 5
                    and "09:30" <= hhmm <= "16:00"
                    and _last_snapshot_hhmm != today_et + slot
                ):
                    _st = asyncio.create_task(_logged_task(
                        _snapshot_chains(), "_snapshot_chains"))
                    _background_tasks.add(_st)
                    _st.add_done_callback(_background_tasks.discard)
                    _last_snapshot_hhmm = today_et + slot
            except Exception as e:
                log.warning(f"snapshot tick err: {e}")
        except Exception as e:
            log.warning(f"scheduler tick err: {e}")
        await asyncio.sleep(60)


_alert_rules: list[dict[str, Any]] = []
_alert_history: list[dict[str, Any]] = []
_alert_id_seq = itertools.count(1)  # monotonic — never rewinds on delete
_alert_collection: Any = None  # MongoDB alerts collection (lazy-init in on_start)


async def _init_alert_collection():
    """Lazy-init the alerts MongoDB collection. Safe to call multiple times."""
    global _alert_collection
    if _alert_collection is not None:
        return
    try:
        _alert_collection = db["alerts"]
        # Index for ticker lookups
        await _alert_collection.create_index("ticker", name="alerts_ticker_idx", sparse=True)
        await _alert_collection.create_index("created_at", name="alerts_created_at_idx")
        log.info("MongoDB alerts collection initialized")
    except Exception as e:
        log.warning(f"Failed to init MongoDB alerts collection: {e}")


async def _sync_rules_to_mongo():
    """Persist all in-memory alert rules to MongoDB. Idempotent upsert."""
    if _alert_collection is None:
        return
    try:
        for rule in _alert_rules:
            await _alert_collection.update_one(
                {"_id": rule["id"]},
                {"$set": rule},
                upsert=True,
            )
    except Exception as e:
        log.warning(f"Failed to sync alert rules to MongoDB: {e}")


async def _sync_history_to_mongo(trigger: dict[str, Any] | None = None):
    """Persist triggered alert history to MongoDB. If trigger is provided, insert it;
    otherwise sync nothing (used after bulk adds)."""
    if _alert_collection is None:
        return
    try:
        if trigger is not None:
            await _alert_collection.insert_one(trigger)
    except Exception as e:
        log.warning(f"Failed to persist alert history to MongoDB: {e}")


async def _load_rules_from_mongo():
    """Load persisted alert rules from MongoDB into in-memory store on startup."""
    if _alert_collection is None:
        return
    try:
        cursor = _alert_collection.find({"active": True})
        async for doc in cursor:
            doc.pop("_id", None)  # MongoDB _id not needed in memory
            if doc not in _alert_rules:
                _alert_rules.append(doc)
        log.info(f"Loaded {len(_alert_rules)} active alert rules from MongoDB")
    except Exception as e:
        log.warning(f"Failed to load alert rules from MongoDB: {e}")


# ---------------------------------------------------------------------------
# Alert quality + provider health endpoints (Phase 6.3 / 6.1 exposure)
# ---------------------------------------------------------------------------


@app.get("/api/alert-quality")
async def alert_quality():
    """Return per-rule per-tier alert quality scores.

    Aggregates triggered alert history into (rule, tier, count, last_triggered)
    buckets so the UI and backtest gating can see which alerts are actually
    firing vs. sitting dormant.
    """
    from collections import defaultdict
    quality: dict[str, dict[str, Any]] = {}
    tier_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for t in _alert_history[-500:]:
        rule_id = t.get("rule_id") or t.get("id") or "unknown"
        tier = t.get("tier", "unknown")
        key = str(rule_id)
        if key not in quality:
            quality[key] = {
                "rule_id": key,
                "trigger_count": 0,
                "last_triggered": t.get("ts") or t.get("created_at", ""),
                "tiers": {},
            }
        quality[key]["trigger_count"] += 1
        quality[key]["last_triggered"] = max(
            quality[key]["last_triggered"],
            t.get("ts") or t.get("created_at", ""),
        )
        tier_counts[key][tier] += 1
    for k, v in quality.items():
        v["tiers"] = dict(tier_counts[k])
        # Derive tier bucket from counts (bronze/silver/gold)
        c = v["tiers"]
        total = sum(c.values())
        if total >= 10:
            v["tier_bucket"] = "gold"
        elif total >= 3:
            v["tier_bucket"] = "silver"
        elif total >= 1:
            v["tier_bucket"] = "bronze"
        else:
            v["tier_bucket"] = "none"
    return {
        "quality": list(quality.values()),
        "total_triggers": len(_alert_history),
        "active_rules": len([r for r in _alert_rules if r.get("active", True)]),
    }


@app.get("/api/provider-health")
async def provider_health():
    """Return data provider health from the DataProviderMonitor.

    Exposes rolling success rates, window calls, seconds since last success,
    and active alerts per provider. Useful for ops dashboards and the deploy
    runbook's yfinance-429 fallback check.
    """
    try:
        from services.meta_observability import provider_monitor
        health = provider_monitor.get_health()
        # enrich with Prometheus gauge values for convenience
        try:
            from services.observability import (
                provider_success_rate,
            )
            for name, stats in health["providers"].items():
                stats["prometheus_success_rate"] = round(
                    provider_success_rate.labels(provider=name)._value.get() or 0.0, 4
                )
        except Exception:
            pass
        return health
    except Exception as e:
        log.warning(f"provider_health endpoint failed: {e}")
        return {"providers": {}, "error": str(e)}, 503


class AlertRule(BaseModel):
    ticker: str
    alert_type: str  # "gex_cross", "gex_spike", "oi_spike", "iv_spike"
    threshold: float
    direction: str = "above"  # "above" or "below"
    expiry: str | None = None
    strike: float | None = None
    label: str | None = None


@app.post("/api/alerts")
async def create_alert(rule: AlertRule):
    """Create a new GEX alert rule. Persisted to MongoDB for durability across restarts."""
    rule_dict = rule.model_dump()
    # Monotonic id — len(_alert_rules)+1 collided after any delete (deleting the
    # middle rule then creating one reused a live id → wrong-target deletes and
    # double-counted triggers).
    rule_dict["id"] = str(next(_alert_id_seq))
    rule_dict["created_at"] = datetime.now(UTC).isoformat()
    rule_dict["active"] = True
    rule_dict["trigger_count"] = 0
    _alert_rules.append(rule_dict)
    # Persist to MongoDB
    await _sync_rules_to_mongo()
    return {"status": "created", "rule": rule_dict}


@app.get("/api/alerts")
async def list_alerts(ticker: str | None = None, active_only: bool = True):
    """List alert rules + AlphaPod-shape flow alerts.

    Returns BOTH the legacy `rules`/`count` payload (consumed by tests and the
    legacy CRA UI) AND the AlphaPod-shape `alerts`/`page`/`page_size`/`total`
    payload (consumed by the AlphaPod SPA). The AlphaPod alerts list is shaped
    from triggered alert history; when no triggers exist, rules are reshaped
    as placeholders so the UI has something to render.
    """
    rules = _alert_rules
    if ticker:
        rules = [r for r in rules if r["ticker"] == ticker.upper()]
    if active_only:
        rules = [r for r in rules if r.get("active", True)]

    try:
        from routes.alphapod_compat import _shape_alert
        source = list(_alert_history) or list(rules)
        if ticker:
            tu = ticker.upper()
            source = [s for s in source if (s.get("ticker") or "").upper() == tu]
        alpha_alerts = [_shape_alert(s, i) for i, s in enumerate(source)]
    except Exception:
        alpha_alerts = []

    return {
        "rules": rules,
        "count": len(rules),
        "alerts": alpha_alerts,
        "page": 1,
        "page_size": len(alpha_alerts),
        "total": len(alpha_alerts),
    }


@app.delete("/api/alerts/{alert_id}")
async def delete_alert(alert_id: str):
    """Delete an alert rule. Removed from both in-memory store and MongoDB."""
    global _alert_rules
    _alert_rules = [r for r in _alert_rules if r["id"] != alert_id]
    if _alert_collection is not None:
        try:
            await _alert_collection.delete_one({"id": alert_id})
        except Exception as e:
            log.warning(f"Failed to delete alert {alert_id} from MongoDB: {e}")
    return {"status": "deleted"}


@app.get("/api/alerts/types")
async def list_alert_types():
    """List all available alert types.

    Derived from the AlertEngine's own detection methods (single source of
    truth) instead of a hand-maintained list that drifts when alert types
    are added/removed in alert_engine.py.
    """
    from alert_engine import ALERT_TYPE_CATALOG

    alert_types = [
        {"type": t, "priority": p, "description": d}
        for t, p, d in ALERT_TYPE_CATALOG
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
        if rule["direction"] == "above" and value > rule["threshold"] or rule["direction"] == "below" and value < rule["threshold"]:
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
                "triggered_at": datetime.now(UTC).isoformat(),
            }
            triggered.append(trigger)
            rule["trigger_count"] = rule.get("trigger_count", 0) + 1
            _alert_history.append(trigger)
            await _sync_history_to_mongo(trigger)

    return {"triggered": triggered, "spot": spot, "asof": datetime.now(UTC).isoformat()}


@app.get("/api/flow/{ticker}")
async def flow_sse(
    ticker: str,
    max_seconds: int = Query(30, ge=1, le=300),
    enforce_window: bool = Query(True),
):
    """SSE flow endpoint for real-time options flow with paid-ticker and window enforcement."""
    t = ticker.strip().upper()

    # Check paid ticker restriction ("*" in PAID_TICKERS opens all tickers;
    # set via /api/live/policy — open universe 2026-09-03).
    if t not in PAID_TICKERS and "*" not in PAID_TICKERS:
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
            et = datetime.now(UTC) - timedelta(hours=offset)
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
        import asyncio as _asyncio
        import json as _json

        from services.flowseeker import fetch_live_flow
        deadline = datetime.now(UTC).timestamp() + max_seconds
        sent = False
        while datetime.now(UTC).timestamp() < deadline:
            try:
                prints = await fetch_live_flow(ticker=t, limit=20, min_premium=0)
                if prints:
                    msg = _json.dumps({"ticker": t, "prints": prints, "ts": datetime.now(UTC).isoformat()})
                    yield f"event: flow\ndata: {msg}\n\n"
                    sent = True
            except Exception as e:
                msg = _json.dumps({"error": str(e), "ticker": t})
                yield f"event: error\ndata: {msg}\n\n"
                break
            # Send heartbeat to keep connection alive and give test client data
            if not sent:
                msg = _json.dumps({"ticker": t, "heartbeat": True, "ts": datetime.now(UTC).isoformat()})
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
                        "asof": datetime.now(UTC).isoformat(),
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
# INTENTIONAL (P2.5-A, fail-closed default): refuse to start with the
# ["*"] wildcard default in any non-development env.  Hardens against
# ad-hoc env typos (e.g. ENVIRONMENT=Produciton, ENVIRONMENT=qa) where
# the operator intended a real-traffic env but accidentally got the
# dev-only wildcard fallthrough.  Local dev (development env) keeps the
# ["*"] fallthrough per TestLocalDevFallthrough.  Uses the existing
# _env top-of-file resolver (L55-56 chain: ENVIRONMENT > ENV >
# "development").  This replaces the prior `(_is_prod or _is_staging)`
# named-env check which still left ad-hoc envs (qa, preview, demo,
# typo'd "production") silently using the wildcard.
if not _cors_origins_env and _env != "development":
    raise RuntimeError(
        f"CORS_ORIGINS must be set in {_env!r} — refusing to start with "
        f"wildcard. Set CORS_ORIGINS to a comma-separated list of allowed origins."
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
    response.headers["X-Frame-Options"] = "DENY"
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
        # This early-return is OUTER to CORSMiddleware (auth is registered after
        # it), so it bypasses CORS. Echo the headers ourselves — otherwise a
        # cross-origin browser sees an opaque CORS error instead of the 401.
        return JSONResponse(
            status_code=e.status_code,
            content={"detail": e.detail},
            headers={
                "Access-Control-Allow-Origin": _get_cors_origin_for_handlers(),
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
            },
        )
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
                log.critical("DASH_SESSION_TOKEN not set — /dashboard/ is INSECURE")
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
    except Exception as e:
        log.warning(f"server.py: route template extraction raise swallowed (route path preserved): {e}", exc_info=True)

    obs_metrics.api_request_duration_seconds.labels(
        route=route,
        method=request.method,
        status=str(response.status_code),
    ).observe(duration)

    obs_metrics.http_requests_total.labels(
        method=request.method,
        endpoint=route,
        status=str(response.status_code),
    ).inc()

    return response


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics exposition endpoint."""
    from starlette.responses import Response
    return Response(
        content=get_metrics_bytes(),
        media_type=get_metrics_content_type(),
    )


# ── VPIN Auto-Feed Background Service ──────────────────────────────────
# Computes VPIN from yfinance trade data and feeds the ToxicityEnsemble
# so the toxicity gauge shows live data instead of "INACTIVE".

# Tickers to auto-feed (configurable)
_VPIN_AUTOFETCH_TICKERS = ["SPY", "QQQ", "IWM"]  # Re-enabled with 3 tickers
_VPIN_AUTOFETCH_INTERVAL = 300


async def _vpin_autofeed_loop():
    """Background loop: fetch recent trades from yfinance, compute VPIN,
    and feed to the ToxicityEnsemble for each tracked ticker."""
    import yfinance as yf

    from routes.ensemble import _ensembles
    from routes.vpin import _vpin_engines

    log.info(f"VPIN auto-feed: started for {_VPIN_AUTOFETCH_TICKERS}")
    while not _shutdown_event.is_set():
        try:
            for ticker in _VPIN_AUTOFETCH_TICKERS:
                if _shutdown_event.is_set():
                    break
                try:
                    # Small delay between tickers to avoid overwhelming yfinance
                    await asyncio.sleep(0.5)
                    # Get recent 1-min bars from yfinance
                    # Index options (SPX, NDX, RUT) need ^ prefix for yfinance
                    yf_ticker = ticker
                    if yf_ticker.upper() in ("SPX", "SPXW", "NDX", "RUT"):
                        yf_ticker = f"^{yf_ticker}"
                    hist = await asyncio.to_thread(
                        lambda t=yf_ticker: yf.Ticker(t).history(period="1d", interval="1m")
                    )
                    if hist is None or len(hist) < 5:
                        continue

                    # Get or create VPIN engine for this ticker
                    t = ticker.upper()
                    if t not in _vpin_engines:
                        from services.vpin_engine import VpinEngine
                        _vpin_engines[t] = VpinEngine(
                            bucket_size=50000.0, window=50, ticker=t
                        )
                    engine = _vpin_engines[t]

                    # Feed each bar as a trade
                    price_changes = hist["Close"].diff().dropna().values.astype(float)
                    volumes = hist["Volume"].iloc[1:].values.astype(float)
                    sigma = float(np.std(price_changes)) if len(price_changes) > 1 else 0.01

                    for pc, vol in zip(price_changes, volumes, strict=False):
                        if vol > 0 and sigma > 0:
                            engine.update(float(pc), float(vol), sigma, dt=1.0)

                    # Feed current VPIN+QI to ensemble
                    vpin_val = engine.compute_vpin()
                    qi_val = engine._qi_tracker.qi
                    if vpin_val > 0:
                        if t not in _ensembles:
                            from services.ml_ensemble import ToxicityEnsemble
                            _ensembles[t] = ToxicityEnsemble()
                        _ensembles[t].update(vpin_val, qi_val)

                except Exception as e:
                    log.debug(f"VPIN auto-feed: {ticker} error: {e}")
                    continue

        except Exception as e:
            log.warning(f"VPIN auto-feed loop error: {e}")

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(_shutdown_event.wait(), timeout=_VPIN_AUTOFETCH_INTERVAL)  # normal interval timeout, continue loop

    log.info("VPIN auto-feed: shutdown complete")


async def _public_sweep_loop():
    """Background institutional sweep over the paid Public universe.
    (B-REGION — Agent B domain: sweep cadence, slice width, budget behavior.)

    Rotates one public_scanner slice per tick — RTH cadence 45s, off-hours
    600s (FLOWW_PUBLIC_SWEEP_RTH_S / _OFFH_S), slice width
    FLOWW_PUBLIC_SWEEP_SLICE, chain depth FLOWW_PUBLIC_SWEEP_MAX_EXPIRES —
    feeding the SAME baseline + institutional alert pipeline as the HTTP scan
    routes, so alerts fire and persist with no tabs open. Budget-gated inside
    sweep_once (skips cleanly when the paid budget is spent); kill switch
    FLOWW_PUBLIC_SWEEP=0. RTH is 09:30–16:05 ET (options session + close
    auction; pre/post-market burns no paid budget on first boot). Follows the
    _vpin_autofeed_loop conventions (shutdown event + wait_for timeout).
    """
    if os.environ.get("FLOWW_PUBLIC_SWEEP", "1") != "1":
        log.info("public sweep disabled (FLOWW_PUBLIC_SWEEP=0)")
        return
    try:
        rth_s = float(os.environ.get("FLOWW_PUBLIC_SWEEP_RTH_S", "45"))
        off_s = float(os.environ.get("FLOWW_PUBLIC_SWEEP_OFFH_S", "600"))
        sl = int(os.environ.get("FLOWW_PUBLIC_SWEEP_SLICE", "8"))
        mx = int(os.environ.get("FLOWW_PUBLIC_SWEEP_MAX_EXPIRES", "2"))
    except (TypeError, ValueError):
        rth_s, off_s, sl, mx = 45.0, 600.0, 8, 2
    log.info("public sweep loop started (rth=%ss offh=%ss slice=%d expiries=%d)",
             rth_s, off_s, sl, mx)
    # U1 provenance: every future sweep/alert mystery resolves to a process.
    # PID + tree sha are logged once here (fail-open; never blocks startup).
    try:
        import pathlib
        import subprocess

        _root = str(pathlib.Path(__file__).resolve().parent.parent)
        _sha = subprocess.run(
            ["git", "-C", _root, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        _sha = "unknown"
    log.info("public sweep identity: pid=%d tree=%s", os.getpid(), _sha)
    cadence = rth_s
    first_tick = True
    while not _shutdown_event.is_set():
        try:
            try:
                from zoneinfo import ZoneInfo
                et_now = datetime.now(ZoneInfo("America/New_York"))
                mins = et_now.hour * 60 + et_now.minute
                in_rth = et_now.weekday() < 5 and 9 * 60 + 30 <= mins <= 16 * 60 + 5
            except Exception:
                in_rth = True  # unknown TZ: stay fresh rather than stall
            cadence = rth_s if in_rth else off_s
            # Off-hours boot must not burn a paid sweep before anyone is
            # watching: sleep through the first off-hours tick, sweep after.
            if in_rth or not first_tick:
                from services.public_scanner import sweep_once
                await sweep_once(slice_size=sl, max_expiries=mx)
            first_tick = False
        except Exception as e:
            log.warning(f"public sweep loop error: {e}")
            cadence = 60.0
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(_shutdown_event.wait(), timeout=cadence)
    log.info("public sweep: shutdown complete")


@app.on_event("startup")
async def on_start():
    try:
        await db.snapshots.create_index([("ticker", 1), ("ts", -1)])
        cache = init_cache(db)
        await cache.ensure_index()
        await _load_policy_from_mongo()
        await _init_alert_collection()
        await _load_rules_from_mongo()
        log.info("MongoDB connected and indexes created")
    except Exception as e:
        log.warning(f"MongoDB unavailable during startup ({type(e).__name__}): {e}")
        log.warning("Server running in degraded mode — DB-dependent endpoints will fail")
    global _scheduler_started, _scheduler_task
    if not _scheduler_started:
        _scheduler_started = True
        _scheduler_task = asyncio.create_task(_scheduler_loop())
        _background_tasks.add(_scheduler_task)
        _scheduler_task.add_done_callback(_background_tasks.discard)
        log.info(f"scheduler started · prefetch at {PREFETCH_HHMM} ET")
        _wt = asyncio.create_task(_logged_task(_warm_default_heatmaps(), "_warm_default_heatmaps"))
        _background_tasks.add(_wt)
        _wt.add_done_callback(_background_tasks.discard)
    # Start VPIN auto-feed background task for toxicity ensemble
    _t = asyncio.create_task(_logged_task(_vpin_autofeed_loop(), "vpin_autofeed"))
    _background_tasks.add(_t)
    _t.add_done_callback(_background_tasks.discard)
    log.info("VPIN auto-feed started for toxicity ensemble")
    # Start paid-Public institutional sweep (alerts with no tabs open)
    _ps = asyncio.create_task(_logged_task(_public_sweep_loop(), "public_sweep"))
    _background_tasks.add(_ps)
    _ps.add_done_callback(_background_tasks.discard)
    log.info("public sweep loop started")
    log.info("databento cache initialized")


@app.on_event("shutdown")
async def on_stop():
    """Graceful shutdown: signal loops, cancel tracked tasks, close MongoDB."""
    log.info("on_stop: shutdown signal received")
    _shutdown_event.set()

    # Cancel the scheduler task first so it stops queueing new work
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.warning(f"on_stop: scheduler task raised on cancel: {e}")

    # Cancel any remaining tracked background tasks
    pending = [t for t in _background_tasks if not t.done()]
    for t in pending:
        t.cancel()
    if pending:
        # Wait with a short bound so a stuck task can't block shutdown
        await asyncio.wait(pending, timeout=5.0)
        log.info(f"on_stop: cancelled {len(pending)} background task(s)")

    # Finally close MongoDB
    client.close()
    try:
        from services.public_api_adapter import close_broker
        await close_broker()
    except Exception as e:
        log.warning(f"on_stop: Public API client close failed: {e}")

    log.info("on_stop: shutdown complete")


# ============ Health check ============
from routes.health import router as health_router

app.include_router(health_router, tags=["health"])

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

from routes.discord import router as discord_router

app.include_router(discord_router, tags=["discord"])

from routes.analytics import router as analytics_router

app.include_router(analytics_router, prefix="/api", tags=["analytics"])

from routes.briefing import router as briefing_router

app.include_router(briefing_router, prefix="/api", tags=["briefing"])

from routes.morning_briefing_api import router as morning_briefing_router

app.include_router(morning_briefing_router, prefix="/api", tags=["morning-briefing"])

from routes.data_providers import router as data_providers_router

app.include_router(data_providers_router, tags=["data"])

from routes.data_quality_api import router as data_quality_router

app.include_router(data_quality_router, prefix="/api", tags=["data-quality"])

from routes.flashalpha import router as flashalpha_router

app.include_router(flashalpha_router, tags=["flashalpha"])

from routes.gemini import router as gemini_router

app.include_router(gemini_router, tags=["ai"])

# ============ Steal-list top-3 router ============
# Dual-GEX (#1), Wheel income screener (#3), IV-from-mid solver (#5).
# Same routes also live standalone on :8001 via services/steal_three_server.py
# for offline dev / quick iteration; both mount the same APIRouter from
# backend/routes/steal_three.py so :8000 and :8001 stay API-identical.
from routes.steal_three import router as steal_three_router

app.include_router(steal_three_router, tags=["steal-three"])

from routes.gex_analysis import router as gex_analysis_router

app.include_router(gex_analysis_router, tags=["gex-analysis"])

from routes.heatseeker import router as heatseeker_router

app.include_router(heatseeker_router, tags=["heatseeker"])

from routes.heatseeker_snapshots_api import router as heatseeker_snapshots_router

app.include_router(heatseeker_snapshots_router, prefix="/api/heatseeker", tags=["heatseeker-snapshots"])

from routes.public_api import router as public_api_router

app.include_router(public_api_router, tags=["public_api"])

from routes.public_brokerage import router as public_brokerage_router

app.include_router(public_brokerage_router, prefix="/api", tags=["public_brokerage"])

from routes.ml_predict_api import router as ml_predict_router

app.include_router(ml_predict_router, tags=["ml-predict"])

from routes.ml_outcome_api import router as ml_outcome_router

app.include_router(ml_outcome_router, tags=["ml-outcome"])

from routes.predictive import router as predictive_router

app.include_router(predictive_router, tags=["predictive"])

from routes.live_trading import router as live_trading_router

app.include_router(live_trading_router, prefix="/api", tags=["live_trading"])

from routes.llm import router as llm_router

app.include_router(llm_router, prefix="/api", tags=["llm"])

from routes.memory import router as memory_router

app.include_router(memory_router, prefix="/api", tags=["memory"])

# ml_training_router removed 2026-05-25: all 10 routes called functions that
# don't exist anywhere in the backend (train_model_endpoint, predict_endpoint, etc.).
# Zero callers in frontend/scripts/tests verified. Working /api/ml/* routes live
# in routes/ml_api.py and routes/ml_predict_api.py — those stay intact.

from routes.portfolio import router as portfolio_router

app.include_router(portfolio_router, prefix="/api", tags=["portfolio"])

from routes.social_flow import router as social_flow_router

app.include_router(social_flow_router, tags=["social"])

# Wire previously orphaned modules
from routes.alerts import router as alerts_router

app.include_router(alerts_router, tags=["alerts"])

# Preferences & theme sync
from routes.preferences import router as preferences_router

app.include_router(preferences_router, tags=["preferences"])

from routes.market_data import router as market_data_router

app.include_router(market_data_router, prefix="/api", tags=["market_data"])

from routes.ml_api import router as ml_api_router

app.include_router(ml_api_router, tags=["ml_api"])

from routes.ml_dashboard import router as ml_dashboard_router

app.include_router(ml_dashboard_router, tags=["ml-dashboard"])

from routes.backtest import router as backtest_router

app.include_router(backtest_router, tags=["backtest"])

from routes.quant import router as quant_router

app.include_router(quant_router, tags=["quant"])

from routes.quant_full import router as quant_full_router

app.include_router(quant_full_router, tags=["quant"])

from routes.chain import router as chain_router

app.include_router(chain_router, tags=["chain"])

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

# ============ AlphaPod-SPA Compatibility Layer ============
# Provides /api/alpha-flow, /api/flow-digest, /api/deep-dive/{ticker},
# /api/gex/spx, /api/earnings/*, /api/flow-alerts. Mounted last so it cannot
# shadow earlier domain routes.
from routes.alphapod_compat import router as alphapod_compat_router

app.include_router(alphapod_compat_router, tags=["alphapod-compat"])

# ============ AgentField Hub Initialization ============
# NOTE: the import itself must be non-fatal. If the optional `agentfield`
# package (or its deps) isn't installed in this venv, the whole server must
# still boot — the feature simply stays disabled. Guarding only the runtime
# startup (below) is NOT enough; an unguarded top-level import kills boot.
try:
    from services.agentfield_hub import init_hub as _init_agentfield_hub
    _AGENTFIELD_AVAILABLE = True
except Exception as _agentfield_import_err:  # noqa: BLE001 - intentionally broad; optional feature
    _AGENTFIELD_AVAILABLE = False
    log.warning(
        f"AgentField hub import failed (non-fatal, feature disabled): {_agentfield_import_err}"
    )

if _AGENTFIELD_AVAILABLE:
    @app.on_event("startup")
    async def startup_agentfield():
        """Initialize AgentField hub (reasoners, cost tracker, dev_mode)."""
        try:
            await _init_agentfield_hub()
            log.info("AgentField hub initialized (node_id=floww-trading, dev_mode=True)")
        except Exception as e:
            log.warning(f"AgentField hub startup failed (non-fatal): {e}")

    # ============ AgentField REST API Routes ============
    from routes.agentfield_api import router as agentfield_api_router
    app.include_router(agentfield_api_router, prefix="/api", tags=["agentfield"])
else:
    log.warning("AgentField REST routes (/api/agentfield/*) disabled — package unavailable")

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
    except Exception as e:
        log.warning(f"server.py: duckdb_engine.stop() raise swallowed (shutdown continued): {e}", exc_info=True)

# ============ Ingestion Pipeline (Mock Feed for now) ============
import contextlib

from services.ingestion_pipeline import IngestionPipeline
from services.mock_schwab_feed import MockSchwabFeed

_ingestion_pipeline: IngestionPipeline | None = None
_mock_feed: MockSchwabFeed | None = None
_mock_feed_task: asyncio.Task | None = None
_mock_feed_task: asyncio.Task | None = None

@app.on_event("startup")
async def startup_ingestion():
    """Launch ingestion pipeline with mock feed on startup."""
    global _ingestion_pipeline, _mock_feed, _mock_feed_task
    try:
        _ingestion_pipeline = IngestionPipeline(
            db=duckdb_engine,
            max_queue_size=10000,
            flush_interval_ms=50.0,
        )
        await _ingestion_pipeline.start()

        # Synthetic dev tick generator. Live market data comes from the
        # Public.com API (fetch_spot_and_chains_merged → public_api_adapter);
        # Schwab is retired (2026-09-03) and this feed is never a live source.
        _mock_feed = MockSchwabFeed(rate=100.0, symbols=["SPY", "QQQ"], seed=42)
        _mock_feed.on_tick(_ingestion_pipeline.enqueue_tick)
        _mock_feed.on_chain(_ingestion_pipeline.enqueue_chain)
        _mock_feed.on_lob(_ingestion_pipeline.enqueue_lob)
        _mock_feed.on_lob_depth(_ingestion_pipeline.enqueue_lob_depth)

        # Run mock feed in background with tracked task
        _mock_feed_task = asyncio.create_task(_mock_feed.start())
        _background_tasks.add(_mock_feed_task)
        _mock_feed_task.add_done_callback(_background_tasks.discard)
        log.info("Ingestion pipeline + mock feed started")
    except Exception as e:
        log.warning(f"Ingestion startup failed (non-fatal): {e}")

@app.on_event("shutdown")
async def shutdown_ingestion() -> None:
    """Drain queue and stop ingestion on shutdown."""
    global _ingestion_pipeline, _mock_feed, _mock_feed_task
    try:
        if _mock_feed_task and not _mock_feed_task.done():
            _mock_feed_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await _mock_feed_task
        if _mock_feed:
            await _mock_feed.stop()
        if _ingestion_pipeline:
            await _ingestion_pipeline.stop()
        log.info("Ingestion pipeline stopped")
    except Exception as e:
        log.warning(f"Ingestion shutdown error: {e}")

# ============ Paper Trading Engine ============
from routes.paper_trading import set_paper_engine as _set_paper_engine
from services.paper_trading import PaperTradingEngine

_paper_engine: PaperTradingEngine | None = None

@app.on_event("startup")
async def startup_paper_trading() -> None:
    """Initialize paper trading engine on startup."""
    global _paper_engine
    try:
        # Close-out sync: when a symbol's paper position nets to flat,
        # auto-close its open Flowseeker journal cards with the realized
        # exit. File-backed store; failures are logged, never fatal.
        def _journal_closeout(symbol: str, exit_price: float) -> None:
            from datetime import date

            from services.journal_store import close_open_by_symbol, get_engine
            closed = close_open_by_symbol(get_engine(), symbol,
                                          exit_price=float(exit_price),
                                          exit_date=date.today().isoformat())
            if closed:
                log.info("Journal close-out: %d card(s) closed for %s @ %s",
                         closed, symbol, exit_price)

        _paper_engine = PaperTradingEngine(
            initial_capital=100_000.0,
            max_position_pct=0.10,
            max_delta_exposure=500.0,
            on_position_closed=_journal_closeout,
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
            _data = await websocket.receive_text()
            # Echo back for now (could handle subscription changes)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

# ============ Paper Trading Routes ============
from routes.paper_trading import router as paper_trading_router

app.include_router(paper_trading_router, tags=["paper_trading"])

# Steal-list #6 sidecar — SqueezeMetrics spot-shifted Exposure Profile.
try:
    import routes.exposure_profile as _exp_profile_sidecar
    app.include_router(_exp_profile_sidecar.router)
except Exception as _exp_exc:    # pragma: no cover (defensive)
    log.warning(f"exposure_profile sidecar mount failed (non-fatal): {_exp_exc}")

# (deduped — see L2905 in the Replay, Agent Hub, Nexus block; P1 entry #4 in docs/superpowers/plans/2026-06-20-freebuff-decoder-hardening-60h.md.)
# ============ Dash UI Mount ============
try:
    from services.dash_ui import create_dash_app
    _dash_app = create_dash_app(app, url_base_pathname="/dashboard/")
    if _dash_app:
        log.info("Dash UI mounted at /dashboard/")
except Exception as e:
    log.warning(f"Dash UI mount failed (non-fatal): {e}")
