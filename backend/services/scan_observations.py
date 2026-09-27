"""Bounded per-name snapshot observations; no cross-name LRU eviction.

Only up to sixty selected contracts per name are retained. A missing baseline
is unknown, not zero. Receipt-window differences are not trade arrival rates.
Disk failure degrades comparison coverage; it does not invent a baseline.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CONTRACT_LIMIT = 60
SYMBOL_LIMIT = 20_000
PAYLOAD_LIMIT = 128 * 1024
STORE_PAYLOAD_LIMIT = 512 * 1024 * 1024
ET = ZoneInfo("America/New_York")


def unique_contracts(contracts):
    """Collapse identical repeats; exclude conflicting readings for one identity."""
    selected, conflicts, display_keys = {}, set(), {}
    for item in contracts or []:
        if not isinstance(item, dict):
            continue
        identity = item.get("osi")
        if not isinstance(identity, str) or not 1 <= len(identity) <= 100:
            continue
        if identity in selected and selected[identity] != item:
            conflicts.add(identity)
        else:
            selected[identity] = item
        # The existing alert/display key omits the option root/deliverable. Two
        # different provider identities cannot safely share that key.
        kind = str(item.get("type") or "").lower()
        kind = "call" if kind.startswith("c") else "put" if kind.startswith("p") else None
        strike = nonnegative(item.get("strike"))
        expiry = str(item.get("expiry") or "")[:10]
        if kind is not None and strike is not None and strike > 0 and len(expiry) == 10:
            key = (kind, strike, expiry)
            other = display_keys.setdefault(key, identity)
            if other != identity:
                conflicts.update((identity, other))
    return [item for identity, item in selected.items() if identity not in conflicts], len(conflicts)


def nonnegative(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def timestamp(value):
    try:
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None
            number = parsed.timestamp()
        elif type(value) in (float, int):
            number = float(value)
        else:
            return None
        datetime.fromtimestamp(number, UTC)
        return number if math.isfinite(number) else None
    except (ValueError, OverflowError, OSError):
        return None


def session_day(value):
    stamp = timestamp(value)
    return datetime.fromtimestamp(stamp, ET).date().isoformat() if stamp is not None else None


def volume_change(current, previous, received_at):
    """Conservative same-receipt-day comparison, with separately proven rate."""
    result = dict(snapshot_volume_change=None, snapshot_elapsed_seconds=None,
                  volume_change_basis=None, vol_delta=None, velocity_per_min=None)
    now = timestamp(received_at)
    current_volume = nonnegative(current.get("volume"))
    if now is None or current_volume is None or not isinstance(previous, dict):
        return result
    if previous.get("uncertain"):
        return result
    prior_volume = nonnegative(previous.get("volume"))
    prior_receipt = timestamp(previous.get("received_at"))
    if (prior_volume is None or prior_receipt is None or now <= prior_receipt
            or session_day(now) != session_day(prior_receipt) or current_volume < prior_volume):
        return result
    source_now = timestamp(current.get("volume_timestamp"))
    source_previous = timestamp(previous.get("volume_timestamp"))
    if (current.get("volume_timestamp") is not None and source_now is None
            or previous.get("volume_timestamp") is not None and source_previous is None):
        return result
    if source_now is not None and source_now > now or source_previous is not None and source_previous > prior_receipt:
        return result
    if source_now is not None and source_previous is not None and source_now <= source_previous:
        return result
    change = current_volume - prior_volume
    result.update(snapshot_volume_change=change, snapshot_elapsed_seconds=now - prior_receipt,
                  volume_change_basis="snapshot_receipt")
    if (source_now is not None and source_previous is not None
            and 0 <= now - source_now <= 60 and source_previous <= prior_receipt
            and 0 < source_now - source_previous <= 300
            and session_day(source_now) == session_day(source_previous) == session_day(now)):
        result.update(vol_delta=change, velocity_per_min=change * 60 / (source_now - source_previous),
                      volume_change_basis="source_volume_time")
    return result


def quote_time(contract):
    bid = timestamp(contract.get("bid_timestamp") or contract.get("bid_event_time"))
    ask = timestamp(contract.get("ask_timestamp") or contract.get("ask_event_time"))
    return min(bid, ask) if bid is not None and ask is not None else None


def eligible_quote(contract, received_at):
    received = timestamp(received_at)
    bid = timestamp(contract.get("bid_timestamp") or contract.get("bid_event_time"))
    ask = timestamp(contract.get("ask_timestamp") or contract.get("ask_event_time"))
    last = timestamp(contract.get("last_timestamp") or contract.get("last_event_time"))
    return (received is not None and bid is not None and ask is not None and last is not None
            and all(0 <= received - value <= 60 for value in (bid, ask, last))
            and 0 <= last - bid <= 5 and 0 <= last - ask <= 5)


def select_observations(contracts, preferred_osis, received_at, previous=None):
    now = timestamp(received_at)
    if now is None:
        raise ValueError("Valid receipt time required")
    preferred = set(preferred_osis)
    previous = previous or {}
    candidates = {}
    for item in unique_contracts(contracts)[0]:
        if not isinstance(item, dict):
            continue
        osi = item.get("osi")
        volume = nonnegative(item.get("volume"))
        if not isinstance(osi, str) or not 1 <= len(osi) <= 100 or volume is None:
            continue
        bid, ask = nonnegative(item.get("bid")), nonnegative(item.get("ask"))
        mid = bid + (ask - bid) / 2 if bid is not None and ask is not None and ask >= bid > 0 else None
        source = quote_time(item)
        prior = previous.get(osi, {})
        if session_day(prior.get("received_at")) != session_day(now):
            prior = {}
        prior_time = timestamp(prior.get("quote_timestamp"))
        prior_receipt = timestamp(prior.get("received_at"))
        source_volume = timestamp(item.get("volume_timestamp"))
        invalid_volume_time = (item.get("volume_timestamp") is not None
                               and (source_volume is None or source_volume > now))
        if invalid_volume_time:
            source_volume = None
        prior_volume_time = timestamp(prior.get("volume_timestamp"))
        source_rewind = (source_volume is not None and prior_volume_time is not None
                         and (source_volume < prior_volume_time
                              or source_volume == prior_volume_time and volume != prior.get("volume")))
        quote_rewind = (source is not None and prior_time is not None
                        and (source < prior_time or source == prior_time and mid != prior.get("mid")))
        if prior_receipt is not None and prior_receipt <= now and (source_rewind or quote_rewind):
            candidates[osi] = {**prior, "uncertain": True}
            continue
        ring = []
        bid_time = timestamp(item.get("bid_timestamp") or item.get("bid_event_time"))
        ask_time = timestamp(item.get("ask_timestamp") or item.get("ask_event_time"))
        valid_book_time = (bid_time is not None and ask_time is not None
                           and all(0 <= now - value <= 60 for value in (bid_time, ask_time)))
        if mid is not None and valid_book_time:
            if (prior_time is not None and prior_receipt is not None and prior_receipt < now
                    and not prior.get("uncertain") and 0 <= source - prior_time <= 60
                    and session_day(source) == session_day(prior_time)):
                ring = [value for value in prior.get("mid_ring", []) if nonnegative(value) is not None][-60:]
            if prior_time is None or source != prior_time or not ring:
                ring = [*ring, mid][-60:]
        candidates[osi] = dict(volume=volume, received_at=now,
                               volume_timestamp=source_volume,
                               mid=mid, quote_timestamp=source if valid_book_time else None, mid_ring=ring, uncertain=invalid_volume_time)
    selected = sorted(candidates, key=lambda key: (key not in preferred, -candidates[key]["volume"], key))[:CONTRACT_LIMIT]
    return {key: candidates[key] for key in selected}, len(candidates) > CONTRACT_LIMIT


class SnapshotObservations:
    def __init__(self, path, *, symbol_limit=SYMBOL_LIMIT, payload_limit=STORE_PAYLOAD_LIMIT):
        if (type(symbol_limit) is not int or type(payload_limit) is not int
                or not 1 <= symbol_limit <= SYMBOL_LIMIT or not 1024 <= payload_limit <= STORE_PAYLOAD_LIMIT):
            raise ValueError("Unsupported observation capacity")
        self.path = str(path)
        self.symbol_limit = symbol_limit
        self.payload_limit = payload_limit
        self._connection = None
        self._lock = threading.RLock()

    def _db(self):
        if self._connection is None:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            deadline = time.monotonic() + 2
            while True:
                connection = sqlite3.connect(self.path, timeout=2, check_same_thread=False)
                try:
                    connection.execute("PRAGMA journal_mode=WAL")
                    connection.execute("PRAGMA synchronous=FULL")
                    connection.execute("PRAGMA journal_size_limit=33554432")
                    connection.execute("CREATE TABLE IF NOT EXISTS observations ("
                                       "ticker TEXT PRIMARY KEY, received REAL NOT NULL, payload TEXT NOT NULL, "
                                       "sha256 TEXT NOT NULL, bytes INTEGER NOT NULL)")
                    connection.execute("CREATE TABLE IF NOT EXISTS observation_totals ("
                                       "id INTEGER PRIMARY KEY CHECK(id=1), symbols INTEGER NOT NULL, bytes INTEGER NOT NULL, retired_before REAL)")
                    connection.execute("INSERT OR IGNORE INTO observation_totals SELECT 1,COUNT(*),COALESCE(SUM(bytes),0),NULL FROM observations")
                    connection.commit()
                    self._connection = connection
                    break
                except BaseException as exc:
                    connection.close()
                    if (isinstance(exc, sqlite3.OperationalError)
                            and getattr(exc, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                            and time.monotonic() < deadline):
                        time.sleep(0.02)
                        continue
                    raise
        return self._connection

    @staticmethod
    def _symbol(ticker):
        if not isinstance(ticker, str) or not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,11}", ticker):
            raise ValueError("Invalid observation ticker")

    @staticmethod
    def _validate(records, received):
        if not isinstance(records, dict) or len(records) > CONTRACT_LIMIT:
            raise ValueError("Invalid observation count")
        for osi, item in records.items():
            if (not isinstance(osi, str) or not 1 <= len(osi) <= 100 or not isinstance(item, dict)
                    or set(item) != {"volume", "received_at", "volume_timestamp", "mid", "quote_timestamp", "mid_ring", "uncertain"}
                    or type(item["uncertain"]) is not bool
                    or nonnegative(item["volume"]) is None or timestamp(item["received_at"]) is None
                    or timestamp(item["received_at"]) > received
                    or any(item[key] is not None and timestamp(item[key]) is None
                           for key in ("volume_timestamp", "quote_timestamp"))
                    or item["mid"] is not None and nonnegative(item["mid"]) is None
                    or not isinstance(item["mid_ring"], list) or len(item["mid_ring"]) > 60
                    or any(nonnegative(value) is None for value in item["mid_ring"])):
                raise ValueError("Invalid saved observation")

    def read(self, ticker):
        self._symbol(ticker)
        with self._lock:
            row = self._db().execute("SELECT received,payload,sha256 FROM observations WHERE ticker=?", (ticker,)).fetchone()
            if row is None:
                return None
            if hashlib.sha256(row[1].encode()).hexdigest() != row[2]:
                raise ValueError("Saved observations failed integrity check")
            records = json.loads(row[1])
            self._validate(records, row[0])
            return dict(received_at=row[0], records=records)

    def write(self, ticker, received_at, records):
        self._symbol(ticker)
        now = timestamp(received_at)
        if now is None or not isinstance(records, dict) or len(records) > CONTRACT_LIMIT:
            raise ValueError("Invalid observation record")
        self._validate(records, now)
        payload = json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False)
        size = len(payload.encode())
        if size > PAYLOAD_LIMIT:
            raise ValueError("Observation record exceeds per-name capacity")
        hashed = hashlib.sha256(payload.encode()).hexdigest()
        with self._lock:
            connection = self._db()
            try:
                connection.execute("BEGIN IMMEDIATE")
                count, used, retired = connection.execute("SELECT symbols,bytes,retired_before FROM observation_totals WHERE id=1").fetchone()
                day_start = datetime.fromtimestamp(now, ET).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
                if retired is not None and now < retired:
                    connection.rollback()
                    return "out_of_order"
                if retired is None or day_start > retired:
                    expired_count, expired_bytes = connection.execute(
                        "SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM observations WHERE received<?", (day_start,)).fetchone()
                    connection.execute("DELETE FROM observations WHERE received<?", (day_start,))
                    count, used = count - expired_count, used - expired_bytes
                    connection.execute("UPDATE observation_totals SET symbols=?,bytes=?,retired_before=? WHERE id=1",
                                       (count, used, day_start))
                old = connection.execute("SELECT received,sha256,bytes FROM observations WHERE ticker=?", (ticker,)).fetchone()
                if old and now <= old[0]:
                    connection.rollback()
                    return "unchanged" if now == old[0] and hashed == old[1] else "out_of_order"
                if (old is None and count >= self.symbol_limit) or used - (old[2] if old else 0) + size > self.payload_limit:
                    connection.rollback()
                    return "capacity_reached"
                connection.execute("INSERT INTO observations VALUES (?,?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET "
                                   "received=excluded.received,payload=excluded.payload,sha256=excluded.sha256,bytes=excluded.bytes",
                                   (ticker, now, payload, hashed, size))
                connection.execute("UPDATE observation_totals SET symbols=?,bytes=? WHERE id=1",
                                   (count + int(old is None), used - (old[2] if old else 0) + size))
                connection.commit()
                return "saved"
            except BaseException:
                connection.rollback()
                raise

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
