#!/usr/bin/env python3
"""
Nightly outcome-refresh trigger for the Tidehunter Pro alert ledger.

Architecture note (2026-09-02): the outcome COMPUTE lives in the running
backend — POST /api/flowseeker/outcomes/refresh — because DuckDBEngine is a
per-process :memory: singleton: the alert ledger (flow_alerts_daily) only
exists inside the server process, so a separate cron process would read its
own empty DB and could never label real alerts. This script therefore just
triggers that endpoint (fail-closed behind X-API-Key, read from the same
.env) and reports the result.

The endpoint writes the precomputed stats + calibration snapshot to Mongo
(flow_outcome_cache), where the morning brief and the Scanner outcome panel
read them.

Run via cron AFTER the market close and after yfinance daily bars settle:
    30 20 * * 1-5  (20:30 ET)

Usage: .venv/bin/python3 cron_outcomes.py [--days 60] [--horizon 2] [--url ...]
Exit codes: 0 = refreshed (or honestly cold), 1 = backend unreachable /
auth rejected / unexpected failure (so cron-mail surfaces real breakage).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cron_outcomes")


def main() -> int:
    ap = argparse.ArgumentParser(description="Trigger in-process outcome refresh on the backend")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--horizon", type=int, default=2)
    ap.add_argument("--url", default="http://localhost:8000",
                    help="backend base URL (default http://localhost:8000)")
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    import httpx

    headers = {}
    api_key = os.environ.get("API_SECRET_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        resp = httpx.post(
            f"{args.url.rstrip('/')}/api/flowseeker/outcomes/refresh",
            params={"days": args.days, "horizon": args.horizon},
            headers=headers,
            timeout=120,
        )
    except Exception as e:
        log.error("backend not reachable: %s", e)
        return 1

    if resp.status_code == 401:
        log.error("auth rejected (401) — API_SECRET_KEY missing/mismatched in .env")
        return 1
    if resp.status_code != 200:
        log.error("refresh failed: HTTP %s %s", resp.status_code, resp.text[:200])
        return 1

    body = resp.json()
    status = body.get("status")
    if status == "no_alerts":
        log.info("ledger cold — nothing to refresh (normal until the engine fires)")
    else:
        log.info("done: %s", body)

    # 2. IVR series refresh (free — Mongo-only): per ticker, ATM IV history
    # from flow_scan_daily (populated intraday by _record_scan_baseline) →
    # percentile rank over the trailing window → RICH/CHEAP tags. Warmup is
    # contractual: under 60 obs → ivr=None, never a fabricated rank.
    try:
        n = asyncio.run(_refresh_ivr())
        log.info("ivr refreshed for %d ticker(s)", n)
    except Exception as e:
        log.warning("ivr refresh skipped: %s", e)
    return 0 if status in ("ok", "no_alerts") else 1


async def _refresh_ivr(window: int = 252, warmup: int = 60) -> int:
    import os as _os
    from datetime import UTC, datetime

    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo import UpdateOne

    mongo_url = _os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = _os.environ.get("DB_NAME", "floww")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    try:
        mdb = client[db_name]
        # ATM IV per ticker-day (only days that actually recorded one).
        cursor = mdb.flow_scan_daily.find(
            {"atm_iv": {"$exists": True, "$gt": 0}},
            {"ticker": 1, "date": 1, "atm_iv": 1},
        ).sort("date", 1).limit(20000)
        series: dict[str, list[tuple[str, float]]] = {}
        async for doc in cursor:
            series.setdefault(doc["ticker"], []).append((doc["date"], doc["atm_iv"]))
        if not series:
            return 0
        ops: list[UpdateOne] = []
        for t, obs in series.items():
            obs = obs[-window:]
            if len(obs) < warmup:
                continue   # warmup contract: no rank until 60 obs
            vals = sorted(v for _, v in obs)
            latest_date, latest_iv = obs[-1]
            below = sum(1 for v in vals if v <= latest_iv)
            ivr = round(100.0 * below / len(vals), 1)
            tag = "RICH" if ivr >= 75 else "CHEAP" if ivr <= 25 else None
            # One doc per (ticker, date): the day's final IVR is the truth.
            ops.append(UpdateOne(
                {"ticker": t, "date": latest_date},
                {"$set": {"ivr": ivr, "atm_iv": latest_iv,
                          "iv_tag": tag, "n_obs": len(obs),
                          "updated_at": datetime.now(UTC).isoformat()}},
                upsert=True,
            ))
        if ops:
            await mdb.flow_iv_daily.bulk_write(ops, ordered=False)
        return len(ops)
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
