"""C2-D wrapper-contract pins (Hermes-Architect, 2026-10-24, lane
backend-lane-20261023 at 4fb9e615, product parent 9b1d1179).

Pins the HTTP request/response CONTRACT of the in-repo Public.com wrapper
(services/public_api.py PublicBroker) for the operations the C2-D enumeration
(takeover-20261022/c2-public30/C2-D-OPERATIONS-20261024.json) found
implemented but untested, plus the mounted-but-untested catalog read:

  * token lifecycle (secret -> access token, cache, refresh at expiry)
  * get_all_instruments (MOUNTED_NOT_TESTED — market_catalog bootstrap)
  * get_instrument (cache population), get_option_greeks, get_history,
    get_unrealized_tax_lots, get_order_v2, replace_order, search_orders,
    get_strategy_quote, preflight_multi_leg
  * cancel_order F25 semantics: DELETE transport, empty body => CANCEL_PENDING
    with raw_empty, JSON body parsed verbatim

Scripted-gateway simulator only (httpx.MockTransport): these pins prove the
WRAPPER's exact request shapes and response handling; they prove NOTHING
about live provider acceptance (the documented landmine: a mocked transport
passes green on values the real gateway rejects). No network, no account,
no order — the entitled/native half of every PUBLIC row stays EXTERNAL_HOLD.
"""
import json

import httpx
import pytest

from services.public_api import BASE_URL, PublicBroker


def _broker(handler):
    def auth_aware(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/access-tokens"):
            return _json_response({"accessToken": "tok-1"})
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(auth_aware), base_url=BASE_URL)
    return PublicBroker(secret_key="test-secret", client=client)


def _json_response(payload):
    return httpx.Response(200, json=payload)


@pytest.mark.asyncio
async def test_token_lifecycle_mints_caches_and_refreshes():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode())
        seen.append(body)
        return _json_response({"accessToken": f"tok-{len(seen)}"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)
    broker = PublicBroker(secret_key="test-secret", client=client)
    token = await broker.auth(10)  # explicit validity on the first mint
    assert token == "tok-1"
    assert broker._access_token == "tok-1"
    await broker._ensure_token()  # cached token: no re-mint
    assert seen == [{"validityInMinutes": 10, "secret": "test-secret"}]
    broker._token_expires_at = 0.0  # force expiry
    await broker._ensure_token()  # refresh uses the DEFAULT validity
    assert seen == [{"validityInMinutes": 10, "secret": "test-secret"},
                    {"validityInMinutes": 55, "secret": "test-secret"}]
    assert broker._access_token == "tok-2"
    assert broker._auth_headers() == {"Authorization": "Bearer tok-2"}
    await broker.close()


@pytest.mark.asyncio
async def test_get_all_instruments_contract():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params)))
        if dict(request.url.params).get("typeFilter") == "EQUITY":
            return _json_response({"instruments": [{"symbol": "SPY", "type": "EQUITY"}]})
        return _json_response({})  # gateway omits the key: wrapper maps to []

    broker = _broker(handler)
    rows = await broker.get_all_instruments(type_filter=["EQUITY"], trading_filter=["ACTIVE"])
    assert rows == [{"symbol": "SPY", "type": "EQUITY"}]
    method, path, params = seen[0]
    assert method == "GET" and path == "/userapigateway/trading/instruments"
    assert params["typeFilter"] == "EQUITY" and params["tradingFilter"] == "ACTIVE"
    assert await broker.get_all_instruments() == []  # absent key => empty list, no crash
    await broker.close()


@pytest.mark.asyncio
async def test_get_instrument_populates_cache():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/userapigateway/trading/instruments/SPY/EQUITY")
        return _json_response({"symbol": "SPY", "type": "EQUITY", "tickSize": 0.01})

    broker = _broker(handler)
    data = await broker.get_instrument("SPY", "EQUITY")
    assert data["tickSize"] == 0.01
    assert broker._instrument_cache["SPY:EQUITY"] == data
    await broker.close()


@pytest.mark.asyncio
async def test_get_option_greeks_request_shape():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(request.url.params)))
        return _json_response({"greeks": {"delta": 0.5}})

    broker = _broker(handler)
    out = await broker.get_option_greeks(["SPY261230C00500000"], account_id="acct-1")
    assert out == {"greeks": {"delta": 0.5}}
    path, params = seen[0]
    assert path == "/userapigateway/option-details/acct-1/greeks"
    assert params["osiSymbols"] == "SPY261230C00500000"
    await broker.close()


@pytest.mark.asyncio
async def test_get_history_paging_params():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return _json_response({"history": [], "nextToken": "n-2"})

    broker = _broker(handler)
    out = await broker.get_history("acct-1", page_size=25, start="2026-10-01",
                                   end="2026-10-23", next_token="n-1")
    assert out["nextToken"] == "n-2"
    assert seen[0] == {"pageSize": "25", "start": "2026-10-01",
                      "end": "2026-10-23", "nextToken": "n-1"}
    await broker.close()


@pytest.mark.asyncio
async def test_get_unrealized_tax_lots_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/userapigateway/trading/acct-1/taxlots/unrealized")
        return _json_response({"lots": [{"symbol": "SPY", "unrealizedPl": 12.5}]})

    broker = _broker(handler)
    assert (await broker.get_unrealized_tax_lots("acct-1"))["lots"][0]["symbol"] == "SPY"
    await broker.close()


@pytest.mark.asyncio
async def test_get_order_v2_returns_typed_payload_verbatim():
    payload = {"orderId": "o-1", "status": "FILLED", "legs": [], "bracket": None}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/userapigateway/trading/acct-1/order/o-1/v2")
        return _json_response(payload)

    broker = _broker(handler)
    assert await broker.get_order_v2("acct-1", "o-1") == payload
    await broker.close()


@pytest.mark.asyncio
async def test_replace_order_payload_and_pending_on_empty_body():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), json.loads(request.read().decode())))
        return httpx.Response(200, content=b"")  # documented empty-body gateway case

    broker = _broker(handler)
    out = await broker.replace_order("acct-1", "o-1", limit_price=1.5, quantity=2,
                                     time_in_force="GTC")
    url, body = seen[0]
    assert url.endswith("/userapigateway/trading/acct-1/order/o-1/replace")
    assert body == {"limitPrice": "1.5", "quantity": 2, "expiration": {"timeInForce": "GTC"}}
    assert out == {"orderId": "o-1", "status": "REPLACE_PENDING", "raw_empty": True}
    await broker.close()


@pytest.mark.asyncio
async def test_search_orders_request_params():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return _json_response({"orders": [], "nextToken": None})

    broker = _broker(handler)
    await broker.search_orders("acct-1", start="2026-10-01", end="2026-10-23",
                               limit=50, next_token="tok")
    assert seen[0] == {"limit": "50", "start": "2026-10-01",
                        "end": "2026-10-23", "nextToken": "tok"}
    await broker.close()


@pytest.mark.asyncio
async def test_get_strategy_quote_posts_exact_leg_definition():
    seen = []
    legs = [{"symbol": "SPY261230C00500000", "side": "BUY", "quantity": 1}]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), json.loads(request.read().decode())))
        return _json_response({"debit": 1.25, "credit": 0.0})

    broker = _broker(handler)
    out = await broker.get_strategy_quote("acct-1", legs)
    url, body = seen[0]
    assert url.endswith("/userapigateway/option-details/acct-1/strategy-quote")
    assert body == {"legs": legs}
    assert out == {"debit": 1.25, "credit": 0.0}
    await broker.close()


@pytest.mark.asyncio
async def test_preflight_multi_leg_payload_contract():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), json.loads(request.read().decode())))
        return _json_response({"estimate": {"fees": 0.65}})

    broker = _broker(handler)
    legs = [{"symbol": "SPY261230C00500000", "side": "BUY", "quantity": 1}]
    out = await broker.preflight_multi_leg("acct-1", legs, order_type="LIMIT",
                                           quantity=2, limit_price=3.5, stop_price=2.5,
                                           time_in_force="GTC", expiration_time="2026-10-30T16:00")
    url, body = seen[0]
    assert url.endswith("/userapigateway/trading/acct-1/preflight/multi-leg")
    assert body == {"orderType": "LIMIT",
                    "expiration": {"timeInForce": "GTC", "expirationTime": "2026-10-30T16:00"},
                    "quantity": 2, "legs": legs, "validateOrder": True,
                    "limitPrice": "3.5", "stopPrice": "2.5"}
    assert out["estimate"]["fees"] == 0.65
    await broker.close()


@pytest.mark.asyncio
async def test_cancel_order_delete_transport_and_pending_semantics():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        if seen and request.method == "DELETE":
            return httpx.Response(200, content=b"")  # documented empty success body
        return _json_response({"orderId": "o-9", "status": "CANCELED"})

    broker = _broker(handler)
    out = await broker.cancel_order("acct-1", "o-9")
    # F25: DELETE is the documented transport; empty body is PENDING, not canceled.
    assert seen == ["DELETE"]
    assert out == {"orderId": "o-9", "status": "CANCEL_PENDING", "raw_empty": True}
    await broker.close()


@pytest.mark.asyncio
async def test_cancel_order_parses_json_body_verbatim():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return _json_response({"orderId": "o-9", "status": "CANCELED"})

    broker = _broker(handler)
    assert (await broker.cancel_order("acct-1", "o-9"))["status"] == "CANCELED"
    await broker.close()
