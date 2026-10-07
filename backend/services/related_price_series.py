"""Independent bounded daily-close evidence; never the model's 21-close cache."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path
from weakref import WeakValueDictionary

from services.agent.access.horizon import ET, _calendar, required_close
from services.related_correlations import aware_clock

MAX_NAMES = 20000
MAX_CLOSES = 300
MAX_PROVIDER_ROWS = 512
MAX_PAYLOAD_BYTES = 32768
MAX_STORE_BYTES = 384 * 1024 * 1024
MAX_SCOPES = 64
CACHE_TTL_SECONDS = 36 * 3600
RETRY_SECONDS = 30


def canonical_symbol(value):
    if not isinstance(value, str):
        return None
    symbol = value.strip().upper()
    return symbol if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,11}", symbol) else None


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _day(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
    clock = aware_clock(value)
    if clock is None:
        return None
    local = clock.astimezone(ET)
    if any((local.hour, local.minute, local.second, local.microsecond)):
        return None
    return local.date().isoformat()


def validate_daily_payload(ticker, payload, *, now, received_at, requested_at=None):
    symbol, current, receipt = canonical_symbol(ticker), aware_clock(now), aware_clock(received_at)
    request_clock = aware_clock(requested_at) if requested_at is not None else current
    result = {
        "ticker": symbol,
        "source": "public_api",
        "interval": "1d",
        "bars": [],
        "status": "unavailable",
        "reason": None,
        "event_time": None,
        "received_at": receipt.isoformat() if receipt else None,
        "event_time_basis": "closed_XNYS_session",
        "price_basis": "provider_reported",
        "adjustment_policy": "unknown",
        "split_dividend_flag": "unverified",
        "quality": "degraded",
        "fill_status": "not_reported",
        "excluded": {"invalid": 0, "unclosed": 0, "future": 0, "conflict": 0, "non_session": 0, "fill": 0},
        "expected_last_close": None,
        "provider_bar_timestamp": None,
    }
    if symbol is None:
        result["reason"] = "unsupported_symbol"
        return result
    if current is None or receipt is None or request_clock is None or request_clock > receipt or receipt > current:
        result["reason"] = "invalid_clock"
        return result
    if not isinstance(payload, dict) or payload.get("symbol") != symbol:
        result["reason"] = "symbol_mismatch"
        return result
    if any(key in payload and payload[key] is not False for key in ("leadingFill", "leading_fill", "fill", "filled")):
        result["reason"] = "filled_history"
        return result
    regular = payload.get("regularMarket")
    raw = regular.get("bars") if isinstance(regular, dict) else None
    if not isinstance(raw, list) or not raw or len(raw) > MAX_PROVIDER_ROWS:
        result["reason"] = "daily_history_unavailable"
        return result
    expected = aware_clock(required_close(current))
    result["expected_last_close"] = expected.isoformat()
    cal = _calendar()
    today = current.astimezone(ET).date().isoformat()
    dates = {}
    conflicts = set()
    source_stamps = {}
    for row in raw:
        if not isinstance(row, dict):
            result["excluded"]["invalid"] += 1
            continue
        day = _day(row.get("date", row.get("timestamp")))
        if (
            day is None
            or row.get("date") is not None
            and row.get("timestamp") is not None
            and _day(row["timestamp"]) != day
        ):
            result["excluded"]["invalid"] += 1
            continue
        if day > today:
            result["excluded"]["future"] += 1
            continue
        try:
            if not cal.is_session(day):
                result["excluded"]["non_session"] += 1
                continue
            close_at = cal.session_close(day).to_pydatetime().astimezone(UTC)
        except (ValueError, KeyError, TypeError):
            result["excluded"]["non_session"] += 1
            continue
        if close_at > current or close_at > receipt or close_at > request_clock:
            result["excluded"]["unclosed"] += 1
            continue
        if any(key in row and row[key] is not False for key in ("leadingFill", "leading_fill", "fill", "filled")):
            result["excluded"]["fill"] += 1
            continue
        if (
            row.get("complete", True) is not True
            or row.get("session", "regular") != "regular"
            or row.get("symbol", symbol) != symbol
            or row.get("ticker", symbol) != symbol
        ):
            result["excluded"]["invalid"] += 1
            continue
        prices = tuple(_number(row.get(key)) for key in ("open", "high", "low", "close"))
        if any(value is None for value in prices):
            result["excluded"]["invalid"] += 1
            continue
        opening, high, low, closing = prices
        if not low <= min(opening, closing) <= max(opening, closing) <= high:
            result["excluded"]["invalid"] += 1
            continue
        if "volume" in row:
            try:
                valid_volume = (
                    not isinstance(row["volume"], bool)
                    and row["volume"] is not None
                    and math.isfinite(float(row["volume"]))
                    and float(row["volume"]) >= 0
                )
            except (TypeError, ValueError, OverflowError):
                valid_volume = False
            if not valid_volume:
                result["excluded"]["invalid"] += 1
                continue
        if day in dates and dates[day] != prices:
            conflicts.add(day)
        dates[day] = prices
        source_stamps[day] = row.get("timestamp", row.get("date"))
    result["excluded"]["conflict"] = len(conflicts)
    bars = [{"date": day, "close": dates[day][3]} for day in sorted(dates) if day not in conflicts][-MAX_CLOSES:]
    if not bars:
        result["reason"] = "no_closed_history"
        return result
    event = cal.session_close(bars[-1]["date"]).to_pydatetime().astimezone(UTC)
    result.update(
        bars=bars,
        event_time=event.isoformat(),
        provider_bar_timestamp=source_stamps.get(bars[-1]["date"]),
        status="stale" if event < expected else "available",
        reason="dated_cache" if event < expected else None,
        admitted_closes=len(bars),
        raw_rows=len(raw),
        request_started_at=request_clock.isoformat(),
    )
    return result


class RelatedSeriesStore:
    """Only explicit data warming writes; empty GET reads do not create files."""

    def __init__(
        self, path, *, max_names=MAX_NAMES, max_payload_bytes=MAX_PAYLOAD_BYTES, max_store_bytes=MAX_STORE_BYTES
    ):
        if (
            not 1 <= max_names <= MAX_NAMES
            or not 1024 <= max_payload_bytes <= MAX_PAYLOAD_BYTES
            or not max_payload_bytes <= max_store_bytes <= MAX_STORE_BYTES
        ):
            raise ValueError("Unsupported related-cache limits")
        self.path = str(path)
        self.max_names = max_names
        self.max_payload_bytes = max_payload_bytes
        self.max_store_bytes = max_store_bytes
        self._connection = None
        self._lock = threading.RLock()
        self.read_error = None

    def _db(self, write=False):
        if self._connection is not None:
            return self._connection
        if self.path == ":memory:":
            write = True
        if not write:
            file = Path(self.path).resolve()
            if not file.exists():
                return None
            return sqlite3.connect(file.as_uri() + "?mode=ro", uri=True, timeout=2, check_same_thread=False)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=2, check_same_thread=False)
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA journal_size_limit=16777216")
        connection.execute("PRAGMA max_page_count=131072")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS related_series(ticker TEXT PRIMARY KEY,event REAL NOT NULL,received REAL NOT NULL,payload TEXT NOT NULL,sha256 TEXT NOT NULL,bytes INTEGER NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS related_attempt(ticker TEXT PRIMARY KEY,status TEXT NOT NULL,attempted REAL NOT NULL,reason TEXT,retry_at REAL NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS related_scope(scope TEXT PRIMARY KEY,cursor INTEGER NOT NULL,total INTEGER NOT NULL,updated REAL NOT NULL)"
        )
        connection.commit()
        self._connection = connection
        return connection

    def _read(self, query, args=()):
        with self._lock:
            try:
                connection = self._db()
            except (sqlite3.Error, OSError):
                self.read_error = "cache_storage_unavailable"
                return []
            if connection is None:
                return []
            try:
                return connection.execute(query, args).fetchall()
            except sqlite3.OperationalError:
                self.read_error = "cache_storage_unavailable"
                return []
            finally:
                if connection is not self._connection:
                    connection.close()

    def many(self, tickers, *, now=None):
        self.read_error = None
        current = aware_clock(now or datetime.now(UTC))
        stamp = current.timestamp()
        expected = aware_clock(required_close(current)).isoformat()
        names = list(dict.fromkeys(filter(None, (canonical_symbol(name) for name in tickers))))
        stored, attempts = {}, {}
        for offset in range(0, len(names), 400):
            batch = names[offset : offset + 400]
            holders = ",".join("?" for _ in batch)
            for symbol, _event, receipt, payload, checksum in self._read(
                "SELECT ticker,event,received,payload,sha256 FROM related_series WHERE ticker IN (" + holders + ")",
                batch,
            ):
                try:
                    if hashlib.sha256(payload.encode()).hexdigest() != checksum:
                        continue
                    value = json.loads(payload)
                    if value.get("ticker") != symbol or not self._valid(value, current, calendar=False):
                        continue
                    value["cache_stale"] = stamp - receipt > CACHE_TTL_SECONDS or value["event_time"] != expected
                    stored[symbol] = value
                except (ValueError, TypeError, KeyError):
                    continue
            for symbol, status, attempted, reason, retry_at in self._read(
                "SELECT ticker,status,attempted,reason,retry_at FROM related_attempt WHERE ticker IN (" + holders + ")",
                batch,
            ):
                attempts[symbol] = {
                    "status": status,
                    "attempted_at": datetime.fromtimestamp(attempted, UTC).isoformat(),
                    "reason": reason,
                    "retry_at": retry_at,
                }
        return {
            symbol: {
                **stored.get(
                    symbol,
                    {
                        "ticker": symbol,
                        "bars": [],
                        "status": "unavailable",
                        "reason": "not_checked",
                        "event_time": None,
                        "received_at": None,
                    },
                ),
                "latest_fetch": attempts.get(symbol),
            }
            for symbol in names
            if symbol in stored or symbol in attempts
        }

    def get(self, ticker, *, now=None):
        return self.many([ticker], now=now).get(canonical_symbol(ticker))

    @staticmethod
    def _valid(series, current, calendar=True):
        if (
            not isinstance(series, dict)
            or canonical_symbol(series.get("ticker")) != series.get("ticker")
            or series.get("source") != "public_api"
            or series.get("price_basis") != "provider_reported"
        ):
            return False
        event, receipt = aware_clock(series.get("event_time")), aware_clock(series.get("received_at"))
        bars = series.get("bars")
        if (
            event is None
            or receipt is None
            or event > receipt
            or receipt > current
            or not isinstance(bars, list)
            or not 1 <= len(bars) <= MAX_CLOSES
        ):
            return False
        dates = []
        for row in bars:
            if (
                not isinstance(row, dict)
                or _day(row.get("date")) != row.get("date")
                or _number(row.get("close")) is None
            ):
                return False
            dates.append(row["date"])
        if dates != sorted(set(dates)):
            return False
        try:
            return (not calendar or all(_calendar().is_session(day) for day in dates)) and _calendar().session_close(
                dates[-1]
            ).to_pydatetime().astimezone(UTC) == event
        except (ValueError, KeyError, TypeError):
            return False

    def save(self, series, *, now=None):
        current = aware_clock(now or datetime.now(UTC))
        if current is None or not self._valid(series, current):
            return False
        payload = json.dumps(series, allow_nan=False, separators=(",", ":"))
        size = len(payload.encode())
        if size > self.max_payload_bytes:
            return False
        symbol = series["ticker"]
        event = aware_clock(series["event_time"]).timestamp()
        receipt = aware_clock(series["received_at"]).timestamp()
        with self._lock:
            connection = self._db(write=True)
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM related_series WHERE received<?", (current.timestamp() - 7 * 86400,))
                connection.execute("DELETE FROM related_attempt WHERE attempted<?", (current.timestamp() - 7 * 86400,))
                old = connection.execute(
                    "SELECT event,received,bytes FROM related_series WHERE ticker=?", (symbol,)
                ).fetchone()
                count, total = connection.execute(
                    "SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM related_series"
                ).fetchone()
                if (
                    old
                    and (event < old[0] or event == old[0] and receipt < old[1])
                    or not old
                    and count >= self.max_names
                    or total - (old[2] if old else 0) + size > self.max_store_bytes
                ):
                    connection.rollback()
                    return False
                connection.execute(
                    "INSERT INTO related_series VALUES(?,?,?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET event=excluded.event,received=excluded.received,payload=excluded.payload,sha256=excluded.sha256,bytes=excluded.bytes",
                    (symbol, event, receipt, payload, hashlib.sha256(payload.encode()).hexdigest(), size),
                )
                connection.execute(
                    "INSERT INTO related_attempt VALUES(?,'available',?,NULL,0) ON CONFLICT(ticker) DO UPDATE SET status='available',attempted=excluded.attempted,reason=NULL,retry_at=0",
                    (symbol, current.timestamp()),
                )
                connection.commit()
                return True
            except BaseException:
                connection.rollback()
                raise

    def failure(self, ticker, reason, *, now=None, retry_after=RETRY_SECONDS, status="failed"):
        symbol = canonical_symbol(ticker)
        current = aware_clock(now or datetime.now(UTC))
        if symbol is None or current is None or status not in ("failed", "deferred"):
            raise ValueError("Invalid failed read")
        delay = max(RETRY_SECONDS, min(86400, float(retry_after)))
        reason = str(reason)[:80]
        with self._lock, self._db(write=True) as connection:
            connection.execute(
                "INSERT INTO related_attempt VALUES(?,?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET status=excluded.status,attempted=excluded.attempted,reason=excluded.reason,retry_at=excluded.retry_at",
                (symbol, status, current.timestamp(), reason, current.timestamp() + delay),
            )
            connection.execute(
                "DELETE FROM related_attempt WHERE ticker NOT IN (SELECT ticker FROM related_attempt ORDER BY attempted DESC,ticker LIMIT ?)",
                (self.max_names,),
            )

    def scope(self, key, *, total=0):
        rows = self._read("SELECT cursor,total FROM related_scope WHERE scope=?", (key,))
        return (
            {"cursor": min(rows[0][0], total), "total": total}
            if rows and rows[0][1] == total
            else {"cursor": 0, "total": total}
        )

    def advance(self, key, cursor, *, total, now=None):
        if (
            not isinstance(key, str)
            or len(key) > 300
            or type(cursor) is not int
            or type(total) is not int
            or not 0 <= cursor <= total
        ):
            raise ValueError("Invalid warming scope")
        stamp = aware_clock(now or datetime.now(UTC)).timestamp()
        with self._lock, self._db(write=True) as connection:
            connection.execute(
                "INSERT INTO related_scope VALUES(?,?,?,?) ON CONFLICT(scope) DO UPDATE SET cursor=excluded.cursor,total=excluded.total,updated=excluded.updated",
                (key, cursor, total, stamp),
            )
            connection.execute(
                "DELETE FROM related_scope WHERE scope NOT IN (SELECT scope FROM related_scope ORDER BY updated DESC,scope LIMIT ?)",
                (MAX_SCOPES,),
            )

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None


_SYMBOL_LOCKS = WeakValueDictionary()


def provider_read_cost():
    from services import public_api_adapter as adapter

    broker = adapter.BROKER
    cost = 3 if broker is None else 1
    expiry = getattr(broker, "_token_expires_at", None)
    if broker is not None and type(expiry) in (int, float) and expiry - time.time() < 300:
        # The shared getter may swallow one failed refresh; get_bars then
        # retries authentication before its data GET. Reserve both attempts.
        cost = 3
    if broker is not None and hasattr(broker, "_access_token") and broker._access_token is None:
        cost = 3
    return cost


async def warm_daily_series(ticker, store, *, now=None, max_reserved_calls=8):
    """One cache-coalesced data-only read under existing Public admission."""
    symbol = canonical_symbol(ticker)
    current = aware_clock(now or datetime.now(UTC))
    if symbol is None:
        return {"symbol": None, "status": "failed", "reason": "unsupported_symbol", "reserved_calls": 0}
    lock = _SYMBOL_LOCKS.get(symbol)
    if lock is None:
        lock = asyncio.Lock()
        _SYMBOL_LOCKS[symbol] = lock
    async with lock:
        cached = await asyncio.to_thread(store.get, symbol, now=current)
        expected = aware_clock(required_close(current)).isoformat()
        if cached and cached.get("event_time") == expected and not cached.get("cache_stale"):
            return {"symbol": symbol, "status": "cached", "reason": None, "reserved_calls": 0}
        retry = (cached or {}).get("latest_fetch") or {}
        if retry.get("retry_at", 0) > current.timestamp():
            return {
                "symbol": symbol,
                "status": "deferred",
                "reason": "retry_cooldown",
                "reserved_calls": 0,
                "retry_after": math.ceil(retry["retry_at"] - current.timestamp()),
            }
        from services import public_api_adapter as adapter
        from services.public_budget import BudgetExhausted, budget

        cost = provider_read_cost()
        if cost > max_reserved_calls:
            return {
                "symbol": symbol,
                "status": "deferred",
                "reason": "batch_call_limit",
                "reserved_calls": 0,
                "retry_after": 0,
            }
        held = False
        started = time.monotonic()
        try:
            await budget.acquire_n(cost, "api.public.com")
            held = True
            broker = await adapter._get_broker()
            if broker is None:
                raise ValueError("provider_unavailable")
            request_clock = current if now is not None else datetime.now(UTC)
            raw = await broker.get_bars(symbol, "YEAR", aggregation="ONE_DAY", trading_session_toggle="REGULAR_HOURS")
            received = current if now is not None else datetime.now(UTC)
            admitted = validate_daily_payload(
                symbol, raw, now=received, received_at=received, requested_at=request_clock
            )
            if not admitted["bars"]:
                await asyncio.to_thread(
                    store.failure, symbol, admitted["reason"] or "daily_history_unavailable", now=received
                )
                return {"symbol": symbol, "status": "failed", "reason": admitted["reason"], "reserved_calls": cost}
            saved = await asyncio.to_thread(store.save, admitted, now=received)
            if not saved:
                await asyncio.to_thread(store.failure, symbol, "cache_admission_refused", now=received)
                return {
                    "symbol": symbol,
                    "status": "failed",
                    "reason": "cache_admission_refused",
                    "reserved_calls": cost,
                }
            budget.record_ok("api.public.com", now=started)
            adapter._record_call(True)
            return {"symbol": symbol, "status": "fetched", "reason": None, "reserved_calls": cost}
        except BudgetExhausted as exc:
            failed_at = current if now is not None else datetime.now(UTC)
            await asyncio.to_thread(
                store.failure, symbol, exc.reason, now=failed_at, retry_after=exc.retry_after, status="deferred"
            )
            return {
                "symbol": symbol,
                "status": "deferred",
                "reason": exc.reason,
                "reserved_calls": 0,
                "retry_after": max(RETRY_SECONDS, exc.retry_after),
            }
        except asyncio.CancelledError:
            raise
        except (sqlite3.Error, OSError):
            return {
                "symbol": symbol,
                "status": "failed",
                "reason": "cache_storage_unavailable",
                "reserved_calls": cost if held else 0,
            }
        except Exception as exc:
            adapter._note_public_429(exc)
            if isinstance(exc, adapter._TRANSPORT_ERRORS):
                adapter._record_call(False)
            failed_at = current if now is not None else datetime.now(UTC)
            await asyncio.to_thread(store.failure, symbol, "provider_read_failed", now=failed_at)
            return {
                "symbol": symbol,
                "status": "failed",
                "reason": "provider_read_failed",
                "reserved_calls": cost if held else 0,
            }
        finally:
            if held:
                budget.release()
