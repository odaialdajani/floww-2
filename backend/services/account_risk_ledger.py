"""
backend/services/account_risk_ledger.py — account-bound risk ledger (S2).

Builds a deterministic risk snapshot from INJECTED verified broker facts
(positions, orders, fills/fees, buying power). Facts arrive as data; this
module never calls a broker, never invents missing values:

- Absent buying power, positions, orders, fills, fee or timestamp facts are
  RISK_FACTS_INCOMPLETE — never skipped, never zero-filled.
- Unknown/stale order states refuse entry (UNKNOWN_ORDERS_PENDING).
- Realized PnL uses FIFO lot matching per symbol (exact Decimal). Open
  exposure marks to given market prices; missing market prices refuse.
- Fills deduplicate by fill_id (reported, counted once).
- No live calls, no activation, no venue flags.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

RISK_LEDGER_VERSION = "account-risk-ledger.v1"

__all__ = ["RISK_LEDGER_VERSION", "evaluate_account_risk"]


def _dec(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{field} must be a Decimal string or int")
    try:
        d = Decimal(value) if isinstance(value, int) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} is not decimal: {value!r}") from exc
    if isinstance(value, float) or not d.is_finite():
        raise ValueError(f"{field} must be finite decimal, not float")
    return d


def _positive(d: Decimal, field: str) -> Decimal:
    if d <= 0:
        raise ValueError(f"{field} must be positive")
    return d


def evaluate_account_risk(
    facts: dict[str, Any], policy: dict[str, Any], today: str | None = None,
) -> dict[str, Any]:
    """Evaluate account risk from injected facts against an account policy.

    facts: {buying_power, positions: [{symbol, quantity, market_price?}],
            open_orders: [{order_id, status, ...}], fills: [{fill_id, symbol,
            side, quantity, price, fees?, ts?}], asof?}
    policy: {max_positions?, max_notional?, max_daily_loss?, today?}
    Returns ok True with snapshot, or ok False with RISK_FACTS_INCOMPLETE /
    UNKNOWN_ORDERS_PENDING / RISK_LIMIT_EXCEEDED + detail. Never raises.
    """
    try:
        return _evaluate(facts, policy, today)
    except (ValueError, TypeError) as exc:
        return {"ok": False, "reason": "RISK_FACTS_INCOMPLETE",
                "detail": str(exc), "version": RISK_LEDGER_VERSION}


def _require_facts(facts: Any) -> dict[str, Any]:
    if not isinstance(facts, dict):
        raise ValueError("facts must be a dict")
    for field in ("buying_power", "positions", "open_orders", "fills"):
        if facts.get(field) is None:
            raise ValueError(f"missing fact: {field}")
    if not isinstance(facts["positions"], list):
        raise ValueError("positions must be a list")
    if not isinstance(facts["open_orders"], list):
        raise ValueError("open_orders must be a list")
    if not isinstance(facts["fills"], list):
        raise ValueError("fills must be a list")
    return facts


def _evaluate(
    facts: dict[str, Any], policy: dict[str, Any], today: str | None,
) -> dict[str, Any]:
    facts = _require_facts(facts)
    if not isinstance(policy, dict):
        raise ValueError("policy must be a dict")
    buying_power = _dec(facts["buying_power"], "buying_power")

    for order in facts["open_orders"]:
        if not isinstance(order, dict) or not order.get("order_id"):
            raise ValueError("open order without order_id")
        if str(order.get("status") or "").upper() == "UNKNOWN":
            return {"ok": False, "reason": "UNKNOWN_ORDERS_PENDING",
                    "detail": f"order {order.get('order_id')} state unknown",
                    "version": RISK_LEDGER_VERSION}

    symbols: set[str] = set()
    exposure = Decimal("0")
    for pos in facts["positions"]:
        if not isinstance(pos, dict):
            raise ValueError("position must be a dict")
        symbol = str(pos.get("symbol") or "").strip()
        if not symbol:
            raise ValueError("position without symbol")
        qty = _dec(pos.get("quantity"), f"{symbol}.quantity")
        if qty == 0:
            continue
        symbols.add(symbol)
        if pos.get("market_price") is None:
            raise ValueError(f"missing market_price for open {symbol}")
        market = _dec(pos.get("market_price"), f"{symbol}.market_price")
        exposure += abs(qty) * market

    seen_fills: set[str] = set()
    duplicate_fills = 0
    premium_paid = Decimal("0")
    premium_received = Decimal("0")
    fees_paid = Decimal("0")
    lots: dict[str, list] = {}
    realized = Decimal("0")
    for fill in facts["fills"]:
        if not isinstance(fill, dict):
            raise ValueError("fill must be a dict")
        fill_id = str(fill.get("fill_id") or "").strip()
        if not fill_id:
            raise ValueError("fill without fill_id")
        if fill_id in seen_fills:
            duplicate_fills += 1
            continue
        seen_fills.add(fill_id)
        symbol = str(fill.get("symbol") or "").strip()
        if not symbol:
            raise ValueError("fill without symbol")
        side = str(fill.get("side") or "").upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"fill {fill_id} bad side")
        qty = _positive(_dec(fill.get("quantity"), f"fill {fill_id}.quantity"), "quantity")
        price = _positive(_dec(fill.get("price"), f"fill {fill_id}.price"), "price")
        if fill.get("fees") is not None:
            fee = _dec(fill.get("fees"), f"fill {fill_id}.fees")
            if fee < 0:
                raise ValueError(f"fill {fill_id} negative fees")
            fees_paid += fee
        amount = qty * price
        if side == "BUY":
            premium_paid += amount
            lots.setdefault(symbol, []).append([qty, price])
        else:
            premium_received += amount
            need = qty
            book = lots.setdefault(symbol, [])
            while need > 0 and book:
                lot_qty, lot_price = book[0]
                take = min(lot_qty, need)
                realized += take * (price - lot_price)
                lot_qty -= take
                need -= take
                if lot_qty == 0:
                    book.pop(0)
                else:
                    book[0][0] = lot_qty
            if need > 0:
                raise ValueError(f"fill {fill_id} sells uncovered quantity")

    snapshot = {
        "buying_power": str(buying_power),
        "n_open_positions": len(symbols),
        "n_open_orders": len(facts["open_orders"]),
        "exposure": str(exposure),
        "premium_paid": str(premium_paid),
        "premium_received": str(premium_received),
        "fees_paid": str(fees_paid),
        "realized": str(realized),
        "duplicate_fills_ignored": duplicate_fills,
    }
    breaches: list[str] = []
    max_positions = policy.get("max_positions")
    if max_positions is not None and len(symbols) >= int(max_positions):
        breaches.append("RISK_MAX_POSITIONS_EXCEEDED")
    max_notional = policy.get("max_notional")
    if max_notional is not None and exposure > Decimal(str(max_notional)):
        breaches.append("RISK_NOTIONAL_EXCEEDED")
    max_daily_loss = policy.get("max_daily_loss")
    if max_daily_loss is not None:
        day = today or policy.get("today")
        if not day:
            return {"ok": False, "reason": "RISK_FACTS_INCOMPLETE",
                    "detail": "max_daily_loss set but no evaluation day",
                    "version": RISK_LEDGER_VERSION}
        day_loss = _day_loss(facts["fills"], str(day))
        snapshot["day_realized"] = str(day_loss)
        if day_loss < 0 and abs(day_loss) > Decimal(str(max_daily_loss)):
            breaches.append("RISK_DAILY_LOSS_EXCEEDED")
    if breaches:
        return {"ok": False, "reason": breaches[0], "detail": "; ".join(breaches),
                "snapshot": snapshot, "version": RISK_LEDGER_VERSION}
    return {"ok": True, "snapshot": snapshot, "version": RISK_LEDGER_VERSION}


def _day_loss(fills: list[dict[str, Any]], day: str) -> Decimal:
    """Realized FIFO PnL for fills timestamped on `day` (YYYY-MM-DD prefix)."""
    total = Decimal("0")
    lots: dict[str, list] = {}
    for fill in fills:
        ts = str(fill.get("ts") or "")
        if not ts.startswith(day):
            continue
        symbol = str(fill.get("symbol") or "")
        side = str(fill.get("side") or "").upper()
        qty = Decimal(str(fill.get("quantity")))
        price = Decimal(str(fill.get("price")))
        if side == "BUY":
            lots.setdefault(symbol, []).append([qty, price])
        else:
            need = qty
            book = lots.setdefault(symbol, [])
            while need > 0 and book:
                lot_qty, lot_price = book[0]
                take = min(lot_qty, need)
                total += take * (price - lot_price)
                lot_qty -= take
                need -= take
                if lot_qty == 0:
                    book.pop(0)
                else:
                    book[0][0] = lot_qty
    return total
