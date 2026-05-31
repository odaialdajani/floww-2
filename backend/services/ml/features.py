"""
backend/services/ml/features.py

Feature engineering on real market data from MongoDB.

Computes ~50 features per ticker per date from:
- GEX snapshots (gex_enhanced_snapshots)
- Outcomes labels (gex_llm_patterns_outcomes)
- Underlying bars (underlying_bars)

All features are computed with strict no-leakage: features at time t only use
data available at or before t.

Feature version: v1.0 (stored alongside every feature row)
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))

log = logging.getLogger("ml.features")

FEATURE_VERSION = "v1.0"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
COLLECTION_FEATURES = "ml_features"


async def load_outcomes(db, ticker: str = "SPY") -> List[Dict]:
    """
    Load labeled outcomes for a ticker, sorted by date.

    SPY outcomes were ingested without a ticker field (issue_145_*); other
    tickers must carry an explicit ticker tag. Returns [] for tickers that
    have no labeled outcomes — callers fall back to bar-derived targets.
    """
    if ticker == "SPY":
        query = {"$or": [
            {"ticker": "SPY"},
            {"_source": "issue_145_next_day_outcomes_2024"},
        ]}
    else:
        query = {"ticker": ticker}
    cursor = db["gex_llm_patterns_outcomes"].find(query).sort("date", 1)
    return await cursor.to_list(length=10000)


# Canonical materialization thresholds (from
# data/github-repos/cloned/iAmGiG_gex-llm-patterns/scripts/validation/paper1/
# 16_analyze_eod_latent_information.py — same definitions used to label SPY).
DIRECTIONAL_MOVE_THRESHOLD = 0.005  # >0.5% abs next-day return
RANGE_EXPANSION_THRESHOLD = 0.015   # >1.5% next-day intraday range
GAP_MOVE_THRESHOLD = 0.003          # >0.3% overnight gap


async def load_underlying_bars(db, ticker: str) -> List[Dict]:
    """Load underlying OHLCV bars sorted by date."""
    cursor = db["underlying_bars"].find(
        {"ticker": ticker}
    ).sort("date", 1)
    return await cursor.to_list(length=100000)


GEX_HISTORY_COLLECTION = "gex_history"


def fetch_gex_history_from_mongo(
    ticker: str,
    *,
    as_of: pd.Timestamp,
    lookback_days: int = 60,
    mongo_db: Any,
) -> List[Dict[str, Any]]:
    """Pull the last ``lookback_days`` of ``(ts, gex_total)`` for ``ticker``.

    Reads from the ``gex_history`` collection populated by
    ``scripts/backfill_gex_history.py``. Returns the exact shape expected by
    ``add_gex_features``: a list of ``{"ts": iso8601, "gex_total": float}``
    dicts sorted ascending by ``ts``.

    Leakage guard: every returned row satisfies ``ts <= as_of``. This is the
    SAME contract ``add_gex_features`` relies on — if the caller filters here
    correctly, downstream feature computation cannot peek at the future.

    ``lookback_days`` is calendar days (not trading days), matching how the
    downstream 60-day z-score lookback is specified in the feature module.
    ``mongo_db`` is a sync pymongo Database (or compatible mock) — we use
    sync here so the same function is callable from training scripts and
    backfills, neither of which run inside an event loop.
    """
    if not isinstance(as_of, pd.Timestamp):
        as_of = pd.Timestamp(as_of)
    if as_of.tzinfo is None:
        as_of = as_of.tz_localize("UTC")

    start_dt = as_of - pd.Timedelta(days=lookback_days)

    as_of_iso = as_of.isoformat()
    start_iso = start_dt.isoformat()

    cursor = mongo_db[GEX_HISTORY_COLLECTION].find(
        {
            "ticker": ticker,
            "ts": {"$gte": start_iso, "$lte": as_of_iso},
        },
        {"ts": 1, "gex_total": 1, "_id": 0},
    )

    rows = [
        {"ts": r["ts"], "gex_total": _safe_float(r.get("gex_total"))}
        for r in cursor
        if r.get("ts") is not None
    ]
    rows.sort(key=lambda r: r["ts"])
    return rows


# ============================================================================
# Feature computation
# ============================================================================

def _safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        f = float(val)
        if f != f:  # NaN
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(val, default=0):
    if val is None:
        return default
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def compute_returns(bars: List[Dict]) -> Dict[str, List[float]]:
    """Compute return series from OHLCV bars."""
    closes = [_safe_float(b.get("close")) for b in bars]
    n = len(closes)
    returns = {}

    # Simple returns for various horizons
    for horizon, name in [(1, "ret_1d"), (3, "ret_3d"), (5, "ret_5d"), (10, "ret_10d"), (21, "ret_21d")]:
        ret = [0.0] * n
        for i in range(horizon, n):
            if closes[i - horizon] > 0:
                ret[i] = (closes[i] - closes[i - horizon]) / closes[i - horizon]
        returns[name] = ret

    # Log returns
    log_ret = [0.0] * n
    for i in range(1, n):
        if closes[i - 1] > 0 and closes[i] > 0:
            log_ret[i] = np.log(closes[i] / closes[i - 1])
    returns["log_ret_1d"] = log_ret

    # Overnight gap (if we have open/close)
    gaps = [0.0] * n
    for i in range(1, n):
        prev_close = _safe_float(bars[i - 1].get("close"))
        curr_open = _safe_float(bars[i].get("open"))
        if prev_close > 0:
            gaps[i] = (curr_open - prev_close) / prev_close
    returns["overnight_gap"] = gaps

    return returns


def compute_realized_vol(bars: List[Dict], windows: List[int] = None) -> Dict[str, List[float]]:
    """Compute realized volatility over various windows."""
    if windows is None:
        windows = [5, 10, 21, 60]

    closes = [_safe_float(b.get("close")) for b in bars]
    n = len(closes)

    # Log returns
    log_ret = [0.0] * n
    for i in range(1, n):
        if closes[i - 1] > 0 and closes[i] > 0:
            log_ret[i] = np.log(closes[i] / closes[i - 1])

    vols = {}
    for w in windows:
        vol = [0.0] * n
        for i in range(w, n):
            window_rets = log_ret[i - w:i]
            if len(window_rets) > 1:
                vol[i] = float(np.std(window_rets) * np.sqrt(252))  # Annualized
        vols[f"realized_vol_{w}d"] = vol

    return vols


def compute_technical_features(bars: List[Dict]) -> Dict[str, List[float]]:
    """Compute technical indicators from OHLCV bars."""
    n = len(bars)
    closes = [_safe_float(b.get("close")) for b in bars]
    highs = [_safe_float(b.get("high")) for b in bars]
    lows = [_safe_float(b.get("low")) for b in bars]
    volumes = [_safe_float(b.get("volume")) for b in bars]

    features = {}

    # Simple Moving Averages
    for window in [5, 10, 21, 50]:
        sma = [0.0] * n
        for i in range(window - 1, n):
            sma[i] = np.mean(closes[i - window + 1:i + 1])
        features[f"sma_{window}"] = sma

    # Price relative to SMA
    for window in [5, 21, 50]:
        rel = [0.0] * n
        sma_key = f"sma_{window}"
        if sma_key in features:
            for i in range(n):
                if features[sma_key][i] > 0:
                    rel[i] = closes[i] / features[sma_key][i] - 1.0
        features[f"price_vs_sma_{window}"] = rel

    # ATR (Average True Range)
    atr_14 = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
    for i in range(14, n):
        atr_14[i] = np.mean(tr[i - 13:i + 1])
    features["atr_14"] = atr_14

    # Volume features
    vol_sma_5 = [0.0] * n
    vol_sma_21 = [0.0] * n
    for i in range(4, n):
        vol_sma_5[i] = np.mean(volumes[i - 4:i + 1])
    for i in range(20, n):
        vol_sma_21[i] = np.mean(volumes[i - 20:i + 1])
    features["volume_sma_5"] = vol_sma_5
    features["volume_sma_21"] = vol_sma_21

    # Relative volume
    rel_vol = [0.0] * n
    for i in range(20, n):
        if vol_sma_21[i] > 0:
            rel_vol[i] = volumes[i] / vol_sma_21[i]
    features["relative_volume"] = rel_vol

    return features


def compute_gex_features(snapshots: List[Dict]) -> Dict[str, List[float]]:
    """Compute GEX-derived features from snapshots."""
    n = len(snapshots)
    features = {}

    # Raw GEX values
    features["net_gex"] = [_safe_float(s.get("net_gex")) for s in snapshots]
    features["net_call_gex"] = [_safe_float(s.get("net_call_gex")) for s in snapshots]
    features["net_put_gex"] = [_safe_float(s.get("net_put_gex")) for s in snapshots]
    features["spot_price"] = [_safe_float(s.get("spot_price")) for s in snapshots]
    features["put_call_ratio"] = [_safe_float(s.get("put_call_ratio")) for s in snapshots]
    features["gex_concentration"] = [_safe_float(s.get("gex_concentration")) for s in snapshots]
    features["options_count"] = [float(_safe_int(s.get("options_count"))) for s in snapshots]

    # GEX z-score (60-day rolling)
    net_gex = features["net_gex"]
    gex_zscore = [0.0] * n
    for i in range(60, n):
        window = net_gex[i - 60:i]
        mean = np.mean(window)
        std = np.std(window)
        if std > 0:
            gex_zscore[i] = (net_gex[i] - mean) / std
    features["net_gex_zscore_60d"] = gex_zscore

    # GEX rate of change
    for horizon in [1, 3, 5, 10]:
        roc = [0.0] * n
        for i in range(horizon, n):
            if abs(net_gex[i - horizon]) > 1e-10:
                roc[i] = (net_gex[i] - net_gex[i - horizon]) / abs(net_gex[i - horizon])
        features[f"net_gex_roc_{horizon}d"] = roc

    # Distance to GEX flip (from gex_concentration)
    # gex_concentration is negative when below flip, positive above
    features["dist_to_flip"] = [-_safe_float(s.get("gex_concentration")) for s in snapshots]

    # GEX regime encoding
    regime_map = {"Positive": 1.0, "Negative": -1.0, "positive": 1.0, "negative": -1.0}
    features["gex_regime_encoded"] = [regime_map.get(s.get("gex_regime", ""), 0.0) for s in snapshots]

    # Realized vol features (from snapshots)
    features["realized_vol_t1"] = [_safe_float(s.get("realized_vol_t1")) for s in snapshots]
    features["realized_vol_t3"] = [_safe_float(s.get("realized_vol_t3")) for s in snapshots]

    # Rolling realized vol
    for key in ["realized_vol_rolling_3d", "realized_vol_rolling_5d"]:
        features[key] = [_safe_float(s.get(key)) for s in snapshots]

    return features


# ============================================================================
# Row-wise GEX features (Phase 4 — SPY v3)
#
# These augment the snapshot-array features above with per-row aggregates that
# depend on a pre-computed `gex_history` column (a list of dicts with keys
# `ts` and `gex_total`, already trimmed to ts <= row.ts upstream so leakage
# is impossible by construction).
#
# Designed for ingestion of a dataframe shaped one-row-per-(ticker, ts), as
# produced by the v3 feature builder. Pure pandas/numpy — no Mongo, no I/O.
# ============================================================================

# Required and optional columns for `add_gex_features`. Documented here so the
# contract is grep-able from the call site.
GEX_FEATURE_REQUIRED_COLS: Tuple[str, ...] = ("ticker", "ts", "spot", "gex_total")
GEX_FEATURE_OPTIONAL_COLS: Tuple[str, ...] = ("gamma_flip", "gex_by_strike")

# Column names this function adds. Used by the idempotency guard.
GEX_FEATURE_OUTPUT_COLS: Tuple[str, ...] = (
    "gex_zscore_60d",
    "gex_roc_5d",
    "gex_regime_pos",
    "gex_distance_to_flip_norm",
    "gex_wall_density_pct",
    "gex_herfindahl",
)

# ε used in safe division across all features (mirrors compute_gex_features
# which uses 1e-10; we adopt 1e-9 per Phase 4 spec).
_GEX_EPS = 1e-9

# Wall-density band: fraction of |GEX| inside ±1% of spot.
_GEX_WALL_BAND_PCT = 0.01

# Minimum history length required for the 5-day rate-of-change.
_GEX_ROC_LOOKBACK = 5


def _extract_history_series(history: Any) -> List[float]:
    """Pull the gex_total scalar series out of a history-column value.

    Accepts None, NaN, empty list, or a list of ``(ts, gex_total)`` tuples /
    ``{"ts": ..., "gex_total": ...}`` dicts. Skips entries we can't parse and
    returns them in input order (the caller is responsible for upstream sort).
    """
    if history is None:
        return []
    # Pandas often hands us a float NaN where a list was expected.
    if isinstance(history, float) and math.isnan(history):
        return []
    if not hasattr(history, "__iter__"):
        return []

    out: List[float] = []
    for item in history:
        val: Any = None
        if isinstance(item, dict):
            val = item.get("gex_total")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            # Convention: (ts, gex_total).
            val = item[1]
        else:
            val = item
        if val is None:
            continue
        try:
            f = float(val)
        except (TypeError, ValueError):
            continue
        if f != f:  # NaN
            continue
        out.append(f)
    return out


def _gex_zscore_60d(gex_total: float, history_vals: List[float]) -> float:
    """``(gex_total - mean(history)) / (std(history) + ε)``.

    History is the trailing N (≤ 60) snapshots, *not* including the current row.
    Leakage argument: the caller filtered ``gex_history`` to ``ts <= current_ts``
    and we never look at the current value when computing mean/std — we only
    use it as the numerator. So this depends solely on ``ts <= t`` data.
    """
    if not history_vals:
        return float("nan")
    arr = np.asarray(history_vals, dtype=float)
    mean = float(np.mean(arr))
    # ddof=0 (population) — matches numpy default and the existing
    # compute_gex_features convention.
    std = float(np.std(arr))
    return (gex_total - mean) / (std + _GEX_EPS)


def _gex_roc_5d(gex_total: float, history_vals: List[float]) -> float:
    """``(gex_total - gex_5d_ago) / |gex_5d_ago + ε|``.

    ``gex_5d_ago`` is the entry 5 positions before the most recent in history.
    For a history sorted oldest-first, that is ``history[-5]``. If fewer than
    5 entries exist we return NaN — the training pipeline drops NaN rows.
    """
    if len(history_vals) < _GEX_ROC_LOOKBACK:
        return float("nan")
    gex_5d_ago = float(history_vals[-_GEX_ROC_LOOKBACK])
    return (gex_total - gex_5d_ago) / (abs(gex_5d_ago) + _GEX_EPS)


def _gex_regime_pos(gex_total: float) -> float:
    """1.0 if dealer GEX is net positive (long gamma regime), else 0.0.

    Pure function of the current snapshot — no history dependency, hence no
    leakage path. Kept as a feature because the v3 variance-floor assertion
    will fail on monotone-sign training windows; this guarantees a binary
    indicator distinct from gex_total itself.
    """
    if gex_total != gex_total:  # NaN
        return float("nan")
    return 1.0 if gex_total > 0.0 else 0.0


def _gex_distance_to_flip_norm(spot: float, gamma_flip: Any) -> float:
    """``(spot - gamma_flip) / spot``.

    Returns 0.0 (with a warning logged once per call site, upstream) when
    ``gamma_flip`` is missing or NaN. We intentionally do NOT raise — many
    tickers will not have a flip on a given day and the model must still
    train on those rows.
    """
    if gamma_flip is None:
        return 0.0
    try:
        gf = float(gamma_flip)
    except (TypeError, ValueError):
        return 0.0
    if gf != gf:  # NaN
        return 0.0
    if spot is None or spot == 0:
        return 0.0
    try:
        s = float(spot)
    except (TypeError, ValueError):
        return 0.0
    if s == 0:
        return 0.0
    return (s - gf) / s


def _gex_wall_density_pct(spot: float, gex_by_strike: Any) -> float:
    """Fraction of total |GEX| concentrated within ±1% of spot.

    ``gex_by_strike`` is a ``Dict[float, float]`` (strike → signed GEX). High
    value means the gamma wall is right at spot; low value means it's diffuse
    or far away. Returns NaN when the dict is missing — that's the contract.
    """
    if not isinstance(gex_by_strike, dict) or not gex_by_strike:
        return float("nan")
    if spot is None or spot == 0:
        return float("nan")
    try:
        s = float(spot)
    except (TypeError, ValueError):
        return float("nan")
    if s == 0:
        return float("nan")

    low = s * (1.0 - _GEX_WALL_BAND_PCT)
    high = s * (1.0 + _GEX_WALL_BAND_PCT)

    total_abs = 0.0
    band_abs = 0.0
    for strike, gex in gex_by_strike.items():
        try:
            k = float(strike)
            g = abs(float(gex))
        except (TypeError, ValueError):
            continue
        if g != g:  # NaN
            continue
        total_abs += g
        if low <= k <= high:
            band_abs += g

    if total_abs <= 0:
        return float("nan")
    return band_abs / total_abs


def _gex_herfindahl(gex_by_strike: Any) -> float:
    """HHI of GEX concentration across strikes.

    ``HHI = Σ_k (|gex_k| / Σ|gex|)²``. Bounded in (0, 1]; 1.0 means everything
    is concentrated at a single strike, 1/N means equal distribution across
    N strikes. Returns NaN when ``gex_by_strike`` is missing.
    """
    if not isinstance(gex_by_strike, dict) or not gex_by_strike:
        return float("nan")
    abs_vals: List[float] = []
    for gex in gex_by_strike.values():
        try:
            g = abs(float(gex))
        except (TypeError, ValueError):
            continue
        if g != g:  # NaN
            continue
        abs_vals.append(g)
    if not abs_vals:
        return float("nan")
    total = sum(abs_vals)
    if total <= 0:
        return float("nan")
    return float(sum((g / total) ** 2 for g in abs_vals))


def add_gex_features(
    df: pd.DataFrame,
    gex_history_col: str = "gex_history",
) -> pd.DataFrame:
    """Append GEX-derived features to a one-row-per-(ticker, ts) dataframe.

    Adds these columns (see module docstrings on each ``_gex_*`` helper for
    the formula and the leakage argument):

      - ``gex_zscore_60d``           — 60-day rolling z-score of gex_total
      - ``gex_roc_5d``               — 5-day rate of change of gex_total
      - ``gex_regime_pos``           — 1 if gex_total > 0 else 0
      - ``gex_distance_to_flip_norm``— (spot - gamma_flip) / spot
      - ``gex_wall_density_pct``     — share of |GEX| within ±1% of spot
      - ``gex_herfindahl``           — HHI of |GEX| across strikes

    Required columns: ``ticker``, ``ts``, ``spot``, ``gex_total``, plus the
    history column named by ``gex_history_col`` (default ``gex_history``).
    Optional columns ``gamma_flip`` and ``gex_by_strike`` enable features
    4–6; their absence yields the documented fallbacks (0.0 or NaN).

    Leakage contract: per the calling builder, every row's ``gex_history``
    is pre-filtered to ``ts <= row.ts``. This function never reads future
    rows, never groups across rows, and never uses the current ``gex_total``
    inside the history aggregates. The ``test_gex_no_future_leakage`` test
    pins this guarantee.

    Idempotent: re-running on output is a no-op (overwrites the same columns
    deterministically; column count does not grow). Non-mutating: returns a
    new dataframe, leaves ``df`` untouched.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"add_gex_features expected DataFrame, got {type(df).__name__}")

    out = df.copy()

    # Empty-frame fast path — preserve the input columns plus the new ones so
    # downstream code that introspects schema gets a stable answer.
    if len(out) == 0:
        for col in GEX_FEATURE_OUTPUT_COLS:
            if col not in out.columns:
                out[col] = pd.Series(dtype="float64")
        return out

    missing_required = [c for c in GEX_FEATURE_REQUIRED_COLS if c not in out.columns]
    # The history column is required too but separately so its rename is honored.
    if gex_history_col not in out.columns:
        missing_required.append(gex_history_col)
    if missing_required:
        raise KeyError(
            f"add_gex_features: missing required columns {missing_required}; "
            f"have {list(out.columns)}"
        )

    has_gamma_flip = "gamma_flip" in out.columns
    has_gex_by_strike = "gex_by_strike" in out.columns

    if not has_gamma_flip:
        log.warning(
            "add_gex_features: 'gamma_flip' column absent — "
            "gex_distance_to_flip_norm will be filled with 0.0 for all rows."
        )

    zscores: List[float] = []
    rocs: List[float] = []
    regimes: List[float] = []
    dists: List[float] = []
    walls: List[float] = []
    hhis: List[float] = []

    spot_arr = out["spot"].tolist()
    gex_arr = out["gex_total"].tolist()
    hist_arr = out[gex_history_col].tolist()
    gamma_flip_arr = out["gamma_flip"].tolist() if has_gamma_flip else [None] * len(out)
    gex_by_strike_arr = (
        out["gex_by_strike"].tolist() if has_gex_by_strike else [None] * len(out)
    )

    for i in range(len(out)):
        try:
            spot_i = float(spot_arr[i]) if spot_arr[i] is not None else 0.0
        except (TypeError, ValueError):
            spot_i = 0.0
        try:
            gex_i = float(gex_arr[i])
            if gex_i != gex_i:  # NaN propagates as NaN below
                gex_i_is_nan = True
            else:
                gex_i_is_nan = False
        except (TypeError, ValueError):
            gex_i = float("nan")
            gex_i_is_nan = True

        history_vals = _extract_history_series(hist_arr[i])

        if gex_i_is_nan:
            zscores.append(float("nan"))
            rocs.append(float("nan"))
            regimes.append(float("nan"))
        else:
            zscores.append(_gex_zscore_60d(gex_i, history_vals))
            rocs.append(_gex_roc_5d(gex_i, history_vals))
            regimes.append(_gex_regime_pos(gex_i))

        dists.append(
            _gex_distance_to_flip_norm(spot_i, gamma_flip_arr[i] if has_gamma_flip else None)
        )

        if has_gex_by_strike:
            walls.append(_gex_wall_density_pct(spot_i, gex_by_strike_arr[i]))
            hhis.append(_gex_herfindahl(gex_by_strike_arr[i]))
        else:
            walls.append(float("nan"))
            hhis.append(float("nan"))

    out["gex_zscore_60d"] = zscores
    out["gex_roc_5d"] = rocs
    out["gex_regime_pos"] = regimes
    out["gex_distance_to_flip_norm"] = dists
    out["gex_wall_density_pct"] = walls
    out["gex_herfindahl"] = hhis

    return out


async def compute_features(
    ticker: str = "SPY",
    as_of: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compute all features for a ticker.

    Args:
        ticker: Ticker symbol
        as_of: Optional upper bound (YYYY-MM-DD) — features after this date are dropped.
        start: Optional inclusive lower bound (YYYY-MM-DD) on the row date.
        end: Optional inclusive upper bound (YYYY-MM-DD) on the row date.

    Returns:
        Dict with feature matrix, dates, feature names, and metadata.

    Tickers without GEX/outcomes data (e.g. QQQ today) get bar-anchored rows
    with GEX features zeroed and targets derived from the next-day OHLCV
    using the canonical materialization thresholds.
    """
    db = get_async_db()

    snapshots = await load_gex_snapshots(db, ticker)
    outcomes = await load_outcomes(db, ticker)
    bars = await load_underlying_bars(db, ticker)

    has_snapshots = bool(snapshots)
    has_outcomes = bool(outcomes)

    if not bars:
        log.warning(f"No underlying_bars rows for {ticker}; cannot compute features")
        return {"error": "no_data", "n_rows": 0, "ticker": ticker}

    if not has_snapshots:
        log.warning(
            f"No GEX snapshots for {ticker}; falling back to bar-anchored rows "
            "with GEX features zeroed."
        )

    if not has_outcomes:
        outcomes_by_date = derive_outcomes_from_bars(bars)
        log.info(
            f"No labeled outcomes for {ticker}; derived {len(outcomes_by_date)} "
            "outcome rows from underlying_bars."
        )
    else:
        outcomes_by_date = {o["date"]: o for o in outcomes}

    log.info(f"Loaded {len(snapshots)} snapshots, {len(outcomes)} outcomes, {len(bars)} bars for {ticker}")

    # Compute bar-based features
    bar_features = compute_technical_features(bars)
    bar_returns = compute_returns(bars)
    bar_vols = compute_realized_vol(bars)

    # Row anchor: snapshots if available, else bars.
    if has_snapshots:
        row_dates = [s["date"] for s in snapshots]
        gex_features = compute_gex_features(snapshots)
    else:
        row_dates = [b["date"] for b in bars]
        n = len(row_dates)
        # Zero-filled placeholders so the schema matches SPY rows.
        zero_keys = [
            "net_gex", "net_call_gex", "net_put_gex", "spot_price",
            "put_call_ratio", "gex_concentration", "options_count",
            "net_gex_zscore_60d",
            "net_gex_roc_1d", "net_gex_roc_3d", "net_gex_roc_5d", "net_gex_roc_10d",
            "dist_to_flip", "gex_regime_encoded",
            "realized_vol_t1", "realized_vol_t3",
            "realized_vol_rolling_3d", "realized_vol_rolling_5d",
        ]
        gex_features = {k: [0.0] * n for k in zero_keys}
        # spot_price is informational — fill from bars so downstream consumers see real prices.
        gex_features["spot_price"] = [_safe_float(b.get("close")) for b in bars]

    calendar_features = compute_calendar_features(row_dates)

    all_features: Dict[str, List[float]] = {}
    all_features.update(gex_features)
    all_features.update(calendar_features)

    bar_date_list = [b["date"] for b in bars]
    for feat_name, feat_values in {**bar_features, **bar_returns, **bar_vols}.items():
        aligned = []
        for sd in row_dates:
            idx = None
            for bi in range(len(bar_date_list) - 1, -1, -1):
                if bar_date_list[bi] <= sd:
                    idx = bi
                    break
            aligned.append(feat_values[idx] if idx is not None else 0.0)
        all_features[feat_name] = aligned

    targets = {
        "directional_move": [],
        "range_expansion": [],
        "gap_move": [],
        "any_materialization": [],
        "return_pct": [],
    }
    for sd in row_dates:
        outcome = outcomes_by_date.get(sd, {})
        for key in targets:
            targets[key].append(float(_safe_float(outcome.get(key, 0))))

    all_features.update(targets)
    snapshot_dates = row_dates

    # Build feature matrix (exclude targets from features)
    target_keys = set(targets.keys())
    feature_names = sorted([k for k in all_features.keys() if k not in target_keys and k != "date"])

    n_rows = len(snapshot_dates)
    n_features = len(feature_names)

    # Filter: only include rows where we have at least some non-zero features
    # and where we have a target
    valid_rows = []
    for i in range(n_rows):
        if targets["directional_move"][i] != 0 or targets["return_pct"][i] != 0:
            valid_rows.append(i)

    # Build output documents
    feature_docs = []
    for i in valid_rows:
        d = snapshot_dates[i]
        if as_of and d > as_of:
            continue
        if start and d < start:
            continue
        if end and d > end:
            continue

        doc = {
            "ticker": ticker,
            "date": d,
            "feature_version": FEATURE_VERSION,
            "target_directional_move": targets["directional_move"][i],
            "target_return_pct": targets["return_pct"][i],
            "target_range_expansion": targets["range_expansion"][i],
            "target_gap_move": targets["gap_move"][i],
            "target_any_materialization": targets["any_materialization"][i],
            "_computed_at": datetime.now(timezone.utc).isoformat(),
        }
        for fn in feature_names:
            doc[fn] = all_features[fn][i]

        feature_docs.append(doc)

    log.info(f"Computed {len(feature_docs)} feature rows with {n_features} features for {ticker}")

    return {
        "ticker": ticker,
        "n_rows": len(feature_docs),
        "n_features": n_features,
        "feature_names": feature_names,
        "docs": feature_docs,
    }


async def store_features(
    ticker: str = "SPY",
    as_of: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute and store features in MongoDB."""
    db = get_async_db()

    result = await compute_features(ticker, as_of, start=start, end=end)
    if result.get("error"):
        return result

    docs = result["docs"]
    if not docs:
        return {"stored": 0, "ticker": ticker, "message": "No valid feature rows"}

    # Upsert all feature documents
    collection = db[COLLECTION_FEATURES]
    # Ensure (ticker, feature_version, date) is unique so SPY and QQQ rows
    # coexist without collision.
    try:
        await collection.create_index(
            [("ticker", 1), ("feature_version", 1), ("date", 1)],
            unique=True,
            name="ticker_version_date_unique",
        )
    except Exception as e:
        log.debug(f"create_index ml_features: {e}")
    stored = 0
    for doc in docs:
        await collection.update_one(
            {"ticker": doc["ticker"], "date": doc["date"], "feature_version": FEATURE_VERSION},
            {"$set": doc},
            upsert=True,
        )
        stored += 1

    # Write manifest
    manifest = {
        "ticker": ticker,
        "feature_version": FEATURE_VERSION,
        "n_rows": stored,
        "n_features": result["n_features"],
        "feature_names": result["feature_names"],
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db["feature_manifests"].update_one(
        {"ticker": ticker, "feature_version": FEATURE_VERSION},
        {"$set": manifest},
        upsert=True,
    )

    log.info(f"Stored {stored} feature rows for {ticker}")
    return {"stored": stored, "ticker": ticker, "n_features": result["n_features"]}


async def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Compute ML features")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--as-of", default=None, help="Upper-bound date (YYYY-MM-DD)")
    parser.add_argument("--start", default=None, help="Inclusive start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="Inclusive end date (YYYY-MM-DD)")
    args = parser.parse_args()

    result = await store_features(args.ticker, args.as_of, start=args.start, end=args.end)
    logger.info(json.dumps(result, indent=2))


def get_async_db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


async def load_gex_snapshots(db, ticker: str = "SPY") -> List[Dict]:
    """
    Load GEX snapshots for a ticker, sorted by date.

    Snapshots may either carry an explicit `ticker` field (newer ingests) or
    only an `_source` tag (legacy SPY backfill). We match either way; tickers
    other than SPY get only docs with `ticker == <ticker>`.
    """
    if ticker == "SPY":
        query = {"$or": [
            {"ticker": "SPY"},
            {"_source": "issue_141_enhanced_dataset"},
        ]}
    else:
        query = {"ticker": ticker}
    cursor = db["gex_enhanced_snapshots"].find(query).sort("date", 1)
    return await cursor.to_list(length=10000)


def derive_outcomes_from_bars(bars: List[Dict]) -> Dict[str, Dict]:
    """
    Derive next-day outcomes from OHLCV bars using the canonical thresholds.

    Returns a dict keyed by the *snapshot date* (i.e. t0), with the outcome
    measured on t1 — matching the convention in `gex_llm_patterns_outcomes`
    where the row date is t0 and fields describe what happened on t1.
    """
    out: Dict[str, Dict] = {}
    n = len(bars)
    for i in range(n - 1):
        t0 = bars[i]
        t1 = bars[i + 1]
        close_t0 = _safe_float(t0.get("close"))
        open_t1 = _safe_float(t1.get("open"))
        close_t1 = _safe_float(t1.get("close"))
        high_t1 = _safe_float(t1.get("high"))
        low_t1 = _safe_float(t1.get("low"))
        if close_t0 <= 0 or open_t1 <= 0:
            continue

        return_pct = (close_t1 - open_t1) / open_t1 * 100.0
        abs_return = abs(return_pct) / 100.0
        gap = abs(open_t1 - close_t0) / close_t0
        rng = (high_t1 - low_t1) / open_t1 if open_t1 > 0 else 0.0

        directional = abs_return > DIRECTIONAL_MOVE_THRESHOLD
        range_exp = rng > RANGE_EXPANSION_THRESHOLD
        gap_move = gap > GAP_MOVE_THRESHOLD

        out[t0["date"]] = {
            "date": t0["date"],
            "directional_move": directional,
            "range_expansion": range_exp,
            "gap_move": gap_move,
            "any_materialization": directional or range_exp or gap_move,
            "return_pct": return_pct,
            "abs_return_pct": abs_return * 100.0,
            "gap_pct": gap * 100.0,
            "range_pct": rng * 100.0,
            "_derived_from": "underlying_bars",
        }
    return out


def compute_calendar_features(dates: List[str]) -> Dict[str, List[float]]:
    """Compute calendar-based features."""
    n = len(dates)
    features = {}

    dow = [0.0] * n  # Day of week (0=Mon)
    dom = [0.0] * n  # Day of month
    month = [0.0] * n
    is_month_end = [0.0] * n
    is_month_start = [0.0] * n

    for i, d in enumerate(dates):
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            dow[i] = float(dt.weekday())
            dom[i] = float(dt.day)
            month[i] = float(dt.month)
            # Month end: last 3 trading days
            is_month_end[i] = 1.0 if dt.day >= 28 else 0.0
            is_month_start[i] = 1.0 if dt.day <= 3 else 0.0
        except Exception:
            pass

    features["day_of_week"] = dow
    features["day_of_month"] = dom
    features["month"] = month
    features["is_month_end"] = is_month_end
    features["is_month_start"] = is_month_start

    return features


if __name__ == "__main__":
    asyncio.run(main())
