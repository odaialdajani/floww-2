"""
backend/services/ml_realtime_features.py

Real-time feature computation for ML inference.

Computes features from:
1. Live options chain (GEX, OI, IV) via yfinance
2. Recent price history (technical indicators)
3. Snapshot deltas (OI changes, volume spikes)

This is the production inference feature pipeline that mirrors
the training feature engineering in scripts/train_spy_ml.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger("ml.realtime_features")


# ===================================================================
# Live data fetching
# ===================================================================

def fetch_live_chain(ticker: str, max_expiries: int = 2) -> Optional[Dict[str, Any]]:
    """Fetch current options chain from yfinance.

    Returns normalized chain dict or None on failure.
    """
    try:
        t = yf.Ticker(ticker)
        expirations = list(t.options) if t.options else []
        if not expirations:
            return None

        # Pick nearest expirations (7-30 DTE preferred)
        now = datetime.now()
        target_dtes = [7, 14, 21, 30]
        selected = []
        for target in target_dtes:
            best = min(expirations,
                       key=lambda e: abs((pd.Timestamp(e) - now).days - target))
            if best not in selected:
                selected.append(best)
            if len(selected) >= max_expiries:
                break

        spot = None
        contracts = []
        for exp_str in selected:
            try:
                chain = t.option_chain(exp_str)
            except Exception:
                continue

            if spot is None and not chain.calls.empty:
                mid = (float(chain.calls.iloc[0].get("bid", 0) or 0) +
                       float(chain.calls.iloc[0].get("ask", 0) or 0)) / 2
                strike = float(chain.calls.iloc[0].get("strike", 0) or 0)
                spot = strike + mid if mid > 0 else float(chain.calls["strike"].median())

            for _, row in chain.calls.iterrows():
                contracts.append({
                    "expiry": exp_str,
                    "strike": float(row.get("strike", 0)),
                    "type": "C",
                    "oi": int(row.get("openInterest", 0) or 0),
                    "volume": int(row.get("volume", 0) or 0),
                    "iv": float(row.get("impliedVolatility", 0) or 0),
                    "delta": float(row.get("delta", 0) or 0),
                    "gamma": float(row.get("gamma", 0) or 0),
                    "bid": float(row.get("bid", 0) or 0),
                    "ask": float(row.get("ask", 0) or 0),
                    "last": float(row.get("lastPrice", 0) or 0),
                })

            for _, row in chain.puts.iterrows():
                contracts.append({
                    "expiry": exp_str,
                    "strike": float(row.get("strike", 0)),
                    "type": "P",
                    "oi": int(row.get("openInterest", 0) or 0),
                    "volume": int(row.get("volume", 0) or 0),
                    "iv": float(row.get("impliedVolatility", 0) or 0),
                    "delta": float(row.get("delta", 0) or 0),
                    "gamma": float(row.get("gamma", 0) or 0),
                    "bid": float(row.get("bid", 0) or 0),
                    "ask": float(row.get("ask", 0) or 0),
                    "last": float(row.get("lastPrice", 0) or 0),
                })

        if spot is None or spot <= 0 or not contracts:
            return None

        return {"spot": spot, "contracts": contracts, "expiries": selected}

    except Exception as e:
        logger.warning(f"Live chain fetch failed for {ticker}: {e}")
        return None


def fetch_price_history(ticker: str, days: int = 60) -> Optional[pd.DataFrame]:
    """Fetch recent price history for technical features."""
    try:
        end = datetime.now()
        start = end - timedelta(days=int(days * 1.5))
        df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"), progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        return df.tail(days)
    except Exception as e:
        logger.warning(f"Price history fetch failed: {e}")
        return None


# ===================================================================
# Feature computation (mirrors train_spy_ml.py)
# ===================================================================

def compute_price_features_realtime(price_df: pd.DataFrame) -> Dict[str, float]:
    """Compute technical features from the most recent price data."""
    features = {}
    idx = len(price_df) - 1
    row = price_df.iloc[idx]

    close = float(row.get("Close", 0))
    features["spot"] = close
    features["close"] = close
    features["volume"] = float(row.get("Volume", 0))
    features["high_low_range"] = float(row.get("High", 0) - row.get("Low", 0))
    features["open_close_diff"] = float(row.get("Close", 0) - row.get("Open", 0))

    for window in [5, 10, 20, 50]:
        if idx >= window:
            ma = float(price_df["Close"].iloc[idx - window:idx].mean())
            features[f"ma_{window}"] = ma
            features[f"close_to_ma_{window}"] = (close - ma) / (ma + 1e-8)
        else:
            features[f"ma_{window}"] = close
            features[f"close_to_ma_{window}"] = 0.0

    for period in [1, 2, 3, 5, 10, 20]:
        if idx >= period:
            prev = float(price_df["Close"].iloc[idx - period])
            features[f"return_{period}d"] = (close - prev) / (prev + 1e-8) if prev > 0 else 0.0
        else:
            features[f"return_{period}d"] = 0.0

    if idx >= 20:
        returns = price_df["Close"].iloc[idx - 20:idx].pct_change().dropna()
        features["realized_vol_20d"] = float(returns.std() * np.sqrt(252))
    else:
        features["realized_vol_20d"] = 0.0

    if idx >= 14:
        deltas = price_df["Close"].iloc[idx - 14:idx + 1].diff()
        gains = float(deltas.where(deltas > 0, 0).sum())
        losses = float((-deltas.where(deltas < 0, 0)).sum())
        rs = gains / (losses + 1e-8)
        features["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))
    else:
        features["rsi_14"] = 50.0

    if idx >= 26:
        ema12 = float(price_df["Close"].iloc[:idx + 1].ewm(span=12).mean().iloc[-1])
        ema26 = float(price_df["Close"].iloc[:idx + 1].ewm(span=26).mean().iloc[-1])
        features["macd"] = ema12 - ema26
    else:
        features["macd"] = 0.0

    return features


def compute_gex_features(chain: Dict[str, Any]) -> Dict[str, float]:
    """Compute GEX features from live chain."""
    spot = chain.get("spot", 0)
    contracts = chain.get("contracts", [])
    features = {}

    _calls = [c for c in contracts if c["type"] in ("C", "CALL")]
    _puts = [c for c in contracts if c["type"] in ("P", "PUT")]

    gex_by_strike: Dict[float, float] = {}
    for c in contracts:
        strike, gamma, oi = c["strike"], c["gamma"], c["oi"]
        if gamma <= 0 or oi <= 0 or strike <= 0:
            continue
        gex_unit = gamma * oi * 100.0 * spot * spot * 0.01
        sign = 1.0 if c["type"] in ("C", "CALL") else -1.0
        gex_by_strike[strike] = gex_by_strike.get(strike, 0.0) + sign * gex_unit

    if not gex_by_strike:
        return _empty_gex()

    strikes_sorted = sorted(gex_by_strike.keys())
    gex_values = [gex_by_strike[k] for k in strikes_sorted]
    abs_gex_values = [abs(v) for v in gex_values]

    features["net_gex"] = sum(gex_values)
    features["total_abs_gex"] = sum(abs_gex_values)
    features["net_gex_normalized"] = features["net_gex"] / (features["total_abs_gex"] + 1e-8)

    king_idx = int(np.argmax(abs_gex_values))
    king_strike = strikes_sorted[king_idx]
    features["king_strike"] = king_strike
    features["king_gex"] = gex_by_strike[king_strike]
    features["king_distance_pct"] = (spot - king_strike) / spot

    features["gex_regime_positive"] = 1.0 if features["net_gex"] > 0 else 0.0
    features["gex_regime_negative"] = 1.0 if features["net_gex"] < 0 else 0.0

    pos_gex = sum(v for v in gex_values if v > 0)
    neg_gex = sum(v for v in gex_values if v < 0)
    features["positive_gex"] = pos_gex
    features["negative_gex"] = neg_gex
    features["gex_ratio"] = pos_gex / (abs(neg_gex) + 1e-8)

    floor_s = [k for k in strikes_sorted if k < spot and gex_by_strike[k] > 0]
    features["floor_strike"] = max(floor_s) if floor_s else 0.0
    features["floor_gex"] = gex_by_strike.get(features["floor_strike"], 0.0)
    features["floor_distance_pct"] = (spot - features["floor_strike"]) / spot if features["floor_strike"] > 0 else 0.0

    ceil_s = [k for k in strikes_sorted if k > spot and gex_by_strike[k] < 0]
    features["ceiling_strike"] = min(ceil_s) if ceil_s else 0.0
    features["ceiling_gex"] = gex_by_strike.get(features["ceiling_strike"], 0.0)
    features["ceiling_distance_pct"] = (features["ceiling_strike"] - spot) / spot if features["ceiling_strike"] > 0 else 0.0

    sorted_abs = sorted(gex_values, key=abs, reverse=True)
    features["gex_top5_concentration"] = sum(abs(v) for v in sorted_abs[:5]) / (features["total_abs_gex"] + 1e-8)
    features["gex_mean"] = float(np.mean(gex_values))
    features["gex_std"] = float(np.std(gex_values))
    features["gex_skew"] = float(np.percentile(gex_values, 75) - np.percentile(gex_values, 25)) if len(gex_values) > 1 else 0.0
    features["gex_kurtosis"] = _kurtosis(gex_values)
    features["gex_num_strikes"] = float(len(strikes_sorted))

    return features


def compute_oi_features(chain: Dict[str, Any]) -> Dict[str, float]:
    """Compute OI features from live chain."""
    features = {}
    contracts = chain.get("contracts", [])
    spot = chain.get("spot", 0)
    calls = [c for c in contracts if c["type"] in ("C", "CALL")]
    puts = [c for c in contracts if c["type"] in ("P", "PUT")]

    total_call_oi = sum(c["oi"] for c in calls)
    total_put_oi = sum(c["oi"] for c in puts)
    features["total_call_oi"] = float(total_call_oi)
    features["total_put_oi"] = float(total_put_oi)
    features["put_call_oi_ratio"] = total_put_oi / (total_call_oi + 1e-8)

    if spot > 0:
        atm_c = [c for c in calls if abs(c["strike"] - spot) / spot < 0.01]
        atm_p = [c for c in puts if abs(c["strike"] - spot) / spot < 0.01]
        features["atm_call_oi"] = float(sum(c["oi"] for c in atm_c))
        features["atm_put_oi"] = float(sum(c["oi"] for c in atm_p))
        features["atm_put_call_oi_ratio"] = features["atm_put_oi"] / (features["atm_call_oi"] + 1e-8)
    else:
        features["atm_call_oi"] = 0.0
        features["atm_put_oi"] = 0.0
        features["atm_put_call_oi_ratio"] = 0.0

    total_oi = sum(c["oi"] for c in contracts)
    if total_oi > 0:
        features["oi_weighted_strike"] = sum(c["strike"] * c["oi"] for c in contracts) / total_oi
        features["oi_weighted_distance"] = (spot - features["oi_weighted_strike"]) / spot if spot > 0 else 0.0
    else:
        features["oi_weighted_strike"] = 0.0
        features["oi_weighted_distance"] = 0.0

    features["total_call_volume"] = float(sum(c["volume"] for c in calls))
    features["total_put_volume"] = float(sum(c["volume"] for c in puts))
    features["put_call_volume_ratio"] = sum(c["volume"] for c in puts) / (sum(c["volume"] for c in calls) + 1e-8)

    return features


def compute_iv_features(chain: Dict[str, Any]) -> Dict[str, float]:
    """Compute IV features from live chain."""
    features = {}
    contracts = chain.get("contracts", [])
    spot = chain.get("spot", 0)
    calls = [c for c in contracts if c["type"] in ("C", "CALL") and c["iv"] > 0]
    puts = [c for c in contracts if c["type"] in ("P", "PUT") and c["iv"] > 0]

    if not calls and not puts:
        return {k: 0.0 for k in [
            "avg_call_iv", "avg_put_iv", "iv_skew", "avg_iv",
            "min_iv", "max_iv", "iv_range", "atm_iv",
            "put_25d_iv", "call_25d_iv", "iv_25d_skew",
        ]}

    features["avg_call_iv"] = float(np.mean([c["iv"] for c in calls])) if calls else 0.0
    features["avg_put_iv"] = float(np.mean([c["iv"] for c in puts])) if puts else 0.0
    features["iv_skew"] = features["avg_put_iv"] - features["avg_call_iv"]

    all_ivs = [c["iv"] for c in contracts if c["iv"] > 0]
    features["avg_iv"] = float(np.mean(all_ivs))
    features["min_iv"] = float(min(all_ivs))
    features["max_iv"] = float(max(all_ivs))
    features["iv_range"] = features["max_iv"] - features["min_iv"]

    if spot > 0:
        atm = [c for c in contracts if abs(c["strike"] - spot) / spot < 0.005 and c["iv"] > 0]
        features["atm_iv"] = float(np.mean([c["iv"] for c in atm])) if atm else 0.0
    else:
        features["atm_iv"] = 0.0

    puts_25d = [c for c in puts if 0.20 <= abs(c.get("delta", 0)) <= 0.30]
    calls_25d = [c for c in calls if 0.20 <= abs(c.get("delta", 0)) <= 0.30]
    features["put_25d_iv"] = float(np.mean([c["iv"] for c in puts_25d])) if puts_25d else 0.0
    features["call_25d_iv"] = float(np.mean([c["iv"] for c in calls_25d])) if calls_25d else 0.0
    features["iv_25d_skew"] = features["put_25d_iv"] - features["call_25d_iv"]

    return features


def _empty_gex() -> Dict[str, float]:
    return {
        "net_gex": 0.0, "total_abs_gex": 0.0, "net_gex_normalized": 0.0,
        "king_strike": 0.0, "king_gex": 0.0, "king_distance_pct": 0.0,
        "gex_regime_positive": 0.0, "gex_regime_negative": 0.0,
        "positive_gex": 0.0, "negative_gex": 0.0, "gex_ratio": 0.0,
        "floor_strike": 0.0, "floor_gex": 0.0, "floor_distance_pct": 0.0,
        "ceiling_strike": 0.0, "ceiling_gex": 0.0, "ceiling_distance_pct": 0.0,
        "gex_top5_concentration": 0.0, "gex_mean": 0.0, "gex_std": 0.0,
        "gex_skew": 0.0, "gex_kurtosis": 0.0, "gex_num_strikes": 0.0,
    }


def _kurtosis(values: list) -> float:
    if len(values) < 4:
        return 0.0
    arr = np.array(values, dtype=float)
    mean, std = np.mean(arr), np.std(arr)
    if std <= 0:
        return 0.0
    return float(np.mean(((arr - mean) / std) ** 4) - 3.0)


# ===================================================================
# Full feature vector computation
# ===================================================================

def compute_features_for_inference(
    ticker: str,
    price_days: int = 60,
) -> Optional[Dict[str, Any]]:
    """Compute the full feature vector for ML inference.

    Returns:
        {
            "features": {feature_name: value, ...},
            "feature_names": [ordered list matching model input],
            "chain_available": bool,
            "spot": float,
            "chain_meta": {num_contracts, expiries, ...},
        }
        or None on failure.
    """
    logger.info(f"Computing inference features for {ticker}")

    # 1. Price history
    price_df = fetch_price_history(ticker, price_days)
    if price_df is None or len(price_df) < 30:
        logger.error(f"Insufficient price history for {ticker}")
        return None

    price_feats = compute_price_features_realtime(price_df)

    # 2. Live options chain
    chain = fetch_live_chain(ticker)
    chain_available = chain is not None and bool(chain.get("contracts"))

    if chain_available:
        gex_feats = compute_gex_features(chain)
        oi_feats = compute_oi_features(chain)
        iv_feats = compute_iv_features(chain)
    else:
        logger.warning(f"No live chain for {ticker}, using synthesized GEX features")
        gex_feats = _empty_gex()
        oi_feats = {}
        iv_feats = {}

    # 3. Combine all features
    all_features = {**price_feats, **gex_feats, **oi_feats, **iv_feats}

    return {
        "features": all_features,
        "feature_names": sorted(all_features.keys()),
        "chain_available": chain_available,
        "spot": price_feats["spot"],
        "chain_meta": {
            "num_contracts": len(chain.get("contracts", [])) if chain else 0,
            "expiries": chain.get("expiries", []) if chain else [],
            "net_gex": gex_feats.get("net_gex", 0),
            "gex_regime": "positive" if gex_feats.get("gex_regime_positive", 0) > 0.5 else "negative",
            "king_distance_pct": gex_feats.get("king_distance_pct", 0),
            "iv_skew": iv_feats.get("iv_skew", 0),
            "put_call_oi_ratio": oi_feats.get("put_call_oi_ratio", 0),
            "put_call_volume_ratio": oi_feats.get("put_call_volume_ratio", 0),
        } if chain_available else None,
        "computed_at": datetime.now().isoformat(),
    }


async def compute_features_async(ticker: str, price_days: int = 60) -> Optional[Dict[str, Any]]:
    """Async wrapper that runs yfinance calls in thread pool."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, compute_features_for_inference, ticker, price_days)
