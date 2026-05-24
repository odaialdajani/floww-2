"""
backend/services/av_adapter.py

Alpha Vantage response normalizer.
Converts AV's JSON payloads → canonical shapes consumed by the analytics layer.
All numeric fields are NaN-guarded per I-8.

Canonical chain shape:
    {
        "spot": {"price": float, "change": float, "change_pct": float, "source": "alphavantage", ...},
        "contracts": [
            {
                "strike": float, "type": "call"|"put", "expiry": str (YYYY-MM-DD),
                "T": float (years), "oi": float, "volume": float,
                "iv": float, "delta": float, "gamma": float, "theta": float,
                "vega": float, "gex": float
            }
        ],
        "asof": str (ISO-8601),
        "data_source": "alphavantage",
        "delay_seconds": 900  # 15 min delay for AV free tier
    }
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Alpha Vantage free tier has a ~15-minute delay on market data
AV_DELAY_SECONDS = 900

# ── NaN guard ─────────────────────────────────────────────────────────

def _safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely coerce a value to float, guarding against None / NaN / Inf.

    Per I-8: any comparison against a feature that may be NaN MUST use
    ``math.isnan(x) or x op limit``, not bare ``x op limit``.
    """
    if v is None:
        return default
    try:
        f = float(v)
    except (ValueError, TypeError):
        return default
    if math.isnan(f) or math.isinf(f):
        logger.debug(f"Coerced NaN/Inf value {v!r} to {default}")
        return default
    return f


def _safe_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    """Safely coerce to int with NaN guard."""
    f = _safe_float(v)
    if f is None:
        return default
    return int(f)


# ── Spot normalizer ───────────────────────────────────────────────────

def normalize_quote(av_quote: dict) -> Optional[dict]:
    """Normalize an Alpha Vantage GLOBAL_QUOTE response to canonical spot shape.

    Expected AV shape (from GLOBAL_QUOTE):
        {"Global Quote": {
            "01. symbol": "...",
            "02. open": "450.00",
            "03. high": "455.00",
            "04. low": "448.00",
            "05. price": "452.10",
            "06. volume": "12345678",
            "07. latest trading day": "2024-01-15",
            "08. previous close": "450.00",
            "09. change": "2.10",
            "10. change percent": "0.4667%"
        }}

    Returns None if required fields are missing or NaN.
    """
    if not av_quote or "Global Quote" not in av_quote:
        return None

    q = av_quote["Global Quote"]
    if not isinstance(q, dict):
        return None

    price = _safe_float(q.get("05. price"))
    if price is None or price <= 0:
        logger.warning("AV quote missing valid price")
        return None

    prev_close = _safe_float(q.get("08. previous close"))
    change = _safe_float(q.get("09. change"))
    change_pct_str = q.get("10. change percent", "")

    change_pct = None
    if change_pct_str and isinstance(change_pct_str, str):
        try:
            change_pct = float(change_pct_str.replace("%", ""))
        except (ValueError, TypeError):
            pass
    if change_pct is None:
        # Fall back to computed value
        if prev_close and prev_close > 0:
            change_pct = round(((price - prev_close) / prev_close) * 100, 4)

    return {
        "price": price,
        "open": _safe_float(q.get("02. open")),
        "high": _safe_float(q.get("03. high")),
        "low": _safe_float(q.get("04. low")),
        "volume": _safe_int(q.get("06. volume")),
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "latest_trading_day": q.get("07. latest trading day", ""),
        "source": "alphavantage",
    }


# ── Options chain normalizer ──────────────────────────────────────────

def normalize_options_chain(
    av_response: dict,
    spot_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Normalize an Alpha Vantage REALTIME_OPTIONS response to canonical chain shape.

    AV REALTIME_OPTIONS shape:
        {
            "endpoint": "REALTIME_OPTIONS",
            "symbol": "SPY",
            "data": [
                {
                    "contractID": "SPY240119C00450000",
                    "symbol": "SPY  240119C00450000",
                    "type": "call",
                    "strike": 450.0,
                    "expiration": "2024-01-19",
                    "bid": 3.45,
                    "ask": 3.50,
                    "last": 3.48,
                    "volume": 1234,
                    "open_interest": 56789,
                    "implied_volatility": 0.185,
                    "delta": 0.55,
                    "gamma": 0.012,
                    "theta": -0.08,
                    "vega": 0.15,
                }
            ]
        }

    Returns canonical shape with NaN-guarded fields.
    If AV data is empty/unavailable, returns shape with empty contracts list.
    """
    if not av_response:
        return _empty_chain(spot_price, "No AV response")

    data = av_response.get("data") or av_response.get("contracts") or []
    if not isinstance(data, list):
        return _empty_chain(spot_price, "AV response has no data array")

    contracts: List[Dict[str, Any]] = []
    bad_contracts = 0

    for raw in data:
        if not isinstance(raw, dict):
            continue

        strike = _safe_float(raw.get("strike"))
        if strike is None or strike <= 0:
            bad_contracts += 1
            continue

        expiry = raw.get("expiration") or raw.get("expiry") or ""
        if not expiry:
            bad_contracts += 1
            continue

        ctype = raw.get("type", "").strip().lower()
        if ctype not in ("call", "put"):
            bad_contracts += 1
            continue

        iv = _safe_float(raw.get("implied_volatility") or raw.get("iv"))
        delta = _safe_float(raw.get("delta"))
        gamma = _safe_float(raw.get("gamma"))
        theta = _safe_float(raw.get("theta"))
        vega = _safe_float(raw.get("vega"))
        oi = _safe_float(raw.get("open_interest") or raw.get("oi"))
        volume = _safe_int(raw.get("volume"))
        bid = _safe_float(raw.get("bid"))
        ask = _safe_float(raw.get("ask"))
        last = _safe_float(raw.get("last"))

        # Compute time-to-expiry in years
        T = _compute_T(expiry)

        # Compute GEX: gamma * spot * oi * 100 (per contract multiplier)
        gex = None
        if gamma is not None and spot_price is not None and oi is not None:
            gex = gamma * spot_price * oi * 100

        contract = {
            "strike": strike,
            "type": ctype,
            "expiry": expiry,
            "T": T,
            "oi": oi,
            "volume": volume,
            "iv": iv,
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "bid": bid,
            "ask": ask,
            "last": last,
            "gex": gex,
        }
        contracts.append(contract)

    if bad_contracts > 0:
        logger.info(f"AV adapter: skipped {bad_contracts} unparseable contracts")

    return {
        "spot": {"price": spot_price, "source": "alphavantage"} if spot_price else None,
        "contracts": contracts,
        "contract_count": len(contracts),
        "asof": datetime.now(timezone.utc).isoformat(),
        "data_source": "alphavantage",
        "delay_seconds": AV_DELAY_SECONDS,
    }


def _compute_T(expiry_str: str) -> Optional[float]:
    """Compute years-to-expiry from an expiry date string (YYYY-MM-DD)."""
    try:
        exp = datetime.strptime(expiry_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = (exp - now).total_seconds()
        if delta <= 0:
            return 0.0
        return round(delta / (365.25 * 86400), 6)
    except (ValueError, TypeError):
        return None


def _empty_chain(spot_price: Optional[float], reason: str) -> Dict[str, Any]:
    """Return an empty canonical chain (no data available)."""
    logger.info(f"AV adapter returning empty chain: {reason}")
    return {
        "spot": {"price": spot_price, "source": "alphavantage"} if spot_price else None,
        "contracts": [],
        "contract_count": 0,
        "asof": datetime.now(timezone.utc).isoformat(),
        "data_source": "alphavantage",
        "delay_seconds": AV_DELAY_SECONDS,
        "_note": reason,
    }


# ── Convenience: fetch + normalize in one call ────────────────────────

async def fetch_and_normalize_chain(
    ticker: str,
    av_provider: Any,
    num_expiries: int = 4,
) -> Dict[str, Any]:
    """Fetch AV data and normalize in one call.

    Alpha Vantage free tier does NOT provide options chain data via API.
    This function fetches spot price from AV and returns an empty chain
    with the spot price for downstream fallback (e.g., yfinance or
    Databento can fill the contracts).

    Args:
        ticker: Stock symbol (e.g. "SPY").
        av_provider: An instance of AlphaVantageProvider with ``get_quote()``.
        num_expiries: Number of expiry months (unused for AV free tier).

    Returns:
        Canonical chain dict with spot price and empty contracts list.
    """
    spot_price = None
    try:
        spot_data = await av_provider.get_quote(ticker)
        if spot_data:
            spot_price = spot_data.get("price")
    except Exception as e:
        logger.warning(f"AV adapter: failed to fetch spot for {ticker}: {e}")

    return normalize_options_chain(av_response=None, spot_price=spot_price)
