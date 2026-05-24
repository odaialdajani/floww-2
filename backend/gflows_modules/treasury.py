"""
Treasury yield curve fetching and tenor matching.
Ported from gflows/modules/calc.py for the Confluence Decoder.

Replaces the hardcoded RISK_FREE_RATE = 0.05 with dynamic,
tenor-matched risk-free rates from FRED or yfinance.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger("treasury")

# Cache TTL: 4 hours (same as gflows)
_CACHE_TTL = 4 * 3600
_cache: Dict[str, any] = {"ts": 0, "data": None}

# Hardcoded neutral upward-sloping curve as last-resort fallback
FALLBACK_YIELD_CURVE = {
    "1mo": 0.025,
    "3mo": 0.028,
    "6mo": 0.030,
    "1yr": 0.032,
    "2yr": 0.035,
    "5yr": 0.038,
    "10yr": 0.040,
}


def _fetch_from_fred() -> Optional[Dict[str, float]]:
    """Fetch treasury yields from FRED API."""
    try:
        import requests
        series = {
            "1mo": "DGS1MO",
            "3mo": "DGS3MO",
            "6mo": "DGS6MO",
            "1yr": "DGS1",
            "2yr": "DGS2",
            "5yr": "DGS5",
            "10yr": "DGS10",
        }
        curve = {}
        for tenor, symbol in series.items():
            url = f"https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": symbol,
                "api_key": "f89a70484b1cf2afbd9f848e139cf8ae",  # FRED test key
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            }
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            observations = data.get("observations", [])
            if observations:
                val = float(observations[0]["value"])
                curve[tenor] = val / 100.0  # convert from % to decimal
        if len(curve) >= 4:
            return curve
    except Exception as e:
        logger.warning(f"FRED treasury fetch failed: {e}")
    return None


def _fetch_from_yfinance() -> Optional[Dict[str, float]]:
    """Fetch treasury yields from yfinance (^IRX, ^FVX, ^TNX)."""
    try:
        import yfinance as yf
        curve = {}
        # ^IRX = 13-week T-bill (proxy for 3mo)
        try:
            irx = yf.Ticker("^IRX")
            curve["3mo"] = float(irx.fast_info.get("lastPrice", 0) or 0) / 100.0
        except Exception:
            pass
        # ^FVX = 5-year T-note
        try:
            fvx = yf.Ticker("^FVX")
            curve["5yr"] = float(fvx.fast_info.get("lastPrice", 0) or 0) / 100.0
        except Exception:
            pass
        # ^TNX = 10-year T-note
        try:
            tnx = yf.Ticker("^TNX")
            curve["10yr"] = float(tnx.fast_info.get("lastPrice", 0) or 0) / 100.0
        except Exception:
            pass

        # Remove any zero values
        curve = {k: v for k, v in curve.items() if v > 0}
        if len(curve) >= 2:
            # Fill 1mo/6mo/1yr/2yr by interpolation
            if "3mo" in curve and "5yr" in curve:
                curve.setdefault("1mo", curve["3mo"] * 0.85)
                curve.setdefault("6mo", curve["3mo"] * 1.15)
                curve.setdefault("1yr", curve["3mo"] * 1.3)
                curve.setdefault("2yr", (curve["3mo"] + curve["5yr"]) / 2)
            return curve
    except Exception as e:
        logger.warning(f"yfinance treasury fetch failed: {e}")
    return None


def fetch_treasury_yield_curve() -> Dict[str, float]:
    """
    Fetch current treasury yield curve with 4-hour caching.

    Strategy:
    1. FRED API (most accurate)
    2. yfinance (^IRX, ^FVX, ^TNX) with interpolation
    3. Hardcoded fallback (neutral upward-sloping curve)

    Returns a dict mapping tenor keys to decimal rates:
        {"1mo": 0.025, "3mo": 0.028, ..., "10yr": 0.040}
    """
    now = time.time()
    if _cache["data"] is not None and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["data"]

    curve = None

    # Try FRED first
    curve = _fetch_from_fred()
    if curve:
        logger.info(f"treasury curve loaded from FRED: {len(curve)} tenors")
        _cache["ts"] = now
        _cache["data"] = curve
        return curve

    # Fall back to yfinance
    curve = _fetch_from_yfinance()
    if curve:
        logger.info(f"treasury curve loaded from yfinance: {len(curve)} tenors")
        _cache["ts"] = now
        _cache["data"] = curve
        return curve

    # Last resort: hardcoded fallback
    logger.warning("treasury curve: using hardcoded fallback")
    _cache["ts"] = now
    _cache["data"] = FALLBACK_YIELD_CURVE
    return FALLBACK_YIELD_CURVE


def get_tenor_matched_rate(
    days_to_expiry: float,
    yield_curve: Optional[Dict[str, float]] = None,
) -> float:
    """
    Map days_to_expiry to the appropriate risk-free rate from the yield curve.

    Tenor matching hierarchy:
        <= 7 days   -> 1mo (or nearest)
        <= 45 days  -> 3mo (or nearest)
        <= 120 days -> 6mo (or nearest)
        <= 270 days -> 1yr (or nearest)
        <= 540 days -> 2yr (or nearest)
        <= 1260 days -> 5yr (or nearest)
        > 1260 days  -> 10yr (or nearest)

    Falls back to 3.0% (0.03) if no yield_curve provided.
    """
    if yield_curve is None:
        yield_curve = fetch_treasury_yield_curve()

    if not yield_curve or not isinstance(yield_curve, dict) or len(yield_curve) == 0:
        return 0.030

    # Determine preferred tenors based on days_to_expiry
    dte = max(days_to_expiry, 0)
    if dte <= 7:
        preferred = ["1mo", "3mo", "6mo", "1yr"]
    elif dte <= 45:
        preferred = ["3mo", "1mo", "6mo", "1yr"]
    elif dte <= 120:
        preferred = ["6mo", "3mo", "1yr", "2yr"]
    elif dte <= 270:
        preferred = ["1yr", "6mo", "2yr", "3mo"]
    elif dte <= 540:
        preferred = ["2yr", "1yr", "5yr", "10yr"]
    elif dte <= 1260:
        preferred = ["5yr", "2yr", "10yr", "1yr"]
    else:
        preferred = ["10yr", "5yr", "2yr", "1yr"]

    # Try preferred tenors in order
    for tenor in preferred:
        if tenor in yield_curve:
            rate = yield_curve[tenor]
            if rate > 0:
                return rate

    # Fallback: return first available rate
    for rate in yield_curve.values():
        if rate > 0:
            return rate

    return 0.030


def get_option_risk_free_rate(
    days_to_expiry: float,
    yield_curve: Optional[Dict[str, float]] = None,
) -> float:
    """
    Convenience wrapper: get the tenor-matched risk-free rate for an option.
    Defaults to 5.0% (0.05) if yield curve is unavailable.
    """
    return get_tenor_matched_rate(days_to_expiry, yield_curve)


def calculate_dte(expiry_str: str) -> int:
    """
    Calculate days to expiry from an expiry date string (YYYY-MM-DD).
    Returns 0 for already-expired options.
    """
    try:
        from datetime import date as date_type
        exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        today = datetime.now(timezone.utc).date()
        return max((exp_date - today).days, 0)
    except Exception:
        return 30  # default fallback


def is_short_dte(expiry_str: str) -> bool:
    """
    Check if this option is 0DTE or 1DTE (short-dated).
    These options should use Volume instead of OI for weighting.
    """
    dte = calculate_dte(expiry_str)
    return dte <= 1
