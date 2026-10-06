"""
backend/services/account_risk_ledger.py — account-bound risk ledger (S2/S7).

Builds a deterministic risk snapshot from INJECTED verified broker facts
(positions, orders, fills/fees, buying power). Facts arrive as data; this
module never calls a broker, never invents missing values:

- Every fill REQUIRES fill_id/symbol/side/quantity/price/fees/ts/multiplier.
  Missing fees, timestamps, or units refuse (RISK_FACTS_INCOMPLETE) — they
  never default to zero.
- Fills normalize ONCE (dedup by fill_id, chronological sort) and a single
  FIFO walk carries lot basis across days, so previous-day lots sold today
  attribute correctly and duplicates never double-count anywhere.
- Daily loss is NET of same-day fill fees: commissions count against the
  day (gross gains would understate a loss — fail-open). Fees on fills
  timestamped today reduce today's realized figure.
- Short (negative-quantity) positions are refused: the FIFO model prices
  long lots only, and silently mispricing a short book would be worse
  than refusing admission until shorts are modeled.
- Exposure and premiums include the contract multiplier declared per
  position/fill (options notional is qty × price × multiplier).
- Open positions REQUIRE market_price and multiplier; orders REQUIRE
  order_id and non-empty status (missing status refuses; UNKNOWN state
  refuses entry separately).
- No live calls, no activation, no venue flags.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

RISK_LEDGER_VERSION = "account-risk-ledger.v1"

__all__ = ["RISK_LEDGER_VERSION", "evaluate_account_risk", "check_affordability"]


def _dec(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{field} must be a Decimal string or int")
    from decimal import InvalidOperation

    try:
        d = Decimal(value) if isinstance(value, int) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} is not decimal: {value!r}") from exc
    if isinstance(value, float) or not d.is_finite():
        raise ValueError(f"{field} must be finite decimal, not float")
    return d


def evaluate_account_risk(
    facts: dict[str, Any], policy: dict[str, Any], today: str | None = None,
    require_complete_policy: bool = False,
) -> dict[str, Any]:
    """Evaluate account risk from injected facts against an account policy.

    facts: {buying_power, positions: [{symbol, quantity, market_price,
             multiplier}], open_orders: [{order_id, status, ...}],
            fills: [{fill_id, symbol, side, quantity, price, fees, ts,
             multiplier}]}
    policy: {max_positions?, max_notional?, max_daily_loss?, today?}
    require_complete_policy: refuse POLICY_INCOMPLETE unless all three
      ceilings are explicitly present (commissioned path; no silent absence).
    Returns ok True with snapshot, or ok False with RISK_FACTS_INCOMPLETE /
    UNKNOWN_ORDERS_PENDING / RISK_LIMIT_EXCEEDED (+breach codes) / POLICY_*.
    Never raises.
    """
    try:
        return _evaluate(facts, policy, today, require_complete_policy)
    except (ValueError, TypeError) as exc:
        reason = str(exc)
        if reason.startswith("RISK_") or reason.startswith("POLICY_") or reason.startswith("UNKNOWN_"):
            code, _, detail = reason.partition(":")
            return {"ok": False, "reason": code,
                    "detail": detail.strip() or code,
                    "version": RISK_LEDGER_VERSION}
        return {"ok": False, "reason": "RISK_FACTS_INCOMPLETE",
                "detail": str(exc), "version": RISK_LEDGER_VERSION}


def _refuse(code: str, detail: str = "") -> ValueError:
    return ValueError(f"{code}:{detail or code}")


def _evaluate(
    facts: dict[str, Any], policy: dict[str, Any], today: str | None,
    require_complete_policy: bool,
) -> dict[str, Any]:
    if not isinstance(facts, dict):
        raise _refuse("RISK_FACTS_INCOMPLETE", "facts must be a dict")
    for field in ("buying_power", "positions", "open_orders", "fills"):
        if facts.get(field) is None:
            raise _refuse("RISK_FACTS_INCOMPLETE", f"missing fact: {field}")
    if not isinstance(facts["positions"], list):
        raise _refuse("RISK_FACTS_INCOMPLETE", "positions must be a list")
    if not isinstance(facts["open_orders"], list):
        raise _refuse("RISK_FACTS_INCOMPLETE", "open_orders must be a list")
    if not isinstance(facts["fills"], list):
        raise _refuse("RISK_FACTS_INCOMPLETE", "fills must be a list")
    if not isinstance(policy, dict):
        raise _refuse("RISK_FACTS_INCOMPLETE", "policy must be a dict")
    if require_complete_policy:
        for field in ("max_positions", "max_notional", "max_daily_loss"):
            if policy.get(field) is None:
                raise _refuse("POLICY_INCOMPLETE", f"required ceiling absent: {field}")
    buying_power = _dec(facts["buying_power"], "buying_power")

    for order in facts["open_orders"]:
        if not isinstance(order, dict) or not order.get("order_id"):
            raise _refuse("RISK_FACTS_INCOMPLETE", "open order without order_id")
        if not str(order.get("status") or "").strip():
            raise _refuse("RISK_FACTS_INCOMPLETE",
                          f"order {order.get('order_id')} missing status")
        if str(order.get("status") or "").upper() == "UNKNOWN":
            return {"ok": False, "reason": "UNKNOWN_ORDERS_PENDING",
                    "detail": f"order {order.get('order_id')} state unknown",
                    "version": RISK_LEDGER_VERSION}

    symbols: set[str] = set()
    exposure = Decimal("0")
    for pos in facts["positions"]:
        if not isinstance(pos, dict):
            raise _refuse("RISK_FACTS_INCOMPLETE", "position must be a dict")
        symbol = str(pos.get("symbol") or "").strip()
        if not symbol:
            raise _refuse("RISK_FACTS_INCOMPLETE", "position without symbol")
        qty = _dec(pos.get("quantity"), f"{symbol}.quantity")
        if qty == 0:
            continue
        if qty < 0:
            raise _refuse("RISK_FACTS_INCOMPLETE",
                          f"short position {symbol} unsupported by the long-lot model")
        symbols.add(symbol)
        if pos.get("market_price") is None:
            raise _refuse("RISK_FACTS_INCOMPLETE",
                          f"missing market_price for open {symbol}")
        if pos.get("multiplier") is None:
            raise _refuse("RISK_FACTS_INCOMPLETE",
                          f"missing multiplier for open {symbol}")
        market = _dec(pos.get("market_price"), f"{symbol}.market_price")
        mult = _dec(pos.get("multiplier"), f"{symbol}.multiplier")
        if mult <= 0:
            raise _refuse("RISK_FACTS_INCOMPLETE", f"{symbol}.multiplier not positive")
        exposure += abs(qty) * market * mult

    events, duplicates = _normalize_fills(facts["fills"])
    premium_paid = Decimal("0")
    premium_received = Decimal("0")
    fees_paid = Decimal("0")
    realized = Decimal("0")
    day_realized: dict[str, Decimal] = {}
    day_fees: dict[str, Decimal] = {}
    lots: dict[str, list] = {}
    for ev in events:
        symbol, side, qty, price, fee, ts, mult = ev
        fees_paid += fee
        day = ts[:10]
        day_fees[day] = day_fees.get(day, Decimal("0")) + fee
        amount = qty * price * mult
        if side == "BUY":
            premium_paid += amount
            lots.setdefault(symbol, []).append([qty, price, mult])
        else:
            premium_received += amount
            need = qty
            book = lots.setdefault(symbol, [])
            while need > 0 and book:
                lot_qty, lot_price, lot_mult = book[0]
                take = min(lot_qty, need)
                gain = take * (price - lot_price) * lot_mult
                realized += gain
                day_realized[day] = day_realized.get(day, Decimal("0")) + gain
                lot_qty -= take
                need -= take
                if lot_qty == 0:
                    book.pop(0)
                else:
                    book[0][0] = lot_qty
            if need > 0:
                raise _refuse("RISK_FACTS_INCOMPLETE",
                              f"sell of uncovered quantity at {ts}")
    snapshot = {
        "buying_power": str(buying_power),
        "n_open_positions": len(symbols),
        "n_open_orders": len(facts["open_orders"]),
        "exposure": str(exposure),
        "premium_paid": str(premium_paid),
        "premium_received": str(premium_received),
        "fees_paid": str(fees_paid),
        "realized": str(realized),
        "duplicate_fills_ignored": duplicates,
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
        # NET day figure: same-day fill fees count against the day, so a
        # gross gain can never hide a net loss from the loss gate.
        loss = (day_realized.get(str(day), Decimal("0"))
                - day_fees.get(str(day), Decimal("0")))
        snapshot["day_realized"] = str(loss)
        snapshot["day_fees"] = str(day_fees.get(str(day), Decimal("0")))
        if loss < 0 and abs(loss) > Decimal(str(max_daily_loss)):
            breaches.append("RISK_DAILY_LOSS_EXCEEDED")
    if breaches:
        return {"ok": False, "reason": breaches[0], "detail": "; ".join(breaches),
                "snapshot": snapshot, "version": RISK_LEDGER_VERSION}
    return {"ok": True, "snapshot": snapshot, "version": RISK_LEDGER_VERSION}


def _normalize_fills(fills: list[dict[str, Any]]) -> tuple[list[tuple], int]:
    """Validate, dedup (once) and chronologically sort fills.

    Returns (events, duplicate_count) where each event is
    (symbol, side, qty, price, fee, ts, mult). Raises _refuse on any
    missing/invalid fact — never defaults.
    """
    seen: set[str] = set()
    duplicates = 0
    events: list[tuple] = []
    for fill in fills:
        if not isinstance(fill, dict):
            raise _refuse("RISK_FACTS_INCOMPLETE", "fill must be a dict")
        fill_id = str(fill.get("fill_id") or "").strip()
        if not fill_id:
            raise _refuse("RISK_FACTS_INCOMPLETE", "fill without fill_id")
        if fill_id in seen:
            duplicates += 1
            continue
        seen.add(fill_id)
        symbol = str(fill.get("symbol") or "").strip()
        if not symbol:
            raise _refuse("RISK_FACTS_INCOMPLETE", "fill without symbol")
        side = str(fill.get("side") or "").upper()
        if side not in ("BUY", "SELL"):
            raise _refuse("RISK_FACTS_INCOMPLETE", f"fill {fill_id} bad side")
        qty = _dec(fill.get("quantity"), f"fill {fill_id}.quantity")
        if qty <= 0:
            raise _refuse("RISK_FACTS_INCOMPLETE", f"fill {fill_id} quantity not positive")
        price = _dec(fill.get("price"), f"fill {fill_id}.price")
        if price <= 0:
            raise _refuse("RISK_FACTS_INCOMPLETE", f"fill {fill_id} price not positive")
        if fill.get("fees") is None:
            raise _refuse("RISK_FACTS_INCOMPLETE", f"fill {fill_id} missing fees")
        fee = _dec(fill.get("fees"), f"fill {fill_id}.fees")
        if fee < 0:
            raise _refuse("RISK_FACTS_INCOMPLETE", f"fill {fill_id} negative fees")
        ts = str(fill.get("ts") or "").strip()
        if not ts:
            raise _refuse("RISK_FACTS_INCOMPLETE", f"fill {fill_id} missing ts")
        if fill.get("multiplier") is None:
            raise _refuse("RISK_FACTS_INCOMPLETE", f"fill {fill_id} missing multiplier")
        mult = _dec(fill.get("multiplier"), f"fill {fill_id}.multiplier")
        if mult <= 0:
            raise _refuse("RISK_FACTS_INCOMPLETE", f"fill {fill_id} multiplier not positive")
        events.append((symbol, side, qty, price, fee, ts, mult))
    events.sort(key=lambda ev: ev[5])
    return events, duplicates


def check_affordability(
    intent: dict[str, Any], facts: dict[str, Any],
) -> dict[str, Any]:
    """Proposed-intent affordability against buying power (S7).

    proposed premium (qty × limit × multiplier, or budget preflight_total
    when larger) + open-order reservation (non-terminal orders need
    quantity/limit_price/multiplier; missing reservation facts refuse) must
    fit buying power, else INSUFFICIENT_BUDGET. Filled/canceled orders do
    not reserve. Never raises (returns refusal dicts).
    """
    try:
        if not isinstance(intent, dict) or not isinstance(facts, dict):
            raise _refuse("RISK_FACTS_INCOMPLETE", "intent/facts must be dicts")
        contract = intent.get("contract") or {}
        qty = _dec(intent.get("quantity"), "intent.quantity")
        if qty <= 0:
            raise _refuse("RISK_FACTS_INCOMPLETE", "intent quantity not positive")
        limit = _dec(intent.get("limit_price"), "intent.limit_price")
        mult = _dec(contract.get("multiplier"), "intent.multiplier")
        if limit <= 0 or mult <= 0:
            raise _refuse("RISK_FACTS_INCOMPLETE", "intent limit/multiplier not positive")
        proposed = qty * limit * mult
        budget = intent.get("budget") or {}
        if budget.get("preflight_total") is not None:
            preflight_total = _dec(budget.get("preflight_total"), "intent.budget.preflight_total")
            if preflight_total > proposed:
                proposed = preflight_total
        buying_power = _dec(facts.get("buying_power"), "buying_power")
        reserved = Decimal("0")
        for order in facts.get("open_orders") or []:
            if not isinstance(order, dict):
                raise _refuse("RISK_FACTS_INCOMPLETE", "open order must be a dict")
            if str(order.get("status") or "").upper() in ("FILLED", "REJECTED", "CANCELED"):
                continue
            for field in ("quantity", "limit_price", "multiplier"):
                if order.get(field) is None:
                    raise _refuse(
                        "RISK_FACTS_INCOMPLETE",
                        f"open order {order.get('order_id')} missing {field} for reservation")
            reserved += (_dec(order.get("quantity"), "order.quantity")
                         * _dec(order.get("limit_price"), "order.limit_price")
                         * _dec(order.get("multiplier"), "order.multiplier"))
        total = proposed + reserved
        if total > buying_power:
            return {"ok": False, "reason": "INSUFFICIENT_BUDGET",
                    "detail": f"proposed {proposed} + reserved {reserved} exceeds "
                              f"buying power {buying_power}",
                    "version": RISK_LEDGER_VERSION}
        return {"ok": True, "proposed": str(proposed), "reserved": str(reserved),
                "buying_power": str(buying_power), "version": RISK_LEDGER_VERSION}
    except (ValueError, TypeError) as exc:
        reason = str(exc)
        if reason.startswith("RISK_") or reason.startswith("POLICY_") or reason.startswith("UNKNOWN_"):
            code, _, detail = reason.partition(":")
            return {"ok": False, "reason": code,
                    "detail": (detail.strip() or code)[:300],
                    "version": RISK_LEDGER_VERSION}
        return {"ok": False, "reason": "RISK_FACTS_INCOMPLETE",
                "detail": reason[:300], "version": RISK_LEDGER_VERSION}
