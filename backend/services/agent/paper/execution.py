"""Bounded internal fill mechanics, prepared but not admitted to application use.

These pure transitions assume a separately validated, human-confirmed proposal.
They do not establish research acceptance, contract metadata truth, account risk
approval, market hours, or lifecycle readiness. No route imports this module.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from decimal import Decimal

from services.agent.paper.accounting import ARITHMETIC_PRECISION, derived, exact, exact_context, simulated_fill
from services.agent.paper.repository import PaperCapacity, PaperConflict, digest, identity, validate_json

MAX_ORDERS = 24
MAX_POSITIONS = 16
MAX_FILLS_PER_ORDER = 8
MAX_QUOTES = 256
MAX_QUOTE_AGE_SECONDS = 300
EXIT_EVENTS = MAX_FILLS_PER_ORDER + 4  # Stage, cancel, close archive, opening archive.
EXIT_ORDERS = 1
EXIT_QUOTES = 8


def instant(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        raise ValueError("A valid source time is required") from None
    if result.tzinfo is None:
        raise ValueError("Source time must include its timezone")
    return result.astimezone(UTC)


def whole_quantity(value):
    if type(value) is not int or not 1 <= value <= 1_000_000:
        raise ValueError("A positive whole quantity within the supported limit is required")
    return value


def _clock(state, now):
    checked = instant(now)
    previous = state.get("checked_at")
    if previous is not None and checked < instant(previous):
        raise PaperConflict("Paper clock moved backwards; retain saved quote consumption")
    state["checked_at"] = checked.isoformat()
    return checked


def new_book(cash, *, currency):
    if currency != "USD":
        raise ValueError("Only an explicitly selected USD account is supported")
    return dict(book_version=1, currency=currency, cash=str(exact(cash, positive=True)),
                initial_cash=str(exact(cash, positive=True)), realized_result="0",
                next_order_sequence=1, orders={}, positions={}, quotes={}, exit_capacity={})


def recovery_events(state):
    """Entry prepays a finite exit budget, consumed rather than refunded on retry."""
    total = sum(item["events"] for item in state["exit_capacity"].values())
    for order in state["orders"].values():
        if order["status"] == "working" and order["side"] == "buy":
            total += MAX_FILLS_PER_ORDER - len(order["fills"]) + 1
    return total


def _exit_use(state, structure, *, orders=0, quotes=0):
    capacity = state["exit_capacity"][structure]
    if capacity["events"] < 1 or capacity["orders"] < orders or capacity["quotes"] < quotes:
        raise PaperCapacity("Reserved exit attempts used; project history and replenish capacity")
    capacity["events"] -= 1
    capacity["orders"] -= orders
    capacity["quotes"] -= quotes


def _capacity(state):
    reserved_orders = sum(item["orders"] for item in state["exit_capacity"].values())
    reserved_quotes = sum(item["quotes"] for item in state["exit_capacity"].values())
    if len(state["orders"]) + reserved_orders > MAX_ORDERS:
        raise PaperCapacity("Keep order slots for existing exits")
    if len(state["quotes"]) + reserved_quotes > MAX_QUOTES:
        raise PaperCapacity("Keep quote-size slots for existing exits")


def _release_exit(state, structure):
    if structure not in state["positions"] and not any(
        order["structure_id"] == structure for order in state["orders"].values()
    ):
        state["exit_capacity"].pop(structure, None)


def reserved_cash(state):
    with exact_context() as context:
        context.prec = ARITHMETIC_PRECISION
        return sum((derived(order["reserved_cash"]) for order in state["orders"].values()
                    if order["status"] == "working"), Decimal(0))


def stage_order(state, *, epoch, contract_id, product_kind, premium_factor, side, quantity, limit,
                fee_per_unit, slippage_enabled, slippage_method, price_increment,
                max_quote_age_seconds, max_spread, latency_ms, now, order_expires_at,
                proposal_digest, committed_version, currency, structure_id=None):
    """Allocate a never-reused order sequence after the caller validates admission."""
    state = validate_json(state)
    identity(epoch)
    if state.get("epoch") not in (None, epoch):
        raise PaperConflict("Prepared book belongs to another account recovery")
    state["epoch"] = epoch
    if currency != "USD" or currency != state.get("currency"):
        raise ValueError("Product and paper-account currencies must match")
    if type(committed_version) is not int or committed_version < 1:
        raise ValueError("A positive committed account version is required")
    if state.get("book_version") != 1 or len(state["orders"]) >= MAX_ORDERS:
        raise PaperCapacity("Prepared order book is unavailable or full")
    if product_kind not in ("option", "equity") or side not in ("buy", "sell"):
        raise ValueError("Unsupported prepared order")
    if not isinstance(contract_id, str) or not 1 <= len(contract_id) <= 100:
        raise ValueError("Verified contract identity is required")
    quantity = whole_quantity(quantity)
    factor = exact(premium_factor, positive=True)
    if product_kind == "equity" and factor != 1:
        raise ValueError("Equity fills use a factor of one")
    price = exact(limit, positive=True)
    fee = exact(fee_per_unit, nonnegative=True)
    increment = exact(price_increment, nonnegative=True)
    exact(max_spread, nonnegative=True)
    if (type(max_quote_age_seconds) is not int or not 1 <= max_quote_age_seconds <= MAX_QUOTE_AGE_SECONDS
            or type(latency_ms) is not int or not 0 <= latency_ms <= 60000):
        raise ValueError("Explicit supported freshness and latency settings are required")
    if not isinstance(proposal_digest, str) or len(proposal_digest) != 64:
        raise ValueError("A frozen validated proposal is required")
    created, expires = _clock(state, now), instant(order_expires_at)
    if expires <= created:
        raise ValueError("Order confirmation has expired")
    # Validate settings without inventing a slippage default.
    simulated_fill(1, factor, price, fee, slippage_enabled=slippage_enabled,
                   slippage_method=slippage_method, price_increment=increment)
    order_id = f"{epoch}:{state['next_order_sequence']}"
    if side == "buy":
        prospective = set(state["positions"]) | {o["structure_id"] for o in state["orders"].values()
                                                 if o["status"] == "working" and o["side"] == "buy"}
        if len(prospective) >= MAX_POSITIONS:
            raise PaperCapacity("Prepared holding limit reached")
        structure_id = order_id  # Never merge two trades merely because the contract matches.
        state["exit_capacity"][structure_id] = dict(events=EXIT_EVENTS, orders=EXIT_ORDERS, quotes=EXIT_QUOTES)
    else:
        position = state["positions"].get(structure_id)
        if (position is None or position["contract_id"] != contract_id
                or exact(position["premium_factor"]) != factor or position["product_kind"] != product_kind):
            raise PaperConflict("Closing requires the exact held structure")
        if any(order["side"] == "sell" and order["structure_id"] == structure_id
               for order in state["orders"].values()):
            raise PaperConflict("Project and archive the previous close before another attempt")
        already_closing = sum(o["remaining"] for o in state["orders"].values()
                              if o["status"] == "working" and o["side"] == "sell" and o["structure_id"] == structure_id)
        if quantity > sum(lot["quantity"] for lot in position["lots"]) - already_closing:
            raise PaperConflict("Closing quantity exceeds unreserved holdings")
        _exit_use(state, structure_id, orders=1)
    with exact_context() as context:
        context.prec = ARITHMETIC_PRECISION
        extra = factor * increment if slippage_enabled and slippage_method == "cash" else Decimal(0)
        unit_reserve = factor * price + fee + extra if side == "buy" else max(Decimal(0), fee + extra - factor * price)
        reservation = unit_reserve * quantity
        if side == "buy" and reservation > derived(state["cash"]) - reserved_cash(state):
            raise PaperConflict("Insufficient unreserved paper cash")
    order = dict(order_id=order_id, structure_id=structure_id, contract_id=contract_id,
                 product_kind=product_kind, currency=currency, premium_factor=str(factor), side=side, quantity=quantity,
                 remaining=quantity, filled=0, limit=str(price), fee_per_unit=str(fee),
                 slippage_enabled=slippage_enabled, slippage_method=slippage_method,
                 price_increment=str(increment), max_quote_age_seconds=max_quote_age_seconds,
                 max_spread=str(exact(max_spread)), latency_ms=latency_ms,
                 created_at=created.isoformat(), expires_at=expires.isoformat(), proposal_digest=proposal_digest,
                 reserved_cash=str(reservation), reserve_per_unit=str(unit_reserve), fills=[], status="working",
                 last_event_version=committed_version)
    state["orders"][order_id] = order
    state["next_order_sequence"] += 1
    _capacity(state)
    return state, dict(kind="paper_order_staged", order_id=order_id, proposal_digest=proposal_digest,
                       reserved_cash=str(reservation), structure_id=structure_id,
                       contract_id=contract_id, product_kind=product_kind, currency=currency,
                       side=side, quantity=quantity, limit=str(price), settings=dict(
                           fee_per_unit=str(fee), slippage_enabled=slippage_enabled,
                           slippage_method=slippage_method, price_increment=str(increment)))


def _quote(quote, order, now):
    if not isinstance(quote, dict):
        raise ValueError("A source quote is required")
    observed = instant(quote.get("observed_at"))
    received = instant(quote.get("received_at"))
    if (now - observed).total_seconds() > order["max_quote_age_seconds"] or observed > now or received > now:
        raise ValueError("Quote is stale or from the future")
    if received < observed:
        raise ValueError("Quote receipt precedes its source time")
    if quote.get("contract_id") != order["contract_id"] or quote.get("size_unit") != (
            "contracts" if order["product_kind"] == "option" else "shares"):
        raise ValueError("Quote contract or size unit differs from the order")
    bid, ask = exact(quote.get("bid"), positive=True), exact(quote.get("ask"), positive=True)
    with exact_context() as context:
        context.prec = ARITHMETIC_PRECISION
        spread = ask - bid
    if ask < bid or spread > exact(order["max_spread"]):
        raise ValueError("Quote spread is crossed or exceeds the chosen limit")
    if any(type(quote.get(key)) is not int or not 0 <= quote[key] < 2**63 for key in ("bid_size", "ask_size")):
        raise ValueError("Verified displayed size is required")
    if not isinstance(quote.get("source_id"), str) or not 1 <= len(quote["source_id"]) <= 200:
        raise ValueError("Stable source quote identity is required")
    body = dict(source_id=quote["source_id"], contract_id=quote["contract_id"], observed_at=observed.isoformat(),
                bid=str(bid), ask=str(ask), bid_size=quote["bid_size"], ask_size=quote["ask_size"], size_unit=quote["size_unit"])
    return body, digest(body)


def fill_order(state, order_id, quote, *, now, committed_version):
    """Use one source quote at most once per order, and share displayed size.

    Fill quantity is derived here from remaining order quantity and unused quote
    size. A retry cannot relabel the same quote as a new economic fill. Only a
    new verified source quote can produce another partial fill on that order.
    """
    state = validate_json(state)
    order = state["orders"].get(order_id)
    if order is None:
        raise PaperConflict("Order is absent or retired; an incoming fill cannot recreate it")
    checked = _clock(state, now)
    body, quote_digest = _quote(quote, order, checked)
    quote_key = digest([body["contract_id"], body["source_id"]])
    earlier = next((fill for fill in order["fills"] if fill["quote_key"] == quote_key), None)
    if earlier is not None:
        if earlier["quote_digest"] != quote_digest:
            raise PaperConflict("The source quote identity has changed content")
        return state, copy.deepcopy(earlier), False
    if order["status"] != "working":
        raise PaperConflict("Order is no longer working")
    if type(committed_version) is not int or committed_version <= order["last_event_version"]:
        raise ValueError("Fill must advance the committed account version")
    if checked >= instant(order["expires_at"]):
        raise PaperConflict("Order confirmation expired; no fill was created")
    if (checked - instant(order["created_at"])).total_seconds() * 1000 < order["latency_ms"]:
        raise PaperConflict("Declared simulated latency has not elapsed")
    for key, saved in list(state["quotes"].items()):
        if (checked - instant(saved["observed_at"])).total_seconds() > MAX_QUOTE_AGE_SECONDS:
            del state["quotes"][key]
    liquidity = state["quotes"].get(quote_key)
    if liquidity is not None and liquidity["quote_digest"] != quote_digest:
        raise PaperConflict("The source quote identity has changed content")
    if liquidity is None:
        if len(state["quotes"]) >= MAX_QUOTES:
            raise PaperCapacity("Quote-size ledger is full; wait for old quotes to expire")
        liquidity = dict(quote_digest=quote_digest, observed_at=body["observed_at"], used_bid=0, used_ask=0)
    side = "ask" if order["side"] == "buy" else "bid"
    available = body[f"{side}_size"] - liquidity[f"used_{side}"]
    quantity = min(order["remaining"], available)
    if quantity <= 0:
        return state, None, False
    direction = 1 if order["side"] == "buy" else -1
    with exact_context() as context:
        context.prec = ARITHMETIC_PRECISION
        fee = exact(order["fee_per_unit"]) * quantity
        fill = simulated_fill(direction * quantity, order["premium_factor"], body[side], fee,
                              slippage_enabled=order["slippage_enabled"],
                              slippage_method=order["slippage_method"], price_increment=order["price_increment"])
        actual_price = derived(fill["fill_price"])
        limit = exact(order["limit"])
        if (direction > 0 and actual_price > limit) or (direction < 0 and actual_price < limit):
            return state, None, False  # An unfilled limit is not a fabricated fill.
        cash_change = derived(fill["cash_change"])
        if direction > 0 and -cash_change > derived(order["reserve_per_unit"]) * quantity:
            raise PaperConflict("Fill cost exceeds its saved buying-power reservation")
        realized_change = Decimal(0)
        if direction > 0:
            position = state["positions"].setdefault(order["structure_id"], dict(
                contract_id=order["contract_id"], product_kind=order["product_kind"],
                premium_factor=order["premium_factor"], lots=[]))
            position["lots"].append(dict(quantity=quantity, cost_per_unit=str(-cash_change / quantity)))
        else:
            position = state["positions"].get(order["structure_id"])
            if position is None or sum(lot["quantity"] for lot in position["lots"]) < quantity:
                raise PaperConflict("Closing fill exceeds the exact structure's holdings")
            remaining = quantity
            basis = Decimal(0)
            for lot in position["lots"]:
                taken = min(lot["quantity"], remaining)
                basis += taken * derived(lot["cost_per_unit"])
                lot["quantity"] -= taken
                remaining -= taken
            position["lots"] = [lot for lot in position["lots"] if lot["quantity"]]
            if not position["lots"]:
                del state["positions"][order["structure_id"]]
            realized_change = cash_change - basis
            state["realized_result"] = str(derived(state["realized_result"]) + realized_change)
            _exit_use(state, order["structure_id"], quotes=int(quote_key not in state["quotes"]))
        state["cash"] = str(derived(state["cash"]) + cash_change)
        order["remaining"] -= quantity
        order["filled"] += quantity
        order["reserved_cash"] = str(derived(order["reserve_per_unit"]) * order["remaining"])
        receipt = dict(kind="paper_fill", fill_id=digest([order_id, quote_key]), order_id=order_id,
                       structure_id=order["structure_id"], quote_key=quote_key, quote_digest=quote_digest,
                       contract_id=order["contract_id"], product_kind=order["product_kind"],
                       currency=order["currency"], proposal_digest=order["proposal_digest"],
                       fill_sequence=len(order["fills"]) + 1, cumulative_quantity=order["filled"],
                       quantity=quantity, accounting=fill, realized_change=str(realized_change),
                       committed_version=committed_version, source_observed_at=body["observed_at"],
                       received_at=instant(quote["received_at"]).isoformat(), filled_at=checked.isoformat())
    order["fills"].append(receipt)
    order["last_event_version"] = committed_version
    if order["remaining"] == 0:
        order["status"] = "filled"
    elif len(order["fills"]) >= MAX_FILLS_PER_ORDER:
        order["status"] = "partially_filled_cancelled"
        order["reserved_cash"] = "0"
        receipt["remainder_cancelled"] = order["remaining"]
        receipt["reason"] = "Declared internal partial-fill limit reached"
    liquidity[f"used_{side}"] += quantity
    state["quotes"][quote_key] = liquidity
    _capacity(state)
    return state, copy.deepcopy(receipt), True


def cancel_order(state, order_id, *, committed_version):
    state = validate_json(state)
    order = state["orders"].get(order_id)
    if order is None:
        raise PaperConflict("Order is absent or retired")
    if order["status"] != "working":
        return state, None, False
    if type(committed_version) is not int or committed_version <= order["last_event_version"]:
        raise ValueError("Cancellation must advance the committed account version")
    order["status"] = "cancelled" if order["filled"] == 0 else "partially_filled_cancelled"
    order["reserved_cash"] = "0"
    order["last_event_version"] = committed_version
    if order["side"] == "sell":
        _exit_use(state, order["structure_id"])
    return state, dict(kind="paper_order_cancelled", order_id=order_id, filled=order["filled"],
                       unfilled=order["remaining"], structure_id=order["structure_id"]), True


def archive_order(state, order_id, *, projected_version):
    """Caller must prove this exact terminal version exists in immutable history."""
    state = validate_json(state)
    order = state["orders"].get(order_id)
    if order is None or order["status"] == "working" or order["last_event_version"] != projected_version:
        raise PaperConflict("Order cannot be retired before terminal history is verified")
    del state["orders"][order_id]
    _exit_use(state, order["structure_id"])
    _release_exit(state, order["structure_id"])
    # next_order_sequence is never reduced, so absence permanently refuses late fills.
    return state, dict(kind="paper_order_archived", order_id=order_id, terminal_version=projected_version)


def replenish_exit_capacity(state, *, now):
    """Caller must first prove all pending history is durably projected."""
    state = validate_json(state)
    if any(order["side"] == "sell" for order in state["orders"].values()):
        raise PaperConflict("Project and archive retained closes before replenishing")
    checked = _clock(state, now)
    for key, quote in list(state["quotes"].items()):
        if (checked - instant(quote["observed_at"])).total_seconds() > MAX_QUOTE_AGE_SECONDS:
            del state["quotes"][key]
    for structure in state["exit_capacity"]:
        state["exit_capacity"][structure] = dict(events=EXIT_EVENTS, orders=EXIT_ORDERS, quotes=EXIT_QUOTES)
    _capacity(state)
    return state, dict(kind="paper_exit_capacity_replenished")
