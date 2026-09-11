"""D4 regression: adapter quote/expiration truth.

- Contracts with expiry before today are dropped; 0DTE (today) is kept.
- result["expiries"] lists only expiries actually fetched (requested vs
  returned coverage distinguished).
- Nonfinite numeric fields sanitize to None; nonfinite strike drops the
  contract. Strict-JSON serializable output.
- spot travels with its spot_source provenance tag.
"""

import json
import math
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.public_api_adapter as adapter
from services.public_budget import PublicBudget


def make_contract(**kw):
    c = MagicMock()
    c.symbol = kw.get("symbol", "SPY261231C00530000")
    c.expiration = kw.get("expiration", "2026-12-31")
    c.strike = kw.get("strike", 530.0)
    c.iv = kw.get("iv", 0.15)
    c.delta = kw.get("delta", 0.45)
    c.gamma = kw.get("gamma", 0.01)
    c.theta = kw.get("theta", -0.05)
    c.vega = kw.get("vega", 0.1)
    c.bid = kw.get("bid", 1.0)
    c.ask = kw.get("ask", 1.2)
    c.mid = kw.get("mid", 1.1)
    c.last = kw.get("last", 1.1)
    c.bid_size = kw.get("bid_size", 10)
    c.ask_size = kw.get("ask_size", 10)
    c.volume = kw.get("volume", 500)
    c.open_interest = kw.get("open_interest", 1000)
    return c


def make_broker(chains):
    broker = MagicMock()
    trading = MagicMock()
    trading.account_id = "acc-123"
    broker.get_trading_account.return_value = trading
    broker.get_option_expirations = AsyncMock(return_value=list(chains))
    quote = MagicMock()
    quote.mid_price = 520.50
    quote.last = 520.50
    quote.symbol = "SPY"
    broker.get_quotes = AsyncMock(return_value=[quote])
    broker.get_option_chain_parsed = AsyncMock(
        side_effect=lambda s, e, a: {"calls": chains[e], "puts": []}
    )
    return broker


@pytest.fixture
def env():
    adapter._CHAIN_CACHE.clear()
    budget = PublicBudget(capacity=60, refill_per_sec=60.0, max_inflight=99)
    broker = make_broker({"2026-12-31": [make_contract()]})
    patches = [
        patch.object(adapter, "_get_broker", new=AsyncMock(return_value=broker)),
        patch("services.public_budget.budget", budget),
    ]
    for p in patches:
        p.start()
    yield broker
    for p in patches:
        p.stop()
    adapter._CHAIN_CACHE.clear()


@pytest.mark.asyncio
async def test_expired_dropped_today_kept(env):
    today = datetime.now(UTC).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    today_s = today.isoformat()
    broker = env
    broker.get_option_expirations = AsyncMock(return_value=[yesterday, today_s])
    old = make_contract(symbol="SPYOLD", expiration=yesterday)
    new = make_contract(symbol="SPYNEW", expiration=today_s)
    broker.get_option_chain_parsed = AsyncMock(
        side_effect=lambda s, e, a: {"calls": [old] if e == yesterday else [new], "puts": []}
    )
    result = await adapter.fetch_chain_from_public_api("SPY", max_expiries=2)
    assert result is not None
    osis = [c["osi"] for c in result["contracts"]]
    assert "SPYOLD" not in osis
    assert "SPYNEW" in osis


@pytest.mark.asyncio
async def test_expiries_lists_only_fetched(env):
    broker = env
    broker.get_option_expirations = AsyncMock(return_value=["2026-12-31", "2027-01-15"])

    async def flaky(symbol, exp, account_id):
        if exp == "2027-01-15":
            raise ConnectionError("chain down")
        return {"calls": [make_contract()], "puts": []}

    broker.get_option_chain_parsed = AsyncMock(side_effect=flaky)
    result = await adapter.fetch_chain_from_public_api("SPY", max_expiries=2)
    assert result is not None
    assert result["expiries"] == ["2026-12-31"]


@pytest.mark.asyncio
async def test_nonfinite_fields_sanitized(env):
    broker = env
    bad = make_contract(
        symbol="SPYBAD",
        iv=float("nan"),
        delta=float("inf"),
        gamma=float("-inf"),
        theta=float("nan"),
        vega=float("nan"),
        bid=float("nan"),
        ask=float("inf"),
        mid=float("nan"),
        last=float("-inf"),
    )
    nan_strike = make_contract(symbol="SPYNANSTRIKE", strike=float("nan"))
    broker.get_option_chain_parsed = AsyncMock(
        return_value={"calls": [bad, nan_strike], "puts": []}
    )
    broker.get_option_expirations = AsyncMock(return_value=["2026-12-31"])
    result = await adapter.fetch_chain_from_public_api("SPY", max_expiries=1)
    assert result is not None
    json.dumps(result, allow_nan=False)
    by_osi = {c["osi"]: c for c in result["contracts"]}
    assert "SPYNANSTRIKE" not in by_osi
    row = by_osi["SPYBAD"]
    for key in ("iv", "delta", "gamma", "theta", "vega", "bid", "ask", "mid", "last"):
        v = row[key]
        assert v is None or (not isinstance(v, float) or math.isfinite(v)), key


@pytest.mark.asyncio
async def test_spot_carries_source(env):
    result = await adapter.fetch_chain_from_public_api("SPY", max_expiries=1)
    assert result is not None
    assert "spot_source" in result and result["spot_source"]
