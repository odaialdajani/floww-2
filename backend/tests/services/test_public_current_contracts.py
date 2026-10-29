"""Current documented transport contracts. Synthetic inputs; no network."""
import copy
import json

import httpx
import pytest

from services.public_api import BASE_URL, PublicBroker

OLD = "00000000-0000-4000-8000-000000000001"
NEW = "00000000-0000-4000-8000-000000000002"
ORIGINAL = {"orderId": OLD, "parentOrderId": "00000000-0000-4000-8000-000000000003", "orderType": "LIMIT",
            "expiration": {"timeInForce": "DAY"}, "quantity": "10"}
LEGS = [{"symbol": "SYNTHETIC-CALL", "side": "BUY", "ratioQuantity": 1}]
QUOTE = {"strategyLegs": [{"instrument": {"symbol": "SYNTHETIC-CALL"},
          "side": "BUY", "ratioQuantity": 1}], "price": "-1.2500", "bid": "-1.2500",
         "ask": "0.2000", "strategyName": "Synthetic", "debitCredit": "UNKNOWN"}


def broker(handler):
    client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    b = PublicBroker(secret_key="offline-only", client=client)
    b._access_token, b._token_expires_at = "offline", float("inf")
    return b


@pytest.mark.asyncio
async def test_replace_full_put_and_no_invented_fill():
    seen = []
    def handle(r):
        seen.append((r.method, r.url.path, json.loads(r.content)))
        return httpx.Response(200, json={"orderId": NEW})
    b = broker(handle)
    try:
        out = await b.replace_order("offline-account", OLD, limit_price="226.00", quantity="10",
              request_id=NEW, order_type="LIMIT", expiration={"timeInForce": "DAY"}, original_order=ORIGINAL)
    finally:
        await b.close()
    assert seen == [("PUT", "/userapigateway/trading/offline-account/order",
        {"orderId": OLD, "requestId": NEW, "orderType": "LIMIT", "expiration": {"timeInForce": "DAY"},
         "quantity": "10", "limitPrice": "226.00"})]
    assert out == {"orderId": NEW}


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"quantity": "11"}, {"request_id": OLD},
    {"original_order": None}, {"original_order": {**ORIGINAL, "parentOrderId": None}},
    {"amount": "100"}, {"limit_price": "NaN"}, {"limit_price": None},
    {"request_id": OLD.replace("-", "")}, {"request_id": ORIGINAL["parentOrderId"]}])
async def test_invalid_replacement_never_authenticates_or_sends(change):
    sent = []
    b = broker(lambda r: sent.append(r))
    b._access_token = None
    args = dict(limit_price="226.00", quantity="10", request_id=NEW, order_type="LIMIT",
                expiration={"timeInForce": "DAY"}, original_order=ORIGINAL)
    args.update(change)
    try:
        with pytest.raises(ValueError):
            await b.replace_order("offline-account", OLD, **args)
        assert not sent
    finally:
        await b.close()


@pytest.mark.asyncio
async def test_search_post_filters_and_truncation_without_pagination():
    seen = []
    def handle(r):
        seen.append((r.method, r.url.path, json.loads(r.content)))
        return httpx.Response(200, json={"orders": [{}] * 500})
    b = broker(handle)
    try:
        out = await b.search_orders("offline-account", status="FILLED", created_after="2026-10-01T00:00:00Z")
        assert seen == [("POST", "/userapigateway/trading/offline-account/order/search",
                         {"status": "FILLED", "createdAfter": "2026-10-01T00:00:00Z"})]
        assert out["possible_truncation"] is True and out["complete_history"] is False
    finally:
        await b.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"orders": []}, {"orders": [{"orderId": OLD}]}, None, "malformed"])
async def test_search_404_preserves_status_and_original_body(body):
    def handle(r):
        return httpx.Response(404, content=b"malformed" if body == "malformed" else json.dumps(body).encode())
    b = broker(handle)
    try:
        with pytest.raises(httpx.HTTPStatusError) as raised:
            await b.search_orders("offline-account")
        assert raised.value.response.status_code == 404
        assert raised.value.response.content == (b"malformed" if body == "malformed" else json.dumps(body).encode())
    finally:
        await b.close()


@pytest.mark.asyncio
async def test_strategy_exact_legs_decimal_text_and_unknown_enum():
    seen = []
    def handle(r):
        seen.append((r.method, r.url.path, json.loads(r.content)))
        return httpx.Response(200, json=QUOTE)
    b = broker(handle)
    try:
        out = await b.get_strategy_quote("offline-account", "SYNTH", LEGS)
        assert seen == [("POST", "/userapigateway/option-details/offline-account/strategy-details/quote",
                         {"baseSymbol": "SYNTH", "optionLegs": LEGS})]
        assert out == QUOTE
    finally:
        await b.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("ratio", [True, 0, -1, 1.5])
async def test_strategy_invalid_ratio_never_sends(ratio):
    sent = []
    b = broker(lambda r: sent.append(r))
    try:
        with pytest.raises(ValueError):
            await b.get_strategy_quote("offline-account", "SYNTH", [{**LEGS[0], "ratioQuantity": ratio}])
        assert not sent
    finally:
        await b.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["strategyLegs", "price", "bid", "ask", "strategyName"])
async def test_strategy_incomplete_response_is_not_success(missing):
    value = copy.deepcopy(QUOTE)
    value.pop(missing)
    b = broker(lambda r: httpx.Response(200, json=value))
    try:
        with pytest.raises(ValueError):
            await b.get_strategy_quote("offline-account", "SYNTH", LEGS)
    finally:
        await b.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("margin", [False, True])
async def test_option_preflight_preserves_effect_type_and_margin(margin):
    seen = []
    def handle(r):
        seen.append(json.loads(r.content))
        return httpx.Response(200, json={"estimate": "offline"})
    b = broker(handle)
    try:
        await b.preflight_single_leg("offline-account", "SYNTHETIC-CALL", "BUY", "LIMIT", 1,
            limit_price="1.25", instrument_type="OPTION", open_close_indicator="CLOSE", use_margin=margin)
        assert seen[0]["instrument"]["type"] == "OPTION"
        assert seen[0]["openCloseIndicator"] == "CLOSE" and seen[0]["useMargin"] is margin
    finally:
        await b.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 503])
async def test_replacement_failure_is_preserved_and_never_retried(status):
    requests = []
    def handle(r):
        requests.append(r)
        return httpx.Response(status, json={"reason": "synthetic refusal"})
    b = broker(handle)
    try:
        with pytest.raises(httpx.HTTPStatusError) as refused:
            await b.replace_order("offline-account", OLD, limit_price="226.00", quantity="10",
                request_id=NEW, order_type="LIMIT", expiration=ORIGINAL["expiration"], original_order=ORIGINAL)
        assert refused.value.response.status_code == status
        assert refused.value.response.json() == {"reason": "synthetic refusal"}
        assert len(requests) == 1
    finally:
        await b.close()


@pytest.mark.asyncio
async def test_replacement_timeout_is_unknown_and_never_retried():
    requests = []
    def handle(r):
        requests.append(r)
        raise httpx.ReadTimeout("synthetic unknown outcome", request=r)
    b = broker(handle)
    try:
        with pytest.raises(httpx.ReadTimeout):
            await b.replace_order("offline-account", OLD, limit_price="226.00", quantity="10",
                request_id=NEW, order_type="LIMIT", expiration=ORIGINAL["expiration"], original_order=ORIGINAL)
        assert len(requests) == 1
    finally:
        await b.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{"instrument_type": "OPTION"},
    {"use_margin": False, "validate_order": False}, {"use_margin": "false"},
    {"use_margin": False, "validate_order": "false"}])
async def test_preflight_invalid_intent_never_authenticates(kwargs):
    sent = []
    b = broker(lambda r: sent.append(r))
    b._access_token = None
    try:
        with pytest.raises(ValueError):
            await b.preflight_single_leg("offline-account", "SYNTH", "BUY", "LIMIT", 1, **kwargs)
        assert not sent
    finally:
        await b.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["symbol", "side", "ratio", "effect", "quote", "duplicate", "equity"])
async def test_strategy_response_must_match_requested_identity(change):
    result = copy.deepcopy(QUOTE)
    leg = result["strategyLegs"][0]
    leg["openCloseIndicator"] = "OPEN"
    if change == "symbol": leg["instrument"]["symbol"] = "FOREIGN-CALL"
    if change == "side": leg["side"] = "SELL"
    if change == "ratio": leg["ratioQuantity"] = 50
    if change == "effect": leg["openCloseIndicator"] = "CLOSE"
    if change == "quote": leg["quote"] = {"symbol": "FOREIGN-CALL", "timestamp": "2026-10-29T14:00:00Z", "signature": "offline"}
    if change == "duplicate": result["strategyLegs"].append(copy.deepcopy(leg))
    if change == "equity": result["equityQuote"] = copy.deepcopy(leg)
    b = broker(lambda r: httpx.Response(200, json=result))
    try:
        with pytest.raises(ValueError):
            await b.get_strategy_quote("offline-account", "SYNTH", [{**LEGS[0], "openCloseIndicator": "OPEN"}])
    finally:
        await b.close()
