async def store_snapshot(snapshot: dict) -> bool:
    """Store a snapshot in MongoDB."""
    if not snapshot:
        return False

    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]

    try:
        await db.snapshots.insert_one(snapshot)
        logger.info(f"Stored snapshot: {snapshot['ticker']} @ {snapshot['spot']:.2f} ({snapshot['regime']})")
        return True
    except Exception as e:
        logger.error(f"Failed to store snapshot: {e}")
        return False
    finally:
        client.close()

"""
Data collection script for ML training.

Fetches historical GEX snapshots to build a diverse training dataset.
Runs as a cron job to continuously collect data.
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
logger = logging.getLogger(__name__)


async def collect_snapshot(ticker: str = "SPY") -> dict:
    """Collect a single GEX snapshot."""
    from server import classify_nodes, compute_gex_by_strike, fetch_spot_and_chains_merged

    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"

    raw = await fetch_spot_and_chains_merged(t, 4)
    spot = raw.get("spot", 0)
    if not spot or not raw.get("contracts"):
        return {}

    strikes = compute_gex_by_strike(spot, raw["contracts"], t)
    total_gex = sum(s["gex"] for s in strikes)
    positive = sorted([s for s in strikes if s["gex"] > 0], key=lambda x: x["gex"], reverse=True)
    negative = sorted([s for s in strikes if s["gex"] < 0], key=lambda x: x["gex"])
    nodes = classify_nodes(strikes, spot)

    snapshot = {
        "ticker": ticker.upper(),
        "ts": datetime.now(timezone.utc).isoformat(),
        "spot": spot,
        "total_gex": round(total_gex, 0),
        "net_gex": round(sum(s["gex"] for s in strikes), 0),
        "king_strike": nodes.get("king", {}).get("strike", 0),
        "king_gex": nodes.get("king", {}).get("gex", 0),
        "top_floor": positive[0]["strike"] if positive else 0,
        "top_ceiling": negative[0]["strike"] if negative else 0,
        "regime": nodes.get("regime", "unknown"),
        "strikes_compact": [
            {"strike": s["strike"], "gex": round(s["gex"], 0)}
            for s in strikes[:20]  # Top 20 strikes
        ],
    }

    return snapshot


async def collect_multiple_tickers(tickers: list = None) -> list:
    """Collect snapshots for multiple tickers."""
    if tickers is None:
        tickers = ["SPY", "QQQ", "IWM", "DIA"]

    results = []
    for ticker in tickers:
        result = await collect_and_store(ticker)
        results.append(result)

    return results


async def collect_and_store(ticker: str = "SPY") -> dict:
    """Collect and store a snapshot."""
    snapshot = await collect_snapshot(ticker)
    if snapshot:
        success = await store_snapshot(snapshot)
        return {"status": "stored" if success else "error", "snapshot": snapshot}
    return {"status": "no_data"}
