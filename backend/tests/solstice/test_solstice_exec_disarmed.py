"""T12 disarmed execution adapter tests: idempotency, unknown ACK, partial fills,
child lifecycle. No live calls — all transport mocked. Execution stays disarmed."""

import sys

sys.path.insert(0, "backend")

from unittest.mock import AsyncMock, MagicMock


def _broker():
    from services.public_api import PublicBroker
    b = PublicBroker.__new__(PublicBroker)
    b._access_token = "tok"
    b._token_expires_at = 9999999999.0
    return b


def test_place_order_mints_uuid_idempotency():
    import asyncio
    b = _broker()
    seen = {}

    async def fake_post(url, json=None, headers=None):
        seen.update(json)
        r = MagicMock()
        r.raise_for_status.return_value = None
        r.json.return_value = {"orderId": json["orderId"], "status": "PENDING",
                               "instrument": json["instrument"], "orderSide": json["orderSide"],
                               "orderType": json["orderType"], "quantity": json["quantity"]}
        return r

    b._client = MagicMock()
    b._client.post = fake_post
    o1 = asyncio.run(b.place_order("a", "SPY260101C00500000", "BUY", "LIMIT", 1, limit_price=1.0))
    o2 = asyncio.run(b.place_order("a", "SPY260101C00500000", "BUY", "LIMIT", 1, limit_price=1.0))
    assert o1.order_id and o2.order_id and o1.order_id != o2.order_id  # one UUID per intent
    assert seen["orderId"] == o2.order_id  # identical resubmission would reuse same ID


def test_cancel_empty_body_is_pending_not_canceled():
    import asyncio
    b = _broker()
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.text = ""
    r.json.side_effect = ValueError("empty")
    b._client = MagicMock()
    b._client.delete = AsyncMock(return_value=r)
    out = asyncio.run(b.cancel_order("a", "oid"))
    assert out["status"] == "CANCEL_PENDING"  # pending cancellation is NOT canceled


def test_parse_order_preserves_bracket_linkage():
    from services.public_api import PublicBroker
    o = PublicBroker._parse_order(
        {"orderId": "x", "status": "OPEN", "instrument": {"symbol": "S"},
         "orderSide": "BUY", "orderType": "LIMIT", "quantity": 1,
         "openCloseIndicator": "OPEN", "averagePrice": 2.5,
         "bracketId": "b1", "parentOrderId": None,
         "legs": [{"side": "BUY", "openCloseIndicator": "OPEN"}]}, "a")
    assert o.open_close == "OPEN" and o.average_price == 2.5
    assert o.bracket_id == "b1" and len(o.legs) == 1


def test_adapter_has_no_order_method():
    import services.public_api_adapter as ada
    assert not hasattr(ada, "place_order")
    assert not hasattr(ada, "place_multileg_order")
    assert not hasattr(ada, "cancel_order")
