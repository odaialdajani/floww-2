#!/usr/bin/env python3
"""
Fetch upcoming earnings dates into Mongo flow_earnings.

Why this exists: ΔOI hygiene (services/oi_hygiene.py) tags OICONF alerts
inside earnings windows — direction into an event is ambiguous (straddle
buyers + premium sellers mix with directionals, Pan-Poteshman semantics
don't transfer). The tag pipeline needs {ticker: report date}; this script
is the only network call in that chain (yfinance .calendar, one batched
call, run weekly — dates move rarely).

Fails soft: yfinance hiccups for a name leave that ticker's window
"unknown", which the tag pipeline surfaces honestly on the alert instead
of skipping silently.

Usage:
    .venv/bin/python3 scripts/fetch_earnings.py SPY QQQ NVDA TSLA
    .venv/bin/python3 scripts/fetch_earnings.py --from-scan 60
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch_earnings")


def _dates_from_yfinance(tickers: list[str]) -> dict[str, str | None]:
    """{ticker: 'YYYY-MM-DD' | None} — None means yfinance gave nothing."""
    import yfinance as yf

    out: dict[str, str | None] = {}
    try:
        tickers_obj = yf.Tickers(" ".join(tickers))
        for t in tickers:
            try:
                cal = tickers_obj.tickers[t].calendar
                d = None
                if isinstance(cal, dict):
                    raw = cal.get("Earnings Date")
                    if isinstance(raw, list) and raw:
                        d = raw[0]
                    elif raw is not None:
                        d = raw
                elif hasattr(cal, "empty") and not cal.empty:
                    row = cal.iloc[0]
                    raw = row.get(getattr(cal, "columns", [])[0]) if len(cal.columns) else None
                    d = raw if raw is not None else None
                if hasattr(d, "date"):
                    d = d.date()
                out[t] = d.isoformat() if isinstance(d, date) else None
            except Exception:
                out[t] = None   # honest unknown — tag pipeline surfaces it
    except Exception as e:
        log.warning("yfinance batch fetch failed: %s", e)
        return {t: None for t in tickers}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch earnings dates into flow_earnings")
    ap.add_argument("tickers", nargs="*", help="tickers to fetch")
    ap.add_argument("--from-scan", type=int, default=0, metavar="DAYS",
                    help="also include tickers seen in flow_scan_daily in the last N days")
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

    import asyncio

    from motor.motor_asyncio import AsyncIOMotorClient

    tickers = list(dict.fromkeys(args.tickers))   # dedupe, keep order
    if args.from_scan:
        async def _scan_tickers() -> list[str]:
            client = AsyncIOMotorClient(
                os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
                serverSelectionTimeoutMS=5000)
            try:
                cutoff = (date.today() - timedelta(days=args.from_scan)).isoformat()
                docs = await client[os.environ.get("DB_NAME", "floww")].flow_scan_daily.distinct(
                    "ticker", {"date": {"$gte": cutoff}})
                return list(docs)[:600]
            finally:
                client.close()
        tickers = list(dict.fromkeys(tickers + asyncio.run(_scan_tickers())))
    if not tickers:
        log.info("no tickers requested (pass tickers or --from-scan N)")
        return 0

    log.info("fetching earnings dates for %d ticker(s)", len(tickers))
    dates = _dates_from_yfinance(tickers)
    known = {t: d for t, d in dates.items() if d}
    log.info("yfinance returned %d/%d date(s)", len(known), len(tickers))

    async def _write() -> int:
        from pymongo import UpdateOne

        client = AsyncIOMotorClient(
            os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
            serverSelectionTimeoutMS=5000)
        try:
            ops = [UpdateOne({"ticker": o["ticker"]}, {"$set": o}, upsert=True)
                   for o in docs]
            res = await client[os.environ.get("DB_NAME", "floww")].flow_earnings.bulk_write(
                ops, ordered=False)
            return res.modified_count or len(ops)
        finally:
            client.close()

    docs = [{"ticker": t, "date": dates.get(t),
             "unknown": dates.get(t) is None,
             "fetched_at": date.today().isoformat()} for t in tickers]
    n = asyncio.run(_write())
    log.info("flow_earnings updated: %d doc(s)", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
