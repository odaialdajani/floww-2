"""
backend/services/cvserver_client.py

CVForge cvserver HTTP client.
Talks to the remote cvserver MCP endpoint at tap.convexvalue.com.
Used as the primary data source for options chains, replacing yfinance.

Environment variables:
    CVSERVER_URL   — cvserver MCP endpoint (default: https://tap.convexvalue.com/api/data/mcp)
    CVSERVER_API_KEY — Bearer token for cvserver auth

Response format from get_chain:
    {
        "symbol": "SPY",
        "params": ["expiration_date", "strike_price", "contract_type", ...],
        "chain": [
            {
                "expiration": "2026-06-22",
                "strikes": [
                    [strike_price, [call_field_values], [put_field_values]],
                    ...
                ]
            },
            ...
        ],
        "contract_count": 13350,
        "elapsed_ms": 0
    }

Field order in the params array determines the order of values in each strike's
call/put arrays. The first param is always "expiration_date" (redundant with the
expiration key), the second is "strike_price" (redundant with the strike array
element), the third is "contract_type" — so actual per-contract fields start at
index 3.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import time
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)

CVSERVER_URL = os.environ.get(
    "CVSERVER_URL", "https://tap.convexvalue.com/api/data/mcp"
)
CVSERVER_API_KEY = os.environ.get("CVSERVER_API_KEY", "")
CVSERVER_TIMEOUT = float(os.environ.get("CVSERVER_TIMEOUT", "30"))

# Symbol mapping: yfinance-style index symbols to cvserver I: format
_SYMBOL_MAP = {
    "^SPX": "I:SPX",
    "^NDX": "I:NDX",
    "^RUT": "I:RUT",
    "^VIX": "I:VIX",
}

# Field name mapping: cvserver param -> our internal contract field name
# Only map numeric fields here; string fields (expiration_date, contract_type)
# are set directly from the group/structural data
FIELD_MAP = {
    "implied_volatility": "iv",
    "delta": "delta",
    "gamma": "gamma",
    "theta": "theta",
    "vega": "vega",
    "open_interest": "oi",
    "day_volume": "volume",
    "bid": "bid",
    "ask": "ask",
    "midpoint": "midpoint",
    "underlying_price": "underlying_price",
}

# Default fields to request from cvserver.
# cvforge-maximization (2026-06-25): we now also pull cvforge's NATIVE greeks
# (delta/gamma/theta/vega), day_volume, and the underlying day-change fields so
# GEX, marks, and the Trinity header chips can use cvforge data directly instead
# of Black-Scholes re-computation / yfinance / blank fields. Trade-level flow
# (bid/ask/trade_*) is structurally null in this snapshot feed — those stay 0 and
# will be sourced from a future trade-level tape. Each field adds payload/parse cost;
# keep this list to what an actual consumer reads.
DEFAULT_FIELDS = [
    "expiration_date", "strike_price", "contract_type",
    "implied_volatility", "open_interest", "underlying_price",
    "delta", "gamma", "theta", "vega", "day_volume",
    "day_change_percent", "day_previous_close",
]

# In-memory cache: cache_key -> (timestamp, data)
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 60  # seconds — per-symbol chain

# ---- Upstream request budget ---------------------------------------------
# Every ConvexValue call in this process funnels through _cached_call, so this
# is the one place that can hold the whole app inside the plan's hourly quota.
# Before this existed, screen_from_cvserver and fetch_chain_for_heatmap had NO
# cache at all (every request hit upstream), fetch_chain_from_cvserver had a TTL
# but no coalescing (N concurrent cold requests = N upstream calls), and a 429
# was swallowed by a generic `except Exception` — so the app answered a
# rate-limit response by immediately trying again.
#
# Three protections, in order of importance:
#   1. TTL cache on EVERY upstream path (was: only the chain path).
#   2. Per-key coalescing lock — the Heatseeker tab and the Flowseeker scanner
#      asking for the same symbol at the same moment share ONE upstream call
#      instead of racing. This is what stops the two tabs double-pulling.
#   3. 429 cool-down + per-key failure backoff — a rate-limited or failing
#      upstream is left alone, and stale cache is served instead of nothing.
SCREEN_TTL = float(os.environ.get("CVSERVER_SCREEN_TTL", "120"))
HEATMAP_TTL = float(os.environ.get("CVSERVER_HEATMAP_TTL", "120"))
RL_PAUSE = float(os.environ.get("CVSERVER_RL_PAUSE", "600"))      # 429 → pause 10 min
FAIL_BACKOFF = float(os.environ.get("CVSERVER_FAIL_BACKOFF", "90"))  # per-key, escalating
HOURLY_CAP = int(float(os.environ.get("CVSERVER_HOURLY_CAP", "20")))  # plan quota: Public is primary, cvserver is scarce failover

_locks: dict[str, asyncio.Lock] = {}
_fails: dict[str, tuple[float, int]] = {}   # key -> (retry_after_ts, consecutive_failures)
_rl_until: float = 0.0                      # wall-clock; > now means rate-limited
_req_log: list[float] = []                  # upstream call timestamps (rolling hour)


def _note_req() -> None:
    """Record one real upstream call for the req/hr readout."""
    now = time.time()
    _req_log.append(now)
    cutoff = now - 3600
    while _req_log and _req_log[0] < cutoff:
        _req_log.pop(0)


def upstream_requests_last_hour() -> int:
    """Actual ConvexValue calls made in the trailing hour (cache hits excluded)."""
    cutoff = time.time() - 3600
    return sum(1 for t in _req_log if t > cutoff)


def budget_status() -> dict:
    """Observability for the rate-limit dashboard / health endpoint."""
    now = time.time()
    return {
        "upstream_requests_last_hour": upstream_requests_last_hour(),
        "rate_limited": now < _rl_until,
        "cooldown_seconds_remaining": max(0, int(_rl_until - now)),
        "cached_keys": len(_cache),
        "keys_in_backoff": sum(1 for ts, _ in _fails.values() if now < ts),
        "cache_ttls": {
            "chain": CACHE_TTL, "screen": SCREEN_TTL, "heatmap": HEATMAP_TTL,
        },
    }


def _is_rate_limit(exc: BaseException) -> bool:
    """True for an upstream 429 / plan-quota response.

    Checks the structured status code first (httpx.HTTPStatusError carries the
    response); the string match is the fallback for wrapped/RuntimeError cases.
    """
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg or "limit reached" in msg or "rate limit" in msg


async def _cached_call(key: str, ttl: float, fetch) -> dict | None:
    """Run `fetch` at most once per `ttl` per key, coalescing concurrent callers.

    Returns cached data when fresh, stale data when upstream is unavailable, or
    None when there is nothing to serve. Never raises — callers keep their
    existing "None means fall back" contract.
    """
    global _rl_until

    def _stale():
        """Last-known-good data, explicitly flagged.

        Serving stale beats serving nothing while upstream is rate-limited, but
        on a trading surface it must never masquerade as fresh — callers and the
        UI can key off `stale` / `age_seconds` to badge it. Shallow-copied so the
        flag can't leak back into the cached entry.
        """
        hit = _cache.get(key)
        if not hit:
            return None
        ts, data = hit
        if not isinstance(data, dict):
            return data
        return {**data, "stale": True, "age_seconds": int(time.time() - ts)}

    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    if now < _rl_until:
        return _stale()                       # rate-limited: stale beats hammering
    fail = _fails.get(key)
    if fail and now < fail[0]:
        return _stale()                       # backing off this key

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        # A concurrent caller may have filled the cache while we waited — this
        # re-check is what turns N simultaneous requests into 1 upstream call.
        now = time.time()
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        if now < _rl_until:
            return _stale()

        if upstream_requests_last_hour() >= HOURLY_CAP:
            logger.warning(
                "cvserver: hourly cap reached (%d/hr) — serving stale, Public stays primary",
                HOURLY_CAP,
            )
            return _stale()

        _note_req()
        try:
            data = await fetch()
        except Exception as e:
            if _is_rate_limit(e):
                _rl_until = time.time() + RL_PAUSE
                logger.error(
                    "cvserver: RATE LIMITED (429) — pausing upstream calls for %ds. "
                    "%d upstream requests in the last hour.",
                    int(RL_PAUSE), upstream_requests_last_hour(),
                )
            else:
                n = _fails.get(key, (0.0, 0))[1] + 1
                _fails[key] = (time.time() + min(FAIL_BACKOFF * n, 600), n)
                logger.warning("cvserver: %s failed (%s); backing off", key, e)
            return _stale()

        if data is None:
            # Empty-but-successful response: don't cache it, but do back off so a
            # dead symbol can't be re-requested on every poll.
            n = _fails.get(key, (0.0, 0))[1] + 1
            _fails[key] = (time.time() + min(FAIL_BACKOFF * n, 600), n)
            return _stale()

        _cache[key] = (time.time(), data)
        _fails.pop(key, None)
        return data

# Module-level shared HTTP client — avoids creating a new TCP connection per call.
# Initialised lazily on first use; replaced on timeout/error if needed.
_http_client: httpx.Client | None = None


def _get_http_client() -> httpx.Client:
    """Return the module-level shared httpx.Client, creating it if needed."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(
            timeout=CVSERVER_TIMEOUT,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _http_client


async def startup() -> None:
    """Initialise the shared HTTP client. Call from FastAPI startup handler."""
    global _http_client
    _http_client = httpx.Client(
        timeout=CVSERVER_TIMEOUT,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )
    logger.info("cvserver_client: HTTP connection pool initialised")


async def shutdown() -> None:
    """Close the shared HTTP client. Call from FastAPI shutdown handler."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        _http_client.close()
        _http_client = None
    logger.info("cvserver_client: HTTP connection pool closed")


def _cvserver_call(method: str, arguments: dict) -> dict:
    """Synchronous JSON-RPC call to cvserver MCP endpoint (uses shared connection pool)."""
    headers = {
        "Content-Type": "application/json",
    }
    if CVSERVER_API_KEY:
        headers["Authorization"] = f"Bearer {CVSERVER_API_KEY}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": arguments,
    }

    client = _get_http_client()
    resp = client.post(CVSERVER_URL, json=payload, headers=headers)
    resp.raise_for_status()
    result = resp.json()

    if "error" in result:
        raise RuntimeError(f"cvserver error: {result['error']}")

    # Extract text content from MCP response
    content = result.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        import json
        return json.loads(content[0]["text"])

    return result.get("result", {})


async def _cvserver_call_async(method: str, arguments: dict) -> dict:
    """Async wrapper for _cvserver_call (runs sync client in thread pool)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _cvserver_call, method, arguments)


def _parse_chain_response(raw: dict, symbol: str) -> dict:
    """
    Parse cvserver get_chain response into our internal format:
    {
        "ticker": "SPY",
        "spot": 746.93,
        "expiries": ["2026-06-22", ...],
        "contracts": [
            {"expiry": "...", "T": 0.01, "type": "call", "strike": 700.0,
             "iv": 0.18, "delta": 0.42, "gamma": 0.003, ...},
            ...
        ],
        "data_source": "cvserver",
    }
    """
    params = raw.get("params", [])
    chain_data = raw.get("chain", [])

    if not chain_data:
        return {
            "ticker": symbol,
            "spot": 0,
            "expiries": [],
            "contracts": [],
            "data_source": "cvserver",
        }

    # Build field index map: param_name -> index in strike arrays
    field_idx = {p: i for i, p in enumerate(params)}

    contracts = []
    expiries = []
    today = datetime.now(UTC).date()
    spot = 0.0

    for exp_group in chain_data:
        expiration = exp_group.get("expiration", "")
        if not expiration:
            continue
        expiries.append(expiration)

        try:
            exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        T = max((exp_date - today).days, 1) / 365.0

        for strike_entry in exp_group.get("strikes", []):
            if not strike_entry or len(strike_entry) < 3:
                continue

            strike_price = float(strike_entry[0])
            call_values = strike_entry[1] if len(strike_entry) > 1 else []
            put_values = strike_entry[2] if len(strike_entry) > 2 else []

            # Extract underlying_price from first available contract
            if spot == 0.0:
                for vals in (call_values, put_values):
                    idx = field_idx.get("underlying_price")
                    if idx is not None and idx < len(vals) and vals[idx] is not None:
                        with contextlib.suppress(TypeError, ValueError):
                            spot = float(vals[idx])

            # Build contract dicts for call and put
            for kind, vals in [("call", call_values), ("put", put_values)]:
                contract = {
                    "expiry": expiration,
                    "T": T,
                    "type": kind,
                    "strike": strike_price,
                }

                # Map each field
                for param_name, field_name in FIELD_MAP.items():
                    idx = field_idx.get(param_name)
                    if idx is not None and idx < len(vals):
                        val = vals[idx]
                        if val is not None:
                            try:
                                fval = float(val)
                                if math.isnan(fval) or math.isinf(fval):
                                    val = 0.0
                                else:
                                    val = fval
                            except (TypeError, ValueError):
                                val = None
                        contract[field_name] = val

                # Ensure required fields exist
                contract.setdefault("iv", 0.0)
                contract.setdefault("oi", 0.0)
                contract.setdefault("volume", 0.0)
                contract.setdefault("delta", 0.0)
                contract.setdefault("gamma", 0.0)
                contract.setdefault("theta", 0.0)
                contract.setdefault("vega", 0.0)
                contract.setdefault("bid", 0.0)
                contract.setdefault("ask", 0.0)
                contract.setdefault("midpoint", 0.0)

                contracts.append(contract)

    return {
        "ticker": symbol,
        "spot": spot,
        "expiries": sorted(expiries),
        "contracts": contracts,
        "data_source": "cvserver",
    }


async def fetch_chain_from_cvserver(
    symbol: str,
    fields: list[str] | None = None,
    max_expiries: int = 32,
) -> dict | None:
    """
    Fetch options chain from cvserver.
    Returns parsed dict in our internal format, or None on failure.
    """
    if not CVSERVER_API_KEY:
        logger.debug("cvserver: no API key configured, skipping")
        return None

    if fields is None:
        fields = DEFAULT_FIELDS

    cv_symbol = _SYMBOL_MAP.get(symbol.upper(), symbol.upper())
    cache_key = f"cvserver:{symbol}:{max_expiries}"

    async def _fetch() -> dict | None:
        raw = await _cvserver_call_async("tools/call", {
            "name": "get_chain",
            "arguments": {
                "symbol": cv_symbol,
                "params": fields,
            },
        })

        if not raw or not raw.get("chain"):
            logger.warning(f"cvserver: empty chain for {symbol}")
            return None

        # Limit expiries BEFORE parsing to avoid OOM on large chains (e.g. SPX has 32+ expiries)
        chain = raw["chain"]
        if max_expiries and len(chain) > max_expiries:
            chain = sorted(chain, key=lambda g: g.get("expiration", ""))[:max_expiries]
            raw2 = {**raw, "chain": chain}
        else:
            raw2 = raw

        parsed = _parse_chain_response(raw2, cv_symbol)

        if not parsed["contracts"]:
            logger.warning(f"cvserver: no contracts parsed for {symbol}")
            return None

        logger.info(
            f"cvserver: {symbol} → {len(parsed['contracts'])} contracts, "
            f"{len(parsed['expiries'])} expiries, spot={parsed['spot']}"
        )
        return parsed

    return await _cached_call(cache_key, CACHE_TTL, _fetch)


async def screen_from_cvserver(
    columns: list[str],
    filters: list[dict],
    sort: list[dict] | None = None,
    limit: int = 100,
) -> dict | None:
    """
    Run a screen query against cvserver.
    Returns {columns, rows, row_count} or None on failure.
    """
    if not CVSERVER_API_KEY:
        return None

    args: dict = {
        "columns": columns,
        "filters": filters,
        "limit": limit,
    }
    if sort:
        args["sort"] = sort

    # Key on the full query so different screens cache independently, but two
    # callers running the SAME screen (e.g. the scanner's market-wide query
    # polled from two open windows) collapse to one upstream call.
    import hashlib
    import json as _json
    digest = hashlib.sha1(
        _json.dumps(args, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    async def _fetch() -> dict | None:
        raw = await _cvserver_call_async("tools/call", {
            "name": "screen",
            "arguments": args,
        })
        return raw or None

    return await _cached_call(f"cvscreen:{digest}", SCREEN_TTL, _fetch)


def clear_cache() -> None:
    """Clear the cvserver response cache."""
    _cache.clear()


async def fetch_chain_for_heatmap(
    symbol: str,
    spot: float,
    max_strikes: int = 200,
) -> dict | None:
    """
    Fetch options chain optimized for heatmap display.
    Uses screen API with filters to get only near-ATM contracts with OI > 0.
    Much faster than get_chain for large symbols like SPX.
    """
    if not CVSERVER_API_KEY:
        return None

    cv_symbol = _SYMBOL_MAP.get(symbol.upper(), symbol.upper())

    # Filter: near-ATM strikes (within 20% of spot) with OI > 0
    lo_strike = spot * 0.8
    hi_strike = spot * 1.2

    columns = ["strike_price", "expiration_date", "contract_type",
               "implied_volatility", "open_interest", "underlying_price"]

    filters = [
        {"field": "underlying_ticker", "op": "eq", "value": cv_symbol},
        {"field": "strike_price", "op": "gte", "value": lo_strike},
        {"field": "strike_price", "op": "lte", "value": hi_strike},
        {"field": "open_interest", "op": "gt", "value": 0},
    ]

    # Bucket spot to the nearest 10 so ordinary tick-by-tick drift doesn't mint a
    # new cache key every poll — the ±20% strike window absorbs far more than
    # that, and the TTL bounds how stale the window can get.
    spot_bucket = int(round(spot / 10.0) * 10) if spot else 0
    cache_key = f"cvheat:{cv_symbol}:{spot_bucket}:{max_strikes}"

    async def _fetch() -> dict | None:
        raw = await asyncio.wait_for(
            _cvserver_call_async("tools/call", {
                "name": "screen",
                "arguments": {
                    "columns": columns,
                    "filters": filters,
                    "sort": [{"field": "strike_price", "direction": "asc"}],
                    "limit": max_strikes * 4,
                },
            }),
            timeout=15.0
        )
        if not raw:
            return None

        rows = raw.get("rows", [])
        if not rows:
            return None

        col_names = raw.get("columns", columns)
        col_idx = {name: i for i, name in enumerate(col_names)}

        contracts = []
        expiries = []
        spot_price = 0.0
        today = datetime.now(UTC).date()

        for row in rows:
            try:
                strike = float(row[col_idx.get("strike_price", 0)])
                expiry = row[col_idx.get("expiration_date", 1)]
                ctype = row[col_idx.get("contract_type", 2)]
                iv = float(row[col_idx.get("implied_volatility", 3)] or 0)
                oi = float(row[col_idx.get("open_interest", 4)] or 0)
                underlying = float(row[col_idx.get("underlying_price", 5)] or 0)
            except (IndexError, TypeError, ValueError):
                continue

            if not expiry or oi <= 0:
                continue

            if spot_price == 0 and underlying > 0:
                spot_price = underlying

            try:
                exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue

            T = max((exp_date - today).days, 1) / 365.0

            contracts.append({
                "expiry": expiry, "T": T, "type": ctype,
                "strike": strike, "iv": iv, "oi": oi,
                "underlying_price": underlying,
            })
            if expiry not in expiries:
                expiries.append(expiry)

        if not contracts:
            return None

        return {
            "ticker": symbol.upper(),
            "spot": spot_price,
            "expiries": sorted(expiries),
            "contracts": contracts,
            "data_source": "cvserver",
        }

    # Timeouts and upstream errors are handled by _cached_call: it logs, applies
    # the per-key backoff (or the global 429 cool-down) and serves stale data.
    return await _cached_call(cache_key, HEATMAP_TTL, _fetch)
