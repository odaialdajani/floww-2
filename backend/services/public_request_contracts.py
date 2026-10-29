"""Pure Public request validation; no authentication, routing or order activation."""
import copy
from decimal import Decimal, InvalidOperation
from uuid import UUID


def decimal_text(value, name, *, positive=True):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{name} must be a finite decimal")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a finite decimal") from exc
    if not number.is_finite() or (positive and number <= 0):
        raise ValueError(f"{name} must be a finite positive decimal")
    return str(value)


def replacement_body(order_id, request_id, order_type, expiration, quantity,
                     amount, limit_price, stop_price, original_order):
    identities = []
    for value in (order_id, request_id):
        try:
            parsed = UUID(value)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Replacement identities must be UUIDs") from exc
        if str(parsed) != value:
            raise ValueError("Replacement identities must use canonical UUID spelling")
        identities.append(parsed)
    if identities[0] == identities[1]:
        raise ValueError("Replacement request must have a distinct identity")
    if not isinstance(original_order, dict) or original_order.get("orderId") != order_id:
        raise ValueError("An exact original order snapshot is required")
    # This wrapper's bounded contract is closing-leg repricing only. Unknown
    # bracket role and bracket entries never become valid by assuming a role.
    if not original_order.get("parentOrderId"):
        raise ValueError("Only an identified bracket closing leg may be repriced")
    try:
        parent = UUID(original_order["parentOrderId"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Closing-leg parent identity must be a UUID") from exc
    if identities[1] == parent:
        raise ValueError("Replacement identity cannot reuse the parent identity")
    if (quantity is None) == (amount is None):
        raise ValueError("Exactly one of quantity and amount is required")
    if order_type not in {"LIMIT", "STOP", "STOP_LIMIT"}:
        raise ValueError("A closing-leg replacement must have a priced order type")
    if not isinstance(expiration, dict) or not expiration.get("timeInForce"):
        raise ValueError("The full original expiration is required")
    if original_order.get("orderType") != order_type or original_order.get("expiration") != expiration:
        raise ValueError("Closing-leg type and expiration cannot change")
    field, value = ("quantity", quantity) if quantity is not None else ("amount", amount)
    value = decimal_text(value, field)
    original = decimal_text(original_order.get(field), field)
    if Decimal(value) != Decimal(original):
        raise ValueError("Closing-leg size cannot change")
    body = {"orderId": order_id, "requestId": request_id, "orderType": order_type,
            "expiration": copy.deepcopy(expiration), field: value}
    for key, price, required in (("limitPrice", limit_price, order_type in {"LIMIT", "STOP_LIMIT"}),
                                 ("stopPrice", stop_price, order_type in {"STOP", "STOP_LIMIT"})):
        if required or price is not None:
            body[key] = decimal_text(price, key)
    return body


def strategy_body(base_symbol, option_legs, equity_leg=None):
    if not isinstance(base_symbol, str) or not base_symbol.strip():
        raise ValueError("A strategy underlying is required")
    if not isinstance(option_legs, list) or not option_legs:
        raise ValueError("Exact option legs are required")
    for leg in option_legs + ([equity_leg] if equity_leg is not None else []):
        if not isinstance(leg, dict) or not isinstance(leg.get("symbol"), str) or not leg["symbol"].strip():
            raise ValueError("Every leg must identify its symbol")
        if leg.get("side") not in {"BUY", "SELL"}:
            raise ValueError("Every leg must identify its side")
        if type(leg.get("ratioQuantity")) is not int or leg["ratioQuantity"] <= 0:
            raise ValueError("Leg ratios must be positive integers")
        if "openCloseIndicator" in leg and leg["openCloseIndicator"] not in {"OPEN", "CLOSE"}:
            raise ValueError("Invalid leg position effect")
    body = {"baseSymbol": base_symbol, "optionLegs": copy.deepcopy(option_legs)}
    if equity_leg is not None:
        body["equityLeg"] = copy.deepcopy(equity_leg)
    return body


def strategy_response(value, request):
    if not isinstance(value, dict) or not isinstance(value.get("strategyLegs"), list) or not value["strategyLegs"]:
        raise ValueError("Strategy response is missing legs")
    if not isinstance(value.get("strategyName"), str) or not value["strategyName"]:
        raise ValueError("Strategy response is missing its name")
    for key in ("price", "bid", "ask"):
        if not isinstance(value.get(key), str):
            raise ValueError(f"Strategy response is missing decimal text: {key}")
        decimal_text(value[key], key, positive=False)
    for leg in value["strategyLegs"] + ([value["equityQuote"]] if value.get("equityQuote") is not None else []):
        if not isinstance(leg, dict) or not isinstance(leg.get("instrument"), dict):
            raise ValueError("Strategy response has an invalid instrument")
        candidate = {"symbol": leg["instrument"].get("symbol"),
                     "side": leg.get("side"), "ratioQuantity": leg.get("ratioQuantity")}
        if "openCloseIndicator" in leg:
            candidate["openCloseIndicator"] = leg["openCloseIndicator"]
        strategy_body("response", [candidate])
        if leg["instrument"].get("baseSymbol") not in (None, request["baseSymbol"]):
            raise ValueError("Strategy response has a different underlying")
        quote = leg.get("quote")
        if quote is not None and (not isinstance(quote, dict) or
                any(not isinstance(quote.get(k), str) or not quote[k] for k in ("symbol", "timestamp", "signature"))):
            raise ValueError("Strategy leg quote is missing signed-quote fields")
        if quote is not None and quote["symbol"] != candidate["symbol"]:
            raise ValueError("Signed quote identity differs from its instrument")
    unmatched = list(value["strategyLegs"])
    for expected in request["optionLegs"]:
        match = next((leg for leg in unmatched if
            leg["instrument"]["symbol"] == expected["symbol"] and
            leg["side"] == expected["side"] and leg["ratioQuantity"] == expected["ratioQuantity"] and
            ("openCloseIndicator" not in expected or leg.get("openCloseIndicator") == expected["openCloseIndicator"])), None)
        if match is None:
            raise ValueError("Strategy response does not match the requested legs")
        unmatched.remove(match)
    if unmatched:
        raise ValueError("Strategy response contains unrequested legs")
    expected_equity, actual_equity = request.get("equityLeg"), value.get("equityQuote")
    if (expected_equity is None) != (actual_equity is None):
        raise ValueError("Strategy equity leg differs from the request")
    if expected_equity is not None and (
        actual_equity["instrument"]["symbol"] != expected_equity["symbol"] or
        actual_equity["side"] != expected_equity["side"] or
        actual_equity["ratioQuantity"] != expected_equity["ratioQuantity"] or
        ("openCloseIndicator" in expected_equity and actual_equity.get("openCloseIndicator") != expected_equity["openCloseIndicator"])
    ):
        raise ValueError("Strategy equity identity differs from the request")
    # Preserve raw UNKNOWN/UNDECIDED, signs, precision and signatures. This
    # validates structure only; it does not authenticate a signed quote.
    return value
