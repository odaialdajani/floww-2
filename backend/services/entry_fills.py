"""Confirmed entry quantities only; no polling, guessed prices, or broker I/O."""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation


def confirmed_entry_fill(order, requested_qty, symbol, side):
    """Validate cumulative filled quantity independently of acceptance status."""
    result = {"journal_status": "unconfirmed_fill", "quantity": None,
              "entry_price": None, "unfilled_qty": None}
    if not isinstance(order, dict):
        return result
    try:
        requested = Decimal(str(requested_qty))
        executed = Decimal(str(order.get("filled_qty")))
        if (not requested.is_finite() or requested <= 0
                or not executed.is_finite() or executed < 0 or executed > requested):
            return result
        if (not order.get("id") or str(order.get("symbol", "")).upper() != str(symbol).upper()
                or str(order.get("side", "")).lower() != str(side).lower()
                or Decimal(str(order.get("qty"))) != requested):
            return result
        result["unfilled_qty"] = str(requested - executed)
        if executed == 0:
            result["journal_status"] = "pending_fill"
            return result
        if isinstance(order.get("filled_avg_price"), bool):
            return result
        price = float(order.get("filled_avg_price"))
        if not math.isfinite(price) or price <= 0:
            return result
    except (ValueError, TypeError, InvalidOperation, OverflowError):
        return result
    return {"journal_status": "confirmed_fill" if executed == requested else "partial_fill",
            "quantity": float(executed), "entry_price": price,
            "unfilled_qty": str(requested - executed)}


def journal_confirmed_entry(engine, seed, order, requested_qty, symbol, side):
    """Insert one known fill per venue order; changed totals require reconciliation.

    The existing journal has no cumulative entry reconciliation lifecycle. A
    later changed snapshot cannot create a second holding or silently rewrite
    an already reserved/closed trade. It returns reconciliation_required.
    """
    from services.journal_store import _to_db_row

    fill = confirmed_entry_fill(order, requested_qty, symbol, side)
    if not isinstance(order, dict) or not order.get("id"):
        return fill
    key = "alpaca-order:" + str(order["id"])
    with engine._conn_lock:
        conn = engine._conn
        existing = conn.execute("SELECT quantity,entry_price,ticker,type,action,strike,expiry "
                                "FROM flow_journal_trades WHERE ckey=?", [key]).fetchall()
        if fill["quantity"] is None:
            # A zero/unknown snapshot cannot erase a previously known execution.
            return {**fill, "journal_status": "reconciliation_required" if existing else fill["journal_status"],
                    "journal_added": 0}
        row = _to_db_row({**seed, "ckey": key, "broker_order_id": key,
            "quantity": str(Decimal(str(order["filled_qty"]))), "entry_price": fill["entry_price"],
            "entry_date": str(order.get("filled_at") or "")})
        if existing:
            expected = (row["quantity"], row["entry_price"], row["ticker"], row["type"],
                        row["action"], row["strike"], row["expiry"])
            same = (len(existing) == 1
                    and Decimal(str(existing[0][0])) == Decimal(expected[0])
                    and existing[0][1:] == expected[1:])
            return {**fill, "journal_status": fill["journal_status"] if same else "reconciliation_required",
                    "journal_added": 0}
        columns = tuple(row)
        conn.execute(f"INSERT INTO flow_journal_trades ({','.join(columns)}) "
                     f"VALUES ({','.join('?' for _ in columns)})", [row[k] for k in columns])
    return {**fill, "journal_added": 1}
