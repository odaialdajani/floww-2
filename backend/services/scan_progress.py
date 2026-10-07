"""Durable fair scan bookkeeping, separate from market observations and findings."""
from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import uuid
from pathlib import Path


class ScanProgress:
    def __init__(self, path, *, lease_seconds=300):
        self.path = str(path)
        self.lease_seconds = float(lease_seconds)
        if not math.isfinite(self.lease_seconds) or self.lease_seconds <= 0:
            raise ValueError("Invalid progress lease")
        self._connection = None
        self._lock = threading.RLock()

    def _db(self):
        if self._connection is None:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=2, check_same_thread=False)
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("CREATE TABLE IF NOT EXISTS scan_scope ("
                                   "scope TEXT PRIMARY KEY, pass_id INTEGER NOT NULL, sequence INTEGER NOT NULL, "
                                   "started REAL NOT NULL, last_complete REAL, directory_at REAL)")
                connection.execute("CREATE TABLE IF NOT EXISTS scan_name ("
                                   "scope TEXT NOT NULL, ticker TEXT NOT NULL, position INTEGER NOT NULL, "
                                   "pass_done INTEGER NOT NULL DEFAULT 0, claim TEXT, claim_until REAL, "
                                   "eligible REAL NOT NULL DEFAULT 0, status TEXT, attempt_status TEXT, attempted REAL, "
                                   "received REAL, detail TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(scope,ticker))")
                # Optional bookkeeping fields from earlier progress versions
                # stay unknown until a new observation supplies them. These are
                # our own progress tables, never historical market tables.
                scope_columns = {row[1] for row in connection.execute("PRAGMA table_info(scan_scope)")}
                name_columns = {row[1] for row in connection.execute("PRAGMA table_info(scan_name)")}
                if "directory_at" not in scope_columns:
                    connection.execute("ALTER TABLE scan_scope ADD COLUMN directory_at REAL")
                if "attempt_status" not in name_columns:
                    connection.execute("ALTER TABLE scan_name ADD COLUMN attempt_status TEXT")
                connection.commit()
            except BaseException:
                connection.close()
                raise
            self._connection = connection
        return self._connection

    @staticmethod
    def _validate(scope, names, now):
        if not isinstance(scope, str) or not 1 <= len(scope) <= 150:
            raise ValueError("Invalid progress scope")
        if not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now) or now < 0:
            raise ValueError("Invalid progress time")
        if any(not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,11}", name) for name in names):
            raise ValueError("Invalid progress ticker")

    def claim(self, scope, names, take, now, *, authoritative=True, directory_at=None):
        names = list(dict.fromkeys(names))
        self._validate(scope, names, now)
        if type(take) is not int or take < 0:
            raise ValueError("Invalid scan width")
        if directory_at is not None and (not isinstance(directory_at, (int, float)) or isinstance(directory_at, bool)
                                         or not math.isfinite(directory_at) or directory_at < 0):
            raise ValueError("Invalid directory clock")
        with self._lock:
            conn = self._db()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("INSERT OR IGNORE INTO scan_scope(scope,pass_id,sequence,started) VALUES (?,1,0,?)", (scope, now))
                pass_id, sequence, saved_directory = conn.execute("SELECT pass_id,sequence,directory_at FROM scan_scope WHERE scope=?", (scope,)).fetchone()
                existing = {row[0] for row in conn.execute("SELECT ticker FROM scan_name WHERE scope=?", (scope,))}
                accept_directory = authoritative and (saved_directory is None or directory_at is not None and directory_at >= saved_directory)
                if accept_directory:
                    conn.executemany("DELETE FROM scan_name WHERE scope=? AND ticker=?", [(scope, name) for name in existing - set(names)])
                    if directory_at is not None:
                        conn.execute("UPDATE scan_scope SET directory_at=? WHERE scope=?", (directory_at, scope))
                # New names join behind the existing outstanding queue. An
                # unavailable/empty directory cannot erase a saved pass.
                for name in names:
                    if name not in existing and (accept_directory or not existing):
                        sequence += 1
                        conn.execute("INSERT INTO scan_name(scope,ticker,position) VALUES (?,?,?)", (scope, name, sequence))
                expired = conn.execute("SELECT ticker FROM scan_name WHERE scope=? AND claim IS NOT NULL "
                                       "AND claim_until<=? ORDER BY position", (scope, now)).fetchall()
                for (name,) in expired:
                    sequence += 1
                    conn.execute("UPDATE scan_name SET claim=NULL,claim_until=NULL,position=?,eligible=0,status='interrupted' "
                                 "WHERE scope=? AND ticker=?", (sequence, scope, name))
                total, pending = conn.execute("SELECT COUNT(*),COALESCE(SUM(pass_done!=?),0) FROM scan_name WHERE scope=?",
                                              (pass_id, scope)).fetchone()
                if total and not pending:
                    pass_id += 1
                    conn.execute("UPDATE scan_scope SET pass_id=?,started=? WHERE scope=?", (pass_id, now, scope))
                candidates = conn.execute("SELECT ticker FROM scan_name WHERE scope=? AND pass_done!=? "
                                          "AND claim IS NULL AND eligible<=? ORDER BY position LIMIT ?",
                                          (scope, pass_id, now, take)).fetchall()
                token = uuid.uuid4().hex
                claims = {}
                for (name,) in candidates:
                    claims[name] = token
                    conn.execute("UPDATE scan_name SET claim=?,claim_until=? WHERE scope=? AND ticker=?",
                                 (token, now + self.lease_seconds, scope, name))
                conn.execute("UPDATE scan_scope SET sequence=? WHERE scope=?", (sequence, scope))
                conn.commit()
                return claims
            except BaseException:
                conn.rollback()
                raise

    def finish(self, scope, ticker, token, outcome, now):
        self._validate(scope, [ticker], now)
        status = outcome.get("status")
        if status not in {"ok", "failed", "deferred"}:
            raise ValueError("Invalid scan outcome")
        received = outcome.get("received_ts") if status == "ok" else None
        if status == "ok" and (not isinstance(received, (int, float)) or isinstance(received, bool)
                               or not math.isfinite(received) or now - received < -30):
            raise ValueError("Unverified successful scan receipt")
        detail = {key: outcome[key] for key in ("expiries_checked", "history_status", "history_capped",
                                              "contract_conflicts", "findings_saved", "reason") if key in outcome}
        encoded = json.dumps(detail, allow_nan=False, separators=(",", ":"))
        with self._lock:
            conn = self._db()
            try:
                conn.execute("BEGIN IMMEDIATE")
                current = conn.execute("SELECT claim,detail FROM scan_name WHERE scope=? AND ticker=?", (scope, ticker)).fetchone()
                if current is None or current[0] != token:
                    conn.rollback()
                    return False
                pass_id, sequence = conn.execute("SELECT pass_id,sequence FROM scan_scope WHERE scope=?", (scope,)).fetchone()
                if status == "deferred":
                    delay = outcome.get("retry_after", 5)
                    delay = delay if isinstance(delay, (int, float)) and not isinstance(delay, bool) and math.isfinite(delay) and delay >= 0 else 5
                    sequence += 1
                    conn.execute("UPDATE scan_name SET claim=NULL,claim_until=NULL,position=?,eligible=?,status=? "
                                 "WHERE scope=? AND ticker=?", (sequence, now + delay, status, scope, ticker))
                    conn.execute("UPDATE scan_scope SET sequence=? WHERE scope=?", (sequence, scope))
                else:
                    previous_detail = json.loads(current[1])
                    if "findings_saved" not in detail and "findings_saved" in previous_detail:
                        detail["findings_saved"] = previous_detail["findings_saved"]
                    encoded = json.dumps(detail, allow_nan=False, separators=(",", ":"))
                    conn.execute("UPDATE scan_name SET claim=NULL,claim_until=NULL,eligible=0,pass_done=?,status=?,attempt_status=?,attempted=?,"
                                 "received=CASE WHEN ? IS NULL THEN received ELSE ? END,detail=? WHERE scope=? AND ticker=?",
                                 (pass_id, status, status, now, received, received, encoded, scope, ticker))
                    pending = conn.execute("SELECT COUNT(*) FROM scan_name WHERE scope=? AND pass_done!=?", (scope, pass_id)).fetchone()[0]
                    if not pending:
                        conn.execute("UPDATE scan_scope SET last_complete=? WHERE scope=?", (now, scope))
                conn.commit()
                return True
            except BaseException:
                conn.rollback()
                raise

    def snapshot(self, scope):
        with self._lock:
            conn = self._db()
            conn.execute("BEGIN")
            try:
                result = self._snapshot(conn, scope)
                conn.commit()
                return result
            except BaseException:
                conn.rollback()
                raise

    def _snapshot(self, conn, scope):
        storage_status = "memory_only" if self.path == ":memory:" else "durable"
        state = conn.execute("SELECT pass_id,started,last_complete,directory_at FROM scan_scope WHERE scope=?", (scope,)).fetchone()
        if state is None:
            return {"status": storage_status, "pass_id": None, "universe": 0, "pending": 0, "inflight": 0,
                    "deferred": 0, "attempted_in_pass": 0, "succeeded_in_pass": 0, "failed_in_pass": 0,
                    "last_complete": None}
        pass_id, started, completed, directory_at = state
        total, pending, inflight, deferred, attempted, succeeded, failed = conn.execute(
            "SELECT COUNT(*),COALESCE(SUM(pass_done!=?),0),COALESCE(SUM(claim IS NOT NULL),0),"
            "COALESCE(SUM(pass_done!=? AND status='deferred'),0),COALESCE(SUM(pass_done=?),0),"
            "COALESCE(SUM(pass_done=? AND status='ok'),0),COALESCE(SUM(pass_done=? AND status='failed'),0) "
            "FROM scan_name WHERE scope=?", (pass_id, pass_id, pass_id, pass_id, pass_id, scope)).fetchone()
        return {"status": storage_status, "pass_id": pass_id, "universe": total, "pending": pending,
                "inflight": inflight, "deferred": deferred, "attempted_in_pass": attempted,
                "succeeded_in_pass": succeeded, "failed_in_pass": failed, "started_at": started,
                "last_complete": completed, "pass_complete": bool(total and not pending), "directory_at": directory_at,
                "pending_includes_inflight_and_deferred": True}

    def attempts(self, scope):
        with self._lock:
            rows = self._db().execute("SELECT ticker,attempt_status,attempted,detail FROM scan_name WHERE scope=? AND attempted IS NOT NULL", (scope,)).fetchall()
        return {ticker: {"status": status, "at": attempted, **json.loads(detail)} for ticker, status, attempted, detail in rows}

    def members(self, scope):
        with self._lock:
            return [row[0] for row in self._db().execute("SELECT ticker FROM scan_name WHERE scope=? ORDER BY position", (scope,))]

    def renew(self, scope, token, now):
        self._validate(scope, [], now)
        with self._lock, self._db() as conn:
            conn.execute("UPDATE scan_name SET claim_until=? WHERE scope=? AND claim=?",
                         (now + self.lease_seconds, scope, token))

    def findings_saved(self, scope, ticker, received, saved):
        with self._lock:
            conn = self._db()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT detail FROM scan_name WHERE scope=? AND ticker=? AND received=? AND attempt_status='ok'",
                                   (scope, ticker, received)).fetchone()
                if row is not None:
                    detail = json.loads(row[0])
                    detail["findings_saved"] = bool(saved)
                    conn.execute("UPDATE scan_name SET detail=? WHERE scope=? AND ticker=? AND received=?",
                                 (json.dumps(detail, allow_nan=False), scope, ticker, received))
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
