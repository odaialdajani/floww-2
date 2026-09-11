"""Durable paper-close intent attribution. No broker I/O or guessed legacy fills.

Each close snapshots exact journal rows before submission. Binding is internal
to the close route, never accepted from reconciliation callers. The fill and
intent transition commit atomically under the journal engine's connection lock.
"""
from __future__ import annotations

import json
import math
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

_KEYS = ("ticker", "type", "action", "strike", "expiry", "entry_date")
_WHERE = " AND ".join(f"{k} IS NOT DISTINCT FROM ?" for k in _KEYS)
_FIELDS = ", ".join(_KEYS) + ", quantity, created_at, updated_at"


@contextmanager
def _transaction(engine):
    with engine._conn_lock:
        conn = engine._conn
        conn.execute("BEGIN TRANSACTION")
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_close_intents (
                    intent_id TEXT PRIMARY KEY, symbol TEXT NOT NULL,
                    order_id TEXT UNIQUE, targets TEXT NOT NULL,
                    status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT current_timestamp
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_close_exceptions (
                    symbol TEXT, order_id TEXT, reason TEXT,
                    observed_at TIMESTAMP DEFAULT current_timestamp,
                    PRIMARY KEY (symbol, order_id)
                )
            """)
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise


def journal_asset_symbol(row):
    """Exact venue instrument; option contracts never alias their underlying."""
    if row["type"] == "equity":
        return row["ticker"]
    if row["type"] not in ("call", "put"):
        return None
    try:
        expiry = datetime.strptime(row["expiry"], "%Y-%m-%d").strftime("%y%m%d")
        strike = Decimal(str(row["strike"])) * 1000
        if not strike.is_finite() or strike < 0 or strike != strike.to_integral_value():
            return None
        return f'{row["ticker"]}{expiry}{"C" if row["type"] == "call" else "P"}{int(strike):08d}'
    except (ValueError, InvalidOperation):
        return None


def _rows(conn, sql, args=None):
    result = conn.execute(sql, args or [])
    columns = [d[0] for d in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def prepare_close(engine, symbol):
    """Reserve a journal snapshot before submitting a broker close.

    Unresolved reservations block duplicate venue submissions, including the
    crash window after submit but before the returned order ID is persisted.
    """
    symbol = str(symbol).upper()
    with _transaction(engine) as conn:
        active = _rows(conn, "SELECT intent_id, status FROM paper_close_intents "
                       "WHERE symbol=? AND status NOT IN ('reconciled', 'canceled')",
                       [symbol])
        if active:
            return {**active[0], "new": False}
        candidates = _rows(conn, f"SELECT {_FIELDS} FROM flow_journal_trades "
                           "WHERE COALESCE(exit_date,'')='' AND exit_price IS NULL")
        targets = [r for r in candidates if journal_asset_symbol(r) == symbol]
        intent_id = str(uuid4())
        conn.execute("INSERT INTO paper_close_intents "
                     "(intent_id,symbol,targets,status) VALUES (?,?,?,'prepared')",
                     [intent_id, symbol, json.dumps(targets, default=str)])
        return {"intent_id": intent_id, "status": "prepared", "new": True}


def bind_close_order(engine, intent_id, order_id):
    """Bind only the order returned by the actual close submission."""
    with _transaction(engine) as conn:
        rows = _rows(conn, "SELECT order_id FROM paper_close_intents WHERE intent_id=?",
                     [intent_id])
        if not rows or not order_id:
            raise ValueError("close response missing a durable order identity")
        if rows[0]["order_id"] not in (None, str(order_id)):
            raise ValueError("close intent cannot be rebound")
        conn.execute("UPDATE paper_close_intents SET order_id=?, status='submitted' "
                     "WHERE intent_id=? AND status='prepared'", [str(order_id), intent_id])


def _result(status, reason="", closed=0):
    return {"status": status, "reason": reason, "journal_closed": closed,
            "reconciled": status == "reconciled"}


def apply_close_fill(engine, symbol, order_id, order):
    """Validate and atomically apply a fill to reserved rows, never symbol-wide."""
    symbol, order_id = str(symbol).upper(), str(order_id)
    with _transaction(engine) as conn:
        intents = _rows(conn, "SELECT * FROM paper_close_intents WHERE order_id=?", [order_id])
        if not intents or intents[0]["symbol"] != symbol:
            reason = "unmatched_close_intent"
            conn.execute("INSERT INTO paper_close_exceptions (symbol,order_id,reason) "
                         "VALUES (?,?,?) ON CONFLICT DO NOTHING", [symbol, order_id, reason])
            return _result("reconciliation_exception", reason)
        intent = intents[0]
        if intent["status"] in ("reconciled", "canceled"):
            return _result(intent["status"])
        if intent["status"] == "reconciliation_exception":
            return _result(intent["status"], intent["reason"])
        if not isinstance(order, dict):
            return _result("pending_fill", "venue_order_unavailable")
        status = str(order.get("status") or "").lower()

        def exception(reason):
            conn.execute("UPDATE paper_close_intents SET status='reconciliation_exception', "
                         "reason=? WHERE intent_id=?", [reason, intent["intent_id"]])
            return _result("reconciliation_exception", reason)

        if str(order.get("id") or "") != order_id or str(order.get("symbol") or "").upper() != symbol:
            return exception("order_identity_mismatch")
        if status in ("canceled", "expired", "rejected"):
            # Terminal status does not imply zero execution. Releasing a partial
            # close would allow another submission against an unchanged journal.
            try:
                executed = Decimal(str(order.get("filled_qty")))
            except InvalidOperation:
                return exception("terminal_fill_quantity_unknown")
            if not executed.is_finite() or executed != 0:
                return exception("terminal_fill_requires_reconciliation")
            conn.execute("UPDATE paper_close_intents SET status='canceled',reason=? "
                         "WHERE intent_id=?", [status, intent["intent_id"]])
            return _result("canceled", status)
        if status != "filled":
            return _result("pending_fill", status or "venue_status_unknown")
        targets = json.loads(intent["targets"])
        try:
            qty = sum((Decimal(str(r["quantity"])) for r in targets), Decimal(0))
            actions = {r["action"] for r in targets}
            px = float(order.get("filled_avg_price"))
            if (not targets or actions not in ({"buy"}, {"sell"})
                    or not qty.is_finite() or qty <= 0
                    or any(Decimal(str(r["quantity"])) <= 0 for r in targets)
                    or Decimal(str(order.get("qty"))) != qty
                    or Decimal(str(order.get("filled_qty"))) != qty
                    or str(order.get("side")).lower() != ("sell" if actions == {"buy"} else "buy")
                    or not math.isfinite(px) or px <= 0):
                return exception("fill_or_target_mismatch")
        except (ValueError, TypeError, InvalidOperation):
            return exception("invalid_fill")

        # Validate every target before updating any: no partial journal close.
        for row in targets:
            matches = _rows(conn, f"SELECT {_FIELDS} FROM flow_journal_trades WHERE {_WHERE} "
                            "AND COALESCE(exit_date,'')='' AND exit_price IS NULL",
                            [row[k] for k in _KEYS])
            if (len(matches) != 1 or any(str(matches[0][k]) != str(row[k])
                                       for k in ("quantity", "created_at", "updated_at"))):
                return exception("reserved_journal_row_changed")
        filled_at = order.get("filled_at") or datetime.now(UTC).isoformat()
        for row in targets:
            conn.execute(f"UPDATE flow_journal_trades SET exit_price=?, exit_date=?, "
                         f"updated_at=current_timestamp WHERE {_WHERE}",
                         [px, str(filled_at), *[row[k] for k in _KEYS]])
        conn.execute("UPDATE paper_close_intents SET status='reconciled' WHERE intent_id=?",
                     [intent["intent_id"]])
        return _result("reconciled", closed=len(targets))


def reconciliation_exceptions(engine):
    """Read existing exception records without creating schema."""
    with engine._conn_lock:
        conn = engine._conn
        tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
        result = []
        if "paper_close_exceptions" in tables:
            result.extend(_rows(conn, "SELECT symbol,order_id,reason FROM paper_close_exceptions"))
        if "paper_close_intents" in tables:
            result.extend(_rows(conn, "SELECT symbol,order_id,status,reason,intent_id "
                                "FROM paper_close_intents WHERE status!='reconciled'"))
        return result
