#!/usr/bin/env python3
"""
scripts/upsert_features_to_mongo.py

Upsert cached CSV features into MongoDB ml_features collection.
Used when ml_features is missing tickers that exist in CSV cache.

Usage:
  cd backend && python -m scripts.upsert_features_to_mongo --dry-run
  cd backend && python -m scripts.upsert_features_to_mongo --upsert
"""
import argparse
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import logging

import numpy as np
import pandas as pd
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cached_features"

# CSV files to upsert (ticker -> csv_path)
CSV_FILES = {
    "IWM": CACHE_DIR / "IWM_v1.0.csv",
    "TLT": CACHE_DIR / "TLT_v1.0.csv",
    "QQQ": CACHE_DIR / "QQQ_v1.0.csv",
    "DIA": CACHE_DIR / "DIA_v1.0.csv",
    "SPY": CACHE_DIR / "SPY_v1.0.csv",
}

META_COLS = {'ticker', 'date', 'feature_version', '_computed_at', '_id'}


async def upsert_all(dry_run: bool = True):
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "confluence_decoder")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    col = db["ml_features"]

    total_inserted = 0
    _total_skipped = 0

    for ticker, csv_path in CSV_FILES.items():
        if not csv_path.exists():
            logger.info(f"  SKIP {ticker}: {csv_path} not found")
            continue

        df = pd.read_csv(csv_path)
        n_rows = len(df)

        # Count existing
        existing = await col.count_documents({"ticker": ticker})
        logger.info(f"\n{ticker}: {n_rows} rows in CSV, {existing} already in MongoDB")

        if dry_run:
            logger.info(f"  DRY RUN — would upsert {n_rows} rows")
            continue

        # Upsert each row
        inserted = 0
        for _, row in df.iterrows():
            doc = sanitize_doc(row.to_dict())
            doc["_computed_at"] = datetime.now(timezone.utc).isoformat()

            # Upsert on ticker + date (unique key)
            await col.update_one(
                {"ticker": doc.get("ticker", ticker), "date": doc.get("date")},
                {"$set": doc},
                upsert=True,
            )
            inserted += 1

        logger.info(f"  Upserted {inserted} rows")
        total_inserted += inserted

    # Final count
    for ticker in CSV_FILES:
        _count = await col.count_documents({"ticker": ticker})
        logger.info(f"  {total_inserted} total upserted" if not dry_run else "")
        break

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upsert", action="store_true", help="Actually upsert (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(upsert_all(dry_run=not args.upsert))


def sanitize_doc(doc: dict) -> dict:
    """Convert numpy types to Python native types for MongoDB."""
    result = {}
    for k, v in doc.items():
        if isinstance(v, (np.integer,)):
            result[k] = int(v)
        elif isinstance(v, (np.floating,)):
            if np.isnan(v) or np.isinf(v):
                result[k] = 0.0
            else:
                result[k] = float(v)
        elif isinstance(v, (np.bool_,)):
            result[k] = bool(v)
        elif pd.isna(v):
            result[k] = None
        else:
            result[k] = v
    return result
