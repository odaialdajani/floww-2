"""
Databento provider — Open Interest via OPRA.PILLAR `statistics` schema (stat_type=9).
Uses tight pre-market window (10:00-13:30 UTC) where EOD OI is published — ~$0.15/ticker/day.
Heavy Mongo caching: 1 fetch per ticker per US trading date.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import databento as db

log = logging.getLogger("databento")

DBN_KEY = os.environ.get("DATABENTO_API_KEY", "")
_hist_client: Optional[db.Historical] = None


def _get_client() -> Optional[db.Historical]:
    global _hist_client, DBN_KEY
    # Re-read env in case .env loaded after module import or key rotated
    key = os.environ.get("DATABENTO_API_KEY", "")
    if _hist_client is None or key != DBN_KEY:
        DBN_KEY = key
        _hist_client = db.Historical(key) if key else None
    return _hist_client


# Parent symbol mapping. SPX index options on CBOE = SPXW.OPT
PARENT_MAP = {
    "SPY": "SPY.OPT",
    "QQQ": "QQQ.OPT",
    "IWM": "IWM.OPT",
    "SPX": "SPXW.OPT",
    "^SPX": "SPXW.OPT",
    "SPXW": "SPXW.OPT",
    "AAPL": "AAPL.OPT",
    "NVDA": "NVDA.OPT",
    "TSLA": "TSLA.OPT",
    "META": "META.OPT",
    "AMZN": "AMZN.OPT",
    "MSFT": "MSFT.OPT",
    "GOOGL": "GOOGL.OPT",
    "AMD": "AMD.OPT",
    "AVGO": "AVGO.OPT",
    "NFLX": "NFLX.OPT",
    "COIN": "COIN.OPT",
    "PLTR": "PLTR.OPT",
    "MU": "MU.OPT",
}


OSI_RE = re.compile(r'^([A-Z]+)\s*(\d{2})(\d{2})(\d{2})([CP])(\d{8})$')


def parse_osi(raw: str) -> Optional[Dict[str, Any]]:
    """Parse OPRA OSI symbol like 'SPY   260612C00500000'"""
    m = OSI_RE.match(raw.strip())
    if not m:
        return None
    und, ymd, typ, strike = m.groups()
    return {
        "underlying": und,
        "expiry": f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:6]}",
        "type": "call" if typ == "C" else "put",
        "strike": int(strike) / 1000.0,
    }


def _last_trading_day_utc(now: Optional[datetime] = None) -> date_cls:
    """Approx US equities last trading day in UTC. Saturday/Sunday roll back.
    Uses America/New_York timezone for correct DST handling."""
    from zoneinfo import ZoneInfo
    ny_tz = ZoneInfo("America/New_York")
    n = (now or datetime.now(timezone.utc)).astimezone(ny_tz)
    # After US market close (4pm ET)
    if n.hour >= 16:
        n = n.replace(hour=16, minute=0, second=0, microsecond=0)
    else:
        n = n.replace(hour=16, minute=0, second=0, microsecond=0) - timedelta(days=1)
    while n.weekday() >= 5:
        n -= timedelta(days=1)
    return n.date()


def _fetch_oi_sync(parent: str, day: date_cls) -> Dict[str, Any]:
    """Blocking Databento fetch. Returns {raw_symbol: {strike, expiry, type, oi}}."""
    client = _get_client()
    if not client:
        log.warning("Databento client not initialized — missing DATABENTO_API_KEY")
        return {}
    # Tight pre-market window where EOD OI is published
    start = f"{day.isoformat()}T10:00:00"
    end = f"{day.isoformat()}T13:30:00"
    try:
        data = client.timeseries.get_range(
            dataset="OPRA.PILLAR",
            symbols=[parent],
            stype_in="parent",
            schema="statistics",
            start=start,
            end=end,
            limit=300000,
        )
        df = data.to_df()
    except Exception as e:
        log.warning(f"databento OI fetch fail {parent} {day}: {e}")
        return {}

    if df is None or df.empty:
        return {}
    df = df[df["stat_type"] == 9]
    if df.empty:
        return {}
    # latest per symbol — sort by timestamp first to ensure .last() picks the newest
    df = df.sort_values("ts_event").groupby("symbol").last().reset_index()

    out: Dict[str, Dict[str, Any]] = {}
    for sym, qty in zip(df["symbol"], df["quantity"]):
        p = parse_osi(sym)
        if not p:
            continue
        if qty != qty or qty is None:  # NaN check first
            continue
        oi = int(qty)
        if oi <= 0:
            continue
        p["oi"] = oi
        out[sym] = p
    return out


class DatabentoCache:
    """Mongo-backed OI cache: doc per (parent, day) holds full snapshot."""

    def __init__(self, mongo_db):
        self.col = mongo_db.databento_oi
        self._mem: Dict[str, Dict[str, Any]] = {}

    async def ensure_index(self):
        try:
            await self.col.create_index([("parent", 1), ("day", 1)], unique=True)
        except Exception:
            pass

    async def get(self, parent: str, day: date_cls) -> Dict[str, Any]:
        key = f"{parent}:{day.isoformat()}"
        if key in self._mem:
            return self._mem[key]
        doc = await self.col.find_one({"parent": parent, "day": day.isoformat()}, {"_id": 0})
        if doc and doc.get("contracts"):
            self._mem[key] = doc["contracts"]
            return doc["contracts"]

        log.info(f"databento: fetching OI {parent} {day} (cache miss)")
        contracts = await asyncio.to_thread(_fetch_oi_sync, parent, day)
        if not contracts:
            return {}
        await self.col.update_one(
            {"parent": parent, "day": day.isoformat()},
            {"$set": {"parent": parent, "day": day.isoformat(),
                      "contracts": contracts, "fetched_at": datetime.now(timezone.utc).isoformat(),
                      "count": len(contracts)}},
            upsert=True,
        )
        self._mem[key] = contracts
        return contracts


_cache: Optional[DatabentoCache] = None


def init_cache(mongo_db) -> DatabentoCache:
    global _cache
    _cache = DatabentoCache(mongo_db)
    return _cache


def get_cache() -> Optional[DatabentoCache]:
    return _cache


async def fetch_oi_for_ticker(ticker: str, day: Optional[date_cls] = None) -> Dict[str, Any]:
    """Public API: get OI keyed by raw OSI symbol for a ticker."""
    key = os.environ.get("DATABENTO_API_KEY", DBN_KEY)
    if not key or not _cache:
        return {}
    parent = PARENT_MAP.get(ticker.upper().replace("^", ""), None)
    if not parent:
        parent = f"{ticker.upper().replace('^','')}.OPT"
    use_day = day or _last_trading_day_utc()
    # Walk back up to 4 trading days if data is missing
    for _ in range(4):
        contracts = await _cache.get(parent, use_day)
        if contracts:
            return contracts
        use_day -= timedelta(days=1)
        while use_day.weekday() >= 5:
            use_day -= timedelta(days=1)
    return {}


# ----------------------------- Live trades / Flowseeker -----------------------

async def stream_live_trades(parent: str, queue: asyncio.Queue, stop_event: asyncio.Event, dry_run: bool = False):
    """Stream live OPRA trades for a parent symbol into a queue.
    EXPENSIVE — only run when client subscribes via /api/flow SSE.
    Hard-stops within ~2s of stop_event being set, even if no trades are flowing."""
    if dry_run:
        return
    key = os.environ.get("DATABENTO_API_KEY", DBN_KEY)
    if not key:
        loop = asyncio.get_event_loop()
        try:
            asyncio.run_coroutine_threadsafe(queue.put({"_error": "Databento key missing"}), loop)
        except Exception:
            pass
        return
    loop = asyncio.get_event_loop()

    def _run():
        live = None
        try:
            live = db.Live(key=key)
            live.subscribe(
                dataset="OPRA.PILLAR",
                schema="trades",
                stype_in="parent",
                symbols=parent,
            )

            def cb(rec):
                try:
                    if stop_event.is_set():
                        try:
                            live.stop()
                        except Exception:
                            pass
                        return
                    sym = getattr(rec, "raw_symbol", None) or getattr(rec, "symbol", None)
                    if not sym:
                        return
                    parsed = parse_osi(sym) if sym else None
                    if not parsed:
                        return
                    px = getattr(rec, "price", 0) / 1e9 if hasattr(rec, "price") else 0
                    sz = getattr(rec, "size", 0)
                    ts = getattr(rec, "ts_event", 0)
                    side = getattr(rec, "side", None)
                    notional = px * sz * 100 if px and sz else 0
                    payload = {
                        "ts": ts,
                        "symbol": sym,
                        "underlying": parsed["underlying"],
                        "strike": parsed["strike"],
                        "expiry": parsed["expiry"],
                        "type": parsed["type"],
                        "price": px,
                        "size": sz,
                        "side": str(side) if side else None,
                        "notional": notional,
                        "unusual": sz >= 100 or notional >= 50000,
                        "sweep": sz >= 250,
                        "block": sz >= 500,
                    }
                    try:
                        asyncio.run_coroutine_threadsafe(queue.put(payload), loop)
                    except Exception:
                        pass
                except Exception as e:
                    log.warning(f"flow cb err: {e}")

            live.add_callback(cb)
            live.start()

            # Poll stop_event every second so manual stop is responsive
            import time as _t
            t0 = _t.time()
            while _t.time() - t0 < 600:  # hard upper-bound 10 min safety
                if stop_event.is_set():
                    break
                _t.sleep(1)
        except Exception as e:
            log.warning(f"flow stream err: {e}")
            try:
                asyncio.run_coroutine_threadsafe(queue.put({"_error": str(e)}), loop)
            except Exception:
                pass
        finally:
            try:
                if live is not None:
                    live.stop()
            except Exception:
                pass

    await asyncio.to_thread(_run)
