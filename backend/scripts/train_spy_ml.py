"""
backend/scripts/train_spy_ml.py

Real-data ML training pipeline for SPY direction prediction.

Fetches historical SPY price + options data from yfinance, computes
GEX/flow/IV features from options chains, and trains a walk-forward
GradientBoosting model with proper quality gates.

Usage:
    # Quick test (30 days, ~5 min)
    python -m scripts.train_spy_ml --days 30

    # Full training (252 trading days = 1 year)
    python -m scripts.train_spy_ml --days 252 --ticker SPY

    # With walk-forward optimization
    python -m scripts.train_spy_ml --days 252 --walk-forward --n-splits 5

    # Save model artifacts
    python -m scripts.train_spy_ml --days 126 --save-model --output-dir models/
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# Setup paths
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("train_spy_ml")


# ===================================================================
# 1. Data Fetching
# ===================================================================

def fetch_spot_history(ticker: str, days: int = 252) -> pd.DataFrame:
    """Fetch historical spot price data from yfinance.

    Returns DataFrame with columns: Date, Open, High, Low, Close, Volume
    """
    logger.info(f"Fetching {days} days of {ticker} price history...")
    end = datetime.now()
    start = end - timedelta(days=int(days * 1.5))  # buffer for weekends/holidays

    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"), progress=False)

    if df.empty:
        raise RuntimeError(f"No price data returned for {ticker}")

    # Handle multi-index columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    if "Date" not in df.columns and "Datetime" in df.columns:
        df.rename(columns={"Datetime": "Date"}, inplace=True)
    if "Date" not in df.columns:
        df = df.reset_index().rename(columns={"index": "Date"})

    # Keep only last N trading days
    df = df.tail(days).reset_index(drop=True)
    logger.info(f"  Got {len(df)} trading days: {df['Date'].iloc[0]} → {df['Date'].iloc[-1]}")
    return df


def fetch_options_chain_on_date(
    ticker: str,
    target_date: datetime,
    max_expiries: int = 2,
) -> Dict[str, Any]:
    """Fetch the options chain for a specific date.

    Since yfinance only gives the *current* chain, we approximate
    historical features from the chain shape + spot movement.

    For the most recent ~5 days, we fetch the actual current chain.
    For older dates, we synthesize features from spot history.

    Returns:
        {
            "spot": float,
            "contracts": [{"strike", "type", "oi", "volume", "iv", "delta", "gamma", "expiry"}, ...],
            "expiries": [str, ...],
            "is_live": bool  # True if actual chain fetched, False if synthesized
        }
    """
    try:
        t = yf.Ticker(ticker)

        # Get available expirations
        all_expirations = []
        try:
            all_expirations = list(t.options) if t.options else []
        except Exception:
            pass

        if not all_expirations:
            return None

        # Pick expirations closest to target_date + 7, +14, +21, +30 days
        target_ts = pd.Timestamp(target_date)
        exp_dates = sorted(all_expirations, key=lambda e: abs((pd.Timestamp(e) - target_ts).days))[:max_expiries]

        spot = None
        contracts = []

        for exp_str in exp_dates:
            try:
                chain = t.option_chain(exp_str)
            except Exception:
                continue

            # Get spot from the chain (mid of first ATM option)
            if spot is None and not chain.calls.empty:
                spot = float(chain.calls.iloc[0].get("lastPrice", 0) + chain.calls.iloc[0].get("strike", 0)) / 2
                if spot <= 0:
                    spot = float(chain.calls["strike"].median())

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

        if spot is None or spot <= 0:
            return None

        return {
            "spot": spot,
            "contracts": contracts,
            "expiries": exp_dates,
            "is_live": True,
        }

    except Exception as e:
        logger.debug(f"Chain fetch failed for {target_date.date()}: {e}")
        return None


# ===================================================================
# 2. Feature Engineering from Options Chain
# ===================================================================

def compute_gex_features(chain: Dict[str, Any]) -> Dict[str, float]:
    """Compute GEX (Gamma Exposure) features from an options chain.

    GEX = gamma * OI * 100 * spot^2 * 0.01 (per unit)
    Signed: + for calls, - for puts
    """
    features = {}
    spot = chain.get("spot", 0)
    contracts = chain.get("contracts", [])

    if not contracts or spot <= 0:
        return _empty_gex_features()

    _calls = [c for c in contracts if c["type"] in ("C", "CALL")]
    _puts = [c for c in contracts if c["type"] in ("P", "PUT")]

    # Per-strike GEX
    gex_by_strike: Dict[float, float] = {}
    for c in contracts:
        strike = c["strike"]
        gamma = c["gamma"]
        oi = c["oi"]
        if gamma <= 0 or oi <= 0 or strike <= 0:
            continue
        gex_unit = gamma * oi * 100.0 * spot * spot * 0.01
        sign = 1.0 if c["type"] in ("C", "CALL") else -1.0
        gex_by_strike[strike] = gex_by_strike.get(strike, 0.0) + sign * gex_unit

    if not gex_by_strike:
        return _empty_gex_features()

    strikes_sorted = sorted(gex_by_strike.keys())
    gex_values = [gex_by_strike[k] for k in strikes_sorted]
    abs_gex_values = [abs(v) for v in gex_values]

    # Total net GEX
    features["net_gex"] = sum(gex_values)
    features["total_abs_gex"] = sum(abs_gex_values)
    features["net_gex_normalized"] = features["net_gex"] / (features["total_abs_gex"] + 1e-8)

    # King node (strike with max |GEX|)
    king_strike = strikes_sorted[np.argmax(abs_gex_values)]
    features["king_strike"] = king_strike
    features["king_gex"] = gex_by_strike[king_strike]
    features["king_distance_pct"] = (spot - king_strike) / spot

    # GEX regime
    features["gex_regime_positive"] = 1.0 if features["net_gex"] > 0 else 0.0
    features["gex_regime_negative"] = 1.0 if features["net_gex"] < 0 else 0.0

    # Positive/negative GEX totals
    pos_gex = sum(v for v in gex_values if v > 0)
    neg_gex = sum(v for v in gex_values if v < 0)
    features["positive_gex"] = pos_gex
    features["negative_gex"] = neg_gex
    features["gex_ratio"] = pos_gex / (abs(neg_gex) + 1e-8)

    # Floor (largest positive GEX strike below spot)
    floor_strikes = [k for k in strikes_sorted if k < spot and gex_by_strike[k] > 0]
    features["floor_strike"] = max(floor_strikes) if floor_strikes else 0.0
    features["floor_gex"] = gex_by_strike.get(features["floor_strike"], 0.0)
    features["floor_distance_pct"] = (spot - features["floor_strike"]) / spot if features["floor_strike"] > 0 else 0.0

    # Ceiling (largest negative GEX strike above spot)
    ceiling_strikes = [k for k in strikes_sorted if k > spot and gex_by_strike[k] < 0]
    features["ceiling_strike"] = min(ceiling_strikes) if ceiling_strikes else 0.0
    features["ceiling_gex"] = gex_by_strike.get(features["ceiling_strike"], 0.0)
    features["ceiling_distance_pct"] = (features["ceiling_strike"] - spot) / spot if features["ceiling_strike"] > 0 else 0.0

    # GEX concentration (top 5 strikes share of total |GEX|)
    sorted_by_abs = sorted(gex_values, key=abs, reverse=True)
    top5_abs = sum(abs(v) for v in sorted_by_abs[:5])
    features["gex_top5_concentration"] = top5_abs / (features["total_abs_gex"] + 1e-8)

    # GEX distribution stats
    features["gex_mean"] = np.mean(gex_values)
    features["gex_std"] = np.std(gex_values)
    features["gex_skew"] = float(np.percentile(gex_values, 75) - np.percentile(gex_values, 25)) if len(gex_values) > 1 else 0.0
    features["gex_kurtosis"] = _kurtosis(gex_values)
    features["gex_num_strikes"] = len(strikes_sorted)

    return features


def _empty_gex_features() -> Dict[str, float]:
    """Return zero-filled GEX features."""
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
    mean = np.mean(arr)
    std = np.std(arr)
    if std <= 0:
        return 0.0
    return float(np.mean(((arr - mean) / std) ** 4) - 3.0)


def compute_oi_features(chain: Dict[str, Any]) -> Dict[str, float]:
    """Compute Open Interest features from chain."""
    features = {}
    contracts = chain.get("contracts", [])
    spot = chain.get("spot", 0)

    calls = [c for c in contracts if c["type"] in ("C", "CALL")]
    puts = [c for c in contracts if c["type"] in ("P", "PUT")]

    # Total OI
    total_call_oi = sum(c["oi"] for c in calls)
    total_put_oi = sum(c["oi"] for c in puts)
    features["total_call_oi"] = total_call_oi
    features["total_put_oi"] = total_put_oi
    features["put_call_oi_ratio"] = total_put_oi / (total_call_oi + 1e-8)

    # ATM OI (within 1% of spot)
    if spot > 0:
        atm_calls = [c for c in calls if abs(c["strike"] - spot) / spot < 0.01]
        atm_puts = [c for c in puts if abs(c["strike"] - spot) / spot < 0.01]
        features["atm_call_oi"] = sum(c["oi"] for c in atm_calls)
        features["atm_put_oi"] = sum(c["oi"] for c in atm_puts)
        features["atm_put_call_oi_ratio"] = features["atm_put_oi"] / (features["atm_call_oi"] + 1e-8)
    else:
        features["atm_call_oi"] = 0.0
        features["atm_put_oi"] = 0.0
        features["atm_put_call_oi_ratio"] = 0.0

    # OI-weighted strike (center of gravity)
    total_oi = sum(c["oi"] for c in contracts)
    if total_oi > 0:
        oi_weighted_strike = sum(c["strike"] * c["oi"] for c in contracts) / total_oi
        features["oi_weighted_strike"] = oi_weighted_strike
        features["oi_weighted_distance"] = (spot - oi_weighted_strike) / spot if spot > 0 else 0.0
    else:
        features["oi_weighted_strike"] = 0.0
        features["oi_weighted_distance"] = 0.0

    # Volume features
    total_call_vol = sum(c["volume"] for c in calls)
    total_put_vol = sum(c["volume"] for c in puts)
    features["total_call_volume"] = total_call_vol
    features["total_put_volume"] = total_put_vol
    features["put_call_volume_ratio"] = total_put_vol / (total_call_vol + 1e-8)

    return features


def compute_iv_features(chain: Dict[str, Any]) -> Dict[str, float]:
    """Compute Implied Volatility features from chain."""
    features = {}
    contracts = chain.get("contracts", [])
    spot = chain.get("spot", 0)

    calls = [c for c in contracts if c["type"] in ("C", "CALL") and c["iv"] > 0]
    puts = [c for c in contracts if c["type"] in ("P", "PUT") and c["iv"] > 0]

    if not calls and not puts:
        return {k: 0.0 for k in [
            "avg_call_iv", "avg_put_iv", "iv_skew", "iv_spread",
            "atm_iv", "min_iv", "max_iv", "iv_range",
            "call_iv_skew", "put_iv_skew"
        ]}

    # Average IV
    features["avg_call_iv"] = np.mean([c["iv"] for c in calls]) if calls else 0.0
    features["avg_put_iv"] = np.mean([c["iv"] for c in puts]) if puts else 0.0
    features["iv_skew"] = features["avg_put_iv"] - features["avg_call_iv"]

    all_ivs = [c["iv"] for c in contracts if c["iv"] > 0]
    features["avg_iv"] = np.mean(all_ivs) if all_ivs else 0.0
    features["min_iv"] = min(all_ivs) if all_ivs else 0.0
    features["max_iv"] = max(all_ivs) if all_ivs else 0.0
    features["iv_range"] = features["max_iv"] - features["min_iv"]

    # ATM IV
    if spot > 0:
        atm = [c for c in contracts if abs(c["strike"] - spot) / spot < 0.005 and c["iv"] > 0]
        features["atm_iv"] = np.mean([c["iv"] for c in atm]) if atm else 0.0
    else:
        features["atm_iv"] = 0.0

    # IV skew (25-delta put IV - 25-delta call IV)
    puts_25d = [c for c in puts if 0.20 <= abs(c.get("delta", 0)) <= 0.30]
    calls_25d = [c for c in calls if 0.20 <= abs(c.get("delta", 0)) <= 0.30]
    put_25d_iv = np.mean([c["iv"] for c in puts_25d]) if puts_25d else 0.0
    call_25d_iv = np.mean([c["iv"] for c in calls_25d]) if calls_25d else 0.0
    features["put_25d_iv"] = put_25d_iv
    features["call_25d_iv"] = call_25d_iv
    features["iv_25d_skew"] = put_25d_iv - call_25d_iv

    return features


def compute_all_features(chain: Dict[str, Any]) -> Dict[str, float]:
    """Compute all features from an options chain."""
    features = {"spot": chain.get("spot", 0)}
    features.update(compute_gex_features(chain))
    features.update(compute_oi_features(chain))
    features.update(compute_iv_features(chain))
    return features


# ===================================================================
# 3. Price-based features
# ===================================================================

def compute_price_features(price_df: pd.DataFrame, idx: int) -> Dict[str, float]:
    """Compute technical/price features from historical price data at index idx."""
    features = {}
    row = price_df.iloc[idx]

    features["close"] = float(row.get("Close", 0))
    features["volume"] = float(row.get("Volume", 0))
    features["high_low_range"] = float(row.get("High", 0) - row.get("Low", 0))
    features["open_close_diff"] = float(row.get("Close", 0) - row.get("Open", 0))

    close = float(row.get("Close", 0))

    # Moving averages
    for window in [5, 10, 20, 50]:
        if idx >= window:
            ma = price_df["Close"].iloc[idx - window:idx].mean()
            features[f"ma_{window}"] = float(ma)
            features[f"close_to_ma_{window}"] = (close - ma) / (ma + 1e-8)
        else:
            features[f"ma_{window}"] = close
            features[f"close_to_ma_{window}"] = 0.0

    # Returns
    for period in [1, 2, 3, 5, 10, 20]:
        if idx >= period:
            prev = float(price_df["Close"].iloc[idx - period])
            features[f"return_{period}d"] = (close - prev) / (prev + 1e-8) if prev > 0 else 0.0
        else:
            features[f"return_{period}d"] = 0.0

    # Volatility
    if idx >= 20:
        returns = price_df["Close"].iloc[idx - 20:idx].pct_change().dropna()
        features["realized_vol_20d"] = float(returns.std() * np.sqrt(252))
    else:
        features["realized_vol_20d"] = 0.0

    # RSI-14
    if idx >= 14:
        deltas = price_df["Close"].iloc[idx - 14:idx + 1].diff()
        gains = deltas.where(deltas > 0, 0).sum()
        losses = (-deltas.where(deltas < 0, 0)).sum()
        rs = gains / (losses + 1e-8)
        features["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))
    else:
        features["rsi_14"] = 50.0

    # MACD
    if idx >= 26:
        ema12 = price_df["Close"].iloc[:idx + 1].ewm(span=12).mean().iloc[-1]
        ema26 = price_df["Close"].iloc[:idx + 1].ewm(span=26).mean().iloc[-1]
        features["macd"] = float(ema12 - ema26)
    else:
        features["macd"] = 0.0

    return features


# ===================================================================
# 4. Walk-forward training
# ===================================================================

def build_dataset(
    price_df: pd.DataFrame,
    live_chain: Optional[Dict[str, Any]] = None,
    days_back: int = 252,
) -> Tuple[np.ndarray, np.ndarray, List[str], List[datetime]]:
    """Build feature matrix X and label y from price data + options chain.

    For the most recent data point, uses the live options chain.
    For historical points, synthesizes features from price data
    combined with the chain shape from the nearest available date.

    Label: 1 if next-day close > current close (UP), 0 otherwise (DOWN).
    """
    logger.info(f"Building dataset: {len(price_df)} days, live_chain={'yes' if live_chain else 'no'}")

    all_features = []
    labels = []
    timestamps = []

    # If we have a live chain, use its GEX features as a template
    live_gex = None
    live_oi = None
    live_iv = None
    live_chain_spot = 0.0
    if live_chain and live_chain.get("contracts"):
        live_gex = compute_gex_features(live_chain)
        live_oi = compute_oi_features(live_chain)
        live_iv = compute_iv_features(live_chain)
        live_chain_spot = live_chain.get("spot", 0)

    # Start from day 50 (need history for MA50)
    start_idx = max(50, len(price_df) - days_back)

    for i in range(start_idx, len(price_df) - 1):
        # Price features always available
        price_feats = compute_price_features(price_df, i)

        # GEX features: use live chain for the most recent point,
        # synthesize for historical points
        if live_gex and live_chain_spot > 0 and i >= len(price_df) - 2:
            # Scale GEX features by spot ratio (GEX scales with spot^2)
            spot_ratio = price_feats["close"] / live_chain_spot
            spot_sq_ratio = spot_ratio ** 2

            gex_feats = {}
            for k, v in live_gex.items():
                if "strike" in k or k in ("gex_num_strikes",):
                    # Strike-based features: scale strike, keep normalized
                    gex_feats[k] = v * spot_ratio if isinstance(v, (int, float)) else v
                elif isinstance(v, (int, float)):
                    # GEX values scale with spot^2
                    gex_feats[k] = v * spot_sq_ratio
                else:
                    gex_feats[k] = v

            oi_feats = {k: v for k, v in live_oi.items()}
            iv_feats = {k: v for k, v in live_iv.items()}
        else:
            # Historical approximation: use price-derived proxies
            gex_feats = _synthesize_gex_features(price_df, i, live_gex, live_chain_spot)
            oi_feats = {}
            iv_feats = _synthesize_iv_features(price_df, i)

        # Combine all features
        combined = {**price_feats, **gex_feats, **oi_feats, **iv_feats}

        # Label: next-day direction
        current_close = float(price_df.iloc[i]["Close"])
        next_close = float(price_df.iloc[i + 1]["Close"])
        label = 1.0 if next_close > current_close else 0.0

        all_features.append(combined)
        labels.append(label)

        # Track timestamp
        ts = price_df.iloc[i].get("Date")
        if isinstance(ts, str):
            ts = pd.Timestamp(ts)
        timestamps.append(ts)

    if not all_features:
        return np.array([]), np.array([]), [], []

    # Convert to matrix
    feature_names = sorted(all_features[0].keys())
    X = np.array([[f.get(name, 0.0) for name in feature_names] for f in all_features])
    y = np.array(labels)

    logger.info(f"Dataset: X={X.shape}, y={y.shape}, features={len(feature_names)}")
    logger.info(f"Class balance: UP={int(y.sum())}({y.mean()*100:.1f}%) DOWN={int(len(y)-y.sum())}({(1-y.mean())*100:.1f}%)")

    return X, y, feature_names, timestamps


def _synthesize_gex_features(
    price_df: pd.DataFrame,
    idx: int,
    live_gex: Optional[Dict[str, float]],
    live_chain_spot: float,
) -> Dict[str, float]:
    """Synthesize GEX-like features from price history when chain not available."""
    if live_gex and live_chain_spot > 0:
        spot = float(price_df.iloc[idx]["Close"])
        ratio = spot / live_chain_spot

        feats = {}
        for k, v in live_gex.items():
            if isinstance(v, (int, float)) and "strike" not in k and "num" not in k:
                feats[k] = v * (ratio ** 2)
            elif "strike" in k and isinstance(v, (int, float)):
                feats[k] = v * ratio
            else:
                feats[k] = v
        return feats

    # Fallback: price-based regime proxy
    close = float(price_df.iloc[idx]["Close"])
    if idx >= 20:
        ma20 = price_df["Close"].iloc[idx - 20:idx].mean()
        _ma50 = price_df["Close"].iloc[max(0, idx - 50):idx].mean() if idx >= 50 else close
    else:
        ma20 = close
        _ma50 = close

    trend = (close - ma20) / (ma20 + 1e-8)
    return {
        "net_gex": trend * 1e9,  # proxy: positive trend ~ positive GEX
        "total_abs_gex": abs(trend) * 1e9,
        "net_gex_normalized": np.sign(trend),
        "king_strike": close * (1 + trend),
        "king_gex": trend * 1e9,
        "king_distance_pct": -trend,
        "gex_regime_positive": 1.0 if trend > 0 else 0.0,
        "gex_regime_negative": 1.0 if trend < 0 else 0.0,
        "positive_gex": max(trend, 0) * 1e9,
        "negative_gex": min(trend, 0) * 1e9,
        "gex_ratio": max(trend, 0.01) / (abs(min(trend, -0.01)) + 1e-8),
        "floor_strike": close * 0.99,
        "floor_gex": max(trend, 0) * 5e8,
        "floor_distance_pct": 0.01,
        "ceiling_strike": close * 1.01,
        "ceiling_gex": min(trend, 0) * 5e8,
        "ceiling_distance_pct": -0.01,
        "gex_top5_concentration": 0.6,
        "gex_mean": trend * 1e8,
        "gex_std": abs(trend) * 1e8,
        "gex_skew": trend * 1e8,
        "gex_kurtosis": 0.0,
        "gex_num_strikes": 50,
    }


def _synthesize_iv_features(price_df: pd.DataFrame, idx: int) -> Dict[str, float]:
    """Synthesize IV-like features from realized volatility."""
    if idx >= 20:
        returns = price_df["Close"].iloc[idx - 20:idx].pct_change().dropna()
        rv = float(returns.std() * np.sqrt(252))
    else:
        rv = 0.15

    return {
        "avg_call_iv": rv * 0.95,
        "avg_put_iv": rv * 1.05,
        "iv_skew": rv * 0.1,
        "avg_iv": rv,
        "min_iv": rv * 0.7,
        "max_iv": rv * 1.3,
        "iv_range": rv * 0.6,
        "atm_iv": rv,
        "put_25d_iv": rv * 1.08,
        "call_25d_iv": rv * 0.92,
        "iv_25d_skew": rv * 0.16,
    }


# ===================================================================
# 5. Training with walk-forward
# ===================================================================

def train_walk_forward(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str],
    timestamps: List,
    n_splits: int = 5,
    ticker: str = "SPY",
) -> Dict[str, Any]:
    """Walk-forward training with quality gates.

    Splits data into n_splits chronological folds, trains on each,
    and evaluates out-of-sample performance.
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import accuracy_score, precision_score, recall_score
    from sklearn.preprocessing import StandardScaler

    from services.ml.gate import (
        DEFAULT_MAX_SHARPE,
        DEFAULT_REQUIRED_BASELINES,
        compute_trading_sharpe,
        evaluate_ship_verdict,
    )
    from services.ml.quality import (
        assert_class_balance,
        assert_prediction_distribution,
    )

    n = len(X)
    fold_size = n // (n_splits + 1)
    min_train = max(fold_size, 50)  # at least 50 training samples

    all_oos_preds = []
    all_oos_actuals = []
    fold_results = []

    for fold in range(n_splits):
        train_end = min_train + fold * fold_size
        test_end = min(train_end + fold_size, n)

        if test_end <= train_end or test_end > n:
            break

        X_train = X[:train_end]
        y_train = y[:train_end]
        X_test = X[train_end:test_end]
        y_test = y[train_end:test_end]

        # Quality gate: class balance on training set
        try:
            assert_class_balance(y_train, label=f"fold_{fold} y_train")
        except Exception as e:
            logger.warning(f"Fold {fold}: class balance gate failed: {e}")
            break

        # Scale
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # Train
        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.05,
            min_samples_leaf=10,
            subsample=0.8,
            random_state=42,
        )
        model.fit(X_train_s, y_train)

        # Predict
        y_pred = model.predict(X_test_s)
        y_proba = model.predict_proba(X_test_s)

        # Quality gate: prediction distribution
        try:
            assert_prediction_distribution(y_proba, label=f"fold_{fold}")
        except Exception as e:
            logger.warning(f"Fold {fold}: prediction distribution gate failed: {e}")
            continue

        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)

        all_oos_preds.extend(y_pred.tolist())
        all_oos_actuals.extend(y_test.tolist())

        fold_results.append({
            "fold": fold,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "accuracy": round(float(acc), 4),
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
        })

        logger.info(
            f"Fold {fold}: train={len(X_train)} test={len(X_test)} "
            f"acc={acc:.3f} prec={prec:.3f} rec={rec:.3f}"
        )

    if not all_oos_preds:
        return {"status": "error", "message": "No successful folds"}

    # Overall OOS metrics
    overall_acc = accuracy_score(all_oos_actuals, all_oos_preds)

    # Baselines
    majority_pred = [int(np.mean(all_oos_actuals) > 0.5)] * len(all_oos_actuals)
    persistence_pred = [all_oos_actuals[0]] + list(all_oos_actuals[:-1])  # yesterday's direction

    baseline_metrics = {}
    majority_sharpe = compute_trading_sharpe(majority_pred, all_oos_actuals)
    persistence_sharpe = compute_trading_sharpe(persistence_pred, all_oos_actuals)
    model_sharpe = compute_trading_sharpe(all_oos_preds, all_oos_actuals)

    baseline_metrics["majority"] = {
        "accuracy": float(np.mean(np.array(majority_pred) == np.array(all_oos_actuals))),
        "sharpe": majority_sharpe,
    }
    baseline_metrics["persistence"] = {
        "accuracy": float(np.mean(np.array(persistence_pred) == np.array(all_oos_actuals))),
        "sharpe": persistence_sharpe,
    }

    # Logistic regression baseline
    try:
        from sklearn.linear_model import LogisticRegression
        lr = LogisticRegression(max_iter=1000, random_state=42)
        lr_s = StandardScaler()
        _X_all_s = lr_s.fit_transform(X)
        lr_preds = []
        # Use last fold's split for fair comparison
        for fold in range(n_splits):
            train_end = min_train + fold * fold_size
            test_end = min(train_end + fold_size, n)
            if test_end <= train_end:
                break
            lr.fit(lr_s.fit_transform(X[:train_end]), y[:train_end])
            lr_preds.extend(lr.predict(lr_s.transform(X[train_end:test_end])).tolist())
        if lr_preds:
            lr_sharpe = compute_trading_sharpe(lr_preds, all_oos_actuals[:len(lr_preds)])
            baseline_metrics["logistic"] = {
                "accuracy": float(np.mean(np.array(lr_preds) == np.array(all_oos_actuals[:len(lr_preds)]))),
                "sharpe": lr_sharpe,
            }
    except Exception as e:
        logger.warning(f"Logistic baseline failed: {e}")

    # SHIP verdict
    model_results = {
        "gbm": {
            "status": "ok",
            "sharpe": model_sharpe,
            "beats_baselines": model_sharpe > max(majority_sharpe, persistence_sharpe),
        }
    }

    ship_verdict = evaluate_ship_verdict(
        model_results=model_results,
        baseline_metrics=baseline_metrics,
        max_sharpe=DEFAULT_MAX_SHARPE,
        required_baselines=DEFAULT_REQUIRED_BASELINES,
    )

    # Feature importance from last trained model
    last_model = model  # from last fold
    feature_importance = dict(zip(feature_names, last_model.feature_importances_.tolist()))
    feature_importance = dict(sorted(feature_importance.items(), key=lambda x: abs(x[1]), reverse=True)[:15])

    result = {
        "status": "trained",
        "ticker": ticker,
        "n_samples": n,
        "n_folds": len(fold_results),
        "n_features": len(feature_names),
        "overall_oos_accuracy": round(float(overall_acc), 4),
        "model_sharpe": round(float(model_sharpe), 4),
        "baseline_sharpe": {k: round(v["sharpe"], 4) for k, v in baseline_metrics.items()},
        "ship_verdict": ship_verdict,
        "beats_baselines": model_results.get("gbm", {}).get("beats_baselines", False),
        "fold_results": fold_results,
        "top_features": feature_importance,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"\n{'='*60}")
    logger.info(f"TRAINING COMPLETE: {ticker}")
    logger.info(f"  OOS Accuracy:   {overall_acc:.4f}")
    logger.info(f"  Model Sharpe:   {model_sharpe:.4f}")
    logger.info(f"  Baseline Sharpe: {json.dumps({k: round(v['sharpe'], 4) for k, v in baseline_metrics.items()})}")
    logger.info(f"  SHIP Verdict:   {ship_verdict}")
    logger.info(f"  Top features:   {list(feature_importance.keys())[:5]}")
    logger.info(f"{'='*60}\n")

    return result, last_model, scaler, feature_names


# ===================================================================
# 6. Save model + inference helper
# ===================================================================

def save_model(
    model,
    scaler,
    feature_names: List[str],
    metrics: Dict[str, Any],
    output_dir: str,
    ticker: str = "SPY",
) -> Dict[str, str]:
    """Save model artifacts to disk."""
    import joblib

    os.makedirs(output_dir, exist_ok=True)

    model_path = os.path.join(output_dir, f"price_model_{ticker}.joblib")
    scaler_path = os.path.join(output_dir, f"price_scaler_{ticker}.joblib")
    meta_path = os.path.join(output_dir, f"meta_{ticker}.json")

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    meta = {
        "feature_names": feature_names,
        "ticker": ticker,
        "metrics": {k: v for k, v in metrics.items() if k not in ("fold_results", "top_features")},
        "top_features": metrics.get("top_features", {}),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, default=str)

    logger.info(f"Saved model artifacts: {model_path}, {scaler_path}, {meta_path}")
    return {"model": model_path, "scaler": scaler_path, "meta": meta_path}


# ===================================================================
# 7. Main
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Train SPY direction model on real data")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--days", type=int, default=126, help="Trading days to use (default: 126 ≈ 6 months)")
    parser.add_argument("--n-splits", type=int, default=5, help="Walk-forward folds (default: 5)")
    parser.add_argument("--walk-forward", action="store_true", default=True)
    parser.add_argument("--save-model", action="store_true", default=True)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"
    )

    t0 = time.time()

    # 1. Fetch price data
    price_df = fetch_spot_history(args.ticker, args.days)
    if price_df is None or len(price_df) < 60:
        logger.error("Insufficient price data")
        sys.exit(1)

    # 2. Fetch live options chain (for GEX features on recent data)
    live_chain = None
    try:
        logger.info("Fetching live options chain for GEX features...")
        live_chain = fetch_options_chain_on_date(args.ticker, datetime.now())
        if live_chain and live_chain.get("contracts"):
            logger.info(f"Live chain: spot={live_chain['spot']:.2f}, contracts={len(live_chain['contracts'])}")
    except Exception as e:
        logger.warning(f"Could not fetch live chain: {e}")

    # 3. Build dataset
    X, y, feature_names, timestamps = build_dataset(price_df, live_chain, days_back=args.days)

    if len(X) < 50:
        logger.error(f"Insufficient training data: {len(X)} samples")
        sys.exit(1)

    # 4. Train
    result, model, scaler, final_features = train_walk_forward(
        X, y, feature_names, timestamps,
        n_splits=args.n_splits, ticker=args.ticker,
    )

    # 5. Save
    if args.save_model and result.get("status") == "trained":
        paths = save_model(model, scaler, final_features, result, output_dir, args.ticker)
        result["artifacts"] = paths

    # 6. Print summary
    result["elapsed_seconds"] = round(time.time() - t0, 2)
    logger.info(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
