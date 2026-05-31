#!/usr/bin/env python3
"""
scripts/engineer_missing_features.py

Compute the 12 missing engineered features from existing CSV columns
and update both the CSV files and MongoDB ml_features collection.

Missing features:
  gap_abs         = abs(overnight_gap)
  gap_large       = int(overnight_gap > 0.02)  # >2% gap
  ret_accel       = ret_3d - ret_1d            # acceleration
  ret_momentum    = ret_5d + ret_21d           # momentum combo
  rsi_overbought  = int(rsi_14 > 70)
  rsi_oversold    = int(rsi_14 < 30)
  sma_10_50_diff  = sma_10 - sma_50
  sma_5_21_cross  = int(sma_5 > sma_21)        # 1 if bullish cross
  sma_5_21_diff   = sma_5 - sma_21
  vol_ratio_5_21  = realized_vol_5d / (realized_vol_21d + 1e-8)
  vol_ratio_5_60  = realized_vol_5d / (realized_vol_60d + 1e-8)
  vol_spike       = int(relative_volume > 2.0)
"""
import asyncio
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import logging

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cached_features"

CSV_FILES = ["IWM_v1.0.csv", "TLT_v1.0.csv", "QQQ_v1.0.csv", "DIA_v1.0.csv", "SPY_v1.0.csv"]


def compute_missing_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add the 12 missing engineered features."""
    df = df.copy()

    # gap features
    if 'overnight_gap' in df.columns:
        df['gap_abs'] = df['overnight_gap'].abs()
        df['gap_large'] = (df['overnight_gap'].abs() > 0.02).astype(int)

    # return acceleration/momentum
    if 'ret_3d' in df.columns and 'ret_1d' in df.columns:
        df['ret_accel'] = df['ret_3d'] - df['ret_1d']
    if 'ret_5d' in df.columns and 'ret_21d' in df.columns:
        df['ret_momentum'] = df['ret_5d'] + df['ret_21d']

    # RSI extremes
    if 'rsi_14' in df.columns:
        df['rsi_overbought'] = (df['rsi_14'] > 70).astype(int)
        df['rsi_oversold'] = (df['rsi_14'] < 30).astype(int)

    # SMA crosses/diffs
    if 'sma_10' in df.columns and 'sma_50' in df.columns:
        df['sma_10_50_diff'] = df['sma_10'] - df['sma_50']
    if 'sma_5' in df.columns and 'sma_21' in df.columns:
        df['sma_5_21_diff'] = df['sma_5'] - df['sma_21']
        df['sma_5_21_cross'] = (df['sma_5'] > df['sma_21']).astype(int)

    # Volatility ratios
    if 'realized_vol_5d' in df.columns and 'realized_vol_21d' in df.columns:
        df['vol_ratio_5_21'] = df['realized_vol_5d'] / (df['realized_vol_21d'] + 1e-8)
    if 'realized_vol_5d' in df.columns and 'realized_vol_60d' in df.columns:
        df['vol_ratio_5_60'] = df['realized_vol_5d'] / (df['realized_vol_60d'] + 1e-8)

    # Volume spike
    if 'relative_volume' in df.columns:
        df['vol_spike'] = (df['relative_volume'] > 2.0).astype(int)

    # Fill any NaN from derivations
    new_cols = ['gap_abs', 'gap_large', 'ret_accel', 'ret_momentum',
                'rsi_overbought', 'rsi_oversold', 'sma_10_50_diff',
                'sma_5_21_cross', 'sma_5_21_diff', 'vol_ratio_5_21',
                'vol_ratio_5_60', 'vol_spike']
    for col in new_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)

    return df


def sanitize_doc(doc: dict) -> dict:
    result = {}
    for k, v in doc.items():
        if isinstance(v, (np.integer,)):
            result[k] = int(v)
        elif isinstance(v, (np.floating,)):
            result[k] = 0.0 if (np.isnan(v) or np.isinf(v)) else float(v)
        elif isinstance(v, (np.bool_,)):
            result[k] = bool(v)
        elif pd.isna(v):
            result[k] = None
        else:
            result[k] = v
    return result


async def update_mongo(ticker: str, df: pd.DataFrame):
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "confluence_decoder")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    col = db["ml_features"]

    new_cols = ['gap_abs', 'gap_large', 'ret_accel', 'ret_momentum',
                'rsi_overbought', 'rsi_oversold', 'sma_10_50_diff',
                'sma_5_21_cross', 'sma_5_21_diff', 'vol_ratio_5_21',
                'vol_ratio_5_60', 'vol_spike']

    updated = 0
    for _, row in df.iterrows():
        doc = sanitize_doc(row.to_dict())
        # Only update the new fields (don't overwrite existing data)
        update_fields = {k: doc.get(k) for k in new_cols if k in doc}
        if update_fields:
            await col.update_one(
                {"ticker": ticker, "date": doc.get("date")},
                {"$set": update_fields},
            )
            updated += 1

    logger.info(f"  MongoDB: updated {updated} docs with {len(new_cols)} new features")
    client.close()


async def main():
    for csv_name in CSV_FILES:
        csv_path = CACHE_DIR / csv_name
        ticker = csv_name.split("_")[0]

        if not csv_path.exists():
            logger.info(f"SKIP {ticker}: {csv_path} not found")
            continue

        df = pd.read_csv(csv_path)
        n_before = len(df.columns)

        # Check if already has the features
        if 'gap_abs' in df.columns and 'vol_spike' in df.columns:
            logger.info(f"{ticker}: already has engineered features ({n_before} cols)")
            continue

        df = compute_missing_features(df)
        n_after = len(df.columns)
        logger.info(f"{ticker}: {n_before} -> {n_after} columns (+{n_after - n_before} features)")

        # Save updated CSV
        df.to_csv(csv_path, index=False)
        logger.info(f"  CSV saved: {csv_path}")

        # Update MongoDB
        await update_mongo(ticker, df)

    logger.info("\nDone. Verifying...")
    # Quick verify
    for csv_name in CSV_FILES:
        csv_path = CACHE_DIR / csv_name
        if csv_path.exists():
            df = pd.read_csv(csv_path, nrows=1)
            has_all = all(f in df.columns for f in ['gap_abs', 'vol_spike', 'ret_accel'])
            logger.info(f"  {csv_name}: {'OK' if has_all else 'MISSING'} ({len(df.columns)} cols)")


if __name__ == "__main__":
    asyncio.run(main())
