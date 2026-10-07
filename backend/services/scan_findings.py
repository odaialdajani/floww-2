"""Bounded dated findings for display only, never an input to live alerts."""

import json
import sqlite3
import threading
import time
from pathlib import Path


class ScanFindings:
    def __init__(self, path):
        self.path = str(path)
        self._connection = None
        self._lock = threading.RLock()

    def _db(self):
        if self._connection is None:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
            self._connection.execute("CREATE TABLE IF NOT EXISTS findings "
                                     "(ticker TEXT PRIMARY KEY, received REAL, payload TEXT)")
        return self._connection

    def save(self, ticker, received, rows):
        # At most three contract examples per symbol, not a historical tape.
        payload = json.dumps({"contracts": len(rows), "examples": rows[:3]}, allow_nan=False)
        with self._lock, self._db() as conn:
            conn.execute("INSERT INTO findings VALUES (?,?,?) ON CONFLICT(ticker) DO UPDATE SET "
                         "received=excluded.received,payload=excluded.payload "
                         "WHERE excluded.received>findings.received", (ticker, received, payload))
            conn.execute("DELETE FROM findings WHERE ticker NOT IN "
                         "(SELECT ticker FROM findings ORDER BY received DESC,ticker LIMIT 500)")

    def recent(self, now=None, tickers=None):
        now = time.time() if now is None else now
        allowed = set(tickers) if tickers is not None else None
        with self._lock:
            rows = self._db().execute("SELECT ticker,received,payload FROM findings "
                                      "WHERE received>=? AND received<=? "
                                      "ORDER BY received DESC,ticker LIMIT 500",
                                      (now - 7 * 86400, now)).fetchall()
        results = []
        for ticker, received, payload in rows:
            if allowed is not None and ticker not in allowed:
                continue
            item = json.loads(payload)
            if item["contracts"]:
                results.append({"ticker": ticker, "received_at": received, **item})
            if len(results) == 100:
                break
        return results

    def saved_records(self, now=None, tickers=None):
        """Read the actually retained records, beyond the old 100-result display cap.

        Original bare examples remain limited. This does not recover pruned
        names, quote extras, source clocks, or full chains.
        """
        now = time.time() if now is None else now
        allowed = set(tickers) if tickers is not None else None
        with self._lock:
            temporary = self._connection is None and self.path != ":memory:"
            if temporary:
                path = Path(self.path).resolve()
                if not path.exists():
                    return []
                conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
            else:
                conn = self._db()
            try:
                rows = conn.execute("SELECT ticker,received,payload FROM findings "
                                    "WHERE received>=? AND received<=? "
                                    "ORDER BY received DESC,ticker LIMIT 500",
                                    (now - 7 * 86400, now)).fetchall()
            finally:
                if temporary:
                    conn.close()
        return [{"ticker": ticker, "received_at": received, **json.loads(payload)}
                for ticker, received, payload in rows if allowed is None or ticker in allowed]

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
