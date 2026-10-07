"""Latest bounded, dated Public scan snapshots for browsing, never live alerts.

Each name retains its own successful rows and original quote/receipt clocks.
Failures are separate checks; they cannot relabel or erase earlier evidence.
There is no historical tape or reconstruction from today's chain.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from pathlib import Path

from services.scan_observations import timestamp

SYMBOL_LIMIT = 20_000
ROWS_PER_SYMBOL = 120
SYMBOL_PAYLOAD_LIMIT = 256 * 1024
STORE_PAYLOAD_LIMIT = 512 * 1024 * 1024
FRESH_RECEIPT_SECONDS = 60
DEFAULT_MAX_AGE_SECONDS = 7 * 86400
LEGACY_SYMBOL_LIMIT = 500
LEGACY_ROWS_PER_SYMBOL = 3


def _key(row):
    return f"{row[0]}|{row[2]}|{float(row[3]):g}|{row[4]}"


def _age(stamp, now):
    value = timestamp(stamp)
    if value is None:
        return None, "unknown"
    if value > now:
        return None, "future"
    return now - value, "known"


class PublicScanObservations:
    def __init__(self, path, *, symbol_limit=SYMBOL_LIMIT, payload_limit=STORE_PAYLOAD_LIMIT):
        if (type(symbol_limit) is not int or not 1 <= symbol_limit <= SYMBOL_LIMIT
                or type(payload_limit) is not int or not 1024 <= payload_limit <= STORE_PAYLOAD_LIMIT):
            raise ValueError("Unsupported dated observation capacity")
        self.path = str(path)
        self.symbol_limit = symbol_limit
        self.payload_limit = payload_limit
        self._connection = None
        self._lock = threading.RLock()

    def _db(self):
        if self._connection is None:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=2, check_same_thread=False)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=FULL")
                conn.execute("PRAGMA journal_size_limit=33554432")
                conn.executescript(
                    "CREATE TABLE IF NOT EXISTS observed_stock (ticker TEXT PRIMARY KEY, received REAL NOT NULL, "
                    "detail TEXT NOT NULL, bytes INTEGER NOT NULL);"
                    "CREATE TABLE IF NOT EXISTS observed_contract (ticker TEXT NOT NULL, ordinal INTEGER NOT NULL, "
                    "volume REAL NOT NULL, expiry TEXT NOT NULL, kind TEXT NOT NULL, row_json TEXT NOT NULL, "
                    "extra_json TEXT, PRIMARY KEY(ticker,ordinal));"
                    "CREATE INDEX IF NOT EXISTS observed_contract_volume ON observed_contract(volume);"
                    "CREATE INDEX IF NOT EXISTS observed_contract_expiry ON observed_contract(expiry);"
                    "CREATE TEMP TABLE IF NOT EXISTS dated_legacy_contract (ticker TEXT NOT NULL, ordinal INTEGER NOT NULL, "
                    "volume REAL NOT NULL, expiry TEXT NOT NULL, kind TEXT NOT NULL, row_json TEXT NOT NULL, "
                    "extra_json TEXT, received REAL NOT NULL);"
                    "CREATE TABLE IF NOT EXISTS observed_check (ticker TEXT PRIMARY KEY, checked REAL NOT NULL, "
                    "status TEXT NOT NULL, reason TEXT);"
                )
            except BaseException:
                conn.close()
                raise
            self._connection = conn
        return self._connection

    def record_attempt(self, ticker, checked, status, reason=None):
        if (not isinstance(ticker, str) or not 1 <= len(ticker) <= 12 or timestamp(checked) is None
                or status not in ("ok", "failed", "deferred", "capacity")):
            raise ValueError("Invalid dated scan check")
        reason = str(reason)[:200] if reason is not None else None
        with self._lock, self._db() as conn:
            exists = conn.execute("SELECT 1 FROM observed_check WHERE ticker=?", (ticker,)).fetchone()
            if not exists and conn.execute("SELECT COUNT(*) FROM observed_check").fetchone()[0] >= self.symbol_limit:
                return "symbol_capacity"
            conn.execute("INSERT INTO observed_check VALUES (?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET "
                         "checked=excluded.checked,status=excluded.status,reason=excluded.reason "
                         "WHERE excluded.checked>observed_check.checked", (ticker, checked, status, reason))
        return "saved"

    def save(self, ticker, pack, *, scope):
        if not isinstance(ticker, str) or not 1 <= len(ticker) <= 12:
            raise ValueError("Valid dated observation stock required")
        received = timestamp(pack.get("received_ts"))
        if received is None or pack.get("status") != "ok" or not isinstance(scope, str) or len(scope) > 100:
            raise ValueError("Successful dated scan receipt and scope required")
        rows = pack.get("rows", [])
        if len(rows) > ROWS_PER_SYMBOL:
            raise ValueError("Dated snapshot exceeds contract bound")
        extras = pack.get("extras") or {}
        encoded_rows = []
        missing_extras = 0
        missing_volume_clocks = 0
        identities = set()
        for ordinal, row in enumerate(rows):
            if (not isinstance(row, list) or len(row) != 10 or row[0] != ticker
                    or not isinstance(row[4], str) or row[2] not in ("call", "put")
                    or type(row[5]) not in (int, float) or not math.isfinite(row[5]) or row[5] < 0):
                raise ValueError("Invalid dated scan contract")
            identity = _key(row)
            if identity in identities:
                raise ValueError("Duplicate dated contract identity")
            identities.add(identity)
            extra = extras.get(identity)
            missing_extras += not isinstance(extra, dict)
            missing_volume_clocks += not isinstance(extra, dict) or timestamp(extra.get("volume_source_time")) is None
            encoded_rows.append((ticker, ordinal, row[5], row[4], row[2], json.dumps(row, allow_nan=False),
                                 json.dumps(extra, allow_nan=False) if isinstance(extra, dict) else None))
        selection = pack.get("selection") or {}
        partial = bool(selection.get("rows_truncated") or pack.get("history_status") != "available"
                       or pack.get("contract_conflicts") or missing_extras or missing_volume_clocks)
        detail = dict(received_at=received, event_time=pack.get("event_time"), scope=scope,
                      source=pack.get("source"), expiries_checked=pack.get("expiries_checked"),
                      expiries=pack.get("expiries"), max_expiries=pack.get("max_expiries"), selection=selection,
                      retained_rows=len(rows), rows_per_ticker_cap=ROWS_PER_SYMBOL,
                      history_status=pack.get("history_status", "unavailable"),
                      history_capped=bool(pack.get("history_capped")), contract_conflicts=pack.get("contract_conflicts", 0),
                      missing_quote_extras=missing_extras, missing_volume_source_clocks=missing_volume_clocks,
                      data_status="partial" if partial else "available", live=False, trade_eligible=False)
        encoded_detail = json.dumps(detail, allow_nan=False)
        size = len(encoded_detail.encode()) + sum(len(item[5].encode()) + len((item[6] or "").encode()) for item in encoded_rows)
        if size > SYMBOL_PAYLOAD_LIMIT:
            return "payload_capacity"
        with self._lock:
            conn = self._db()
            try:
                conn.execute("BEGIN IMMEDIATE")
                previous = conn.execute("SELECT received,bytes FROM observed_stock WHERE ticker=?", (ticker,)).fetchone()
                if previous is not None and received <= previous[0]:
                    conn.rollback()
                    return "unchanged"
                if previous is None and conn.execute("SELECT COUNT(*) FROM observed_stock").fetchone()[0] >= self.symbol_limit:
                    conn.rollback()
                    return "symbol_capacity"
                used = conn.execute("SELECT COALESCE(SUM(bytes),0) FROM observed_stock").fetchone()[0]
                if used - (previous[1] if previous else 0) + size > self.payload_limit:
                    conn.rollback()
                    return "payload_capacity"
                conn.execute("INSERT INTO observed_stock VALUES (?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET "
                             "received=excluded.received,detail=excluded.detail,bytes=excluded.bytes",
                             (ticker, received, encoded_detail, size))
                conn.execute("DELETE FROM observed_contract WHERE ticker=?", (ticker,))
                conn.executemany("INSERT INTO observed_contract VALUES (?,?,?,?,?,?,?)", encoded_rows)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        self.record_attempt(ticker, received, "ok")
        return "saved"

    def page(self, *, now=None, universe=None, offset=0, limit=100, ticker=None, min_volume=0,
             expiry=None, contract_type=None, age="all", scope=None, max_age_seconds=DEFAULT_MAX_AGE_SECONDS, legacy_records=None, order="stocks"):
        now = time.time() if now is None else now
        if (timestamp(now) is None or type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 500
                or age not in ("all", "recent", "stale") or order not in ("stocks", "received") or not 0 <= min_volume <= 1e12
                or not 60 <= max_age_seconds <= DEFAULT_MAX_AGE_SECONDS):
            raise ValueError("Unsupported dated observation filter")
        allowed = set(universe) if universe is not None else None
        with self._lock:
            conn = self._db()
            conn.execute("BEGIN")
            try:
                stocks = conn.execute("SELECT s.ticker,s.received,s.detail,c.checked,c.status,c.reason "
                                      "FROM observed_stock s LEFT JOIN observed_check c ON c.ticker=s.ticker").fetchall()
                checks = conn.execute("SELECT ticker,status FROM observed_check").fetchall()
                stored = conn.execute("SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM observed_stock").fetchone()
                metadata = {}
                for name, received, detail_json, checked, status, reason in stocks:
                    if allowed is not None and name not in allowed:
                        continue
                    detail = json.loads(detail_json)
                    receipt_age, receipt_clock = _age(received, now)
                    source_age, source_clock = _age(detail.get("event_time"), now)
                    metadata[name] = {**detail, "receipt_age_seconds": receipt_age, "receipt_clock_status": receipt_clock,
                                      "source_age_seconds": source_age, "source_clock_status": source_clock,
                                      "latest_attempt_at": checked, "latest_attempt_status": status,
                                      "latest_attempt_reason": reason}
                # Legacy examples use their actual rows and receipt only. Rich
                # snapshots (including newer zero results) always win by stock.
                conn.execute("DELETE FROM dated_legacy_contract")
                legacy_metadata = {}
                check_details = {name: (checked, status, reason) for name, checked, status, reason in
                                 conn.execute("SELECT ticker,checked,status,reason FROM observed_check")}
                for legacy in (legacy_records or [])[:LEGACY_SYMBOL_LIMIT]:
                    name = legacy.get("ticker")
                    if name in metadata or allowed is not None and name not in allowed:
                        continue
                    received = timestamp(legacy.get("received_at"))
                    receipt_age, receipt_clock = _age(received, now)
                    if received is None or receipt_age is None or receipt_age > max_age_seconds:
                        continue
                    examples, seen = [], set()
                    for example in (legacy.get("examples") or [])[:LEGACY_ROWS_PER_SYMBOL]:
                        try:
                            valid = (isinstance(example, list) and len(example) >= 7 and example[0] == name
                                     and example[2] in ("call", "put") and isinstance(example[4], str)
                                     and type(example[5]) in (int, float) and math.isfinite(example[5]) and example[5] >= 0)
                            identity = _key(example) if valid else None
                            if identity is None or identity in seen:
                                continue
                            encoded = json.dumps(example, allow_nan=False)
                        except (ValueError, TypeError):
                            continue
                        seen.add(identity)
                        examples.append(example)
                        conn.execute("INSERT INTO dated_legacy_contract VALUES (?,?,?,?,?,?,NULL,?)",
                                     (name, len(examples)-1, example[5], example[4], example[2], encoded, received))
                    checked, status, reason = check_details.get(name, (None, None, None))
                    original_count = legacy.get("contracts") if type(legacy.get("contracts")) is int else None
                    legacy_metadata[name] = dict(received_at=received, event_time=None, source=None, scope=None,
                                                 expiries_checked=None, expiries=None, max_expiries=None,
                                                 receipt_age_seconds=receipt_age, receipt_clock_status=receipt_clock,
                                                 source_age_seconds=None, source_clock_status="unknown",
                                                 retained_rows=len(examples), original_retained_rows=original_count,
                                                 selection=None, rows_per_ticker_cap=LEGACY_ROWS_PER_SYMBOL,
                                                 data_status="legacy_limited", quote_extras_available=False,
                                                 missing_quote_extras=len(examples), missing_volume_source_clocks=len(examples),
                                                 latest_attempt_at=checked, latest_attempt_status=status, latest_attempt_reason=reason,
                                                 live=False, trade_eligible=False)
                metadata.update(legacy_metadata)
                candidates = [name for name, detail in metadata.items()
                              if detail["receipt_age_seconds"] is not None and detail["receipt_age_seconds"] <= max_age_seconds
                              and (not ticker or ticker.upper() in name.upper())
                              and (not scope or detail["scope"] == scope)
                              and (age == "all" or (detail["receipt_age_seconds"] <= FRESH_RECEIPT_SECONDS) == (age == "recent"))]
                where = ["c.ticker IN (" + ",".join("?" for _ in candidates) + ")", "c.volume>=?"] if candidates else ["0", "c.volume>=?"]
                params = [*candidates, min_volume]
                if expiry:
                    where.append("c.expiry=?")
                    params.append(expiry)
                if contract_type:
                    if contract_type not in ("call", "put"):
                        raise ValueError("Unsupported dated contract type")
                    where.append("c.kind=?")
                    params.append(contract_type)
                clause = " AND ".join(where)
                source = "(SELECT c.ticker,c.ordinal,c.volume,c.expiry,c.kind,c.row_json,c.extra_json,s.received "\
                         "FROM observed_contract c JOIN observed_stock s ON s.ticker=c.ticker UNION ALL "\
                         "SELECT ticker,ordinal,volume,expiry,kind,row_json,extra_json,received FROM dated_legacy_contract) c"
                total = conn.execute("SELECT COUNT(*) FROM " + source + " WHERE " + clause, params).fetchone()[0]
                if order == "stocks":
                    # Rank qualifying contracts inside each stock before paging.
                    # Large ETF chains cannot consume the first server group.
                    query = "WITH qualifying AS (SELECT c.*,ROW_NUMBER() OVER "\
                            "(PARTITION BY c.ticker ORDER BY c.ordinal) AS stock_row FROM " + source + " WHERE " + clause + ") "\
                            "SELECT ticker,row_json,extra_json FROM qualifying "\
                            "ORDER BY stock_row,received DESC,ticker,ordinal LIMIT ? OFFSET ?"
                else:
                    query = "SELECT c.ticker,c.row_json,c.extra_json FROM " + source + " WHERE " + clause\
                            + " ORDER BY c.received DESC,c.ticker,c.ordinal LIMIT ? OFFSET ?"
                selected = conn.execute(query, [*params, limit, offset]).fetchall()
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        rows, quote_truth, row_observations = [], {}, {}
        for name, row_json, extra_json in selected:
            row = json.loads(row_json)
            rows.append(row)
            identity = _key(row)
            extra = json.loads(extra_json) if extra_json is not None else {}
            if extra_json is not None:
                quote_truth[identity] = extra
            detail = metadata[name]
            volume_age, volume_clock = _age(extra.get("volume_source_time"), now)
            quote_age, quote_clock = _age(extra.get("quote_source_time"), now)
            row_observations[identity] = dict(received_at=detail["received_at"], event_time=detail["event_time"],
                                              receipt_age_seconds=detail["receipt_age_seconds"], scope=detail["scope"], source=detail["source"],
                                              volume_source_time=extra.get("volume_source_time"),
                                              volume_source_age_seconds=volume_age, volume_clock_status=volume_clock,
                                              quote_source_time=extra.get("quote_source_time"),
                                              quote_source_age_seconds=quote_age, quote_clock_status=quote_clock,
                                              bid_source_time=extra.get("bid_source_time"), ask_source_time=extra.get("ask_source_time"),
                                              last_source_time=extra.get("last_source_time"), oi_source_time=extra.get("oi_source_time"),
                                              quote_extras_available=extra_json is not None, data_status=detail["data_status"], live=False, trade_eligible=False)
        observed = len(metadata)
        known_universe = len(allowed) if allowed is not None else None
        coverage = dict(universe=known_universe, observed_tickers=observed,
                        missing_tickers=max(0, known_universe - observed) if known_universe is not None else None,
                        available_tickers=len(candidates),
                        stale_tickers=sum(item["receipt_age_seconds"] is not None and item["receipt_age_seconds"] > FRESH_RECEIPT_SECONDS
                                          for item in metadata.values()),
                        expired_tickers=sum(item["receipt_age_seconds"] is not None and item["receipt_age_seconds"] > max_age_seconds
                                            for item in metadata.values()),
                        source_clock_unknown_tickers=sum(item["source_clock_status"] != "known" for item in metadata.values()),
                        receipt_clock_unknown_tickers=sum(item["receipt_clock_status"] != "known" for item in metadata.values()),
                        source_stale_tickers=sum(item["source_age_seconds"] is not None and item["source_age_seconds"] > FRESH_RECEIPT_SECONDS
                                                 for item in metadata.values()),
                        partial_tickers=sum(item["data_status"] in ("partial", "legacy_limited") for item in metadata.values()),
                        legacy_limited_tickers=len(legacy_metadata), legacy_retention_ticker_limit=LEGACY_SYMBOL_LIMIT,
                        legacy_examples_per_ticker_limit=LEGACY_ROWS_PER_SYMBOL,
                        legacy_pruned_names_recoverable=False,
                        zero_result_tickers=sum(item["retained_rows"] == 0 for item in metadata.values()),
                        latest_failed_tickers=sum(status == "failed" for name, status in checks if allowed is None or name in allowed),
                        deferred_tickers=sum(status == "deferred" for name, status in checks if allowed is None or name in allowed),
                        storage_capacity_tickers=sum(status == "capacity" for name, status in checks if allowed is None or name in allowed),
                        symbol_limit=self.symbol_limit, stored_tickers=stored[0], payload_bytes=stored[1],
                        payload_limit_bytes=self.payload_limit, rows_per_ticker_cap=ROWS_PER_SYMBOL,
                        capacity_covers_current_universe=known_universe is not None and known_universe <= self.symbol_limit,
                        full_contract_chains=False, complete_realtime_market=False,
                        max_age_seconds=max_age_seconds, recent_receipt_window_seconds=FRESH_RECEIPT_SECONDS,
                        retention="latest_successful_bounded_snapshot_per_ticker")
        return dict(rows=rows, quote_truth=quote_truth, row_observations=row_observations, observations_by_ticker={name: metadata[name] for name in dict.fromkeys(r[0] for r in rows)},
                    total=total, count=len(rows), offset=offset, limit=limit, order=order,
                    next_offset=offset+len(rows) if offset+len(rows) < total else None,
                    coverage=coverage, checked_at=now, source="public-scan-observations", live=False, trade_eligible=False,
                    pagination_consistency="latest snapshots may change between page reads",
                    legacy_examples_included=any(row[0] in legacy_metadata for row in rows),
                    truncated=offset+len(rows) < total)

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
